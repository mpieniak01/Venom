"""Real loopback HTTP/SSE tests, with an explicit nonmodel token fixture."""

import json
import socket
import struct
import threading
import urllib.error
import urllib.request

import pytest

from scripts.llm.onnx_gpu_bridge import BridgeServer, RequestError, validate_request


class TokenFixture:
    model_name = "fixture-model"
    device = "test-fixture"

    def close(self):
        pass

    def generate(self, request, stats, stop_event=None):
        stats.update(prompt_tokens=3, completion_tokens=0, finish_reason="stop")
        for token in ["Dzień ", "dobry"]:
            stats["completion_tokens"] += 1
            yield token


@pytest.fixture
def bridge():
    server = BridgeServer(("127.0.0.1", 0), TokenFixture())
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}
    )
    worker.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        assert not worker.is_alive()


def request(base, payload):
    data = json.dumps(payload).encode()
    return urllib.request.urlopen(
        urllib.request.Request(
            base + "/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
        ),
        timeout=3,
    )


def message(**kwargs):
    return {
        "model": "fixture-model",
        "messages": [{"role": "user", "content": "hello"}],
        **kwargs,
    }


def assert_generation_idle(server):
    # HTTP body completion can precede the handler's finally block on its thread.
    assert server.generation_lock.acquire(timeout=1)
    server.generation_lock.release()


def run_background(action):
    results = []

    def run():
        try:
            results.append(action())
        except BaseException as error:
            results.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    return worker, results


def completion_result(base, payload):
    try:
        with request(base, payload) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        with error:
            return error.code, error.read()


def gate_native_call(monkeypatch, owner, method, count=None, fail=False):
    entered, release = threading.Event(), threading.Event()
    original = getattr(owner, method)
    used = False

    def call(instance, *args, **kwargs):
        nonlocal used
        if not used and (count is None or instance.count == count):
            used = True
            entered.set()
            if not release.wait(3):
                raise RuntimeError("fixture_native_gate_timeout")
            if fail:
                raise RuntimeError("fixture_native_failed")
        return original(instance, *args, **kwargs)

    monkeypatch.setattr(owner, method, call)
    return entered, release


def test_http_completion_has_actual_chunks_usage_and_model(bridge):
    server, base = bridge
    with request(base, message(max_tokens=8)) as response:
        body = json.load(response)
    assert body["choices"][0]["message"]["content"] == "Dzień dobry"
    assert body["usage"] == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    assert body["model"] == "fixture-model"
    assert_generation_idle(server)


def test_sse_sends_token_deltas_and_explicit_termination(bridge):
    server, base = bridge
    with request(base, message(stream=True)) as response:
        assert response.headers["Content-Type"] == "text/event-stream"
        frames = [
            line[6:]
            for line in response.read().decode().splitlines()
            if line.startswith("data: ")
        ]
    assert frames[-1] == "[DONE]"
    chunks = [json.loads(frame) for frame in frames[:-1]]
    assert (
        "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
        == "Dzień dobry"
    )
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert_generation_idle(server)


def test_engine_failure_is_503_not_empty_success(bridge):
    server, base = bridge

    def broken(request, stats, stop_event=None):
        raise RuntimeError("native engine failed")

    server.engine.generate = broken
    with pytest.raises(urllib.error.HTTPError) as error:
        request(base, message())
    assert error.value.code == 503
    assert "native engine failed" in json.load(error.value)["error"]["message"]
    assert_generation_idle(server)


def test_serial_worker_rejects_parallel_generation(bridge):
    server, base = bridge
    server.generation_lock.acquire()
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            request(base, message())
        assert error.value.code == 429
    finally:
        server.generation_lock.release()


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "other"},
        {"tools": []},
        {"max_tokens": True},
        {"max_tokens": 0},
        {"temperature": -1},
        {"stream": "yes"},
        {"messages": []},
        {"messages": [{"role": "user", "content": []}]},
    ],
)
def test_unsupported_or_invalid_contract_is_rejected(changes):
    with pytest.raises(RequestError):
        validate_request(message(**changes), "fixture-model")


@pytest.mark.parametrize("seed", [-(2**63), -(2**31), -1, 0, 1, 2**31 - 1, 2**63 - 1])
def test_seed_validation_preserves_signed_64_bit_integers(seed):
    validated = validate_request(message(seed=seed), "fixture-model")
    assert validated["seed"] == seed
    assert type(validated["seed"]) is int


@pytest.mark.parametrize(
    "seed", [True, False, 0.0, 1.5, "0", [], {}, -(2**63) - 1, 2**63]
)
def test_seed_validation_rejects_coercion_and_signed_64_bit_overflow(seed):
    with pytest.raises(RequestError, match="seed_must_be_signed_64_bit_integer"):
        validate_request(message(seed=seed), "fixture-model")


@pytest.mark.parametrize("changes", [{}, {"seed": None}])
def test_optional_seed_retains_the_unseeded_contract(changes):
    validated = validate_request(message(**changes), "fixture-model")
    assert validated.get("seed") is None


def test_health_and_model_discovery(bridge):
    _, base = bridge
    with urllib.request.urlopen(base + "/health") as response:
        assert json.load(response)["device"] == "test-fixture"
    with urllib.request.urlopen(base + "/v1/models") as response:
        assert json.load(response)["data"][0]["id"] == "fixture-model"


def test_native_stream_usage_option_is_served_not_ignored(bridge):
    _, base = bridge
    with request(
        base, message(stream=True, stream_options={"include_usage": True})
    ) as response:
        frames = [
            line[6:]
            for line in response.read().decode().splitlines()
            if line.startswith("data: ")
        ]
    final = json.loads(frames[-2])
    assert final["choices"] == []
    assert final["usage"]["completion_tokens"] == 2
    assert frames[-1] == "[DONE]"


@pytest.fixture
def fake_native_sdk(tmp_path, monkeypatch):
    """Native option/loop contract fixture; real GPU proof is separate."""
    from types import SimpleNamespace

    from scripts.llm import onnx_gpu_bridge as module

    seen = {
        "options": [],
        "destroyed": [],
        "providers": [],
        "calls": [],
        "released": [],
    }

    class Config:
        def __init__(self, path):
            pass

        def clear_providers(self):
            seen["providers"].clear()

        def append_provider(self, provider):
            seen["providers"].append(provider)

    class Model:
        device_type = "CUDA"

        def __init__(self, config):
            seen["calls"].append("model")

        def __del__(self):
            seen["released"].append("model")

    class Tokenizer:
        def __init__(self, model):
            seen["calls"].append("tokenizer")

        def __del__(self):
            seen["released"].append("tokenizer")

        def apply_chat_template(self, messages, **kwargs):
            seen["calls"].append("template")
            assert json.loads(messages)[0]["role"] == "user"
            assert kwargs["add_generation_prompt"] is True
            return "prompt"

        def encode(self, prompt):
            seen["calls"].append("encode")
            return [1, 2, 3]

        def create_stream(self):
            seen["calls"].append("stream")
            return SimpleNamespace(decode=lambda token: str(token))

    class Params:
        def __init__(self, model):
            pass

        def set_search_options(self, **kwargs):
            seen["options"].append(kwargs)

    class Generator:
        def __init__(self, model, params):
            seen["calls"].append("generator")
            self.count = 0

        def append_tokens(self, tokens):
            assert tokens == [1, 2, 3]

        def is_done(self):
            return self.count >= 10

        def generate_next_token(self):
            self.count += 1

        def get_next_tokens(self):
            return [self.count]

        def __del__(self):
            seen["destroyed"].append(self.count)

    sdk = SimpleNamespace(
        Config=Config,
        Model=Model,
        Tokenizer=Tokenizer,
        GeneratorParams=Params,
        Generator=Generator,
    )
    original = module.importlib.import_module
    monkeypatch.setattr(
        module.importlib,
        "import_module",
        lambda name: sdk if name == "onnxruntime_genai" else original(name),
    )
    (tmp_path / "genai_config.json").write_text(
        json.dumps({"model": {"context_length": 2048}})
    )
    return module, sdk, seen, tmp_path


def test_sdk_uppercase_cuda_is_canonicalized_for_the_actual_health_contract(
    bridge, fake_native_sdk
):
    server, base = bridge
    module, sdk, _, path = fake_native_sdk
    assert sdk.Model.device_type == "CUDA"
    server.engine = module.OnnxEngine(str(path), "fixture-model")
    assert server.engine.device == "cuda"
    with urllib.request.urlopen(base + "/health") as response:
        assert json.load(response) == {
            "status": "ok",
            "engine": "onnx-gpu",
            "device": "cuda",
        }


def test_engine_close_is_idempotent_and_releases_tokenizer_before_model(
    fake_native_sdk,
):
    module, _, seen, path = fake_native_sdk
    engine = module.OnnxEngine(str(path), "fixture-model")
    engine.close()
    engine.close()
    assert seen["released"] == ["tokenizer", "model"]
    with pytest.raises(RuntimeError, match="engine_closed"):
        list(engine.generate(validate_request(message(), "fixture-model"), {}))
    assert seen["options"] == []


@pytest.mark.parametrize("failure", ["tokenizer", "config"])
def test_partial_engine_construction_releases_owned_native_objects(
    fake_native_sdk, monkeypatch, failure
):
    module, sdk, seen, path = fake_native_sdk
    if failure == "tokenizer":

        def broken_tokenizer(model):
            raise RuntimeError("tokenizer_failed")

        monkeypatch.setattr(sdk, "Tokenizer", broken_tokenizer)
        error, match, released = RuntimeError, "tokenizer_failed", ["model"]
    else:
        (path / "genai_config.json").write_text("{}")
        error, match, released = KeyError, "model", ["tokenizer", "model"]
    with pytest.raises(error, match=match):
        module.OnnxEngine(str(path), "fixture-model")
    assert seen["released"] == released


def test_failed_server_bind_releases_the_constructed_engine(bridge, fake_native_sdk):
    server, _ = bridge
    module, _, seen, path = fake_native_sdk
    engine = module.OnnxEngine(str(path), "fixture-model")
    with pytest.raises(OSError):
        module.BridgeServer(server.server_address, engine)
    assert seen["released"] == ["tokenizer", "model"]
    engine.close()
    assert seen["released"] == ["tokenizer", "model"]


def test_idle_server_teardown_releases_native_objects_once(fake_native_sdk):
    module, _, seen, path = fake_native_sdk
    server = module.BridgeServer(
        ("127.0.0.1", 0), module.OnnxEngine(str(path), "fixture-model")
    )
    server.server_close()
    server.server_close()
    assert seen["released"] == ["tokenizer", "model"]
    assert_generation_idle(server)


def test_busy_server_teardown_fails_explicitly_without_calling_engine_close(
    fake_native_sdk, monkeypatch
):
    module, _, seen, path = fake_native_sdk
    engine = module.OnnxEngine(str(path), "fixture-model")
    closes = []
    native_close = engine.close

    def close():
        closes.append("close")
        native_close()

    monkeypatch.setattr(engine, "close", close)
    server = module.BridgeServer(("127.0.0.1", 0), engine)
    server.shutdown_timeout = 0.01
    server.generation_lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="active_generation_shutdown_timeout"):
            server.server_close()
        assert closes == []
        assert seen["released"] == []
        assert server.stop_event.is_set()
    finally:
        server.generation_lock.release()
        server.server_close()
    assert closes == ["close"]
    assert seen["released"] == ["tokenizer", "model"]


@pytest.mark.parametrize("signal_failure", [False, True])
def test_main_idle_exit_or_signal_setup_failure_releases_native_objects(
    fake_native_sdk, monkeypatch, signal_failure
):
    module, _, seen, path = fake_native_sdk
    monkeypatch.setattr(
        "sys.argv",
        [
            "onnx_gpu_bridge",
            "--model",
            str(path),
            "--model-name",
            "fixture-model",
            "--port",
            "0",
        ],
    )

    def set_signal(signum, handler):
        if signal_failure:
            raise RuntimeError("signal_setup_failed")

    monkeypatch.setattr(module.signal, "signal", set_signal)
    monkeypatch.setattr(
        module.BridgeServer, "serve_forever", lambda *args, **kwargs: None
    )
    if signal_failure:
        with pytest.raises(RuntimeError, match="signal_setup_failed"):
            module.main()
    else:
        module.main()
    assert seen["released"] == ["tokenizer", "model"]


def test_shutdown_sets_stop_before_stopping_the_accept_loop(
    fake_native_sdk, monkeypatch
):
    module, _, _, path = fake_native_sdk
    observed = []
    server = module.BridgeServer(
        ("127.0.0.1", 0), module.OnnxEngine(str(path), "fixture-model")
    )
    monkeypatch.setattr(
        module.ThreadingHTTPServer,
        "shutdown",
        lambda instance: observed.append(instance.stop_event.is_set()),
    )
    try:
        server.shutdown()
        server.shutdown()
        assert observed == [True, True]
    finally:
        server.server_close()


def test_stop_before_native_execution_creates_no_request_native_objects(
    fake_native_sdk,
):
    module, _, seen, path = fake_native_sdk
    engine = module.OnnxEngine(str(path), "fixture-model")
    stop_event = threading.Event()
    stop_event.set()
    with pytest.raises(module.GenerationCancelled, match="worker_stopping"):
        list(
            engine.generate(
                validate_request(message(), "fixture-model"), {}, stop_event
            )
        )
    assert seen["calls"] == ["model", "tokenizer"]
    assert seen["options"] == []
    engine.close()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("phase", ["tokenization", "prefill"])
def test_stop_during_native_setup_is_503_before_the_first_token(
    bridge, fake_native_sdk, monkeypatch, stream, phase
):
    server, base = bridge
    module, sdk, seen, path = fake_native_sdk
    server.engine = module.OnnxEngine(str(path), "fixture-model")
    owner, method = (
        (sdk.Tokenizer, "encode")
        if phase == "tokenization"
        else (sdk.Generator, "append_tokens")
    )
    entered, release = gate_native_call(monkeypatch, owner, method)
    client, results = run_background(
        lambda: completion_result(base, message(stream=stream, max_tokens=2))
    )
    try:
        assert entered.wait(1)
        server.shutdown()
        assert server.stop_event.is_set()
        assert seen["released"] == []
        release.set()
        server.server_close()
        client.join(timeout=2)
        assert not client.is_alive()
        status, body = results[0]
        assert status == 503
        assert json.loads(body)["error"] == {
            "message": "worker_stopping",
            "type": "generation_cancelled",
        }
        assert "usage" not in json.loads(body)
        assert seen["destroyed"] == ([0] if phase == "prefill" else [])
        assert seen["released"] == ["tokenizer", "model"]
        assert_generation_idle(server)
    finally:
        release.set()
        client.join(timeout=3)


def test_active_loopback_sse_stop_waits_for_native_return_and_emits_only_error(
    bridge, fake_native_sdk, monkeypatch
):
    server, base = bridge
    module, sdk, seen, path = fake_native_sdk
    server.engine = module.OnnxEngine(str(path), "fixture-model")
    entered, release = gate_native_call(
        monkeypatch, sdk.Generator, "generate_next_token", count=1
    )
    response = request(
        base, message(stream=True, max_tokens=4, stream_options={"include_usage": True})
    )
    closer = None
    try:
        assert entered.wait(1)

        def close_worker():
            server.shutdown()
            server.server_close()

        closer, outcomes = run_background(close_worker)
        assert server.stop_event.wait(1)
        assert seen["released"] == []
        release.set()
        frames = [
            line[6:]
            for line in response.read().decode().splitlines()
            if line.startswith("data: ")
        ]
        closer.join(timeout=2)
        assert not closer.is_alive()
        assert outcomes == [None]
        assert "[DONE]" not in frames
        payloads = [json.loads(frame) for frame in frames]
        assert payloads[-1]["error"] == {
            "message": "worker_stopping",
            "type": "generation_cancelled",
        }
        assert not any("usage" in payload for payload in payloads)
        assert not any(
            choice.get("finish_reason") is not None
            for payload in payloads
            for choice in payload.get("choices", [])
        )
        assert seen["destroyed"] == [2]
        assert seen["released"] == ["tokenizer", "model"]
        assert_generation_idle(server)
    finally:
        release.set()
        response.close()
        if closer is not None:
            closer.join(timeout=3)


@pytest.mark.parametrize("endpoint", ["/health", "/v1/models", "/v1/chat/completions"])
def test_requests_after_stop_are_rejected_without_generation(
    bridge, monkeypatch, endpoint
):
    server, base = bridge

    def forbidden(*args, **kwargs):
        pytest.fail("generation must not run after stop")

    monkeypatch.setattr(server.engine, "generate", forbidden)
    server.stop_event.set()
    with pytest.raises(urllib.error.HTTPError) as error:
        if endpoint.endswith("completions"):
            request(base, message(stream=True))
        else:
            urllib.request.urlopen(base + endpoint, timeout=2)
    assert error.value.code == 503
    assert json.load(error.value)["error"] == {
        "message": "worker_stopping",
        "type": "generation_cancelled",
    }
    assert_generation_idle(server)


def test_already_accepted_request_is_rejected_after_validation_stop(
    bridge, monkeypatch
):
    from scripts.llm import onnx_gpu_bridge as module

    server, base = bridge
    entered, release = threading.Event(), threading.Event()
    original = module.validate_request

    def validate(*args):
        validated = original(*args)
        entered.set()
        assert release.wait(3)
        return validated

    def forbidden(*args, **kwargs):
        pytest.fail("accepted request must not generate after stop")

    monkeypatch.setattr(module, "validate_request", validate)
    monkeypatch.setattr(server.engine, "generate", forbidden)
    client, results = run_background(lambda: completion_result(base, message()))
    try:
        assert entered.wait(1)
        server.stop_event.set()
        release.set()
        client.join(timeout=2)
        assert not client.is_alive()
        status, body = results[0]
        assert status == 503
        assert json.loads(body)["error"]["message"] == "worker_stopping"
        assert_generation_idle(server)
    finally:
        release.set()
        client.join(timeout=3)


@pytest.mark.parametrize("native_failure", [False, True])
def test_loopback_sse_disconnect_cleans_iterator_and_allows_recovery_without_io_noise(
    bridge, fake_native_sdk, monkeypatch, native_failure
):
    server, base = bridge
    module, sdk, seen, path = fake_native_sdk
    server.engine = module.OnnxEngine(str(path), "fixture-model")
    entered, release = gate_native_call(
        monkeypatch, sdk.Generator, "generate_next_token", count=1, fail=native_failure
    )
    errors = []
    monkeypatch.setattr(server, "handle_error", lambda *args: errors.append(True))
    body = json.dumps(message(stream=True, max_tokens=4)).encode()
    client = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
    try:
        client.sendall(
            b"POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\n"
            b"Content-Type: application/json\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\n\r\n"
            + body
        )
        assert entered.wait(1)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        client.close()
        release.set()
        assert_generation_idle(server)
        assert seen["destroyed"] == ([1] if native_failure else [2])
        assert errors == []
        assert not server.stop_event.is_set()
        with request(base, message(max_tokens=2)) as response:
            assert json.load(response)["choices"][0]["message"]["content"] == "12"
        assert_generation_idle(server)
        assert errors == []
    finally:
        release.set()
        client.close()


@pytest.mark.parametrize("stream", [False, True])
def test_iterator_close_failure_prevents_success_and_releases_generation_lock(
    bridge, monkeypatch, stream
):
    server, base = bridge
    original = server.engine.generate

    class BadCloseIterator:
        def __init__(self):
            self.tokens = iter(["one"])

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.tokens)

        def close(self):
            raise RuntimeError("fixture_close_failed")

    def generate(request, stats, stop_event=None):
        stats.update(prompt_tokens=3, completion_tokens=1, finish_reason="stop")
        return BadCloseIterator()

    monkeypatch.setattr(server.engine, "generate", generate)
    status, body = completion_result(
        base, message(stream=stream, stream_options={"include_usage": True})
    )
    if stream:
        assert status == 200
        frames = [
            line[6:] for line in body.decode().splitlines() if line.startswith("data: ")
        ]
        assert "[DONE]" not in frames
        assert json.loads(frames[-1])["error"]["message"] == "fixture_close_failed"
        assert not any("usage" in json.loads(frame) for frame in frames)
    else:
        assert status == 503
        assert json.loads(body)["error"]["message"] == "fixture_close_failed"
    assert_generation_idle(server)
    monkeypatch.setattr(server.engine, "generate", original)
    with request(base, message()) as response:
        assert json.load(response)["choices"][0]["message"]["content"] == "Dzień dobry"
    assert_generation_idle(server)


def test_finally_releases_lock_even_when_failed_iterator_cleanup_raises(
    bridge, monkeypatch
):
    server, base = bridge
    failed_cleanup, reported_error = threading.Event(), threading.Event()
    errors = []

    class BrokenIterator:
        def __next__(self):
            raise RuntimeError("fixture_generation_failed")

        def close(self):
            failed_cleanup.set()
            raise RuntimeError("fixture_cleanup_failed")

    monkeypatch.setattr(
        server.engine, "generate", lambda *args, **kwargs: BrokenIterator()
    )

    def handle_error(*args):
        errors.append(True)
        reported_error.set()

    monkeypatch.setattr(server, "handle_error", handle_error)
    status, body = completion_result(base, message())
    assert status == 503
    assert json.loads(body)["error"]["message"] == "fixture_generation_failed"
    assert failed_cleanup.wait(1)
    assert_generation_idle(server)
    assert reported_error.wait(1)
    # The cleanup failure remains visible through the server error path; the
    # failed request must not leave the single-worker lock permanently occupied.
    assert errors == [True]


def test_generation_budget_and_cancellation_release_native_generator(fake_native_sdk):
    module, _, seen, path = fake_native_sdk
    engine = module.OnnxEngine(str(path), "fixture-model")
    stats = {}
    iterator = engine.generate(
        validate_request(
            message(max_tokens=2, temperature=0.3, top_k=5), "fixture-model"
        ),
        stats,
    )
    assert list(iterator) == ["1", "2"]
    assert stats == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "finish_reason": "length",
    }
    assert seen["options"][0]["max_length"] == 5
    assert seen["options"][0]["temperature"] == 0.3
    assert seen["providers"] == ["cuda"]
    iterator = engine.generate(validate_request(message(), "fixture-model"), {})
    assert next(iterator) == "1"
    iterator.close()
    assert seen["destroyed"][-1] == 1


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("seed", [-(2**31), -1, 0, 17, 2**31 - 1])
def test_seed_reaches_native_search_unchanged_in_both_transports(
    bridge, fake_native_sdk, stream, seed
):
    server, base = bridge
    module, _, seen, path = fake_native_sdk
    server.engine = module.OnnxEngine(str(path), "fixture-model")
    with request(
        base,
        message(
            max_tokens=2,
            temperature=0.3,
            stream=stream,
            stream_options={"include_usage": True},
            seed=seed,
        ),
    ) as response:
        if stream:
            frames = [
                line[6:]
                for line in response.read().decode().splitlines()
                if line.startswith("data: ")
            ]
            assert frames[-1] == "[DONE]"
            usage = json.loads(frames[-2])["usage"]
            assert json.loads(frames[-3])["choices"][0]["finish_reason"] == "length"
        else:
            body = json.load(response)
            assert body["choices"][0]["message"]["content"] == "12"
            assert body["choices"][0]["finish_reason"] == "length"
            usage = body["usage"]
    assert usage == {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
    assert seen["options"][0]["random_seed"] == seed
    assert type(seen["options"][0]["random_seed"]) is int
    assert seen["calls"] == [
        "model",
        "tokenizer",
        "template",
        "encode",
        "generator",
        "stream",
    ]
    assert seen["providers"] == ["cuda"]
    assert_generation_idle(server)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("seed", [-(2**63), -(2**31) - 1, 2**31, 2**63 - 1])
def test_native_seed_range_failure_precedes_tokenization_and_http_success(
    bridge, fake_native_sdk, stream, seed
):
    server, base = bridge
    module, _, seen, path = fake_native_sdk
    server.engine = module.OnnxEngine(str(path), "fixture-model")
    with pytest.raises(urllib.error.HTTPError) as error:
        request(base, message(seed=seed, stream=stream))
    assert error.value.code == 400
    assert json.load(error.value)["error"] == {
        "message": "seed_out_of_native_range",
        "type": "invalid_request_error",
    }
    assert seen["calls"] == ["model", "tokenizer"]
    assert seen["options"] == []
    assert_generation_idle(server)


def test_seed_is_request_local_and_omission_or_null_does_not_set_native_default(
    fake_native_sdk,
):
    module, _, seen, path = fake_native_sdk
    engine = module.OnnxEngine(str(path), "fixture-model")
    for changes in [{"seed": 0}, {}, {"seed": None}]:
        list(
            engine.generate(
                validate_request(message(max_tokens=1, **changes), "fixture-model"), {}
            )
        )
    assert seen["options"][0]["random_seed"] == 0
    assert all("random_seed" not in options for options in seen["options"][1:])
    assert (
        seen["calls"]
        == ["model", "tokenizer"] + ["template", "encode", "generator", "stream"] * 3
    )


def test_cpu_fallback_is_rejected_instead_of_qualified(fake_native_sdk):
    module, sdk, seen, path = fake_native_sdk
    sdk.Model.device_type = "CPU"
    with pytest.raises(RuntimeError, match="no_cpu_fallback"):
        module.OnnxEngine(str(path), "fixture-model")
    assert seen["released"] == ["model"]


def test_context_and_elapsed_budget_fail_explicitly(fake_native_sdk, monkeypatch):
    from types import SimpleNamespace

    module, _, seen, path = fake_native_sdk
    engine = module.OnnxEngine(str(path), "fixture-model")
    engine.context_length = 3
    with pytest.raises(RequestError, match="context_limit"):
        list(engine.generate(validate_request(message(), "fixture-model"), {}))
    engine.context_length = 2048
    ticks = iter([0, 61])
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    with pytest.raises(TimeoutError, match="deadline"):
        list(engine.generate(validate_request(message(), "fixture-model"), {}))
    assert seen["destroyed"][-1] == 0


@pytest.mark.parametrize("payload", [None, [], {"messages": []}])
def test_nonobject_or_empty_message_requests_are_invalid(payload):
    with pytest.raises(RequestError):
        validate_request(payload, "fixture-model")
