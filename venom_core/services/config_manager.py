"""
Moduł: config_manager - Zarządzanie konfiguracją runtime Venom.

Odpowiada za:
- Pobieranie whitelisty parametrów z .env
- Walidację i zapis zmian konfiguracji
- Backup .env do config/env-history/
- Określanie, które usługi wymagają restartu po zmianie
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field, validator

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


# Whitelist parametrów dostępnych do edycji przez UI
CONFIG_WHITELIST = {
    # AI Configuration
    "AI_MODE",
    "LLM_SERVICE_TYPE",
    "LLM_LOCAL_ENDPOINT",
    "LLM_MODEL_NAME",
    "LLM_LOCAL_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "HYBRID_CLOUD_PROVIDER",
    "HYBRID_LOCAL_MODEL",
    "HYBRID_CLOUD_MODEL",
    "SENSITIVE_DATA_LOCAL_ONLY",
    "ENABLE_MODEL_ROUTING",
    "FORCE_LOCAL_MODEL",
    "ENABLE_MULTI_SERVICE",
    # LLM Server Commands
    "VLLM_START_COMMAND",
    "VLLM_STOP_COMMAND",
    "OLLAMA_START_COMMAND",
    "OLLAMA_STOP_COMMAND",
    # Hive Configuration
    "ENABLE_HIVE",
    "HIVE_URL",
    "HIVE_REGISTRATION_TOKEN",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "REDIS_PASSWORD",
    "HIVE_HIGH_PRIORITY_QUEUE",
    "HIVE_BACKGROUND_QUEUE",
    "HIVE_BROADCAST_CHANNEL",
    "HIVE_TASK_TIMEOUT",
    "HIVE_MAX_RETRIES",
    # Nexus Configuration
    "ENABLE_NEXUS",
    "NEXUS_SHARED_TOKEN",
    "NEXUS_HEARTBEAT_TIMEOUT",
    "NEXUS_PORT",
    # Background Tasks
    "VENOM_PAUSE_BACKGROUND_TASKS",
    "ENABLE_AUTO_DOCUMENTATION",
    "ENABLE_AUTO_GARDENING",
    "ENABLE_MEMORY_CONSOLIDATION",
    "ENABLE_HEALTH_CHECKS",
    "WATCHER_DEBOUNCE_SECONDS",
    "IDLE_THRESHOLD_MINUTES",
    # Shadow Agent
    "ENABLE_PROACTIVE_MODE",
    "ENABLE_DESKTOP_SENSOR",
    "SHADOW_CONFIDENCE_THRESHOLD",
    "SHADOW_PRIVACY_FILTER",
    "SHADOW_CLIPBOARD_MAX_LENGTH",
    "SHADOW_CHECK_INTERVAL",
    # Ghost Agent
    "ENABLE_GHOST_AGENT",
    "GHOST_MAX_STEPS",
    "GHOST_STEP_DELAY",
    "GHOST_VERIFICATION_ENABLED",
    "GHOST_SAFETY_DELAY",
    "GHOST_VISION_CONFIDENCE",
    # Audio Interface
    "ENABLE_AUDIO_INTERFACE",
    "WHISPER_MODEL_SIZE",
    "TTS_MODEL_PATH",
    "AUDIO_DEVICE",
    "VAD_THRESHOLD",
    "SILENCE_DURATION",
}

# Parametry sekretów (maskowane w UI)
SECRET_PARAMS = {
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "HIVE_REGISTRATION_TOKEN",
    "NEXUS_SHARED_TOKEN",
    "REDIS_PASSWORD",
    "LLM_LOCAL_API_KEY",
    "TTS_MODEL_PATH",
}

# Mapowanie parametrów na usługi wymagające restartu
RESTART_REQUIREMENTS = {
    "AI_MODE": ["backend"],
    "LLM_SERVICE_TYPE": ["backend"],
    "LLM_LOCAL_ENDPOINT": ["backend"],
    "LLM_MODEL_NAME": ["backend"],
    "HYBRID_CLOUD_PROVIDER": ["backend"],
    "HYBRID_LOCAL_MODEL": ["backend"],
    "HYBRID_CLOUD_MODEL": ["backend"],
    "ENABLE_MODEL_ROUTING": ["backend"],
    "FORCE_LOCAL_MODEL": ["backend"],
    "VLLM_START_COMMAND": [],
    "VLLM_STOP_COMMAND": [],
    "OLLAMA_START_COMMAND": [],
    "OLLAMA_STOP_COMMAND": [],
    "ENABLE_HIVE": ["backend"],
    "HIVE_URL": ["backend"],
    "REDIS_HOST": ["backend"],
    "REDIS_PORT": ["backend"],
    "ENABLE_NEXUS": ["backend"],
    "NEXUS_PORT": ["backend"],
    "VENOM_PAUSE_BACKGROUND_TASKS": ["backend"],
    "ENABLE_AUTO_DOCUMENTATION": ["backend"],
    "ENABLE_AUTO_GARDENING": ["backend"],
    "ENABLE_GHOST_AGENT": ["backend"],
    "ENABLE_DESKTOP_SENSOR": ["backend"],
    "ENABLE_AUDIO_INTERFACE": ["backend"],
}


class ConfigUpdateRequest(BaseModel):
    """Request do aktualizacji konfiguracji."""

    updates: Dict[str, Any] = Field(..., description="Mapa klucz->wartość do aktualizacji")

    @validator("updates")
    def validate_whitelist(cls, v):
        """Sprawdź czy wszystkie klucze są na whiteliście."""
        invalid_keys = set(v.keys()) - CONFIG_WHITELIST
        if invalid_keys:
            # Nie ujawniamy które klucze są nieprawidłowe ze względów bezpieczeństwa
            raise ValueError(
                f"Znaleziono {len(invalid_keys)} nieprawidłowych kluczy konfiguracji"
            )
        return v


class ConfigManager:
    """Manager konfiguracji runtime."""

    def __init__(self):
        """Inicjalizacja managera."""
        self.project_root = Path(__file__).parent.parent.parent
        self.env_file = self.project_root / ".env"
        self.env_history_dir = self.project_root / "config" / "env-history"
        self.env_history_dir.mkdir(parents=True, exist_ok=True)

    def get_config(self, mask_secrets: bool = True) -> Dict[str, Any]:
        """
        Pobiera aktualną konfigurację.

        Args:
            mask_secrets: Czy maskować sekrety

        Returns:
            Słownik z konfiguracją
        """
        config = {}

        # Wczytaj .env
        env_values = self._read_env_file()

        # Zwróć tylko parametry z whitelisty
        for key in CONFIG_WHITELIST:
            value = env_values.get(key, "")

            # Maskuj sekrety jeśli potrzeba
            if mask_secrets and key in SECRET_PARAMS and value:
                config[key] = self._mask_secret(value)
            else:
                config[key] = value

        return config

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aktualizuje konfigurację.

        Args:
            updates: Mapa klucz->wartość do aktualizacji

        Returns:
            Słownik z rezultatem operacji
        """
        logger.info(f"Aktualizacja konfiguracji: {list(updates.keys())}")

        # Walidacja
        try:
            ConfigUpdateRequest(updates=updates)
        except Exception as e:
            return {
                "success": False,
                "message": f"Błąd walidacji: {str(e)}",
                "restart_required": [],
            }

        # Backup .env
        backup_path = self._backup_env_file()
        if not backup_path:
            return {
                "success": False,
                "message": "Nie udało się utworzyć backupu .env",
                "restart_required": [],
            }

        # Wczytaj aktualny .env
        env_values = self._read_env_file()

        # Zastosuj zmiany
        changed_keys = []
        for key, value in updates.items():
            old_value = env_values.get(key, "")
            if str(value) != str(old_value):
                env_values[key] = str(value)
                changed_keys.append(key)

        # Zapisz .env
        try:
            self._write_env_file(env_values)
        except Exception as e:
            logger.exception("Błąd zapisu .env")
            return {
                "success": False,
                "message": f"Błąd zapisu .env: {str(e)}",
                "restart_required": [],
            }

        # Określ które usługi wymagają restartu
        restart_services = self._determine_restart_services(changed_keys)

        message = f"Zaktualizowano {len(changed_keys)} parametrów. Backup: {backup_path.name}"
        logger.info(message)

        return {
            "success": True,
            "message": message,
            "restart_required": list(restart_services),
            "changed_keys": changed_keys,
            "backup_path": str(backup_path),
        }

    def _read_env_file(self) -> Dict[str, str]:
        """Wczytuje .env do słownika."""
        env_values = {}

        if not self.env_file.exists():
            logger.warning(f".env nie istnieje: {self.env_file}")
            return env_values

        try:
            with open(self.env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # Parsuj linie KEY=VALUE
                    match = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line)
                    if match:
                        key, value = match.groups()
                        # Usuń cudzysłowy jeśli są
                        value = value.strip().strip('"').strip("'")
                        env_values[key] = value

        except Exception as e:
            logger.exception("Błąd wczytywania .env")

        return env_values

    def _write_env_file(self, env_values: Dict[str, str]):
        """Zapisuje słownik do .env."""
        # Wczytaj oryginał aby zachować komentarze i strukturę
        original_lines = []
        if self.env_file.exists():
            with open(self.env_file, "r", encoding="utf-8") as f:
                original_lines = f.readlines()

        # Zbuduj nowy plik
        new_lines = []
        processed_keys = set()

        for line in original_lines:
            stripped = line.strip()

            # Zachowaj puste linie i komentarze
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue

            # Sprawdź czy to linia KEY=VALUE
            match = re.match(r"^([A-Z_][A-Z0-9_]*)=", stripped)
            if match:
                key = match.group(1)
                if key in env_values:
                    # Zastąp wartość
                    new_lines.append(f"{key}={env_values[key]}\n")
                    processed_keys.add(key)
                else:
                    # Zachowaj oryginalną linię
                    new_lines.append(line)
            else:
                # Zachowaj linię
                new_lines.append(line)

        # Dodaj nowe klucze które nie były w oryginalnym pliku
        for key, value in env_values.items():
            if key not in processed_keys:
                new_lines.append(f"{key}={value}\n")

        # Zapisz
        with open(self.env_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    def _backup_env_file(self) -> Optional[Path]:
        """Tworzy backup .env do config/env-history/."""
        if not self.env_file.exists():
            return None

        try:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_name = f".env-{timestamp}"
            backup_path = self.env_history_dir / backup_name

            shutil.copy2(self.env_file, backup_path)
            logger.info(f"Utworzono backup .env: {backup_path}")

            # Usuń stare backupy (zachowaj ostatnie 50)
            self._cleanup_old_backups(max_keep=50)

            return backup_path

        except Exception as e:
            logger.exception("Błąd tworzenia backupu .env")
            return None

    def _cleanup_old_backups(self, max_keep: int = 50):
        """Usuwa stare backupy .env."""
        try:
            backups = sorted(
                self.env_history_dir.glob(".env-*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            # Usuń nadmiarowe backupy
            for backup in backups[max_keep:]:
                backup.unlink()
                logger.debug(f"Usunięto stary backup: {backup.name}")

        except Exception as e:
            logger.warning(f"Błąd czyszczenia starych backupów: {e}")

    def _determine_restart_services(self, changed_keys: List[str]) -> Set[str]:
        """Określa które usługi wymagają restartu."""
        restart_services = set()

        for key in changed_keys:
            services = RESTART_REQUIREMENTS.get(key, [])
            restart_services.update(services)

        return restart_services

    def _mask_secret(self, value: str) -> str:
        """Maskuje sekret."""
        if not value:
            return ""

        if len(value) <= 8:
            return "*" * len(value)

        # Pokaż pierwsze 4 i ostatnie 4 znaki
        return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"

    def get_backup_list(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Pobiera listę backupów .env."""
        try:
            backups = sorted(
                self.env_history_dir.glob(".env-*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            result = []
            for backup in backups[:limit]:
                stat = backup.stat()
                result.append(
                    {
                        "filename": backup.name,
                        "path": str(backup),
                        "size_bytes": stat.st_size,
                        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    }
                )

            return result

        except Exception as e:
            logger.warning(f"Błąd pobierania listy backupów: {e}")
            return []

    def restore_backup(self, backup_filename: str) -> Dict[str, Any]:
        """Przywraca .env z backupu."""
        # SECURITY: Validate backup_filename to prevent path traversal
        # Only allow filenames matching the expected pattern: .env-YYYYMMDD-HHMMSS
        if not re.match(r'^\.env-\d{8}-\d{6}$', backup_filename):
            return {
                "success": False,
                "message": "Nieprawidłowa nazwa pliku backupu",
            }
        
        # Ensure the filename doesn't contain path separators
        if '/' in backup_filename or '\\' in backup_filename or '..' in backup_filename:
            return {
                "success": False,
                "message": "Nieprawidłowa nazwa pliku backupu",
            }
        
        backup_path = self.env_history_dir / backup_filename

        if not backup_path.exists():
            return {
                "success": False,
                "message": f"Backup nie istnieje: {backup_filename}",
            }

        try:
            # Najpierw zrób backup aktualnego .env
            current_backup = self._backup_env_file()

            # Przywróć z backupu
            shutil.copy2(backup_path, self.env_file)

            logger.info(f"Przywrócono .env z backupu: {backup_filename}")

            return {
                "success": True,
                "message": f"Przywrócono .env z backupu: {backup_filename}. Aktualny .env zapisany jako: {current_backup.name if current_backup else 'N/A'}",
                "restart_required": ["backend", "ui"],
            }

        except Exception as e:
            logger.exception("Błąd przywracania backupu")
            return {
                "success": False,
                "message": f"Błąd przywracania backupu: {str(e)}",
            }


# Singleton
config_manager = ConfigManager()
