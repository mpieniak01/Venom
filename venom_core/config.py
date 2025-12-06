
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Venom Meta-Intelligence"
    ENV: str = "development"

    WORKSPACE_ROOT: str = "./workspace"
    MEMORY_ROOT: str = "./data/memory"

    # Modele ONNX
    MODEL_PHI3_PATH: str = "models/phi3-mini-4k-instruct-onnx"

    class Config:
        env_file = ".env"


SETTINGS = Settings()
