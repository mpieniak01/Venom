#!/usr/bin/env python3
"""217DB probe: live component snapshot from multi_runtime daemon."""

from __future__ import annotations

from _217db_probe_utils import print_json, request_json


def main() -> int:
    payload = request_json("GET", "/components")
    print_json(
        {
            "runtime_id": payload.get("runtime_id"),
            "timestamp_ms": payload.get("timestamp_ms"),
            "components": payload.get("components", []),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
