import sys
from pathlib import Path

from loguru import logger

# Upewniamy się, że katalog na logi istnieje
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
    "<level>{message}</level>",
)

logger.add(LOG_DIR / "venom.log", rotation="10 MB")


def get_logger(name: str):
    """Zwraca logger z podaną nazwą."""
    return logger.bind(name=name)
