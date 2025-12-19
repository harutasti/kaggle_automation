from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


TARGET_ITEM_TYPES = {"reasoning", "agent_message", "web_search"}


def extract_codex_messages_from_jsonl(jsonl_text: str) -> List[Dict[str, str]]:
    """
    Extract reasoning/agent_message/web_search items from Codex JSONL output.

    Returns a list of dicts with keys: type, text.
    """
    if not jsonl_text:
        return []

    messages: List[Dict[str, str]] = []
    seen_ids: set[str] = set()

    for raw_line in jsonl_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            # Ignore non-JSON lines (e.g., "Reading prompt from stdin...")
            continue

        if not isinstance(event, dict):
            continue

        event_type = str(event.get("type") or "")
        if not event_type.startswith("item."):
            continue

        item = event.get("item")
        if not isinstance(item, dict):
            continue

        item_type = item.get("type")
        if item_type not in TARGET_ITEM_TYPES:
            continue

        item_id = item.get("id")
        if isinstance(item_id, str) and item_id in seen_ids:
            continue

        text: Optional[str] = None
        if item_type in ("reasoning", "agent_message"):
            # Prefer completed items to avoid partial duplicates.
            if event_type != "item.completed":
                continue
            text = item.get("text")
        elif item_type == "web_search":
            # Web search items may appear as started/updated/completed.
            text = item.get("query") or item.get("search_query")

        if not text:
            continue

        messages.append({"type": str(item_type), "text": str(text)})
        if isinstance(item_id, str) and item_id:
            seen_ids.add(item_id)

    return messages


def format_codex_messages(messages: List[Dict[str, str]]) -> str:
    """Render messages as a plain-text trace with type headers."""
    if not messages:
        return ""

    blocks: List[str] = []
    for msg in messages:
        mtype = msg.get("type", "message")
        text = msg.get("text", "")
        if text is None:
            continue
        blocks.append(f"[{mtype}]\n{text}".rstrip())
    return "\n\n".join(blocks).strip() + "\n"


def write_codex_messages_file(
    *,
    jsonl_path: str | Path,
    output_path: str | Path | None = None,
) -> Optional[Path]:
    """
    Parse JSONL and write filtered messages to a separate file.
    """
    jsonl_path = Path(jsonl_path)
    if not jsonl_path.exists():
        return None

    if output_path is None:
        output_path = jsonl_path.with_suffix(".messages.txt")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        jsonl_text = jsonl_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    messages = extract_codex_messages_from_jsonl(jsonl_text)
    if not messages:
        # Write an empty file to indicate the pipeline ran.
        output_path.write_text("", encoding="utf-8")
        return output_path

    rendered = format_codex_messages(messages)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path
