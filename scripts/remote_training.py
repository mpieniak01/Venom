#!/usr/bin/env python3
"""Explicit local or SSH training CLI; no automatic model or service startup."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from venom_core.services.remote_training.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
