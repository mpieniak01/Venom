"""Shared helpers for 221B model introspection scripts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request


def read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def env_value(name: str, env_file: dict[str, str], default: str) -> str:
    if name in os.environ:
        return os.environ[name]
    if name in env_file:
        return env_file[name]
    return default


def base_url_from_env(default: str = "http://127.0.0.1:8000") -> str:
    return os.getenv("VENOM_BASE_URL", default).rstrip("/")


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_sec: float = 30.0,
) -> tuple[int, Any]:
    data_bytes: bytes | None = None
    headers: dict[str, str] = {}
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url=url, method=method, data=data_bytes, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), json.loads(raw) if raw.strip() else None
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}
