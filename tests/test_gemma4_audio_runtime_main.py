from __future__ import annotations

from fastapi.testclient import TestClient

import services.gemma4_audio_runtime.main as runtime_main
from services.gemma4_audio_runtime.engine import Gemma4Daemon


def _make_test_daemon(engine_stub) -> Gemma4Daemon:
    """Construct a daemon wired to a pre-built engine stub."""
    daemon = Gemma4Daemon(cache_dir="models_cache/hf")
    daemon._target_engine = engine_stub  # noqa: SLF001
    return daemon


def test_extract_text_prompt_from_openai_messages_prefers_latest_user_text() -> None:
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": [{"type": "text", "text": "pierwszy"}]},
        {"role": "user", "content": "drugi"},
    ]

    assert runtime_main._extract_text_prompt_from_openai_messages(messages) == "drugi"  # noqa: SLF001


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
