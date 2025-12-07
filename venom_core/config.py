from pydantic import ConfigDict, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    APP_NAME: str = "Venom Meta-Intelligence"
    ENV: str = "development"

    WORKSPACE_ROOT: str = "./workspace"
    MEMORY_ROOT: str = "./data/memory"
    STATE_FILE_PATH: str = "./data/memory/state_dump.json"

    # Modele ONNX
    MODEL_PHI3_PATH: str = "models/phi3-mini-4k-instruct-onnx"

    # Konfiguracja LLM (Local-First Brain)
    LLM_SERVICE_TYPE: str = "local"  # Opcje: "local", "openai", "azure"
    LLM_LOCAL_ENDPOINT: str = "http://localhost:11434/v1"  # Ollama/vLLM
    LLM_MODEL_NAME: str = "phi3:latest"
    LLM_LOCAL_API_KEY: str = "venom-local"  # Dummy key dla lokalnych serwerów
    OPENAI_API_KEY: str = ""  # Opcjonalne, wymagane tylko dla typu "openai"

    # Konfiguracja Docker Sandbox
    DOCKER_IMAGE_NAME: str = "python:3.11-slim"
    ENABLE_SANDBOX: bool = True

    # Konfiguracja Background Tasks (THE_OVERMIND)
    VENOM_PAUSE_BACKGROUND_TASKS: bool = False  # Globalny wyłącznik dla zadań w tle
    ENABLE_AUTO_DOCUMENTATION: bool = True  # Automatyczna aktualizacja dokumentacji
    ENABLE_AUTO_GARDENING: bool = True  # Automatyczna refaktoryzacja w trybie Idle
    ENABLE_MEMORY_CONSOLIDATION: bool = False  # Konsolidacja pamięci (placeholder)
    ENABLE_HEALTH_CHECKS: bool = True  # Sprawdzanie zdrowia systemu
    WATCHER_DEBOUNCE_SECONDS: int = (
        5  # Czas debounce dla watchdog (unikanie wielokrotnych triggerów)
    )
    IDLE_THRESHOLD_MINUTES: int = (
        15  # Czas bezczynności przed uruchomieniem auto-gardening
    )
    GARDENER_COMPLEXITY_THRESHOLD: int = 10  # Próg złożoności dla auto-refaktoryzacji
    MEMORY_CONSOLIDATION_INTERVAL_MINUTES: int = 60  # Interwał konsolidacji pamięci
    HEALTH_CHECK_INTERVAL_MINUTES: int = 5  # Interwał sprawdzania zdrowia systemu

    # Konfiguracja External Integrations (THE_TEAMMATE)
    # UWAGA: Sekrety używają SecretStr aby zapobiec przypadkowemu logowaniu
    GITHUB_TOKEN: SecretStr = SecretStr("")  # Personal Access Token do GitHub API
    GITHUB_REPO_NAME: str = ""  # Nazwa repozytorium np. "mpieniak01/Venom"
    DISCORD_WEBHOOK_URL: SecretStr = SecretStr(
        ""
    )  # Webhook URL dla powiadomień Discord
    SLACK_WEBHOOK_URL: SecretStr = SecretStr("")  # Webhook URL dla powiadomień Slack
    ENABLE_ISSUE_POLLING: bool = False  # Włącz automatyczne sprawdzanie Issues
    ISSUE_POLLING_INTERVAL_MINUTES: int = 5  # Interwał sprawdzania nowych Issues

    # Konfiguracja Audio Interface (THE_AVATAR)
    ENABLE_AUDIO_INTERFACE: bool = False  # Włącz interfejs głosowy (STT/TTS)
    WHISPER_MODEL_SIZE: str = "base"  # Rozmiar modelu Whisper ('tiny', 'base', 'small', 'medium', 'large')
    TTS_MODEL_PATH: str = ""  # Ścieżka do modelu Piper TTS (ONNX), puste = mock mode
    AUDIO_DEVICE: str = "cpu"  # Urządzenie dla modeli audio ('cpu', 'cuda')
    VAD_THRESHOLD: float = 0.5  # Próg Voice Activity Detection (0.0-1.0)
    SILENCE_DURATION: float = 1.5  # Czas ciszy (sekundy) oznaczający koniec wypowiedzi

    # Konfiguracja IoT Bridge (Rider-Pi)
    ENABLE_IOT_BRIDGE: bool = False  # Włącz komunikację z Raspberry Pi
    RIDER_PI_HOST: str = "192.168.1.100"  # Adres IP Raspberry Pi
    RIDER_PI_PORT: int = 22  # Port SSH (22) lub HTTP (8888 dla pigpio)
    RIDER_PI_USERNAME: str = "pi"  # Nazwa użytkownika SSH
    RIDER_PI_PASSWORD: SecretStr = SecretStr("")  # Hasło SSH (opcjonalne jeśli używamy klucza)
    RIDER_PI_KEY_FILE: str = ""  # Ścieżka do klucza SSH (opcjonalne)
    RIDER_PI_PROTOCOL: str = "ssh"  # Protokół komunikacji ('ssh' lub 'http')
    IOT_REQUIRE_CONFIRMATION: bool = True  # Wymagaj potwierdzenia dla komend sprzętowych


SETTINGS = Settings()
