"""Remote target selection, admission and UI administration use fixtures only."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from venom_core.api.routes import vast_chat
from venom_core.api.routes.vast_chat import AttachRequest
from venom_core.api.schemas.system_llm import ActiveLlmServerRequest
from venom_core.services import runtime_admission as admission
from venom_core.services import runtime_switch_gate as gate
from venom_core.services import vast_chat_model_config as model_config
from venom_core.services import vast_chat_runtime as remote

PLAN = "a" * 32
TARGET = f"ollama@vast:{PLAN}:42"
DIGEST = "d" * 64


@pytest.fixture
def target(tmp_path, monkeypatch):
    state = {
        "target_id": TARGET,
        "generation": "generation-one",
        "available": True,
        "endpoint": "http://127.0.0.1:15434/v1",
        "version": "0.40.11",
        "models": [{"name": "demo:latest", "digest": DIGEST, "size": 1024}],
        "error": None,
    }
    connection = Mock()
    connection.status.side_effect = lambda refresh=True: copy.deepcopy(state)
    connection.attach.side_effect = lambda plan: copy.deepcopy(state)
    connection.detach.return_value = {
        **state,
        "available": False,
        "endpoint": None,
        "models": [],
    }
    monkeypatch.setattr(remote, "_SELECTION", tmp_path / "selection.json")
    monkeypatch.setattr(remote, "_selected", None)
    monkeypatch.setattr(remote, "connection", lambda: connection)
    monkeypatch.setattr(
        admission,
        "_ADMISSION",
        admission.RuntimeAdmission(tmp_path / "admission.sqlite"),
    )
    with gate._STATE_LOCK:
        monkeypatch.setattr(gate, "_STATE", gate._RuntimeSwitchGateState())
    return state, connection


def select():
    return asyncio.run(remote.select_model("demo:latest"))


def test_remote_selection_keeps_local_settings_untouched(target):
    from venom_core.config import SETTINGS

    before = (
        SETTINGS.LLM_LOCAL_ENDPOINT,
        SETTINGS.ACTIVE_LLM_SERVER,
        SETTINGS.LLM_MODEL_NAME,
    )
    result = select()
    assert result["active_server"] == remote.SERVER
    assert result["active_model"] == "demo:latest"
    assert before == (
        SETTINGS.LLM_LOCAL_ENDPOINT,
        SETTINGS.ACTIVE_LLM_SERVER,
        SETTINGS.LLM_MODEL_NAME,
    )
    saved = json.loads(remote._SELECTION.read_text())
    assert saved == {"target_id": TARGET, "model": "demo:latest", "digest": DIGEST}
    assert remote._SELECTION.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("change", ["unavailable", "different-target", "no-endpoint"])
def test_selected_unavailable_target_never_becomes_local(target, change):
    state, _ = target
    select()
    if change == "different-target":
        state["target_id"] = f"ollama@vast:{'b' * 32}:43"
    elif change == "no-endpoint":
        state["endpoint"] = None
    else:
        state.update(available=False, endpoint=None)
    runtime = remote.runtime_override()
    assert runtime is not None
    assert remote.is_remote(runtime)
    assert TARGET in runtime.runtime_id
    assert runtime.endpoint is None
    assert remote.server_name(runtime) == remote.SERVER


def test_runtime_identity_tracks_generation_and_model_digest(target):
    state, _ = target
    select()
    first = remote.runtime_override()
    state["generation"] = "generation-two"
    second = remote.runtime_override()
    assert first.runtime_id != second.runtime_id
    assert first.config_hash != second.config_hash
    state["models"][0]["digest"] = "e" * 64
    select()
    third = remote.runtime_override()
    assert third.runtime_id == second.runtime_id
    assert third.config_hash != second.config_hash


@pytest.mark.parametrize("change", ["unavailable", "target", "model", "digest"])
def test_generation_preflight_rejects_changed_remote_target(target, change):
    state, _ = target
    select()
    if change == "unavailable":
        state["available"] = False
    elif change == "target":
        state["target_id"] = f"ollama@vast:{'b' * 32}:43"
    elif change == "model":
        state["models"] = []
    else:
        state["models"][0]["digest"] = "f" * 64
    preflight = remote.preflight()
    with pytest.raises(HTTPException) as error:
        asyncio.run(preflight)
    assert error.value.status_code == 503
    assert remote.selection()["target_id"] == TARGET


def test_preflight_and_override_are_noops_without_remote_selection(target):
    _, connection = target
    assert remote.runtime_override() is None
    asyncio.run(remote.preflight())
    connection.status.assert_not_called()


def test_generation_guard_does_not_enter_body_after_remote_disappears(target):
    state, _ = target
    select()
    state["available"] = False
    reached = []

    async def attempt():
        async with gate.runtime_request_guard(request_kind="simple_chat"):
            reached.append(True)

    operation = attempt()
    with pytest.raises(HTTPException) as error:
        asyncio.run(operation)
    assert error.value.status_code == 503
    assert reached == []
    assert gate.get_runtime_switch_gate_snapshot().active_requests == 0


def test_expected_identity_prevents_generation_after_reconnect(target):
    state, _ = target
    select()
    old = remote.runtime_override()
    state["generation"] = "new-generation"
    current = remote.runtime_override()
    with pytest.raises(HTTPException) as error:
        remote.assert_identity(current, old.runtime_id, old.config_hash)
    assert error.value.status_code == 409


def test_clear_selection_explicitly_restores_local_runtime(target):
    select()
    remote.clear_selection()
    assert remote.runtime_override() is None
    assert json.loads(remote._SELECTION.read_text()) is None


@pytest.mark.parametrize("payload", ["{", "[]", "{}", '{"target_id":"other"}'])
def test_corrupt_persisted_selection_is_fail_closed(target, monkeypatch, payload):
    remote._SELECTION.write_text(payload)
    monkeypatch.setattr(remote, "_selected", remote._UNSET)
    runtime = remote.runtime_override()
    assert runtime is not None
    assert remote.is_remote(runtime)
    assert runtime.endpoint is None
    preflight = remote.preflight()
    with pytest.raises(HTTPException) as error:
        asyncio.run(preflight)
    assert error.value.status_code == 503


@pytest.mark.parametrize("instance_suffix", ["42١", "42１"])
def test_persisted_target_rejects_non_ascii_instance_digits(
    target, monkeypatch, instance_suffix
):
    remote._SELECTION.write_text(
        json.dumps(
            {
                "target_id": f"ollama@vast:{PLAN}:{instance_suffix}",
                "model": "demo:latest",
                "digest": DIGEST,
            }
        )
    )
    monkeypatch.setattr(remote, "_selected", remote._UNSET)
    assert remote.selection()["target_id"] == "ollama@vast:unavailable"
    runtime = remote.runtime_override()
    assert runtime is not None
    assert remote.is_remote(runtime)
    assert runtime.endpoint is None
    preflight = remote.preflight()
    with pytest.raises(HTTPException) as error:
        asyncio.run(preflight)
    assert error.value.status_code == 503


def test_model_config_is_scoped_to_remote_target_not_local_ollama(target):
    state, _ = target
    assert model_config.scope("ollama") is None
    assert model_config.scope(remote.SERVER) == remote.SERVER + "@" + TARGET
    select()
    assert model_config.scope(None) == remote.SERVER + "@" + TARGET
    state["target_id"] = f"ollama@vast:{'b' * 32}:43"
    assert model_config.scope(remote.SERVER) != remote.SERVER + "@" + TARGET


def test_model_capabilities_use_same_remote_endpoint(target):
    _, connection = target
    connection.model_details.return_value = {
        "capabilities": ["completion"],
        "details": {"family": "fixture", "parameter_size": "1B"},
        "model_info": {"general.architecture": "fixture"},
    }
    result = model_config.capabilities("demo:latest")
    connection.model_details.assert_called_once_with("demo:latest")
    assert result["success"]
    assert result["runtime_capabilities"]["runtime_id"] == TARGET + ":generation-one"


def test_model_config_rejects_local_only_or_missing_remote_model(target):
    state, _ = target
    with pytest.raises(HTTPException) as error:
        model_config.require_model("local-only")
    assert error.value.status_code == 404
    state["available"] = False
    with pytest.raises(HTTPException) as error:
        model_config.require_model("demo:latest")
    assert error.value.status_code == 503


def test_target_payload_exposes_only_remote_models_and_unavailable_is_empty(target):
    state, _ = target
    select()
    payload = asyncio.run(remote.target_payload())
    assert payload["runtime_id"] == remote.SERVER
    assert payload["models"][0]["digest"] == DIGEST
    assert payload["models"][0]["active"]
    state.update(available=False, models=[])
    payload = asyncio.run(remote.target_payload())
    assert not payload["available"]
    assert payload["models"] == []


def test_api_attach_rejects_remote_request_before_ssh(target):
    _, connection = target
    app = FastAPI()
    app.include_router(vast_chat.router, prefix="/api/v1")
    with TestClient(app, client=("203.0.113.5", 40000)) as client:
        response = client.post(
            "/api/v1/system/vast-chat/attach", json={"plan_id": PLAN}
        )
    assert response.status_code == 403
    connection.attach.assert_not_called()


def test_api_local_attach_and_detach_do_not_change_selection(target):
    _, connection = target
    select()
    app = FastAPI()
    app.include_router(vast_chat.router, prefix="/api/v1")
    with TestClient(app, client=("127.0.0.1", 40000)) as client:
        response = client.post(
            "/api/v1/system/vast-chat/attach", json={"plan_id": PLAN}
        )
        assert response.status_code == 200
        response = client.post("/api/v1/system/vast-chat/detach")
        assert response.status_code == 200
    connection.attach.assert_called_once_with(PLAN)
    connection.detach.assert_called_once()
    assert remote.selection()["target_id"] == TARGET


def test_api_attach_other_plan_is_rejected_while_remote_selected(target):
    _, connection = target
    select()
    request = AttachRequest(plan_id="b" * 32)
    activation = vast_chat.attach(request)
    with pytest.raises(HTTPException) as error:
        asyncio.run(activation)
    assert error.value.status_code == 409
    connection.attach.assert_not_called()


def test_activate_drains_requests_and_releases_switch_on_failure(target, monkeypatch):
    from venom_core.utils import llm_runtime

    active = SimpleNamespace(provider="ollama", runtime_id="ollama@local")
    monkeypatch.setattr(llm_runtime, "get_active_llm_runtime", lambda: active)
    monkeypatch.setattr(
        vast_chat, "assert_runtime_switch_source_allowed", lambda value: value
    )
    monkeypatch.setattr(
        vast_chat, "assert_runtime_switch_ownership_token", lambda token: None
    )
    monkeypatch.setattr(
        vast_chat, "wait_for_runtime_requests_to_drain", AsyncMock(return_value=False)
    )
    request = ActiveLlmServerRequest(server_name=remote.SERVER, model="demo:latest")
    activation = vast_chat.activate(request, "ui")
    with pytest.raises(HTTPException) as error:
        asyncio.run(activation)
    assert error.value.status_code == 409
    assert not gate.get_runtime_switch_gate_snapshot().in_progress
    assert remote.selection() is None


def test_kernel_local_service_uses_selected_remote_model_and_endpoint(target):
    from venom_core.execution.kernel_builder import KernelBuilder

    state, _ = target
    select()
    builder = object.__new__(KernelBuilder)
    from venom_core.config import SETTINGS

    builder.settings = SETTINGS
    register = Mock()
    builder._register_local_http_service = register
    kernel = Mock()
    builder._register_local_service(kernel, "local_llm", "local-name", False)
    register.assert_called_once_with(
        kernel,
        "local_llm",
        "demo:latest",
        state["endpoint"],
        api_key="ollama",
        max_retries=0,
    )


def test_kernel_cannot_build_local_client_for_offline_selected_target(target):
    from venom_core.execution.kernel_builder import KernelBuilder

    state, _ = target
    select()
    state.update(available=False, endpoint=None)
    builder = object.__new__(KernelBuilder)
    from venom_core.config import SETTINGS

    builder.settings = SETTINGS
    builder._register_local_http_service = Mock()
    kernel = Mock()
    with pytest.raises(ValueError, match="vast_chat_target_unavailable"):
        builder._register_local_service(kernel, "local_llm", "local-name", False)
    builder._register_local_http_service.assert_not_called()


def test_kernel_remote_selection_overrides_cloud_service_configuration(
    target, monkeypatch
):
    from venom_core.config import SETTINGS
    from venom_core.execution.kernel_builder import KernelBuilder

    select()
    monkeypatch.setattr(SETTINGS, "LLM_SERVICE_TYPE", "openai")
    monkeypatch.setattr(SETTINGS, "AI_MODE", "HYBRID")
    monkeypatch.setattr(SETTINGS, "FORCE_LOCAL_MODEL", False)
    builder = KernelBuilder(settings=SETTINGS, enable_routing=False)
    builder._register_service = Mock()
    builder._register_local_http_service = Mock()
    builder.build_kernel()
    builder._register_service.assert_not_called()
    assert builder._register_local_http_service.call_args.args[2] == "demo:latest"
    assert (
        builder._register_local_http_service.call_args.args[3] == target[0]["endpoint"]
    )


def test_successful_activation_uses_shared_switch_and_saves_model(target, monkeypatch):
    from venom_core.utils import llm_runtime

    active = SimpleNamespace(provider="ollama", runtime_id="ollama@local")
    monkeypatch.setattr(llm_runtime, "get_active_llm_runtime", lambda: active)
    monkeypatch.setattr(
        vast_chat, "assert_runtime_switch_source_allowed", lambda value: value
    )
    monkeypatch.setattr(
        vast_chat, "assert_runtime_switch_ownership_token", lambda token: None
    )
    wait = AsyncMock(return_value=True)
    monkeypatch.setattr(vast_chat, "wait_for_runtime_requests_to_drain", wait)
    request = ActiveLlmServerRequest(server_name=remote.SERVER, model="demo:latest")
    result = asyncio.run(vast_chat.activate(request, "ui"))
    assert result["active_model"] == "demo:latest"
    wait.assert_awaited_once()
    assert not gate.get_runtime_switch_gate_snapshot().in_progress
    assert remote.selection()["target_id"] == TARGET


def test_remote_sdk_does_not_retry_generation_and_local_defaults_are_unchanged(
    target, monkeypatch
):
    from venom_core.execution import kernel_builder
    from venom_core.execution.kernel_builder import KernelBuilder

    factory = Mock()
    monkeypatch.setattr(kernel_builder, "AsyncOpenAI", factory)
    monkeypatch.setattr(kernel_builder, "MafChatService", Mock())
    builder = object.__new__(KernelBuilder)
    builder.settings = SimpleNamespace(LLM_LOCAL_API_KEY="local-fixture-key")
    kernel = Mock()
    builder._register_local_http_service(
        kernel,
        "local",
        "remote-model",
        target[0]["endpoint"],
        api_key="ollama",
        max_retries=0,
    )
    assert factory.call_args.kwargs == {
        "api_key": "ollama",
        "base_url": target[0]["endpoint"],
        "max_retries": 0,
    }
    factory.reset_mock()
    builder._register_local_http_service(
        kernel, "local", "local-model", "http://localhost:11434/v1"
    )
    assert factory.call_args.kwargs == {
        "api_key": "local-fixture-key",
        "base_url": "http://localhost:11434/v1",
    }


def test_direct_service_uses_remote_history_endpoint_and_no_local_adapter(
    target, monkeypatch
):
    from venom_core.api.schemas.llm_simple import SimpleChatRequest
    from venom_core.services import llm_simple_service as simple

    state, _ = target
    select()
    runtime = remote.runtime_override()
    monkeypatch.setattr(simple, "_trace_simple_request", Mock())
    monkeypatch.setattr(simple, "_trace_context_preview", Mock())
    adapter = AsyncMock(side_effect=AssertionError("local adapter must not be queried"))
    monkeypatch.setattr(simple, "_get_active_adapter_id", adapter)
    captured = {}

    async def stream(**kwargs):
        captured.update(kwargs)
        yield "event: done\\ndata: {}\\n\\n"

    monkeypatch.setattr(simple, "_stream_simple_chunks", stream)
    request = SimpleChatRequest(
        content="second prompt",
        model="demo:latest",
        expected_runtime_id=runtime.runtime_id,
        expected_config_hash=runtime.config_hash,
        history=[
            {"role": "user", "content": "first prompt"},
            {"role": "assistant", "content": "first answer"},
        ],
    )

    async def run():
        response = await simple.stream_simple_chat(request)
        return [chunk async for chunk in response.body_iterator]

    assert asyncio.run(run())
    adapter.assert_not_awaited()
    assert captured["completions_url"] == state["endpoint"] + "/chat/completions"
    assert captured["payload"]["model"] == "demo:latest"
    assert captured["payload"]["messages"][-3:] == [
        {"role": "user", "content": "first prompt"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second prompt"},
    ]
    assert "keep_alive" not in captured["payload"]
    assert "options" not in captured["payload"]


@pytest.mark.parametrize("change", ["runtime", "model", "history"])
def test_direct_service_rejects_drift_or_oversized_history_before_stream(
    target, monkeypatch, change
):
    from venom_core.api.schemas.llm_simple import SimpleChatRequest
    from venom_core.services import llm_simple_service as simple

    select()
    runtime = remote.runtime_override()
    monkeypatch.setattr(simple, "_trace_simple_request", Mock())
    monkeypatch.setattr(simple, "_trace_context_preview", Mock())
    stream = Mock(side_effect=AssertionError("must reject before stream"))
    monkeypatch.setattr(simple, "_stream_simple_chunks", stream)
    values = {
        "content": "prompt",
        "model": "demo:latest",
        "expected_runtime_id": runtime.runtime_id,
        "expected_config_hash": runtime.config_hash,
    }
    if change == "runtime":
        values["expected_runtime_id"] = runtime.runtime_id + "-old"
    elif change == "model":
        values["model"] = "local-only"
    else:
        values["history"] = [
            {"role": "user", "content": "x" * 30000},
            {"role": "assistant", "content": "y" * 30000},
        ]
    request = SimpleChatRequest(**values)
    stream_operation = simple.stream_simple_chat(request)
    with pytest.raises(HTTPException) as error:
        asyncio.run(stream_operation)
    assert error.value.status_code == (400 if change == "history" else 409)
    stream.assert_not_called()


def test_remote_form_defaults_are_read_from_remote_show(target):
    _state, connection = target
    connection.model_details.return_value = {
        "parameters": "temperature 0.25\ntop_p 0.8\nnum_predict 512\nnum_ctx 32768\ntop_k nan"
    }
    schema = model_config.generation_schema("demo:latest")
    assert schema["temperature"].default == 0.25
    assert schema["top_p"].default == 0.8
    assert schema["max_tokens"].default == 512
    assert schema["top_k"].default == 40


@pytest.mark.parametrize("failure", ["offline", "digest", "identity", "cancel"])
def test_rejected_preflight_releases_admission_for_target_switch(
    target, tmp_path, monkeypatch, failure
):
    state, _ = target
    select()
    runtime = remote.runtime_override()
    ledger = admission.RuntimeAdmission(tmp_path / "enabled.sqlite", enabled=True)
    monkeypatch.setattr(admission, "_ADMISSION", ledger)
    expected_id = runtime.runtime_id
    if failure == "offline":
        state["available"] = False
    elif failure == "digest":
        state["models"][0]["digest"] = "f" * 64
    elif failure == "identity":
        expected_id += "-stale"
    else:
        monkeypatch.setattr(
            remote, "preflight", AsyncMock(side_effect=asyncio.CancelledError)
        )

    async def attempt():
        async with gate.runtime_request_guard(
            request_kind="simple_chat_stream", expected_runtime_id=expected_id
        ):
            pytest.fail("Preflight must reject before generation starts")

    error = asyncio.CancelledError if failure == "cancel" else HTTPException
    operation = attempt()
    with pytest.raises(error):
        asyncio.run(operation)
    assert ledger.snapshot()["active_operations"] == 0
    assert gate.get_runtime_switch_gate_snapshot().active_requests == 0
    with ledger.operation(kind="runtime_switch", mutation=True):
        remote.clear_selection()
    assert remote.selection() is None


@pytest.mark.parametrize("failure", ["error", "cancel"])
def test_dispatched_generation_retains_uncertainty_and_blocks_switch(
    target, tmp_path, monkeypatch, failure
):
    select()
    ledger = admission.RuntimeAdmission(tmp_path / "enabled.sqlite", enabled=True)
    monkeypatch.setattr(admission, "_ADMISSION", ledger)

    async def attempt():
        async with gate.runtime_request_guard(request_kind="simple_chat_stream"):
            if failure == "cancel":
                raise asyncio.CancelledError
            raise HTTPException(503, "Generation failed after dispatch")

    error = asyncio.CancelledError if failure == "cancel" else HTTPException
    operation = attempt()
    with pytest.raises(error):
        asyncio.run(operation)
    assert ledger.snapshot()["active_operations"] == 1
    assert gate.get_runtime_switch_gate_snapshot().active_requests == 0

    def attempt_switch():
        with ledger.operation(kind="runtime_switch", mutation=True):
            pytest.fail("Uncertain generation must still prevent switching")

    with pytest.raises(admission.RuntimeAdmissionError):
        attempt_switch()


@pytest.mark.parametrize("host,expected", [("127.0.0.1", 200), ("203.0.113.5", 403)])
def test_api_status_is_local_administration_only(target, host, expected):
    _, connection = target
    connection.status.reset_mock()
    app = FastAPI()
    app.include_router(vast_chat.router, prefix="/api/v1")
    with TestClient(app, client=(host, 40000)) as client:
        result = client.get("/api/v1/system/vast-chat")
    assert result.status_code == expected
    assert connection.status.call_count == (1 if expected == 200 else 0)


@pytest.mark.parametrize("provider", ["openai", "onnx"])
def test_failed_activation_preserves_local_model_with_vast_selected(
    target, monkeypatch, provider
):
    from venom_core.api.routes import system_llm

    select()
    for name, value in {
        "LLM_MODEL_NAME": "local-only",
        "LLM_SERVICE_TYPE": "local",
        "ACTIVE_LLM_SERVER": "ollama",
        "LLM_CONFIG_HASH": "local-hash",
    }.items():
        monkeypatch.setattr(system_llm.SETTINGS, name, value)
    monkeypatch.setattr(
        system_llm,
        "get_active_llm_runtime",
        lambda settings=None: remote.runtime_override()
        if settings is None
        else SimpleNamespace(config_hash="candidate"),
    )
    monkeypatch.setattr(
        system_llm.config_manager,
        "update_config",
        Mock(side_effect=RuntimeError("save failed")),
    )
    if provider == "onnx":
        monkeypatch.setattr(system_llm, "_ensure_server_allowed", lambda _: None)
        monkeypatch.setattr(
            system_llm.system_llm_service,
            "inspect_onnx_worker",
            AsyncMock(return_value={"ready": True, "models": ["candidate"]}),
        )
    if provider == "onnx":
        activation = system_llm._activate_onnx_runtime("candidate")
        with pytest.raises(RuntimeError, match="save failed"):
            asyncio.run(activation)
    else:
        with pytest.raises(RuntimeError, match="save failed"):
            system_llm._activate_cloud_runtime(provider, "candidate")
    assert system_llm.SETTINGS.LLM_MODEL_NAME == "local-only"
    assert system_llm.SETTINGS.LLM_SERVICE_TYPE == "local"
    assert system_llm.SETTINGS.ACTIVE_LLM_SERVER == "ollama"
    assert system_llm.SETTINGS.LLM_CONFIG_HASH == "local-hash"
    assert remote.selection()["model"] == "demo:latest"
