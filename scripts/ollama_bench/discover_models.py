#!/usr/bin/env python3
# ruff: noqa: E402
"""Wylistowanie modeli dostępnych w lokalnym Ollama."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json

from scripts.ollama_bench.common import DEFAULT_OLLAMA_ENDPOINT, discover_models


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover local Ollama models")
    parser.add_argument("--endpoint", default=DEFAULT_OLLAMA_ENDPOINT)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument(
        "--out", default="", help="Optional path to save model list JSON"
    )
    args = parser.parse_args()

    models = discover_models(endpoint=args.endpoint, timeout=args.timeout)
    payload = {"count": len(models), "models": models}

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for model in models:
            print(model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
