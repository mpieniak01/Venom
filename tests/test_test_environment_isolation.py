"""Isolation and read-only preconditions for the test runner."""

import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import conftest
from venom_core.config import SETTINGS
from venom_core.services import runtime_admission


@pytest.fixture(autouse=True)
def _isolate_live_target_environment(monkeypatch):
    """Tests explicitly choose both settings rather than inheriting an operator profile."""
    monkeypatch.delenv("VENOM_TEST_STACK_BASE", raising=False)
    monkeypatch.delenv("VENOM_API_BASE", raising=False)


def test_each_test_uses_private_runtime_ledger(monkeypatch):
    monkeypatch.setattr(SETTINGS, "RUNTIME_ADMISSION_ENABLED", True)
    memory = Path(SETTINGS.MEMORY_ROOT)
    assert memory.is_relative_to(conftest._TEST_MEMORY_ROOT)
    admission = runtime_admission.get_runtime_admission()
    assert admission.database == memory / "runtime-admission.sqlite3"
    with admission.operation(kind="test_isolation"):
        assert admission.snapshot()["status"] == "busy"
    assert admission.snapshot()["status"] == "available"


def test_disabled_admission_still_uses_private_runtime_ledger(monkeypatch):
    monkeypatch.setattr(SETTINGS, "RUNTIME_ADMISSION_ENABLED", False)
    memory = Path(SETTINGS.MEMORY_ROOT)
    assert memory.is_relative_to(conftest._TEST_MEMORY_ROOT)
    admission = runtime_admission.get_runtime_admission()
    assert admission.database == memory / "runtime-admission.sqlite3"
    assert admission.snapshot()["status"] == "disabled"


@pytest.mark.parametrize("port", [3300, 8800, 11434])
def test_simulated_test_cannot_connect_to_real_services(port):
    with socket.socket() as sock:
        with pytest.raises(PermissionError, match="protected service"):
            sock.connect(("127.0.0.1", port))


def test_unprotected_local_mock_port_is_allowed():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket() as client:
            client.connect(server.getsockname())
            conn, _ = server.accept()
            conn.close()


def test_live_and_direct_suites_are_skipped_without_opt_in():
    live = SimpleNamespace(keywords={"live_venom": True})
    direct = SimpleNamespace(keywords={"unsafe_direct_runtime": True})
    assert conftest._resolve_skip_marker(live, run_integration=False, run_live=False)
    assert conftest._resolve_skip_marker(direct, run_integration=True, run_live=True)


def test_stack_preflight_api_read_does_not_require_model(monkeypatch):
    monkeypatch.setenv("VENOM_TEST_STACK_BASE", "http://127.0.0.1:8800")
    seen = []

    def read(url):
        seen.append(url)
        if url.endswith("/healthz"):
            return {"status": "ok", "component": "venom-core"}
        return {"active_server": None, "active_model": None}

    monkeypatch.setattr(conftest, "_read_live_json", read)
    assert conftest._stack_state(requires_model=False) == ("ready", "ready")
    assert len(seen) == 2
    assert conftest._stack_state(requires_model=True) == (
        "stack_degraded",
        "runtime_model_unavailable",
    )


@pytest.mark.parametrize("status", ["busy", "owned", "quarantined", "disabled"])
def test_stack_preflight_rejects_unavailable_runtime(monkeypatch, status):
    monkeypatch.setenv("VENOM_TEST_STACK_BASE", "http://127.0.0.1:8800")

    def read(url):
        if url.endswith("/healthz"):
            return {"status": "ok", "component": "venom-core"}
        if url.endswith("/active"):
            return {"active_server": "ollama", "active_model": "existing"}
        return {"runtime": {"status": status, "active_operations": 0}}

    monkeypatch.setattr(conftest, "_read_live_json", read)
    assert conftest._stack_state() == ("stack_degraded", "runtime_busy")


def test_stack_preflight_rejects_nonlocal_or_unavailable_service(monkeypatch):
    monkeypatch.setenv("VENOM_TEST_STACK_BASE", "https://example.invalid:8800")
    assert conftest._stack_state() == ("stack_degraded", "invalid_local_target")
    monkeypatch.setenv("VENOM_TEST_STACK_BASE", "http://127.0.0.1:8800")
    monkeypatch.setattr(
        conftest, "_read_live_json", lambda _: (_ for _ in ()).throw(OSError())
    )
    assert conftest._stack_state() == ("stack_not_started", "stack_not_started")


def test_preflight_rejects_arbitrary_health_service(monkeypatch):
    monkeypatch.setenv("VENOM_TEST_STACK_BASE", "http://127.0.0.1:8800")
    monkeypatch.setattr(
        conftest,
        "_read_live_json",
        lambda _: {"status": "ok", "component": "other-service"},
    )
    assert conftest._stack_state(requires_model=False) == (
        "stack_degraded",
        "invalid_venom_health",
    )


def test_conflicting_configured_urls_fail_before_any_probe(monkeypatch):
    from tests.perf import chat_pipeline

    monkeypatch.setenv("VENOM_TEST_STACK_BASE", "http://127.0.0.1:8800")
    monkeypatch.setenv("VENOM_API_BASE", "http://127.0.0.1:8801")
    monkeypatch.setattr(
        conftest, "_read_live_json", lambda _: pytest.fail("unexpected probe")
    )
    assert conftest._stack_state() == ("stack_degraded", "invalid_local_target")
    with pytest.raises(ValueError, match="conflicting"):
        chat_pipeline._resolve_api_base()


def test_remote_and_legacy_fallback_url_cannot_replace_local_target(monkeypatch):
    from tests.perf import chat_pipeline

    monkeypatch.delenv("VENOM_TEST_STACK_BASE", raising=False)
    monkeypatch.delenv("VENOM_API_BASE", raising=False)
    monkeypatch.setenv("API_PROXY_TARGET", "https://remote.example:8800")
    monkeypatch.setenv("NEXT_PUBLIC_API_BASE", "https://other.example:8800")
    monkeypatch.setenv("API_BASE_URL", "https://third.example:8800")
    assert chat_pipeline._resolve_api_base() == "http://127.0.0.1:8800"
    monkeypatch.setenv("VENOM_TEST_STACK_BASE", "https://remote.example:8800")
    with pytest.raises(ValueError, match="invalid local target"):
        chat_pipeline._resolve_api_base()
    assert conftest._stack_state() == ("stack_degraded", "invalid_local_target")


def test_changed_target_is_rejected_before_probe(monkeypatch):
    monkeypatch.delenv("VENOM_API_BASE", raising=False)
    monkeypatch.setenv("VENOM_TEST_STACK_BASE", "http://127.0.0.1:8801")
    monkeypatch.setattr(
        conftest, "_read_live_json", lambda _: pytest.fail("unexpected probe")
    )
    assert conftest._stack_state(expected_base="http://127.0.0.1:8800") == (
        "stack_degraded",
        "live_target_changed",
    )


def test_target_changed_during_readonly_preflight_fails_closed(monkeypatch):
    monkeypatch.delenv("VENOM_API_BASE", raising=False)
    monkeypatch.setenv("VENOM_TEST_STACK_BASE", "http://127.0.0.1:8800")

    def read(url):
        if url.endswith("/healthz"):
            return {"status": "ok", "component": "venom-core"}
        monkeypatch.setenv("VENOM_TEST_STACK_BASE", "http://127.0.0.1:8801")
        return {"active_server": None, "active_model": None}

    monkeypatch.setattr(conftest, "_read_live_json", read)
    assert conftest._stack_state(requires_model=False) == (
        "stack_degraded",
        "live_target_changed",
    )


def test_live_connections_are_limited_to_verified_host_and_port(monkeypatch):
    monkeypatch.setattr(conftest, "_LIVE_API_ALLOWED", True)
    monkeypatch.setattr(conftest, "_LIVE_API_TARGET", ("127.0.0.1", 8800))
    conftest._check_test_connection(("127.0.0.1", 8800))
    for address in [("127.0.0.1", 8801), ("192.0.2.1", 8800), ("127.0.0.2", 8800)]:
        with pytest.raises(PermissionError, match="differs"):
            conftest._check_test_connection(address)
    with pytest.raises(PermissionError, match="protected service"):
        conftest._check_test_connection(("127.0.0.1", 11434))


def test_model_requires_active_server_as_well_as_model(monkeypatch):
    monkeypatch.delenv("VENOM_API_BASE", raising=False)
    monkeypatch.setenv("VENOM_TEST_STACK_BASE", "http://127.0.0.1:8800")

    def read(url):
        if url.endswith("/healthz"):
            return {"status": "ok", "component": "venom-core"}
        return {"active_server": "", "active_model": "existing"}

    monkeypatch.setattr(conftest, "_read_live_json", read)
    assert conftest._stack_state() == ("stack_degraded", "runtime_model_unavailable")


def test_perf_preflight_rejects_changed_collected_base_without_probe(monkeypatch):
    from tests.perf import chat_pipeline

    monkeypatch.delenv("VENOM_API_BASE", raising=False)
    monkeypatch.setenv("VENOM_TEST_STACK_BASE", "http://127.0.0.1:8801")
    monkeypatch.setattr(chat_pipeline, "API_BASE", "http://127.0.0.1:8800")
    monkeypatch.setattr(
        conftest, "_read_live_json", lambda _: pytest.fail("unexpected probe")
    )
    node = SimpleNamespace(
        nodeid="tests/perf/test_example.py::test_it", keywords={"live_venom": True}
    )
    fixture = conftest._live_preflight.__wrapped__(SimpleNamespace(node=node))
    with pytest.raises(pytest.skip.Exception, match="live_target_changed"):
        next(fixture)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["FAILED", "LOST"])
async def test_failed_live_task_after_start_is_failure_not_skip(monkeypatch, status):
    from unittest.mock import AsyncMock

    from tests.perf import latency_api_helpers

    monkeypatch.setattr(
        latency_api_helpers, "poll_task_completion", AsyncMock(return_value=status)
    )
    with pytest.raises(AssertionError, match=status):
        await latency_api_helpers.resolve_timeout_result(
            "test-task",
            start=0.0,
            first_token_time=None,
            event="timeout",
            api_base="http://127.0.0.1:8800",
            status_timeout=0.1,
            status_poll_interval=0.01,
            stream_timeout=0.1,
        )


def test_reserved_background_worker_blocks_teardown_until_finished(tmp_path):
    import threading

    before = set(threading.enumerate())
    admission = runtime_admission.RuntimeAdmission(
        tmp_path / "admission.sqlite3", enabled=True
    )
    reserved = admission.reserve_background(kind="test_worker")
    stop = threading.Event()
    worker = threading.Thread(
        target=reserved, args=(lambda: stop.wait(2.0),), daemon=True
    )
    worker.start()
    try:
        with pytest.raises(RuntimeError, match="did not finish"):
            conftest._join_test_admission_threads(before, timeout=0.01)
    finally:
        stop.set()
        worker.join(timeout=2.0)
    conftest._join_test_admission_threads(before, timeout=0.1)
    assert not worker.is_alive()


@pytest.mark.parametrize(
    "case_name",
    [
        "test_process_encoded_audio_buffer_full_flow",
        "test_process_audio_buffer_runs_normal_flow",
    ],
)
def test_live_audio_model_scenarios_are_blocked_even_with_live_opt_in(case_name):
    import ast

    source = Path("tests/test_audio_stream_live.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    case = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == case_name
    )
    marker_names = {
        node.attr
        for decorator in case.decorator_list
        for node in ast.walk(decorator)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
        and node.value.attr == "mark"
    }
    assert "unsafe_direct_runtime" in marker_names
    item = SimpleNamespace(keywords={name: True for name in marker_names})
    assert conftest._resolve_skip_marker(item, run_integration=True, run_live=True)


@pytest.mark.parametrize(
    "path", ["tests/test_rag_integration.py", "tests/test_forge_live.py"]
)
def test_direct_model_suites_are_blocked_before_dependency_setup(path):
    import ast

    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    declarations = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in node.targets
        )
    ]
    marks = {
        node.attr
        for declaration in declarations
        for node in ast.walk(declaration.value)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
        and node.value.attr == "mark"
    }
    assert "unsafe_direct_runtime" in marks
    assert conftest._resolve_skip_marker(
        SimpleNamespace(keywords={name: True for name in marks}),
        run_integration=True,
        run_live=True,
    )
    if path.endswith("test_rag_integration.py"):
        calls = [
            node
            for statement in tree.body
            if not isinstance(
                statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            )
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
        ]
        assert all(
            not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "importorskip"
            )
            for node in calls
        )


def test_worker_guard_does_not_read_clock_when_no_new_workers(monkeypatch):
    import threading

    previous = set(threading.enumerate())
    with monkeypatch.context() as patch:
        patch.setattr(
            conftest.time, "monotonic", lambda: pytest.fail("patched clock used")
        )
        conftest._join_test_admission_threads(previous)


def test_worker_guard_uses_original_clock_when_test_patches_monotonic(
    monkeypatch, tmp_path
):
    import threading

    previous = set(threading.enumerate())
    admission = runtime_admission.RuntimeAdmission(
        tmp_path / "admission.sqlite3", enabled=True
    )
    reserved = admission.reserve_background(kind="test_worker_clock")
    stop = threading.Event()
    worker = threading.Thread(
        target=reserved, args=(lambda: stop.wait(2.0),), daemon=True
    )
    worker.start()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(
                conftest.time, "monotonic", lambda: pytest.fail("patched clock used")
            )
            with pytest.raises(RuntimeError, match="did not finish"):
                conftest._join_test_admission_threads(previous, timeout=0.01)
    finally:
        stop.set()
        worker.join(timeout=2.0)
    assert not worker.is_alive()
