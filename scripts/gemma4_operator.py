#!/usr/bin/env python3
"""Prepare Gemma operator evidence on CPU; paid training is a separate operation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from venom_core.services.gemma4_operator.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
