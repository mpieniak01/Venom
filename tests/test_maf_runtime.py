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
    assert requests[0]["max_tokens"] == 12
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
    assert result.content == "gotowe"
    assert calls == ["ok"]
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
    prepared_settings = CompletionOptions()
    with pytest.raises(Exception, match="offline"):
        await model.get_chat_message_content(
            chat_history=history, settings=prepared_settings
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


@pytest.mark.asyncio
async def test_local_aliases_and_nonstandard_options_use_chat_completion_contract():
    bodies = []

    def respond(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=completion())

    model = service(respond)
    history = ConversationHistory()
    history.add_user_message("test")
    await model.get_chat_message_content(
        chat_history=history,
        settings=CompletionOptions(num_predict=17, top_k=7, repeat_penalty=1.1),
    )
    assert bodies[0]["max_tokens"] == 17
    assert "num_predict" not in bodies[0]
    assert bodies[0]["top_k"] == 7
    assert bodies[0]["repeat_penalty"] == 1.1
    await model.aclose()


@pytest.mark.asyncio
async def test_optional_settings_preserve_existing_dispatcher_call():
    model = service(lambda request: httpx.Response(200, json=completion()))
    history = ConversationHistory()
    history.add_user_message("test")
    assert (
        await model.get_chat_message_content(chat_history=history, settings=None)
    ).content == "odpowiedź"
    await model.aclose()


@pytest.mark.parametrize("field", ["model", "messages", "tools", "stream"])
def test_generation_extensions_cannot_override_routing_or_tool_policy(field):
    prepared_completion_options = CompletionOptions(extra_body={field: "override"})
    with pytest.raises(ValueError, match="cannot_override_transport"):
        MafChatService._options(prepared_completion_options)


def test_default_service_alias_preserves_named_local_runtime_selection():
    from types import SimpleNamespace

    runtime = AgentRuntime()
    local = SimpleNamespace(service_id="local")
    runtime.add_service(local)
    assert runtime.get_service("default") is local
    assert runtime.get_service() is local
    with pytest.raises(KeyError):
        runtime.get_service("missing")
    with pytest.raises(ValueError, match="duplicate_model_service"):
        runtime.add_service(local)


@pytest.mark.asyncio
async def test_action_specific_read_permission_does_not_grant_write(
    monkeypatch, tmp_path
):
    from venom_core.core.permission_guard import permission_guard
    from venom_core.execution.skills.file_skill import FileSkill

    monkeypatch.setattr(permission_guard, "_current_level", 0)
    (tmp_path / "existing.txt").write_text("read ok")
    runtime = AgentRuntime()
    runtime.add_plugin(FileSkill(workspace_root=str(tmp_path)), "Files")
    tools = {tool.name: tool for tool in runtime.native_tools()}
    assert await tools["Files-read_file"].func(file_path="existing.txt") == "read ok"
    with pytest.raises(Exception, match="Brak uprawnień"):
        await tools["Files-write_file"].func(file_path="forbidden.txt", content="no")
    assert not (tmp_path / "forbidden.txt").exists()


@pytest.mark.asyncio
async def test_custom_tool_cannot_self_declare_read_permissions(monkeypatch):
    from venom_core.core.permission_guard import permission_guard

    monkeypatch.setattr(permission_guard, "_current_level", 0)

    class CustomTool:
        @tool_function(name="custom", description="Untrusted")
        def custom(self) -> str:
            raise AssertionError("must never execute")

    CustomTool.custom.__venom_tool__["permission_skill"] = "FileReadSkill"
    runtime = AgentRuntime()
    runtime.add_plugin(CustomTool(), "Custom")
    prepared_operation = runtime.native_tools()[0].func
    with pytest.raises(Exception, match="Brak uprawnień"):
        prepared_operation()


@pytest.mark.asyncio
@pytest.mark.parametrize("is_async", [False, True])
async def test_integrator_reads_sync_and_async_platform_results_without_awaiting_strings(
    is_async,
):
    import threading
    from types import SimpleNamespace

    from venom_core.agents.integrator import IntegratorAgent

    main_thread = threading.get_ident()
    called_in = []

    def sync_issues(**kwargs):
        called_in.append(threading.get_ident())
        return "#42: real synchronous result"

    async def async_issues(**kwargs):
        return "#42: async adapter result"

    actor = object.__new__(IntegratorAgent)
    actor.platform_skill = SimpleNamespace(
        get_assigned_issues=async_issues if is_async else sync_issues
    )
    result = await actor.poll_issues()
    assert len(result) == 1
    assert result[0].startswith("#42:")
    if not is_async:
        assert called_in
        assert called_in[0] != main_thread


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "step",
    [
        {"action": "click"},
        {"action": "fill", "selector": "input"},
        {"action": "verify_text", "selector": "div"},
    ],
)
async def test_tester_rejects_invalid_scenario_before_browser_action(step):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from venom_core.agents.tester import TesterAgent

    actor = object.__new__(TesterAgent)
    actor.browser_skill = SimpleNamespace(
        click_element=AsyncMock(),
        fill_form=AsyncMock(),
        get_text_content=AsyncMock(),
        close_browser=AsyncMock(),
    )
    report = await actor.run_e2e_scenario("http://fixture.invalid", [step])
    assert "invalid_scenario_field:" in report
    actor.browser_skill.click_element.assert_not_called()
    actor.browser_skill.fill_form.assert_not_called()
    actor.browser_skill.get_text_content.assert_not_called()
    actor.browser_skill.close_browser.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_structured_review_schema_reaches_native_transport(stream):
    bodies = []
    text = json.dumps({"decision": "APPROVED", "feedback": "verified"})
    format_spec = {
        "type": "json_schema",
        "json_schema": {
            "name": "council_review",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string", "enum": ["APPROVED", "REVISE"]},
                    "feedback": {"type": "string"},
                },
                "required": ["decision", "feedback"],
                "additionalProperties": False,
            },
        },
    }

    def respond(request):
        bodies.append(json.loads(request.content))
        if not stream:
            return httpx.Response(200, json=completion(text))
        chunk = {
            "id": "structured",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "fixture-model",
            "choices": [
                {"index": 0, "delta": {"content": text}, "finish_reason": None}
            ],
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n",
        )

    model = service(respond)
    history = ConversationHistory(system_message="Review using the JSON schema")
    history.add_user_message("Candidate")
    settings = CompletionOptions(max_tokens=96, response_format=format_spec)
    if stream:
        fragments = []
        async for parts in model.get_streaming_chat_message_contents(
            chat_history=history, settings=settings
        ):
            fragments.extend(part.content for part in parts)
        result = "".join(fragments)
    else:
        result = (
            await model.get_chat_message_content(
                chat_history=history, settings=settings
            )
        ).content
    assert json.loads(result) == {"decision": "APPROVED", "feedback": "verified"}
    assert bodies[0]["response_format"] == format_spec
    assert bodies[0]["max_tokens"] == 96
    await model.aclose()


def test_completion_options_revalidate_mutated_instances():
    from pydantic import ValidationError

    options = CompletionOptions(max_tokens=8, temperature=0.2)
    options.max_tokens = 16
    assert CompletionOptions.model_validate(options).max_tokens == 16
    options.max_tokens = "invalid token count"
    with pytest.raises(ValidationError):
        CompletionOptions.model_validate(options)


@pytest.mark.asyncio
async def test_completed_tool_is_not_repeated_after_context_fallback():
    from venom_core.agents.base import BaseAgent

    effects = []
    requests = []
    continuation_failed = False

    class Tools:
        @tool_function(name="record", description="Record one fixture effect")
        async def record(self, text: str) -> str:
            effects.append(text)
            return "recorded"

    def respond(request):
        nonlocal continuation_failed
        body = json.loads(request.content)
        requests.append(body)
        if not any(message["role"] == "tool" for message in body["messages"]):
            call = {
                "id": f"call-{len(requests)}",
                "type": "function",
                "function": {
                    "name": "Safe-record",
                    "arguments": '{"text":"once"}',
                },
            }
            return httpx.Response(200, json=completion(None, [call]))
        if not continuation_failed:
            continuation_failed = True
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": (
                            "maximum context length is 64 tokens; "
                            "request has 32 input tokens"
                        ),
                        "type": "invalid_request_error",
                        "code": "context_length_exceeded",
                    }
                },
            )
        return httpx.Response(200, json=completion("done"))

    class Agent(BaseAgent):
        async def process(self, input_text):
            return input_text

    model = service(respond)
    runtime = AgentRuntime(permission_checker=lambda name: True)
    runtime.add_service(model)
    runtime.add_plugin(Tools(), "Safe")
    history = ConversationHistory()
    history.add_user_message("record once")
    settings = CompletionOptions(
        max_tokens=64, function_choice_behavior=ToolPolicy.Auto()
    )
    try:
        result = await Agent(runtime)._invoke_chat_with_fallbacks(
            model, history, settings, enable_functions=True
        )
        assert result.content == "done"
        assert effects == ["once"]
        assert len(requests) == 3
        assert [message["role"] for message in requests[2]["messages"]] == [
            "user",
            "assistant",
            "tool",
        ]
        assert requests[2]["messages"][1]["tool_calls"][0]["id"] == "call-1"
        assert requests[2]["messages"][2]["tool_call_id"] == "call-1"
        assert [str(message.role) for message in history] == [
            "user",
            "assistant",
            "tool",
        ]
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["provider_error", "cancellation"])
async def test_completed_tool_history_survives_failed_continuation(failure):
    import asyncio

    effects = []
    continuation_started = asyncio.Event()
    fail_continuation = True

    class Tools:
        @tool_function(name="record", description="Record one fixture effect")
        async def record(self, text: str) -> str:
            effects.append(text)
            return "recorded"

    async def respond(request):
        body = json.loads(request.content)
        if not any(message["role"] == "tool" for message in body["messages"]):
            call = {
                "id": "completed-call",
                "type": "function",
                "function": {
                    "name": "Safe-record",
                    "arguments": '{"text":"once"}',
                },
            }
            return httpx.Response(200, json=completion(None, [call]))
        if fail_continuation:
            continuation_started.set()
            if failure == "cancellation":
                await asyncio.Event().wait()
            return httpx.Response(503, json={"error": {"message": "offline"}})
        return httpx.Response(200, json=completion("done"))

    model = service(respond)
    runtime = AgentRuntime(permission_checker=lambda name: True)
    runtime.add_service(model)
    runtime.add_plugin(Tools(), "Safe")
    history = ConversationHistory()
    history.add_user_message("record once")
    settings = CompletionOptions(function_choice_behavior=ToolPolicy.Auto())
    task = asyncio.create_task(
        model.get_chat_message_content(
            chat_history=history, settings=settings, kernel=runtime
        )
    )
    try:
        await asyncio.wait_for(continuation_started.wait(), timeout=2)
        if failure == "cancellation":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(Exception, match="offline"):
                await task
        assert effects == ["once"]
        assert [str(message.role) for message in history] == [
            "user",
            "assistant",
            "tool",
        ]
        assert history[1].native_message.contents[0].call_id == "completed-call"
        assert history[2].native_message.contents[0].call_id == "completed-call"

        fail_continuation = False
        result = await model.get_chat_message_content(
            chat_history=history, settings=settings, kernel=runtime
        )
        assert result.content == "done"
        assert effects == ["once"]
        assert len(history) == 3
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await runtime.aclose()


@pytest.fixture
def maf_admission(tmp_path, monkeypatch):
    from venom_core.services import runtime_admission

    admission = runtime_admission.RuntimeAdmission(tmp_path / "maf-ledger.sqlite3")
    monkeypatch.setattr(runtime_admission, "_ADMISSION", admission)
    return admission


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 413, 415, 422])
@pytest.mark.parametrize("stream", [False, True])
async def test_maf_rejected_http_releases_own_operation(maf_admission, status, stream):
    model = service(
        lambda request: httpx.Response(
            status, json={"error": {"message": "rejected fixture"}}
        )
    )
    history = ConversationHistory(system_message="fixture")
    history.add_user_message("fixture")
    try:
        with pytest.raises(Exception, match="rejected fixture") as caught:
            if stream:
                async for _ in model.get_streaming_chat_message_contents(
                    chat_history=history
                ):
                    pytest.fail("rejected request must not produce content")
            else:
                await model.get_chat_message_content(chat_history=history)
        assert caught.value.__cause__ is not None
        assert maf_admission.snapshot()["status"] == "available"
        assert maf_admission.snapshot()["active_operations"] == 0
    finally:
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_maf_unknown_server_failure_remains_quarantined(maf_admission, status):
    model = service(
        lambda request: httpx.Response(
            status, json={"error": {"message": "uncertain fixture"}}
        )
    )
    try:
        with pytest.raises(Exception, match="uncertain fixture"):
            await model.get_chat_message_content(
                chat_history=ConversationHistory(system_message="fixture")
            )
        assert maf_admission.snapshot()["status"] == "quarantined"
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_maf_timeout_before_later_rejection_stays_quarantined(maf_admission):
    from venom_core.execution.maf_transport import maf_transport_scope

    attempts = 0

    def respond(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("unknown first attempt", request=request)
        return httpx.Response(400, json={"error": {"message": "later rejection"}})

    model = service(respond)
    client = model._owned_client
    try:
        with pytest.raises(Exception, match="later rejection"):
            with maf_admission.operation(kind="maf_generation"), maf_transport_scope():
                with pytest.raises(Exception, match="timed out"):
                    await client.chat.completions.create(model="fixture", messages=[])
                await client.chat.completions.create(model="fixture", messages=[])
        assert attempts == 2
        assert maf_admission.snapshot()["status"] == "quarantined"
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_maf_stream_eof_without_done_keeps_quarantine(maf_admission):
    packet = {
        "id": "fixture",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "fixture",
        "choices": [
            {"index": 0, "delta": {"content": "partial"}, "finish_reason": None}
        ],
    }
    model = service(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="data: " + json.dumps(packet) + "\n\n",
        )
    )
    try:
        with pytest.raises(Exception, match="upstream_stream_incomplete"):
            async for _ in model.get_streaming_chat_message_contents(
                chat_history=ConversationHistory(system_message="fixture")
            ):
                pass
        assert maf_admission.snapshot()["status"] == "quarantined"
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_maf_done_stream_releases_admission(maf_admission):
    model = service(
        lambda request: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, text="data: [DONE]\n\n"
        )
    )
    try:
        async for _ in model.get_streaming_chat_message_contents(
            chat_history=ConversationHistory(system_message="fixture")
        ):
            pass
        assert maf_admission.snapshot()["status"] == "available"
    finally:
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("first_status", [200, 503])
async def test_maf_followup_rejection_requires_completed_prior_response(
    maf_admission, first_status
):
    from venom_core.execution.maf_transport import maf_transport_scope

    attempts = 0

    def respond(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                first_status,
                json=completion()
                if first_status == 200
                else {"error": {"message": "unknown attempt"}},
            )
        return httpx.Response(422, json={"error": {"message": "followup rejected"}})

    model = service(respond)
    try:
        with pytest.raises(Exception, match="followup rejected"):
            with maf_admission.operation(kind="maf_generation"), maf_transport_scope():
                try:
                    await model._owned_client.chat.completions.create(
                        model="fixture", messages=[]
                    )
                except Exception:
                    assert first_status == 503
                await model._owned_client.chat.completions.create(
                    model="fixture", messages=[]
                )
        assert maf_admission.snapshot()["status"] == (
            "available" if first_status == 200 else "quarantined"
        )
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_maf_rejection_cannot_mask_later_timeout(maf_admission):
    from venom_core.execution.maf_transport import maf_transport_scope

    attempts = 0

    def respond(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(400, json={"error": {"message": "rejected"}})
        raise httpx.ReadTimeout("unknown followup", request=request)

    model = service(respond)
    try:
        with pytest.raises(Exception, match="timed out"):
            with maf_admission.operation(kind="maf_generation"), maf_transport_scope():
                with pytest.raises(Exception, match="rejected"):
                    await model._owned_client.chat.completions.create(
                        model="fixture", messages=[]
                    )
                await model._owned_client.chat.completions.create(
                    model="fixture", messages=[]
                )
        assert maf_admission.snapshot()["status"] == "quarantined"
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_maf_real_stream_close_keeps_uncertain_work_and_cleans_context(
    maf_admission,
):
    from venom_core.execution import maf_transport

    class Interrupted(httpx.AsyncByteStream):
        async def __aiter__(self):
            packet = {
                "id": "fixture",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "fixture",
                "choices": [
                    {"index": 0, "delta": {"content": "partial"}, "finish_reason": None}
                ],
            }
            yield ("data: " + json.dumps(packet) + "\n\n").encode()
            raise httpx.ReadError("interrupted fixture")

    model = service(
        lambda request: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=Interrupted()
        )
    )
    iterator = model.get_streaming_chat_message_contents(
        chat_history=ConversationHistory(system_message="fixture")
    )
    try:
        assert (await anext(iterator))[0].content == "partial"
        await iterator.aclose()
        assert maf_admission.snapshot()["status"] == "quarantined"
        assert maf_transport._EVIDENCE.get() is None
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_maf_stream_transport_error_is_not_rejection(maf_admission):
    class Interrupted(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b": keepalive\n\n"
            raise httpx.ReadError("interrupted fixture")

    model = service(
        lambda request: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=Interrupted()
        )
    )
    try:
        with pytest.raises(Exception, match="interrupted fixture"):
            async for _ in model.get_streaming_chat_message_contents(
                chat_history=ConversationHistory(system_message="fixture")
            ):
                pass
        assert maf_admission.snapshot()["status"] == "quarantined"
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_maf_serializes_negative_keep_alive_as_number_for_ollama():
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion())

    model = service(respond)
    try:
        await model.get_chat_message_content(
            chat_history=ConversationHistory(system_message="fixture"),
            settings=CompletionOptions(extra_body={"keep_alive": "-1"}),
        )
        assert requests[0]["keep_alive"] == -1
        assert type(requests[0]["keep_alive"]) is int
    finally:
        await model.aclose()
