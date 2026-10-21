"""Durable host ownership: actual work lifetime, not HTTP/TTL lifetime."""

import asyncio
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
    with pytest.raises(RuntimeAdmissionError, match="runtime_busy"):
        with admission.operation(kind="chat"):
            pytest.fail("chat cannot enter while lab owns its runtime")
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
    with pytest.raises(RuntimeAdmissionError):
        with lease.operation():
            pytest.fail("cancelled lease started another operation")
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
    with pytest.raises(RuntimeError):
        with lease.operation():
            raise RuntimeError("adapter failed before confirming process exit")
    assert admission.snapshot()["status"] == "quarantined"
    assert not lease.release()
    assert not lease.recover(confirm_quiescent=lambda: False)
    assert lease.recover(confirm_quiescent=lambda: True)
    assert acquire(admission, "second-run").release()


def test_terminal_model_failure_with_confirmed_join_is_not_quarantined(admission):
    lease = acquire(admission)
    with pytest.raises(ValueError):
        with lease.operation(confirm_quiescent=lambda: True):
            raise ValueError("model rejected input after worker joined")
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
        with pytest.raises(RuntimeAdmissionError):
            await asyncio.create_task(mutation())


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
    with pytest.raises(TimeoutError):
        with admission.operation(kind="chat_stream"):
            raise TimeoutError("socket ended without a terminal generation packet")
    assert admission.snapshot()["status"] == "quarantined"
    with pytest.raises(RuntimeAdmissionError):
        acquire(admission)
    with pytest.raises(RuntimeAdmissionError):
        with admission.operation(kind="stop", mutation=True):
            pytest.fail("uncertain generation may still occupy the daemon")
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
        if stream == "async":
            await function(*args, **kwargs)
        elif stream == "async_stream":
            async for _ in function(*args, **kwargs):
                pytest.fail("stream unexpectedly admitted")
        elif stream == "sync_stream":
            list(function(*args, **kwargs))
        else:
            function(*args, **kwargs)
    assert lease.release()


@pytest.mark.asyncio
async def test_existing_runtime_request_guard_and_http_paths_are_integrated(admission):
    from venom_core.infrastructure.traffic_control.http_client import (
        TrafficControlledHttpClient,
    )
    from venom_core.services.runtime_switch_gate import runtime_request_guard

    lease = acquire(admission)
    with pytest.raises(RuntimeAdmissionError):
        async with runtime_request_guard(request_kind="simple_chat"):
            pytest.fail("existing simple/voice guard did not honor lab lease")
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
    with pytest.raises(RuntimeError):
        with lease.operation():
            raise RuntimeError("worker failed")
    lease.cancel()
    with pytest.raises(RuntimeAdmissionError, match="runtime_quiescence_unconfirmed"):
        with lease.cleanup(confirm_quiescent=lambda: False):
            pass
    assert not lease.release()
    with lease.cleanup(confirm_quiescent=lambda: True):
        with pytest.raises(RuntimeAdmissionError):
            with lease.operation():
                pytest.fail("cleanup admitted another generation")
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
    with pytest.raises(TimeoutError):
        with admission.operation(kind="chat"):
            raise TimeoutError("unconfirmed daemon generation")
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
        with pytest.raises(TimeoutError):
            with admission.operation(kind="transport"):
                raise TimeoutError("terminal completion unknown")
    with pytest.raises(RuntimeAdmissionError, match="runtime_recovery_required"):
        with admission.operation(kind="new_work"):
            pytest.fail("full evidence ledger admitted more work")
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
        with pytest.raises(RuntimeAdmissionError):
            with admission.operation(kind="model_unload", mutation=True):
                pytest.fail("nested mutation bypassed another chat's generation")
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
