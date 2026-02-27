"""Tests for task_pipeline: TaskValidator, ResultProcessor, ExecutionStrategy, ContextBuilder."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from venom_core.core.models import TaskRequest
from venom_core.core.orchestrator.task_pipeline.context_builder import ContextBuilder
from venom_core.core.orchestrator.task_pipeline.execution_strategy import (
    ExecutionStrategy,
)
from venom_core.core.orchestrator.task_pipeline.result_processor import ResultProcessor
from venom_core.core.orchestrator.task_pipeline.task_validator import TaskValidator

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _make_orch(
    *,
    tracer=None,
    dispatcher_kernel=None,
    dispatcher_agent_map=None,
    session_id_result=None,
    store_lesson=True,
    should_log_learning=True,
    should_use_council=False,
    campaign_flow=None,
    build_error_envelope_fn=None,
    set_runtime_error_fn=None,
):
    """Return a minimal namespace that satisfies the task_pipeline classes."""

    errors_set = {}

    def default_build_error(
        *,
        error_code,
        error_message,
        error_details=None,
        stage=None,
        retryable=False,
        error_class=None,
    ):
        return {
            "error_code": error_code,
            "error_message": error_message,
            "error_details": error_details or {},
            "stage": stage,
            "retryable": retryable,
            "error_class": error_class or error_code,
        }

    def default_set_runtime_error(task_id, envelope):
        errors_set[task_id] = envelope

    state = SimpleNamespace(
        logs=[],
        updates=[],
        statuses=[],
        task=None,
        add_log=lambda tid, msg: None,
        update_context=lambda tid, payload: None,
        update_status=AsyncMock(),
        get_task=lambda tid: None,
    )

    dispatcher = SimpleNamespace(
        kernel=dispatcher_kernel,
        agent_map=dispatcher_agent_map or {},
        goal_store=None,
        dispatch=AsyncMock(return_value="dispatch_result"),
    )

    lessons_mgr = SimpleNamespace(
        should_log_learning=lambda *a, **kw: should_log_learning,
        append_learning_log=MagicMock(),
        save_task_lesson=AsyncMock(),
    )

    session_handler = SimpleNamespace(
        _memory_upsert=MagicMock(),
        session_store=None,
    )

    orch = SimpleNamespace(
        state_manager=state,
        request_tracer=tracer,
        task_dispatcher=dispatcher,
        lessons_manager=lessons_mgr,
        session_handler=session_handler,
        _campaign_flow=campaign_flow,
        _build_error_envelope=build_error_envelope_fn or default_build_error,
        _set_runtime_error=set_runtime_error_fn or default_set_runtime_error,
        _should_store_lesson=lambda *a, **kw: store_lesson,
        _should_use_council=lambda *a, **kw: should_use_council,
        _trace_llm_start=MagicMock(),
        _append_session_history=MagicMock(),
        _broadcast_event=AsyncMock(),
        _apply_preferred_language=AsyncMock(
            side_effect=lambda tid, req, result: result
        ),
        run_council=AsyncMock(return_value="council_result"),
        _code_generation_with_review=AsyncMock(return_value="code_result"),
        _generate_help_response=AsyncMock(return_value="help_result"),
        task_manager=SimpleNamespace(),
        submit_task=AsyncMock(),
        event_broadcaster=None,
    )
    orch._errors_set = errors_set
    return orch


# ---------------------------------------------------------------------------
# TaskValidator
# ---------------------------------------------------------------------------


class TestTaskValidatorForcedTool:
    def test_validate_forced_tool_raises_when_forced_tool_without_intent(self):
        """validate_forced_tool should raise RuntimeError when forced_tool set but no intent."""
        orch = _make_orch()
        validator = TaskValidator(orch)
        task_id = uuid4()

        with pytest.raises(RuntimeError, match="forced_tool_unknown"):
            validator.validate_forced_tool(task_id, "browser", None)

        # Error envelope should be set
        assert task_id in orch._errors_set
        assert orch._errors_set[task_id]["error_code"] == "forced_tool_unknown"

    def test_validate_forced_tool_ok_when_no_forced_tool(self):
        """validate_forced_tool should do nothing when forced_tool is None."""
        orch = _make_orch()
        validator = TaskValidator(orch)
        # Should not raise
        validator.validate_forced_tool(uuid4(), None, None)
        validator.validate_forced_tool(uuid4(), None, "GENERAL_CHAT")

    def test_validate_forced_tool_ok_when_both_tool_and_intent_provided(self):
        """validate_forced_tool should not raise when forced_intent is present."""
        orch = _make_orch()
        validator = TaskValidator(orch)
        # Should not raise
        validator.validate_forced_tool(uuid4(), "git", "VERSION_CONTROL")


class TestTaskValidatorCapabilities:
    def test_validate_capabilities_raises_when_kernel_required_but_missing(self):
        """validate_capabilities should raise RuntimeError when kernel required but missing."""
        orch = _make_orch(dispatcher_kernel=None)
        tracer = MagicMock()
        orch.request_tracer = tracer
        validator = TaskValidator(orch)
        task_id = uuid4()

        with pytest.raises(RuntimeError, match="execution_contract_violation"):
            validator.validate_capabilities(
                task_id, kernel_required=True, tool_required=False
            )

        assert task_id in orch._errors_set
        assert orch._errors_set[task_id]["error_code"] == "execution_contract_violation"
        # Tracer should log multiple steps
        assert tracer.add_step.call_count >= 3

    def test_validate_capabilities_ok_when_kernel_not_required(self):
        """validate_capabilities should not raise when kernel_required=False."""
        orch = _make_orch(dispatcher_kernel=None)
        validator = TaskValidator(orch)
        # Should not raise
        validator.validate_capabilities(
            uuid4(), kernel_required=False, tool_required=True
        )

    def test_validate_capabilities_ok_when_kernel_present(self):
        """validate_capabilities should not raise when kernel exists."""
        orch = _make_orch(dispatcher_kernel=MagicMock())
        validator = TaskValidator(orch)
        # Should not raise
        validator.validate_capabilities(
            uuid4(), kernel_required=True, tool_required=False
        )

    def test_validate_capabilities_logs_tracer_step_on_success(self):
        """validate_capabilities should add a tracer step on success path."""
        tracer = MagicMock()
        orch = _make_orch(dispatcher_kernel=MagicMock())
        orch.request_tracer = tracer
        validator = TaskValidator(orch)
        task_id = uuid4()

        validator.validate_capabilities(
            task_id, kernel_required=True, tool_required=True
        )

        tracer.add_step.assert_called_once()
        call_args = tracer.add_step.call_args
        assert call_args[0][2] == "requirements_resolved"

    def test_validate_capabilities_no_tracer_no_crash(self):
        """validate_capabilities should not crash when request_tracer is None."""
        orch = _make_orch(dispatcher_kernel=None)
        orch.request_tracer = None
        validator = TaskValidator(orch)
        task_id = uuid4()

        with pytest.raises(RuntimeError):
            validator.validate_capabilities(
                task_id, kernel_required=True, tool_required=False
            )


class TestTaskValidatorRouting:
    def _make_runtime(self, provider="ollama", config_hash="h1", runtime_id=None):
        return SimpleNamespace(
            provider=provider,
            model_name="llama3",
            endpoint="http://localhost:11434",
            service_type="local",
            config_hash=config_hash,
            runtime_id=runtime_id,
        )

    def test_validate_routing_raises_for_onnx_runtime(self, monkeypatch):
        """validate_routing should raise for ONNX provider."""
        runtime = self._make_runtime(provider="onnx")
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.get_active_llm_runtime",
            lambda: runtime,
        )
        orch = _make_orch()
        validator = TaskValidator(orch)
        task_id = uuid4()

        with pytest.raises(RuntimeError, match="runtime_not_supported"):
            validator.validate_routing(task_id, TaskRequest(content="x"), None)

        assert orch._errors_set[task_id]["error_code"] == "runtime_not_supported"

    def test_validate_routing_raises_on_provider_mismatch(self, monkeypatch):
        """validate_routing should raise when forced provider doesn't match active."""
        runtime = self._make_runtime(provider="ollama")
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.get_active_llm_runtime",
            lambda: runtime,
        )
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.normalize_forced_provider",
            lambda v: v,
        )
        orch = _make_orch()
        validator = TaskValidator(orch)
        task_id = uuid4()

        with pytest.raises(RuntimeError, match="forced_provider_mismatch"):
            validator.validate_routing(task_id, TaskRequest(content="x"), "openai")

        assert orch._errors_set[task_id]["error_code"] == "forced_provider_mismatch"

    def test_validate_routing_raises_on_hash_mismatch(self, monkeypatch):
        """validate_routing should raise when config hash doesn't match expected."""
        runtime = self._make_runtime(provider="ollama", config_hash="actual-hash")
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.get_active_llm_runtime",
            lambda: runtime,
        )
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.normalize_forced_provider",
            lambda v: v,
        )
        orch = _make_orch()
        tracer = MagicMock()
        orch.request_tracer = tracer
        validator = TaskValidator(orch)
        task_id = uuid4()
        request = TaskRequest(content="x", expected_config_hash="expected-hash")

        with pytest.raises(RuntimeError, match="routing_mismatch"):
            validator.validate_routing(task_id, request, None)

        assert orch._errors_set[task_id]["error_code"] == "routing_mismatch"
        mismatch_calls = [
            c for c in tracer.add_step.call_args_list if "routing_mismatch" in str(c)
        ]
        assert mismatch_calls

    def test_validate_routing_raises_on_runtime_id_mismatch(self, monkeypatch):
        """validate_routing should raise when runtime_id doesn't match expected."""
        runtime = self._make_runtime(provider="ollama", runtime_id="runtime-actual")
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.get_active_llm_runtime",
            lambda: runtime,
        )
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.normalize_forced_provider",
            lambda v: v,
        )
        orch = _make_orch()
        orch.request_tracer = None
        validator = TaskValidator(orch)
        task_id = uuid4()
        request = TaskRequest(content="x", expected_runtime_id="runtime-expected")

        with pytest.raises(RuntimeError, match="routing_mismatch"):
            validator.validate_routing(task_id, request, None)

    def test_validate_routing_ok_when_hashes_match(self, monkeypatch):
        """validate_routing should pass silently when hashes match."""
        runtime = self._make_runtime(provider="ollama", config_hash="good-hash")
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.get_active_llm_runtime",
            lambda: runtime,
        )
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.normalize_forced_provider",
            lambda v: v,
        )
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.SETTINGS",
            SimpleNamespace(LLM_CONFIG_HASH="good-hash"),
        )
        orch = _make_orch()
        orch.request_tracer = None
        validator = TaskValidator(orch)
        task_id = uuid4()
        request = TaskRequest(content="x")
        # Should not raise
        validator.validate_routing(task_id, request, None)


# ---------------------------------------------------------------------------
# ResultProcessor
# ---------------------------------------------------------------------------


class TestResultProcessorExtractErrorDetails:
    def test_extract_error_details_with_none_request_and_context(self):
        """_extract_error_details should handle None request and context gracefully."""
        orch = _make_orch()
        rp = ResultProcessor(orch)
        details = rp._extract_error_details(ValueError("boom"), None, None)
        assert details["exception"] == "ValueError"
        assert "prompt_preview" not in details

    def test_extract_error_details_with_request_content(self):
        """_extract_error_details should add prompt_preview from request.content."""
        orch = _make_orch()
        rp = ResultProcessor(orch)
        request = TaskRequest(content="some prompt text")
        details = rp._extract_error_details(ValueError("err"), request, None)
        assert "prompt_preview" in details
        assert "some prompt text" in details["prompt_preview"]

    def test_extract_error_details_with_long_content_truncated(self):
        """_extract_error_details should truncate long request content."""
        orch = _make_orch()
        rp = ResultProcessor(orch)
        long_content = "x" * 500
        request = TaskRequest(content=long_content)
        details = rp._extract_error_details(ValueError("err"), request, None)
        assert details["prompt_preview"].endswith("...")

    def test_extract_error_details_with_context(self):
        """_extract_error_details should add prompt_context and truncated flag."""
        orch = _make_orch()
        rp = ResultProcessor(orch)
        details = rp._extract_error_details(ValueError("err"), None, "short context")
        assert details["prompt_context"] == "short context"
        assert details["prompt_context_truncated"] is False

    def test_extract_error_details_with_long_context_truncated(self):
        """_extract_error_details should truncate context over 4000 chars."""
        orch = _make_orch()
        rp = ResultProcessor(orch)
        long_ctx = "a" * 5000
        details = rp._extract_error_details(ValueError("err"), None, long_ctx)
        assert details["prompt_context"].endswith("...(truncated)")
        assert details["prompt_context_truncated"] is True

    def test_extract_error_details_token_error_raw(self):
        """_extract_error_details should capture raw token error string."""
        orch = _make_orch()
        rp = ResultProcessor(orch)
        exc = ValueError("Too many input tokens in request")
        details = rp._extract_error_details(exc, None, None)
        assert "raw_token_error" in details


@pytest.mark.asyncio
class TestResultProcessorProcessError:
    async def test_process_error_updates_status_failed(self):
        """process_error should set task status to FAILED."""
        orch = _make_orch()
        rp = ResultProcessor(orch)
        task_id = uuid4()
        request = TaskRequest(content="x")

        await rp.process_error(task_id, RuntimeError("oops"), request)

        orch.state_manager.update_status.assert_awaited_once()
        call_args = orch.state_manager.update_status.call_args
        from venom_core.core.models import TaskStatus

        assert call_args[0][1] == TaskStatus.FAILED

    async def test_process_error_broadcasts_task_failed(self):
        """process_error should broadcast TASK_FAILED event."""
        orch = _make_orch()
        rp = ResultProcessor(orch)
        task_id = uuid4()

        await rp.process_error(task_id, RuntimeError("oops"), None)

        orch._broadcast_event.assert_awaited_once()
        call_args = orch._broadcast_event.call_args
        assert call_args[1]["event_type"] == "TASK_FAILED"

    async def test_process_error_sets_error_envelope_when_no_existing(self):
        """process_error should set error envelope when none exists in context."""
        orch = _make_orch()
        rp = ResultProcessor(orch)
        task_id = uuid4()

        await rp.process_error(task_id, ValueError("fail"), TaskRequest(content="x"))

        assert task_id in orch._errors_set
        assert orch._errors_set[task_id]["error_code"] == "agent_error"

    async def test_process_error_skips_envelope_when_existing_error_code(self):
        """process_error should skip building envelope when existing error already set."""
        existing_envelope = {"error_code": "forced_tool_unknown"}
        task_mock = SimpleNamespace(
            context_history={"llm_runtime": {"error": existing_envelope}}
        )
        orch = _make_orch()
        orch.state_manager.get_task = lambda tid: task_mock
        set_calls = []
        orch._set_runtime_error = lambda tid, env: set_calls.append(env)
        rp = ResultProcessor(orch)
        task_id = uuid4()

        await rp.process_error(task_id, ValueError("fail"), None)

        # Should NOT add a new envelope since one already exists
        assert not set_calls

    async def test_process_error_updates_tracer_when_present(self):
        """process_error should update tracer status to FAILED."""
        tracer = MagicMock()
        orch = _make_orch()
        orch.request_tracer = tracer
        rp = ResultProcessor(orch)
        task_id = uuid4()

        await rp.process_error(task_id, RuntimeError("err"), None)

        from venom_core.core.tracer import TraceStatus

        tracer.update_status.assert_called_once_with(task_id, TraceStatus.FAILED)


@pytest.mark.asyncio
class TestResultProcessorProcessSuccess:
    async def test_process_success_marks_task_completed(self):
        """process_success should call update_status with COMPLETED."""
        agent = MagicMock()
        agent.__class__.__name__ = "MockAgent"
        orch = _make_orch(dispatcher_agent_map={"GENERAL_CHAT": agent})
        rp = ResultProcessor(orch)
        task_id = uuid4()
        request = TaskRequest(content="hello", session_id="s1")

        await rp.process_success(
            task_id, "result", "GENERAL_CHAT", "ctx", request, False
        )

        orch.state_manager.update_status.assert_awaited_once()
        from venom_core.core.models import TaskStatus

        assert orch.state_manager.update_status.call_args[0][1] == TaskStatus.COMPLETED

    async def test_process_success_broadcasts_task_completed(self):
        """process_success should broadcast TASK_COMPLETED event."""
        orch = _make_orch(dispatcher_agent_map={"GENERAL_CHAT": None})
        rp = ResultProcessor(orch)
        task_id = uuid4()
        request = TaskRequest(content="hello")

        await rp.process_success(
            task_id, "result", "GENERAL_CHAT", "ctx", request, False
        )

        orch._broadcast_event.assert_awaited()
        event_types = [c[1]["event_type"] for c in orch._broadcast_event.call_args_list]
        assert "TASK_COMPLETED" in event_types

    async def test_process_success_updates_tracer_when_present(self):
        """process_success should update tracer to COMPLETED."""
        tracer = MagicMock()
        orch = _make_orch()
        orch.request_tracer = tracer
        rp = ResultProcessor(orch)
        task_id = uuid4()
        request = TaskRequest(content="hi")

        await rp.process_success(
            task_id, "result", "GENERAL_CHAT", "ctx", request, False
        )

        from venom_core.core.tracer import TraceStatus

        tracer.update_status.assert_called_with(task_id, TraceStatus.COMPLETED)

    async def test_process_success_saves_lesson_when_should_store(self):
        """process_success should save lesson when _should_store_lesson returns True."""
        orch = _make_orch(store_lesson=True)
        rp = ResultProcessor(orch)
        task_id = uuid4()
        request = TaskRequest(content="hi")

        await rp.process_success(
            task_id, "result", "GENERAL_CHAT", "ctx", request, False
        )

        orch.lessons_manager.save_task_lesson.assert_awaited_once()

    async def test_process_success_skips_lesson_when_disabled(self):
        """process_success should not save lesson when _should_store_lesson returns False."""
        orch = _make_orch(store_lesson=False)
        rp = ResultProcessor(orch)
        task_id = uuid4()
        request = TaskRequest(content="hi")

        await rp.process_success(
            task_id, "result", "GENERAL_CHAT", "ctx", request, False
        )

        orch.lessons_manager.save_task_lesson.assert_not_awaited()

    async def test_process_success_appends_learning_log_when_needed(self):
        """process_success should call append_learning_log when should_log_learning returns True."""
        orch = _make_orch(should_log_learning=True)
        rp = ResultProcessor(orch)
        task_id = uuid4()
        request = TaskRequest(content="hi")

        await rp.process_success(
            task_id, "result", "GENERAL_CHAT", "ctx", request, False
        )

        orch.lessons_manager.append_learning_log.assert_called_once()

    async def test_process_success_memory_upsert_when_session_id_and_result(self):
        """process_success should call _memory_upsert when session_id and result present."""
        orch = _make_orch()
        rp = ResultProcessor(orch)
        task_id = uuid4()
        request = TaskRequest(content="hi", session_id="sess-1")

        await rp.process_success(
            task_id, "result text", "GENERAL_CHAT", "ctx", request, False
        )

        orch.session_handler._memory_upsert.assert_called_once()

    async def test_log_agent_action_formats_dict_result(self):
        """_log_agent_action should JSON-format dict results in broadcast."""
        orch = _make_orch()
        orch.request_tracer = None
        rp = ResultProcessor(orch)
        task_id = uuid4()
        result = {"key": "value", "count": 3}

        await rp._log_agent_action(task_id, "TestAgent", "GENERAL_CHAT", result)

        orch._broadcast_event.assert_awaited_once()
        msg = orch._broadcast_event.call_args[1]["message"]
        assert '"key"' in msg

    async def test_log_agent_action_skips_broadcast_for_empty_result(self):
        """_log_agent_action should not broadcast when formatted result is empty."""
        orch = _make_orch()
        orch.request_tracer = None
        rp = ResultProcessor(orch)
        task_id = uuid4()

        await rp._log_agent_action(task_id, "TestAgent", "GENERAL_CHAT", "  ")

        orch._broadcast_event.assert_not_awaited()


# ---------------------------------------------------------------------------
# ExecutionStrategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExecutionStrategy:
    async def test_execute_start_campaign_creates_flow_and_returns_summary(
        self, monkeypatch
    ):
        """execute should route START_CAMPAIGN intent to campaign mode."""
        campaign_result = {"summary": "campaign done"}
        campaign_flow = AsyncMock()
        campaign_flow.execute = AsyncMock(return_value=campaign_result)

        orch = _make_orch()
        orch.request_tracer = None
        orch._campaign_flow = campaign_flow

        strategy = ExecutionStrategy(orch)
        result = await strategy.execute(
            uuid4(), "START_CAMPAIGN", "ctx", TaskRequest(content="launch")
        )
        assert result == "campaign done"

    async def test_execute_start_campaign_creates_flow_when_none(self, monkeypatch):
        """execute should create CampaignFlow when _campaign_flow is None."""
        orch = _make_orch()
        orch.request_tracer = None
        orch._campaign_flow = None

        fake_campaign_result = {"summary": "ok"}
        fake_flow = AsyncMock()
        fake_flow.execute = AsyncMock(return_value=fake_campaign_result)

        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.execution_strategy.CampaignFlow",
            lambda **kwargs: fake_flow,
        )

        strategy = ExecutionStrategy(orch)
        result = await strategy.execute(
            uuid4(), "START_CAMPAIGN", "ctx", TaskRequest(content="launch")
        )
        assert result == "ok"
        # Flow should now be set
        assert orch._campaign_flow is fake_flow

    async def test_execute_help_request_returns_help_response(self):
        """execute should route HELP_REQUEST intent to help response."""
        orch = _make_orch()
        orch.request_tracer = None
        strategy = ExecutionStrategy(orch)

        result = await strategy.execute(
            uuid4(), "HELP_REQUEST", "ctx", TaskRequest(content="help")
        )
        assert result == "help_result"
        orch._generate_help_response.assert_awaited_once()

    async def test_execute_council_when_should_use_council(self):
        """execute should route to council when _should_use_council returns True."""
        orch = _make_orch(should_use_council=True)
        orch.request_tracer = None
        strategy = ExecutionStrategy(orch)

        result = await strategy.execute(
            uuid4(), "GENERAL_CHAT", "ctx", TaskRequest(content="complex question")
        )
        assert result == "council_result"
        orch.run_council.assert_awaited_once()

    async def test_execute_code_generation_intent(self):
        """execute should route CODE_GENERATION intent to code review loop."""
        orch = _make_orch(should_use_council=False)
        orch.request_tracer = None
        strategy = ExecutionStrategy(orch)

        result = await strategy.execute(
            uuid4(), "CODE_GENERATION", "ctx", TaskRequest(content="write code")
        )
        assert result == "code_result"
        orch._code_generation_with_review.assert_awaited_once()

    async def test_execute_complex_planning_with_generation_params(self):
        """execute should dispatch COMPLEX_PLANNING with generation_params when provided."""
        orch = _make_orch(should_use_council=False)
        orch.request_tracer = None
        strategy = ExecutionStrategy(orch)
        task_id = uuid4()
        params = {"temperature": 0.5}
        request = TaskRequest(content="plan", generation_params=params)

        result = await strategy.execute(task_id, "COMPLEX_PLANNING", "ctx", request)

        assert result == "dispatch_result"
        orch.task_dispatcher.dispatch.assert_awaited_once_with(
            "COMPLEX_PLANNING", "ctx", generation_params=params
        )

    async def test_execute_complex_planning_without_generation_params(self):
        """execute should dispatch COMPLEX_PLANNING without extra args when no generation_params."""
        orch = _make_orch(should_use_council=False)
        orch.request_tracer = None
        strategy = ExecutionStrategy(orch)
        task_id = uuid4()
        request = TaskRequest(content="plan")

        result = await strategy.execute(task_id, "COMPLEX_PLANNING", "ctx", request)

        assert result == "dispatch_result"
        orch.task_dispatcher.dispatch.assert_awaited_once_with(
            "COMPLEX_PLANNING", "ctx"
        )

    async def test_execute_default_intent_dispatches(self):
        """execute should dispatch unrecognized intent via default path."""
        orch = _make_orch(should_use_council=False)
        orch.request_tracer = None
        strategy = ExecutionStrategy(orch)
        task_id = uuid4()
        request = TaskRequest(content="some task")

        result = await strategy.execute(task_id, "KNOWLEDGE_SEARCH", "ctx", request)

        assert result == "dispatch_result"
        orch.task_dispatcher.dispatch.assert_awaited_once()

    async def test_execute_default_intent_with_generation_params(self):
        """execute should pass generation_params in default path when provided."""
        orch = _make_orch(should_use_council=False)
        orch.request_tracer = None
        strategy = ExecutionStrategy(orch)
        task_id = uuid4()
        params = {"max_tokens": 100}
        request = TaskRequest(content="task", generation_params=params)

        await strategy.execute(task_id, "KNOWLEDGE_SEARCH", "ctx", request)

        orch.task_dispatcher.dispatch.assert_awaited_once_with(
            "KNOWLEDGE_SEARCH", "ctx", generation_params=params
        )

    async def test_execute_adds_tracer_step_for_help_request(self):
        """execute should add a tracer step when routing HELP_REQUEST."""
        tracer = MagicMock()
        orch = _make_orch()
        orch.request_tracer = tracer
        strategy = ExecutionStrategy(orch)

        await strategy.execute(
            uuid4(), "HELP_REQUEST", "ctx", TaskRequest(content="help")
        )

        step_actions = [c[0][2] for c in tracer.add_step.call_args_list]
        assert "route_help" in step_actions

    async def test_execute_adds_tracer_step_for_campaign(self):
        """execute should add tracer step when routing START_CAMPAIGN."""
        tracer = MagicMock()
        orch = _make_orch()
        orch.request_tracer = tracer
        fake_flow = AsyncMock()
        fake_flow.execute = AsyncMock(return_value={"summary": "done"})
        orch._campaign_flow = fake_flow
        strategy = ExecutionStrategy(orch)

        await strategy.execute(
            uuid4(), "START_CAMPAIGN", "ctx", TaskRequest(content="start")
        )

        step_actions = [c[0][2] for c in tracer.add_step.call_args_list]
        assert "route_campaign" in step_actions

    async def test_execute_default_tracer_shows_agent_name(self):
        """execute default path should include agent name in tracer step."""
        tracer = MagicMock()
        agent = MagicMock()
        agent.__class__.__name__ = "SpecificAgent"
        orch = _make_orch(
            should_use_council=False,
            dispatcher_agent_map={"RESEARCH": agent},
        )
        orch.request_tracer = tracer
        strategy = ExecutionStrategy(orch)

        await strategy.execute(
            uuid4(), "RESEARCH", "ctx", TaskRequest(content="research")
        )

        step_details = [str(c) for c in tracer.add_step.call_args_list]
        assert any("SpecificAgent" in d for d in step_details)


# ---------------------------------------------------------------------------
# ContextBuilder (additional branches not covered by test_orchestrator_components)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestContextBuilderPreprocessRequest:
    async def test_preprocess_request_session_reset_handled(self, monkeypatch):
        """preprocess_request should handle session_reset=True from parsed slash command."""
        logs = []

        class DummyState:
            def update_context(self, task_id, payload):
                pass

            def add_log(self, task_id, msg):
                logs.append(msg)

        orch = SimpleNamespace(
            state_manager=DummyState(),
            request_tracer=None,
            session_handler=SimpleNamespace(session_store=None),
        )
        builder = ContextBuilder(orch)

        from venom_core.core.slash_commands import SlashCommandResult

        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.context_builder.parse_slash_command",
            lambda _: SlashCommandResult(
                token="clear",
                cleaned="",
                forced_tool=None,
                forced_intent=None,
                session_reset=True,
            ),
        )

        task_id = uuid4()
        request = TaskRequest(content="/clear", session_id="s1")
        await builder.preprocess_request(task_id, request)

        assert any(
            "Wyczyszczono" in log for log in logs
        )  # Production code log message (Polish)

    async def test_preprocess_request_forced_tool_triggers_resolve_intent(
        self, monkeypatch
    ):
        """preprocess_request should resolve intent when forced_tool set without forced_intent."""
        state = SimpleNamespace(update_context=MagicMock(), add_log=MagicMock())
        tracer = MagicMock()
        orch = SimpleNamespace(
            state_manager=state,
            request_tracer=tracer,
            session_handler=SimpleNamespace(session_store=None),
        )
        builder = ContextBuilder(orch)

        from venom_core.core.slash_commands import SlashCommandResult

        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.context_builder.parse_slash_command",
            lambda _: SlashCommandResult(
                token="git",
                cleaned="status",
                forced_tool="git",
                forced_intent=None,
            ),
        )
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.context_builder.resolve_forced_intent",
            lambda tool: "VERSION_CONTROL",
        )

        task_id = uuid4()
        request = TaskRequest(content="/git status")
        await builder.preprocess_request(task_id, request)

        assert request.forced_intent == "VERSION_CONTROL"
        assert request.forced_tool == "git"

    async def test_preprocess_request_skips_slash_when_forced_tool_already_set(self):
        """preprocess_request should skip slash parsing when forced_tool is pre-set."""
        state = SimpleNamespace(update_context=MagicMock(), add_log=MagicMock())
        orch = SimpleNamespace(
            state_manager=state,
            request_tracer=None,
            session_handler=SimpleNamespace(session_store=None),
        )
        builder = ContextBuilder(orch)
        task_id = uuid4()
        request = TaskRequest(
            content="some content", forced_tool="browser", forced_intent="BROWSE"
        )
        # Should not raise and should not call parse_slash_command
        await builder.preprocess_request(task_id, request)
        # forced_tool stays unchanged
        assert request.forced_tool == "browser"


@pytest.mark.asyncio
class TestContextBuilderPrepareContext:
    async def test_prepare_context_with_images_adds_descriptions(self, monkeypatch):
        """prepare_context should append image descriptions to context."""
        state = SimpleNamespace(add_log=MagicMock())

        async def fake_analyze(img, prompt=None):
            return f"description of {img}"

        eyes = SimpleNamespace(analyze_image=fake_analyze)
        orch = SimpleNamespace(
            state_manager=state,
            eyes=eyes,
            request_tracer=None,
        )
        builder = ContextBuilder(orch)
        task_id = uuid4()
        request = TaskRequest(content="base", images=["img1", "img2"])

        ctx = await builder.prepare_context(task_id, request)

        assert "[OBRAZ 1]" in ctx
        assert "description of img1" in ctx
        assert "[OBRAZ 2]" in ctx

    async def test_prepare_context_logs_error_when_image_analysis_fails(
        self, monkeypatch
    ):
        """prepare_context should log an error when image analysis raises."""
        logs = []
        state = SimpleNamespace(add_log=lambda tid, msg: logs.append(msg))

        async def failing_analyze(img, prompt=None):
            raise RuntimeError("analyze failed")

        eyes = SimpleNamespace(analyze_image=failing_analyze)
        orch = SimpleNamespace(
            state_manager=state,
            eyes=eyes,
            request_tracer=None,
        )
        builder = ContextBuilder(orch)
        task_id = uuid4()
        request = TaskRequest(content="base", images=["bad_img"])

        ctx = await builder.prepare_context(task_id, request)

        assert "[OBRAZ 1]" not in ctx
        assert any(
            "Nie udało się" in log for log in logs
        )  # Production code log message (Polish)

    async def test_prepare_context_with_extra_context_appends_block(self):
        """prepare_context should append extra_context block when non-empty."""
        from venom_core.core.models import TaskExtraContext

        state = SimpleNamespace(add_log=MagicMock())
        orch = SimpleNamespace(
            state_manager=state, eyes=MagicMock(), request_tracer=None
        )
        builder = ContextBuilder(orch)
        task_id = uuid4()
        extra = TaskExtraContext(files=["a.py"], links=[], paths=[], notes=[])
        request = TaskRequest(content="base", extra_context=extra)

        ctx = await builder.prepare_context(task_id, request)

        assert "[DODATKOWE DANE]" in ctx  # Production code marker (Polish)
        assert "a.py" in ctx


@pytest.mark.asyncio
class TestContextBuilderBuildContext:
    async def test_build_context_skips_session_block_for_forced_tool(self, monkeypatch):
        """build_context should not prepend session context when forced_tool is set."""
        logs = []
        orch = SimpleNamespace(
            state_manager=SimpleNamespace(add_log=lambda _tid, msg: logs.append(msg)),
            request_tracer=None,
            _build_session_context_block=MagicMock(
                return_value="[KONTEKST SESJI]\nmeta"
            ),
            _get_runtime_context_char_limit=lambda _runtime: 100000,
        )
        builder = ContextBuilder(orch)
        task_id = uuid4()
        request = TaskRequest(content="ceny DDR5", forced_tool="research")

        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.context_builder.get_active_llm_runtime",
            lambda: SimpleNamespace(provider="ollama"),
        )

        out = await builder.build_context(task_id, request, fast_path=False)

        assert out == "ceny DDR5"
        orch._build_session_context_block.assert_not_called()
        assert any(
            "Pominięto kontekst sesji dla wymuszonego toola" in log for log in logs
        )

    async def test_build_context_keeps_session_block_without_forced_tool(
        self, monkeypatch
    ):
        """build_context should prepend session context for normal requests."""
        orch = SimpleNamespace(
            state_manager=SimpleNamespace(add_log=lambda *_args, **_kwargs: None),
            request_tracer=None,
            _build_session_context_block=MagicMock(
                return_value="[KONTEKST SESJI]\nmeta"
            ),
            _get_runtime_context_char_limit=lambda _runtime: 100000,
        )
        builder = ContextBuilder(orch)
        task_id = uuid4()
        request = TaskRequest(content="zwykłe pytanie")

        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.context_builder.get_active_llm_runtime",
            lambda: SimpleNamespace(provider="ollama"),
        )

        out = await builder.build_context(task_id, request, fast_path=False)

        assert out.startswith("[KONTEKST SESJI]\nmeta\n\n")
        orch._build_session_context_block.assert_called_once()


@pytest.mark.asyncio
class TestContextBuilderUpdateForcedRouteContext:
    async def test_update_forced_route_sets_context_without_tracer(self):
        """_update_forced_route_context should update context even without tracer."""
        updates = []
        state = SimpleNamespace(
            update_context=lambda tid, payload: updates.append(payload),
            add_log=MagicMock(),
        )
        orch = SimpleNamespace(
            state_manager=state,
            request_tracer=None,
        )
        builder = ContextBuilder(orch)
        task_id = uuid4()

        builder._update_forced_route_context(task_id, "browser", None, "BROWSE")

        assert any("forced_route" in u for u in updates)

    async def test_update_forced_route_calls_tracer_when_present(self):
        """_update_forced_route_context should call tracer methods when tracer set."""
        updates = []
        state = SimpleNamespace(
            update_context=lambda tid, payload: updates.append(payload),
        )
        tracer = MagicMock()
        orch = SimpleNamespace(state_manager=state, request_tracer=tracer)
        builder = ContextBuilder(orch)
        task_id = uuid4()

        builder._update_forced_route_context(task_id, "git", None, "VERSION_CONTROL")

        tracer.set_forced_route.assert_called_once()
        tracer.add_step.assert_called()

    async def test_update_forced_route_skips_set_forced_route_when_only_intent(self):
        """_update_forced_route_context should not call set_forced_route when only intent set."""
        state = SimpleNamespace(update_context=MagicMock())
        tracer = MagicMock()
        orch = SimpleNamespace(state_manager=state, request_tracer=tracer)
        builder = ContextBuilder(orch)
        task_id = uuid4()

        builder._update_forced_route_context(task_id, None, None, "GENERAL_CHAT")

        tracer.set_forced_route.assert_not_called()
        # But add_step should still be called
        tracer.add_step.assert_called()
