"""Tests for task_pipeline: TaskValidator, ResultProcessor, ExecutionStrategy, ContextBuilder."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from venom_core.core.autonomy_enforcement import AutonomyPermissionDenied
from venom_core.core.models import TaskRequest
from venom_core.core.orchestrator.task_pipeline.context_builder import ContextBuilder
from venom_core.core.orchestrator.task_pipeline.execution_strategy import (
    ExecutionStrategy,
)
from venom_core.core.orchestrator.task_pipeline.result_processor import ResultProcessor
from venom_core.core.orchestrator.task_pipeline.task_validator import TaskValidator
from venom_core.core.policy_autonomy_contract import build_autonomy_block_payload

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
        """An ONNX worker must be explicitly enabled."""
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.SETTINGS.ONNX_LLM_ENABLED",
            False,
        )
        runtime = self._make_runtime(provider="onnx")
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.get_active_llm_runtime",
            lambda: runtime,
        )
        orch = _make_orch()
        validator = TaskValidator(orch)
        task_id = uuid4()

        prepared_task_request_2 = TaskRequest(content="x")
        with pytest.raises(RuntimeError, match="runtime_not_supported"):
            validator.validate_routing(task_id, prepared_task_request_2, None)

        assert orch._errors_set[task_id]["error_code"] == "runtime_not_supported"

    @pytest.mark.parametrize("endpoint", [None, "", "not-an-http-endpoint"])
    def test_validate_routing_rejects_missing_onnx_worker(self, monkeypatch, endpoint):
        runtime = self._make_runtime(provider="onnx")
        runtime.endpoint = endpoint
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.SETTINGS.ONNX_LLM_ENABLED",
            True,
        )
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.get_active_llm_runtime",
            lambda: runtime,
        )
        prepared_operation = TaskValidator(_make_orch()).validate_routing
        prepared_uuid4 = uuid4()
        prepared_task_request = TaskRequest(content="x")
        with pytest.raises(RuntimeError, match="runtime_not_supported"):
            prepared_operation(prepared_uuid4, prepared_task_request, None)

    def test_validate_routing_accepts_enabled_onnx_http_worker(self, monkeypatch):
        runtime = self._make_runtime(provider="onnx")
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.SETTINGS.ONNX_LLM_ENABLED",
            True,
        )
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.task_validator.get_active_llm_runtime",
            lambda: runtime,
        )
        orch = _make_orch()
        TaskValidator(orch).validate_routing(
            uuid4(),
            TaskRequest(content="x", expected_config_hash=runtime.config_hash),
            None,
        )
        assert not orch._errors_set

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

        prepared_task_request_3 = TaskRequest(content="x")
        with pytest.raises(RuntimeError, match="forced_provider_mismatch"):
            validator.validate_routing(task_id, prepared_task_request_3, "openai")

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

    async def test_process_error_maps_autonomy_denied_to_canonical_payload(self):
        """process_error should map autonomy deny to canonical runtime/session context."""
        orch = _make_orch()
        update_calls: list[tuple[object, dict]] = []
        orch.state_manager.update_context = lambda tid, payload: update_calls.append(
            (tid, payload)
        )
        rp = ResultProcessor(orch)
        task_id = uuid4()
        request = TaskRequest(content="x", session_id="session-1")
        payload = build_autonomy_block_payload(
            user_message="AutonomyViolation: Brak uprawnień do shella",
            operation="shell_execution",
            required_level=40,
            required_level_name="ROOT",
            task_id=str(task_id),
            session_id="session-1",
        )
        exc = AutonomyPermissionDenied(payload)

        await rp.process_error(task_id, exc, request)

        assert task_id in orch._errors_set
        assert orch._errors_set[task_id]["error_code"] == "AUTONOMY_PERMISSION_DENIED"
        assert orch._errors_set[task_id]["stage"] == "autonomy_enforcement"
        assert update_calls
        update_payload = update_calls[-1][1]
        assert update_payload["policy_blocked"] is True
        assert update_payload["decision"] == "block"
        assert update_payload["reason_code"] == "AUTONOMY_PERMISSION_DENIED"
        assert update_payload["technical_context"]["operation"] == "shell_execution"
        orch._append_session_history.assert_called()


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

    @pytest.mark.parametrize("use_notes", [True, False])
    async def test_chat_notes_policy_saves_history_without_automatic_indexing(
        self, use_notes
    ):
        orch = _make_orch(store_lesson=True)
        request = TaskRequest(content="hi", session_id="own", use_notes=use_notes)
        task_id = uuid4()

        await ResultProcessor(orch).process_success(
            task_id, "answer", "GENERAL_CHAT", "ctx", request, False
        )

        orch.session_handler._memory_upsert.assert_not_called()
        orch.lessons_manager.save_task_lesson.assert_not_awaited()
        orch._append_session_history.assert_called_once_with(
            task_id, role="assistant", content="answer", session_id="own"
        )

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

    async def test_note_lookup_dispatches_to_chat_without_council(self):
        orch = _make_orch(should_use_council=True)
        request = TaskRequest(
            content="Jaki jest kod odbioru z notatki?", use_notes=False
        )

        result = await ExecutionStrategy(orch).execute(
            uuid4(), "GENERAL_CHAT", "ctx", request, note_lookup=True
        )

        assert result == "dispatch_result"
        orch.task_dispatcher.dispatch.assert_awaited_once_with(
            "GENERAL_CHAT", "ctx", generation_params=None, note_lookup=True
        )

    @pytest.mark.parametrize("use_notes", [False, True])
    async def test_general_chat_with_explicit_notes_policy_uses_supplied_context(
        self, use_notes
    ):
        orch = _make_orch(should_use_council=False)
        request = TaskRequest(content="What is a file extension?", use_notes=use_notes)

        await ExecutionStrategy(orch).execute(uuid4(), "GENERAL_CHAT", "ctx", request)

        orch.task_dispatcher.dispatch.assert_awaited_once_with(
            "GENERAL_CHAT", "ctx", generation_params=None, note_lookup=True
        )

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
    async def test_unknown_provider_prefix_survives_preprocessing_without_a_forced_route(
        self,
    ):
        state = SimpleNamespace(update_context=MagicMock(), add_log=MagicMock())
        builder = ContextBuilder(
            SimpleNamespace(state_manager=state, request_tracer=None)
        )
        request = TaskRequest(content="/rider stan")

        await builder.preprocess_request(uuid4(), request)

        assert request.content == "/rider stan"
        assert request.forced_tool is None
        assert request.forced_provider is None
        assert request.forced_intent is None
        state.update_context.assert_not_called()

    async def test_explicit_forced_tool_is_preserved_for_a_provider_prefixed_message(
        self,
    ):
        state = SimpleNamespace(update_context=MagicMock(), add_log=MagicMock())
        builder = ContextBuilder(
            SimpleNamespace(state_manager=state, request_tracer=None)
        )
        request = TaskRequest(content="/rider stan", forced_tool="git")

        await builder.preprocess_request(uuid4(), request)

        assert request.content == "/rider stan"
        assert request.forced_tool == "git"
        assert request.forced_intent == "VERSION_CONTROL"

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

    async def test_short_chat_retains_question_and_recent_correction(self, monkeypatch):
        """Keep the current question and newest correction under a tight context budget."""
        block = MagicMock(return_value="old " * 100 + "latest correction")
        orch = SimpleNamespace(
            state_manager=SimpleNamespace(add_log=MagicMock()),
            _build_session_context_block=block,
            _get_runtime_context_char_limit=lambda _: 80,
        )
        monkeypatch.setattr(
            "venom_core.core.orchestrator.task_pipeline.context_builder.get_active_llm_runtime",
            lambda: SimpleNamespace(provider="ollama"),
        )
        task_id = uuid4()
        request = TaskRequest(content="What is the final date?", session_id="a")

        result = await ContextBuilder(orch).build_context(
            task_id, request, fast_path=True
        )

        block.assert_called_once_with(request, task_id, include_memory=True)
        assert len(result) == 80
        assert result.endswith("latest correction\n\nWhat is the final date?")


def test_memory_selection_never_falls_back_to_another_session():
    """Exclude another session even when there are no matching entries."""
    from venom_core.core.orchestrator.session_handler import SessionHandler

    foreign = {"metadata": {"session_id": "other"}, "text": "foreign"}
    own = {"metadata": {"session_id": "own"}, "text": "own"}
    shared = {"metadata": {}, "text": "shared"}
    select = SessionHandler._select_relevant_memory_items
    assert select([foreign], "own") == []
    assert select([foreign, own, shared], "own") == [own, shared]
    assert select([foreign, own, shared], None) == [shared]


@pytest.mark.parametrize(
    ("prompt", "subject"),
    [
        ("Według notatki podaj termin dla projektu Jasny Brzeg.", "Jasny Brzeg"),
        (
            "According to the retrieved notes, what is the code for Copper Quay?",
            "Copper Quay",
        ),
    ],
)
def test_rag_retrieval_rejects_other_subject_and_other_session(prompt, subject):
    """Require both the requested subject and the allowed session scope."""
    from venom_core.core.orchestrator.session_handler import SessionHandler

    search = MagicMock(
        return_value=[
            {"text": "Projekt Ciemny Brzeg: 08:50", "metadata": {"session_id": "own"}},
            {
                "text": f"{subject}: 19:30",
                "metadata": {"session_id": "foreign"},
            },
            {"text": f"{subject}: 07:41", "metadata": {"session_id": "own"}},
        ]
    )
    handler = SessionHandler(
        MagicMock(), SimpleNamespace(vector_store=SimpleNamespace(search=search))
    )
    request = TaskRequest(content=prompt, session_id="own")
    context, _ = handler._retrieve_relevant_memory(request, "own")
    first, last = subject.split()
    search.assert_called_once_with(
        subject,
        limit=8,
        session_scope=True,
        session_id="own",
        text_pattern=rf"(?i)\b{first}[ \t]+{last}\b",
    )
    assert "07:41" in context
    assert "08:50" not in context
    assert "19:30" not in context

    parts = []
    handler._attach_memory_block(uuid4(), MagicMock(), request, [], parts)
    assert "reference data" in parts[0]
    assert "07:41" in parts[1]
    assert "19:30" not in parts[1]

    search.return_value.pop()
    parts = []
    handler._attach_memory_block(uuid4(), MagicMock(), request, [], parts)
    assert "no matching source" in parts[0]
    assert parts[1:] == ["[PAMIĘĆ] Brak źródła pasującego do wskazanej nazwy."]


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


def test_vector_search_applies_session_scope_before_limit(tmp_path):
    """Prefilter the vector query so unrelated sessions cannot consume the result limit."""
    from venom_core.memory.vector_store import VectorStore

    pytest.importorskip("lancedb")

    class Embeddings:
        embedding_dimension = 3

        def get_embedding(self, text):
            """Return the test query embedding without calling a remote model."""
            if "właściwy" in text:
                return [0.0, 0.0, 1.0]
            return [1.0, 0.0, 0.0] if "foreign" in text else [0.0, 1.0, 0.0]

        def get_embeddings_batch(self, texts):
            """Return fixed embeddings for the test records."""
            return [self.get_embedding(text) for text in texts]

    store = VectorStore(db_path=str(tmp_path), embedding_service=Embeddings())
    store.upsert("foreign", {"session_id": "foreign"})
    store.upsert("own", {"session_id": "own"})
    store.upsert("shared", {})
    assert store.search("foreign", limit=1)[0]["text"] == "foreign"
    scoped = store.search("foreign", limit=2, session_scope=True, session_id="own")
    assert {item["text"] for item in scoped} == {"own", "shared"}
    global_only = store.search("foreign", limit=2, session_scope=True)
    assert [item["text"] for item in global_only] == ["shared"]

    for i in range(10):
        store.upsert(f"Jasny Brzegowy wpis {i}", {"session_id": "own"})
    matching = "JASNY BRZEG: właściwy termin"
    store.upsert(matching, {"session_id": "own"})
    store.upsert("Jasny Brzeg: tajny termin", {"session_id": "foreign"})
    unfiltered = store.search(
        "Jasny Brzeg", limit=8, session_scope=True, session_id="own"
    )
    assert all(item["text"] != matching for item in unfiltered)
    scoped = store.search(
        "Jasny Brzeg",
        limit=8,
        session_scope=True,
        session_id="own",
        text_pattern=r"(?i)\bJasny[ \t]+Brzeg\b",
    )
    assert [item["text"] for item in scoped] == [matching]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_reply", "tool_required", "accepted"),
    [("", False, True), (None, False, False), (None, True, True)],
)
async def test_empty_chat_result_depends_on_origin(
    monkeypatch, provider_reply, tool_required, accepted
):
    """Allow an empty provider or tool result while rejecting empty model text."""
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch

    orch = _make_orch()
    callback = MagicMock()
    orch.streaming_handler = SimpleNamespace(create_stream_callback=lambda _: callback)
    provider = AsyncMock(return_value=provider_reply)
    model = AsyncMock(return_value="")
    monkeypatch.setattr(dispatch, "handle_conversation_turn", provider)
    monkeypatch.setattr(
        dispatch, "ExecutionStrategy", lambda _: SimpleNamespace(execute=model)
    )
    monkeypatch.setattr(
        dispatch, "get_active_llm_runtime", lambda: SimpleNamespace(provider="ollama")
    )
    task_id = uuid4()
    request = TaskRequest(content="hello")

    if accepted:
        assert (
            await dispatch._execute_with_stream_callback(
                orch,
                task_id,
                "GENERAL_CHAT",
                "context",
                request,
                tool_required=tool_required,
            )
            == ""
        )
    else:
        with pytest.raises(RuntimeError, match="Model nie zwrócił treści"):
            await dispatch._execute_with_stream_callback(
                orch,
                task_id,
                "GENERAL_CHAT",
                "context",
                request,
                tool_required=tool_required,
            )

    if provider_reply is not None:
        callback.assert_called_once_with("")
        model.assert_not_awaited()
    else:
        model.assert_awaited_once()


def test_memory_subject_requires_explicit_named_source():
    """Keep ordinary time phrases from narrowing RAG to a named subject."""
    from venom_core.core.orchestrator.session_handler import SessionHandler

    assert SessionHandler._named_memory_subject("Plan this for Monday Morning") is None
    assert (
        SessionHandler._named_memory_subject(
            "According to the notes, this is urgent. Plan this for Monday Morning."
        )
        is None
    )
    assert (
        SessionHandler._named_memory_subject("Notes for project Jasny Brzeg")
        == "Jasny Brzeg"
    )


@pytest.mark.parametrize(
    ("enabled", "use_notes", "searches"),
    [(True, False, 0), (False, True, 0), (True, True, 1)],
)
def test_full_chat_notes_gate_keeps_session_history(
    tmp_path, monkeypatch, enabled, use_notes, searches
):
    from venom_core.config import SETTINGS
    from venom_core.core.orchestrator.session_handler import SessionHandler
    from venom_core.services.session_store import SessionStore

    monkeypatch.setattr(SETTINGS, "CHAT_NOTES_ENABLED", enabled)
    state, memory = MagicMock(), MagicMock()
    state.get_task.return_value.context_history = {}
    state.get_task.return_value.context_used = None
    memory.vector_store.search.return_value = [
        {
            "id": "saved-note",
            "text": "Jasny Brzeg: 07:41",
            "metadata": {"session_id": "own"},
        },
    ]
    store = SessionStore(str(tmp_path / "session.json"))
    store.append_message("own", {"role": "user", "content": "earlier turn"})
    handler = SessionHandler(
        state_manager=state, memory_skill=memory, session_store=store
    )
    handler._ensure_session_summary = MagicMock()
    result = handler.build_session_context_block(
        TaskRequest(
            content="Według notatki projektu Jasny Brzeg podaj termin.",
            session_id="own",
            use_notes=use_notes,
        ),
        uuid4(),
    )
    assert "earlier turn" in result
    assert ("07:41" in result) == bool(searches)
    assert ("Saved notes are disabled" in result) == (not searches)
    if searches:
        assert state.get_task.return_value.context_used.memory_entries == ["saved-note"]
    assert memory.vector_store.search.call_count == searches
    handler._ensure_session_summary.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("use_notes", [False, True])
@pytest.mark.parametrize(
    "prompt",
    [
        "Według notatki projektu Srebrny Brzeg, jaki jest kod odbioru?",
        "Jaki jest kod odbioru według notatki projektu Srebrny Brzeg?",
        "According to the notes for project Silver Bank, what is the pickup code?",
    ],
)
async def test_full_normal_routes_saved_pickup_code_to_chat(prompt, use_notes):
    from venom_core.core.orchestrator.orchestrator_dispatch import _resolve_task_intent

    classifier = AsyncMock(return_value="CODE_GENERATION")
    orch = SimpleNamespace(intent_manager=SimpleNamespace(classify_intent=classifier))
    request = TaskRequest(content=prompt, session_id="own", use_notes=use_notes)

    intent, debug = await _resolve_task_intent(orch, request, prompt)

    assert intent == "GENERAL_CHAT"
    assert debug["source"] == "saved_note_lookup"
    classifier.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prompt", "options"),
    [
        ("Jaki kod napisać bez notatek?", {"use_notes": False}),
        (
            "Według notatki projektu Srebrny Brzeg, napisz funkcję w Pythonie.",
            {"use_notes": True},
        ),
        (
            "Napisz kod do obsługi błędów z dokumentacji projektu Srebrny Brzeg.",
            {"use_notes": False},
        ),
        ("Według notatki projektu Srebrny Brzeg, jaki jest kod odbioru?", {}),
        (
            "Według notatki projektu Srebrny Brzeg, jaki jest kod odbioru?",
            {"use_notes": True, "forced_provider": "ollama"},
        ),
    ],
)
async def test_full_normal_saved_note_routing_preserves_explicit_and_legacy_routes(
    prompt, options
):
    from venom_core.core.orchestrator.orchestrator_dispatch import _resolve_task_intent

    classifier = AsyncMock(return_value="CODE_GENERATION")
    orch = SimpleNamespace(intent_manager=SimpleNamespace(classify_intent=classifier))
    request = TaskRequest(content=prompt, session_id="own", **options)

    intent, _ = await _resolve_task_intent(orch, request, prompt)

    assert intent == "CODE_GENERATION"
    classifier.assert_awaited_once_with(prompt)


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Sprawdź Venoma i Rider-Pi", (False, True, True)),
        ("Jak sprawdzić stan Rider-Pi?", (True, False, True)),
        ("Check status of Venom", (False, True, False)),
        ("Sprawdź Rider-Pi i włącz napęd", None),
        ("Powiedział «Sprawdź Rider-Pi»", None),
        ("Sprawdź http://192.0.2.1", None),
    ],
)
def test_g5_diagnostic_commands_accept_only_complete_read_requests(prompt, expected):
    from venom_core.services.operator_diagnostics import parse_diagnostic_request

    request = parse_diagnostic_request(prompt)

    assert (
        None if request is None else (request.guide, request.venom, request.rider)
    ) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["offline", "partial", "denied", "stale"])
async def test_g5_rider_evidence_keeps_read_failures_and_ack_separate(
    monkeypatch, scenario
):
    import time

    import httpx

    from venom_core.services import operator_diagnostics as diagnostics

    control = {
        "safety": {
            "observed_at": time.time() - (60 if scenario == "stale" else 0),
            "output": {"lx": 0.25, "az": -0.75},
            "last_ack": {"accepted": True, "status": "executed"},
        },
    }
    samples = {
        "offline": {
            "connection": {"status": "offline"},
            "errors": {"health": "pi_unreachable"},
        },
        "partial": {
            "connection": {"status": "degraded"},
            "control": control,
            "health": {"status": "ok"},
            "errors": {"telemetry": "pi_unreachable", "settings": "forbidden"},
        },
        "stale": {
            "connection": {"status": "degraded"},
            "control": control,
        },
    }
    calls = []

    def endpoint(request):
        calls.append((request.method, str(request.url)))
        if scenario == "denied":
            return httpx.Response(403, json={"detail": "private secret"})
        return httpx.Response(200, json=samples[scenario])

    client = httpx.AsyncClient
    monkeypatch.setattr(
        diagnostics.httpx,
        "AsyncClient",
        lambda **options: client(transport=httpx.MockTransport(endpoint), **options),
    )
    command = diagnostics.parse_diagnostic_request("Sprawdź Rider-Pi")
    assert command is not None

    reply = await diagnostics.run_operator_diagnostics(
        command, "http://127.0.0.1:8000/api/v1/system/services"
    )

    assert calls == [
        ("GET", "http://127.0.0.1:8000/api/v1/rider/status?section=overview")
    ]
    if scenario == "offline":
        assert "**brak transportu**" in reply
        assert "Odczytano: brak" in reply
        assert "Sprawdź wybór urządzenia i stan transportu" in reply
    elif scenario == "partial":
        assert "**częściowy odczyt**" in reply
        assert "Odmowa: settings." in reply
        assert "Odczytano: control, health." in reply
        assert "Bez danych: telemetry, system." in reply
        assert "lx (liniowa)=0.25, az (obrotowa)=-0.75" in reply
        assert "ACK potwierdza przyjęcie" in reply
        assert "Brak dowodu fizycznego skutku" in reply
    elif scenario == "stale":
        assert "Stan sterowania przeterminowany" in reply
        assert "0.25" not in reply
    else:
        assert "**odmowa**" in reply
        assert "HTTP 403" in reply
        assert "private secret" not in reply


@pytest.mark.asyncio
async def test_g5_guide_and_api_failure_use_host_runbook(monkeypatch, tmp_path):
    import httpx

    from venom_core.services import operator_diagnostics as diagnostics

    log = tmp_path / "venom.log"
    log.write_bytes(
        b"x" * 17000 + b"\n2026-11-08 12:00:00.000 | ERROR    | password=fixture\n"
    )
    calls = []

    def endpoint(request):
        calls.append(request.method)
        raise httpx.ConnectError("offline", request=request)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        diagnostics.httpx,
        "AsyncClient",
        lambda **options: client(transport=httpx.MockTransport(endpoint), **options),
    )
    guide = diagnostics.parse_diagnostic_request("Jak sprawdzić Venoma i Rider-Pi?")
    check = diagnostics.parse_diagnostic_request("Sprawdź Venoma")
    assert guide is not None
    assert check is not None
    origin = "http://127.0.0.1:8000/api/v1/system/services"

    instructions = await diagnostics.run_operator_diagnostics(
        guide, origin, log_dir=tmp_path
    )
    assert not calls
    assert diagnostics.RUNBOOK in instructions
    assert diagnostics.HOST_CHECK in instructions

    reply = await diagnostics.run_operator_diagnostics(check, origin, log_dir=tmp_path)
    assert calls == ["GET"]
    assert "Brak odpowiedzi lokalnego API" in reply
    assert diagnostics.HOST_CHECK in reply
    assert "16384 B" in reply
    assert "ERROR=1" in reply
    assert "password" not in reply


@pytest.mark.parametrize(
    ("client_host", "origin", "studio", "expected"),
    [
        ("192.0.2.2", None, False, 403),
        ("127.0.0.1", "https://example.invalid", False, 403),
        ("127.0.0.1", None, True, 409),
        ("127.0.0.1", None, False, 201),
    ],
)
def test_g5_task_requires_operator_before_queueing(
    client_host, origin, studio, expected
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from venom_core.api.dependencies import get_orchestrator
    from venom_core.api.routes import tasks

    app = FastAPI()
    app.include_router(tasks.router)
    app.state.studio_runtime = object() if studio else None
    submit = AsyncMock(
        return_value={"task_id": uuid4(), "status": "PENDING", "message": "queued"}
    )
    get_runtime = MagicMock(return_value=SimpleNamespace(submit_task=submit))
    app.dependency_overrides[get_orchestrator] = lambda: get_runtime()
    headers = {"Origin": origin} if origin else {}
    response = TestClient(app, client=(client_host, 51100)).post(
        "/api/v1/tasks",
        json={"content": "Sprawdź Rider-Pi"},
        headers=headers,
    )

    assert response.status_code == expected
    assert get_runtime.call_count == submit.await_count == int(expected == 201)


@pytest.mark.asyncio
async def test_g5_routing_uses_full_dispatcher_without_classification(monkeypatch):
    from venom_core.agents.system_status import SystemStatusAgent
    from venom_core.core.dispatcher import TaskDispatcher
    from venom_core.core.orchestrator.orchestrator_dispatch import _resolve_task_intent
    from venom_core.services import operator_diagnostics as diagnostics
    from venom_core.services.execution_template_planner import resolve_response_template

    orch = SimpleNamespace(intent_manager=SimpleNamespace(classify_intent=AsyncMock()))
    command = TaskRequest(content="Sprawdź Rider-Pi")
    diagnose = AsyncMock(return_value="Dowód")
    agent = SystemStatusAgent(
        MagicMock(), "http://127.0.0.1:8000/api/v1/system/services"
    )
    monkeypatch.setattr(agent, "diagnose", diagnose)
    dispatcher = SimpleNamespace(
        node_manager=None,
        system_status_agent=agent,
        agent_map={diagnostics.DIAGNOSTICS_INTENT: agent},
    )

    intent, debug = await _resolve_task_intent(orch, command, command.content)
    template = resolve_response_template(command, intent)
    answer = await TaskDispatcher.dispatch(dispatcher, intent, command.content)

    assert intent == diagnostics.DIAGNOSTICS_INTENT
    assert debug["source"] == "operator_diagnostics"
    assert template is not None
    assert template.requires_llm is False
    assert answer == "Dowód"
    diagnose.assert_awaited_once_with(command.content)
    orch.intent_manager.classify_intent.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "allowed", "expected"),
    [
        (
            "Pokaż nazwy plików i katalogów w katalogu głównym workspace "
            "(`.`), bez schodzenia do podkatalogów. Tylko odczyt.",
            True,
            "[plik] odczyt.txt",
        ),
        (
            'Wypisz pliki w katalogu "notatki testowe"',
            True,
            "[plik] notatki testowe/proba.txt",
        ),
        ('Wypisz pliki w katalogu ".."', True, "Odmowa dostępu"),
        ("Wypisz pliki", False, "Odmowa dostępu"),
    ],
)
async def test_normal_workspace_listing_returns_verified_file_skill_result(
    tmp_path, monkeypatch, content, allowed, expected
):
    from venom_core.agents import librarian
    from venom_core.core.dispatcher import TaskDispatcher
    from venom_core.core.orchestrator.orchestrator_dispatch import _resolve_task_intent
    from venom_core.execution.skills.file_skill import FileSkill
    from venom_core.services.operator_diagnostics import DIAGNOSTICS_INTENT

    (tmp_path / "odczyt.txt").write_text("treść nie powinna trafić do listy")
    nested = tmp_path / "notatki testowe"
    nested.mkdir()
    (nested / "proba.txt").touch()
    agent = librarian.LibrarianAgent(MagicMock())
    agent.file_skill = FileSkill(str(tmp_path))
    monkeypatch.setattr(
        librarian.permission_guard, "check_permission", lambda _: allowed
    )
    classify = AsyncMock()
    orch = SimpleNamespace(intent_manager=SimpleNamespace(classify_intent=classify))
    dispatcher = SimpleNamespace(
        node_manager=None,
        librarian_agent=agent,
        agent_map={DIAGNOSTICS_INTENT: object()},
    )

    intent, debug = await _resolve_task_intent(
        orch, TaskRequest(content=content), content
    )
    result = await TaskDispatcher.dispatch(dispatcher, intent, content)

    assert debug["source"] == "workspace_listing"
    assert expected in result
    assert "treść nie powinna trafić do listy" not in result
    classify.assert_not_awaited()


def test_g5_services_reports_named_failures_without_raw_fields():
    from datetime import UTC, datetime

    from venom_core.services import operator_diagnostics as diagnostics

    sample = diagnostics.ProbeResult(
        {
            "services": [
                {"name": "Redis", "status": "offline", "error": "fixture secret"},
                {"name": "Backend", "status": "online"},
            ]
        },
        "odczytano",
        "HTTP 200",
    )
    result = diagnostics._services_evidence(sample, datetime.now(UTC))
    assert result.status == "częściowy odczyt"
    assert "Redis=offline" in result.detail
    assert "fixture secret" not in result.detail


@pytest.mark.asyncio
async def test_g5_rider_token_is_sent_only_to_the_local_rider_probe(
    monkeypatch, tmp_path
):
    import httpx

    from venom_core.services import operator_diagnostics as diagnostics

    token = "fixture-rider-token"
    monkeypatch.setenv("RIDER_ACCESS_TOKEN", token)
    calls = []

    def endpoint(request):
        auth = request.headers.get("Authorization")
        calls.append((request.method, request.url.path, auth))
        if request.url.path == "/api/v1/system/services":
            return httpx.Response(200, json={"services": []})
        if auth != f"Bearer {token}":
            return httpx.Response(403)
        return httpx.Response(
            200, json={"connection": {"status": "online"}, "health": {}}
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        diagnostics.httpx,
        "AsyncClient",
        lambda **options: client(transport=httpx.MockTransport(endpoint), **options),
    )
    check = diagnostics.parse_diagnostic_request("Sprawdź Venoma i Rider-Pi")
    assert check is not None
    report = await diagnostics.run_operator_diagnostics(
        check, "http://127.0.0.1:8000/api/v1/system/services", log_dir=tmp_path
    )

    assert calls == [
        ("GET", "/api/v1/system/services", None),
        ("GET", "/api/v1/rider/status", f"Bearer {token}"),
    ]
    assert "Odczytano: health." in report
    assert token not in report


@pytest.mark.asyncio
async def test_g5_never_probes_nonloopback_or_follows_redirects(monkeypatch):
    import httpx

    from venom_core.services import operator_diagnostics as diagnostics

    monkeypatch.setenv("RIDER_ACCESS_TOKEN", "fixture-rider-token")
    urls = []

    def endpoint(request):
        urls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://192.0.2.4/other"})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        diagnostics.httpx,
        "AsyncClient",
        lambda **options: client(transport=httpx.MockTransport(endpoint), **options),
    )
    check = diagnostics.parse_diagnostic_request("Sprawdź Rider-Pi")
    assert check is not None
    refusal = await diagnostics.run_operator_diagnostics(
        check, "http://192.0.2.4:8000/api/v1/system/services"
    )
    assert not urls
    assert "Odmowa diagnostyki" in refusal
    redirect = await diagnostics.run_operator_diagnostics(
        check, "http://127.0.0.1:8000/api/v1/system/services"
    )
    assert urls == ["http://127.0.0.1:8000/api/v1/rider/status?section=overview"]
    assert "HTTP 302" in redirect
