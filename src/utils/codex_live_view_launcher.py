from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class CodexLiveViewConfig:
    """
    Configuration for spawning a separate terminal to follow Codex JSONL output.

    Backends:
      - auto: choose best available
      - tmux: open a new tmux window (requires being inside tmux)
      - gnome-terminal: spawn a new GNOME Terminal window (requires GUI)
      - xterm: spawn a new xterm window (requires GUI)
      - none: disable spawning
    """

    enabled: bool = False
    backend: str = "auto"
    title_prefix: str = "AutoKaggle"
    viewer_script_rel: str = "src/tools/codex_live_view.py"
    viewer_extra_args: list[str] = field(default_factory=list)

    # Viewer defaults (can be overridden by viewer_extra_args)
    viewer_from_end: bool = False
    viewer_timestamps: bool = False
    viewer_idle_exit_seconds: float = 3.0

    def to_viewer_args(self, *, label: str, jsonl_path: str, pid: Optional[int]) -> list[str]:
        args: list[str] = [
            self.viewer_script_rel,
            "--follow",
            jsonl_path,
            "--label",
            label,
            "--idle-exit-seconds",
            str(self.viewer_idle_exit_seconds),
        ]
        if pid is not None:
            args.extend(["--pid", str(pid)])
        if self.viewer_from_end:
            args.append("--from-end")
        if self.viewer_timestamps:
            args.append("--timestamps")
        args.extend(self.viewer_extra_args)
        return args


def _sanitize_title(text: str, max_len: int = 40) -> str:
    s = "".join(ch if ch.isalnum() or ch in ("-", "_", ".", " ") else "_" for ch in text)
    s = s.strip()
    if not s:
        s = "codex"
    return s[:max_len]


class CodexLiveViewLauncher:
    """
    Launches a dedicated live viewer for a Codex JSONL stream in a separate terminal.
    """

    def __init__(self, config: dict, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("AutoKaggle.CodexLiveView")

        cfg = config.get("codex_live_view") or config.get("live_view") or {}
        self.cfg = CodexLiveViewConfig(
            enabled=bool(cfg.get("enabled", False)),
            backend=str(cfg.get("backend", "auto")),
            title_prefix=str(cfg.get("title_prefix", "AutoKaggle")),
            viewer_script_rel=str(cfg.get("viewer_script", "src/tools/codex_live_view.py")),
            viewer_extra_args=list(cfg.get("viewer_args", []) or []),
            viewer_from_end=bool(cfg.get("viewer_from_end", False)),
            viewer_timestamps=bool(cfg.get("viewer_timestamps", False)),
            viewer_idle_exit_seconds=float(cfg.get("viewer_idle_exit_seconds", 3.0)),
        )

    def enabled(self) -> bool:
        return self.cfg.enabled and self.cfg.backend.lower() not in ("off", "false", "0", "none", "")

    def build_manual_command(self, *, label: str, jsonl_path: str, pid: Optional[int]) -> str:
        uv = shutil.which("uv") or "uv"
        viewer_args = self.cfg.to_viewer_args(label=label, jsonl_path=jsonl_path, pid=pid)
        # Render as a single command string for humans.
        parts = [uv, "run"] + viewer_args
        quoted = " ".join(shlex.quote(p) for p in parts)
        return f"cd {shlex.quote(str(PROJECT_ROOT))} && {quoted}"

    def launch(self, *, label: str, jsonl_path: str, pid: Optional[int]) -> bool:
        """
        Attempt to launch a separate terminal viewer. Returns True if launched.
        """
        if not self.enabled():
            return False

        backend = self.cfg.backend.lower()
        if backend == "auto":
            for candidate in ("tmux", "gnome-terminal", "xterm"):
                if self._try_backend(candidate, label=label, jsonl_path=jsonl_path, pid=pid):
                    return True
            self.logger.info("No supported terminal backend found for live view (auto).")
            return False

        return self._try_backend(backend, label=label, jsonl_path=jsonl_path, pid=pid)

    def _try_backend(self, backend: str, *, label: str, jsonl_path: str, pid: Optional[int]) -> bool:
        if backend == "tmux":
            return self._launch_tmux(label=label, jsonl_path=jsonl_path, pid=pid)
        if backend == "gnome-terminal":
            return self._launch_gnome_terminal(label=label, jsonl_path=jsonl_path, pid=pid)
        if backend == "xterm":
            return self._launch_xterm(label=label, jsonl_path=jsonl_path, pid=pid)
        if backend in ("none", "off", "false", "0", ""):
            return False

        self.logger.info(f"Unsupported live view backend: {backend}")
        return False

    def _viewer_cmd(self, *, label: str, jsonl_path: str, pid: Optional[int]) -> list[str]:
        uv = shutil.which("uv") or "uv"
        viewer_args = self.cfg.to_viewer_args(label=label, jsonl_path=jsonl_path, pid=pid)
        return [uv, "run", *viewer_args]

    def _launch_tmux(self, *, label: str, jsonl_path: str, pid: Optional[int]) -> bool:
        tmux = shutil.which("tmux")
        if not tmux:
            return False
        if not os.environ.get("TMUX"):
            # We deliberately require being inside tmux to avoid hijacking the main terminal.
            return False

        title = _sanitize_title(f"{self.cfg.title_prefix}:{label}", max_len=30)
        cmd = [tmux, "new-window", "-n", title, "-c", str(PROJECT_ROOT), *self._viewer_cmd(label=label, jsonl_path=jsonl_path, pid=pid)]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.logger.info(f"Spawned tmux live view window: {title} (label={label})")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to spawn tmux live view: {e}")
            return False

    def _has_gui(self) -> bool:
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    def _launch_gnome_terminal(self, *, label: str, jsonl_path: str, pid: Optional[int]) -> bool:
        term = shutil.which("gnome-terminal")
        if not term or not self._has_gui():
            return False

        title = _sanitize_title(f"{self.cfg.title_prefix}:{label}")
        cmd_str = self.build_manual_command(label=label, jsonl_path=jsonl_path, pid=pid)
        try:
            subprocess.Popen(
                [term, "--title", title, "--", "bash", "-lc", cmd_str],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.logger.info(f"Spawned gnome-terminal live view: {title} (label={label})")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to spawn gnome-terminal live view: {e}")
            return False

    def _launch_xterm(self, *, label: str, jsonl_path: str, pid: Optional[int]) -> bool:
        xterm = shutil.which("xterm")
        if not xterm or not self._has_gui():
            return False

        title = _sanitize_title(f"{self.cfg.title_prefix}:{label}")
        cmd_str = self.build_manual_command(label=label, jsonl_path=jsonl_path, pid=pid)
        try:
            subprocess.Popen(
                [xterm, "-T", title, "-e", "bash", "-lc", cmd_str],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.logger.info(f"Spawned xterm live view: {title} (label={label})")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to spawn xterm live view: {e}")
            return False
