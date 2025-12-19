#!/usr/bin/env python3
"""
Run Codex and show its JSONL stream in a separate terminal (no live output in this terminal).

Example:
  uv run src/tests/run_codex_in_separate_terminal.py "summarize this repo"

Backends:
  - auto (default): tmux (if inside tmux) -> gnome-terminal -> xterm
  - tmux: opens a new tmux window (requires being inside tmux)
  - gnome-terminal / xterm: opens a new GUI terminal window (requires DISPLAY/WAYLAND)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Add project root to sys.path so we can import src.utils.*
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.codex_live_view_launcher import CodexLiveViewLauncher  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Codex and view output in a separate terminal.")
    parser.add_argument("prompt", help="Prompt passed to `codex exec --json` via stdin")
    parser.add_argument("--backend", default="auto", help="Terminal backend: auto|tmux|gnome-terminal|xterm")
    parser.add_argument("--label", default="Codex", help="Label for the viewer prefix/window title")
    parser.add_argument(
        "--output",
        default="",
        help="Path to write JSONL output (default: logs/codex-live/codex_live_*.jsonl)",
    )
    args = parser.parse_args()

    out_path = Path(args.output) if args.output else None
    if out_path is None:
        logs_dir = PROJECT_ROOT / "logs" / "codex-live"
        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = logs_dir / f"codex_live_{ts}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Launch Codex with stdout streamed to JSONL file.
    cmd = ["codex", "exec", "--skip-git-repo-check", "--json"]
    with out_path.open("w", encoding="utf-8") as f:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.PIPE,
            stdout=f,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdin is not None
        proc.stdin.write(args.prompt)
        if not args.prompt.endswith("\n"):
            proc.stdin.write("\n")
        proc.stdin.close()

    # Best-effort viewer spawn.
    launcher = CodexLiveViewLauncher(
        {
            "codex_live_view": {
                "enabled": True,
                "backend": args.backend,
                "title_prefix": "CodexLive",
                "viewer_script": "src/tools/codex_live_view.py",
                "viewer_args": [],
                "viewer_timestamps": True,
            }
        }
    )

    launched = launcher.launch(label=args.label, jsonl_path=str(out_path), pid=proc.pid)
    if not launched:
        manual = launcher.build_manual_command(label=args.label, jsonl_path=str(out_path), pid=proc.pid)
        print(f"Viewer not spawned (backend={args.backend}). Run manually:\n  {manual}")

    # Wait for Codex to finish; viewer will close itself afterwards.
    rc = proc.wait()
    print(f"Codex exited with code {rc}. JSONL saved to {out_path}")
    raise SystemExit(rc)


if __name__ == "__main__":
    main()

