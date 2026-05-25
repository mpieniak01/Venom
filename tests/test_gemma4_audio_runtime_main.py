from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import services.multi_runtime.main as runtime_main
from services.multi_runtime.engine import MultiRuntimeDaemon


def _make_test_daemon(engine_stub) -> MultiRuntimeDaemon:
    """Construct a daemon wired to a pre-built engine stub."""
    daemon = MultiRuntimeDaemon(cache_dir="models_cache/hf")
    daemon._target_engine = engine_stub  # noqa: SLF001
    return daemon


def test_extract_text_prompt_from_openai_messages_prefers_latest_user_text() -> None:
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": [{"type": "text", "text": "pierwszy"}]},
        {"role": "user", "content": "drugi"},
    ]

    assert runtime_main._extract_text_prompt_from_openai_messages(messages) == "drugi"  # noqa: SLF001


def test_extract_image_urls_from_openai_messages() -> None:
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "opisz"}]},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.test/a.png"},
                },
                {"type": "image_url", "image_url": "https://example.test/b.png"},
            ],
        },
    ]
    assert runtime_main._extract_image_urls_from_openai_messages(messages) == [  # noqa: SLF001
        "https://example.test/a.png",
        "https://example.test/b.png",
    ]


def test_chat_completions_uses_pydantic_payload_and_sampling(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class EngineStub:
        model_id = "google/gemma-4-E2B-it"

        def is_loaded(self) -> bool:
            return True

        def respond(self, _audio, **kwargs):
            captured.update(kwargs)
            return "to jest odpowiedz", 0.25

    daemon = _make_test_daemon(EngineStub())
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    client = TestClient(runtime_main.app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "google/gemma-4-E2B-it",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Ile to 5*5?"}]}
            ],
            "max_tokens": 77,
            "temperature": 0.2,
            "top_p": 0.9,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "to jest odpowiedz"
    assert captured["max_new_tokens"] == 77
    assert captured["do_sample"] is True
    assert captured["temperature"] == 0.2
    assert captured["top_p"] == 0.9
    assert body["usage"]["prompt_tokens"] >= 1
    assert body["usage"]["completion_tokens"] == max(1, len("to jest odpowiedz") // 4)


def test_chat_completions_accepts_image_urls(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class EngineStub:
        model_id = "google/gemma-4-E2B-it"

        def is_loaded(self) -> bool:
            return True

        def respond(self, _audio, **kwargs):
            captured.update(kwargs)
            return "ok", 0.05

    daemon = _make_test_daemon(EngineStub())
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    async def _fake_image_from_url(_url: str):
        return object()

    monkeypatch.setattr(runtime_main, "_image_from_url", _fake_image_from_url)

    client = TestClient(runtime_main.app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "co jest na obrazku"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "https://example.test/image.png"},
                        },
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200
    assert isinstance(captured.get("images"), list)
    assert len(captured["images"]) == 1


def test_chat_completions_accepts_data_image_urls(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class EngineStub:
        model_id = "google/gemma-4-E2B-it"

        def is_loaded(self) -> bool:
            return True

        def respond(self, _audio, **kwargs):
            captured.update(kwargs)
            return "ok", 0.05

    daemon = _make_test_daemon(EngineStub())
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    def _fake_image_from_data_field(_data: str):
        return object()

    monkeypatch.setattr(
        runtime_main, "_image_from_data_field", _fake_image_from_data_field
    )

    client = TestClient(runtime_main.app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,Zm9v"},
                        }
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200
    assert isinstance(captured.get("images"), list)
    assert len(captured["images"]) == 1


def test_validate_image_url_rejects_private_hosts() -> None:
    runtime_main._validate_image_url("https://example.com/a.png")  # noqa: SLF001
    try:
        runtime_main._validate_image_url("http://127.0.0.1/a.png")  # noqa: SLF001
    except ValueError as exc:
        assert "Local/private hosts" in str(exc)
    else:
        raise AssertionError("Expected ValueError for private host")


def test_validate_image_url_honors_allowlist(monkeypatch) -> None:
    monkeypatch.setenv(
        "GEMMA4_AUDIO_IMAGE_ALLOWED_HOSTS", "example.com,cdn.example.com"
    )
    runtime_main._validate_image_url("https://example.com/a.png")  # noqa: SLF001
    try:
        runtime_main._validate_image_url("https://evil.example/a.png")  # noqa: SLF001
    except ValueError as exc:
        assert "not allowed by policy" in str(exc)
    else:
        raise AssertionError("Expected ValueError for disallowed host")


def test_image_from_path_blocks_when_policy_disabled(
    tmp_path: Path, monkeypatch
) -> None:
    sample = tmp_path / "a.png"
    sample.write_bytes(b"not-an-image")
    monkeypatch.delenv("GEMMA4_AUDIO_IMAGE_INPUT_DIR", raising=False)
    try:
        runtime_main._image_from_path(str(sample))  # noqa: SLF001
    except ValueError as exc:
        assert "disabled by policy" in str(exc)
    else:
        raise AssertionError("Expected ValueError when local file loading disabled")


def test_image_from_path_rejects_outside_allowed_dir(
    tmp_path: Path, monkeypatch
) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside.png"
    allowed.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"not-an-image")
    monkeypatch.setenv("GEMMA4_AUDIO_IMAGE_INPUT_DIR", str(allowed))
    try:
        runtime_main._image_from_path(str(outside))  # noqa: SLF001
    except ValueError as exc:
        assert "outside allowed input directory" in str(exc)
    else:
        raise AssertionError("Expected ValueError for path traversal/outside path")


def test_chat_completions_rejects_streaming(monkeypatch) -> None:
    class EngineStub:
        model_id = "m"

        def is_loaded(self) -> bool:
            return True

    daemon = _make_test_daemon(EngineStub())
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    client = TestClient(runtime_main.app)

    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hej"}], "stream": True},
    )

    assert response.status_code == 400
    assert "Streaming is not supported" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_completions_does_not_decrement_inflight_when_increment_fails(
    monkeypatch,
) -> None:
    class EngineStub:
        model_id = "google/gemma-4-E2B-it"

        def is_loaded(self) -> bool:
            return True

        def respond(self, _audio, **kwargs):
            return "ok", 0.01

    daemon = _make_test_daemon(EngineStub())
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    async def _increment_fail() -> None:
        raise RuntimeError("increment failed")

    called = {"decrement": 0}

    async def _decrement_track() -> int:
        called["decrement"] += 1
        return 0

    monkeypatch.setattr(runtime_main, "_increment_respond_inflight", _increment_fail)
    monkeypatch.setattr(runtime_main, "_decrement_respond_inflight", _decrement_track)

    payload = runtime_main.ChatCompletionRequest(
        model="google/gemma-4-E2B-it",
        messages=[runtime_main.ChatCompletionMessage(role="user", content="hej")],
    )

    with pytest.raises(RuntimeError, match="increment failed"):
        await runtime_main.chat_completions(payload)

    assert called["decrement"] == 0


@pytest.mark.asyncio
async def test_respond_decrements_inflight_when_model_not_loaded(monkeypatch) -> None:
    class EngineStub:
        def is_loaded(self) -> bool:
            return False

    class DaemonStub:
        def active_engine(self):
            return EngineStub()

    monkeypatch.setattr(runtime_main, "get_daemon", lambda: DaemonStub())

    calls = {"inc": 0, "dec": 0}

    async def _increment_ok() -> None:
        calls["inc"] += 1

    async def _decrement_ok() -> int:
        calls["dec"] += 1
        return 0

    monkeypatch.setattr(runtime_main, "_increment_respond_inflight", _increment_ok)
    monkeypatch.setattr(runtime_main, "_decrement_respond_inflight", _decrement_ok)

    request = runtime_main.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/respond",
            "headers": [],
            "query_string": b"",
        }
    )

    with pytest.raises(runtime_main.HTTPException) as exc_info:
        await runtime_main.respond(request)

    assert exc_info.value.status_code == 503
    assert calls["inc"] == 1
    assert calls["dec"] == 1
