
from loguru import logger
from pathlib import Path
import sys

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
