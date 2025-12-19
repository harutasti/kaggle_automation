#!/usr/bin/env python3
"""
Spawn a separate terminal to view an existing Codex JSONL file.

This lets you validate that the terminal backend works without running Codex.

Example (tmux):
  uv run src/tests/open_live_view_terminal.py \\
    --backend tmux \\
    --label PA0 \\
    --jsonl experiments/titanic/20251218_090505/codex-responses/PA/response-0-decision_retry.jsonl
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.codex_live_view_launcher import CodexLiveViewLauncher  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Open a live Codex JSONL viewer in a separate terminal.")
    parser.add_argument("--jsonl", required=True, help="Path to an existing Codex JSONL file")
    parser.add_argument("--backend", default="auto", help="Terminal backend: auto|tmux|gnome-terminal|xterm")
    parser.add_argument("--label", default="Codex", help="Label for the viewer prefix/window title")
    parser.add_argument("--pid", type=int, default=None, help="Optional PID to monitor for auto-close")
    parser.add_argument("--timestamps", action="store_true", help="Show local timestamps in the viewer")
    args = parser.parse_args()

    jsonl_path = str(Path(args.jsonl).resolve())

    launcher = CodexLiveViewLauncher(
        {
            "codex_live_view": {
                "enabled": True,
                "backend": args.backend,
                "title_prefix": "AutoKaggle",
                "viewer_script": "src/tools/codex_live_view.py",
                "viewer_args": [],
                "viewer_timestamps": bool(args.timestamps),
            }
        }
    )

    launched = launcher.launch(label=args.label, jsonl_path=jsonl_path, pid=args.pid)
    if launched:
        print(f"Spawned live viewer for {jsonl_path} (backend={args.backend}).")
        return

    manual = launcher.build_manual_command(label=args.label, jsonl_path=jsonl_path, pid=args.pid)
    print(f"Viewer not spawned (backend={args.backend}). Run manually:\n  {manual}")

    # Helpful hint for tmux users.
    if args.backend == "tmux" and not os.environ.get("TMUX"):
        print("Note: tmux backend requires running inside an existing tmux session.")


if __name__ == "__main__":
    main()

