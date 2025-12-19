#!/usr/bin/env python3
"""
Compatibility wrapper for manual testing.

Prefer running:
  uv run src/tools/codex_live_view.py ...
"""

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.tools.codex_live_view import main


if __name__ == "__main__":
    main()
