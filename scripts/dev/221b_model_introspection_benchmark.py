#!/usr/bin/env python3
"""221B benchmark: latency and payload size of model introspection snapshot."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.dev.model_introspection_221b_utils import (  # noqa: E402
    base_url_from_env,
    request_json,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="221B model introspection benchmark")
    parser.add_argument(
        "--base-url",
        default=base_url_from_env("http://127.0.0.1:8000"),
        help="Base URL for the Venom API (default: %(default)s).",
    )
    parser.add_argument("--runs", type=int, default=5, help="Number of runs.")
    parser.add_argument(
        "--output",
        default="test-results/benchmarks/221b_model_introspection_benchmark.json",
        help="Where to write the benchmark report.",
    )
    return parser


def _run_once(base_url: str) -> dict[str, object]:
    started = time.perf_counter()
    status, payload = request_json(f"{base_url}/api/v1/models/introspection")
    elapsed = time.perf_counter() - started
    if status != 200:
        raise RuntimeError(f"introspection request failed: status={status}")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    snapshot = payload.get("snapshot", {}) if isinstance(payload, dict) else {}
    return {
        "elapsed_sec": round(elapsed, 4),
        "payload_bytes": len(body),
        "runtime_label": snapshot.get("summary", {}).get("runtime_label"),
        "provider": snapshot.get("summary", {}).get("provider"),
        "packages": snapshot.get("available_packages", []),
    }


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    runs = max(1, int(args.runs))
    try:
        samples = [_run_once(args.base_url.rstrip("/")) for _ in range(runs)]
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    elapsed = [float(sample["elapsed_sec"]) for sample in samples]
    payload_sizes = [int(sample["payload_bytes"]) for sample in samples]

    report = {
        "runs": runs,
        "base_url": args.base_url.rstrip("/"),
        "samples": samples,
        "summary": {
            "elapsed_sec_mean": round(statistics.mean(elapsed), 4),
            "elapsed_sec_median": round(statistics.median(elapsed), 4),
            "payload_bytes_mean": round(statistics.mean(payload_sizes), 2),
            "payload_bytes_max": max(payload_sizes),
            "payload_bytes_min": min(payload_sizes),
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Saved benchmark report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
