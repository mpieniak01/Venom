from pathlib import Path

# --- STRUKTURA VENOMA v2 ---
# Definicja katalogów i plików
STRUCTURE = {
    ".": [".env", "requirements.txt", "README.md"],
    "docs": ["VENOM_DIAGRAM.md", "VENOM_MASTER_VISION_V2.md"],
    "data/memory": ["lessons_learned.json"],
    "web/templates": ["base.html", "index.html"],
    "web/static/css": ["app.css"],
    "web/static/js": ["app.js"],
    "tests": ["test_healthz.py", "__init__.py"],
    "logs": [],  # katalog na logi Venoma
    "workspace": [],  # root na workspace (zgodnie z config.WORKSPACE_ROOT)
    "scripts": [],  # tu trzymamy genesis, migracje, narzędzia CLI
    "venom_core": ["__init__.py", "main.py", "config.py"],
    "venom_core/core": [
        "__init__.py",
        "orchestrator.py",
        "intent_manager.py",
        "policy_engine.py",
        "state_manager.py",
    ],
    "venom_core/agents": [
        "__init__.py",
        "architect.py",
        "librarian.py",
        "coder.py",
        "critic.py",
        "writer.py",
    ],
    "venom_core/execution": ["__init__.py", "kernel_builder.py"],
    "venom_core/execution/skills": [
        "__init__.py",
        "file_skill.py",
        "shell_skill.py",
        "git_skill.py",
    ],
    "venom_core/perception": ["__init__.py", "eyes.py", "antenna.py"],
    "venom_core/memory": [
        "__init__.py",
        "graph_store.py",
        "vector_store.py",
        "lessons_store.py",
    ],
    "venom_core/infrastructure": [
        "__init__.py",
        "onnx_runtime.py",
        "docker_habitat.py",
        "hardware_pi.py",
    ],
    "venom_core/utils": ["__init__.py", "logger.py", "helpers.py"],
}

# --- TREŚCI STARTOWE (BOILERPLATE) ---
CONTENTS = {
    "venom_core/main.py": """
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from venom_core.config import SETTINGS
from venom_core.utils.logger import logger

# Inicjalizacja Aplikacji (Organizmu)
app = FastAPI(title="Venom", version="2.0.0")

# Montowanie zasobów statycznych
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")


@app.on_event("startup")
async def startup_event():
    logger.info("🧬 VENOM ORGANISM IS AWAKENING...")
    # TODO: inicjalizacja Orchestratora, pamięci, połączeń z bazą


@app.get("/healthz")
async def health_check():
    return {"status": "alive", "pulse": "steady", "system": "venom_v2"}


@app.get("/")
async def dashboard(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "name": "Venom"},
    )
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


def create_structure():
    print("🧬 Rozpoczynam sekwencję GENESIS...")
    base_path = Path.cwd()

    for folder, files in STRUCTURE.items():
        dir_path = base_path / folder
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 Katalog OK: {folder}")

        for file in files:
            file_path = dir_path / file
            if not file_path.exists():
                key = f"{folder}/{file}" if folder != "." else file
                content = CONTENTS.get(key, "")
                # Domyślna treść dla pustych plików .py (żeby były modułami)
                if not content and file.endswith(".py"):
                    module_name = file.replace(".py", "")
                    content = f'"""Moduł: {module_name}"""\n'

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  └── 📄 Utworzono plik: {folder}/{file}")
            else:
                print(f"  └── ⚠️ Pominięto (istnieje): {folder}/{file}")

    print("\n✅ GENESIS ZAKOŃCZONE. Organizm Venom posiada strukturę.")
    print("👉 Następny krok: uzupełnij .env i uruchom:")
    print("   uvicorn venom_core.main:app --reload")


if __name__ == "__main__":
    create_structure()
