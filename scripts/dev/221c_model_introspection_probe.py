#!/usr/bin/env python3
"""221C probe: optionally run live model analysis from Inspector flow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.dev.model_introspection_221b_utils import (  # noqa: E402
    base_url_from_env,
    env_value,
    read_env_file,
    request_json,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="221C model introspection probe")
    parser.add_argument(
        "--base-url",
        default=base_url_from_env("http://127.0.0.1:8000"),
        help="Base URL for the Venom API (default: %(default)s).",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Optional .env file used as fallback for environment values.",
    )
    parser.add_argument(
        "--prompt",
        default="Co to jest slonce?",
        help="Prompt sent to the active model when live analysis is enabled.",
    )
    parser.add_argument(
        "--live-analysis-enabled",
        action="store_true",
        help="Execute the active model. Disabled by default for stack safety.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=128,
        help="Max tokens for the optional live analysis request.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Temperature for the optional live analysis request.",
    )
    parser.add_argument(
        "--output",
        default="test-results/benchmarks/221c_model_introspection_probe.json",
        help="Where to write the JSON snapshot.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    env_file = {}
    if args.env_file:
        env_path = Path(args.env_file)
        if env_path.exists():
            env_file = read_env_file(env_path)

    base_url = env_value("VENOM_BASE_URL", env_file, args.base_url).rstrip("/")
    payload = {
        "prompt": args.prompt,
        "live_analysis_enabled": bool(args.live_analysis_enabled),
        "max_tokens": int(args.max_tokens),
        "temperature": float(args.temperature),
    }
    status, response_payload = request_json(
        f"{base_url}/api/v1/models/introspection/analyze",
        method="POST",
        payload=payload,
    )
    if status != 200:
        print(json.dumps(response_payload, indent=2, ensure_ascii=False))
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(response_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(response_payload, indent=2, ensure_ascii=False))
    print(f"Saved analysis snapshot: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
