"""Probe retrieval mode behavior in runtime response diagnostics."""

from __future__ import annotations

import json

import requests


def _set_mode(mode: str) -> None:
    url = "http://127.0.0.1:8014/v1/daemon/profile"
    resp = requests.post(url, json={"retrieval_mode": mode}, timeout=5)
    resp.raise_for_status()


def _respond() -> dict:
    url = "http://127.0.0.1:8014/v1/respond"
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Krótka odpowiedź testowa."}],
            }
        ],
    }
    resp = requests.post(url, json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    summary: dict[str, object] = {}
    for mode in ("off", "auto", "always"):
        _set_mode(mode)
        response = _respond()
        summary[mode] = {
            "retrieval_used": response.get("retrieval_used"),
            "execution_trace": response.get("execution_trace", []),
        }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
