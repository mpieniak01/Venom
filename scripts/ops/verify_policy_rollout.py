#!/usr/bin/env python3
"""Validate 201D runtime-only policy rollout across environments."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

ROLLOUT_PATH = "/api/v1/system/autonomy/rollout-status"
OBSERVABILITY_PATH = "/api/v1/system/autonomy/observability"


@dataclass
class EnvironmentCheck:
    base_url: str
    ok: bool
    detail: str


def _fetch_json(base_url: str, path: str, timeout: float) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _check_environment(base_url: str, timeout: float) -> EnvironmentCheck:
    try:
        rollout = _fetch_json(base_url, ROLLOUT_PATH, timeout=timeout)
        observability = _fetch_json(base_url, OBSERVABILITY_PATH, timeout=timeout)
    except urllib.error.HTTPError as exc:
        return EnvironmentCheck(
            base_url=base_url,
            ok=False,
            detail=f"HTTP {exc.code}: {exc.reason}",
        )
    except urllib.error.URLError as exc:
        return EnvironmentCheck(
            base_url=base_url,
            ok=False,
            detail=f"Network error: {exc.reason}",
        )
    except Exception as exc:  # pragma: no cover - hard-failure fallback
        return EnvironmentCheck(
            base_url=base_url,
            ok=False,
            detail=f"Unexpected error: {exc}",
        )

    readiness = str(rollout.get("readiness", "")).strip().lower()
    policy_enabled = bool(rollout.get("policy_gate_enabled"))
    runtime_only = bool(rollout.get("runtime_only_architecture"))
    observability_ok = isinstance(observability.get("policy"), dict)
    ok = readiness == "ready" and policy_enabled and runtime_only and observability_ok
    detail = (
        f"readiness={readiness}, policy_gate_enabled={policy_enabled}, "
        f"runtime_only_architecture={runtime_only}, observability={observability_ok}"
    )
    return EnvironmentCheck(base_url=base_url, ok=ok, detail=detail)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate runtime-only policy rollout readiness on target environments.",
    )
    parser.add_argument(
        "--base-url",
        action="append",
        required=True,
        help="Environment base URL, e.g. http://localhost:8000",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Request timeout in seconds.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = [_check_environment(url, timeout=args.timeout) for url in args.base_url]

    print("201D rollout verification")
    for check in checks:
        state = "PASS" if check.ok else "FAIL"
        print(f"- {state} {check.base_url}: {check.detail}")

    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
