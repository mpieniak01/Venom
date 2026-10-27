import os

import pytest


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
    return


@pytest.fixture(scope="session", autouse=True)
def configure_local_settings():
    """
    Nadpisuje autouse fixture z tests/conftest.py dla testów wydajnościowych.

    W testach perf/real-data nie zmieniamy SETTINGS ani ścieżek stanu,
    aby weryfikować faktyczne pliki i zachowanie backendu.
    """

    return {}
