from pathlib import Path

INIT_PY_FILE = "__init__.py"

# --- STRUKTURA VENOMA v2 ---
# Definicja katalogów i plików
STRUCTURE = {
    ".": [".env", "requirements.txt", "README.md"],
    "docs": ["VENOM_DIAGRAM.md", "VENOM_MASTER_VISION_V2.md"],
    "data/memory": ["lessons_learned.json"],
    "tests": ["test_healthz.py", INIT_PY_FILE],
    "logs": [],  # katalog na logi Venoma
    "workspace": [],  # root na workspace (zgodnie z config.WORKSPACE_ROOT)
    "scripts": [],  # tu trzymamy genesis, migracje, narzędzia CLI
    "venom_core": [INIT_PY_FILE, "main.py", "config.py"],
    "venom_core/core": [
        INIT_PY_FILE,
        "orchestrator.py",
        "intent_manager.py",
        "policy_engine.py",
        "state_manager.py",
    ],
    "venom_core/agents": [
        INIT_PY_FILE,
        "architect.py",
        "librarian.py",
        "coder.py",
        "critic.py",
        "writer.py",
    ],
    "venom_core/execution": [INIT_PY_FILE, "kernel_builder.py"],
    "venom_core/execution/skills": [
        INIT_PY_FILE,
        "file_skill.py",
        "shell_skill.py",
        "git_skill.py",
    ],
    "venom_core/perception": [INIT_PY_FILE, "eyes.py", "antenna.py"],
    "venom_core/memory": [
        INIT_PY_FILE,
        "graph_store.py",
        "vector_store.py",
        "lessons_store.py",
    ],
    "venom_core/infrastructure": [
        INIT_PY_FILE,
        "onnx_runtime.py",
        "docker_habitat.py",
        "hardware_pi.py",
    ],
    "venom_core/utils": [INIT_PY_FILE, "logger.py", "helpers.py"],
}

# --- TREŚCI STARTOWE (BOILERPLATE) ---
CONTENTS = {
    "venom_core/main.py": """
from fastapi import FastAPI, Request

from venom_core.config import SETTINGS
from venom_core.utils.logger import logger

# Inicjalizacja Aplikacji (Organizmu)
app = FastAPI(title="Venom", version="2.0.0")


@app.on_event("startup")
async def startup_event():
    logger.info("🧬 VENOM ORGANISM IS AWAKENING...")
    # TODO: inicjalizacja Orchestratora, pamięci, połączeń z bazą


@app.get("/healthz")
async def health_check():
    return {"status": "alive", "pulse": "steady", "system": "venom_v2"}


@app.get("/")
async def root(request: Request):
    return {"name": "Venom", "status": "ok"}
""",
    "venom_core/config.py": """
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
""",
    "venom_core/utils/logger.py": """
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
""",
}


def _resolve_file_content(folder: str, file_name: str) -> str:
    key = f"{folder}/{file_name}" if folder != "." else file_name
    content = CONTENTS.get(key, "")
    if not content and file_name.endswith(".py"):
        module_name = file_name.replace(".py", "")
        return f'"""Moduł: {module_name}"""\n'
    return content


def _create_file_if_missing(base_dir: Path, folder: str, file_name: str):
    file_path = base_dir / folder / file_name
    if file_path.exists():
        print(f"  └── ⚠️ Pominięto (istnieje): {folder}/{file_name}")
        return

    content = _resolve_file_content(folder, file_name)
    with open(file_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(content)
    print(f"  └── 📄 Utworzono plik: {folder}/{file_name}")


def create_structure():
    print("🧬 Rozpoczynam sekwencję GENESIS...")
    base_path = Path.cwd()

    for folder, files in STRUCTURE.items():
        dir_path = base_path / folder
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 Katalog OK: {folder}")

        for file in files:
            _create_file_if_missing(base_path, folder, file)

    print("\n✅ GENESIS ZAKOŃCZONE. Organizm Venom posiada strukturę.")
    print("👉 Następny krok: uzupełnij .env i uruchom:")
    print("   uvicorn venom_core.main:app --reload")


if __name__ == "__main__":
    create_structure()
