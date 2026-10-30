import atexit
import importlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import pytest

# A pytest process must never own the running host's admission ledger. Create
# the private root before test modules import Settings; xdist workers each load
# conftest in a separate process and therefore receive distinct roots.
_TEST_MEMORY_ROOT = Path(tempfile.mkdtemp(prefix="venom-pytest-memory-"))
os.environ["MEMORY_ROOT"] = str(_TEST_MEMORY_ROOT)
atexit.register(shutil.rmtree, _TEST_MEMORY_ROOT, ignore_errors=True)

# Prevent unmarked in-process test code from reaching the operator's local
# services during collection or simulated test execution. This does not cover
# subprocesses; those still need an explicit audit or network isolation.
_TEST_MONOTONIC = time.monotonic
_LIVE_API_ALLOWED = False
_LIVE_API_TARGET: tuple[str, int] | None = None
_DIRECT_RUNTIME_PORTS = {11434}
_PROTECTED_SERVICE_PORTS = {3300, 8800, *_DIRECT_RUNTIME_PORTS}
for _name in ("VENOM_TEST_STACK_BASE", "VENOM_API_BASE", "API_PROXY_TARGET"):
    try:
        _port = urlsplit(os.environ.get(_name, "")).port
    except ValueError:
        _port = None
    if _port is not None:
        _PROTECTED_SERVICE_PORTS.add(_port)
_original_socket_connect = socket.socket.connect
_original_socket_connect_ex = socket.socket.connect_ex


def _check_test_connection(address: Any) -> None:
    if not isinstance(address, tuple) or len(address) < 2:
        return  # Unix-domain sockets do not reach a TCP endpoint.
    host, port = address[0], address[1]
    if port in _DIRECT_RUNTIME_PORTS:
        raise PermissionError(
            f"test connection to protected service port {port} blocked"
        )
    if _LIVE_API_ALLOWED:
        # A live test is allowed to reach precisely the candidate host/port
        # captured before preflight, not another local or remote service.
        if _LIVE_API_TARGET is None:
            raise PermissionError("live target has not been captured")
        expected_host, expected_port = _LIVE_API_TARGET
        permitted_hosts = (
            {"127.0.0.1", "::1", "localhost"}
            if expected_host == "localhost"
            else {expected_host}
        )
        if str(host).lower() not in permitted_hosts or port != expected_port:
            raise PermissionError("connection differs from verified live target")
    elif port in _PROTECTED_SERVICE_PORTS:
        raise PermissionError(
            f"test connection to protected service port {port} blocked"
        )


def _guarded_socket_connect(sock: socket.socket, address: Any):
    _check_test_connection(address)
    return _original_socket_connect(sock, address)


def _guarded_socket_connect_ex(sock: socket.socket, address: Any):
    _check_test_connection(address)
    return _original_socket_connect_ex(sock, address)


socket.socket.connect = _guarded_socket_connect
socket.socket.connect_ex = _guarded_socket_connect_ex

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


def _read_live_json(url: str) -> dict[str, Any]:
    """Read a bounded response; never start, repair, or mutate the host."""
    with urllib.request.urlopen(url, timeout=1.5) as response:
        if response.status != 200:
            raise ValueError("unexpected HTTP status")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload


def _configured_live_base() -> str:
    """Resolve one local API target; conflicting settings are never guessed."""
    values = [
        os.environ.get(key, "").strip().rstrip("/")
        for key in ("VENOM_TEST_STACK_BASE", "VENOM_API_BASE")
        if os.environ.get(key, "").strip()
    ]
    if len(set(values)) > 1:
        raise ValueError("conflicting live target settings")
    base_url = values[0] if values else "http://127.0.0.1:8800"
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid local target") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        raise ValueError("invalid local target")
    return base_url


def _stack_state(
    *, requires_model: bool = True, expected_base: str | None = None
) -> tuple[str, str]:
    """Check the same existing local Venom instance used by the live test."""
    try:
        base_url = _configured_live_base()
    except ValueError:
        return ("stack_degraded", "invalid_local_target")
    if expected_base is not None and base_url != expected_base:
        return ("stack_degraded", "live_target_changed")
    try:
        health = _read_live_json(f"{base_url}/healthz")
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ):
        return ("stack_not_started", "stack_not_started")
    if health.get("status") != "ok" or health.get("component") != "venom-core":
        return ("stack_degraded", "invalid_venom_health")
    try:
        active = _read_live_json(f"{base_url}/api/v1/system/llm-servers/active")
        # The model is optional for read-only/API tests, but the response shape
        # identifies a Venom API rather than an arbitrary service on the port.
        if "active_server" not in active or "active_model" not in active:
            return ("stack_degraded", "invalid_venom_identity")
        if not requires_model:
            try:
                if _configured_live_base() != base_url:
                    return ("stack_degraded", "live_target_changed")
            except ValueError:
                return ("stack_degraded", "live_target_changed")
            return ("ready", "ready")
        if (
            not str(active.get("active_model") or "").strip()
            or not str(active.get("active_server") or "").strip()
        ):
            return ("stack_degraded", "runtime_model_unavailable")
        resources = _read_live_json(f"{base_url}/api/v1/system/models/resources")
        runtime = resources.get("runtime")
        if not isinstance(runtime, dict) or runtime.get("status") != "available":
            return ("stack_degraded", "runtime_busy")
        if runtime.get("active_operations", 0) or "owner" in runtime:
            return ("stack_degraded", "runtime_busy")
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ):
        return ("stack_degraded", "stack_degraded")
    try:
        if _configured_live_base() != base_url:
            return ("stack_degraded", "live_target_changed")
    except ValueError:
        return ("stack_degraded", "live_target_changed")
    return ("ready", "ready")


def _is_live(item: pytest.Item) -> bool:
    return any(
        name in item.keywords
        for name in (
            "live_venom",
            "live_model",
            "requires_stack",
            "manual_llm",
            "requires_docker",
            "requires_docker_compose",
            "unsafe_direct_runtime",
        )
    )


def _resolve_skip_marker(item: pytest.Item, *, run_integration: bool, run_live: bool):
    if "unsafe_direct_runtime" in item.keywords:
        return pytest.mark.skip(reason="direct runtime bypasses host admission")
    if _is_live(item) and not run_live:
        return pytest.mark.skip(reason="live test disabled; use --run-live-tests")
    if "integration" in item.keywords and not run_integration:
        return pytest.mark.skip(
            reason="pomijam testy integracyjne (użyj --run-integration aby uruchomić)"
        )
    return None


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Uruchom testy oznaczone markerem integration",
    )
    parser.addoption(
        "--run-live-tests",
        action="store_true",
        default=False,
        help="Uruchom zakwalifikowane testy na już działającym lokalnym Venomie",
    )


def pytest_configure(config):
    for marker in (
        "requires_docker: test wymaga istniejącego Venoma oraz Docker daemon",
        "requires_docker_compose: test wymaga istniejącego Venoma oraz Docker Compose",
        "integration: test integracyjny uruchamiany tylko z --run-integration",
        "requires_stack: test wymaga istniejącego Venoma oraz gotowego modelu",
        "live_venom: test wymaga istniejącego lokalnego API Venoma",
        "live_model: test wymaga istniejącego API Venoma, modelu i wolnego runtime",
        "unsafe_direct_runtime: direct generation bypasses host admission and is disabled",
        "live_state_file: test cannot yet inspect live state through the supported API",
    ):
        config.addinivalue_line("markers", marker)


def _configured_workers(config) -> int:
    raw = os.environ.get("PYTEST_XDIST_WORKER_COUNT")
    if raw is None:
        if hasattr(config, "workerinput"):
            return 2  # A worker without a reliable count must fail closed.
        raw = config.getoption("numprocesses", default=0)
    try:
        workers = int(raw or 0)
    except (TypeError, ValueError):
        return 2
    return workers if workers >= 0 else 2


def pytest_collection_modifyitems(config, items):
    run_integration = config.getoption("--run-integration")
    run_live = config.getoption("--run-live-tests")
    workers = _configured_workers(config)
    for item in items:
        # Mark dependencies before the expression filter is evaluated.
        if any(
            name in item.keywords
            for name in (
                "manual_llm",
                "requires_docker",
                "requires_docker_compose",
                "requires_stack",
            )
        ):
            item.add_marker(pytest.mark.live_venom)
        marker = _resolve_skip_marker(
            item, run_integration=run_integration, run_live=run_live
        )
        if marker:
            item.add_marker(marker)
        elif _is_live(item) and workers > 1:
            item.add_marker(
                pytest.mark.skip(reason="live tests require at most one worker")
            )
        if "live_state_file" in item.keywords:
            item.add_marker(
                pytest.mark.skip(reason="live state file lacks supported API access")
            )


@pytest.fixture(autouse=True)
def _isolate_vast_chat_selection(request, monkeypatch, tmp_path):
    """Offline tests cannot read or overwrite the operator's runtime selection."""
    if _is_live(request.node):
        return
    from venom_core.services import vast_chat_runtime

    monkeypatch.setattr(
        vast_chat_runtime, "_SELECTION", tmp_path / "vast-selection.json"
    )
    monkeypatch.setattr(vast_chat_runtime, "_selected", None)
    from venom_core.services import vast_chat_connection

    monkeypatch.setattr(vast_chat_connection, "ROOT", tmp_path / "vast")
    monkeypatch.setattr(vast_chat_connection, "_connection", None)


@pytest.fixture(autouse=True)
def _live_preflight(request: pytest.FixtureRequest):
    global _LIVE_API_ALLOWED, _LIVE_API_TARGET
    item = request.node
    if not _is_live(item):
        yield
        return
    try:
        target = _configured_live_base()
    except ValueError:
        pytest.skip("live precondition: invalid_local_target")
    if item.nodeid.startswith("tests/perf/"):
        # Performance helpers capture API_BASE at import; it must still match
        # the environment used for this test's actual preflight.
        from tests.perf import chat_pipeline

        if chat_pipeline.API_BASE != target:
            pytest.skip("live precondition: live_target_changed")
    parsed = urlsplit(target)
    _LIVE_API_TARGET = (
        parsed.hostname or "",
        parsed.port or (443 if parsed.scheme == "https" else 80),
    )
    _LIVE_API_ALLOWED = True
    try:
        requires_model = any(
            name in item.keywords for name in ("live_model", "requires_stack")
        )
        state, reason = _stack_state(
            requires_model=requires_model, expected_base=target
        )
        if state != "ready":
            pytest.skip(f"live precondition: {reason}")
        if "requires_docker_compose" in item.keywords and not _has_docker_compose():
            pytest.skip("Docker Compose unavailable")
        if "requires_docker" in item.keywords and not _has_docker():
            pytest.skip("Docker daemon unavailable")
        yield
    finally:
        _LIVE_API_ALLOWED = False
        _LIVE_API_TARGET = None


def _join_test_admission_threads(
    previous: set[threading.Thread], timeout: float = 3.0
) -> None:
    """Wait only for background admission workers created by this test."""
    workers = [
        thread
        for thread in threading.enumerate()
        if thread not in previous
        and getattr(getattr(thread, "_target", None), "__qualname__", "")
        == "RuntimeAdmission.reserve_background.<locals>.execute"
    ]
    if not workers:
        return
    deadline = _TEST_MONOTONIC() + timeout
    for worker in workers:
        worker.join(max(0.0, deadline - _TEST_MONOTONIC()))
    if any(worker.is_alive() for worker in workers):
        raise RuntimeError("test admission background worker did not finish")


@pytest.fixture(autouse=True)
def _isolate_test_runtime(monkeypatch: pytest.MonkeyPatch):
    """Give each test its own ledger, including when xdist reuses a worker."""
    from venom_core.config import SETTINGS
    from venom_core.services import runtime_admission

    previous_threads = set(threading.enumerate())
    memory = _TEST_MEMORY_ROOT / uuid.uuid4().hex
    monkeypatch.setenv("MEMORY_ROOT", str(memory))
    monkeypatch.setattr(SETTINGS, "MEMORY_ROOT", str(memory))
    monkeypatch.setattr(runtime_admission, "_ADMISSION", None)
    # Provider controls and selections are operator state, never test fixtures.
    from venom_core.services import (
        openrouter_runtime,
        remote_provider_control,
        vast_chat_runtime,
    )

    monkeypatch.setattr(
        remote_provider_control, "_STATE", memory / "provider-control.json"
    )
    monkeypatch.setattr(remote_provider_control, "_CHECKS", {})
    monkeypatch.setattr(openrouter_runtime, "_STATE", memory / "openrouter")
    monkeypatch.setattr(vast_chat_runtime, "_SELECTION", memory / "vast-selection.json")
    monkeypatch.setattr(vast_chat_runtime, "_selected", vast_chat_runtime._UNSET)
    yield
    # Do not rotate the test singleton while a reserved background worker can
    # still use it. An unresolved worker aborts the worker process fail-closed.
    try:
        _join_test_admission_threads(previous_threads)
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=1)
    # Private ledgers remain until process exit, avoiding deletion while an
    # unknown/untracked worker may still be finishing.


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
        "ENABLE_SANDBOX": False,
        "ALLOW_SANDBOX_CONTAINERS": False,
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
