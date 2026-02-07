import asyncio
import sys
from pathlib import Path
from typing import Any

from loguru import logger

# Upewniamy się, że katalog na logi istnieje
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Globalna referencja do EventBroadcaster (będzie ustawiona przez main.py)
_event_broadcaster = None
_log_tasks: set[asyncio.Task[Any]] = set()


def set_event_broadcaster(broadcaster):
    """
    Ustawia EventBroadcaster dla live log streaming.

    Args:
        broadcaster: Instancja EventBroadcaster
    """
    global _event_broadcaster
    _event_broadcaster = broadcaster


def log_sink(message):
    """
    Custom sink dla loguru który przekazuje logi do EventBroadcaster.

    Args:
        message: LogRecord z loguru - obiekt zawierający informacje o logu
    """
    if _event_broadcaster is not None:
        # Walidacja typu
        if not hasattr(message, "record"):
            return

        # Parsuj rekord loga
        record = message.record
        level = record["level"].name
        msg = record["message"]

        # Wyślij przez WebSocket (async, ale w sync kontekście)
        # Trzymamy referencję do taska, aby uniknąć przedwczesnego GC.
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                try:
                    task = loop.create_task(
                        _event_broadcaster.broadcast_log(level=level, message=msg)
                    )
                    _log_tasks.add(task)
                    task.add_done_callback(_log_tasks.discard)
                except Exception:
                    # Błąd przy tworzeniu zadania - pomijamy aby nie zablokować loggera
                    pass
        except RuntimeError:
            # Brak event loop - pomijamy broadcast
            pass


logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
    "<level>{message}</level>",
)

logger.add(LOG_DIR / "venom.log", rotation="10 MB")

# Dodaj custom sink dla live streaming
logger.add(log_sink, format="{message}")


def get_logger(name: str):
    """Zwraca logger z podaną nazwą."""
    return logger.bind(name=name)
