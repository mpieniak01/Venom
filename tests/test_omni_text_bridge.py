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
from venom_core.services.chat_policy.direct_correction import correction_context
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
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 8
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
    assert identity["weights_sha256"] in body
    assert "event: content" in body
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
    assert len(calls) == 1
    assert bridge.state() == old


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
        {"temperature": 0.8},
        {"top_p": 0.5},
        {"logprobs": True},
        {"top_logprobs": 2},
        {"seed": 42},
        {"think": True},
        {"stream": False},
    ],
)
async def test_unsupported_or_stale_request_does_not_generate(native, fields):
    _, calls = native
    await bridge.switch("p13")
    with pytest.raises(HTTPException):
        await bridge.response(SimpleChatRequest(content="question", **fields))
    assert len(calls) == 1


def test_normal_endpoint_uses_selected_native_adapter(native, monkeypatch):
    _, calls = native
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
                "expected_runtime_id": selected.json()["selection"]["runtime_id"],
                "history": [
                    {"role": "user", "content": "Anna, 120 zł"},
                    {"role": "assistant", "content": "Anna, 120 zł"},
                ]
                * 11,
            },
        )
        assert response.status_code == 200, response.text
        assert len(calls[-1]["messages"]) == 23
        assert "Anna, 120" in response.text
        assert "weights_sha256" in response.text
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
    assert len(calls) == 1
    assert bridge.state()["selection"] == selected["selection"]
    disabled = await bridge.switch(
        None, expected_runtime_id=selected["selection"]["runtime_id"]
    )
    assert disabled["selection"] is None
    assert len(calls) == 1


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
@pytest.mark.parametrize(
    ("prompt", "prior", "expected", "forbidden", "scope"),
    [
        (
            "Na kartce jest tylko „Opiekun: Igor”. Odczytaj z kartki opiekuna i numer rezerwacji.",
            "Na zajęcia mam rezerwację 52. Opiekunem jest Igor.",
            ("Igor", "brak danych"),
            "52",
            "source_only",
        ),
        (
            "Proponuję opłatę 47 zł. To na razie sugestia. Jaką opłatę mam wpisać do aktualnych ustaleń?",
            "Ustalam, że opłata za materiały wynosi 32 zł.",
            ("32 zł", "47 zł", "propozycją"),
            "Obowiązuje 47 zł",
            "pending_fee",
        ),
    ],
)
async def test_verified_correction_is_persisted_without_model_generation(
    native, monkeypatch, prompt, prior, expected, forbidden, scope
):
    from venom_core.config import SETTINGS
    from venom_core.services.chat_history import persist_direct_response

    monkeypatch.setattr(SETTINGS, "ENABLE_ACADEMY", False)
    monkeypatch.setattr(SETTINGS, "ACADEMY_QUALIFIED_CHAT_ENABLED", False)
    _, calls = native
    selected = await bridge.switch("p13")

    class Store:
        def append_turn_once(self, *args):
            self.args = args

    store = Store()
    request = SimpleChatRequest(
        content=prompt,
        history=[
            HistoryMessage(role="user", content=prior),
            HistoryMessage(role="assistant", content="Zapisano ustalenia."),
        ],
        session_id="session",
        expected_runtime_id=selected["selection"]["runtime_id"],
    )
    wrapped = persist_direct_response(await bridge.response(request), request, store)
    chunks = [chunk async for chunk in wrapped.body_iterator]
    assert len(calls) == 1  # The adapter selection probe is the only worker call.
    meta = json.loads(chunks[-1].split("data: ", 1)[1])["model_identity"]
    assistant = store.args[2][1]
    assert all(
        value.casefold() in assistant["content"].casefold() for value in expected
    )
    assert forbidden not in assistant["content"]
    assert meta["context_policy"] == scope
    assert (
        meta["response_source"]
        == assistant["model_identity"]["response_source"]
        == "correction_rule"
    )
    assert meta["weights_sha256"] == selected["selection"]["weights_sha256"]
    assert "input_messages_sha256" not in meta
    assert "tool_result" not in assistant


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
    assert "--net" in args
    assert "--kill-child=SIGKILL" in args
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
            assert kwargs["enable_thinking"] is False
            assert kwargs["add_generation_prompt"]
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
            assert kwargs["generation_mode"] == "text"
            assert kwargs["max_new_tokens"] == 16
            assert kwargs["do_sample"] is False
            return SimpleNamespace(sequences=Sequences(), sequence_lengths=[5])

    base = Model()

    def load_base(path, **kwargs):
        calls["base"] = (path, kwargs)
        return base

    def load_peft(model, path, **kwargs):
        assert model is base
        assert path == "/adapter"
        assert kwargs["is_trainable"] is False
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
    assert result["identity"] == expected
    assert result["text"] == "native answer"
    assert result["input_messages_sha256"] == stable_hash(messages)
    assert result["snapshot_manifest_sha256"] == digest(SNAPSHOT_PIN)
    assert result["prompt_tokens"] == 3
    assert result["output_tokens"] == 2
    assert result["peak_reserved_mib"] == 1
    assert calls["messages"] == messages
    assert calls["base"][1]["local_files_only"]


@pytest.mark.asyncio
async def test_rollback_rejects_resealed_previous_adapter_before_probe(native):
    root, calls = native
    original = await bridge.switch("p13")
    current = await bridge.switch(
        "candidate", expected_runtime_id=original["selection"]["runtime_id"]
    )
    before = bridge.state()
    directory = root / "adapters/p13"
    (directory / "adapter_model.safetensors").write_bytes(b"replacement sealed weights")
    hashes = read_json(directory / "hashes.json")
    hashes["adapter_model.safetensors"] = digest(
        directory / "adapter_model.safetensors"
    )
    write(directory / "hashes.json", hashes)
    entry = read_json(directory / "adapter.json")
    entry["weights_sha256"] = hashes["adapter_model.safetensors"]
    write(directory / "adapter.json", entry)
    # The replacement passes catalog validation, but is not the retained selection.
    assert bridge._resolve("p13").payload() != original["selection"]
    with pytest.raises(HTTPException, match="omni_native_text_selection_changed"):
        await bridge.rollback(expected_runtime_id=current["selection"]["runtime_id"])
    assert len(calls) == 2
    assert bridge.state() == before


@pytest.mark.asyncio
async def test_native_direct_calculator_preserves_unit_and_own_provenance(
    native, monkeypatch
):
    from venom_core.config import SETTINGS
    from venom_core.services.chat_history import persist_direct_response

    monkeypatch.setattr(SETTINGS, "ENABLE_ACADEMY", False)
    _, calls = native
    selected = await bridge.switch("p13")

    class Store:
        def append_turn_once(self, *args):
            self.args = args

    store = Store()
    request = SimpleChatRequest(
        content="Oblicz: 2 × 1,25. Jednostka: l.",
        session_id="paint",
        expected_runtime_id=selected["selection"]["runtime_id"],
    )
    wrapped = persist_direct_response(await bridge.response(request), request, store)
    content = "".join([part async for part in wrapped.body_iterator])
    assert len(calls) == 1  # Only the selection probe called the model.
    assert "2,5 l" in content
    assert "input_messages_sha256" not in content
    assistant = store.args[2][1]
    assert assistant["model_identity"]["response_source"] == "calculator"
    assert (
        assistant["model_identity"]["weights_sha256"]
        == selected["selection"]["weights_sha256"]
    )
    assert assistant["tool_result"] == {
        "tool": "calculator",
        "status": "succeeded",
        "value": "2.5",
        "unit": "l",
        "recomputed": False,
    }
    repeated = await bridge.response(
        SimpleChatRequest(
            content="Powtórz tylko wynik.",
            history=[
                HistoryMessage(role="user", content=request.content),
                HistoryMessage(role="assistant", content=assistant["content"]),
            ],
        )
    )
    repeated_text = "".join([part async for part in repeated.body_iterator])
    assert '"recomputed": true' in repeated_text and "2,5 l" in repeated_text
    quoted = await bridge.response(
        SimpleChatRequest(content="Przetłumacz: «Oblicz 2 * 1,25 l»")
    )
    assert "Anna, 120 zł" in "".join([part async for part in quoted.body_iterator])
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "text", "receipt"),
    [
        (
            "Oblicz 4 - 2,5 i podaj wynik w litrach.",
            "1,5 l",
            ("succeeded", "1.5", "l"),
        ),
        ("Policz 2 * 1,25 l", "2,5 l", ("succeeded", "2.5", "l")),
        ("Policz: −4 × 2", "-8", ("succeeded", "-8", None)),
        ("Użyj kalkulatora.", "Jakie wyrażenie", ("missing_expression", None, None)),
        (
            "Oblicz: 3 / 0. Jednostka: kg.",
            "Nie udało się obliczyć",
            ("invalid_expression", None, "kg"),
        ),
        ("Napisz wiadomość z „Policz 2 * 3 zł”.", "Anna, 120 zł", None),
        ("Oblicz: „Policz 2 * 3 zł”", "Anna, 120 zł", None),
        ("Oblicz powierzchnię szklarni.", "Anna, 120 zł", None),
        ("Oblicz 3 * 5 groszy.", "Anna, 120 zł", None),
        ("Policz 2 * 4\nOpisz wynik.", "Anna, 120 zł", None),
        ("Powtórz wynik.", "Anna, 120 zł", None),
    ],
)
async def test_native_calculator_requires_explicit_bounded_command(
    native, command, text, receipt
):
    _, calls = native
    await bridge.switch("p13")
    response = await bridge.response(SimpleChatRequest(content=command))
    packets = [packet async for packet in response.body_iterator]
    finished = json.loads(packets[-1].split("data: ", 1)[1])["model_identity"]
    assert text in "".join(packets)
    if receipt is None:
        assert "tool_result" not in finished and len(calls) == 2
        return
    assert len(calls) == 1
    tool_result = finished["tool_result"]
    assert (tool_result["status"], tool_result["value"], tool_result["unit"]) == receipt


def test_rejected_proposal_keeps_confirmed_fee():
    users = [
        "Szykuję próbę chóru: sala Pod Lipą, piątek o 18:20, składka 14 zł.",
        "Przenoszę próbę do sali Pod Sową. Ktoś zaproponował 19 zł. Podaj aktualne ustalenia.",
        "Odrzucam podwyżkę. Na aktualnej ulotce jest tylko napis „Sala Pod Sową”. "
        "Jaką składkę podaje sama ulotka?",
    ]
    card = correction_context(users[-1], users[:-1])
    assert card and card.scope == "source_only"
    assert "Sama karta nie podaje kwoty." in card.text
    assert "14 zł" not in card.text and "19 zł" not in card.text

    state = correction_context("Podaj wiążące ustalenia z rozmowy.", users)
    assert state and state.scope == "binding_fee"
    assert "14 zł" in state.text and "19 zł" not in state.text


def test_accepted_fee_survives_partial_card_lookup():
    users = [
        "Rezerwację szafki prowadzi Aneta. Numer 27, odbiór w sobotę o 10:45, kaucja 36 zł.",
        "Zamiast Anety wpisz Olę. Proponuję podnieść kaucję do 44 zł. Podaj ustalenia.",
        "Zatwierdzam kaucję 44 zł. Mam też kartkę z samym tekstem „Opiekunka: Ola”. "
        "Podaj opiekunkę i numer szafki z kartki.",
    ]
    card = correction_context(users[-1], users[:-1])
    assert card and card.scope == "source_only"
    assert "Sama karta nie podaje numeru." in card.text

    state = correction_context("Podaj końcowe ustalenia rozmowy.", users)
    assert state and "44 zł" in state.text and "36 zł" not in state.text


def test_registration_cancellation_preserves_free_admission():
    prior = ["Napisz zaproszenie. Wstęp jest wolny, ale trzeba się zapisać."]
    state = correction_context(
        "Zapisy jednak odwołane. Wstęp nadal wolny. Przeredaguj zaproszenie.", prior
    )
    assert state and state.scope == "registration_cancelled"
    assert "nie trzeba się zapisywać" in state.text
    assert "Wstęp jest wolny" in state.text
    assert correction_context("Przetłumacz „Zapisy jednak odwołane.”", prior) is None


def test_no_hint_on_plain_text_or_ambiguous_price():
    assert correction_context("Podaj ustalenia", ["Jaka będzie pogoda?"]) is None
    prior = [
        "Ustalam składkę 14 zł i kaucję 20 zł.",
        "Proponuję 25 zł. Powtórz ustalenia.",
    ]
    assert correction_context("Odrzucam propozycję. Podaj ustalenia.", prior) is None


def test_unrelated_later_topic_does_not_inherit_previous_fee():
    prior = [
        "Ustalam opłatę 12 zł.",
        "Proponuję 16 zł.",
        "Odrzucam zmianę.",
        "Przejdźmy do osobnego tematu. Bilety drukujemy w piątek.",
    ]
    assert correction_context("Podaj aktualne ustalenia.", prior) is None


def test_source_context_does_not_infer_absence_for_prose():
    result = correction_context(
        "Ulotka ma tylko napis „Sala Pod Sową i składka dziesięć zł”. "
        "Jaką składkę podaje sama ulotka?",
        [],
    )
    assert result is not None
    assert result.scope == "source_only"
    assert "Sama karta nie podaje kwoty." not in result.text


def test_pending_proposal_keeps_unannotated_native_context():
    previous = [
        "Szykuję próbę chóru: sala Pod Lipą, piątek o 18:20, składka 14 zł.",
    ]
    assert (
        correction_context(
            "Przenoszę próbę do sali Pod Sową. Proponuję 19 zł. Podaj ustalenia.",
            previous,
        )
        is None
    )


@pytest.mark.asyncio
async def test_native_cancellation_corrects_signup_draft_with_distinct_origin(
    native, monkeypatch
):
    _, calls = native
    await bridge.switch("p13")
    original_invoke = bridge.omni_native_dialogue._invoke
    draft = "Zapraszamy do Klubu Logiki. Proszę się zapisać, aby wziąć udział."

    async def invoke(*args, **kwargs):
        result = json.loads(await original_invoke(*args, **kwargs))
        result["text"] = draft
        return json.dumps(result).encode()

    monkeypatch.setattr(bridge.omni_native_dialogue, "_invoke", invoke)
    request = SimpleChatRequest(
        content="Zapisy jednak odwołane. Wstęp nadal wolny. Przeredaguj zaproszenie.",
        history=[
            HistoryMessage(
                role="user", content="Napisz zaproszenie, ale trzeba się zapisać."
            ),
        ],
    )
    response = await bridge.response(request)
    packets = [packet async for packet in response.body_iterator]
    answer = json.loads(packets[1].split("data: ", 1)[1])["text"]
    identity = json.loads(packets[-1].split("data: ", 1)[1])["model_identity"]
    assert (
        answer
        == "Zapraszamy do Klubu Logiki. Wstęp jest wolny i nie trzeba się zapisywać."
    )
    assert identity["context_policy"] == "registration_cancelled"
    assert identity["response_source"] == "correction_rule"
    assert identity["input_messages_sha256"] == stable_hash(calls[-1]["messages"])


def test_cancelled_registration_leaves_compliant_reply_and_unrelated_scope_alone():
    previous = ["Napisz zaproszenie. Wstęp jest wolny, ale trzeba się zapisać."]
    correct = "Zapraszamy do klubu. Wstęp jest wolny i nie trzeba się zapisywać."
    context = correction_context(
        "Odwołuję zapisy. Wstęp jest wolny. Napisz zaproszenie.", previous
    )
    assert context is not None
    assert bridge.corrected_registration_reply(context, correct) is None
    assert correction_context("Odwołuję zapisy. Co o tym sądzisz?", previous) is None


def test_cancelled_registration_fallback_contains_only_confirmed_commitments():
    context = correction_context(
        "Odwołuję zapisy. Napisz zaproszenie.",
        ["Napisz zaproszenie, ale trzeba się zapisać."],
    )
    assert context is not None
    assert (
        bridge.corrected_registration_reply(
            context, "Zapraszamy na poczęstunek. Zapisy są obowiązkowe."
        )
        == "Zapraszamy do udziału. Zapisy nie są wymagane."
    )


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Na kartce jest tylko „Opiekun: Igor”. "
            "Odczytaj z kartki opiekuna i numer rezerwacji.",
            "Opiekun: Igor. Numer rezerwacji: brak danych.",
        ),
        (
            "Zatwierdzam kaucję 44 zł. Mam też kartkę z samym tekstem „Opiekunka: Ola”. "
            "Podaj opiekunkę i numer szafki z kartki, wskazując brakujące dane.",
            "Opiekunka: Ola. Numer szafki: brak danych.",
        ),
        (
            "Na kartce widnieje wyłącznie „Opiekun: Igor”. "
            "Podaj numer rezerwacji z kartki.",
            "Numer rezerwacji: brak danych.",
        ),
        (
            "Na kartce jest tylko „Opiekun: Igor; numer rezerwacji: 19”. "
            "Odczytaj z kartki opiekuna i numer rezerwacji.",
            None,
        ),
        (
            "Zapamiętaj opis „Opiekun: Igor”. Na kartce jest tylko. "
            "Odczytaj z kartki opiekuna i numer rezerwacji.",
            None,
        ),
        (
            "Na kartce jest „Opiekun: Igor”. Odczytaj z kartki opiekuna i numer rezerwacji.",
            None,
        ),
        (
            "Przeredaguj: Na kartce jest tylko „Opiekun: Igor”. "
            "Odczytaj z kartki opiekuna i numer rezerwacji.",
            None,
        ),
        (
            "Na kartce jest tylko „Opiekun: Igor”. "
            "Odczytaj z kartki opiekunkę i numer rezerwacji.",
            None,
        ),
    ],
)
def test_verified_single_field_card_does_not_import_conversation_values(
    question, expected
):
    context = correction_context(
        question, ["Ustalam numer rezerwacji 52 i szafki 27. Opiekunką jest Aneta."]
    )
    assert (context.verified_reply if context else None) == expected
    if expected is not None:
        assert context.scope == "source_only"


@pytest.mark.parametrize(
    ("previous", "question"),
    [
        (
            [
                "Ustalam, że warsztat linorytu jest w środę o 17:40, a opłata za materiały wynosi 32 zł."
            ],
            "Proponuję opłatę 47 zł. To na razie sugestia. Jaką opłatę mam wpisać do aktualnych ustaleń?",
        ),
        (
            ["Ustalam opłatę 32 zł.", "Proponuję opłatę 47 zł."],
            "Ile wynosi obecnie opłata?",
        ),
        (
            ["Akceptuję opłatę 32 zł."],
            "Proponuję opłatę 47 zł. Jaka opłata obowiązuje?",
        ),
    ],
)
def test_explicit_pending_fee_question_returns_confirmed_amount(previous, question):
    context = correction_context(question, previous)
    assert context and context.scope == "pending_fee"
    assert context.verified_reply == (
        "Obowiązuje 32 zł. Kwota 47 zł jest propozycją do zatwierdzenia."
    )


@pytest.mark.parametrize(
    ("previous", "question"),
    [
        (
            ["Ustalam opłatę 32 zł.", "Teraz o parkingu."],
            "Proponuję opłatę 47 zł. Jaka opłata obowiązuje?",
        ),
        (
            ["Ustalam opłatę 32 zł i kaucję 15 zł."],
            "Proponuję opłatę 47 zł. Jaka opłata obowiązuje?",
        ),
        (
            ["Ustalam, że opłata nie wynosi 32 zł."],
            "Proponuję opłatę 47 zł. Jaka opłata obowiązuje?",
        ),
        (
            ["Ustalam opłatę 32 zł."],
            "Proponuję kaucję 47 zł. Jaka opłata obowiązuje?",
        ),
        (
            ["Ustalam opłatę 32 zł."],
            "Przetłumacz „Proponuję opłatę 47 zł. Jaka opłata obowiązuje?”",
        ),
        (
            [
                "Ustalam opłatę 32 zł.",
                "Proponuję opłatę 47 zł.",
                "Akceptuję opłatę 47 zł.",
            ],
            "Jaka opłata obowiązuje?",
        ),
    ],
)
def test_pending_fee_does_not_override_unrelated_or_approved_state(previous, question):
    context = correction_context(question, previous)
    assert context is None or context.scope != "pending_fee"


@pytest.mark.parametrize("separator", [" ", "\u00a0", "\u202f"])
def test_pending_fee_preserves_grouped_amount(separator):
    current = f"1{separator}200,50"
    proposed = f"1{separator}450"
    context = correction_context(
        f"Proponuję opłatę {proposed} zł. Jaka opłata obowiązuje?",
        [f"Ustalam, że opłata wynosi {current} zł."],
    )
    assert context is not None
    assert context.verified_reply == (
        f"Obowiązuje {current} zł. Kwota {proposed} zł jest propozycją do zatwierdzenia."
    )
