"""Small text-only OpenAI HTTP boundary for an isolated ONNX GenAI CUDA worker.

No application imports, CPU fallback, model download or second ORT distribution.
Explicit seeds must fit ORT GenAI's native signed32 range; -1 requests its random
device behavior. Omitted/null seeds retain the model's configured default.
Shutdown is cooperative between native calls; an in-flight GPU call is never
interrupted. The bounded cleanup wait is not a native execution deadline.
"""

from __future__ import annotations

import argparse
import importlib
import json
import signal
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class RequestError(ValueError):
    """The requested operation is outside this worker's explicit contract."""


class GenerationCancelled(RuntimeError):
    """Shutdown was observed before or between native generation calls."""


class ClientDisconnected(Exception):
    """Socket I/O failed; do not attempt another response on this connection."""


def check_stopping(stop_event: threading.Event | None) -> None:
    if stop_event is not None and stop_event.is_set():
        raise GenerationCancelled("worker_stopping")


def validate_request(data: Any, model_name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RequestError("request_must_be_an_object")
    supported = {
        "model",
        "messages",
        "stream",
        "stream_options",
        "max_tokens",
        "max_completion_tokens",
        "temperature",
        "top_p",
        "top_k",
        "repetition_penalty",
        "seed",
    }
    if set(data) - supported:
        raise RequestError(
            "unsupported_parameters: " + ",".join(sorted(set(data) - supported))
        )
    if data.get("model", model_name) != model_name:
        raise RequestError("unknown_model")
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages or len(messages) > 100:
        raise RequestError("nonempty_messages_required")
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {
            "system",
            "user",
            "assistant",
        }:
            raise RequestError("text_conversation_roles_required")
        if not isinstance(message.get("content"), str):
            raise RequestError("text_content_required")
    tokens = data.get("max_completion_tokens", data.get("max_tokens", 64))
    if type(tokens) is not int or not 1 <= tokens <= 512:
        raise RequestError("max_tokens_out_of_range")
    if (
        "max_tokens" in data
        and "max_completion_tokens" in data
        and data["max_tokens"] != tokens
    ):
        raise RequestError("conflicting_token_limits")
    if type(data.get("stream", False)) is not bool:
        raise RequestError("stream_must_be_boolean")
    stream_options = data.get("stream_options", {})
    if (
        not isinstance(stream_options, dict)
        or set(stream_options) - {"include_usage"}
        or type(stream_options.get("include_usage", False)) is not bool
    ):
        raise RequestError("unsupported_stream_options")
    seed = data.get("seed")
    if seed is not None and (type(seed) is not int or not -(2**63) <= seed < 2**63):
        raise RequestError("seed_must_be_signed_64_bit_integer")
    result = dict(data, model=model_name, max_tokens=tokens)
    for name, low, high, default in [
        ("temperature", 0, 2, 0),
        ("top_p", 0.0001, 1, 1),
        ("repetition_penalty", 0.01, 10, 1),
    ]:
        value = data.get(name, default)
        if type(value) not in {int, float} or not low <= value <= high:
            raise RequestError(f"{name}_out_of_range")
        result[name] = value
    if "top_k" in data and (
        type(data["top_k"]) is not int or not 0 <= data["top_k"] <= 1000
    ):
        raise RequestError("top_k_out_of_range")
    return result


class OnnxEngine:
    def __init__(self, model_path: str, model_name: str):
        og = importlib.import_module("onnxruntime_genai")

        self.og = og
        self.model_name = model_name
        self.model: Any = None
        self.tokenizer: Any = None
        try:
            config = og.Config(model_path)
            config.clear_providers()
            config.append_provider("cuda")
            self.model = og.Model(config)
            self.device = str(self.model.device_type).lower()
            if self.device != "cuda":
                raise RuntimeError("cuda_model_required_no_cpu_fallback")
            self.tokenizer = og.Tokenizer(self.model)
            config_data = json.loads(
                (Path(model_path) / "genai_config.json").read_text()
            )
            self.context_length = int(config_data["model"]["context_length"])
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        """Release owned native references in order; callers must exclude generation."""
        self.tokenizer = None
        self.model = None

    def generate(
        self,
        request: dict[str, Any],
        stats: dict[str, Any],
        stop_event: threading.Event | None = None,
    ):
        check_stopping(stop_event)
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("engine_closed")
        seed = request.get("seed")
        # ORT GenAI 0.12.2: Search.random_seed and Python search-option casts use int32.
        # https://github.com/microsoft/onnxruntime-genai/blob/v0.12.2/src/config.h#L344
        if seed is not None and not -(2**31) <= seed < 2**31:
            raise RequestError("seed_out_of_native_range")
        check_stopping(stop_event)
        prompt = self.tokenizer.apply_chat_template(
            json.dumps(request["messages"]), add_generation_prompt=True
        )
        check_stopping(stop_event)
        tokens = self.tokenizer.encode(prompt)
        check_stopping(stop_event)
        if len(tokens) + request["max_tokens"] > min(self.context_length, 2048):
            raise RequestError("context_limit_exceeded")
        params = self.og.GeneratorParams(self.model)
        options = {
            "max_length": len(tokens) + request["max_tokens"],
            "do_sample": request["temperature"] > 0,
            "top_p": request["top_p"],
            "repetition_penalty": request["repetition_penalty"],
        }
        if request["temperature"] > 0:
            options["temperature"] = request["temperature"]
        if "top_k" in request:
            options["top_k"] = request["top_k"]
        if seed is not None:
            options["random_seed"] = seed
        check_stopping(stop_event)
        params.set_search_options(**options)
        check_stopping(stop_event)
        generator = self.og.Generator(self.model, params)
        try:
            check_stopping(stop_event)
            stream = self.tokenizer.create_stream()
            stats.update(
                prompt_tokens=len(tokens), completion_tokens=0, finish_reason="stop"
            )
            deadline = time.monotonic() + 60
            check_stopping(stop_event)
            generator.append_tokens(tokens)
            while True:
                check_stopping(stop_event)
                if (
                    stats["completion_tokens"] >= request["max_tokens"]
                    or generator.is_done()
                ):
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("generation_deadline_exceeded")
                check_stopping(stop_event)
                generator.generate_next_token()
                check_stopping(stop_event)
                stats["completion_tokens"] += 1
                next_tokens = generator.get_next_tokens()
                check_stopping(stop_event)
                piece = stream.decode(next_tokens[0])
                check_stopping(stop_event)
                yield piece
            check_stopping(stop_event)
            if stats["completion_tokens"] >= request["max_tokens"]:
                stats["finish_reason"] = "length"
        finally:
            del generator


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    io_timeout = 5.0
    shutdown_timeout = (
        6.0  # Socket timeout plus margin; cannot interrupt a native call.
    )

    def __init__(self, address, engine):
        self.engine = engine
        self.generation_lock = threading.Lock()
        self.stop_event = threading.Event()
        super().__init__(address, BridgeHandler)

    def shutdown(self) -> None:
        self.stop_event.set()
        super().shutdown()

    def server_close(self) -> None:
        self.stop_event.set()
        super().server_close()
        if not self.generation_lock.acquire(timeout=self.shutdown_timeout):
            raise RuntimeError("active_generation_shutdown_timeout")
        try:
            self.engine.close()
        finally:
            self.generation_lock.release()


class BridgeHandler(BaseHTTPRequestHandler):
    server: BridgeServer

    def log_message(self, format, *args):
        # Never log conversation inputs, authentication headers or request bodies.
        return

    def setup(self):
        super().setup()
        self.connection.settimeout(self.server.io_timeout)

    def json_response(self, status: int, payload: dict[str, Any]):
        body = json.dumps(payload, ensure_ascii=False).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError as error:
            raise ClientDisconnected from error

    def error_response(self, status, kind, error, streaming=False):
        payload = {"error": {"message": str(error), "type": kind}}
        try:
            if streaming:
                self.event(payload)
            else:
                self.json_response(status, payload)
        except ClientDisconnected:
            pass

    def do_GET(self):
        try:
            check_stopping(self.server.stop_event)
            self.get_response()
        except GenerationCancelled as error:
            self.error_response(503, "generation_cancelled", error)
        except ClientDisconnected:
            pass

    def get_response(self):
        if self.path == "/health":
            self.json_response(
                200,
                {
                    "status": "ok",
                    "engine": "onnx-gpu",
                    "device": self.server.engine.device,
                },
            )
        elif self.path == "/v1/models":
            self.json_response(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.server.engine.model_name,
                            "object": "model",
                            "owned_by": "local",
                        }
                    ],
                },
            )
        else:
            self.json_response(404, {"error": {"message": "unknown_endpoint"}})

    def event(self, payload):
        self.write_event(json.dumps(payload, ensure_ascii=False))

    def write_event(self, data: str):
        try:
            self.wfile.write(("data: " + data + "\n\n").encode())
            self.wfile.flush()
        except OSError as error:
            raise ClientDisconnected from error

    def do_POST(self):
        iterator = None
        acquired = False
        streaming = False
        try:
            check_stopping(self.server.stop_event)
            if self.path != "/v1/chat/completions":
                self.json_response(404, {"error": {"message": "unknown_endpoint"}})
                return
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024 * 1024:
                raise RequestError("request_size_out_of_range")
            try:
                body = self.rfile.read(size)
            except OSError as error:
                raise ClientDisconnected from error
            check_stopping(self.server.stop_event)
            request = validate_request(json.loads(body), self.server.engine.model_name)
            check_stopping(self.server.stop_event)
            acquired = self.server.generation_lock.acquire(blocking=False)
            if not acquired:
                check_stopping(self.server.stop_event)
                self.json_response(429, {"error": {"message": "worker_busy"}})
                return
            check_stopping(self.server.stop_event)
            stats: dict[str, Any] = {}
            iterator = self.server.engine.generate(
                request, stats, stop_event=self.server.stop_event
            )
            first = next(
                iterator, ""
            )  # Fail before 200 headers if tokenization/model execution fails.
            check_stopping(self.server.stop_event)
            stamp = {
                "id": "chatcmpl-" + uuid.uuid4().hex,
                "created": int(time.time()),
                "model": self.server.engine.model_name,
            }
            if request.get("stream", False):
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                except OSError as error:
                    raise ClientDisconnected from error
                streaming = True

                def chunk(delta, finish=None):
                    return dict(
                        stamp,
                        object="chat.completion.chunk",
                        choices=[{"index": 0, "delta": delta, "finish_reason": finish}],
                    )

                check_stopping(self.server.stop_event)
                self.event(chunk({"role": "assistant"}))
                if first:
                    check_stopping(self.server.stop_event)
                    self.event(chunk({"content": first}))
                for piece in iterator:
                    check_stopping(self.server.stop_event)
                    if piece:
                        self.event(chunk({"content": piece}))
                closing_iterator, iterator = iterator, None
                closing_iterator.close()
                check_stopping(self.server.stop_event)
                self.event(chunk({}, stats["finish_reason"]))
                if request.get("stream_options", {}).get("include_usage", False):
                    check_stopping(self.server.stop_event)
                    self.event(
                        dict(
                            stamp,
                            object="chat.completion.chunk",
                            choices=[],
                            usage={
                                "prompt_tokens": stats["prompt_tokens"],
                                "completion_tokens": stats["completion_tokens"],
                                "total_tokens": stats["prompt_tokens"]
                                + stats["completion_tokens"],
                            },
                        )
                    )
                check_stopping(self.server.stop_event)
                self.write_event("[DONE]")
            else:
                pieces = [first]
                for piece in iterator:
                    check_stopping(self.server.stop_event)
                    pieces.append(piece)
                closing_iterator, iterator = iterator, None
                closing_iterator.close()
                check_stopping(self.server.stop_event)
                content = "".join(pieces)
                self.json_response(
                    200,
                    dict(
                        stamp,
                        object="chat.completion",
                        choices=[
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": content},
                                "finish_reason": stats["finish_reason"],
                            }
                        ],
                        usage={
                            "prompt_tokens": stats["prompt_tokens"],
                            "completion_tokens": stats["completion_tokens"],
                            "total_tokens": stats["prompt_tokens"]
                            + stats["completion_tokens"],
                        },
                    ),
                )
        except (ClientDisconnected, BrokenPipeError, ConnectionResetError):
            pass  # Iterator cleanup below cancels further token generation.
        except GenerationCancelled as error:
            self.error_response(503, "generation_cancelled", error, streaming)
        except (ValueError, UnicodeError) as error:
            self.error_response(400, "invalid_request_error", error, streaming)
        except Exception as error:  # noqa: BLE001 - Native engine exceptions must become explicit HTTP failures.
            self.error_response(503, "engine_error", error, streaming)
        finally:
            try:
                if iterator is not None:
                    iterator.close()
            finally:
                if acquired:
                    self.server.generation_lock.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    engine = OnnxEngine(args.model, args.model_name)
    server = BridgeServer((args.host, args.port), engine)

    def stop(signum, frame):
        server.stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    try:
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
