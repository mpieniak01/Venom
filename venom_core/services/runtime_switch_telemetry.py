"""Runtime switch telemetry helpers used across API/service entrypoints."""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import HTTPException

from venom_core.core import metrics as metrics_module
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

ALLOWED_RUNTIME_SWITCH_SOURCES = {"ui", "make_start"}
_missing_runtime_switch_token_warned = False


def normalize_runtime_switch_source(raw_source: str | None) -> str:
    source = str(raw_source or "").strip().lower()
    return source or "ui"


def assert_runtime_switch_source_allowed(raw_source: str | None) -> str:
    source = normalize_runtime_switch_source(raw_source)
    if source not in ALLOWED_RUNTIME_SWITCH_SOURCES:
        raise HTTPException(
            status_code=403,
            detail=(
                "Nieautoryzowane źródło przełączenia runtime. "
                "Dozwolone: ui, make_start."
            ),
        )
    return source


def assert_runtime_switch_ownership_token(request_token: str | None) -> None:
    global _missing_runtime_switch_token_warned
    required = str(os.getenv("VENOM_RUNTIME_SWITCH_TOKEN", "")).strip()
    if not required:
        if not _missing_runtime_switch_token_warned:
            logger.warning(
                "VENOM_RUNTIME_SWITCH_TOKEN is not configured; runtime switch "
                "ownership checks are disabled."
            )
            _missing_runtime_switch_token_warned = True
        return
    provided = str(request_token or "").strip()
    if not hmac.compare_digest(provided, required):
        raise HTTPException(
            status_code=403,
            detail="Brak poprawnego ownership_token dla przełączenia runtime.",
        )


def emit_runtime_model_event(event_name: str, **payload: Any) -> None:
    logger.info(
        "runtime_event={} {}",
        event_name,
        ", ".join(f"{key}={value}" for key, value in sorted(payload.items())),
    )
    collector = metrics_module.get_metrics_collector()
    if collector is None:
        return
    collector.record_runtime_switch_event(
        event_name=event_name,
        source=str(payload.get("source") or ""),
        runtime=str(payload.get("runtime") or ""),
    )
