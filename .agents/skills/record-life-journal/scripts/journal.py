#!/usr/bin/env python3
"""Thin project-local entrypoint for the deterministic diary core."""

from diary_agent.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

