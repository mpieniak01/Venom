"""Tests for FlowRouter, StreamingHandler, BackgroundScheduler (gaps), and Swarm."""

# ruff: noqa: E402

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from venom_core.core.flow_router import FlowRouter

# ---------------------------------------------------------------------------
# FlowRouter
# ---------------------------------------------------------------------------


class TestFlowRouterInit:
    def test_init_without_council_flow(self):
        """FlowRouter should default _council_flow to None."""
        router = FlowRouter()
        assert router._council_flow is None

    def test_init_with_council_flow(self):
        """FlowRouter should store provided council_flow."""
        council = MagicMock()
        router = FlowRouter(council_flow=council)
        assert router._council_flow is council

    def test_set_council_flow(self):
        """set_council_flow should update _council_flow."""
        router = FlowRouter()
        council = MagicMock()
        router.set_council_flow(council)
        assert router._council_flow is council


class TestFlowRouterShouldUseCouncil:
    def test_returns_false_when_no_council_flow(self):
        """should_use_council should return False when _council_flow is None."""
        router = FlowRouter()
        assert router.should_use_council("complex task", "GENERAL_CHAT") is False

    def test_delegates_to_council_flow(self):
        """should_use_council should delegate to _council_flow.should_use_council."""
        council = MagicMock()
        council.should_use_council.return_value = True
        router = FlowRouter(council_flow=council)
        result = router.should_use_council("content", "intent")
        assert result is True
        council.should_use_council.assert_called_once_with("content", "intent")

    def test_delegates_false_decision(self):
        """should_use_council should propagate False from council_flow."""
        council = MagicMock()
        council.should_use_council.return_value = False
        router = FlowRouter(council_flow=council)
        assert router.should_use_council("simple task", "TIME_REQUEST") is False


class TestFlowRouterDetermineFlow:
    def test_campaign_intent_routes_to_campaign(self):
        """START_CAMPAIGN should produce campaign flow."""
        router = FlowRouter()
        flow_name, meta = router.determine_flow("launch", "START_CAMPAIGN")
        assert flow_name == "campaign"
        assert meta["mode"] == "campaign"

    def test_help_intent_routes_to_help(self):
        """HELP_REQUEST should produce help flow."""
        router = FlowRouter()
        flow_name, meta = router.determine_flow("help me", "HELP_REQUEST")
        assert flow_name == "help"
        assert meta["mode"] == "help"

    def test_council_routes_to_council_when_enabled(self):
        """determine_flow should return council when should_use_council is True."""
        council = MagicMock()
        council.should_use_council.return_value = True
        router = FlowRouter(council_flow=council)
        flow_name, meta = router.determine_flow("complex", "GENERAL_CHAT")
        assert flow_name == "council"
        assert meta["mode"] == "council"

    def test_code_generation_routes_to_code_review(self):
        """CODE_GENERATION should produce code_review flow."""
        router = FlowRouter()
        flow_name, meta = router.determine_flow("write code", "CODE_GENERATION")
        assert flow_name == "code_review"
        assert meta["mode"] == "coder_critic"

    def test_complex_planning_routes_to_standard_architect(self):
        """COMPLEX_PLANNING should produce standard flow with architect mode."""
        router = FlowRouter()
        flow_name, meta = router.determine_flow("plan", "COMPLEX_PLANNING")
        assert flow_name == "standard"
        assert meta["mode"] == "architect"

    def test_unknown_intent_routes_to_standard(self):
        """Unknown intent should produce standard flow."""
        router = FlowRouter()
        flow_name, meta = router.determine_flow("task", "KNOWLEDGE_SEARCH")
        assert flow_name == "standard"
        assert meta["mode"] == "standard"
        assert meta["intent"] == "KNOWLEDGE_SEARCH"


# ---------------------------------------------------------------------------
# StreamingHandler
# ---------------------------------------------------------------------------

from venom_core.core.streaming_handler import StreamingHandler


class TestStreamingHandlerInit:
    def test_init_stores_state_manager_and_interval(self):
        """StreamingHandler should store state_manager and partial_emit_interval."""
        state = MagicMock()
        handler = StreamingHandler(state_manager=state, partial_emit_interval=0.5)
        assert handler.state_manager is state
        assert handler.partial_emit_interval == 0.5

    def test_init_default_interval(self):
        """StreamingHandler default partial_emit_interval should be 0.25."""
        state = MagicMock()
        handler = StreamingHandler(state_manager=state)
        assert handler.partial_emit_interval == 0.25


class TestStreamingHandlerShouldEmitPartial:
    def test_always_emits_before_first_chunk(self):
        """_should_emit_partial returns True when first_chunk_sent=False."""
        handler = StreamingHandler(state_manager=MagicMock())
        result = handler._should_emit_partial(
            first_chunk_sent=False, now=10.0, last_partial_emit=9.99
        )
        assert result is True

    def test_emits_after_interval_elapsed(self):
        """_should_emit_partial returns True when interval has elapsed."""
        handler = StreamingHandler(state_manager=MagicMock(), partial_emit_interval=0.1)
        result = handler._should_emit_partial(
            first_chunk_sent=True, now=10.2, last_partial_emit=10.0
        )
        assert result is True

    def test_does_not_emit_within_interval(self):
        """_should_emit_partial returns False when interval has NOT elapsed."""
        handler = StreamingHandler(state_manager=MagicMock(), partial_emit_interval=1.0)
        result = handler._should_emit_partial(
            first_chunk_sent=True, now=10.05, last_partial_emit=10.0
        )
        assert result is False


class TestStreamingHandlerEmitPartialUpdate:
    def test_emit_partial_update_calls_state_manager(self):
        """_emit_partial_update should call update_partial_result and update_context."""
        state = MagicMock()
        handler = StreamingHandler(state_manager=state)
        task_id = uuid4()
        now = time.perf_counter()

        handler._emit_partial_update(
            task_id=task_id,
            stream_buffer=["hello ", "world"],
            now=now,
            stream_start=now - 0.1,
            chunk_count=2,
        )

        state.update_partial_result.assert_called_once_with(task_id, "hello world")
        state.update_context.assert_called_once()
        ctx_call = state.update_context.call_args
        assert ctx_call[0][0] == task_id
        assert "streaming" in ctx_call[0][1]
        assert ctx_call[0][1]["streaming"]["chunk_count"] == 2


class TestStreamingHandlerHandleFirstChunk:
    def test_handle_first_chunk_logs_and_updates_context(self):
        """_handle_first_chunk should add_log and update_context for first token."""
        state = MagicMock()
        state.get_task.return_value = None
        handler = StreamingHandler(state_manager=state)
        task_id = uuid4()
        now = time.perf_counter()

        handler._handle_first_chunk(
            task_id=task_id,
            preview="Hello world",
            now=now,
            stream_start=now - 0.05,
            chunk_count=1,
            collector=None,
        )

        state.add_log.assert_called_once()
        assert state.update_context.call_count == 2  # first_token + streaming

    def test_handle_first_chunk_truncates_long_preview(self):
        """_handle_first_chunk should truncate preview longer than 200 chars."""
        state = MagicMock()
        state.get_task.return_value = None
        handler = StreamingHandler(state_manager=state)
        task_id = uuid4()
        long_preview = "x" * 300
        now = time.perf_counter()

        handler._handle_first_chunk(
            task_id=task_id,
            preview=long_preview,
            now=now,
            stream_start=now,
            chunk_count=1,
            collector=None,
        )

        log_msg = state.add_log.call_args[0][1]
        assert "..." in log_msg

    def test_handle_first_chunk_with_collector(self):
        """_handle_first_chunk should call collector.add_llm_first_token_sample when present."""
        state = MagicMock()
        state.get_task.return_value = None
        collector = MagicMock()
        handler = StreamingHandler(state_manager=state)
        task_id = uuid4()
        now = time.perf_counter()

        handler._handle_first_chunk(
            task_id=task_id,
            preview="Hi",
            now=now,
            stream_start=now - 0.01,
            chunk_count=1,
            collector=collector,
        )

        collector.add_llm_first_token_sample.assert_called_once()

    def test_handle_first_chunk_with_task_context_used(self):
        """_handle_first_chunk should serialize context_used when task is available."""
        state = MagicMock()
        context_used = MagicMock()
        context_used.model_dump.return_value = {"tokens": 100}
        task_mock = SimpleNamespace(context_used=context_used)
        state.get_task.return_value = task_mock
        handler = StreamingHandler(state_manager=state)
        task_id = uuid4()
        now = time.perf_counter()

        handler._handle_first_chunk(
            task_id=task_id,
            preview="Hi",
            now=now,
            stream_start=now,
            chunk_count=1,
            collector=None,
        )

        context_used.model_dump.assert_called_once()


class TestStreamingHandlerCreateStreamCallback:
    def test_callback_ignores_empty_text(self):
        """Stream callback should return early for empty text."""
        state = MagicMock()
        handler = StreamingHandler(state_manager=state, partial_emit_interval=100.0)
        task_id = uuid4()
        callback = handler.create_stream_callback(task_id)

        callback("")  # Should not update anything
        state.update_partial_result.assert_not_called()

    def test_callback_accumulates_and_emits_partial(self):
        """Stream callback should accumulate text and emit partial updates."""
        state = MagicMock()
        state.get_task.return_value = None
        handler = StreamingHandler(state_manager=state, partial_emit_interval=0.0)
        task_id = uuid4()
        callback = handler.create_stream_callback(task_id)

        callback("Hello")
        callback(" world")

        # Should have emitted partial updates
        assert state.update_partial_result.call_count >= 1

    def test_callback_captures_first_chunk(self):
        """Stream callback should handle first_chunk logic on non-empty first text."""
        state = MagicMock()
        state.get_task.return_value = None
        handler = StreamingHandler(state_manager=state, partial_emit_interval=100.0)
        task_id = uuid4()
        callback = handler.create_stream_callback(task_id)

        callback("First token")

        # add_log should be called for first chunk
        state.add_log.assert_called()


# ---------------------------------------------------------------------------
# BackgroundScheduler — uncovered gaps
# ---------------------------------------------------------------------------

from venom_core.core.scheduler import STATE_PAUSED, STATE_RUNNING, BackgroundScheduler


@pytest.fixture
def scheduler():
    """Create a BackgroundScheduler instance (not started)."""
    return BackgroundScheduler(allow_test_override=True)


class TestBackgroundSchedulerGetStatus:
    def test_get_status_when_stopped(self, scheduler):
        """get_status should return 'stopped' state when scheduler not started."""
        status = scheduler.get_status()
        assert status["is_running"] is False
        assert status["state"] == "stopped"

    @pytest.mark.asyncio
    async def test_get_status_when_running(self, scheduler):
        """get_status should return 'running' when scheduler is started."""
        await scheduler.start()
        try:
            status = scheduler.get_status()
            assert status["state"] == "running"
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_get_status_when_paused(self, scheduler):
        """get_status should return 'paused' when scheduler is started and paused."""
        await scheduler.start()
        scheduler.scheduler.pause()
        try:
            status = scheduler.get_status()
            assert status["state"] == "paused"
            assert status["paused"] is True
        finally:
            await scheduler.stop()


class TestBackgroundSchedulerPauseResumeJobs:
    @pytest.mark.asyncio
    async def test_pause_all_jobs_when_running(self, scheduler):
        """pause_all_jobs should pause the scheduler when it is running."""
        scheduler.scheduler.start()
        scheduler.is_running = True
        try:
            await scheduler.pause_all_jobs()
            assert scheduler.scheduler.state == STATE_PAUSED
        finally:
            scheduler.scheduler.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_pause_all_jobs_noop_when_not_running(self, scheduler):
        """pause_all_jobs should not raise when scheduler not running."""
        scheduler.is_running = False
        await scheduler.pause_all_jobs()  # Should not raise

    @pytest.mark.asyncio
    async def test_resume_all_jobs_after_pause(self, scheduler):
        """resume_all_jobs should resume a paused scheduler."""
        scheduler.scheduler.start()
        scheduler.scheduler.pause()
        scheduler.is_running = True
        try:
            await scheduler.resume_all_jobs()
            assert scheduler.scheduler.state == STATE_RUNNING
        finally:
            scheduler.scheduler.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_resume_all_jobs_noop_when_not_running(self, scheduler):
        """resume_all_jobs should not raise when scheduler not running."""
        scheduler.is_running = False
        await scheduler.resume_all_jobs()  # Should not raise

    @pytest.mark.asyncio
    async def test_pause_broadcasts_event_when_broadcaster_set(self, scheduler):
        """pause_all_jobs should broadcast when event_broadcaster is set."""
        broadcaster = MagicMock()
        broadcaster.broadcast_event = AsyncMock()
        scheduler.event_broadcaster = broadcaster
        scheduler.scheduler.start()
        scheduler.is_running = True
        try:
            await scheduler.pause_all_jobs()
            broadcaster.broadcast_event.assert_awaited_once()
        finally:
            scheduler.scheduler.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_resume_broadcasts_event_when_broadcaster_set(self, scheduler):
        """resume_all_jobs should broadcast when event_broadcaster is set."""
        broadcaster = MagicMock()
        broadcaster.broadcast_event = AsyncMock()
        scheduler.event_broadcaster = broadcaster
        scheduler.scheduler.start()
        scheduler.scheduler.pause()
        scheduler.is_running = True
        try:
            await scheduler.resume_all_jobs()
            broadcaster.broadcast_event.assert_awaited_once()
        finally:
            scheduler.scheduler.shutdown(wait=False)


class TestBackgroundSchedulerGetJobs:
    def test_get_jobs_returns_empty_when_no_jobs(self, scheduler):
        """get_jobs should return empty list when no jobs registered."""
        jobs = scheduler.get_jobs()
        assert isinstance(jobs, list)
        assert len(jobs) == 0

    @pytest.mark.asyncio
    async def test_get_jobs_with_registered_job(self, scheduler):
        """get_jobs should include job metadata when job is in registry."""
        await scheduler.start()
        try:

            def dummy_func():
                pass

            scheduler.add_interval_job(
                func=dummy_func,
                seconds=30,
                job_id="test_job",
                description="Test job",
            )
            jobs = scheduler.get_jobs()
            assert any(j["id"] == "test_job" for j in jobs)
            assert any(j.get("description") == "Test job" for j in jobs)
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_get_jobs_next_run_time_handles_datetime_attribute(self, scheduler):
        """get_jobs should handle datetime next_run_time attribute correctly."""
        await scheduler.start()
        try:

            def dummy_func():
                pass

            scheduler.add_interval_job(func=dummy_func, seconds=60, job_id="j1")
            jobs = scheduler.get_jobs()
            assert isinstance(jobs, list)
        finally:
            await scheduler.stop()


class TestBackgroundSchedulerGetJobStatus:
    def test_get_job_status_returns_none_for_unknown_job(self, scheduler):
        """get_job_status should return None when job doesn't exist."""
        result = scheduler.get_job_status("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_job_status_returns_status_for_known_job(self, scheduler):
        """get_job_status should return dict with job info for existing job."""
        await scheduler.start()
        try:

            def dummy_func():
                pass

            scheduler.add_interval_job(
                func=dummy_func,
                seconds=30,
                job_id="status_test",
                description="Status Test",
            )
            status = scheduler.get_job_status("status_test")
            assert status is not None
            assert status["id"] == "status_test"
            assert status.get("description") == "Status Test"
        finally:
            await scheduler.stop()


class TestBackgroundSchedulerStart:
    @pytest.mark.asyncio
    async def test_start_paused_noop_when_not_override(self, monkeypatch):
        """start should be noop when VENOM_PAUSE_BACKGROUND_TASKS=True and no override."""
        monkeypatch.setattr(
            "venom_core.core.scheduler.SETTINGS",
            SimpleNamespace(VENOM_PAUSE_BACKGROUND_TASKS=True),
        )
        sched = BackgroundScheduler(allow_test_override=False)
        await sched.start()
        assert sched.is_running is False

    @pytest.mark.asyncio
    async def test_start_broadcasts_when_broadcaster_set(self, monkeypatch):
        """start should broadcast when event_broadcaster is set."""
        monkeypatch.setattr(
            "venom_core.core.scheduler.SETTINGS",
            SimpleNamespace(VENOM_PAUSE_BACKGROUND_TASKS=False),
        )
        broadcaster = MagicMock()
        broadcaster.broadcast_event = AsyncMock()
        sched = BackgroundScheduler(allow_test_override=True)
        sched.event_broadcaster = broadcaster
        await sched.start()
        assert sched.is_running is True
        broadcaster.broadcast_event.assert_awaited_once()
        sched.scheduler.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_stop_broadcasts_when_broadcaster_set(self, monkeypatch):
        """stop should broadcast when event_broadcaster is set."""
        monkeypatch.setattr(
            "venom_core.core.scheduler.SETTINGS",
            SimpleNamespace(VENOM_PAUSE_BACKGROUND_TASKS=False),
        )
        broadcaster = MagicMock()
        broadcaster.broadcast_event = AsyncMock()
        sched = BackgroundScheduler(allow_test_override=True)
        sched.event_broadcaster = broadcaster
        await sched.start()
        broadcaster.broadcast_event.reset_mock()
        await sched.stop()
        broadcaster.broadcast_event.assert_awaited_once()


class TestBackgroundSchedulerScheduleMethods:
    @pytest.mark.asyncio
    async def test_schedule_daily_standup_adds_cron_job(self, scheduler):
        """schedule_daily_standup should add a cron job."""
        await scheduler.start()
        try:
            executive = MagicMock()
            job_id = scheduler.schedule_daily_standup(executive, hour=9, minute=0)
            assert job_id == "daily_standup"
            jobs = scheduler.get_jobs()
            assert any(j["id"] == "daily_standup" for j in jobs)
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_schedule_nightly_dreaming_adds_cron_job(self, scheduler):
        """schedule_nightly_dreaming should add a cron job."""
        await scheduler.start()
        try:
            dream_engine = MagicMock()
            job_id = scheduler.schedule_nightly_dreaming(
                dream_engine, start_hour=2, end_hour=6
            )
            assert job_id == "nightly_dreaming"
            jobs = scheduler.get_jobs()
            assert any(j["id"] == "nightly_dreaming" for j in jobs)
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_schedule_idle_dreaming_adds_interval_job(self, scheduler):
        """schedule_idle_dreaming should add an interval job."""
        await scheduler.start()
        try:
            dream_engine = MagicMock()
            job_id = scheduler.schedule_idle_dreaming(
                dream_engine, check_interval_minutes=5
            )
            assert job_id == "idle_dreaming_check"
            jobs = scheduler.get_jobs()
            assert any(j["id"] == "idle_dreaming_check" for j in jobs)
        finally:
            await scheduler.stop()


# ---------------------------------------------------------------------------
# Swarm — uncovered gaps (extract_venom_tools, _is_kernel_method)
# ---------------------------------------------------------------------------

import venom_core.core.swarm as swarm_mod
from venom_core.core.swarm import (
    VenomAgent,
    create_venom_agent_wrapper,
    extract_venom_tools,
)


class DummyAgent:
    SYSTEM_PROMPT = "dummy prompt"

    def __init__(self, kernel=None):
        if kernel is not None:
            self.kernel = kernel

    async def process(self, message: str) -> str:
        return f"processed: {message}"


class DummyKernel:
    def __init__(self, plugins=None):
        self.plugins = plugins or {}


class TestExtractVenomTools:
    def test_extract_tools_returns_empty_when_no_kernel(self):
        """extract_venom_tools should return empty list when agent has no kernel."""
        agent = DummyAgent()  # no kernel attribute
        tools = extract_venom_tools(agent)
        assert tools == []

    def test_extract_tools_returns_empty_when_no_plugins(self):
        """extract_venom_tools should return empty list when kernel has no plugins."""
        kernel = DummyKernel(plugins={})
        agent = DummyAgent(kernel=kernel)
        tools = extract_venom_tools(agent)
        assert tools == []

    def test_extract_tools_with_callable_functions(self):
        """extract_venom_tools should produce tool defs for callable plugin members."""

        class DummyPlugin:
            def do_something(self) -> str:
                """Does something."""
                return "result"

        kernel = DummyKernel(plugins={"MyPlugin": DummyPlugin()})
        agent = DummyAgent(kernel=kernel)
        tools = extract_venom_tools(agent)
        # Should find at least do_something
        tool_names = [t["function"]["name"] for t in tools]
        assert any("do_something" in name for name in tool_names)
        # Each entry should follow schema
        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]

    def test_extract_tools_handles_kernel_error_gracefully(self):
        """extract_venom_tools should catch exceptions and return empty list."""

        class ErrorKernel:
            @property
            def plugins(self):
                raise RuntimeError("kernel broken")

        agent = DummyAgent(kernel=ErrorKernel())
        tools = extract_venom_tools(agent)
        assert tools == []

    def test_extract_tools_skips_private_functions(self):
        """extract_venom_tools should skip members starting with '_'."""

        class DummyPlugin:
            def _private_func(self):
                return "private"

            def public_func(self):
                return "public"

        kernel = DummyKernel(plugins={"Plug": DummyPlugin()})
        agent = DummyAgent(kernel=kernel)
        tools = extract_venom_tools(agent)
        tool_names = [t["function"]["name"] for t in tools]
        assert not any("_private_func" in name for name in tool_names)


class TestVenomAgentIsKernelMethod:
    def _make_venom_agent(self, monkeypatch):
        """Create a VenomAgent with stubbed registration."""
        inner_agent = DummyAgent(kernel=DummyKernel())
        monkeypatch.setattr(
            swarm_mod.VenomAgent, "_register_venom_functions", lambda self: None
        )
        return VenomAgent(
            name="TestAgent",
            venom_agent=inner_agent,
            system_message="test",
        )

    def test_is_kernel_method_returns_false_for_private(self, monkeypatch):
        """_is_kernel_method should return False for private members."""
        va = self._make_venom_agent(monkeypatch)

        class MockPlugin:
            def _private_func(self):
                pass

        plugin = MockPlugin()
        assert (
            va._is_kernel_method(plugin, "_private_func", plugin._private_func) is False
        )

    def test_is_kernel_method_returns_false_when_not_in_class_dict(self, monkeypatch):
        """_is_kernel_method should return False when method not in class __dict__."""
        va = self._make_venom_agent(monkeypatch)

        class MockPlugin:
            pass

        plugin = MockPlugin()

        def not_in_class_dict():
            pass

        assert va._is_kernel_method(plugin, "some_func", not_in_class_dict) is False

    def test_is_kernel_method_returns_true_for_kernel_decorated(self, monkeypatch):
        """_is_kernel_method should return True for methods with __kernel_function__."""
        va = self._make_venom_agent(monkeypatch)

        class MockPlugin:
            def my_func(self):
                pass

        MockPlugin.my_func.__kernel_function__ = True
        plugin = MockPlugin()
        assert va._is_kernel_method(plugin, "my_func", plugin.my_func) is True


class TestCreateVenomAgentWrapper:
    def test_uses_agent_system_prompt_when_not_provided(self, monkeypatch):
        """create_venom_agent_wrapper should use agent.SYSTEM_PROMPT when system_message=None."""
        monkeypatch.setattr(
            swarm_mod.VenomAgent, "_register_venom_functions", lambda self: None
        )
        agent = DummyAgent(kernel=DummyKernel())
        wrapper = create_venom_agent_wrapper(agent, "MyAgent")
        assert wrapper.system_message == "dummy prompt"

    def test_uses_default_prompt_when_agent_has_no_system_prompt(self, monkeypatch):
        """create_venom_agent_wrapper should fallback to generic prompt."""
        monkeypatch.setattr(
            swarm_mod.VenomAgent, "_register_venom_functions", lambda self: None
        )
        monkeypatch.delattr(DummyAgent, "SYSTEM_PROMPT", raising=False)
        agent = DummyAgent(kernel=DummyKernel())
        wrapper = create_venom_agent_wrapper(agent, "GenAgent")
        assert "GenAgent" in wrapper.system_message

    def test_uses_provided_system_message(self, monkeypatch):
        """create_venom_agent_wrapper should use provided system_message."""
        monkeypatch.setattr(
            swarm_mod.VenomAgent, "_register_venom_functions", lambda self: None
        )
        agent = DummyAgent(kernel=DummyKernel())
        wrapper = create_venom_agent_wrapper(
            agent, "Agent", system_message="Custom prompt"
        )
        assert wrapper.system_message == "Custom prompt"
