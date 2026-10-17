"""Real MAF + OpenAI SDK transport tests, without network/models or hardware."""

import json

import httpx
import pytest
from openai import AsyncOpenAI

from venom_core.execution.agent_contracts import (
    CompletionOptions,
    ConversationHistory,
    ToolPolicy,
    tool_function,
)
from venom_core.execution.maf_runtime import AgentRuntime, MafChatService


def completion(text="odpowiedź", calls=None):
    message = {"role": "assistant", "content": text}
    if calls is not None:
        message["tool_calls"] = calls
    return {
        "id": "test",
        "object": "chat.completion",
        "created": 1,
        "model": "fixture-model",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if calls else "stop",
            }
        ],
    }


def service(handler):
    client = AsyncOpenAI(
        api_key="local-fixture",
        base_url="http://fixture.invalid/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    return MafChatService("local", "fixture-model", async_client=client)


@pytest.mark.asyncio
async def test_native_maf_completion_preserves_messages_options_and_model():
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion())

    model = service(respond)
    history = ConversationHistory(system_message="instrukcja")
    history.add_user_message("pytanie")
    result = await model.get_chat_message_content(
        chat_history=history, settings=CompletionOptions(temperature=0.2, max_tokens=12)
    )
    assert result.content == "odpowiedź"
    assert requests[0]["model"] == "fixture-model"
    assert [m["role"] for m in requests[0]["messages"]] == ["system", "user"]
    assert requests[0]["temperature"] == 0.2
    assert len(history) == 2
    await model.aclose()


@pytest.mark.asyncio
async def test_native_maf_executes_bound_tool_once_and_sends_result():
    calls = []

    class Tools:
        @tool_function(name="echo", description="Return text")
        async def echo(self, text: str) -> str:
            calls.append(text)
            return "wynik: " + text

    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            tool = {
                "id": "call-1",
                "type": "function",
                "function": {"name": "Safe-echo", "arguments": '{"text":"ok"}'},
            }
            return httpx.Response(200, json=completion(None, [tool]))
        return httpx.Response(200, json=completion("gotowe"))

    model = service(respond)
    runtime = AgentRuntime(permission_checker=lambda name: True)
    runtime.add_service(model)
    runtime.add_plugin(Tools(), "Safe")
    history = ConversationHistory()
    history.add_user_message("echo")
    result = await model.get_chat_message_content(
        chat_history=history,
        settings=CompletionOptions(function_choice_behavior=ToolPolicy.Auto()),
        kernel=runtime,
    )
    assert result.content == "gotowe" and calls == ["ok"]
    assert any(
        m["role"] == "tool" and "wynik: ok" in m["content"]
        for m in requests[1]["messages"]
    )
    assert any(m.native_message is not None for m in history)
    await runtime.aclose()


@pytest.mark.asyncio
async def test_native_maf_stream_emits_text_deltas():
    chunks = [
        {
            "id": "stream",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "fixture-model",
            "choices": [
                {"index": 0, "delta": {"content": text}, "finish_reason": None}
            ],
        }
        for text in ["dzień ", "dobry"]
    ]
    data = (
        "".join("data: " + json.dumps(x) + "\n\n" for x in chunks) + "data: [DONE]\n\n"
    )
    model = service(
        lambda request: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, text=data
        )
    )
    history = ConversationHistory()
    history.add_user_message("pytanie")
    result = []
    async for parts in model.get_streaming_chat_message_contents(
        chat_history=history, settings=CompletionOptions()
    ):
        result.extend(p.content for p in parts)
    assert result == ["dzień ", "dobry"]
    await model.aclose()


@pytest.mark.asyncio
async def test_provider_failure_is_not_replaced_by_empty_success():
    model = service(
        lambda request: httpx.Response(503, json={"error": {"message": "offline"}})
    )
    history = ConversationHistory()
    history.add_user_message("pytanie")
    with pytest.raises(Exception, match="offline"):
        await model.get_chat_message_content(
            chat_history=history, settings=CompletionOptions()
        )
    await model.aclose()


@pytest.mark.asyncio
async def test_provider_extensions_reach_request_body_without_changing_model():
    bodies = []

    def respond(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=completion())

    model = service(respond)
    history = ConversationHistory()
    history.add_user_message("pytanie")
    await model.get_chat_message_content(
        chat_history=history, settings=CompletionOptions(extra_body={"top_k": 7})
    )
    assert bodies[0]["top_k"] == 7
    assert bodies[0]["model"] == "fixture-model"
    await model.aclose()


@pytest.mark.asyncio
async def test_native_tool_permission_is_checked_at_execution_and_denial_has_no_side_effect():
    calls = []

    class Tools:
        @tool_function(name="write", description="Write")
        async def write(self, text: str) -> str:
            calls.append(text)
            return text

    runtime = AgentRuntime(permission_checker=lambda name: False)
    runtime.add_plugin(Tools(), "Files")
    tool = runtime.native_tools()[0]
    with pytest.raises(PermissionError, match="permission_denied"):
        await tool.func(text="forbidden")
    assert calls == []


def test_native_filters_exclude_unselected_tools_and_groups():
    class Tools:
        @tool_function(name="one", description="One")
        def one(self) -> str:
            return "one"

        @tool_function(name="two", description="Two")
        def two(self) -> str:
            return "two"

    runtime = AgentRuntime()
    runtime.add_plugin(Tools(), "A")
    runtime.add_plugin(Tools(), "B")
    assert [
        t.name
        for t in runtime.native_tools(
            {"included_plugins": ["A"], "excluded_functions": ["A-two"]}
        )
    ] == ["A-one"]
    assert runtime.native_tools({"excluded_plugins": ["A", "B"]}) == []
    assert runtime.native_tools({"included_functions": []}) == []


@pytest.mark.asyncio
async def test_cancellation_propagates_without_fallback_or_assistant_history():
    import asyncio

    started = asyncio.Event()

    async def respond(request):
        started.set()
        await asyncio.Event().wait()

    model = service(respond)
    history = ConversationHistory()
    history.add_user_message("wait")
    task = asyncio.create_task(
        model.get_chat_message_content(
            chat_history=history, settings=CompletionOptions()
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(history) == 1
    await model.aclose()


@pytest.mark.asyncio
async def test_created_client_is_closed_on_shutdown():
    model = MafChatService(
        "local", "fixture", api_key="fixture", base_url="http://fixture.invalid/v1"
    )
    client = model._owned_client
    assert not client.is_closed()
    await model.aclose()
    assert client.is_closed()


@pytest.mark.asyncio
async def test_chat_agent_reaches_maf_once_without_test_shortcut_or_tool_planner(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace

    from venom_core.agents import base as base_agent
    from venom_core.agents import chat as chat_agent
    from venom_core.agents.chat import ChatAgent

    runtime_info = SimpleNamespace(provider="ollama", model_name="fixture-model")
    monkeypatch.setattr(chat_agent, "get_active_llm_runtime", lambda: runtime_info)
    monkeypatch.setattr(base_agent, "get_active_llm_runtime", lambda: runtime_info)
    monkeypatch.setattr(chat_agent.SETTINGS, "MEMORY_ROOT", str(tmp_path))
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion("stolica to Warszawa"))

    runtime = AgentRuntime()
    runtime.add_service(service(respond))
    result = await ChatAgent(runtime).process("Jaka jest stolica Polski?")
    assert result == "stolica to Warszawa"
    assert len(requests) == 1
    assert "tools" not in requests[0]
    await runtime.aclose()
