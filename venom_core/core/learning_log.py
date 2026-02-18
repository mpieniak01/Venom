"""Obsługa boot_id i wpisów dla logu uczenia (requests.jsonl)."""

import json
from pathlib import Path
from typing import Any

from venom_core.utils.boot_id import BOOT_ID
from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

LEARNING_LOG_PATH = Path("./data/learning/requests.jsonl")
LEARNING_LOG_META_PATH = Path("./data/learning/requests_meta.json")


def ensure_learning_log_boot_id() -> None:
    """Czyści log uczenia po restarcie backendu (zmiana boot_id)."""
    try:
        if LEARNING_LOG_META_PATH.exists():
            payload = json.loads(LEARNING_LOG_META_PATH.read_text(encoding="utf-8"))
            stored_boot = payload.get("boot_id")
            if stored_boot and stored_boot != BOOT_ID:
                if LEARNING_LOG_PATH.exists():
                    LEARNING_LOG_PATH.unlink(missing_ok=True)
        else:
            LEARNING_LOG_META_PATH.parent.mkdir(parents=True, exist_ok=True)
        LEARNING_LOG_META_PATH.write_text(
            json.dumps({"boot_id": BOOT_ID}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Nie udało się sprawdzić boot_id logu uczenia: %s", exc)


def append_learning_log_entry(entry: dict[str, Any]) -> None:
    """Append single JSON entry to learning log in JSONL format."""
    try:
        ensure_learning_log_boot_id()
        LEARNING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(entry)
        payload.setdefault("timestamp", get_utc_now_iso())
        with LEARNING_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Nie udało się zapisać wpisu learning log: %s", exc)
