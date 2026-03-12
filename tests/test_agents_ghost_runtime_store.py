"""Targeted tests for Ghost API runtime state helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.api.routes import agents as mod


def test_ghost_run_state_store_lifecycle(tmp_path):
    store = mod._GhostRunStateStore(tmp_path / "ghost-state.json")

    assert store.get() is None
    assert store.try_start({"task_id": "t1", "status": "running"}) is True
    assert store.try_start({"task_id": "t2", "status": "running"}) is False

    current = store.update("other-task", {"status": "failed"})
    assert current is not None
    assert current["task_id"] == "t1"
    assert current["status"] == "running"

    updated = store.update("t1", {"status": "completed", "result": "ok"})
    assert updated is not None
    assert updated["status"] == "completed"
    assert updated["result"] == "ok"

    store.clear()
    assert store.get() is None


def test_ghost_run_state_store_invalid_json_returns_none(tmp_path):
    state_path = tmp_path / "broken-state.json"
    state_path.write_text("{not-json", encoding="utf-8")
    store = mod._GhostRunStateStore(state_path)

    assert store.get() is None


def test_ghost_run_state_store_non_dict_payload_returns_none(tmp_path):
    state_path = tmp_path / "list-state.json"
    state_path.write_text('["not-a-dict"]', encoding="utf-8")
    store = mod._GhostRunStateStore(state_path)

    assert store.get() is None


def test_ghost_run_state_path_resolution_guards(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.SETTINGS, "WORKSPACE_ROOT", str(tmp_path))
    default_path = (tmp_path / ".venom" / "runtime" / "ghost_run_state.json").resolve()

    assert mod._resolve_ghost_run_state_path(None) == default_path
    assert mod._resolve_ghost_run_state_path("") == default_path
    assert (
        mod._resolve_ghost_run_state_path("state/custom.json")
        == (tmp_path / "state" / "custom.json").resolve()
    )
    assert mod._resolve_ghost_run_state_path("../escape.json") == default_path
    assert mod._resolve_ghost_run_state_path("/etc/passwd") == default_path


def test_ghost_run_state_store_constructor_rejects_unsafe_path(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.SETTINGS, "WORKSPACE_ROOT", str(tmp_path))
    store = mod._GhostRunStateStore(Path("/etc/passwd"))

    expected = (tmp_path / ".venom" / "runtime" / "ghost_run_state.json").resolve()
    assert store._state_path == expected

    assert store.try_start({"task_id": "t1", "status": "running"}) is True
    assert expected.exists()


@pytest.mark.asyncio
async def test_run_ghost_process_with_cancel_watch_success(tmp_path, monkeypatch):
    store = mod._GhostRunStateStore(tmp_path / "state.json")
    monkeypatch.setattr(mod, "_ghost_run_store", store)
    mod._ghost_local_tasks.clear()
    store.try_start({"task_id": "task-ok", "status": "running"})

    ghost = MagicMock()
    ghost.process = AsyncMock(return_value="done")
    ghost.emergency_stop_trigger = MagicMock()
    monkeypatch.setattr(mod, "_ghost_agent", ghost)

    result = await mod._run_ghost_process_with_cancel_watch(
        task_id="task-ok", content="open app"
    )

    assert result == "done"
    ghost.emergency_stop_trigger.assert_not_called()


@pytest.mark.asyncio
async def test_run_ghost_process_with_cancel_watch_cancelled(tmp_path, monkeypatch):
    store = mod._GhostRunStateStore(tmp_path / "state.json")
    monkeypatch.setattr(mod, "_ghost_run_store", store)
    mod._ghost_local_tasks.clear()
    store.try_start({"task_id": "task-cancel", "status": "running"})

    started = asyncio.Event()

    async def _slow_process(_content: str) -> str:
        started.set()
        await asyncio.sleep(0.5)
        return "never"

    ghost = MagicMock()
    ghost.process = AsyncMock(side_effect=_slow_process)
    ghost.emergency_stop_trigger = MagicMock()
    monkeypatch.setattr(mod, "_ghost_agent", ghost)

    task = asyncio.create_task(
        mod._run_ghost_process_with_cancel_watch(
            task_id="task-cancel",
            content="open app",
        )
    )
    await started.wait()
    store.update("task-cancel", {"status": "cancelling"})

    with pytest.raises(asyncio.CancelledError):
        await task

    ghost.emergency_stop_trigger.assert_called_once()


@pytest.mark.asyncio
async def test_run_ghost_job_updates_completed_state(tmp_path, monkeypatch):
    store = mod._GhostRunStateStore(tmp_path / "state.json")
    monkeypatch.setattr(mod, "_ghost_run_store", store)
    mod._ghost_local_tasks.clear()
    store.try_start(
        {"task_id": "job-ok", "status": "running", "runtime_profile": "desktop_safe"}
    )
    mod._ghost_local_tasks["job-ok"] = MagicMock()

    monkeypatch.setattr(
        mod,
        "_run_ghost_process_with_cancel_watch",
        AsyncMock(return_value="job done"),
    )
    publish = MagicMock()
    monkeypatch.setattr(mod, "_publish_ghost_audit", publish)

    payload = mod.GhostRunRequest(content="do stuff")
    result = await mod._run_ghost_job(task_id="job-ok", payload=payload, actor="tester")

    assert result == "job done"
    state = store.get()
    assert state is not None
    assert state["status"] == "completed"
    assert state["result"] == "job done"
    assert "finished_at" in state
    assert "job-ok" not in mod._ghost_local_tasks
    assert any(
        call.kwargs["action"] == "ghost.run.completed" for call in publish.mock_calls
    )


@pytest.mark.asyncio
async def test_run_ghost_job_updates_failed_state(tmp_path, monkeypatch):
    store = mod._GhostRunStateStore(tmp_path / "state.json")
    monkeypatch.setattr(mod, "_ghost_run_store", store)
    mod._ghost_local_tasks.clear()
    store.try_start(
        {
            "task_id": "job-fail",
            "status": "running",
            "runtime_profile": "desktop_power",
        }
    )
    mod._ghost_local_tasks["job-fail"] = MagicMock()

    monkeypatch.setattr(
        mod,
        "_run_ghost_process_with_cancel_watch",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    publish = MagicMock()
    monkeypatch.setattr(mod, "_publish_ghost_audit", publish)

    payload = mod.GhostRunRequest(content="do stuff")
    with pytest.raises(RuntimeError, match="boom"):
        await mod._run_ghost_job(task_id="job-fail", payload=payload, actor="tester")

    state = store.get()
    assert state is not None
    assert state["status"] == "failed"
    assert state["result"] == "boom"
    assert "job-fail" not in mod._ghost_local_tasks
    assert any(
        call.kwargs["action"] == "ghost.run.failed" for call in publish.mock_calls
    )


@pytest.mark.asyncio
async def test_run_ghost_job_updates_cancelled_state(tmp_path, monkeypatch):
    store = mod._GhostRunStateStore(tmp_path / "state.json")
    monkeypatch.setattr(mod, "_ghost_run_store", store)
    mod._ghost_local_tasks.clear()
    store.try_start(
        {
            "task_id": "job-cancel",
            "status": "running",
            "runtime_profile": "desktop_safe",
        }
    )
    mod._ghost_local_tasks["job-cancel"] = MagicMock()

    monkeypatch.setattr(
        mod,
        "_run_ghost_process_with_cancel_watch",
        AsyncMock(side_effect=asyncio.CancelledError),
    )
    publish = MagicMock()
    monkeypatch.setattr(mod, "_publish_ghost_audit", publish)

    payload = mod.GhostRunRequest(content="do stuff")
    with pytest.raises(asyncio.CancelledError):
        await mod._run_ghost_job(task_id="job-cancel", payload=payload, actor="tester")

    state = store.get()
    assert state is not None
    assert state["status"] == "cancelled"
    assert "job-cancel" not in mod._ghost_local_tasks
    assert any(
        call.kwargs["action"] == "ghost.run.cancelled" for call in publish.mock_calls
    )
