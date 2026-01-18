"""Obsługa boot_id dla logu uczenia (requests.jsonl)."""

import json
from pathlib import Path

from venom_core.utils.boot_id import BOOT_ID
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
        logger.warning("Nie udalo sie sprawdzic boot_id logu uczenia: %s", exc)
