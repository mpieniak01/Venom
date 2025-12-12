import shutil
import subprocess
from typing import Any, Dict

import pytest


def _has_docker() -> bool:
    return shutil.which("docker") is not None


def _has_docker_compose() -> bool:
    if shutil.which("docker-compose"):
        return True
    if not _has_docker():
        return False
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=True,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


DOCKER_AVAILABLE = _has_docker()
DOCKER_COMPOSE_AVAILABLE = _has_docker_compose()


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Uruchom testy oznaczone markerem integration",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "requires_docker: test wymaga dostępnego Docker daemon"
    )
    config.addinivalue_line(
        "markers",
        "requires_docker_compose: test wymaga docker compose (docker-compose lub docker compose)",
    )
    config.addinivalue_line(
        "markers",
        "integration: test integracyjny wymagający dodatkowych zależności (uruchamiany tylko z --run-integration)",
    )


def pytest_collection_modifyitems(config, items):
    run_integration = config.getoption("--run-integration")
    skip_integration = pytest.mark.skip(
        reason="pomijam testy integracyjne (użyj --run-integration aby uruchomić)"
    )
    skip_docker = pytest.mark.skip(reason="pomijam - Docker nie jest dostępny")
    skip_compose = pytest.mark.skip(reason="pomijam - Docker Compose nie jest dostępny")

    for item in items:
        if "requires_docker_compose" in item.keywords and not DOCKER_COMPOSE_AVAILABLE:
            item.add_marker(skip_compose)
            continue
        if "requires_docker" in item.keywords and not DOCKER_AVAILABLE:
            item.add_marker(skip_docker)
            continue
        if "integration" in item.keywords and not run_integration:
            item.add_marker(skip_integration)


@pytest.fixture(scope="session", autouse=True)
def configure_local_settings(tmp_path_factory) -> Dict[str, Any]:
    """
    Utrzymuje spójne środowisko testowe poprzez wymuszenie trybu lokalnego
    i izolację pliku stanu, aby testy nie odczytywały przypadkowego stanu.
    """

    from venom_core.config import SETTINGS

    overrides = {
        "AI_MODE": "LOCAL",
        "ENABLE_MODEL_ROUTING": False,
        "FORCE_LOCAL_MODEL": True,
        # Wyłącz zadania w tle, które w testach nie są potrzebne
        "VENOM_PAUSE_BACKGROUND_TASKS": True,
        "ENABLE_AUTO_DOCUMENTATION": False,
        "ENABLE_AUTO_GARDENING": False,
        "ENABLE_MEMORY_CONSOLIDATION": False,
        "ENABLE_HEALTH_CHECKS": False,
        "INTENT_CLASSIFIER_TIMEOUT_SECONDS": 0.2,
    }

    tmp_state_dir = tmp_path_factory.mktemp("state")
    overrides["STATE_FILE_PATH"] = str(tmp_state_dir / "state_dump.json")

    original_values = {attr: getattr(SETTINGS, attr) for attr in overrides}

    for attr, value in overrides.items():
        setattr(SETTINGS, attr, value)

    yield original_values

    for attr, value in original_values.items():
        setattr(SETTINGS, attr, value)
