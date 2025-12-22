import asyncio
import os
import re
import subprocess
import argparse
import shutil
import glob
import json
import sys
from pathlib import Path
from tqdm import tqdm
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

try:
    # Ensure crawler prints flush promptly when invoked via subprocess.
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass


# --------------------------------------------------------------------------- #
# Page-level helpers                                                          #
# --------------------------------------------------------------------------- #
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


def download_kaggle_competition_data(competition_id: str, output_dir: str) -> bool:
    """
    Use the Kaggle Python API to download and unzip competition data.

    Requires a `kaggle.json` credentials file next to this script or in ~/.kaggle.
    """
    current_dir = Path(__file__).resolve().parent
    # Prefer a kaggle.json in the current working directory, fall back to alongside this script.
    kaggle_json_src = Path.cwd() / "kaggle.json"
    if not kaggle_json_src.exists():
        kaggle_json_src = current_dir / "kaggle.json"
    kaggle_dir_dest = Path.home() / ".kaggle"
    kaggle_json_dest = kaggle_dir_dest / "kaggle.json"

    data_dir = Path(output_dir) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
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
        api.competition_download_files(competition_id, path=str(data_dir), force=True)

        # Unzip all .zip files (using glob to avoid shell injection)
        zip_files = list(data_dir.glob("*.zip"))
        for zip_file in zip_files:
            print(f"[download] unzipping {zip_file}")
            subprocess.run(
                ['unzip', '-o', str(zip_file), '-d', str(data_dir)],
                check=True
            )

        # Remove the .zip files after extraction
        for zip_file in zip_files:
            print(f"[download] removing {zip_file}")
            zip_file.unlink()

        print("[download] data download, extraction, and cleanup complete")
        return True

    except subprocess.CalledProcessError as e:
        print(f"[download] command returned {e.returncode}: {e.cmd}")
        return False
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


async def clean_all_discussions_and_aggregate_upvotes(raw_dir):
    """
    Process every discussion file in `raw_dir`:

    • Each file is cleaned via `clean_discussion_file`.
    • Files with no up-voted content are still cleaned but not aggregated.
    • Aggregated up-voted entries are written to upvoted_discussions.md.
    """
    raw_files = glob.glob(os.path.join(raw_dir, "discussion_*.md"))
    print(f"[clean] found {len(raw_files)} raw discussion files")

    aggregated = []
    for i, raw_path in enumerate(raw_files, 1):
        try:
            cleaned_path, upvoted, _, title = clean_discussion_file(raw_path)
            # delete original raw file only if a different name was produced
            if raw_path != cleaned_path and os.path.exists(raw_path):
                os.remove(raw_path)

            if upvoted:
                aggregated.append(
                    {"title": title, "entries": upvoted, "file": cleaned_path}
                )

            print(f"[clean] ({i}/{len(raw_files)}) {Path(raw_path).name} → cleaned")

        except Exception as e:
            print(f"[clean] error processing {raw_path}: {e}")

    # write aggregation
    upvoted_path = os.path.join(raw_dir, "upvoted_discussions.md")
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
):
    """
    Crawl a non-discussion page, clean its Markdown, and save it.
    """
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(f"# Kaggle Competition: {competition_id} – {page_type}\n\n")
        fh.write(f"Source: {url}\n\n---\n\n")
        fh.write(cleaned)

    print(f"[crawl] saved {output_path}")
    return True



async def crawl_discussion_page(
    crawler: AsyncWebCrawler,
    url: str,
    output_path: Path,
    thread_id: str,
):
    """
    Fetch a single discussion thread and store its raw Markdown verbatim.
    """
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(res.markdown.raw_markdown)

    print(f"[discussion] saved {output_path}")
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
    download_kaggle_competition_data(competition_id, base_dir)

    if args.data_only:
        print("[mode] data-only requested; skipping page/discussion crawling")
        print(f"[output] files saved under {base_dir.resolve()}")
        return

    # 2. Crawler
    browser_cfg = BrowserConfig(
        headless=not args.visible,
        verbose=True,
        viewport_width=1920,
        viewport_height=1080,
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
            await crawl_generic_page(crawler, url, out_path, ptype, competition_id)
            await asyncio.sleep(1)

        # 4. Discussions
        print("\n=== Crawling discussion threads (most-voted) ===")
        list_url = f"{base_url}/discussion?sort=votes"
        # Discussion list page is also dynamic; avoid waiting for full network idle.
        list_cfg = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_until="domcontentloaded",
            page_timeout=60_000,
        )

        list_res = await safe_arun(crawler, list_url, list_cfg)
        if not list_res or not list_res.html:
            print("[discussion] failed to fetch discussion list – skipping")
        else:
            pattern = rf'href="(/competitions/{re.escape(competition_id)}/discussion/\d+[^"]*)"'
            matches = re.findall(pattern, list_res.html)
            links = [f"https://www.kaggle.com{m}#appreciation" for m in matches]
            unique_links = list(dict.fromkeys(links))[: args.max_discussions]
            print(
                f"[discussion] found {len(unique_links)} discussion links "
                f"(limited to {args.max_discussions})"
            )

            for idx, url in enumerate(tqdm(unique_links, desc="discussions"), 1):
                m = re.search(r"/discussion/(\d+)", url)
                thread_id = m.group(1) if m else f"thread_{idx:03d}"
                out_path = discussions_dir / f"discussion_{thread_id}.md"

                if out_path.exists():
                    print(f"[discussion] skip existing {out_path.name}")
                    continue

                await crawl_discussion_page(crawler, url, out_path, thread_id)
                await asyncio.sleep(1)

    # 5. Cleaning & aggregation
    print("\n=== Cleaning discussions & aggregating up-voted content ===")
    await clean_all_discussions_and_aggregate_upvotes(discussions_dir)

    print("\n=== All done ===")
    print(f"[output] files saved under {base_dir.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
