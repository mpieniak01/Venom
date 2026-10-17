#!/usr/bin/env python3
"""Thin executable wrapper; all behavior lives in the shared service."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from venom_core.services.vast_environments.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
