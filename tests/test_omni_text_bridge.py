"""Native PEFT chat uses verified weights and preserves atomic history selection."""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN
from venom_core.api.routes import llm_simple
from venom_core.api.schemas.llm_simple import HistoryMessage, SimpleChatRequest
from venom_core.services import omni_native_text as bridge
from venom_core.services.training_experiments.profiles import (
    digest,
    read_json,
    stable_hash,
)
from venom_core.utils.llm_runtime import LLMRuntimeInfo


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def native(tmp_path, monkeypatch):
    pin = read_json(SNAPSHOT_PIN)
    root, snapshot, env = (
        tmp_path / name for name in ("catalog", "snapshot", "python")
    )
    for p in (root, snapshot, env / "bin"):
        p.mkdir(parents=True)
    (env / "bin/python").symlink_to(Path(sys.executable).resolve())
    for name, val in (
        ("OMNI_NATIVE_TEXT_CATALOG_ROOT", root),
        ("OMNI_NATIVE_SNAPSHOT", snapshot),
        ("OMNI_NATIVE_TEXT_ENV", env),
    ):
        monkeypatch.setenv(name, str(val))
    for tag in ("p13", "candidate"):
        d = root / "adapters" / tag
        config = {
            "base_model_name_or_path": pin["repo"],
            "bias": "none",
            "lora_alpha": 8,
            "lora_dropout": 0.05,
            "peft_type": "LORA",
            "r": 4,
            "target_modules": r"model\.language_model\..*\.(q_proj|v_proj)",
            "task_type": "CAUSAL_LM",
        }
        write(d / "adapter_config.json", config)
        (d / "adapter_model.safetensors").write_bytes(tag.encode())
        hashes = {
            name: digest(d / name)
            for name in ("adapter_config.json", "adapter_model.safetensors")
        }
        write(d / "hashes.json", hashes)
        write(
            d / "adapter.json",
            {
                "schema_version": 1,
                "adapter_id": tag,
                "label": tag,
                "model": pin["repo"],
                "revision": pin["revision"],
                "snapshot_sha256": digest(SNAPSHOT_PIN),
                "config_sha256": hashes["adapter_config.json"],
                "weights_sha256": hashes["adapter_model.safetensors"],
                "source": {"identity": "fixture", "sha256": "a" * 64},
            },
        )
    monkeypatch.setattr(bridge, "_ACTIVE", None)
    monkeypatch.setattr(bridge, "_PREVIOUS", None)
    monkeypatch.setattr(bridge, "_ORDINARY", None)
    monkeypatch.setattr(bridge, "_LOCK", asyncio.Lock())
    runtime = LLMRuntimeInfo(
        "ollama", "previous-model", "http://127.0.0.1:11434", "local", "local"
    )
    monkeypatch.setattr(bridge, "get_active_llm_runtime", lambda: runtime)

    @asynccontextmanager
    async def guard(**kwargs):
        yield

    monkeypatch.setattr(bridge, "runtime_request_guard", guard)
    calls = []

    async def invoke(snapshot, payload, *, adapter, python_env):
        data = json.loads(payload)
        calls.append(data)
        return json.dumps(
            {
                "identity": data["identity"],
                "input_messages_sha256": stable_hash(data["messages"]),
                "snapshot_manifest_sha256": data["identity"]["snapshot_sha256"],
                "text": "Anna, 120 zł",
                "output_tokens": 5,
            }
        ).encode()

    monkeypatch.setattr(bridge.omni_native_dialogue, "_invoke", invoke)
    return root, calls


@pytest.mark.asyncio
async def test_switch_probes_and_preserves_history(native):
    root, calls = native
    result = await bridge.switch("p13")
    identity = result["selection"]
    assert len(calls) == 1 and calls[0]["max_tokens"] == 8
    request = SimpleChatRequest(
        content="Popraw osobę na Annę. Podaj pełny rekord.",
        history=[
            HistoryMessage(role="user", content="Jan, 120 zł"),
            HistoryMessage(role="assistant", content="Jan, 130 zł"),
        ],
    )
    response = await bridge.response(request)
    body = "".join([p async for p in response.body_iterator])
    assert calls[-1]["messages"] == [
        {"role": "user", "content": "Jan, 120 zł"},
        {"role": "assistant", "content": "Jan, 130 zł"},
        {"role": "user", "content": request.content},
    ]
    assert identity["weights_sha256"] in body and "event: content" in body
    assert "previous-model" in body
    await bridge.rollback(expected_runtime_id=identity["runtime_id"])
    assert not bridge.selected()


@pytest.mark.asyncio
async def test_failed_load_and_cancel_leave_previous_selection(native, monkeypatch):
    await bridge.switch("p13")
    old = bridge.state()

    async def fail(*args, **kwargs):
        raise OSError("load failed")

    monkeypatch.setattr(bridge.omni_native_dialogue, "_invoke", fail)
    with pytest.raises(HTTPException, match="omni_native_text_generation_failed"):
        await bridge.switch(
            "candidate", expected_runtime_id=old["selection"]["runtime_id"]
        )
    assert bridge.state() == old

    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(bridge.omni_native_dialogue, "_invoke", cancel)
    with pytest.raises(asyncio.CancelledError):
        await bridge.switch(
            "candidate", expected_runtime_id=old["selection"]["runtime_id"]
        )
    assert bridge.state() == old


@pytest.mark.asyncio
async def test_changed_weights_and_stale_selection_fail_closed(native):
    root, calls = native
    await bridge.switch("p13")
    old = bridge.state()
    with pytest.raises(HTTPException):
        await bridge.switch("candidate", expected_runtime_id="stale")
    (root / "adapters/p13/adapter_model.safetensors").write_bytes(b"changed")
    with pytest.raises(HTTPException):
        await bridge.response(SimpleChatRequest(content="test"))
    assert len(calls) == 1 and bridge.state() == old


@pytest.mark.parametrize("adapter", ["../p13", "/tmp/p13", "no-such-adapter"])
def test_catalog_rejects_paths(native, adapter):
    with pytest.raises(HTTPException):
        bridge._resolve(adapter)


def test_catalog_rejects_symlink(native, tmp_path):
    root, _ = native
    (root / "adapters/link").symlink_to(root / "adapters/p13", target_is_directory=True)
    with pytest.raises(HTTPException):
        bridge._resolve("link")


@pytest.mark.asyncio
async def test_switch_and_rollback_really_reload_previous(native):
    _, calls = native
    a = await bridge.switch("p13")
    b = await bridge.switch(
        "candidate", expected_runtime_id=a["selection"]["runtime_id"]
    )
    restored = await bridge.rollback(expected_runtime_id=b["selection"]["runtime_id"])
    assert restored["selection"] == a["selection"]
    assert [c["identity"]["adapter_id"] for c in calls] == ["p13", "candidate", "p13"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"tools": [{}]},
        {"material_ids": ["x"]},
        {"max_tokens": 2048},
        {"expected_runtime_id": "wrong"},
        {"model": "ollama-model"},
    ],
)
async def test_unsupported_or_stale_request_does_not_generate(native, fields):
    _, calls = native
    await bridge.switch("p13")
    with pytest.raises(HTTPException):
        await bridge.response(SimpleChatRequest(content="question", **fields))
    assert len(calls) == 1


def test_normal_endpoint_uses_selected_native_adapter(native, monkeypatch):
    app = FastAPI()
    app.include_router(llm_simple.router)
    paths = app.openapi()["paths"]
    assert "/api/v1/llm/native-text/selection" in paths
    assert not any("/llm/api/" in path for path in paths)
    monkeypatch.setattr(
        "venom_core.services.llm_simple_service.assert_runtime_request_allowed",
        lambda **kw: None,
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/llm/native-text/catalog").status_code == 200
        selected = client.put(
            "/api/v1/llm/native-text/selection", json={"adapter_id": "p13"}
        )
        assert selected.status_code == 200, selected.text
        response = client.post(
            "/api/v1/llm/simple/stream",
            json={
                "content": "Podaj rekord.",
                "history": [
                    {"role": "user", "content": "Anna, 120 zł"},
                    {"role": "assistant", "content": "Anna, 120 zł"},
                ],
            },
        )
        assert response.status_code == 200, response.text
        assert "Anna, 120" in response.text and "weights_sha256" in response.text
        rid = selected.json()["selection"]["runtime_id"]
        assert (
            client.post(
                "/api/v1/llm/native-text/rollback", json={"expected_runtime_id": rid}
            ).json()["selection"]
            is None
        )


@pytest.mark.asyncio
async def test_ordinary_runtime_drift_rejects_generation_and_rollback(
    native, monkeypatch
):
    _, calls = native
    selected = await bridge.switch("p13")
    changed = LLMRuntimeInfo(
        "ollama", "different-model", "http://127.0.0.1:11434", "local", "local"
    )
    monkeypatch.setattr(bridge, "get_active_llm_runtime", lambda: changed)
    with pytest.raises(HTTPException, match="runtime_changed"):
        await bridge.response(SimpleChatRequest(content="hello"))
    with pytest.raises(HTTPException, match="runtime_changed"):
        await bridge.rollback(expected_runtime_id=selected["selection"]["runtime_id"])
    assert len(calls) == 1 and bridge.state()["selection"] == selected["selection"]


@pytest.mark.asyncio
async def test_response_identity_is_persisted_with_the_actual_answer(native):
    from venom_core.services.chat_history import persist_direct_response

    _, calls = native
    await bridge.switch("p13")

    class Store:
        def append_turn_once(self, *args):
            self.args = args

    store = Store()
    request = SimpleChatRequest(content="Podaj rekord.", session_id="session")
    response = await bridge.response(request)
    wrapped = persist_direct_response(response, request, store)
    _ = [part async for part in wrapped.body_iterator]
    assistant = store.args[2][1]
    assert assistant["content"] == "Anna, 120 zł"
    assert assistant["model_identity"]["adapter_id"] == "p13"
    assert (
        assistant["model_identity"]["weights_sha256"]
        == calls[0]["identity"]["weights_sha256"]
    )
    assert assistant["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_offline_transport_mounts_only_requested_adapter(monkeypatch, tmp_path):
    from venom_core.services import omni_native_dialogue as transport

    calls = []

    class Process:
        returncode = 0

        async def communicate(self, payload=None):
            assert payload == b"request"
            return b"reply", b""

    async def create(*args, **kwargs):
        calls.append(args)
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    result = await transport._invoke(
        tmp_path, b"request", adapter=tmp_path / "adapter", python_env=tmp_path / "env"
    )
    assert result == b"reply"
    args = calls[0]
    assert "--net" in args and "--kill-child=SIGKILL" in args
    assert args[-2:] == (str(tmp_path / "adapter"), "omni_native_text_worker.py")
    assert str(tmp_path / "env/bin/python") in args


@pytest.fixture
def text_worker(monkeypatch):
    import importlib

    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[1] / "scripts/llm")
    )
    return importlib.import_module("omni_native_text_worker")


def test_worker_verifies_actual_adapter_bytes(text_worker, tmp_path, monkeypatch):
    monkeypatch.setattr(text_worker, "verify_snapshot", lambda: "revision")
    monkeypatch.setattr(text_worker, "PIN", SNAPSHOT_PIN)
    (tmp_path / "adapter_config.json").write_bytes(b"config")
    (tmp_path / "adapter_model.safetensors").write_bytes(b"weights")
    actual_path = Path
    monkeypatch.setattr(
        text_worker,
        "Path",
        lambda path: tmp_path if path == "/adapter" else actual_path(path),
    )
    expected = {
        "revision": "revision",
        "model": read_json(SNAPSHOT_PIN)["repo"],
        "snapshot_sha256": digest(SNAPSHOT_PIN),
        "config_sha256": digest(tmp_path / "adapter_config.json"),
        "weights_sha256": digest(tmp_path / "adapter_model.safetensors"),
    }
    assert text_worker.identity({"identity": expected}) == expected
    (tmp_path / "adapter_model.safetensors").write_bytes(b"different")
    with pytest.raises(text_worker.WorkerError, match="adapter_changed"):
        text_worker.identity({"identity": expected})
    with pytest.raises(text_worker.WorkerError, match="snapshot_invalid"):
        text_worker.identity({"identity": {**expected, "revision": "different"}})


def test_worker_uses_native_multimodal_class_and_text_only_peft(
    text_worker, monkeypatch
):
    import contextlib
    from types import SimpleNamespace

    calls = {}
    expected = {
        "revision": "pin",
        "weights_sha256": "w",
        "snapshot_sha256": digest(SNAPSHOT_PIN),
    }
    monkeypatch.setattr(text_worker, "PIN", SNAPSHOT_PIN)
    monkeypatch.setattr(text_worker, "identity", lambda request: expected)
    monkeypatch.setattr(text_worker, "gpu_budget", lambda torch: None)

    class Inputs(dict):
        def to(self, device):
            assert device == "cuda"
            return self

    class Processor:
        def apply_chat_template(self, messages, **kwargs):
            calls["messages"] = messages
            assert (
                kwargs["enable_thinking"] is False and kwargs["add_generation_prompt"]
            )
            return Inputs(input_ids=SimpleNamespace(shape=(1, 3)))

        tokenizer = SimpleNamespace(decode=lambda tokens, **kw: "native answer")

    class Sequences:
        def __getitem__(self, index):
            assert index == (0, slice(3, 5))
            return [10, 11]

    class Model:
        generation_config = SimpleNamespace()
        model = SimpleNamespace(language_model=object())

        def eval(self):
            return self

        def parameters(self):
            return [SimpleNamespace(device=SimpleNamespace(type="cuda"))]

        def generate(self, **kwargs):
            assert (
                kwargs["generation_mode"] == "text" and kwargs["max_new_tokens"] == 16
            )
            assert kwargs["do_sample"] is False
            return SimpleNamespace(sequences=Sequences(), sequence_lengths=[5])

    base = Model()

    def load_base(path, **kwargs):
        calls["base"] = (path, kwargs)
        return base

    def load_peft(model, path, **kwargs):
        assert model is base and path == "/adapter" and kwargs["is_trainable"] is False
        return base

    torch = SimpleNamespace(
        bfloat16="bf16",
        inference_mode=contextlib.nullcontext,
        cuda=SimpleNamespace(
            synchronize=lambda: None, max_memory_reserved=lambda: 1048576
        ),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoModelForMultimodalLM=SimpleNamespace(from_pretrained=load_base),
            AutoProcessor=SimpleNamespace(from_pretrained=lambda *a, **kw: Processor()),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "peft",
        SimpleNamespace(PeftModel=SimpleNamespace(from_pretrained=load_peft)),
    )
    monkeypatch.setattr(
        text_worker,
        "import_module",
        lambda name: SimpleNamespace(can_use_lfm3_conv=lambda: True),
    )
    messages = [{"role": "user", "content": "question"}]
    result = text_worker.generate({"messages": messages, "max_tokens": 16})
    assert result["identity"] == expected and result["text"] == "native answer"
    assert result["input_messages_sha256"] == stable_hash(messages)
    assert result["snapshot_manifest_sha256"] == digest(SNAPSHOT_PIN)
    assert result["prompt_tokens"] == 3 and result["output_tokens"] == 2
    assert result["peak_reserved_mib"] == 1
    assert calls["messages"] == messages and calls["base"][1]["local_files_only"]
