#!/usr/bin/env python3
"""Thin project-local entrypoint for the deterministic diary core."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from diary_agent.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

