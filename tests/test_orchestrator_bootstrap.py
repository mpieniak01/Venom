"""Tests for orchestrator bootstrap modules: re-exports, events, middleware, kernel_manager."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# orchestrator.py – re-export module (backward-compat shim)
# ---------------------------------------------------------------------------


def test_orchestrator_reexport_module_exposes_orchestrator_class():
    """Importing from the re-export shim should work and expose Orchestrator."""
    import venom_core.core.orchestrator as orch_module

    from venom_core.core.orchestrator.orchestrator_core import (
        Orchestrator as DirectOrch,
    )

    assert orch_module.Orchestrator is DirectOrch


def test_orchestrator_reexport_module_exposes_constants():
    """Constants re-exported by the shim should match the package values."""
    import venom_core.core.orchestrator as orch_module

    from venom_core.core.orchestrator.constants import (
        COUNCIL_TASK_THRESHOLD,
        MAX_CONTEXT_CHARS,
        MAX_REPAIR_ATTEMPTS,
        SESSION_HISTORY_LIMIT,
    )

    assert orch_module.MAX_CONTEXT_CHARS == MAX_CONTEXT_CHARS
    assert orch_module.MAX_REPAIR_ATTEMPTS == MAX_REPAIR_ATTEMPTS
    assert orch_module.COUNCIL_TASK_THRESHOLD == COUNCIL_TASK_THRESHOLD
    assert orch_module.SESSION_HISTORY_LIMIT == SESSION_HISTORY_LIMIT


# ---------------------------------------------------------------------------
# orchestrator_events.py – None-tracer branches
# ---------------------------------------------------------------------------

from venom_core.core.orchestrator.orchestrator_events import (
    build_error_envelope,
    set_runtime_error,
    trace_llm_start,
    trace_step_async,
)


def test_trace_llm_start_noop_when_tracer_is_none():
    """trace_llm_start should return early without error when request_tracer is None."""
    orch = SimpleNamespace(request_tracer=None)
    # Should not raise; exercises the early-return branch (line 32)
    trace_llm_start(orch, uuid4(), "GENERAL_CHAT")


@pytest.mark.asyncio
async def test_trace_step_async_noop_when_tracer_is_none():
    """trace_step_async should return early without error when request_tracer is None."""
    orch = SimpleNamespace(request_tracer=None)
    # Exercises the early-return branch (line 47)
    await trace_step_async(orch, uuid4(), "Actor", "action", status="ok")


def test_set_runtime_error_skips_tracer_when_none():
    """set_runtime_error should update state_manager but skip tracer when it is None."""

    class DummyState:
        def __init__(self):
            self.last_update = None

        def update_context(self, task_id, payload):
            self.last_update = (task_id, payload)

    state = DummyState()
    orch = SimpleNamespace(state_manager=state, request_tracer=None)
    task_id = uuid4()
    envelope = {"error_code": "E1", "error_message": "boom"}

    # Exercises the 84->exit branch (tracer is None)
    set_runtime_error(orch, task_id, envelope)

    assert state.last_update is not None
    assert state.last_update[0] == task_id
    assert state.last_update[1]["llm_runtime"]["status"] == "error"
    assert state.last_update[1]["llm_runtime"]["error"] == envelope


def test_build_error_envelope_with_all_fields():
    """build_error_envelope should populate all fields when provided."""
    envelope = build_error_envelope(
        error_code="CODE",
        error_message="msg",
        error_details={"key": "value"},
        stage="execution",
        retryable=True,
        error_class="CustomClass",
    )
    assert envelope["error_code"] == "CODE"
    assert envelope["error_class"] == "CustomClass"
    assert envelope["error_message"] == "msg"
    assert envelope["error_details"] == {"key": "value"}
    assert envelope["stage"] == "execution"
    assert envelope["retryable"] is True


# ---------------------------------------------------------------------------
# middleware.py – Middleware class
# ---------------------------------------------------------------------------

from venom_core.core.orchestrator.middleware import Middleware


def test_middleware_init_stores_dependencies():
    """Middleware.__init__ should assign state_manager, broadcaster and tracer."""
    state = MagicMock()
    broadcaster = MagicMock()
    tracer = MagicMock()

    mw = Middleware(state_manager=state, event_broadcaster=broadcaster, request_tracer=tracer)

    assert mw.state_manager is state
    assert mw.event_broadcaster is broadcaster
    assert mw.request_tracer is tracer


def test_middleware_init_allows_none_optionals():
    """Middleware.__init__ should allow None for optional dependencies."""
    state = MagicMock()
    mw = Middleware(state_manager=state)

    assert mw.state_manager is state
    assert mw.event_broadcaster is None
    assert mw.request_tracer is None


@pytest.mark.asyncio
async def test_middleware_broadcast_event_calls_broadcaster():
    """broadcast_event should delegate to event_broadcaster when it is set."""

    class DummyBroadcaster:
        def __init__(self):
            self.calls = []

        async def broadcast_event(self, event_type, message, agent=None, data=None):
            self.calls.append((event_type, message, agent, data))

    broadcaster = DummyBroadcaster()
    state = MagicMock()
    mw = Middleware(state_manager=state, event_broadcaster=broadcaster)

    await mw.broadcast_event("EVT", "hello", agent="bot", data={"x": 1})

    assert len(broadcaster.calls) == 1
    assert broadcaster.calls[0] == ("EVT", "hello", "bot", {"x": 1})


@pytest.mark.asyncio
async def test_middleware_broadcast_event_noop_when_no_broadcaster():
    """broadcast_event should not raise when event_broadcaster is None."""
    mw = Middleware(state_manager=MagicMock())
    # Should complete without error
    await mw.broadcast_event("EVT", "msg")


def test_middleware_build_error_envelope_defaults():
    """build_error_envelope should use error_code as error_class when not given."""
    mw = Middleware(state_manager=MagicMock())
    env = mw.build_error_envelope(error_code="ERR_X", error_message="Something failed")

    assert env["error_code"] == "ERR_X"
    assert env["error_class"] == "ERR_X"
    assert env["error_message"] == "Something failed"
    assert env["error_details"] == {}
    assert env["stage"] is None
    assert env["retryable"] is False


def test_middleware_build_error_envelope_with_all_fields():
    """build_error_envelope should populate all provided fields."""
    mw = Middleware(state_manager=MagicMock())
    env = mw.build_error_envelope(
        error_code="ERR_Y",
        error_message="detail",
        error_details={"info": "x"},
        stage="dispatch",
        retryable=True,
        error_class="CustomErr",
    )

    assert env["error_class"] == "CustomErr"
    assert env["stage"] == "dispatch"
    assert env["retryable"] is True
    assert env["error_details"] == {"info": "x"}


def test_middleware_set_runtime_error_updates_state_and_tracer():
    """set_runtime_error should update state_manager and call tracer.set_error_metadata."""

    class DummyState:
        def __init__(self):
            self.updates = []

        def update_context(self, task_id, payload):
            self.updates.append((task_id, payload))

    class DummyTracer:
        def __init__(self):
            self.metadata_calls = []

        def set_error_metadata(self, task_id, envelope):
            self.metadata_calls.append((task_id, envelope))

    state = DummyState()
    tracer = DummyTracer()
    mw = Middleware(state_manager=state, request_tracer=tracer)
    task_id = uuid4()
    envelope = {"error_code": "E2", "error_message": "fail"}

    mw.set_runtime_error(task_id, envelope)

    assert len(state.updates) == 1
    assert state.updates[0][0] == task_id
    assert state.updates[0][1]["llm_runtime"]["status"] == "error"
    assert state.updates[0][1]["llm_runtime"]["error"] == envelope
    assert "last_error_at" in state.updates[0][1]["llm_runtime"]
    assert tracer.metadata_calls == [(task_id, envelope)]


def test_middleware_set_runtime_error_skips_tracer_when_none():
    """set_runtime_error should not raise when request_tracer is None."""

    class DummyState:
        def __init__(self):
            self.updates = []

        def update_context(self, task_id, payload):
            self.updates.append((task_id, payload))

    state = DummyState()
    mw = Middleware(state_manager=state)
    task_id = uuid4()
    envelope = {"error_code": "E3", "error_message": "no tracer"}

    mw.set_runtime_error(task_id, envelope)

    assert len(state.updates) == 1
    assert state.updates[0][1]["llm_runtime"]["error"] == envelope


# ---------------------------------------------------------------------------
# kernel_manager.py – KernelManager class
# ---------------------------------------------------------------------------

from venom_core.core.orchestrator.kernel_manager import KernelManager


def _make_runtime(config_hash: str = "hash-v1"):
    return SimpleNamespace(config_hash=config_hash)


def test_kernel_manager_init_stores_attributes(monkeypatch):
    """KernelManager.__init__ should store all injected dependencies."""
    monkeypatch.setattr(
        "venom_core.core.orchestrator.kernel_manager.get_active_llm_runtime",
        lambda: _make_runtime("hash-abc"),
    )

    dispatcher = MagicMock()
    broadcaster = MagicMock()
    node_mgr = MagicMock()

    km = KernelManager(
        task_dispatcher=dispatcher,
        event_broadcaster=broadcaster,
        node_manager=node_mgr,
    )

    assert km.task_dispatcher is dispatcher
    assert km.event_broadcaster is broadcaster
    assert km.node_manager is node_mgr
    assert km._kernel_config_hash == "hash-abc"


def test_kernel_manager_init_default_optionals(monkeypatch):
    """KernelManager.__init__ should default event_broadcaster and node_manager to None."""
    monkeypatch.setattr(
        "venom_core.core.orchestrator.kernel_manager.get_active_llm_runtime",
        lambda: _make_runtime("hash-xyz"),
    )

    dispatcher = MagicMock()
    km = KernelManager(task_dispatcher=dispatcher)

    assert km.event_broadcaster is None
    assert km.node_manager is None


def test_kernel_manager_refresh_kernel_rebuilds_dispatcher(monkeypatch):
    """refresh_kernel should create a new TaskDispatcher and update state."""
    initial_hash = "hash-old"
    new_hash = "hash-new"

    monkeypatch.setattr(
        "venom_core.core.orchestrator.kernel_manager.get_active_llm_runtime",
        lambda: _make_runtime(initial_hash),
    )

    fake_kernel = MagicMock()
    fake_builder = MagicMock()
    fake_builder.build_kernel.return_value = fake_kernel

    fake_dispatcher = MagicMock()
    fake_dispatcher.goal_store = "goal-store-obj"

    fake_new_dispatcher = MagicMock()
    FakeTaskDispatcher = MagicMock(return_value=fake_new_dispatcher)

    monkeypatch.setattr(
        "venom_core.core.orchestrator.kernel_manager.KernelBuilder",
        lambda: fake_builder,
    )
    monkeypatch.setattr(
        "venom_core.core.orchestrator.kernel_manager.get_active_llm_runtime",
        lambda: _make_runtime(new_hash),
    )

    km = KernelManager(task_dispatcher=fake_dispatcher)
    # Override after __init__ to ensure correct hash
    km._kernel_config_hash = initial_hash

    runtime_info = _make_runtime(new_hash)

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "venom_core.core.orchestrator.kernel_manager.get_active_llm_runtime",
            lambda: runtime_info,
        )
        # Patch the TaskDispatcher import inside refresh_kernel
        import venom_core.core.orchestrator.kernel_manager as km_module

        orig_dispatcher_cls = None
        import importlib
        import venom_core.core.dispatcher as dispatcher_module

        orig_cls = dispatcher_module.TaskDispatcher

        try:
            dispatcher_module.TaskDispatcher = FakeTaskDispatcher
            returned = km.refresh_kernel(runtime_info)
        finally:
            dispatcher_module.TaskDispatcher = orig_cls

    assert returned is fake_new_dispatcher
    assert km.task_dispatcher is fake_new_dispatcher
    assert km._kernel_config_hash == new_hash


def test_kernel_manager_refresh_kernel_if_needed_returns_true_on_hash_change(
    monkeypatch,
):
    """refresh_kernel_if_needed should refresh and return True when config hash changed."""
    monkeypatch.setattr(
        "venom_core.core.orchestrator.kernel_manager.get_active_llm_runtime",
        lambda: _make_runtime("hash-1"),
    )

    dispatcher = MagicMock()
    dispatcher.goal_store = None
    km = KernelManager(task_dispatcher=dispatcher)
    assert km._kernel_config_hash == "hash-1"

    # Simulate hash change
    new_runtime = _make_runtime("hash-2")
    monkeypatch.setattr(
        "venom_core.core.orchestrator.kernel_manager.get_active_llm_runtime",
        lambda: new_runtime,
    )

    fake_kernel = MagicMock()
    fake_builder = MagicMock()
    fake_builder.build_kernel.return_value = fake_kernel
    monkeypatch.setattr(
        "venom_core.core.orchestrator.kernel_manager.KernelBuilder",
        lambda: fake_builder,
    )

    fake_new_dispatcher = MagicMock()
    import venom_core.core.dispatcher as dispatcher_module

    orig_cls = dispatcher_module.TaskDispatcher
    dispatcher_module.TaskDispatcher = MagicMock(return_value=fake_new_dispatcher)
    try:
        result = km.refresh_kernel_if_needed()
    finally:
        dispatcher_module.TaskDispatcher = orig_cls

    assert result is True
    assert km._kernel_config_hash == "hash-2"


def test_kernel_manager_refresh_kernel_if_needed_returns_false_when_unchanged(
    monkeypatch,
):
    """refresh_kernel_if_needed should return False when config hash is unchanged."""
    monkeypatch.setattr(
        "venom_core.core.orchestrator.kernel_manager.get_active_llm_runtime",
        lambda: _make_runtime("hash-stable"),
    )

    km = KernelManager(task_dispatcher=MagicMock())
    # Same hash returned again
    result = km.refresh_kernel_if_needed()

    assert result is False
