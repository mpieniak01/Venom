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
