#!/usr/bin/env python3
"""
claude_code_demo.py – Example showing how to call Anthropic Claude
from a Python script.

This demo shows how to compose the CLI command, invoke Claude in either interactive or JSON modes, and capture
its output programmatically.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Tuple, Any

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)7s | %(message)s",
)
logger = logging.getLogger("claude_demo")

# ---------------------------------------------------------------------------
# Constants (mirroring the originals, trimmed for clarity)
# ---------------------------------------------------------------------------
ALLOWED_TOOLS: List[str] = [
    "Read", "Write", "LS", "Grep", "Bash",  # basic file & shell helpers
]

DISALLOWED_TOOLS: List[str] = [
    "Bash(rm -rf:*)",                # protect against destructive ops
    "Bash(git reset --hard:*)",
    "Bash(git push --force:*)",
]

# Optional sentinel we can look for in Claude’s stdout when we want a simple
# end‑of‑output marker (not mandatory for the demo to work).
SENTINEL_DONE = "### DONE ###"

# ---------------------------------------------------------------------------
# Helper to build the Claude CLI command
# ---------------------------------------------------------------------------

def claude_cmd(
    prompt: str,
    *,
    interactive: bool = False,
    tools: List[str] | None = None,
) -> List[str]:
    """Return a list of argv tokens that invoke Claude with the given *prompt*.

    Parameters
    ----------
    prompt: str
        The text prompt to pass to Claude.
    interactive: bool, default False
        If *True* we launch Claude in an interactive TTY so the user can chat
        in real‑time. Otherwise we run non‑interactive mode and request JSON
        output that we can parse.
    tools: list[str] | None
        Custom list of permitted tools (defaults to :pydata:`ALLOWED_TOOLS`).
    """
    tools = tools or ALLOWED_TOOLS

    if interactive:
        # In interactive mode we let Claude ask to use tools freely; the user
        # decides whether to approve. The flag below skips any permission
        # prompts that would normally block.
        flags = ["--dangerously-skip-permissions"]
    else:
        # Non‑interactive (batch) mode: we ask Claude to return a JSON object
        # so our Python code can consume it easily.
        flags = ["-p", "--output-format", "json", "--verbose"]

    return [
        "claude",
        *flags,
        prompt,
        "--allowedTools", ",".join(tools),
        "--disallowedTools", ",".join(DISALLOWED_TOOLS),
    ]

# ---------------------------------------------------------------------------
# Function to actually run Claude and collect its output
# ---------------------------------------------------------------------------

def launch_claude(
    prompt: str,
    *,
    interactive: bool = False,
    cwd: Path | None = None,
) -> Tuple[Any, str]:
    """Run Claude and return (parsed, raw_stdout).

    If *interactive* is *True* the call opens a PTY so the user can converse
    directly; in that case the function returns an empty dict for *parsed* and
    an empty string for *raw* when the session ends.
    """
    cmd = claude_cmd(prompt, interactive=interactive)
    logger.info("$ %s", " ".join(cmd))

    if interactive:
        # We hand control over to the user until they exit (e.g. Ctrl‑D).
        if cwd:
            import os
            os.chdir(cwd)
        import pty
        pty.spawn(cmd)
        return {}, ""  # Nothing to parse in this mode

    # Batch mode: capture Claude’s stdout so we can parse JSON.
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    raw = proc.stdout or ""

    # Try JSON‑parsing the entire stdout. If Claude printed additional text
    # before/after the JSON blob, this might fail – in real‑world systems you
    # would extract the JSON substring instead. For brevity we skip that here.
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON output; returning raw text only")
        parsed = {}

    return parsed, raw

# ---------------------------------------------------------------------------
# Main demo – run a *very* general task prompt
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal Claude CLI demo")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Open an interactive Claude session instead of batch JSON mode",
    )
    args = parser.parse_args()

    # A short and *generic* task suitable for quick experimentation.
    task_prompt = (
        "Read the following short paragraph and produce a concise bullet‑point "
        "summary.
        "\"\"\"\n"
        "Python is a high‑level, interpreted programming language known for its "
        "readability and broad standard library. Created by Guido van Rossum and "
        "first released in 1991, it emphasizes code readability with its notable "
        "use of significant indentation.\n"
        "\"\"\"\n"
        f"{SENTINEL_DONE}"
    )

    parsed, raw = launch_claude(task_prompt, interactive=args.interactive)

    # ---------------------------------------------------------------------
    # Display what we got back (skip if user ran interactive mode).
    # ---------------------------------------------------------------------
    if args.interactive:
        logger.info("Interactive session terminated by user")
    else:
        print("--- Raw output from Claude ---")
        print(raw)
        print("\n--- Parsed JSON (if any) ---")
        print(json.dumps(parsed, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
