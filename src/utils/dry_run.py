"""
Dry-run (simulation_mode) helpers.

Goal: exercise the full AutoKaggle pipeline (crawler, worktrees, uv sync, RAD, PA evolution),
while avoiding any Codex CLI calls.

All behavior here is deterministic and derived from stable hashes (no reliance on Python's
process-randomized `hash()`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Optional


def stable_hash_int(value: str) -> int:
    """Return a stable non-negative int derived from sha256(value)."""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    # Use first 8 bytes to keep int size reasonable.
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def stable_choice(items: list[str], key: str, default: Optional[str] = None) -> str:
    """Deterministically pick an item from a non-empty list."""
    if not items:
        if default is None:
            raise ValueError("items must be non-empty")
        return default
    idx = stable_hash_int(key) % len(items)
    return items[idx]


def stable_uniform(key: str, low: float, high: float) -> float:
    """Deterministically generate a float in [low, high)."""
    if high <= low:
        raise ValueError("high must be > low")
    n = stable_hash_int(key) % 1_000_000
    return low + (high - low) * (n / 1_000_000.0)


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_jsonl_agent_message(path: str | Path, text: str) -> None:
    """
    Write a minimal Codex-like JSONL stream containing one agent message.

    This is compatible with src.utils.codex_executor.extract_text_from_jsonl(), which looks
    for `type == "item.completed"` and `item.type == "agent_message"`.
    """
    p = Path(path)
    ensure_dir(p.parent)
    event = {"type": "item.completed", "item": {"type": "agent_message", "text": text}}
    p.write_text(json.dumps(event) + "\n", encoding="utf-8")


def first_match(patterns: Iterable[str], value: str) -> Optional[str]:
    for pat in patterns:
        if pat in value:
            return pat
    return None

