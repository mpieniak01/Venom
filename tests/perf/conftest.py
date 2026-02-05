import pytest


@pytest.fixture(scope="session", autouse=True)
def configure_local_settings():
    """
    Nadpisuje autouse fixture z tests/conftest.py dla testów wydajnościowych.

    W testach perf/real-data nie zmieniamy SETTINGS ani ścieżek stanu,
    aby weryfikować faktyczne pliki i zachowanie backendu.
    """

    yield {}
