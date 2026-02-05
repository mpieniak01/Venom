import os

import httpx
import pytest

from .chat_pipeline import _resolve_api_base


def _backend_available() -> bool:
    base = _resolve_api_base()
    healthz = f"{base}/healthz"
    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(healthz)
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def pytest_collection_modifyitems(config, items):
    if _backend_available():
        return
    skip_perf = pytest.mark.skip(
        reason="Backend API niedostępny – pomijam testy perf.",
    )
    for item in items:
        item.add_marker(skip_perf)


@pytest.fixture(scope="session", autouse=True)
def configure_perf_defaults():
    """
    Ustawia bezpieczne domyślne wartości dla testów perf,
    aby nie uruchamiać ciężkich ścieżek bez potrzeby.
    """
    os.environ.setdefault("VENOM_FORCE_INTENT", "HELP_REQUEST")
    os.environ.setdefault("VENOM_STREAM_TIMEOUT", "15")
    os.environ.setdefault("VENOM_PIPELINE_CONCURRENCY", "1")
    os.environ.setdefault("VENOM_PIPELINE_BUDGET", "8.0")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    yield


@pytest.fixture(scope="session", autouse=True)
def configure_local_settings():
    """
    Nadpisuje autouse fixture z tests/conftest.py dla testów wydajnościowych.

    W testach perf/real-data nie zmieniamy SETTINGS ani ścieżek stanu,
    aby weryfikować faktyczne pliki i zachowanie backendu.
    """

    yield {}
