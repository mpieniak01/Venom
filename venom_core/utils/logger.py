import sys
from pathlib import Path

from loguru import logger

# Upewniamy się, że katalog na logi istnieje
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Globalna referencja do EventBroadcaster (będzie ustawiona przez main.py)
_event_broadcaster = None


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
        message: Wiadomość z loguru
    """
    if _event_broadcaster is not None:
        # Parsuj rekord loga
        record = message.record
        level = record["level"].name
        msg = record["message"]
        timestamp = record["time"].isoformat()

        # Wyślij przez WebSocket (async, ale w sync kontekście)
        # Używamy asyncio.create_task aby nie blokować loggera
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    _event_broadcaster.broadcast_log(level=level, message=msg)
                )
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

