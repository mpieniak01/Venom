"""Probe current component snapshot from local multi_runtime daemon."""

from __future__ import annotations

import json

import requests


def main() -> None:
    base_url = "http://127.0.0.1:8014"
    resp = requests.get(f"{base_url}/v1/components", timeout=3)
    resp.raise_for_status()
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
