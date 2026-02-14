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

from pydantic import BaseModel, Field, SecretStr, field_validator

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)


# Whitelist parametrów dostępnych do edycji przez UI
CONFIG_WHITELIST = {
    # AI Configuration
    "AI_MODE",
    "LLM_SERVICE_TYPE",
    "LLM_LOCAL_ENDPOINT",
    "URL_SCHEME_POLICY",
    "LLM_MODEL_NAME",
    "ACTIVE_PROVIDER",
    "WORKFLOW_RUNTIME",
    "KERNEL",
    "INTENT_MODE",
    "EMBEDDING_MODEL",
    "LLM_LOCAL_API_KEY",
    "SIMPLE_MODE_SYSTEM_PROMPT",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "HYBRID_CLOUD_PROVIDER",
    "HYBRID_LOCAL_MODEL",
    "HYBRID_CLOUD_MODEL",
    "SENSITIVE_DATA_LOCAL_ONLY",
    "ENABLE_MODEL_ROUTING",
    "FORCE_LOCAL_MODEL",
    "ENABLE_MULTI_SERVICE",
    "ENABLE_META_LEARNING",
    "LESSONS_TTL_DAYS",
    # Intent Embedding Router
    "ENABLE_INTENT_EMBEDDING_ROUTER",
    "INTENT_EMBED_MODEL_NAME",
    "INTENT_EMBED_MIN_SCORE",
    "INTENT_EMBED_MARGIN",
    "LAST_MODEL_OLLAMA",
    "LAST_MODEL_VLLM",
    "PREVIOUS_MODEL_OLLAMA",
    "PREVIOUS_MODEL_VLLM",
    "ACTIVE_LLM_SERVER",
    "LLM_CONFIG_HASH",
    "MODEL_GENERATION_OVERRIDES",
    # LLM Server Commands
    "VLLM_START_COMMAND",
    "VLLM_STOP_COMMAND",
    "VLLM_RESTART_COMMAND",
    "VLLM_ENDPOINT",
    "VLLM_MODEL_PATH",
    "VLLM_SERVED_MODEL_NAME",
    "VLLM_CHAT_TEMPLATE",
    "VLLM_GPU_MEMORY_UTILIZATION",
    "VLLM_MAX_BATCHED_TOKENS",
    "OLLAMA_START_COMMAND",
    "OLLAMA_STOP_COMMAND",
    "OLLAMA_RESTART_COMMAND",
    "SUMMARY_STRATEGY",
    "PROMPTS_DIR",
    "ENABLE_CONTEXT_COMPRESSION",
    "MAX_CONTEXT_TOKENS",
    "DOCKER_IMAGE_NAME",
    "ENABLE_SANDBOX",
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
    "GARDENER_COMPLEXITY_THRESHOLD",
    "MEMORY_CONSOLIDATION_INTERVAL_MINUTES",
    "HEALTH_CHECK_INTERVAL_MINUTES",
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
    # External integrations
    "ENABLE_HF_INTEGRATION",
    "HF_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_REPO_NAME",
    "DISCORD_WEBHOOK_URL",
    "SLACK_WEBHOOK_URL",
    "ENABLE_ISSUE_POLLING",
    "ISSUE_POLLING_INTERVAL_MINUTES",
    "TAVILY_API_KEY",
    # Calendar
    "ENABLE_GOOGLE_CALENDAR",
    "GOOGLE_CALENDAR_CREDENTIALS_PATH",
    "GOOGLE_CALENDAR_TOKEN_PATH",
    "VENOM_CALENDAR_ID",
    "VENOM_CALENDAR_NAME",
    # IoT Bridge
    "ENABLE_IOT_BRIDGE",
    "RIDER_PI_HOST",
    "RIDER_PI_PORT",
    "RIDER_PI_USERNAME",
    "RIDER_PI_PASSWORD",
    "RIDER_PI_KEY_FILE",
    "RIDER_PI_PROTOCOL",
    "IOT_REQUIRE_CONFIRMATION",
    # Academy (fine-tuning)
    "ENABLE_ACADEMY",
    "ACADEMY_TRAINING_DIR",
    "ACADEMY_MODELS_DIR",
    "ACADEMY_MIN_LESSONS",
    "ACADEMY_TRAINING_INTERVAL_HOURS",
    "ACADEMY_DEFAULT_BASE_MODEL",
    "ACADEMY_LORA_RANK",
    "ACADEMY_LEARNING_RATE",
    "ACADEMY_NUM_EPOCHS",
    "ACADEMY_BATCH_SIZE",
    "ACADEMY_MAX_SEQ_LENGTH",
    "ACADEMY_ENABLE_GPU",
    "ACADEMY_USE_LOCAL_RUNTIME",
    "ACADEMY_TRAINING_IMAGE",
    # Simulation
    "ENABLE_SIMULATION",
    "SIMULATION_CHAOS_ENABLED",
    "SIMULATION_MAX_STEPS",
    "SIMULATION_USER_MODEL",
    "SIMULATION_ANALYST_MODEL",
    "SIMULATION_DEFAULT_USERS",
    "SIMULATION_LOGS_DIR",
    # Launchpad / media
    "ENABLE_LAUNCHPAD",
    "DEPLOYMENT_SSH_KEY_PATH",
    "DEPLOYMENT_DEFAULT_USER",
    "DEPLOYMENT_TIMEOUT",
    "ASSETS_DIR",
    "ENABLE_IMAGE_GENERATION",
    "IMAGE_GENERATION_SERVICE",
    "DALLE_MODEL",
    "IMAGE_DEFAULT_SIZE",
    "IMAGE_STYLE",
    # Dreamer
    "ENABLE_DREAMING",
    "DREAMING_IDLE_THRESHOLD_MINUTES",
    "DREAMING_NIGHT_HOURS",
    "DREAMING_MAX_SCENARIOS",
    "DREAMING_CPU_THRESHOLD",
    "DREAMING_MEMORY_THRESHOLD",
    "DREAMING_SCENARIO_COMPLEXITY",
    "DREAMING_VALIDATION_STRICT",
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
    "HF_TOKEN",
    "GITHUB_TOKEN",
    "DISCORD_WEBHOOK_URL",
    "SLACK_WEBHOOK_URL",
    "TAVILY_API_KEY",
    "RIDER_PI_PASSWORD",
    "RIDER_PI_KEY_FILE",
}

# Mapowanie parametrów na usługi wymagające restartu
RESTART_REQUIREMENTS = {
    "AI_MODE": ["backend"],
    "INTENT_MODE": ["backend"],
    "KERNEL": ["backend"],
    "WORKFLOW_RUNTIME": ["backend"],
    "LLM_SERVICE_TYPE": ["backend"],
    "LLM_LOCAL_ENDPOINT": ["backend"],
    "URL_SCHEME_POLICY": ["backend"],
    "LLM_MODEL_NAME": ["backend"],
    "ACTIVE_PROVIDER": ["backend"],
    "EMBEDDING_MODEL": ["backend"],
    "SIMPLE_MODE_SYSTEM_PROMPT": ["backend"],
    "HYBRID_CLOUD_PROVIDER": ["backend"],
    "HYBRID_LOCAL_MODEL": ["backend"],
    "HYBRID_CLOUD_MODEL": ["backend"],
    "ENABLE_MODEL_ROUTING": ["backend"],
    "FORCE_LOCAL_MODEL": ["backend"],
    "VLLM_START_COMMAND": [],
    "VLLM_STOP_COMMAND": [],
    "VLLM_ENDPOINT": ["backend"],
    "VLLM_CHAT_TEMPLATE": ["backend"],
    "OLLAMA_START_COMMAND": [],
    "OLLAMA_STOP_COMMAND": [],
    "ENABLE_META_LEARNING": [],
    "LESSONS_TTL_DAYS": [],
    "LAST_MODEL_OLLAMA": [],
    "LAST_MODEL_VLLM": [],
    "PREVIOUS_MODEL_OLLAMA": [],
    "PREVIOUS_MODEL_VLLM": [],
    "ACTIVE_LLM_SERVER": [],
    "LLM_CONFIG_HASH": [],
    "MODEL_GENERATION_OVERRIDES": [],
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

    updates: Dict[str, Any] = Field(
        ..., description="Mapa klucz->wartość do aktualizacji"
    )

    @field_validator("updates", mode="before")
    def validate_updates(cls, v: Any) -> Dict[str, Any]:
        """Sprawdź whitelist i zakresy wartości dla konfiguracji."""
        if not isinstance(v, dict):
            raise ValueError("Pole 'updates' musi być mapą klucz->wartość")

        typed_updates: Dict[str, Any] = v
        cls._validate_whitelist(typed_updates)
        errors: List[str] = []
        cls._validate_port_params(typed_updates, errors)
        cls._validate_threshold_params(typed_updates, errors)
        cls._validate_boolean_params(typed_updates, errors)
        cls._validate_non_negative_int_params(typed_updates, errors)
        cls._validate_mode_params(typed_updates, errors)

        if errors:
            raise ValueError("; ".join(errors))

        return typed_updates

    @classmethod
    def _validate_whitelist(cls, updates: Dict[str, Any]) -> None:
        invalid_keys = set(updates.keys()) - CONFIG_WHITELIST
        if invalid_keys:
            raise ValueError(
                f"Znaleziono {len(invalid_keys)} nieprawidłowych kluczy konfiguracji"
            )

    @classmethod
    def _validate_port_params(cls, updates: Dict[str, Any], errors: List[str]) -> None:
        for param in ["REDIS_PORT", "NEXUS_PORT"]:
            if param not in updates:
                continue
            try:
                port = int(updates[param])
                if port < 1 or port > 65535:
                    errors.append(f"{param} musi być w zakresie 1-65535")
            except (ValueError, TypeError):
                errors.append(f"{param} musi być liczbą całkowitą")

    @classmethod
    def _validate_threshold_params(
        cls, updates: Dict[str, Any], errors: List[str]
    ) -> None:
        for param in [
            "SHADOW_CONFIDENCE_THRESHOLD",
            "GHOST_VISION_CONFIDENCE",
            "VAD_THRESHOLD",
        ]:
            if param not in updates:
                continue
            try:
                threshold = float(updates[param])
                if threshold < 0.0 or threshold > 1.0:
                    errors.append(f"{param} musi być w zakresie 0.0-1.0")
            except (ValueError, TypeError):
                errors.append(f"{param} musi być liczbą zmiennoprzecinkową")

    @classmethod
    def _validate_boolean_params(
        cls, updates: Dict[str, Any], errors: List[str]
    ) -> None:
        bool_params = [
            "ENABLE_HIVE",
            "ENABLE_NEXUS",
            "ENABLE_GHOST_AGENT",
            "ENABLE_DESKTOP_SENSOR",
            "ENABLE_PROACTIVE_MODE",
            "ENABLE_AUDIO_INTERFACE",
            "ENABLE_AUTO_DOCUMENTATION",
            "ENABLE_AUTO_GARDENING",
            "ENABLE_MEMORY_CONSOLIDATION",
            "ENABLE_HEALTH_CHECKS",
            "VENOM_PAUSE_BACKGROUND_TASKS",
            "SENSITIVE_DATA_LOCAL_ONLY",
            "ENABLE_MODEL_ROUTING",
            "FORCE_LOCAL_MODEL",
            "ENABLE_MULTI_SERVICE",
            "GHOST_VERIFICATION_ENABLED",
        ]
        for param in bool_params:
            if param not in updates:
                continue
            val_str = str(updates[param]).lower()
            if val_str not in ["true", "false", "0", "1", "yes", "no"]:
                errors.append(
                    f"{param} musi być wartością boolean (true/false/0/1/yes/no)"
                )

    @classmethod
    def _validate_non_negative_int_params(
        cls, updates: Dict[str, Any], errors: List[str]
    ) -> None:
        non_negative_int_params = [
            "REDIS_DB",
            "HIVE_TASK_TIMEOUT",
            "HIVE_MAX_RETRIES",
            "NEXUS_HEARTBEAT_TIMEOUT",
            "WATCHER_DEBOUNCE_SECONDS",
            "IDLE_THRESHOLD_MINUTES",
            "GHOST_MAX_STEPS",
            "GHOST_STEP_DELAY",
            "GHOST_SAFETY_DELAY",
            "SHADOW_CLIPBOARD_MAX_LENGTH",
            "SHADOW_CHECK_INTERVAL",
            "SILENCE_DURATION",
        ]
        for param in non_negative_int_params:
            if param not in updates:
                continue
            try:
                value = int(updates[param])
                if value < 0:
                    errors.append(f"{param} musi być liczbą nieujemną")
            except (ValueError, TypeError):
                errors.append(f"{param} musi być liczbą całkowitą")

    @classmethod
    def _validate_mode_params(cls, updates: Dict[str, Any], errors: List[str]) -> None:
        if "AI_MODE" in updates:
            valid_modes = ["LOCAL", "CLOUD", "HYBRID"]
            if str(updates["AI_MODE"]).upper() not in valid_modes:
                errors.append(f"AI_MODE musi być jednym z: {', '.join(valid_modes)}")

        if "LLM_SERVICE_TYPE" in updates:
            valid_types = ["local", "openai", "google", "ollama", "vllm"]
            if str(updates["LLM_SERVICE_TYPE"]).lower() not in valid_types:
                errors.append(
                    f"LLM_SERVICE_TYPE musi być jednym z: {', '.join(valid_types)}"
                )

        if "URL_SCHEME_POLICY" in updates:
            valid_policies = ["auto", "force_http", "force_https"]
            if str(updates["URL_SCHEME_POLICY"]).lower() not in valid_policies:
                errors.append(
                    "URL_SCHEME_POLICY musi być jednym z: " + ", ".join(valid_policies)
                )


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
        config: Dict[str, Any] = {}

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

    def get_effective_config_with_sources(
        self, mask_secrets: bool = True
    ) -> tuple[Dict[str, Any], Dict[str, str]]:
        """
        Pobiera efektywną konfigurację (env fallbackuje do domyślnych wartości Settings)
        oraz źródło każdej wartości.

        Returns:
            tuple:
                - config: mapa klucz->wartość (sekrety opcjonalnie maskowane)
                - sources: mapa klucz->"env" | "default"
        """
        config: Dict[str, Any] = {}
        sources: Dict[str, str] = {}
        env_values = self._read_env_file()

        for key in CONFIG_WHITELIST:
            raw_value = env_values.get(key)
            if raw_value is not None:
                value = raw_value
                sources[key] = "env"
            else:
                value = self._default_value_as_string(key)
                sources[key] = "default"

            if mask_secrets and key in SECRET_PARAMS and value:
                config[key] = self._mask_secret(value)
            else:
                config[key] = value

        return config, sources

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
        changed_keys: List[str] = []
        for key, value in updates.items():
            old_value = env_values.get(key, "")
            if str(value) != str(old_value):
                env_values[key] = str(value)
                changed_keys.append(key)

        # [AUTO-SYNC LOGIC] Automatyczna aktualizacja endpointu przy zmianie serwera
        if "ACTIVE_LLM_SERVER" in updates and "LLM_LOCAL_ENDPOINT" not in updates:
            new_server = str(updates["ACTIVE_LLM_SERVER"]).lower()
            if new_server == "vllm":
                # Pobierz endpoint vLLM z updates (jeśli zmieniany) lub z obecnych wartości
                vllm_endpoint = updates.get("VLLM_ENDPOINT")
                if not vllm_endpoint:
                    vllm_endpoint = env_values.get(
                        "VLLM_ENDPOINT", build_http_url("localhost", 8001, "/v1")
                    )

                env_values["LLM_LOCAL_ENDPOINT"] = str(vllm_endpoint)
                changed_keys.append("LLM_LOCAL_ENDPOINT")
                logger.info(
                    f"Auto-Sync: Ustawiono LLM_LOCAL_ENDPOINT na {vllm_endpoint} (vLLM)"
                )

            elif new_server == "ollama":
                # Domyślny endpoint Ollama
                ollama_endpoint = build_http_url("localhost", 11434, "/v1")
                env_values["LLM_LOCAL_ENDPOINT"] = ollama_endpoint
                changed_keys.append("LLM_LOCAL_ENDPOINT")
                logger.info(
                    f"Auto-Sync: Ustawiono LLM_LOCAL_ENDPOINT na {ollama_endpoint} (Ollama)"
                )

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

        message = (
            f"Zaktualizowano {len(changed_keys)} parametrów. Backup: {backup_path.name}"
        )
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
        env_values: Dict[str, str] = {}

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

        except Exception:
            logger.exception("Błąd wczytywania .env")

        return env_values

    @staticmethod
    def _default_value_as_string(key: str) -> str:
        """Konwertuje domyślną wartość z Settings na string kompatybilny z .env."""
        if not hasattr(SETTINGS, key):
            return ""

        value = getattr(SETTINGS, key)
        if value is None:
            return ""
        if isinstance(value, SecretStr):
            return value.get_secret_value()
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, (int, float)):
            return str(value)
        return str(value)

    def _write_env_file(self, env_values: Dict[str, str]) -> None:
        """Zapisuje słownik do .env."""
        # Wczytaj oryginał aby zachować komentarze i strukturę
        original_lines: List[str] = []
        if self.env_file.exists():
            with open(self.env_file, "r", encoding="utf-8") as f:
                original_lines = f.readlines()

        # Zbuduj nowy plik
        new_lines: List[str] = []
        processed_keys: Set[str] = set()

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

        except Exception:
            logger.exception("Błąd tworzenia backupu .env")
            return None

    def _cleanup_old_backups(self, max_keep: int = 50) -> None:
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
        restart_services: Set[str] = set()

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

            result: List[Dict[str, Any]] = []
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
        if not re.match(r"^\.env-\d{8}-\d{6}$", backup_filename):
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
