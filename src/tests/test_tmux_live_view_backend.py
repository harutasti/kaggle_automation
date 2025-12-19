#!/usr/bin/env python3
"""
Smoke test: validate the tmux backend can spawn a separate live viewer window.

This does NOT run Codex (no costs). It starts a detached tmux session, runs
`open_live_view_terminal.py` inside tmux (so $TMUX is set), and asserts that a
viewer window is created.

Run:
  uv run src/tests/test_tmux_live_view_backend.py
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True, capture_output=True, check=check)


def _has_tmux() -> bool:
    try:
        out = _run(["tmux", "-V"], check=False)
        return out.returncode == 0
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for tmux live view backend.")
    parser.add_argument("--session", default="ak_live_view_test", help="Temporary tmux session name")
    parser.add_argument("--label", default="TEST", help="Label for the viewer window")
    parser.add_argument("--jsonl", default="/tmp/live_view_test.jsonl", help="Nonexistent JSONL path (viewer will wait)")
    parser.add_argument("--timeout-seconds", type=float, default=5.0, help="How long to wait for the window to appear")
    args = parser.parse_args()

    if not _has_tmux():
        print("❌ tmux is not installed. Install it via your OS package manager (e.g., apt-get install tmux).")
        raise SystemExit(1)

    # Clean up prior runs.
    _run(["tmux", "kill-session", "-t", args.session], check=False)
    try:
        os.remove(args.jsonl)
    except FileNotFoundError:
        pass

    # Start detached session.
    _run(["tmux", "new-session", "-d", "-s", args.session, "-c", str(PROJECT_ROOT)])

    # Run the launcher inside tmux so $TMUX is set.
    inner = (
        f"uv run src/tests/open_live_view_terminal.py --backend tmux "
        f"--label {shlex.quote(args.label)} --jsonl {shlex.quote(args.jsonl)}"
    )
    _run(
        [
            "tmux",
            "new-window",
            "-t",
            args.session,
            "-n",
            "runner",
            "-c",
            str(PROJECT_ROOT),
            "bash",
            "-lc",
            inner,
        ],
        check=True,
    )

    expected_window_name = f"AutoKaggle_{args.label}"

    deadline = time.time() + args.timeout_seconds
    found = False
    last_out = ""
    while time.time() < deadline:
        proc = _run(["tmux", "list-windows", "-t", args.session], check=False)
        last_out = (proc.stdout or "") + (proc.stderr or "")
        if expected_window_name in last_out:
            found = True
            break
        time.sleep(0.2)

    # Cleanup session (also kills the spawned viewer).
    _run(["tmux", "kill-session", "-t", args.session], check=False)

    if not found:
        print("❌ Failed to find viewer window.")
        print(f"Expected window name to include: {expected_window_name!r}")
        print("tmux list-windows output:")
        print(last_out.strip())
        raise SystemExit(1)

    print("✅ tmux live view backend spawned viewer window successfully.")


if __name__ == "__main__":
    main()

