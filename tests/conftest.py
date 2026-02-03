import shutil
import subprocess
import warnings
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=".*PydanticDeprecatedSince211.*",
    module="pydantic._internal._generate_schema",
)


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


# --- Fake Vector Store Implementation ---


class FakeVectorStore:
    def __init__(self, *args, **kwargs):
        # Akceptujemy argumenty konstruktora, żeby pasowało do patcha klasy
        self.entries = []

    def upsert(
        self,
        text,
        metadata=None,
        collection_name=None,
        chunk_text=True,
        id_override=None,
    ):
        import uuid

        metadata = metadata or {}
        entry = {
            "id": id_override or str(uuid.uuid4()),
            "text": text,
            "metadata": metadata,
            "collection": collection_name or "default",
        }
        self.entries.append(entry)
        return {"message": "success", "chunks_count": 1}

    def list_entries(
        self, limit=200, metadata_filters=None, collection_name=None, entry_id=None
    ):
        results = []
        for entry in self.entries:
            if entry_id and entry["id"] != entry_id:
                continue
            if collection_name and entry["collection"] != collection_name:
                continue
            if metadata_filters:
                match = True
                entry_meta = entry.get("metadata", {})
                for k, v in metadata_filters.items():
                    if entry_meta.get(k) != v:
                        match = False
                        break
                if not match:
                    continue
            results.append(entry)
        return results

    def delete_by_metadata(self, filters, collection_name=None):
        if not filters:
            raise ValueError("filters nie może być puste")
        initial_count = len(self.entries)
        new_entries = []
        for entry in self.entries:
            meta = entry.get("metadata", {})
            should_delete = True
            for k, v in filters.items():
                if meta.get(k) != v:
                    should_delete = False
                    break
            if not should_delete:
                new_entries.append(entry)
        deleted = initial_count - len(new_entries)
        self.entries = new_entries
        return deleted

    def delete_session(self, session_id, collection_name=None):
        return self.delete_by_metadata({"session_id": session_id})

    def delete_entry(self, entry_id, collection_name=None):
        initial_count = len(self.entries)
        self.entries = [e for e in self.entries if e["id"] != entry_id]
        return initial_count - len(self.entries)

    def search(self, query, limit=3, collection_name=None):
        # Dummy search: return all matching collection
        results = []
        for entry in self.entries:
            if collection_name and entry["collection"] != collection_name:
                continue
            # Poor man's full text search for testing
            if query.lower() in entry["text"].lower():
                results.append(
                    {"text": entry["text"], "metadata": entry["metadata"], "score": 1.0}
                )
        return results[:limit]

    def wipe_collection(self, collection_name=None):
        # remove all from this collection
        # if collection_name is None, assume default? Or all?
        # VectorStore wipe_collection uses self.collection_name.
        # But we mock it. Let's assume wipe means delete all for test simplicity if collection matched.
        # In real tests, most usage is clear_global -> wipe default.
        initial_count = len(self.entries)
        if collection_name:
            self.entries = [
                e for e in self.entries if e["collection"] != collection_name
            ]
        else:
            self.entries = []
        return initial_count - len(self.entries)

    def update_metadata(self, entry_id, metadata_patch, collection_name=None):
        for entry in self.entries:
            if entry["id"] == entry_id:
                entry["metadata"].update(metadata_patch)
                return True
        return False


@pytest.fixture
def fake_vector_store():
    return FakeVectorStore()


@pytest.fixture
def mock_lifespan_deps():
    """
    Patchuje klasy dependency w venom_core.main, aby lifespan nie używał prawdziwych klas.
    Zwraca instancje mocków/faków, które można skonfigurować w testach.
    """
    fake_vector_store_instance = FakeVectorStore()

    # Patch VectorStore class to return our fake instance
    p1 = patch("venom_core.main.VectorStore", return_value=fake_vector_store_instance)

    # Patch LessonsStore to return a MagicMock
    mock_lessons = MagicMock()
    mock_lessons.lessons = {}
    p2 = patch("venom_core.main.LessonsStore", return_value=mock_lessons)

    # Patch Orchestrator to return a MagicMock
    mock_orch = MagicMock()
    p3 = patch("venom_core.main.Orchestrator", return_value=mock_orch)

    # Warto też spatchować globalną zmienną 'orchestrator' w venom_core.main,
    # jeśli jest już zainicjalizowana, żeby była naszym mockiem na pewno.
    p4 = patch("venom_core.main.orchestrator", mock_orch)

    # Patch CodeGraphStore (GraphStore)
    mock_graph = MagicMock()
    p5 = patch("venom_core.main.CodeGraphStore", return_value=mock_graph)

    with p1, p2, p3, p4, p5:
        yield {
            "vector_store": fake_vector_store_instance,
            "lessons_store": mock_lessons,
            "orchestrator": mock_orch,
            "graph_store": mock_graph,
        }
