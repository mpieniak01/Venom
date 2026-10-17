"""Bounded, synthetic Ollama checks. No pulls, no production model routing."""

from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import json
import statistics
import struct
import time
import zlib
from dataclasses import dataclass, field
from typing import Any

import httpx

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import WorkloadProfile, digest, now

SUITE_VERSION = "venom-vast-model-v4"


def fixture_image() -> str:
    width = height = 64
    raw = b"".join(
        b"\x00" + (b"\x00\xff\x00" if y < height // 2 else b"\xff\xff\x00") * width
        for y in range(height)
    )

    def chunk(kind, data):
        return (
            struct.pack("!I", len(data))
            + kind
            + data
            + struct.pack("!I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(png).decode()


@dataclass
class StreamCapture:
    started: float
    size: int = 0
    first: float | None = None
    text: str = ""
    last: dict = field(default_factory=dict)
    tool_calls: list[dict] = field(default_factory=list)

    def append(self, line: str) -> bool:
        self.size += len(line)
        if self.size > 2_000_000 or time.monotonic() - self.started > 60:
            raise VastError("vast.sample_limit")
        if not line:
            return False
        item = json.loads(line)
        if item.get("error"):
            raise VastError("vast.backend_error")
        message = item.get("message") or {}
        content = message.get("content") or ""
        if content and self.first is None:
            self.first = time.monotonic() - self.started
        self.text += content
        self.tool_calls.extend(message.get("tool_calls") or [])
        if item.get("done"):
            self.last = item
            return True
        return False


def _capture(client: httpx.Client, body: dict, started: float) -> StreamCapture:
    capture = StreamCapture(started)
    with client.stream("POST", "/api/chat", json=body) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if capture.append(line):
                break
    return capture


def _sample_metrics(capture: StreamCapture) -> dict:
    elapsed = time.monotonic() - capture.started
    result = {
        "status": "ok" if capture.last else "incomplete",
        "wall_s": round(elapsed, 6),
        "ttft_s": round(capture.first, 6) if capture.first is not None else None,
        "response": capture.text[:8192],
        "output_characters": len(capture.text),
        "characters_s": round(len(capture.text) / elapsed, 3) if elapsed > 0 else None,
        "characters_s_basis": "Unicode code points / complete request wall time",
    }
    for key in (
        "load_duration",
        "prompt_eval_count",
        "prompt_eval_duration",
        "eval_count",
        "eval_duration",
    ):
        result[key] = capture.last.get(key)
    for prefix, count, duration in (
        ("decode", "eval_count", "eval_duration"),
        ("prefill", "prompt_eval_count", "prompt_eval_duration"),
    ):
        if capture.last.get(duration):
            result[prefix + "_tokens_s"] = round(
                capture.last.get(count, 0) * 1e9 / capture.last[duration], 3
            )
    return result


def _sample_correct(name: str, capture: StreamCapture) -> bool | None:
    if name == "json":
        return json.loads(capture.text) == {"ok": True}
    if name == "image":
        return "green" in capture.text.lower() and "yellow" in capture.text.lower()
    if name == "tools":
        return any(
            call.get("function", {}).get("name") == "read_benchmark_sensor"
            for call in capture.tool_calls
        )
    return None


def _suite_status(failed: list, count: int, expected: int) -> str:
    if failed:
        return "unsuitable"
    return "suitable" if count == expected else "inconclusive"


class OllamaProbe:
    def __init__(self, client: httpx.Client, profile: WorkloadProfile):
        self.client = client
        self.profile = profile

    def metadata(self) -> dict:
        version = self.client.get("/api/version")
        tags = self.client.get("/api/tags")
        version.raise_for_status()
        tags.raise_for_status()
        models = tags.json().get("models", [])
        candidates = [m for m in models if m.get("name") == self.profile.model]
        if len(candidates) != 1:
            raise VastError("vast.model_missing")
        model = candidates[0]
        if model.get("digest") != self.profile.model_digest:
            raise VastError("vast.model_digest_mismatch")
        return {
            "engine_version": version.json().get("version"),
            "model": self.profile.model,
            "digest": model.get("digest"),
            "size_bytes": model.get("size"),
        }

    def _payload(self, name: str, words: int = 0) -> dict:
        vocabulary = ("red", "blue", "green", "one", "two", "three")
        # Deterministic synthetic prompt data, independent of security randomness.
        entropy = hashlib.shake_256((SUITE_VERSION + name).encode()).digest(words)
        reference = " ".join(vocabulary[value % len(vocabulary)] for value in entropy)
        prompt = f"Run {name}. Reference data: {reference}. Write 30 numbered short steps for assessing a model server."
        return {
            "model": self.profile.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "think": False,
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_ctx": self.profile.context_tokens,
                "num_predict": self.profile.output_tokens,
            },
        }

    def capture(self, body: dict, started: float) -> StreamCapture:
        return _capture(self.client, body, started)

    def sample(self, name: str, body: dict) -> dict:
        started = time.monotonic()
        row: dict[str, Any] = {
            "case": name,
            "request_sha256": digest(body),
            "started_at": now().isoformat(),
        }
        try:
            capture = self.capture(body, started)
            row.update(_sample_metrics(capture))
            correct = _sample_correct(name, capture)
            if correct is not None:
                row["correct"] = correct
        except (httpx.HTTPError, ValueError, TypeError, VastError):
            row.update(
                status="error",
                error="vast.backend_error",
                wall_s=round(time.monotonic() - started, 6),
            )
        return row

    def ready(self) -> dict:
        meta = self.metadata()
        sample = self.sample("readiness", self._payload("readiness"))
        if sample["status"] != "ok":
            raise VastError("vast.model_not_ready")
        return {"runtime": "ready", **meta, "sample": sample}

    def benchmark(self, max_seconds: int = 600) -> dict:
        if not 1 <= max_seconds <= 900:
            raise VastError("vast.invalid_timeout")
        meta = self.metadata()
        rows = []
        started = time.monotonic()
        requests = [("short-" + str(i), 0) for i in range(3)]
        requests += [("medium-" + str(i), 1300) for i in range(2)]
        requests += [("long-" + str(i), 5300) for i in range(2)]
        for name, words in requests:
            if time.monotonic() - started >= max_seconds:
                break
            rows.append(self.sample(name, self._payload(name, words)))
        if time.monotonic() - started < max_seconds:
            batch_start = time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(
                        self.sample,
                        f"parallel-{i}",
                        self._payload(f"parallel-{i}", 1300),
                    )
                    for i in range(2)
                ]
                rows.extend(future.result() for future in futures)
            parallel_wall = time.monotonic() - batch_start
        else:
            parallel_wall = None
        cases = []
        body = self._payload("json")
        body["format"] = "json"
        body["messages"][0]["content"] = 'Return exactly {"ok":true}.'
        cases.append(("json", body))
        body = self._payload("image")
        body["messages"][0].update(
            content="Name the top and bottom colors in order.", images=[fixture_image()]
        )
        cases.append(("image", body))
        body = self._payload("tools")
        body["messages"][0]["content"] = (
            "Call read_benchmark_sensor to get the synthetic temperature."
        )
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "read_benchmark_sensor",
                    "description": "Synthetic sensor; no robot access.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        ]
        cases.append(("tools", body))
        required = self.profile.runtime.capabilities
        selected = [
            (name, body)
            for name, body in cases
            if ("vision" if name == "image" else name) in required
        ]
        for name, body in selected:
            if time.monotonic() - started >= max_seconds:
                break
            rows.append(self.sample(name, body))
        failed = [
            row["case"]
            for row in rows
            if row["status"] != "ok" or row.get("correct") is False
        ]
        ttfts = [
            row["ttft_s"]
            for row in rows
            if row.get("ttft_s") is not None and row["case"].startswith("short")
        ]
        status = _suite_status(failed, len(rows), 9 + len(selected))
        return {
            "schema_version": 1,
            "suite_version": SUITE_VERSION,
            "observed_at": now().isoformat(),
            "status": status,
            "errors": failed,
            "required_capabilities": required,
            "skipped_capabilities": [
                name for name in ["json", "vision", "tools"] if name not in required
            ],
            "metadata": meta,
            "profile": self.profile.model_dump(mode="json"),
            "transport": "SSH forwarding to instance loopback",
            "cache": "Natural first load; OS and prefix cache may already be warm",
            "samples": rows,
            "parallel_wall_s": parallel_wall,
            "short_ttft_median_s": statistics.median(ttfts) if ttfts else None,
            "image_sha256": hashlib.sha256(
                base64.b64decode(fixture_image())
            ).hexdigest(),
            "qualification": "This workload/engine only; failures do not identify a faulty GPU.",
        }


def compare(reports: list[dict]) -> dict:
    if len(reports) < 2:
        raise VastError("vast.two_reports_required")
    keys = [
        digest({k: x.get(k) for k in ("suite_version", "profile", "metadata")})
        for x in reports
    ]
    return {
        "comparable": len(set(keys)) == 1,
        "runs": [
            {
                k: r.get(k)
                for k in ("status", "short_ttft_median_s", "parallel_wall_s", "errors")
            }
            for r in reports
        ],
        "note": "Hardware, engine, model, context and transport differences must be interpreted explicitly.",
    }
