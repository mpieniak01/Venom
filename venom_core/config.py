from pydantic import ConfigDict
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


SETTINGS = Settings()
