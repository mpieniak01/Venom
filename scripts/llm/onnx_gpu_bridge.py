"""Small text-only OpenAI HTTP boundary for an isolated ONNX GenAI CUDA worker.

No application imports, CPU fallback, model download or second ORT distribution.
Explicit seeds must fit ORT GenAI's native signed32 range; -1 requests its random
device behavior. Omitted/null seeds retain the model's configured default.
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
        config = og.Config(model_path)
        config.clear_providers()
        config.append_provider("cuda")
        self.model = og.Model(config)
        self.device = str(self.model.device_type)
        if self.device.lower() != "cuda":
            raise RuntimeError("cuda_model_required_no_cpu_fallback")
        self.tokenizer = og.Tokenizer(self.model)
        config_data = json.loads((Path(model_path) / "genai_config.json").read_text())
        self.context_length = int(config_data["model"]["context_length"])

    def generate(self, request: dict[str, Any], stats: dict[str, Any]):
        seed = request.get("seed")
        # ORT GenAI 0.12.2: Search.random_seed and Python search-option casts use int32.
        # https://github.com/microsoft/onnxruntime-genai/blob/v0.12.2/src/config.h#L344
        if seed is not None and not -(2**31) <= seed < 2**31:
            raise RequestError("seed_out_of_native_range")
        prompt = self.tokenizer.apply_chat_template(
            json.dumps(request["messages"]), add_generation_prompt=True
        )
        tokens = self.tokenizer.encode(prompt)
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
        params.set_search_options(**options)
        generator = self.og.Generator(self.model, params)
        stream = self.tokenizer.create_stream()
        stats.update(
            prompt_tokens=len(tokens), completion_tokens=0, finish_reason="stop"
        )
        deadline = time.monotonic() + 60
        try:
            generator.append_tokens(tokens)
            while (
                not generator.is_done()
                and stats["completion_tokens"] < request["max_tokens"]
            ):
                if time.monotonic() > deadline:
                    raise TimeoutError("generation_deadline_exceeded")
                generator.generate_next_token()
                stats["completion_tokens"] += 1
                yield stream.decode(generator.get_next_tokens()[0])
            if stats["completion_tokens"] >= request["max_tokens"]:
                stats["finish_reason"] = "length"
        finally:
            del generator


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, engine):
        self.engine = engine
        self.generation_lock = threading.Lock()
        super().__init__(address, BridgeHandler)


class BridgeHandler(BaseHTTPRequestHandler):
    server: BridgeServer

    def log_message(self, format, *args):
        # Never log conversation inputs, authentication headers or request bodies.
        return

    def json_response(self, status: int, payload: dict[str, Any]):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
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
        self.wfile.write(
            ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode()
        )
        self.wfile.flush()

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.json_response(404, {"error": {"message": "unknown_endpoint"}})
            return
        iterator = None
        acquired = False
        streaming = False
        try:
            self.connection.settimeout(5)
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024 * 1024:
                raise RequestError("request_size_out_of_range")
            request = validate_request(
                json.loads(self.rfile.read(size)), self.server.engine.model_name
            )
            acquired = self.server.generation_lock.acquire(blocking=False)
            if not acquired:
                self.json_response(429, {"error": {"message": "worker_busy"}})
                return
            stats: dict[str, Any] = {}
            iterator = self.server.engine.generate(request, stats)
            first = next(
                iterator, ""
            )  # Fail before 200 headers if tokenization/model execution fails.
            stamp = {
                "id": "chatcmpl-" + uuid.uuid4().hex,
                "created": int(time.time()),
                "model": self.server.engine.model_name,
            }
            if request.get("stream", False):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                streaming = True

                def chunk(delta, finish=None):
                    return dict(
                        stamp,
                        object="chat.completion.chunk",
                        choices=[{"index": 0, "delta": delta, "finish_reason": finish}],
                    )

                self.event(chunk({"role": "assistant"}))
                if first:
                    self.event(chunk({"content": first}))
                for piece in iterator:
                    if piece:
                        self.event(chunk({"content": piece}))
                self.event(chunk({}, stats["finish_reason"]))
                if request.get("stream_options", {}).get("include_usage", False):
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
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            else:
                content = first + "".join(iterator)
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
        except (BrokenPipeError, ConnectionResetError):
            pass  # Closing the iterator below cancels further token generation.
        except (ValueError, UnicodeError) as error:
            if streaming:
                self.event(
                    {"error": {"message": str(error), "type": "invalid_request_error"}}
                )
            else:
                self.json_response(
                    400,
                    {"error": {"message": str(error), "type": "invalid_request_error"}},
                )
        except Exception as error:  # noqa: BLE001 - Native engine exceptions must become explicit HTTP failures.
            if streaming:
                self.event({"error": {"message": str(error), "type": "engine_error"}})
            else:
                self.json_response(
                    503, {"error": {"message": str(error), "type": "engine_error"}}
                )
        finally:
            if iterator is not None:
                iterator.close()
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
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
