"""Snapshot runtime diagnostics endpoints for quick review."""

from __future__ import annotations

import json

import requests


def main() -> None:
    base = "http://127.0.0.1:8014"
    status = requests.get(f"{base}/status", timeout=5)
    daemon_status = requests.get(f"{base}/v1/daemon/status", timeout=5)
    components = requests.get(f"{base}/v1/components", timeout=5)

    for response in (status, daemon_status, components):
        response.raise_for_status()

    snapshot = {
        "status": status.json(),
        "daemon_status": daemon_status.json(),
        "components": components.json(),
    }
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
