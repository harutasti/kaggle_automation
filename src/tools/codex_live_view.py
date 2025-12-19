#!/usr/bin/env python3
"""
Live Codex JSONL viewer (and optional runner).

This tool renders Codex CLI's JSONL event stream (`codex exec --json`) in real time
with visual distinctions per event/item type.

Usage:
  # Run Codex and render its JSONL stream live (same terminal)
  uv run src/tools/codex_live_view.py "your prompt here"

  # Follow an existing JSONL file (run this in a separate terminal if desired)
  uv run src/tools/codex_live_view.py --follow /path/to/output.jsonl --pid 12345
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from rich.console import Console
from rich.text import Text


PROJECT_ROOT = Path(__file__).resolve().parents[2]


EVENT_STYLE: dict[str, str] = {
    "thread.started": "dim",
    "turn.started": "bold bright_green",
    "turn.completed": "bold bright_green",
    "item.started": "bright_yellow",
    "item.updated": "bright_yellow",
    "item.completed": "white",
    "error": "bold bright_red",
}

ITEM_STYLE: dict[str, str] = {
    "reasoning": "dim",
    "agent_message": "bold white",
    "command_execution": "bright_cyan",
    "file_change": "bold magenta",
    "todo_list": "bright_yellow",
    "web_search": "bright_blue",
}

FILE_CHANGE_KIND_STYLE: dict[str, str] = {
    "add": "green",
    "update": "yellow",
    "delete": "red",
}


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # If we can't signal it, assume it's alive.
        return True


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _truncate_lines(text: str, max_lines: int) -> str:
    if max_lines <= 0:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    head = "\n".join(lines[:max_lines])
    return head + f"\n... ({len(lines) - max_lines} more lines truncated)"


@dataclass
class RenderConfig:
    label: str = ""
    show_reasoning: bool = True
    show_agent_messages: bool = True
    show_command_output: bool = True
    timestamps: bool = False
    max_text_chars: int = 4000
    max_command_output_lines: int = 80
    max_command_output_chars: int = 12000


class JsonlRenderer:
    def __init__(self, console: Console, config: RenderConfig):
        self.console = console
        self.config = config
        self._seen_turn_completed = False

    @property
    def seen_turn_completed(self) -> bool:
        return self._seen_turn_completed

    def render_raw_line(self, line: str) -> None:
        line = line.rstrip("\n")
        if not line.strip():
            return
        self.console.print(self._prefix_text(line, style="dim"))

    def render_event(self, obj: Dict[str, Any]) -> None:
        event_type = obj.get("type") or "unknown"

        if event_type == "turn.completed":
            self._seen_turn_completed = True

        if event_type == "error":
            msg = obj.get("message", "")
            self.console.print(self._prefix_text(f"[error] {msg}", style=EVENT_STYLE["error"]))
            return

        if event_type == "thread.started":
            tid = obj.get("thread_id", "")
            self.console.print(self._prefix_text(f"thread.started id={tid}", style=EVENT_STYLE["thread.started"]))
            return

        if event_type == "turn.started":
            self.console.print(self._prefix_text("turn.started", style=EVENT_STYLE["turn.started"]))
            return

        if event_type == "turn.completed":
            usage = obj.get("usage") or {}
            usage_str = ""
            if isinstance(usage, dict):
                usage_str = (
                    f" input={usage.get('input_tokens','?')}"
                    f" cached={usage.get('cached_input_tokens','?')}"
                    f" output={usage.get('output_tokens','?')}"
                )
            self.console.print(self._prefix_text(f"turn.completed{usage_str}", style=EVENT_STYLE["turn.completed"]))
            return

        if event_type.startswith("item.") and isinstance(obj.get("item"), dict):
            self._render_item_event(event_type, obj["item"])
            return

        # Fallback: print JSON in a compact form.
        self.console.print(
            self._prefix_text(json.dumps(obj, ensure_ascii=False), style=EVENT_STYLE.get(event_type, "dim"))
        )

    def _render_item_event(self, event_type: str, item: Dict[str, Any]) -> None:
        item_type = item.get("type") or "unknown"
        item_id = item.get("id", "")
        status = item.get("status")
        style = ITEM_STYLE.get(item_type, "white")

        header = f"{event_type} {item_type}"
        if item_id:
            header += f" {item_id}"
        if status:
            header += f" status={status}"

        if item_type == "reasoning":
            if not self.config.show_reasoning:
                return
            text = item.get("text") or ""
            if not isinstance(text, str):
                text = str(text)
            text = _truncate_text(text, self.config.max_text_chars)
            self.console.print(self._prefix_text(header, style=style))
            if text:
                self.console.print(self._prefix_text(text, style=style))
            return

        if item_type == "agent_message":
            if not self.config.show_agent_messages:
                return
            text = item.get("text") or ""
            if not isinstance(text, str):
                text = str(text)
            text = _truncate_text(text, self.config.max_text_chars)
            self.console.print(self._prefix_text(header, style=style))
            if text:
                self.console.print(self._prefix_text(text, style=style))
            return

        if item_type == "web_search":
            query = item.get("query", "")
            self.console.print(self._prefix_text(f"{header} query={query}", style=style))
            return

        if item_type == "todo_list":
            items = item.get("items") or []
            self.console.print(self._prefix_text(header, style=style))
            if isinstance(items, list):
                for entry in items[:200]:
                    if isinstance(entry, dict):
                        todo_text = entry.get("text", "")
                        completed = bool(entry.get("completed", False))
                        mark = "[x]" if completed else "[ ]"
                        line_style = "green" if completed else style
                        self.console.print(self._prefix_text(f"  {mark} {todo_text}", style=line_style))
                    else:
                        self.console.print(self._prefix_text(f"  - {entry}", style=style))
            return

        if item_type == "file_change":
            changes = item.get("changes") or []
            self.console.print(self._prefix_text(header, style=style))
            if isinstance(changes, list):
                for ch in changes[:200]:
                    if not isinstance(ch, dict):
                        self.console.print(self._prefix_text(f"  - {ch}", style=style))
                        continue
                    kind = str(ch.get("kind", "change"))
                    path = str(ch.get("path", ""))
                    kind_style = FILE_CHANGE_KIND_STYLE.get(kind, style)
                    self.console.print(self._prefix_text(f"  - {kind}: {path}", style=kind_style))
            return

        if item_type == "command_execution":
            cmd = item.get("command", "")
            exit_code = item.get("exit_code", None)
            self.console.print(self._prefix_text(f"{header} cmd={cmd}", style=style))

            if event_type == "item.completed":
                exit_style = "green" if exit_code == 0 else "bold red"
                self.console.print(self._prefix_text(f"  -> exit_code={exit_code}", style=exit_style))

            if event_type == "item.completed" and self.config.show_command_output:
                out = item.get("aggregated_output") or ""
                if not isinstance(out, str):
                    out = str(out)
                out = _truncate_text(out, self.config.max_command_output_chars)
                out = _truncate_lines(out, self.config.max_command_output_lines)
                if out.strip():
                    for line in out.splitlines():
                        self.console.print(self._prefix_text(f"  | {line}", style="cyan"))
            return

        self.console.print(self._prefix_text(header, style=style))

    def _prefix_text(self, text: str, *, style: str = "") -> Text:
        prefix = ""
        if self.config.timestamps:
            prefix += datetime.now().strftime("%H:%M:%S") + " "
        if self.config.label:
            prefix += f"[{self.config.label}] "
        t = Text(prefix + text)
        if style:
            t.stylize(style)
        return t


def _start_codex_process(prompt: str, cwd: Path) -> subprocess.Popen:
    cmd = ["codex", "exec", "--skip-git-repo-check", "--json"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    assert proc.stdin is not None
    assert proc.stdout is not None

    proc.stdin.write(prompt)
    if not prompt.endswith("\n"):
        proc.stdin.write("\n")
    proc.stdin.flush()
    proc.stdin.close()
    return proc


def _iter_process_stdout_lines(proc: subprocess.Popen, timeout_s: Optional[int]) -> Iterable[str]:
    assert proc.stdout is not None

    start = time.time()
    for line in proc.stdout:
        yield line
        if timeout_s is not None and (time.time() - start) > timeout_s:
            proc.terminate()
            break

    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _follow_jsonl_file(
    path: Path,
    renderer: JsonlRenderer,
    *,
    pid: Optional[int],
    exit_on_turn_completed: bool,
    from_end: bool,
    poll_interval_s: float,
    idle_exit_seconds: float,
) -> int:
    last_activity = time.time()

    while not path.exists():
        renderer.console.print(renderer._prefix_text(f"Waiting for file to exist: {path}", style="dim"))
        time.sleep(poll_interval_s)
        if pid is not None and not _is_process_alive(pid):
            renderer.console.print(renderer._prefix_text("Process ended before file appeared.", style="bold red"))
            return 2

    with path.open("r", encoding="utf-8", errors="replace") as f:
        if from_end:
            f.seek(0, os.SEEK_END)

        while True:
            line = f.readline()
            if line:
                last_activity = time.time()
                _render_line(renderer, line)
                if exit_on_turn_completed and renderer.seen_turn_completed:
                    return 0
                continue

            if pid is not None and not _is_process_alive(pid):
                if (time.time() - last_activity) >= idle_exit_seconds:
                    renderer.console.print(renderer._prefix_text("Process exited; viewer closing.", style="dim"))
                    return 0

            time.sleep(poll_interval_s)


def _render_line(renderer: JsonlRenderer, line: str) -> None:
    stripped = line.strip("\n")
    if not stripped.strip():
        return
    try:
        obj = json.loads(stripped)
    except Exception:
        renderer.render_raw_line(stripped)
        return
    if isinstance(obj, dict):
        renderer.render_event(obj)
    else:
        renderer.render_raw_line(stripped)


def main() -> None:
    parser = argparse.ArgumentParser(description="Live Codex JSONL viewer (and optional runner).")
    parser.add_argument("prompt", nargs="?", help="Prompt to run with `codex exec --json`")
    parser.add_argument("--follow", type=str, help="Follow an existing JSONL file")
    parser.add_argument("--pid", type=int, default=None, help="PID to monitor; viewer exits after PID ends + idle time")
    parser.add_argument("--label", type=str, default="", help="Optional label prefix for every rendered line")
    parser.add_argument("--output", type=str, default="", help="Write raw JSONL output to this file (exec mode)")
    parser.add_argument("--timeout", type=int, default=0, help="Optional timeout seconds for codex exec (0=none)")
    parser.add_argument("--from-end", action="store_true", help="Follow from end of file (follow mode)")
    parser.add_argument("--poll-interval", type=float, default=0.2, help="Follow poll interval seconds")
    parser.add_argument("--idle-exit-seconds", type=float, default=3.0, help="Exit when PID is dead and no new data for N seconds")
    parser.add_argument("--no-render", action="store_true", help="Exec mode: do not render events (write JSONL only)")
    parser.add_argument("--timestamps", action="store_true", help="Show local timestamps for each printed line")
    parser.add_argument("--no-reasoning", action="store_true", help="Hide reasoning items")
    parser.add_argument("--no-agent-messages", action="store_true", help="Hide agent_message items")
    parser.add_argument("--no-command-output", action="store_true", help="Hide command aggregated output")
    parser.add_argument("--max-text-chars", type=int, default=4000, help="Max chars for reasoning/agent text")
    parser.add_argument("--max-command-output-lines", type=int, default=80, help="Max lines for command output")
    parser.add_argument("--max-command-output-chars", type=int, default=12000, help="Max chars for command output")
    args = parser.parse_args()

    console = Console()
    cfg = RenderConfig(
        label=args.label,
        show_reasoning=not args.no_reasoning,
        show_agent_messages=not args.no_agent_messages,
        show_command_output=not args.no_command_output,
        timestamps=args.timestamps,
        max_text_chars=args.max_text_chars,
        max_command_output_lines=args.max_command_output_lines,
        max_command_output_chars=args.max_command_output_chars,
    )
    renderer = JsonlRenderer(console, cfg)

    if args.follow:
        follow_path = Path(args.follow)
        rc = _follow_jsonl_file(
            follow_path,
            renderer,
            pid=args.pid,
            exit_on_turn_completed=True,
            from_end=args.from_end,
            poll_interval_s=args.poll_interval,
            idle_exit_seconds=args.idle_exit_seconds,
        )
        raise SystemExit(rc)

    if not args.prompt:
        console.print("Provide a prompt or use --follow.", style="bold red")
        raise SystemExit(2)

    out_path = Path(args.output) if args.output else None
    if out_path is None:
        logs_dir = PROJECT_ROOT / "logs" / "codex-live"
        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = logs_dir / f"codex_live_{ts}.jsonl"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    timeout_s = args.timeout if args.timeout > 0 else None

    console.print(f"Running: codex exec --json (cwd={PROJECT_ROOT})", style="bold")
    console.print(f"Raw stream saved to: {out_path}", style="dim")

    proc = _start_codex_process(args.prompt, cwd=PROJECT_ROOT)
    console.print(f"Codex PID: {proc.pid}", style="dim")

    with out_path.open("w", encoding="utf-8") as out_f:
        for line in _iter_process_stdout_lines(proc, timeout_s=timeout_s):
            out_f.write(line)
            out_f.flush()
            if not args.no_render:
                _render_line(renderer, line)

    console.print("Codex stream ended.", style="bold bright_green")


if __name__ == "__main__":
    main()

