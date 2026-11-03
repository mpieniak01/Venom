#!/usr/bin/env python3
"""Prepare and run the opt-in FunctionGemma experiment."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from venom_core.services.functiongemma.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
