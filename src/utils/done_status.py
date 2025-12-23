from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import os


@dataclass(frozen=True)
class DoneStatus:
    """Parsed DONE status."""
    raw: Optional[str]
    normalized: str
    ok: Optional[bool]  # True=success, False=failure, None=unknown/missing
    detail: Optional[str] = None


def _extract_detail(raw: str, prefix: str) -> Optional[str]:
    remainder = raw[len(prefix):].strip()
    if remainder.startswith(":"):
        remainder = remainder[1:].strip()
    return remainder or None


def parse_done_text(text: Optional[str]) -> DoneStatus:
    if text is None:
        return DoneStatus(raw=None, normalized="MISSING", ok=None, detail=None)

    raw = text.strip()
    if not raw:
        return DoneStatus(raw=text, normalized="UNKNOWN", ok=None, detail=None)

    upper = raw.upper()

    if upper.startswith("SUCCESS"):
        return DoneStatus(raw=raw, normalized="SUCCESS", ok=True, detail=_extract_detail(raw, "SUCCESS"))
    if upper.startswith("FAILURE"):
        return DoneStatus(raw=raw, normalized="FAILURE", ok=False, detail=_extract_detail(raw, "FAILURE"))
    if upper.startswith("ERROR"):
        return DoneStatus(raw=raw, normalized="ERROR", ok=False, detail=_extract_detail(raw, "ERROR"))
    if upper.startswith("UNEXPECTED_FAILURE"):
        return DoneStatus(
            raw=raw,
            normalized="UNEXPECTED_FAILURE",
            ok=False,
            detail=_extract_detail(raw, "UNEXPECTED_FAILURE"),
        )
    if upper.startswith("RESUME_FAILURE"):
        return DoneStatus(
            raw=raw,
            normalized="RESUME_FAILURE",
            ok=False,
            detail=_extract_detail(raw, "RESUME_FAILURE"),
        )

    return DoneStatus(raw=raw, normalized="UNKNOWN", ok=None, detail=raw)


def read_done_status(path: str) -> DoneStatus:
    if not os.path.exists(path):
        return DoneStatus(raw=None, normalized="MISSING", ok=None, detail=None)

    try:
        with open(path, "r", encoding="utf-8") as f:
            return parse_done_text(f.read())
    except Exception:
        # Treat unreadable file as unknown
        return DoneStatus(raw=None, normalized="UNKNOWN", ok=None, detail=None)
