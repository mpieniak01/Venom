"""Konfiguracja Venom Spore."""

import os

from pydantic import ConfigDict, SecretStr
from pydantic_settings import BaseSettings


class SporeSettings(BaseSettings):
    """Konfiguracja Venom Spore."""

    model_config = ConfigDict(env_file=".env", env_prefix="SPORE_")

    # Podstawowa konfiguracja
    NODE_NAME: str = os.getenv("HOSTNAME", "venom-spore-1")
    NEXUS_HOST: str = "localhost"
    NEXUS_PORT: int = 8000
    SHARED_TOKEN: SecretStr = SecretStr("")

    # Możliwości węzła
    ENABLE_SHELL: bool = True
    ENABLE_FILE: bool = True
    ENABLE_DOCKER: bool = False
    ENABLE_CAMERA: bool = False

    # Tags opisujące węzeł
    NODE_TAGS: str = (
        ""  # Tagi rozdzielone przecinkami, np. "location:server_room,gpu,camera"
    )

    # Heartbeat
    HEARTBEAT_INTERVAL: int = 30  # Sekundy między heartbeat


SPORE_SETTINGS = SporeSettings()
