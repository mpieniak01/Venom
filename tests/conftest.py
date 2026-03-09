import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# --- Test Artifact Strategy: CLEAN vs PRESERVE ---
# Polityka w docs/TEST_ARTIFACTS_POLICY.md i docs/PL/TEST_ARTIFACTS_POLICY.md

_ARTIFACT_MODE = os.environ.get("VENOM_TEST_ARTIFACT_MODE", "clean").lower()
_ARTIFACT_DIR_OVERRIDE = os.environ.get("VENOM_TEST_ARTIFACT_DIR")

if _ARTIFACT_DIR_OVERRIDE:
    _PYTEST_ARTIFACTS_ROOT = Path(_ARTIFACT_DIR_OVERRIDE)
else:
    session_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    _PYTEST_ARTIFACTS_ROOT = (
        Path("test-results") / "tmp" / f"session-{session_timestamp}"
    )

# Ustaw izolowane ścieżki artefaktów zanim testy zaimportują moduły runtime.
os.environ.setdefault(
    "CHRONOS_TIMELINES_DIR", str(_PYTEST_ARTIFACTS_ROOT / "data" / "timelines")
)
os.environ.setdefault(
    "DREAMING_OUTPUT_DIR", str(_PYTEST_ARTIFACTS_ROOT / "data" / "synthetic_training")
)

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=".*PydanticDeprecatedSince211.*",
    module="pydantic._internal._generate_schema",
)
# Noise from intentionally simulated timeout/error branches with AsyncMock in tests.
warnings.filterwarnings(
    "ignore",
    category=RuntimeWarning,
    message=r"coroutine 'AsyncMockMixin\._execute_mock_call' was never awaited",
)

try:
    from requests.exceptions import RequestsDependencyWarning

    warnings.filterwarnings("ignore", category=RequestsDependencyWarning)
except Exception:
    # requests może nie być dostępny w wybranych profilach testowych
    pass


def _cleanup_magicmock_dirs(root: Path) -> None:
    """
    Usuń artefakty katalogowe powstające przy błędnie zmockowanych ścieżkach,
    np. "<MagicMock name='SETTINGS.WORKSPACE_ROOT' ...>".
    """

    for path in root.iterdir():
        if not path.is_dir():
            continue
        if "MagicMock" not in path.name:
            continue
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def cleanup_magicmock_artifacts() -> None:
    _cleanup_magicmock_dirs(Path.cwd())
    yield
    _cleanup_magicmock_dirs(Path.cwd())


def _has_docker() -> bool:
    if importlib.util.find_spec("docker") is None:
        return False
    try:
        docker_mod = importlib.import_module("docker")
        # W repo istnieje katalog `docker/`, który może zostać zaimportowany jako
        # namespace package i dać fałszywie pozytywny wynik. Wymagamy API SDK.
        if not callable(getattr(docker_mod, "from_env", None)):
            return False
        importlib.import_module("docker.errors")
    except Exception:
        return False
    if shutil.which("docker") is None:
        return False
    try:
        # Sama obecność binarki nie wystarcza: testy wymagają działającego daemonu.
        result = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _has_docker_compose() -> bool:
    # StackManager używa wyłącznie składni `docker compose` (plugin CLI),
    # więc samodzielna binarka `docker-compose` nie jest wystarczająca.
    if not _has_docker():
        return False
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


DOCKER_AVAILABLE = _has_docker()
DOCKER_COMPOSE_AVAILABLE = _has_docker_compose()


def _stack_state() -> tuple[str, str]:
    """
    Zwraca (state, reason_code):
    - ready
    - stack_not_started
    - stack_degraded
    """
    # 197B policy: tests oznaczone `requires_stack` muszą rozróżniać
    # brak stacka od degradacji runtime i mapować oba przypadki na skip.

    base_url = os.environ.get("VENOM_TEST_STACK_BASE", "http://127.0.0.1:8000").rstrip(
        "/"
    )
    health_url = f"{base_url}/healthz"
    active_url = f"{base_url}/api/v1/system/llm-servers/active"

    try:
        with urllib.request.urlopen(health_url, timeout=1.5) as response:
            if response.status >= 500:
                return ("stack_not_started", "stack_not_started")
    except (urllib.error.URLError, TimeoutError, OSError):
        return ("stack_not_started", "stack_not_started")

    try:
        with urllib.request.urlopen(active_url, timeout=1.5) as response:
            if response.status >= 500:
                return ("stack_degraded", "stack_degraded")
            payload = json.loads(response.read().decode("utf-8") or "{}")
            active_model = str(payload.get("active_model") or "").strip()
            if not active_model:
                return ("stack_degraded", "runtime_model_unavailable")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return ("stack_degraded", "stack_degraded")

    return ("ready", "ready")


def _resolve_skip_marker(item, *, run_integration: bool):
    if "requires_docker_compose" in item.keywords and not DOCKER_COMPOSE_AVAILABLE:
        return pytest.mark.skip(reason="pomijam - Docker Compose nie jest dostępny")
    if "requires_docker" in item.keywords and not DOCKER_AVAILABLE:
        return pytest.mark.skip(reason="pomijam - Docker daemon nie jest dostępny")
    if "integration" in item.keywords and not run_integration:
        return pytest.mark.skip(
            reason="pomijam testy integracyjne (użyj --run-integration aby uruchomić)"
        )
    if "requires_stack" in item.keywords:
        # Kontrakt: dla testów zależnych od stacka brak precondition => skip (nie fail).
        stack_state, reason_code = _stack_state()
        if stack_state != "ready":
            return pytest.mark.skip(reason=f"pomijam - stack niegotowy ({reason_code})")
    return None


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
        "requires_docker_compose: test wymaga działającego `docker compose` (Docker CLI plugin)",
    )
    config.addinivalue_line(
        "markers",
        "integration: test integracyjny wymagający dodatkowych zależności (uruchamiany tylko z --run-integration)",
    )
    config.addinivalue_line(
        "markers",
        "requires_stack: test wymaga uruchomionego stacka i gotowego modelu czatu (w przeciwnym razie skip)",
    )


def pytest_collection_modifyitems(config, items):
    run_integration = config.getoption("--run-integration")

    for item in items:
        marker = _resolve_skip_marker(item, run_integration=run_integration)
        if marker:
            item.add_marker(marker)


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
    tmp_workspace_dir = tmp_path_factory.mktemp("workspace")
    tmp_academy_training_dir = tmp_path_factory.mktemp("academy-training")
    tmp_academy_models_dir = tmp_path_factory.mktemp("academy-models")
    tmp_academy_user_data_dir = tmp_path_factory.mktemp("academy-user-data")
    overrides["STATE_FILE_PATH"] = str(tmp_state_dir / "state_dump.json")
    overrides["WORKSPACE_ROOT"] = str(tmp_workspace_dir)
    overrides["REPO_ROOT"] = str(tmp_workspace_dir)
    # Izoluj artefakty chronosa/snienia od repozytorium podczas testów.
    overrides["CHRONOS_TIMELINES_DIR"] = str(tmp_state_dir / "timelines")
    overrides["DREAMING_OUTPUT_DIR"] = str(tmp_state_dir / "synthetic_training")
    # Izoluj artefakty Academy od repozytorium podczas testów.
    overrides["ACADEMY_TRAINING_DIR"] = str(tmp_academy_training_dir)
    overrides["ACADEMY_MODELS_DIR"] = str(tmp_academy_models_dir)
    overrides["ACADEMY_USER_DATA_DIR"] = str(tmp_academy_user_data_dir)

    original_values = {attr: getattr(SETTINGS, attr) for attr in overrides}

    for attr, value in overrides.items():
        setattr(SETTINGS, attr, value)

    # Utrzymaj spójną ścieżkę jobs history także dla helperów korzystających
    # z modułowej stałej, aby testy nie zapisywały do ./data/training/jobs.jsonl.
    from venom_core.api.routes import academy as academy_routes

    original_jobs_history_file = academy_routes.JOBS_HISTORY_FILE
    academy_routes.JOBS_HISTORY_FILE = (
        Path(overrides["ACADEMY_TRAINING_DIR"]) / "jobs.jsonl"
    )

    yield original_values

    academy_routes.JOBS_HISTORY_FILE = original_jobs_history_file

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

    @staticmethod
    def _matches_entry_id(entry: dict, entry_id) -> bool:
        return not entry_id or entry["id"] == entry_id

    @staticmethod
    def _matches_collection(entry: dict, collection_name) -> bool:
        return not collection_name or entry["collection"] == collection_name

    @staticmethod
    def _matches_metadata(entry: dict, metadata_filters) -> bool:
        if not metadata_filters:
            return True
        entry_meta = entry.get("metadata", {})
        for key, value in metadata_filters.items():
            if entry_meta.get(key) != value:
                return False
        return True

    def list_entries(
        self, limit=200, metadata_filters=None, collection_name=None, entry_id=None
    ):
        results = []
        for entry in self.entries:
            if not self._matches_entry_id(entry, entry_id):
                continue
            if not self._matches_collection(entry, collection_name):
                continue
            if not self._matches_metadata(entry, metadata_filters):
                continue
            results.append(entry)
        if limit is None:
            return results
        return results[:limit]

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
            # Poor man's full text search for testing: check if all query words are present
            query_words = query.lower().split()
            text_lower = entry["text"].lower()
            if all(word in text_lower for word in query_words):
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


# --- Test Artifact Management Fixtures ---


@pytest.fixture(scope="session")
def test_artifact_session_dir() -> Path:
    """
    Globalny katalog artefaktów dla sesji testowej.
    W trybie CLEAN: usuwany po sesji.
    W trybie PRESERVE: zachowany do analizy.
    """
    artifact_dir = _PYTEST_ARTIFACTS_ROOT
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Zapisz metadane sesji
    metadata = {
        "type": "test_artifact_session",
        "mode": _ARTIFACT_MODE,
        "timestamp": datetime.now().isoformat(),
        "artifact_dir": str(artifact_dir),
    }
    metadata_file = artifact_dir / "session_metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2))

    yield artifact_dir

    # Cleanup w trybie CLEAN
    if _ARTIFACT_MODE == "clean":
        if artifact_dir.exists():
            shutil.rmtree(artifact_dir, ignore_errors=True)
    else:
        print(f"\n📁 Artefakty testowe zachowane w: {artifact_dir}")


@pytest.fixture
def test_artifact_dir(test_artifact_session_dir, request) -> Path:
    """
    Katalog artefaktów dla pojedynczego testu.
    Każdy test otrzymuje własny podkatalog w ramach sesji.
    """
    # Utwórz unikalny katalog dla tego testu
    test_name = request.node.name
    test_dir = test_artifact_session_dir / test_name
    test_dir.mkdir(parents=True, exist_ok=True)

    # Zapisz metadane testu
    metadata = {
        "type": "test_artifact",
        "test_name": test_name,
        "test_path": request.node.nodeid,
        "timestamp": datetime.now().isoformat(),
    }
    metadata_file = test_dir / "test_metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2))

    return test_dir
