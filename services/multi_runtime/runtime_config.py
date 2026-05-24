"""Shared runtime config reads for multi_runtime service modules."""

from __future__ import annotations

import os

from venom_core.config import SETTINGS


def read_config_str(name: str, default: str = "") -> str:
    raw = getattr(SETTINGS, name, None)
    if raw is None or str(raw).strip() == "":
        raw = os.environ.get(name)
    if raw is None:
        return default
    text = str(raw).strip()
    return text or default


def read_config_int(name: str, default: int) -> int:
    raw = read_config_str(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default
