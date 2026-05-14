"""Shared helpers for 217DB probe scripts."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from typing import Any

import requests


def base_url_from_args(default_port: int = 8014) -> str:
    raw = os.getenv("VENOM_MULTI_RUNTIME_BASE_URL", "").strip()
    if raw:
        return raw.rstrip("/")
    port = os.getenv("VENOM_MULTI_RUNTIME_PORT", str(default_port)).strip()
    return f"http://127.0.0.1:{port}"


def daemon_base_url() -> str:
    return f"{base_url_from_args()}/v1"


def request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    response = requests.request(
        method,
        f"{daemon_base_url()}{path}",
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def print_json(payload: Any) -> None:
    if is_dataclass(payload):
        payload = asdict(payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
