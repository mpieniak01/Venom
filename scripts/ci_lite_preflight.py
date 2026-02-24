#!/usr/bin/env python3
"""Validate CI-lite Python dependencies before running lite audits/tests."""

from __future__ import annotations

import importlib.util
import os
import sys

REQUIRED_PACKAGES = ["pytest", "pydantic", "fastapi", "semantic_kernel", "numpy"]


def main() -> int:
    missing = [
        name for name in REQUIRED_PACKAGES if importlib.util.find_spec(name) is None
    ]
    if not missing:
        print("✅ CI-lite preflight OK")
        return 0

    hint = (
        "Uruchom: pip install -r requirements-ci-lite.txt"
        if os.environ.get("CI") == "true"
        else "Uruchom: make ci-lite-bootstrap"
    )
    print(
        "❌ Brak wymaganych pakietów CI-lite: " + ", ".join(missing) + "\n   " + hint,
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
