#!/usr/bin/env python3
"""Export FastAPI OpenAPI schema to a JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export OpenAPI schema")
    parser.add_argument(
        "--output",
        default="openapi/openapi.json",
        help="Path to output OpenAPI JSON file",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation level",
    )
    return parser.parse_args()


def main() -> int:
    from venom_core.main import app

    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    output_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=args.indent) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI exported to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
