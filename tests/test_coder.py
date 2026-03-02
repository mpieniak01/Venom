from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.coder import CoderAgent


@pytest.mark.asyncio
async def test_read_file_prefers_skill_manager_path() -> None:
    agent = object.__new__(CoderAgent)
    invoke = AsyncMock(return_value="mcp-content")
    agent.skill_manager = SimpleNamespace(invoke_mcp_tool=invoke)
    agent.file_skill = SimpleNamespace(
        read_file=AsyncMock(return_value="legacy-content")
    )

    result = await CoderAgent._read_file(agent, "demo.py")

    assert result == "mcp-content"
    invoke.assert_awaited_once_with(
        "file",
        "read_file",
        {"file_path": "demo.py"},
        is_external=False,
    )


@pytest.mark.asyncio
async def test_read_file_uses_legacy_file_skill_without_skill_manager() -> None:
    agent = object.__new__(CoderAgent)
    read_file = AsyncMock(return_value="legacy-content")
    agent.skill_manager = None
    agent.file_skill = SimpleNamespace(read_file=read_file)

    result = await CoderAgent._read_file(agent, "legacy.py")

    assert result == "legacy-content"
    read_file.assert_awaited_once_with("legacy.py")


@pytest.mark.asyncio
async def test_process_with_params_delegates_to_internal() -> None:
    agent = object.__new__(CoderAgent)
    process_internal = AsyncMock(return_value="ok")
    agent._process_internal = process_internal
    agent._get_safe_params_for_logging = lambda params: {
        "temperature": params.get("temperature")
    }

    result = await CoderAgent.process_with_params(
        agent,
        "build helper",
        {"temperature": 0.2},
    )

    assert result == "ok"
    process_internal.assert_awaited_once_with("build helper", {"temperature": 0.2})


@pytest.mark.asyncio
async def test_process_delegates_to_internal_without_params() -> None:
    agent = object.__new__(CoderAgent)
    process_internal = AsyncMock(return_value="ok")
    agent._process_internal = process_internal

    result = await CoderAgent.process(agent, "hello")

    assert result == "ok"
    process_internal.assert_awaited_once_with("hello", None)


@pytest.mark.asyncio
async def test_process_internal_success_returns_stripped_response() -> None:
    agent = object.__new__(CoderAgent)
    agent.kernel = SimpleNamespace(get_service=lambda: object())
    agent.SYSTEM_PROMPT = "system"
    agent._create_execution_settings = lambda **kwargs: kwargs
    agent._invoke_chat_with_fallbacks = AsyncMock(return_value="  generated  ")

    result = await CoderAgent._process_internal(
        agent, "write code", {"temperature": 0.1}
    )

    assert result == "generated"
    agent._invoke_chat_with_fallbacks.assert_awaited_once()


def test_build_verification_chat_history_contains_prompt_and_script() -> None:
    agent = object.__new__(CoderAgent)
    agent.SYSTEM_PROMPT = "system"

    history = CoderAgent._build_verification_chat_history(
        agent,
        "create script",
        "demo.py",
    )

    assert len(history.messages) == 2
    assert history.messages[0].role == AuthorRole.SYSTEM
    assert "demo.py" in str(history.messages[1].content)


def test_append_repair_feedback_to_history_adds_user_message() -> None:
    agent = object.__new__(CoderAgent)
    history = ChatHistory()

    CoderAgent._append_repair_feedback_to_history(
        agent,
        history,
        "Traceback...",
        "broken.py",
    )

    assert len(history.messages) == 1
    assert history.messages[0].role == AuthorRole.USER
    assert "broken.py" in str(history.messages[0].content)


def test_build_final_verification_result_payload() -> None:
    payload = CoderAgent._build_final_verification_result(
        success=True,
        output="ok",
        attempts=1,
        final_code="print(1)",
    )
    assert payload == {
        "success": True,
        "output": "ok",
        "attempts": 1,
        "final_code": "print(1)",
    }


@pytest.mark.asyncio
async def test_run_single_verification_attempt_requests_retry_when_file_missing() -> (
    None
):
    agent = object.__new__(CoderAgent)
    agent.kernel = SimpleNamespace(get_service=lambda: object())
    agent._invoke_chat_with_fallbacks = AsyncMock(return_value="assistant response")
    agent._read_file = AsyncMock(side_effect=FileNotFoundError())
    agent.shell_skill = SimpleNamespace(
        run_shell=lambda _cmd, timeout=30: "",
        get_exit_code_from_output=lambda _output: 1,
    )
    history = ChatHistory()

    result = await CoderAgent._run_single_verification_attempt(
        agent,
        chat_history=history,
        script_name="script.py",
    )

    assert result["retry"] is True
    assert result["exit_code"] == 1
    assert len(history.messages) == 2
    assert history.messages[-1].role == AuthorRole.USER


@pytest.mark.asyncio
async def test_run_single_verification_attempt_executes_shell_on_saved_file() -> None:
    agent = object.__new__(CoderAgent)
    agent.kernel = SimpleNamespace(get_service=lambda: object())
    agent._invoke_chat_with_fallbacks = AsyncMock(return_value="assistant response")
    agent._read_file = AsyncMock(return_value="print('ok')")
    agent.shell_skill = SimpleNamespace(
        run_shell=lambda _cmd, timeout=30: "ok",
        get_exit_code_from_output=lambda _output: 0,
    )
    history = ChatHistory()

    result = await CoderAgent._run_single_verification_attempt(
        agent,
        chat_history=history,
        script_name="script.py",
    )

    assert result["retry"] is False
    assert result["exit_code"] == 0
    assert result["code_content"] == "print('ok')"


@pytest.mark.asyncio
async def test_process_with_verification_without_self_repair_uses_process() -> None:
    agent = object.__new__(CoderAgent)
    agent.enable_self_repair = False
    agent.process = AsyncMock(return_value="generated")

    result = await CoderAgent.process_with_verification(
        agent,
        "write helper",
        script_name="helper.py",
        max_retries=2,
    )

    assert result["success"] is True
    assert result["output"] == "generated"
    assert result["attempts"] == 1


@pytest.mark.asyncio
async def test_process_with_verification_returns_failure_when_attempts_raise() -> None:
    agent = object.__new__(CoderAgent)
    agent.enable_self_repair = True
    history = ChatHistory()
    agent._build_verification_chat_history = lambda *_args, **_kwargs: history
    agent._run_single_verification_attempt = AsyncMock(side_effect=RuntimeError("boom"))

    result = await CoderAgent.process_with_verification(
        agent,
        "write helper",
        script_name="helper.py",
        max_retries=2,
    )

    assert result["success"] is False
    assert result["attempts"] == 2
    assert "boom" in result["output"]
