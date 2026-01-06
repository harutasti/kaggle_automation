import argparse
import asyncio
import datetime as dt
import difflib
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from tqdm import tqdm

try:
    # Ensure crawler prints flush promptly when invoked via subprocess.
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass


# --------------------------------------------------------------------------- #
# Cache helpers                                                               #
# --------------------------------------------------------------------------- #
def _utcnow_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _parse_iso(ts: Optional[str]) -> Optional[dt.datetime]:
    if not ts:
        return None
    try:
        value = ts
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return dt.datetime.fromisoformat(value)
    except Exception:
        return None


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _summarize_diff(old_text: Optional[str], new_text: Optional[str], max_samples: int = 6) -> Dict[str, Any]:
    old_text = old_text or ""
    new_text = new_text or ""
    old_lines = [line.rstrip() for line in old_text.splitlines()]
    new_lines = [line.rstrip() for line in new_text.splitlines()]

    added_lines: List[str] = []
    removed_lines: List[str] = []
    for line in difflib.unified_diff(old_lines, new_lines, n=0):
        if line.startswith(("---", "+++", "@@")):
            continue
        if line.startswith("+"):
            value = line[1:].strip()
            if value and value not in added_lines:
                added_lines.append(value)
        elif line.startswith("-"):
            value = line[1:].strip()
            if value and value not in removed_lines:
                removed_lines.append(value)

    old_headings = set(_extract_title(line) for line in old_lines if line.strip().startswith("#"))
    new_headings = set(_extract_title(line) for line in new_lines if line.strip().startswith("#"))
    old_headings.discard("")
    new_headings.discard("")

    return {
        "added_headings": sorted(new_headings - old_headings)[:max_samples],
        "removed_headings": sorted(old_headings - new_headings)[:max_samples],
        "added_lines_sample": added_lines[:max_samples],
        "removed_lines_sample": removed_lines[:max_samples],
        "added_lines_count": len(added_lines),
        "removed_lines_count": len(removed_lines),
    }


def _render_summary_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Crawler Summary (Cache/Diff)",
        "",
        f"- competition_id: {payload.get('competition_id', 'unknown')}",
        f"- generated_at: {payload.get('generated_at', 'unknown')}",
        f"- cache_enabled: {payload.get('cache_enabled', False)}",
        f"- cache_ttl_hours: {payload.get('cache_ttl_hours', 'unknown')}",
    ]
    stats = payload.get("stats", {}) or {}
    lines.append(
        "- stats: fetched={fetched}, skipped={skipped}, new={new}, updated={updated}, unchanged={unchanged}".format(
            fetched=stats.get("fetched", 0),
            skipped=stats.get("skipped", 0),
            new=stats.get("new", 0),
            updated=stats.get("updated", 0),
            unchanged=stats.get("unchanged", 0),
        )
    )
    lines.append("")

    changes = payload.get("changes", []) or []
    if not changes:
        lines.append("No content changes detected. Cached artifacts reused.")
        return "\n".join(lines)

    lines.append("## Changes")
    for change in changes:
        title = change.get("title") or change.get("page_type") or "unknown"
        path = change.get("path", "unknown")
        lines.append(f"- [{change.get('change', 'updated')}] {title} ({path})")
        diff_summary = change.get("diff_summary", {}) or {}
        added = ", ".join(diff_summary.get("added_headings", []) or [])
        removed = ", ".join(diff_summary.get("removed_headings", []) or [])
        if added:
            lines.append(f"  - added_headings: {added}")
        if removed:
            lines.append(f"  - removed_headings: {removed}")
        if diff_summary.get("added_lines_sample"):
            sample = "; ".join(diff_summary["added_lines_sample"])
            lines.append(f"  - added_lines_sample: {sample}")
        if diff_summary.get("removed_lines_sample"):
            sample = "; ".join(diff_summary["removed_lines_sample"])
            lines.append(f"  - removed_lines_sample: {sample}")
    return "\n".join(lines)


class CrawlerCache:
    def __init__(
        self,
        base_dir: Path,
        *,
        enabled: bool = True,
        ttl_hours: Optional[float] = 24.0,
        summary_enabled: bool = True,
    ) -> None:
        self.base_dir = base_dir
        self.cache_dir = base_dir / "cache"
        self.index_path = self.cache_dir / "index.json"
        self.summary_path = self.cache_dir / "summary.json"
        self.summary_md_path = self.cache_dir / "summary.md"
        self.enabled = enabled
        self.ttl_hours = ttl_hours
        self.summary_enabled = summary_enabled
        self.index: Dict[str, Dict[str, Any]] = self._load_index()
        self.stats = {
            "fetched": 0,
            "skipped": 0,
            "new": 0,
            "updated": 0,
            "unchanged": 0,
        }
        self.changes: List[Dict[str, Any]] = []

    def _load_index(self) -> Dict[str, Dict[str, Any]]:
        if not self.index_path.exists():
            return {}
        try:
            with self.index_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.base_dir))
        except Exception:
            return str(path)

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        if not self.ttl_hours or self.ttl_hours <= 0:
            return True
        last_fetched = _parse_iso(entry.get("last_fetched"))
        if not last_fetched:
            return True
        now = dt.datetime.utcnow()
        age = now - last_fetched.replace(tzinfo=None)
        return age.total_seconds() >= float(self.ttl_hours) * 3600

    def should_fetch(self, url: str, output_path: Path) -> bool:
        if not self.enabled:
            return True
        if not output_path.exists():
            return True
        entry = self.index.get(url)
        if not entry:
            return True
        return self._is_expired(entry)

    def record_skip(self, page_type: str, url: str, output_path: Path) -> None:
        self.stats["skipped"] += 1
        entry = self.index.get(url)
        if not entry:
            self.index[url] = {
                "url": url,
                "page_type": page_type,
                "path": self._relative_path(output_path),
                "last_fetched": None,
            }

    def record_fetch(
        self,
        page_type: str,
        url: str,
        output_path: Path,
        new_content: str,
        old_content: Optional[str],
        *,
        title: Optional[str] = None,
    ) -> str:
        now = _utcnow_iso()
        new_hash = _hash_text(new_content)
        old_hash = _hash_text(old_content) if old_content else None

        if old_content is None:
            change = "new"
        elif new_hash == old_hash:
            change = "unchanged"
        else:
            change = "updated"

        entry = self.index.get(url, {})
        entry.update(
            {
                "url": url,
                "page_type": page_type,
                "path": self._relative_path(output_path),
                "hash": new_hash,
                "last_fetched": now,
            }
        )
        if title:
            entry["title"] = title
        if change in ("new", "updated"):
            entry["last_changed"] = now
            entry["change_count"] = int(entry.get("change_count", 0)) + 1

        self.index[url] = entry
        self.stats["fetched"] += 1
        self.stats[change] += 1

        if change in ("new", "updated"):
            diff_summary = _summarize_diff(old_content, new_content)
            self.changes.append(
                {
                    "url": url,
                    "page_type": page_type,
                    "path": entry.get("path"),
                    "title": entry.get("title", ""),
                    "change": change,
                    "fetched_at": now,
                    "diff_summary": diff_summary,
                }
            )

        return change

    def save(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("w", encoding="utf-8") as handle:
            json.dump(self.index, handle, indent=2, ensure_ascii=True)

    def write_summary(self, competition_id: str) -> None:
        self.save()
        if not self.summary_enabled:
            return
        payload = {
            "competition_id": competition_id,
            "generated_at": _utcnow_iso(),
            "cache_enabled": self.enabled,
            "cache_ttl_hours": self.ttl_hours,
            "stats": self.stats,
            "changes": self.changes,
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.summary_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
        )
        self.summary_md_path.write_text(
            _render_summary_markdown(payload), encoding="utf-8"
        )


# --------------------------------------------------------------------------- #
# Page-level helpers                                                          #
# --------------------------------------------------------------------------- #
async def _scroll_discussion_list(page) -> None:
    """Try to trigger lazy-loading for discussion lists."""
    print("[HOOK] scrolling discussion list")
    try:
        for _ in range(8):
            await page.mouse.wheel(0, 3000)
            await asyncio.sleep(1)
    except Exception as e:
        print(f"[HOOK] scroll discussion list failed: {e}")


async def before_retrieve_html(page, context, **kwargs):
    """
    Hook executed by crawl4ai *before* the HTML of a page is captured.

    It waits briefly to allow the DOM to stabilise and tries to dismiss
    common cookie / consent pop-up banners.
    """
    print("[HOOK] before_retrieve_html – initial wait & pop-up dismissal")

    # Small delay so that the page can finish its initial rendering
    await asyncio.sleep(2)

    # Dismiss cookie / pop-up banners
    try:
        selectors = [
            'button.accept-cookies',
            '.cookie-banner button',
            'text="Accept"',
            'text="OK"',
            'text="Got it"',
            'text="Accept All Cookies"',
        ]
        for sel in selectors:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    print(f"Clicking consent button {sel!r}")
                    await btn.click()
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"Selector {sel!r} raised {e}")
    except Exception as e:
        print(f"Pop-up handler raised {e}")

    try:
        url = page.url or ""
    except Exception:
        url = ""
    if "/discussion" in url and "sort=votes" in url:
        await _scroll_discussion_list(page)
    return page


async def safe_arun(crawler, url, cfg, max_retries: int = 5):
    """
    Wrapper around crawler.arun with exponential back-off retries for rate limits.
    """
    attempt = 0
    while attempt < max_retries:
        try:
            if attempt:
                cfg.cache_mode = CacheMode.BYPASS
                print(f"[safe_arun] retry {attempt} for {url}")

            res = await crawler.arun(url=url, config=cfg)
            if not res or not res.html:
                raise RuntimeError("No HTML returned")

            bad_signatures = [
                "Too many requests",
                "Please wait",
                "try again later",
                "CAPTCHA",
            ]
            if any(sig.lower() in res.html.lower() for sig in bad_signatures):
                raise RuntimeError("Rate-limit page detected")

            if "kaggle.com" in url and len(res.html) < 5_000:
                raise RuntimeError("HTML very small – likely incomplete")

            return res

        except Exception as e:
            wait = 2 ** attempt
            print(f"[safe_arun] {e} – waiting {wait}s then retrying")
            await asyncio.sleep(wait)
            attempt += 1

    print(f"[safe_arun] giving up after {max_retries} retries")
    return None


def _resolve_optional_path(cli_value, env_var, candidates):
    if cli_value:
        candidate = Path(cli_value).expanduser()
        if candidate.exists():
            return candidate
        print(f"[cookies] {candidate} not found")
        return None

    env_value = os.environ.get(env_var)
    if env_value:
        candidate = Path(env_value).expanduser()
        if candidate.exists():
            return candidate
        print(f"[cookies] {env_var} set but file missing: {candidate}")
        return None

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def _load_json_file(path: Path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        print(f"[cookies] file not found: {path}")
    except Exception as e:
        print(f"[cookies] failed to read {path}: {e}")
    return None


def _load_cookie_settings(cookies_path: Path | None, storage_state_path: Path | None):
    cookies = []
    storage_state = None

    if storage_state_path:
        data = _load_json_file(storage_state_path)
        if isinstance(data, dict):
            storage_state = data
            if isinstance(data.get("cookies"), list):
                cookies = data["cookies"]
            print(f"[cookies] loaded storage state from {storage_state_path}")
        else:
            print(f"[cookies] invalid storage state format in {storage_state_path}")

    if cookies_path:
        data = _load_json_file(cookies_path)
        if isinstance(data, list):
            cookies = data
        elif isinstance(data, dict):
            if isinstance(data.get("cookies"), list):
                cookies = data["cookies"]
            elif "name" in data and "value" in data:
                cookies = [data]
            else:
                print(f"[cookies] unrecognized cookie format in {cookies_path}")
        else:
            print(f"[cookies] invalid cookie format in {cookies_path}")

        if cookies:
            print(f"[cookies] loaded {len(cookies)} cookies from {cookies_path}")

    return cookies, storage_state


def _extract_discussion_links(html: str, competition_id: str) -> list:
    pattern = rf'href="(/competitions/{re.escape(competition_id)}/discussion/\d+[^"]*)"'
    matches = re.findall(pattern, html)
    links = [f"https://www.kaggle.com{m}#appreciation" for m in matches]
    return list(dict.fromkeys(links))


def _save_discussion_list_html(debug_dir: Path, label: str, html: str) -> None:
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        output_path = debug_dir / f"discussion_list_{label}.html"
        output_path.write_text(html, encoding="utf-8")
        print(f"[discussion] saved list HTML -> {output_path}")
    except Exception as e:
        print(f"[discussion] failed to save list HTML: {e}")


def clean_markdown(md: str, competition_id: str, page_type: str = "overview"):
    """
    Simple clean-ups for Kaggle Markdown (navigation bars, cookie banners, etc.).
    Discussion threads are stored raw and are **not** passed through this.
    """
    md = re.sub(
        r'\[!\[Kaggle\]\(https://www\.kaggle\.com/static/images/site-logo\.svg\)\]\(https://www\.kaggle\.com/\)',
        '',
        md,
        flags=re.DOTALL,
    )
    md = re.sub(r'Kaggle uses cookies.*?OK, Got it\.', '', md, flags=re.DOTALL)
    md = re.sub(
        rf'\[(Overview|Data|Code|Models|Discussion|Leaderboard|Rules)\]'
        rf'\(https://www\.kaggle\.com/competitions/{re.escape(competition_id)}/[a-z]+\)',
        r'\1',
        md,
    )
    md = re.sub(r'\n{3,}', '\n\n', md)
    if "code" in page_type.lower():
        md = re.sub(r'content_copy.*?Copy code', '', md, flags=re.DOTALL)
    return md.strip()


def download_kaggle_competition_data(
    competition_id: str,
    output_dir: str,
    *,
    force: bool = False,
) -> bool:
    """
    Use the Kaggle Python API to download and unzip competition data.

    Requires a `kaggle.json` credentials file next to this script or in ~/.kaggle.
    Set force=True to re-download even if data is already present.
    """
    current_dir = Path(__file__).resolve().parent
    # Prefer a kaggle.json in the current working directory, fall back to alongside this script.
    kaggle_json_src = Path.cwd() / "kaggle.json"
    if not kaggle_json_src.exists():
        kaggle_json_src = current_dir / "kaggle.json"
    kaggle_config_dir = os.environ.get("KAGGLE_CONFIG_DIR")
    kaggle_dir_dest = Path(kaggle_config_dir) if kaggle_config_dir else Path.home() / ".kaggle"
    kaggle_json_dest = kaggle_dir_dest / "kaggle.json"

    data_dir = Path(output_dir) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    if not force:
        existing_files = [
            p for p in data_dir.iterdir() if p.is_file() and not p.name.startswith(".")
        ]
        if existing_files:
            print(f"[download] data already present in {data_dir}; skipping download")
            return True
    kaggle_dir_dest.mkdir(parents=True, exist_ok=True)

    if not kaggle_json_src.exists():
        print("[download] kaggle.json missing – data download skipped")
        return False

    try:
        if (
            not kaggle_json_dest.exists()
            or kaggle_json_src.stat().st_mtime > kaggle_json_dest.stat().st_mtime
        ):
            print(f"[download] copying {kaggle_json_src} -> {kaggle_json_dest}")
            shutil.copy2(kaggle_json_src, kaggle_json_dest)
            kaggle_json_dest.chmod(0o600)

        # Ensure a concrete user agent to avoid NoneType header errors
        with kaggle_json_dest.open("r", encoding="utf-8") as f:
            creds = json.load(f)
        if not creds.get("user_agent"):
            creds["user_agent"] = "autokaggler/1.0"
            with kaggle_json_dest.open("w", encoding="utf-8") as f:
                json.dump(creds, f)
            kaggle_json_dest.chmod(0o600)
            print(f"[download] set user_agent to {creds['user_agent']} in {kaggle_json_dest}")

        # Set environment variables to prevent None values in headers
        os.environ["KAGGLE_USER_AGENT"] = creds.get("user_agent", "autokaggler/1.0")
        os.environ["KAGGLE_USERNAME"] = creds.get("username", "")
        os.environ["KAGGLE_KEY"] = creds.get("key", "")

        # Ensure all proxy/path config values are strings, not None
        if "proxy" not in creds or creds["proxy"] is None:
            creds.pop("proxy", None)
        if "path" not in creds or creds["path"] is None:
            creds.pop("path", None)
        if "competition" not in creds or creds["competition"] is None:
            creds.pop("competition", None)

        # Rewrite config without None values
        with kaggle_json_dest.open("w", encoding="utf-8") as f:
            json.dump(creds, f)
        kaggle_json_dest.chmod(0o600)

        # Use Kaggle Python API directly instead of CLI
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()

        print(f"[download] downloading competition files for {competition_id}")
        api.competition_download_files(competition_id, path=str(data_dir), force=force)

        # Unzip all .zip files using Python to avoid shell dependencies.
        zip_files = list(data_dir.glob("*.zip"))
        for zip_file in zip_files:
            print(f"[download] unzipping {zip_file}")
            with zipfile.ZipFile(zip_file, "r") as zf:
                zf.extractall(data_dir)

        # Remove the .zip files after extraction
        for zip_file in zip_files:
            print(f"[download] removing {zip_file}")
            zip_file.unlink()

        print("[download] data download, extraction, and cleanup complete")
        return True

    except Exception as e:
        import traceback
        print(f"[download] unexpected error: {e}")
        print("[download] full traceback:")
        traceback.print_exc()
        return False


# --------------------------------------------------------------------------- #
# Discussion-cleaning helpers (adapted from crawl_discussion.py)              #
# --------------------------------------------------------------------------- #
def clean_discussion_file(input_file, output_file=None):
    """
    Clean a single raw discussion Markdown file:

    • Strip user-profile URLs but keep display names.
    • Remove inline images / noisy UI artifacts.
    • Separate main post and comments.
    • Return metadata + write the cleaned Markdown.

    Returns
    -------
    (output_path, upvoted_entries, cleaned_text, discussion_title)

    upvoted_entries is a list of dicts for entries with ≥1 up-vote.
    Each dict has keys: type ('main' / 'comment'), user, upvotes, time,
    content, full_md.
    """
    if output_file is None:
        input_path = Path(input_file)
        output_file = str(
            input_path.parent / f"{input_path.stem}_cleaned{input_path.suffix}"
        )

    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()

    # --- meta ------------------------------------------------------------ #
    title_match = re.search(r"### ([^\n]+)", content)
    title = title_match.group(1) if title_match else "Untitled Discussion"

    poster_match = re.search(r"\[(.+?)\]\(https://www\.kaggle\.com/[^)]+\)", content)
    poster = poster_match.group(1) if poster_match else "Unknown User"

    # drop user URLs (keep display names)
    content = re.sub(r"\[([^\]]+)\]\(https://www\.kaggle\.com/[^)]+\)", r"\1", content)

    time_match = re.search(r"Posted (\d+ years?|\d+ months?|\d+ weeks?|\d+ days?) ago", content)
    posted_time = time_match.group(1) if time_match else "unknown time"

    upvotes_match = re.search(r"arrow_drop_up(\d+)", content)
    upvotes = upvotes_match.group(1) if upvotes_match else "0"

    # --- main body ------------------------------------------------------- #
    main_content_pattern = re.compile(
        r"### [^\n]+\n(.*?)(?:##\s*Comments|\[Beginner\]|This topic is locked for replies)",
        re.DOTALL,
    )
    mc_match = main_content_pattern.search(content)
    if mc_match:
        main_content = mc_match.group(1).strip()
    else:
        # fallback: between title and first comment section
        lines = content.split("\n")
        title_idx = next((i for i, l in enumerate(lines) if l.startswith("### ")), -1)
        comm_idx = next(
            (i for i, l in enumerate(lines) if ("## Comments" in l or "Comments" in l) and i > title_idx),
            len(lines),
        )
        main_body_lines = []
        for l in lines[title_idx + 1 : comm_idx]:
            if any(x in l for x in ("Posted ", "arrow_drop_up", "medal", "[](")):
                continue
            main_body_lines.append(l.strip())
        main_content = "\n".join([l for l in main_body_lines if l]).strip()

    # strip images / links
    main_content = re.sub(r"!\[.*?\]\(.*?\)", "", main_content)
    main_content = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", main_content)

    # --- comments -------------------------------------------------------- #
    comments = []
    upvoted_entries = []

    comment_blocks = list(re.finditer(r"###\s+([^\n]+)\n(.*?)(?=###|\Z)", content, re.DOTALL))
    for block in comment_blocks:
        header = block.group(1)
        section = block.group(2)

        name_match = re.match(r"\[([^\]]+)\]", header)
        comment_user = name_match.group(1) if name_match else header.strip()

        comment_time = "unknown time"
        comment_upvotes = "0"
        comment_content_lines = []

        for line in section.split("\n"):
            if "Posted " in line:
                tm = re.search(r"Posted (\d+ years?|\d+ months?|\d+ weeks?|\d+ days?) ago", line)
                if tm:
                    comment_time = tm.group(1)
                continue
            if "arrow_drop_up" in line:
                um = re.search(r"arrow_drop_up(\d+)", line)
                if um:
                    comment_upvotes = um.group(1)
                continue
            if line.strip() and not any(x in line for x in ("[](", "medal", "more_vert")):
                comment_content_lines.append(line.strip())

        comment_text = "\n".join(comment_content_lines).strip()
        comment_text = re.sub(r"!\[.*?\]\(.*?\)", "", comment_text)
        comment_text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", comment_text)

        if comment_text:
            md_block = (
                f"**{comment_user} | Posted {comment_time} ago | Upvotes: {comment_upvotes}**\n"
                f"{comment_text}"
            )
            comments.append(md_block)

            if int(comment_upvotes) >= 1:
                upvoted_entries.append(
                    {
                        "type": "comment",
                        "user": comment_user,
                        "upvotes": int(comment_upvotes),
                        "time": comment_time,
                        "content": comment_text,
                        "full_md": md_block,
                    }
                )

    # main entry up-vote check
    main_md = f"**{poster} | Posted {posted_time} ago | Upvotes: {upvotes}**\n{main_content}"
    if int(upvotes) >= 1:
        upvoted_entries.insert(
            0,
            {
                "type": "main",
                "user": poster,
                "upvotes": int(upvotes),
                "time": posted_time,
                "content": main_content,
                "full_md": main_md,
            },
        )

    # compose cleaned file
    cleaned = f"# {title}\n\n{main_md}\n\n"
    if comments:
        cleaned += "## Comments\n\n" + "\n\n---\n\n".join(comments)

    with open(output_file, "w", encoding="utf-8") as fh:
        fh.write(cleaned)

    return output_file, upvoted_entries, cleaned, title


def parse_cleaned_discussion_file(cleaned_path: str):
    """Parse a cleaned discussion Markdown file and return title + upvoted entries."""
    try:
        text = Path(cleaned_path).read_text(encoding="utf-8")
    except Exception as e:
        print(f"[clean] failed to read cleaned discussion {cleaned_path}: {e}")
        return "Untitled Discussion", []

    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Untitled Discussion"

    entry_pattern = re.compile(
        r"\*\*(.+?)\s+\|\s+Posted\s+(.+?)\s+ago\s+\|\s+Upvotes:\s*(\d+)\*\*\n"
        r"(.*?)(?=\n\*\*|\n##\s+Comments|\Z)",
        re.DOTALL,
    )

    entries = []
    for match in entry_pattern.finditer(text):
        user = match.group(1).strip()
        posted_time = match.group(2).strip()
        try:
            upvotes = int(match.group(3))
        except ValueError:
            upvotes = 0
        content = match.group(4).strip()
        if upvotes < 1 or not content:
            continue
        full_md = f"**{user} | Posted {posted_time} ago | Upvotes: {upvotes}**\n{content}"
        entries.append(
            {
                "type": "entry",
                "user": user,
                "upvotes": upvotes,
                "time": posted_time,
                "content": content,
                "full_md": full_md,
            }
        )

    return title, entries


async def clean_all_discussions_and_aggregate_upvotes(raw_dir):
    """
    Process every discussion file in `raw_dir`:

    • Each file is cleaned via `clean_discussion_file`.
    • Files with no up-voted content are still cleaned but not aggregated.
    • Aggregated up-voted entries are written to upvoted_discussions.md.
    """
    raw_files = sorted([
        path
        for path in glob.glob(os.path.join(raw_dir, "discussion_*.md"))
        if "_cleaned" not in Path(path).stem
    ])
    print(f"[clean] found {len(raw_files)} raw discussion files")

    for i, raw_path in enumerate(raw_files, 1):
        try:
            cleaned_path, _, _, _ = clean_discussion_file(raw_path)
            # delete original raw file only if a different name was produced
            if raw_path != cleaned_path and os.path.exists(raw_path):
                os.remove(raw_path)

            print(f"[clean] ({i}/{len(raw_files)}) {Path(raw_path).name} → cleaned")

        except Exception as e:
            print(f"[clean] error processing {raw_path}: {e}")

    cleaned_files = sorted(glob.glob(os.path.join(raw_dir, "discussion_*_cleaned.md")))
    upvoted_path = os.path.join(raw_dir, "upvoted_discussions.md")

    if not cleaned_files:
        if os.path.exists(upvoted_path):
            print("[clean] no cleaned discussions found; keeping existing aggregation")
        else:
            print("[clean] no cleaned discussions found; skipping aggregation")
        return

    aggregated = []
    for cleaned_path in cleaned_files:
        title, entries = parse_cleaned_discussion_file(cleaned_path)
        if entries:
            aggregated.append(
                {"title": title, "entries": entries, "file": cleaned_path}
            )

    # write aggregation
    with open(upvoted_path, "w", encoding="utf-8") as fh:
        for idx, disc in enumerate(aggregated, 1):
            fh.write("#" * 5 + "\n")
            fh.write(f"## Discussion {idx}: {disc['title']}\n")
            fh.write("#" * 5 + "\n\n")
            for entry in disc["entries"]:
                fh.write(entry["full_md"].strip() + "\n")
                fh.write("---\n")
    print(f"[clean] aggregation complete → {upvoted_path}")


# --------------------------------------------------------------------------- #
# Crawlers                                                                    #
# --------------------------------------------------------------------------- #
async def crawl_generic_page(
    crawler: AsyncWebCrawler,
    url: str,
    output_path: Path,
    page_type: str,
    competition_id: str,
    cache: Optional[CrawlerCache] = None,
):
    """
    Crawl a non-discussion page, clean its Markdown, and save it.
    """
    if cache and not cache.should_fetch(url, output_path):
        cache.record_skip(page_type, url, output_path)
        print(f"[cache] {page_type} fresh; skipping fetch")
        return True

    print(f"[crawl] {page_type}: {url}")

    cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until="networkidle",
        page_timeout=120_000,
        scan_full_page=True,
        scroll_delay=1.0,  # harmless even without explicit scrolling
        simulate_user=True,
        magic=True,
    )

    res = await safe_arun(crawler, url, cfg)
    if not res or not (res.markdown and res.markdown.raw_markdown):
        print(f"[crawl] FAILED – no Markdown for {url}")
        return False

    cleaned = clean_markdown(res.markdown.raw_markdown, competition_id, page_type)
    header = f"# Kaggle Competition: {competition_id} – {page_type}\n\nSource: {url}\n\n---\n\n"
    new_text = header + cleaned
    existing_text = None
    if output_path.exists():
        try:
            existing_text = output_path.read_text(encoding="utf-8")
        except Exception:
            existing_text = None

    change = None
    if cache:
        change = cache.record_fetch(
            page_type,
            url,
            output_path,
            new_text,
            existing_text,
            title=_extract_title(new_text),
        )

    if change != "unchanged" or existing_text is None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        print(f"[crawl] saved {output_path}")
    else:
        print(f"[cache] no change detected for {output_path.name}")
    return True



async def crawl_discussion_page(
    crawler: AsyncWebCrawler,
    url: str,
    output_path: Path,
    thread_id: str,
    cache: Optional[CrawlerCache] = None,
):
    """
    Fetch a single discussion thread and store its raw Markdown verbatim.
    """
    if cache and not cache.should_fetch(url, output_path):
        cache.record_skip("Discussion", url, output_path)
        print(f"[cache] discussion {thread_id} fresh; skipping fetch")
        return True

    print(f"[discussion] thread {thread_id}: {url}")

    # Discussions are dynamic and often never reach "networkidle" on Kaggle.
    # Use DOMContentLoaded to avoid long hangs/timeouts.
    cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until="domcontentloaded",
        page_timeout=120_000,
        scan_full_page=True,
        simulate_user=True,
        magic=True,
    )

    res = await safe_arun(crawler, url, cfg)
    if not res or not (res.markdown and res.markdown.raw_markdown):
        print(f"[discussion] FAILED – no Markdown for {url}")
        return False

    new_text = res.markdown.raw_markdown
    existing_text = None
    if output_path.exists():
        try:
            existing_text = output_path.read_text(encoding="utf-8")
        except Exception:
            existing_text = None

    change = None
    if cache:
        change = cache.record_fetch(
            "Discussion",
            url,
            output_path,
            new_text,
            existing_text,
            title=_extract_title(new_text) or f"discussion_{thread_id}",
        )

    if change != "unchanged" or existing_text is None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        print(f"[discussion] saved {output_path}")
    else:
        print(f"[cache] no change detected for discussion {thread_id}")
    return True


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #
async def main():
    parser = argparse.ArgumentParser(
        description="Crawl a Kaggle competition – pages, top discussions & data"
    )
    parser.add_argument(
        "competition_id",
        help='Competition slug (e.g. "titanic" or "house-prices-advanced-regression-techniques")',
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete any existing output for this competition before crawling",
    )
    parser.add_argument(
        "--max-discussions",
        type=int,
        default=20,
        help="How many top-voted discussions to download (default 20)",
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Run the browser *not* in headless mode (useful for debugging)",
    )
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Only download competition data and skip crawling pages/discussions",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable crawler cache and always fetch pages/discussions",
    )
    parser.add_argument(
        "--cache-ttl-hours",
        type=float,
        default=24.0,
        help="Re-fetch cached pages after this many hours (default 24)",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Disable writing crawler cache summary files",
    )
    parser.add_argument(
        "--cookies-path",
        default=None,
        help="Path to JSON cookies for a logged-in Kaggle session",
    )
    parser.add_argument(
        "--storage-state-path",
        default=None,
        help="Path to Playwright storage state JSON for a logged-in session",
    )
    args = parser.parse_args()

    competition_id = args.competition_id
    base_url = f"https://www.kaggle.com/competitions/{competition_id}"

    # Directory layout
    base_dir = Path("kaggle_competitions") / competition_id
    pages_dir = base_dir / "pages"
    data_dir = base_dir / "data"
    discussions_dir = base_dir / "discussions" / f"top_{args.max_discussions}_most_voted"

    if args.force and base_dir.exists():
        print(f"[setup] clearing previous output in {base_dir}")
        shutil.rmtree(base_dir)

    for d in (pages_dir, data_dir, discussions_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 1. Dataset
    download_kaggle_competition_data(competition_id, base_dir, force=args.force)

    if args.data_only:
        print("[mode] data-only requested; skipping page/discussion crawling")
        print(f"[output] files saved under {base_dir.resolve()}")
        return

    cache = CrawlerCache(
        base_dir,
        enabled=not args.no_cache,
        ttl_hours=args.cache_ttl_hours,
        summary_enabled=not args.no_summary,
    )

    # 2. Crawler
    cookies_path = _resolve_optional_path(
        args.cookies_path,
        "KAGGLE_COOKIES_PATH",
        [
            Path.cwd() / "kaggle_cookies.json",
            Path.home() / ".kaggle" / "kaggle_cookies.json",
        ],
    )
    storage_state_path = _resolve_optional_path(
        args.storage_state_path,
        "KAGGLE_STORAGE_STATE_PATH",
        [
            Path.cwd() / "kaggle_storage_state.json",
            Path.home() / ".kaggle" / "kaggle_storage_state.json",
        ],
    )
    cookies, storage_state = _load_cookie_settings(cookies_path, storage_state_path)

    browser_cfg = BrowserConfig(
        headless=not args.visible,
        verbose=True,
        viewport_width=1920,
        viewport_height=1080,
        cookies=cookies,
        storage_state=storage_state,
    )
    print(f"[setup] browser running in {'visible' if args.visible else 'headless'} mode")

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        crawler.crawler_strategy.set_hook("before_retrieve_html", before_retrieve_html)

        # 3. Main pages
        print("\n=== Crawling main competition pages ===")
        main_pages = [
            (base_url, "Overview", pages_dir / f"{competition_id}_overview.md"),
            (f"{base_url}/rules", "Rules", pages_dir / f"{competition_id}_rules.md"),
            (
                f"{base_url}/leaderboard",
                "Leaderboard",
                pages_dir / f"{competition_id}_leaderboard.md",
            ),
        ]
        for url, ptype, out_path in tqdm(main_pages, desc="pages"):
            await crawl_generic_page(
                crawler, url, out_path, ptype, competition_id, cache=cache
            )
            await asyncio.sleep(1)

        # 4. Discussions
        print("\n=== Crawling discussion threads (most-voted) ===")
        list_url = f"{base_url}/discussion?sort=votes"
        list_cfg = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_until="domcontentloaded",
            wait_for="a[href*='/discussion/']",
            wait_for_timeout=20_000,
            page_timeout=90_000,
            scan_full_page=True,
            scroll_delay=0.5,
            max_scroll_steps=12,
            simulate_user=True,
            magic=True,
            remove_overlay_elements=True,
            override_navigator=True,
        )
        list_cfg_networkidle = list_cfg.clone(
            wait_until="networkidle",
            page_timeout=120_000,
            max_scroll_steps=20,
            scroll_delay=0.7,
        )

        debug_dir = discussions_dir / "_debug"
        list_attempts = [
            ("domcontentloaded", list_cfg),
            ("networkidle", list_cfg_networkidle),
        ]
        unique_links = []

        for label, cfg in list_attempts:
            list_res = await safe_arun(crawler, list_url, cfg)
            if not list_res or not list_res.html:
                print(f"[discussion] failed to fetch discussion list ({label})")
                continue

            _save_discussion_list_html(debug_dir, label, list_res.html)
            links = _extract_discussion_links(list_res.html, competition_id)
            if links:
                unique_links = links[: args.max_discussions]
                print(
                    f"[discussion] found {len(unique_links)} discussion links "
                    f"(limited to {args.max_discussions})"
                )
                break

            print(f"[discussion] no links found using {label}; retrying")

        if not unique_links:
            print(
                f"[discussion] found 0 discussion links "
                f"(limited to {args.max_discussions})"
            )

        for idx, url in enumerate(tqdm(unique_links, desc="discussions"), 1):
            m = re.search(r"/discussion/(\d+)", url)
            thread_id = m.group(1) if m else f"thread_{idx:03d}"
            out_path = discussions_dir / f"discussion_{thread_id}.md"
            await crawl_discussion_page(
                crawler, url, out_path, thread_id, cache=cache
            )
            await asyncio.sleep(1)

    # 5. Cleaning & aggregation
    print("\n=== Cleaning discussions & aggregating up-voted content ===")
    await clean_all_discussions_and_aggregate_upvotes(discussions_dir)

    cache.write_summary(competition_id)

    print("\n=== All done ===")
    print(f"[output] files saved under {base_dir.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
