"""Durable host ownership: actual work lifetime, not HTTP/TTL lifetime."""

import asyncio
import os
from dataclasses import replace

import pytest

from venom_core.services import runtime_admission as admission_module
from venom_core.services.runtime_admission import (
    RuntimeAdmission,
    RuntimeAdmissionError,
    admitted_operation,
)


@pytest.fixture
def admission(tmp_path, monkeypatch):
    value = RuntimeAdmission(tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(admission_module, "_ADMISSION", value)
    return value


def acquire(admission, run="run-1"):
    return admission.acquire(
        owner="cooperation_lab", run_id=run, engine="fixture", model="immutable-digest"
    )


def run_scoped(scope, failure=None):
    """Exercise one admitted action, distinguishing entry from a body failure."""
    with scope:
        if failure is not None:
            raise failure
        return "admitted"


async def invoke_host_entrypoint(function, args, kwargs, stream):
    if stream == "async":
        return await function(*args, **kwargs)
    if stream == "async_stream":
        return [item async for item in function(*args, **kwargs)]
    if stream == "sync_stream":
        return list(function(*args, **kwargs))
    return function(*args, **kwargs)


def test_disabled_is_fail_closed_without_creating_files(tmp_path):
    value = RuntimeAdmission(tmp_path / "disabled.sqlite3", enabled=False)
    with value.operation(kind="existing_chat"):
        assert value.snapshot()["status"] == "disabled"
    with pytest.raises(RuntimeAdmissionError, match="runtime_admission_disabled"):
        acquire(value)
    assert not value.database.exists()


@pytest.mark.parametrize(
    "name,value", [("WEB_CONCURRENCY", "2"), ("UVICORN_WORKERS", "invalid")]
)
def test_unqualified_worker_topology_is_rejected(admission, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeAdmissionError, match="runtime_topology_unsupported"):
        acquire(admission)


def test_exclusive_owner_blocks_host_and_wrong_capability(admission):
    lease = acquire(admission)
    assert admission.snapshot()["owner"] == "cooperation_lab"
    assert admission.snapshot()["owner_pid"] == os.getpid()
    scope = admission.operation(kind="chat")
    with pytest.raises(RuntimeAdmissionError, match="runtime_busy"):
        run_scoped(scope)
    with pytest.raises(RuntimeAdmissionError, match="runtime_busy"):
        acquire(admission, "run-2")
    foreign = replace(lease, _token="forged")
    with pytest.raises(RuntimeAdmissionError, match="runtime_lease_invalid"):
        foreign.release()
    with pytest.raises(RuntimeAdmissionError, match="runtime_lease_invalid"):
        foreign.recover(confirm_quiescent=lambda: True)
    assert lease.release()
    assert lease.release()
    assert admission.snapshot()["status"] == "available"


def test_running_host_operation_blocks_acquire_and_mutation(admission):
    with admission.operation(kind="chat"):
        with pytest.raises(RuntimeAdmissionError):
            acquire(admission)
        # Calls nested in the same host operation share its capability.
        with admission.operation(kind="maf"):
            assert admission.snapshot()["active_operations"] == 1
    assert acquire(admission).release()


def test_cancel_never_frees_active_operation(admission):
    lease = acquire(admission)
    with lease.operation():
        lease.cancel()
        assert not lease.release()
        assert not lease.recover(confirm_quiescent=lambda: True)
        assert admission.snapshot()["status"] == "cancelling"
    scope = lease.operation()
    with pytest.raises(RuntimeAdmissionError):
        run_scoped(scope)
    assert lease.release()


@pytest.mark.asyncio
async def test_waiter_cancel_keeps_actual_worker_owned_until_late_completion(admission):
    started, finish, ended = asyncio.Event(), asyncio.Event(), asyncio.Event()
    lease = acquire(admission)

    async def worker():
        started.set()
        await finish.wait()
        ended.set()
        return "late result"

    waiter = asyncio.create_task(lease.run(worker))
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not ended.is_set()
    assert not lease.release()
    with pytest.raises(RuntimeAdmissionError):
        acquire(admission, "second-run")
    finish.set()
    await ended.wait()
    await asyncio.sleep(0)
    assert lease.release()


def test_failed_adapter_quarantines_and_requires_trusted_quiescence(admission):
    lease = acquire(admission)
    scope = lease.operation()
    failure = RuntimeError("adapter failed before confirming process exit")
    with pytest.raises(RuntimeError, match="adapter failed"):
        run_scoped(scope, failure)
    assert admission.snapshot()["status"] == "quarantined"
    assert not lease.release()
    assert not lease.recover(confirm_quiescent=lambda: False)
    assert lease.recover(confirm_quiescent=lambda: True)
    assert acquire(admission, "second-run").release()


def test_terminal_model_failure_with_confirmed_join_is_not_quarantined(admission):
    lease = acquire(admission)
    scope = lease.operation(confirm_quiescent=lambda: True)
    failure = ValueError("model rejected input after worker joined")
    with pytest.raises(ValueError, match="model rejected"):
        run_scoped(scope, failure)
    assert lease.release()


def test_restart_does_not_forget_lease_or_quarantine(admission):
    lease = acquire(admission)
    replacement = RuntimeAdmission(admission.database)
    with pytest.raises(RuntimeAdmissionError):
        acquire(replacement, "new-process")
    with lease.operation():
        assert not replacement.recover(confirm_quiescent=lambda: True)
    assert replacement.recover(confirm_quiescent=lambda: True)


def test_identity_validation_and_environment_guard(admission, monkeypatch):
    with pytest.raises(RuntimeAdmissionError, match="runtime_identity_invalid"):
        admission.acquire(owner="", run_id="r", engine="fixture", model="m")
    monkeypatch.setattr(
        admission_module,
        "ensure_data_mutation_allowed",
        lambda name: (_ for _ in ()).throw(PermissionError(name)),
    )
    with pytest.raises(PermissionError):
        acquire(admission)


@pytest.mark.asyncio
async def test_decorator_covers_sync_async_and_streaming(admission):
    @admitted_operation("sync")
    def sync():
        return admission.snapshot()["active_operations"]

    @admitted_operation("async")
    async def asynchronous():
        return sync()

    @admitted_operation("generator")
    def generator():
        yield sync()

    @admitted_operation("stream")
    async def stream():
        yield await asynchronous()

    assert sync() == 1
    assert await asynchronous() == 1
    assert list(generator()) == [1]
    assert [item async for item in stream()] == [1]
    assert admission.snapshot()["active_operations"] == 0
    lease = acquire(admission)
    with pytest.raises(RuntimeAdmissionError):
        sync()
    assert lease.release()


@pytest.mark.asyncio
async def test_child_task_cannot_reuse_parent_operation_as_its_own(admission):
    async def mutation():
        with admission.operation(kind="switch", mutation=True):
            pytest.fail("parallel mutation bypassed parent generation")

    with admission.operation(kind="chat"):
        task = asyncio.create_task(mutation())
        with pytest.raises(RuntimeAdmissionError):
            await task


def test_reserved_background_worker_has_no_queue_admission_gap(admission):
    with admission.operation(kind="benchmark_start"):
        run_worker = admission.reserve_background(kind="benchmark_worker")
    assert admission.snapshot()["active_operations"] == 1
    with pytest.raises(RuntimeAdmissionError):
        acquire(admission)

    def worker():
        with admission.operation(kind="scheduler"):
            assert admission.snapshot()["active_operations"] == 1
        return "joined"

    assert run_worker(worker) == "joined"
    assert acquire(admission).release()


def test_uncertain_host_transport_prevents_experiment_and_switch(admission):
    scope = admission.operation(kind="chat_stream")
    failure = TimeoutError("socket ended without a terminal generation packet")
    with pytest.raises(TimeoutError, match="terminal generation packet"):
        run_scoped(scope, failure)
    assert admission.snapshot()["status"] == "quarantined"
    with pytest.raises(RuntimeAdmissionError):
        acquire(admission)
    scope = admission.operation(kind="stop", mutation=True)
    with pytest.raises(RuntimeAdmissionError):
        run_scoped(scope)
    assert not admission.recover(confirm_quiescent=lambda: False)
    assert admission.recover(confirm_quiescent=lambda: True)
    assert acquire(admission).release()


def test_restart_process_identity_requires_explicit_recovery(admission, monkeypatch):
    lease = acquire(admission)
    with admission._transaction() as db:
        db.execute("UPDATE lease SET pid=987654")
    assert admission.snapshot()["status"] == "quarantined"
    assert not lease.release()
    assert admission.recover(confirm_quiescent=lambda: True)


@pytest.mark.asyncio
async def test_two_generations_cannot_enter_same_lease_in_parallel(admission):
    lease = acquire(admission)
    started, finish = asyncio.Event(), asyncio.Event()

    async def worker():
        started.set()
        await finish.wait()

    first = asyncio.create_task(lease.run(worker))
    await started.wait()
    with pytest.raises(RuntimeAdmissionError):
        await lease.run(worker)
    finish.set()
    await first
    assert lease.release()


def test_lease_does_not_depend_on_ttl_or_http_clock(admission, monkeypatch):
    lease = acquire(admission)
    with admission._transaction() as db:
        db.execute("UPDATE lease SET pid=999999")
    replacement = RuntimeAdmission(admission.database)
    with pytest.raises(RuntimeAdmissionError):
        acquire(replacement, "not-expired-by-clock")
    assert not lease.release()


@pytest.mark.asyncio
async def test_confirmed_failure_of_awaited_worker_releases_without_quarantine(
    admission,
):
    lease = acquire(admission)

    async def worker():
        raise ValueError("input rejected; adapter already joined its child")

    with pytest.raises(ValueError):
        await lease.run(worker, confirm_quiescent=lambda: True)
    assert lease.release()


@pytest.mark.parametrize(
    "module_name,attribute,args,kwargs,stream",
    [
        (
            "venom_core.execution.maf_runtime",
            "MafChatService.get_chat_message_content",
            (None,),
            {"chat_history": None},
            "async",
        ),
        (
            "venom_core.execution.maf_runtime",
            "MafChatService.get_streaming_chat_message_contents",
            (None,),
            {"chat_history": None},
            "async_stream",
        ),
        (
            "venom_core.execution.ollama_agent_loop",
            "OllamaAgentLoop._call_ollama",
            (None, []),
            {},
            "sync",
        ),
        (
            "venom_core.execution.onnx_llm_client",
            "OnnxLlmClient.stream_generate",
            (None,),
            {"messages": []},
            "sync_stream",
        ),
        (
            "venom_core.core.llm_server_controller",
            "LlmServerController.run_action",
            (None, "ollama", "stop"),
            {},
            "async",
        ),
        (
            "venom_core.core.model_registry",
            "ModelRegistry.activate_model",
            (None, "fixture", "ollama"),
            {},
            "async",
        ),
        (
            "venom_core.core.model_manager",
            "ModelManager.activate_version",
            (None, "fixture"),
            {},
            "sync",
        ),
        (
            "venom_core.core.model_manager",
            "ModelManager.unload_all",
            (None,),
            {},
            "async",
        ),
        (
            "venom_core.services.benchmark",
            "BenchmarkService.start_benchmark",
            (None, ["fixture"]),
            {},
            "async",
        ),
        (
            "venom_core.services.benchmark_coding",
            "CodingBenchmarkService.start_run",
            (None, ["fixture"], ["fixture"]),
            {},
            "sync",
        ),
        (
            "venom_core.services.ollama_runtime_policy",
            "enforce_single_loaded_ollama_model",
            (),
            {"endpoint": "http://127.0.0.1:11434", "selected_model": "fixture"},
            "async",
        ),
    ],
)
@pytest.mark.asyncio
async def test_real_host_entrypoints_reject_while_experiment_owns_runtime(
    admission, module_name, attribute, args, kwargs, stream
):
    import importlib

    function = importlib.import_module(module_name)
    for name in attribute.split("."):
        function = getattr(function, name)
    lease = acquire(admission)
    with pytest.raises(RuntimeAdmissionError):
        await invoke_host_entrypoint(function, args, kwargs, stream)
    assert lease.release()


@pytest.mark.asyncio
async def test_existing_runtime_request_guard_and_http_paths_are_integrated(admission):
    from venom_core.infrastructure.traffic_control.http_client import (
        TrafficControlledHttpClient,
    )
    from venom_core.services.runtime_switch_gate import runtime_request_guard

    lease = acquire(admission)

    async def guarded_request():
        async with runtime_request_guard(request_kind="simple_chat"):
            return "admitted"

    with pytest.raises(RuntimeAdmissionError):
        await guarded_request()
    async with TrafficControlledHttpClient(provider="ollama") as client:
        with pytest.raises(RuntimeAdmissionError):
            await client.apost("http://127.0.0.1:11434/api/chat", json={})
    assert lease.release()


def test_http_classification_and_conditional_guard_skip_non_runtime(admission):
    from types import SimpleNamespace

    from venom_core.infrastructure.traffic_control.http_client import _runtime_request

    client = SimpleNamespace(provider="ollama")
    assert _runtime_request(client, "POST", "http://localhost:11434/api/chat")
    assert not _runtime_request(client, "GET", "http://localhost:11434/api/tags")
    assert not _runtime_request(
        SimpleNamespace(provider="github"),
        "POST",
        "https://github.com/chat/completions",
    )

    @admitted_operation("conditional", when=lambda enabled: enabled)
    def operation(enabled):
        return "ordinary integration"

    lease = acquire(admission)
    assert operation(False) == "ordinary integration"
    with pytest.raises(RuntimeAdmissionError):
        operation(True)
    assert lease.release()


@pytest.mark.asyncio
async def test_real_thread_adapter_lifecycle_can_cancel_then_close_own_process(
    admission,
):
    import threading

    lease = acquire(admission)
    started, finish = threading.Event(), threading.Event()
    closed = False

    def load():
        with lease.operation(kind="load"):
            assert admission.snapshot()["active_operations"] == 2

    def generate():
        with lease.operation():
            started.set()
            assert finish.wait(timeout=2)
            return "last token"

    def close():
        nonlocal closed
        with lease.cleanup(confirm_quiescent=lambda: closed):
            closed = True  # Represents verified synchronize + process.join.

    async def lifecycle():
        await asyncio.to_thread(load)
        try:
            return await asyncio.to_thread(generate)
        finally:
            await asyncio.to_thread(close)

    waiter = asyncio.create_task(lease.run(lifecycle, confirm_quiescent=lambda: closed))
    assert await asyncio.to_thread(started.wait, 2)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not lease.release()
    assert not closed
    finish.set()
    workers = list(admission._tasks)
    assert len(workers) == 1
    await asyncio.gather(*workers)
    assert closed
    assert lease.release()


def test_cleanup_after_failure_requires_verified_quiescence_and_forbids_generation(
    admission,
):
    lease = acquire(admission)
    scope = lease.operation()
    failure = RuntimeError("worker failed")
    with pytest.raises(RuntimeError, match="worker failed"):
        run_scoped(scope, failure)
    lease.cancel()
    cleanup = lease.cleanup(confirm_quiescent=lambda: False)
    with pytest.raises(RuntimeAdmissionError, match="runtime_quiescence_unconfirmed"):
        run_scoped(cleanup)
    assert not lease.release()
    with lease.cleanup(confirm_quiescent=lambda: True):
        scope = lease.operation()
        with pytest.raises(RuntimeAdmissionError):
            run_scoped(scope)
    assert lease.release()


def test_readonly_snapshot_is_side_effect_free_even_when_mutations_denied(
    admission, monkeypatch
):
    assert admission.snapshot()["status"] == "available"
    assert not admission.database.exists()
    lease = acquire(admission)
    monkeypatch.setattr(
        admission_module,
        "ensure_data_mutation_allowed",
        lambda name: (_ for _ in ()).throw(PermissionError(name)),
    )
    assert admission.snapshot()["status"] == "owned"
    assert lease._token not in str(admission.snapshot())


def test_orphaned_host_operation_is_reported_as_quarantine_after_restart(
    admission, monkeypatch
):
    scope = admission.operation(kind="chat")
    failure = TimeoutError("unconfirmed daemon generation")
    with pytest.raises(TimeoutError, match="unconfirmed daemon generation"):
        run_scoped(scope, failure)
    with admission._transaction() as db:
        db.execute("UPDATE operation SET pid=999999")
    assert admission.snapshot()["status"] == "quarantined"
    assert admission.recover(confirm_quiescent=lambda: True)


def test_corrupt_ledger_snapshot_fails_closed_without_rewriting_file(admission):
    admission.database.write_bytes(b"corrupt ledger fixture")
    assert admission.snapshot()["status"] == "quarantined"
    assert admission.database.read_bytes() == b"corrupt ledger fixture"


@pytest.mark.skipif(
    not admission_module.sys.platform.startswith("linux"),
    reason="Linux host process topology qualification",
)
def test_actual_second_process_is_refused_and_crash_preserves_quarantine(tmp_path):
    import subprocess
    import sys

    database = tmp_path / "process-ledger.sqlite3"
    script = """
from pathlib import Path
import sys
from venom_core.services.runtime_admission import RuntimeAdmission
admission = RuntimeAdmission(Path(sys.argv[1]))
lease = admission.acquire(owner='cooperation_lab', run_id='crash-run', engine='fixture', model='fixture')
with lease.operation():
    print('worker-active', flush=True)
    input()
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(database)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "worker-active"
        other_api_worker = RuntimeAdmission(database)
        assert other_api_worker.snapshot()["status"] == "quarantined"
        with pytest.raises(RuntimeAdmissionError, match="runtime_topology_unsupported"):
            acquire(other_api_worker)
        process.kill()
        process.communicate(timeout=5)
        assert other_api_worker.snapshot()["status"] == "quarantined"
        with pytest.raises(RuntimeAdmissionError, match="runtime_busy"):
            acquire(other_api_worker)
        assert not other_api_worker.recover(confirm_quiescent=lambda: False)
        assert other_api_worker.recover(confirm_quiescent=lambda: True)
        assert acquire(other_api_worker, "after-recovery").release()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def test_host_lock_unsupported_platform_is_explicit(admission, monkeypatch):
    monkeypatch.setattr(admission_module.sys, "platform", "unsupported-host")
    with pytest.raises(RuntimeAdmissionError, match="runtime_topology_unsupported"):
        acquire(admission)


def test_nested_caught_transport_failure_remains_visible_to_admission(admission):
    with admission.operation(kind="operator_fallback"):
        try:
            with admission.operation(kind="native_http"):
                raise TimeoutError("remote generation end not observed")
        except TimeoutError:
            pass
    assert admission.snapshot()["status"] == "quarantined"
    with pytest.raises(RuntimeAdmissionError):
        acquire(admission)
    assert admission.recover(confirm_quiescent=lambda: True)


def test_uncertain_operation_ledger_has_bounded_growth(admission, monkeypatch):
    monkeypatch.setattr(admission_module, "_MAX_OPERATIONS", 2)
    for _ in range(2):
        scope = admission.operation(kind="transport")
        failure = TimeoutError("terminal completion unknown")
        with pytest.raises(TimeoutError, match="terminal completion unknown"):
            run_scoped(scope, failure)
    scope = admission.operation(kind="new_work")
    with pytest.raises(RuntimeAdmissionError, match="runtime_recovery_required"):
        run_scoped(scope)
    assert admission.snapshot()["active_operations"] == 2
    assert admission.recover(confirm_quiescent=lambda: True)


def test_existing_stream_preflight_reports_busy_before_preparing_sse(admission):
    from venom_core.services.runtime_switch_gate import assert_runtime_request_allowed

    lease = acquire(admission)
    with pytest.raises(RuntimeAdmissionError, match="runtime_busy"):
        assert_runtime_request_allowed(request_kind="simple_chat")
    assert lease.release()
    assert_runtime_request_allowed(request_kind="simple_chat")


@pytest.mark.asyncio
async def test_nested_mutation_still_respects_independent_active_generation(admission):
    started, finish = asyncio.Event(), asyncio.Event()

    async def independent_chat():
        with admission.operation(kind="chat"):
            started.set()
            await finish.wait()

    other = asyncio.create_task(independent_chat())
    await started.wait()
    with admission.operation(kind="benchmark_start"):
        scope = admission.operation(kind="model_unload", mutation=True)
        with pytest.raises(RuntimeAdmissionError):
            run_scoped(scope)
    finish.set()
    await other


@pytest.mark.asyncio
async def test_benchmark_route_conflict_survives_legacy_generic_error_handlers(
    admission,
):
    from venom_core.api.routes import benchmark, benchmark_coding

    lease = acquire(admission)
    with pytest.raises(RuntimeAdmissionError, match="runtime_busy"):
        await benchmark.start_benchmark(None)
    # Coding start returns before its worker; admission is outside legacy catches.
    function = next(
        value
        for name, value in vars(benchmark_coding).items()
        if name.startswith("start_") and callable(value)
    )
    with pytest.raises(RuntimeAdmissionError, match="runtime_busy"):
        await function(None)
    assert lease.release()


@pytest.mark.skipif(
    not admission_module.sys.platform.startswith("linux"),
    reason="Linux application file descriptor regression",
)
def test_readonly_snapshot_always_closes_database_file_descriptor(admission):
    import gc
    from pathlib import Path

    lease = acquire(admission)
    target = str(admission.database.resolve())

    def descriptors():
        total = 0
        for path in Path("/proc/self/fd").iterdir():
            try:
                total += admission_module.os.readlink(path) == target
            except FileNotFoundError:
                pass
        return total

    baseline = descriptors()
    was_enabled = gc.isenabled()
    gc.disable()  # Do not let GC hide a connection left open by a transaction CM.
    try:
        for _ in range(20):
            assert admission.snapshot()["status"] == "owned"
        assert descriptors() == baseline
    finally:
        if was_enabled:
            gc.enable()
    assert lease.release()


@pytest.mark.parametrize("enabled", ["false", "true"])
def test_actual_application_openapi_resolves_wrapped_route_annotations(enabled):
    import os
    import subprocess
    import sys

    environment = {
        **os.environ,
        "VENOM_RUNTIME_PROFILE": "llm_off",
        "LLM_WARMUP_ON_STARTUP": "false",
        "FEATURE_COOPERATION_LAB": "false",
        "RUNTIME_ADMISSION_ENABLED": enabled,
        "API_OPTIONAL_MODULES": "",
    }
    script = """
from venom_core.main import app
schema = app.openapi()
assert len(schema['paths']) > 100
expected = {
    '/api/v1/benchmark/start': 'BenchmarkStartRequest',
    '/api/v1/benchmark/coding/start': 'CodingBenchmarkStartRequest',
    '/api/v1/system/llm-servers/active': 'ActiveLlmServerRequest',
    '/api/v1/system/llm-runtime/active': 'LlmRuntimeActivateRequest',
    '/api/v1/models/switch': 'ModelSwitchRequest',
}
for path, request_type in expected.items():
    request = schema['paths'][path]['post']['requestBody']['content']['application/json']['schema']
    assert request['$ref'] == '#/components/schemas/' + request_type
    assert request_type in schema['components']['schemas']
print('actual-application-openapi-pass')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr + result.stdout[-2000:]
    assert "actual-application-openapi-pass" in result.stdout


def test_new_ledger_and_leaf_directory_are_private_under_standard_umask(tmp_path):
    import os
    import stat

    parent = tmp_path / "private-runtime"
    value = RuntimeAdmission(parent / "ledger.sqlite3")
    previous = os.umask(0o022)
    try:
        lease = acquire(value)
    finally:
        os.umask(previous)
    assert stat.S_IMODE(parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(value.database.stat().st_mode) == 0o600
    assert (
        stat.S_IMODE(value.database.with_suffix(".host.lock").stat().st_mode) == 0o600
    )
    assert lease.release()


def test_existing_parent_is_preserved_and_owned_legacy_ledger_becomes_private(tmp_path):
    import stat

    parent = tmp_path / "existing-runtime"
    parent.mkdir(mode=0o750)
    value = RuntimeAdmission(parent / "ledger.sqlite3")
    lease = acquire(value)
    value.database.chmod(0o644)
    assert lease.release()
    assert stat.S_IMODE(parent.stat().st_mode) == 0o750
    assert stat.S_IMODE(value.database.stat().st_mode) == 0o600


@pytest.mark.parametrize("target_kind", ["file", "parent", "hardlink", "fifo"])
def test_unsafe_ledger_paths_are_rejected_without_touching_targets(
    tmp_path, target_kind
):
    import os

    outside = tmp_path / "outside"
    outside.mkdir(mode=0o750)
    target = outside / "original.sqlite3"
    target.write_bytes(b"not an admission ledger")
    target.chmod(0o640)
    database = tmp_path / "ledger.sqlite3"
    if target_kind == "file":
        database.symlink_to(target)
    elif target_kind == "parent":
        parent = tmp_path / "linked-parent"
        parent.symlink_to(outside, target_is_directory=True)
        database = parent / "new.sqlite3"
    elif target_kind == "hardlink":
        os.link(target, database)
    else:
        os.mkfifo(database)
    value = RuntimeAdmission(database)
    assert value.snapshot() == {
        "api_version": 1,
        "status": "quarantined",
        "active_operations": 0,
        "code": "runtime_storage_unsafe",
    }
    with pytest.raises(RuntimeAdmissionError, match="runtime_storage_unsafe"):
        acquire(value)
    assert target.read_bytes() == b"not an admission ledger"
    assert target.stat().st_mode & 0o777 == 0o640
    assert outside.stat().st_mode & 0o777 == 0o750
    assert not (outside / "new.sqlite3").exists()
    assert not (outside / "new.host.lock").exists()


def test_unsafe_host_lock_does_not_rewrite_external_file_or_create_ledger(tmp_path):
    target = tmp_path / "external-lock"
    target.write_text("unrelated file")
    database = tmp_path / "ledger.sqlite3"
    database.with_suffix(".host.lock").symlink_to(target)
    value = RuntimeAdmission(database)
    with pytest.raises(RuntimeAdmissionError, match="runtime_storage_unsafe"):
        acquire(value)
    assert not database.exists()
    assert target.read_text() == "unrelated file"


@pytest.mark.parametrize("quiescent", [False, True])
def test_cleanup_body_failure_still_reconciles_only_verified_quiescence(
    admission, quiescent
):
    lease = acquire(admission)
    scope = lease.operation()
    generation_error = RuntimeError("generation worker failed")
    with pytest.raises(RuntimeError, match="generation worker failed"):
        run_scoped(scope, generation_error)
    lease.cancel()
    cleanup = lease.cleanup(confirm_quiescent=lambda: quiescent)
    cleanup_error = ValueError("housekeeping failed after worker close")
    expected = ValueError if quiescent else RuntimeAdmissionError
    message = "housekeeping failed" if quiescent else "runtime_quiescence_unconfirmed"
    with pytest.raises(expected, match=message):
        run_scoped(cleanup, cleanup_error)
    assert admission.snapshot()["active_operations"] == 0
    assert lease.release() is quiescent
    if quiescent:
        assert acquire(admission, "after-verified-cleanup").release()
    else:
        assert admission.snapshot()["status"] == "quarantined"


async def _normal_chat_with_mock_transport(monkeypatch, handler):
    """Run the public simple service through the actual guarded HTTP transport."""
    import json
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import httpx

    from venom_core.api.schemas.llm_simple import SimpleChatRequest
    from venom_core.infrastructure.traffic_control.http_client import (
        TrafficControlledHttpClient,
    )
    from venom_core.services import llm_simple_service, llm_simple_transport

    errors = []
    runtime = SimpleNamespace(
        provider="ollama",
        model_name="preserved-model",
        endpoint="http://fixture/v1",
        service_type="local",
        config_hash="preserved-config",
        runtime_id="fixture",
    )

    @asynccontextmanager
    async def client_factory(**kwargs):
        async with TrafficControlledHttpClient(**kwargs) as client:
            await client._async_client.aclose()
            client._async_client = httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            )
            yield client

    async def no_adapter():
        return None

    tracer = SimpleNamespace(
        set_error_metadata=lambda _request, metadata: errors.append(metadata)
    )
    monkeypatch.setattr(
        llm_simple_transport, "TrafficControlledHttpClient", client_factory
    )
    monkeypatch.setattr(llm_simple_service, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(llm_simple_service, "_get_active_adapter_id", no_adapter)
    monkeypatch.setattr(llm_simple_service, "_get_request_tracer", lambda: tracer)
    monkeypatch.setattr(llm_simple_service.SETTINGS, "OLLAMA_RETRY_MAX_ATTEMPTS", 1)
    response = await llm_simple_service.stream_simple_chat(
        SimpleChatRequest(content="One short reply.", max_tokens=8)
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = []
    for chunk in chunks:
        lines = chunk.splitlines()
        events.append(
            (
                lines[0].removeprefix("event: "),
                json.loads(lines[1].removeprefix("data: ")),
            )
        )
    return events, errors


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 413, 415, 422])
async def test_normal_chat_http_rejection_preserves_error_and_releases_admission(
    admission, monkeypatch, status
):
    import json

    import httpx

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, json={"error": "model secret-key-value does not support thinking"}
        )

    events, errors = await _normal_chat_with_mock_transport(monkeypatch, handler)
    assert [name for name, _ in events] == ["start", "error"]
    assert events[-1][1]["code"] == "llm_http_error"
    assert len(calls) == 1
    assert admission.snapshot()["status"] == "available"
    assert admission.snapshot()["active_operations"] == 0
    assert acquire(admission, "lab-after-rejection").release()
    diagnostic = json.loads(errors[0]["error_details"]["response"])
    assert diagnostic["reason_code"] == "unsupported_thinking"
    assert diagnostic["sampled_bytes"] > 0
    assert not diagnostic["truncated_or_incomplete"]
    assert "secret-key-value" not in json.dumps([events, errors])


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504])
async def test_normal_chat_unconfirmed_http_failure_keeps_quarantine(
    admission, monkeypatch, status
):
    import httpx

    def handler(_request):
        return httpx.Response(status, json={"error": "unknown daemon work state"})

    events, _errors = await _normal_chat_with_mock_transport(monkeypatch, handler)
    assert [name for name, _ in events] == ["start", "error"]
    assert admission.snapshot()["status"] == "quarantined"
    assert admission.snapshot()["active_operations"] == 1
    with pytest.raises(RuntimeAdmissionError):
        acquire(admission, "must-not-admit")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["read_timeout", "incomplete_2xx"])
async def test_normal_chat_unknown_generation_end_is_not_http_rejection(
    admission, monkeypatch, failure
):
    import httpx

    def handler(request):
        if failure == "read_timeout":
            raise httpx.ReadTimeout(
                "terminal worker state not observed", request=request
            )
        return httpx.Response(
            200, content='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        )

    events, _errors = await _normal_chat_with_mock_transport(monkeypatch, handler)
    assert events[0][0] == "start"
    assert events[-1][0] == "error"
    assert "done" not in [name for name, _ in events]
    assert admission.snapshot()["status"] == "quarantined"
    assert admission.snapshot()["active_operations"] == 1


@pytest.mark.asyncio
async def test_rejection_proof_cannot_release_a_different_operation(admission):
    import httpx

    from venom_core.infrastructure.traffic_control.http_client import (
        TrafficControlledHttpClient,
    )

    async with TrafficControlledHttpClient(provider="ollama") as client:
        await client._async_client.aclose()
        client._async_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(404, json={"error": "model not found"})
            )
        )

        async def request():
            async with client.astream(
                "POST", "http://fixture/v1/chat/completions", disable_retry=True
            ):
                pytest.fail("rejected HTTP response must not reach generation reader")

        with pytest.raises(httpx.HTTPStatusError) as rejected:
            await request()
    assert admission.snapshot()["status"] == "available"
    scope = admission.operation(kind="another-worker")
    with pytest.raises(httpx.HTTPStatusError):
        run_scoped(scope, rejected.value)
    assert admission.snapshot()["status"] == "quarantined"


@pytest.mark.asyncio
async def test_error_body_diagnostic_is_bounded_and_raw_body_never_reaches_trace(
    admission, monkeypatch
):
    import json

    import httpx

    def handler(_request):
        return httpx.Response(400, content=b"secret-key-value" * 10000)

    _events, errors = await _normal_chat_with_mock_transport(monkeypatch, handler)
    diagnostic = json.loads(errors[0]["error_details"]["response"])
    assert diagnostic["reason_code"] == "unspecified"
    assert diagnostic["sampled_bytes"] == 2048
    assert diagnostic["truncated_or_incomplete"]
    assert "secret-key-value" not in json.dumps(errors)
    assert admission.snapshot()["status"] == "available"


@pytest.mark.parametrize(
    "body,expected",
    [
        (b"[]", "unspecified"),
        (b'{"error": 42}', "unspecified"),
        (b'{"error":{"message":"model private-name not found"}}', "model_not_found"),
        (b'{"error":"model is required"}', "model_required"),
        (b'{"error":"unrecognized private diagnostic"}', "unspecified"),
    ],
)
def test_upstream_reason_is_a_fixed_code_not_raw_error_body(body, expected):
    from venom_core.infrastructure.traffic_control.http_client import _error_reason

    assert _error_reason(body) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["read_error", "stalled_body"])
async def test_rejected_error_body_read_is_bounded_without_inventing_model_completion(
    admission, monkeypatch, failure
):
    import json

    import httpx

    class UnavailableErrorBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"private diagnostic prefix"
            if failure == "read_error":
                raise httpx.ReadError("error body became unavailable")
            await asyncio.Event().wait()

    def handler(_request):
        return httpx.Response(400, stream=UnavailableErrorBody())

    events, errors = await _normal_chat_with_mock_transport(monkeypatch, handler)
    assert [name for name, _ in events] == ["start", "error"]
    diagnostic = json.loads(errors[0]["error_details"]["response"])
    assert diagnostic["truncated_or_incomplete"]
    assert diagnostic["reason_code"] == "unspecified"
    assert "private diagnostic prefix" not in json.dumps(errors)
    # The HTTP rejection, not receipt of its optional body, proves no generation
    # was accepted. A timeout of an accepted request is covered separately.
    assert admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_caller_status_error_after_accepted_response_is_not_transport_proof(
    admission,
):
    import httpx

    from venom_core.infrastructure.traffic_control.http_client import (
        TrafficControlledHttpClient,
    )

    async with TrafficControlledHttpClient(provider="ollama") as client:
        await client._async_client.aclose()
        client._async_client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={}))
        )

        async def consume_accepted_response():
            async with client.astream(
                "POST", "http://fixture/v1/chat/completions", disable_retry=True
            ) as response:
                assert response.status_code == 200
                # A consumer cannot turn its own exception/status into rejection proof.
                rejected = httpx.Response(400, request=response.request)
                rejected.raise_for_status()

        with pytest.raises(httpx.HTTPStatusError):
            await consume_accepted_response()
    assert admission.snapshot()["status"] == "quarantined"
    assert admission.snapshot()["active_operations"] == 1


@pytest.mark.asyncio
async def test_prior_rejection_cannot_hide_later_accepted_work_in_same_operation(
    admission,
):
    import httpx

    from venom_core.infrastructure.traffic_control.http_client import (
        TrafficControlledHttpClient,
    )

    statuses = iter([400, 200])
    url = "http://fixture/v1/chat/completions"
    async with TrafficControlledHttpClient(provider="ollama") as client:
        await client._async_client.aclose()
        client._async_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    next(statuses), json={"error": "rejected"}
                )
            )
        )
        with admission.operation(kind="outer_chat"):

            async def first_request():
                async with client.astream("POST", url, disable_retry=True):
                    pytest.fail("rejected request reached consumer")

            with pytest.raises(httpx.HTTPStatusError) as saved:
                await first_request()

            async def later_request():
                async with client.astream("POST", url, disable_retry=True) as response:
                    assert response.status_code == 200
                    # A real but old proof must not certify the accepted worker.
                    raise saved.value

            with pytest.raises(httpx.HTTPStatusError):
                await later_request()
    assert admission.snapshot()["status"] == "quarantined"
    assert admission.snapshot()["active_operations"] == 1


def test_process_instance_identity_is_stable_but_changes_with_boot(monkeypatch):
    from pathlib import Path

    identity = admission_module.process_instance_identity(os.getpid())
    assert identity is not None
    assert len(identity) == 64
    assert identity == admission_module.process_instance_identity(os.getpid())
    original = Path.read_text

    def changed_boot(path, *args, **kwargs):
        return (
            "another-boot"
            if path.name == "boot_id"
            else original(path, *args, **kwargs)
        )

    monkeypatch.setattr(Path, "read_text", changed_boot)
    assert identity != admission_module.process_instance_identity(os.getpid())


@pytest.mark.parametrize("pid", [0, -1, True, None])
def test_process_instance_identity_rejects_invalid_pid(pid):
    assert admission_module.process_instance_identity(pid) is None


def test_process_instance_identity_requires_readable_consistent_proc_metadata(
    monkeypatch,
):
    from pathlib import Path

    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: "malformed")
    assert admission_module.process_instance_identity(os.getpid()) is None
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError()),
    )
    assert admission_module.process_instance_identity(os.getpid()) is None


def test_legacy_lease_schema_migrates_and_reused_pid_is_quarantined(
    admission, monkeypatch
):
    import sqlite3

    with sqlite3.connect(admission.database) as db:
        db.execute(
            "CREATE TABLE lease (id INTEGER PRIMARY KEY, token TEXT, owner TEXT, run_id TEXT, engine TEXT, model TEXT, pid INTEGER, cancelled INTEGER DEFAULT 0, quarantine INTEGER DEFAULT 0)"
        )
    lease = acquire(admission)
    original = admission.snapshot()
    assert original[
        "owner_process_identity"
    ] == admission_module.process_instance_identity(os.getpid())
    monkeypatch.setattr(
        admission_module,
        "process_instance_identity",
        lambda _pid: "different-process-lifetime",
    )
    current = admission.snapshot()
    assert current["owner_pid"] == os.getpid()
    assert current["owner_process_identity"] == original["owner_process_identity"]
    assert current["status"] == "quarantined"
    assert lease.release()


def test_process_identity_supports_container_init_pid_one(monkeypatch):
    from pathlib import Path

    boot = ["boot-one"]

    def proc_metadata(path, *_args, **_kwargs):
        if path.name == "boot_id":
            return boot[0]
        assert str(path) == "/proc/1/stat"
        return "1 (container api) R " + "0 " * 18 + "42"

    monkeypatch.setattr(Path, "read_text", proc_metadata)
    monkeypatch.setattr(os, "readlink", lambda _path: "pid:[4026531836]")
    identity = admission_module.process_instance_identity(1)
    assert identity is not None
    assert len(identity) == 64
    boot[0] = "boot-two"
    assert admission_module.process_instance_identity(1) != identity


def test_recovery_startup_holds_writer_lock_and_preserves_quarantine(admission):
    import sqlite3
    from contextlib import closing

    lease = acquire(admission)
    with admission._transaction() as db:
        db.execute("UPDATE lease SET quarantine=1")
    observed = []
    with admission.recovery_startup(
        permitted=lambda value: observed.append(value) or True
    ):
        with closing(sqlite3.connect(admission.database, timeout=0.01)) as other:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("BEGIN IMMEDIATE")
    assert observed[0]["status"] == "quarantined"
    assert observed[0]["active_operations"] == 0
    assert "token" not in observed[0]
    assert admission.snapshot()["status"] == "quarantined"
    assert lease.recover(confirm_quiescent=lambda: True)


def test_recovery_startup_rechecks_fresh_state_and_fails_closed(admission):
    lease = acquire(admission)
    with pytest.raises(RuntimeAdmissionError, match="runtime_busy"):
        with admission.recovery_startup(permitted=lambda _value: True):
            pass
    with admission._transaction() as db:
        db.execute("UPDATE lease SET quarantine=1")
    with pytest.raises(RuntimeAdmissionError, match="runtime_busy"):
        with admission.recovery_startup(permitted=lambda _value: False):
            pass
    assert admission.snapshot()["status"] == "quarantined"
    with admission._transaction() as db:
        db.execute(
            "INSERT INTO operation(token,lease_token,kind,pid) SELECT 'busy',token,'generation',pid FROM lease"
        )
    with pytest.raises(RuntimeAdmissionError, match="runtime_busy"):
        with admission.recovery_startup(permitted=lambda _value: True):
            pass
    with admission._transaction() as db:
        db.execute("DELETE FROM operation")
    assert lease.recover(confirm_quiescent=lambda: True)
