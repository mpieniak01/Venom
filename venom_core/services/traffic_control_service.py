"""Helpers for route/service access to Traffic Control runtime state."""

from __future__ import annotations

from typing import Any


def get_traffic_controller() -> Any:
    from venom_core.infrastructure.traffic_control import get_traffic_controller as _get

    return _get()
