#!/usr/bin/env python3
"""202C runtime switch soak (ollama -> onnx -> ollama + unload-all)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _202c_common import (
    activate_runtime,
    dump_json,
    get_active_runtime,
    http_json,
    pick_gemma3_model,
    resolve_base_url,
    wait_backend_ready,
)

CRITICAL_FAILURES = {
    "activate_failed",
    "stuck_runtime",
    "contract_break",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="202C runtime switch soak")
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--sequence", default="ollama,onnx,ollama")
    parser.add_argument(
        "--json-output",
        default="test-results/202c/switch_soak_report.json",
    )
    return parser.parse_args()


def _verify_active(
    base_url: str, expected_runtime: str
) -> tuple[bool, str, dict[str, Any]]:
    code, payload = get_active_runtime(base_url)
    if code != 200 or not isinstance(payload, dict):
        return False, "contract_break", {"status": code, "payload": payload}
    active = str(payload.get("active_server") or "").strip().lower()
    if active != expected_runtime:
        return (
            False,
            "stuck_runtime",
            {
                "expected_runtime": expected_runtime,
                "active_server": active,
                "payload": payload,
            },
        )
    return True, "ok", payload


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[2]
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = (root / env_file).resolve()

    base_url = resolve_base_url(env_file=env_file, explicit=args.base_url)
    sequence = [
        item.strip().lower() for item in args.sequence.split(",") if item.strip()
    ]

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "cycles": args.cycles,
        "sequence": sequence,
        "events": [],
        "critical_failures": [],
        "counters": {
            "activate_failed": 0,
            "stuck_runtime": 0,
            "contract_break": 0,
            "unload_failed": 0,
            "cycles_completed": 0,
        },
    }

    if not wait_backend_ready(base_url, timeout_sec=30):
        report["critical_failures"].append("backend_not_ready")
        dump_json((root / args.json_output).resolve(), report)
        return 1

    code, options_payload = http_json(
        f"{base_url}/api/v1/system/llm-runtime/options", timeout_sec=30.0
    )
    if code != 200 or not isinstance(options_payload, dict):
        report["critical_failures"].append("runtime_options_unavailable")
        dump_json((root / args.json_output).resolve(), report)
        return 1

    model_by_runtime: dict[str, str | None] = {}
    for runtime in sequence:
        model_by_runtime[runtime] = pick_gemma3_model(options_payload, runtime)

    for cycle in range(1, args.cycles + 1):
        cycle_errors: list[str] = []
        steps: list[dict[str, Any]] = []

        for runtime in sequence:
            model_name = model_by_runtime.get(runtime)
            ok, message, activation_payload = activate_runtime(
                base_url, runtime, model_name
            )
            step = {
                "cycle": cycle,
                "runtime": runtime,
                "model": model_name,
                "activation_ok": ok,
                "activation_message": message,
                "activation_payload": activation_payload,
            }
            if not ok:
                report["counters"]["activate_failed"] += 1
                cycle_errors.append("activate_failed")
                steps.append(step)
                continue

            verify_ok, verify_reason, verify_payload = _verify_active(base_url, runtime)
            step["verify_ok"] = verify_ok
            step["verify_reason"] = verify_reason
            step["verify_payload"] = verify_payload
            if not verify_ok:
                report["counters"][verify_reason] += 1
                cycle_errors.append(verify_reason)
            steps.append(step)

            unload_code, unload_payload = http_json(
                f"{base_url}/api/v1/models/unload-all",
                method="POST",
                payload={},
                timeout_sec=60.0,
            )
            unload_ok = unload_code == 200
            steps.append(
                {
                    "cycle": cycle,
                    "runtime": runtime,
                    "action": "unload-all",
                    "ok": unload_ok,
                    "status": unload_code,
                    "payload": unload_payload,
                }
            )
            if not unload_ok:
                report["counters"]["unload_failed"] += 1

        report["events"].append(
            {
                "cycle": cycle,
                "errors": sorted(set(cycle_errors)),
                "steps": steps,
            }
        )
        if not cycle_errors:
            report["counters"]["cycles_completed"] += 1

    for key in CRITICAL_FAILURES:
        if report["counters"].get(key, 0) > 0:
            report["critical_failures"].append(key)

    dump_json((root / args.json_output).resolve(), report)

    return 0 if not report["critical_failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
