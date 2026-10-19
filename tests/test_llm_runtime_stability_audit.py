from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "dev" / "llm_runtime_stability_audit.py"
    spec = importlib.util.spec_from_file_location(
        "llm_runtime_stability_audit", script_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pick_model_prefers_gemma3_pattern():
    module = _load_module()
    model = module._pick_model(
        available_models=["llama3.2:3b", "gemma3:4b", "gemma2:2b"],
        preferred_patterns=["gemma3", "gemma2"],
    )
    assert model == "gemma3:4b"


def test_pick_model_falls_back_to_first_when_no_match():
    module = _load_module()
    model = module._pick_model(
        available_models=["qwen2.5:7b", "llama3.2:3b"],
        preferred_patterns=["gemma3"],
    )
    assert model == "qwen2.5:7b"


def test_runtime_models_from_options_deduplicates():
    module = _load_module()
    payload = {
        "runtimes": [
            {
                "runtime_id": "ollama",
                "models": [
                    {"name": "gemma3:4b"},
                    {"name": "Gemma3:4b"},
                    {"name": "gemma2:2b"},
                ],
            }
        ]
    }
    assert module._runtime_models_from_options(payload, "ollama") == [
        "gemma3:4b",
        "gemma2:2b",
    ]


def test_runtime_models_from_options_missing_runtime_returns_empty():
    module = _load_module()
    payload = {"runtimes": [{"runtime_id": "vllm", "models": [{"name": "foo"}]}]}
    assert module._runtime_models_from_options(payload, "onnx") == []


def test_verify_active_server_allows_model_mismatch_when_not_strict(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "_http_json",
        lambda *_args, **_kwargs: (
            200,
            {
                "active_server": "onnx",
                "active_model": "models/gemma-3-1b-it-onnx-q4-genai",
            },
        ),
    )
    ok, _msg = module._verify_active_server(
        "http://127.0.0.1:8000",
        runtime="onnx",
        model="gemma-3-4b-it-onnx-build-test",
        strict_model=False,
    )
    assert ok is True


def _response(body, *, status=200, content_type="text/event-stream"):
    stream = io.BytesIO(body)
    stream.status = status
    stream.headers = {"Content-Type": content_type}
    return stream


@pytest.mark.parametrize(
    "active,expected", [("", False), ("model-extra", False), ("model", True)]
)
def test_strict_model_requires_nonempty_exact_identity(monkeypatch, active, expected):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "_http_json",
        lambda *a, **k: (200, {"active_server": "vllm", "active_model": active}),
    )
    assert (
        module._verify_active_server("http://fixture", runtime="vllm", model="model")[0]
        is expected
    )


@pytest.mark.parametrize(
    "body,reason",
    [
        (b"event: done\ndata: {}\n\n", "empty_output"),
        (b'event: content\ndata: {"text":"hello"}\n\n', "missing_done"),
        (b'event: error\ndata: {"message":"engine failure"}\n\n', "error_event"),
        (b"event: content\ndata: {invalid}\n\n", "generation_failed"),
        (b"event: content\ndata: []\n\n", "invalid_content"),
        (b'event: content\ndata: {"text":42}\n\n', "invalid_content"),
        (
            b'event: content\ndata: {"text":"  "}\n\nevent: done\ndata: {}\n\n',
            "empty_output",
        ),
        (b"event: content\ndata: \xff\n\n", "generation_failed"),
    ],
)
def test_generation_rejects_false_successes(monkeypatch, body, reason):
    module = _load_module()
    monkeypatch.setattr(module.request, "urlopen", lambda *a, **k: _response(body))
    ok, message = module._verify_generation("http://fixture", model="model")
    assert not ok
    assert reason in message


@pytest.mark.parametrize(
    "status,content_type", [(503, "text/event-stream"), (200, "application/json")]
)
def test_generation_requires_successful_sse_response(monkeypatch, status, content_type):
    module = _load_module()
    monkeypatch.setattr(
        module.request,
        "urlopen",
        lambda *a, **k: _response(b"", status=status, content_type=content_type),
    )
    ok, message = module._verify_generation("http://fixture", model="model")
    assert not ok
    assert "not_sse" in message


def test_generation_network_failure_is_not_success(monkeypatch):
    module = _load_module()

    def unavailable(*args, **kwargs):
        raise module.error.URLError("offline fixture")

    monkeypatch.setattr(module.request, "urlopen", unavailable)
    ok, message = module._verify_generation("http://fixture", model="model")
    assert not ok
    assert "offline fixture" in message


def test_stream_has_deadline_and_bounded_frames():
    module = _load_module()
    prepared_argument = io.BytesIO()
    with pytest.raises(TimeoutError, match="deadline"):
        module._read_generation_stream(prepared_argument, deadline=-1)
    prepared_argument_2 = io.BytesIO(b"x" * 65537)
    prepared_deadline = module.time.monotonic() + 10
    with pytest.raises(ValueError, match="too_large"):
        module._read_generation_stream(prepared_argument_2, deadline=prepared_deadline)
    prepared_argument_3 = io.BytesIO(b": keepalive\n\n" * 100000)
    prepared_deadline_2 = module.time.monotonic() + 10
    with pytest.raises(ValueError, match="too_large"):
        module._read_generation_stream(
            prepared_argument_3, deadline=prepared_deadline_2
        )


def test_generation_uses_actual_api_schema_over_loopback():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    module = _load_module()
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            captured["path"] = self.path
            captured["payload"] = json.loads(
                self.rfile.read(int(self.headers["Content-Length"]))
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                'event: start\ndata: {}\n\nevent: content\ndata: {\ndata: "text":"Cześć"}\n\nevent: done\ndata: {}\n\n'.encode()
            )

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}
    )
    worker.start()
    try:
        ok, message = module._verify_generation(
            f"http://127.0.0.1:{server.server_port}", model="exact-model"
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    assert ok
    assert "generation_chars=5" in message
    assert not worker.is_alive()
    assert captured["path"] == "/api/v1/llm/simple/stream"
    assert captured["payload"]["model"] == "exact-model"
    assert captured["payload"]["content"]
    assert captured["payload"]["max_tokens"] == 32
    assert captured["payload"]["stream"] is True


def _rig_audit(module, monkeypatch, *, generation_ok=True, raced=False):
    calls = {"generations": [], "unloads": []}
    identities = iter([True, not raced, True, True])
    monkeypatch.setattr(module, "_activate_server", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(
        module,
        "_verify_active_server",
        lambda *a, **k: (next(identities), "identity_changed"),
    )

    def generate(*args, **kwargs):
        calls["generations"].append(kwargs["model"])
        return generation_ok, "fixture_generation_failed"

    def unload(*args, **kwargs):
        calls["unloads"].append(True)
        return True, "ok"

    monkeypatch.setattr(module, "_verify_generation", generate)
    monkeypatch.setattr(module, "_unload_all", unload)
    return calls


def test_audit_does_not_pass_health_only(monkeypatch):
    module = _load_module()
    calls = _rig_audit(module, monkeypatch, generation_ok=False)
    result = module._audit_runtime(
        base_url="http://fixture",
        runtime="vllm",
        options_payload={
            "runtimes": [{"runtime_id": "vllm", "models": [{"name": "model"}]}]
        },
        preferred_patterns=[],
    )
    assert not result.ok
    assert "fixture_generation_failed" in result.errors
    assert calls["generations"] == ["model"]
    assert len(calls["unloads"]) == 1


def test_audit_does_not_unload_a_concurrent_model_selection(monkeypatch):
    module = _load_module()
    calls = _rig_audit(module, monkeypatch, raced=True)
    result = module._audit_runtime(
        base_url="http://fixture",
        runtime="vllm",
        options_payload={
            "runtimes": [{"runtime_id": "vllm", "models": [{"name": "model"}]}]
        },
        preferred_patterns=[],
    )
    assert not result.ok
    assert "identity_changed" in result.errors
    assert calls["generations"] == ["model"]
    assert not calls["unloads"]


def test_recovered_secondary_activation_still_requires_generation(monkeypatch):
    module = _load_module()
    calls = _rig_audit(module, monkeypatch)
    monkeypatch.setattr(
        module,
        "_activate_server",
        lambda *a, **k: (k["model"] == "first", "activation timeout"),
    )
    monkeypatch.setattr(module, "_wait_active_server", lambda *a, **k: (True, "ready"))
    result = module._audit_runtime(
        base_url="http://fixture",
        runtime="vllm",
        options_payload={
            "runtimes": [
                {
                    "runtime_id": "vllm",
                    "models": [{"name": "first"}, {"name": "second"}],
                }
            ]
        },
        preferred_patterns=[],
    )
    assert result.ok
    assert calls["generations"] == ["first", "second"]
    assert len(calls["unloads"]) == 2


def test_onnx_without_declared_model_cannot_qualify(monkeypatch):
    module = _load_module()

    def forbidden(*a, **k):
        raise AssertionError("must not activate unknown model")

    monkeypatch.setattr(module, "_activate_server", forbidden)
    result = module._audit_runtime(
        base_url="http://fixture",
        runtime="onnx",
        options_payload={},
        preferred_patterns=[],
    )
    assert not result.ok
    assert result.errors == ["no_models_available_for_runtime"]


def test_initial_identity_mismatch_never_generates_or_unloads(monkeypatch):
    module = _load_module()
    calls = _rig_audit(module, monkeypatch)
    monkeypatch.setattr(
        module, "_verify_active_server", lambda *a, **k: (False, "foreign_model")
    )
    result = module._audit_runtime(
        base_url="http://fixture",
        runtime="vllm",
        options_payload={
            "runtimes": [{"runtime_id": "vllm", "models": [{"name": "model"}]}]
        },
        preferred_patterns=[],
    )
    assert not result.ok
    assert result.errors == ["foreign_model"]
    assert not calls["generations"]
    assert not calls["unloads"]
