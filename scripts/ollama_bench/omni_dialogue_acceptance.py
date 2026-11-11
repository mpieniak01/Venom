"""Replay the frozen Omni dialogue cases on local Venom transports, outside CI."""

from __future__ import annotations

import argparse
import base64
import io
import json
import statistics
import time
import wave
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

import httpx
from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from scripts.ollama_bench.omni_dialogue_fixtures import verify
from scripts.ollama_bench.omni_pilot import digest, write_json
from scripts.ollama_bench.polish_benchmark import exact
from scripts.ollama_bench.run_lfm3 import ResourceSampler

AUDIO = "/api/v1/chat/audio"
MATERIALS = "/api/v1/chat/materials"
CHAT = "/api/v1/llm/simple/stream"
ARMS = ("cascade", "interleaved", "audio")
MODEL = "lfm3-omni:2b"
TIMEOUT = 120


def pcm(blob: bytes, expected_rate: int) -> bytes:
    with wave.open(io.BytesIO(blob), "rb") as source:
        if (
            source.getnchannels() != 1
            or source.getsampwidth() != 2
            or source.getframerate() != expected_rate
        ):
            raise ValueError("Unexpected WAV format")
        audio = source.readframes(source.getnframes())
    if not audio:
        raise ValueError("Empty audio")
    return audio


def wav_bytes(audio: bytes, rate: int) -> bytes:
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as output:
            output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
            output.writeframes(audio)
        return buffer.getvalue()


def require_ok(response: httpx.Response) -> httpx.Response:
    if not response.is_success:
        raise RuntimeError(f"HTTP {response.status_code} {response.text[:300]}")
    return response


def _verify_native(result, mode):
    if (
        result.get("generation_mode") != mode
        or result.get("pipeline_id") != "omni_native_dialogue"
        or result.get("generation_count") != 1
        or not result.get("model_revision")
    ):
        raise RuntimeError("Turn did not confirm exactly one native generation")


def _native_http(client, session_id, recording, image, mode):
    files = {"audio": ("input.pcm", recording, "application/octet-stream")}
    if image is not None:
        files["image"] = ("input.png", image, "image/png")
    result = require_ok(
        client.post(
            f"{AUDIO}/multimodal-turn",
            data={
                "session_id": session_id,
                "sample_rate": "16000",
                "language": "pl",
                "generation_mode": mode,
            },
            files=files,
        )
    ).json()
    _verify_native(result, mode)
    if result.get("no_speech"):
        raise RuntimeError("Non-silent case was handled as silence")
    output = base64.b64decode(result.pop("audio_base64"), validate=True)
    return result, output


def _native_ws(socket, recording, image, mode):
    start = {
        "command": "start_recording",
        "format": "pcm16",
        "sample_rate": 16000,
        "channels": 1,
        "multimodal": True,
        "generation_mode": mode,
    }
    if image is not None:
        start["image"] = base64.b64encode(image).decode("ascii")
    socket.send(json.dumps(start))
    event = json.loads(socket.recv(timeout=TIMEOUT))
    if event.get("type") != "recording_started":
        raise RuntimeError(f"Unexpected start event: {event.get('type')}")
    socket.send(recording)
    started = time.perf_counter()
    socket.send(json.dumps({"command": "stop_recording"}))
    events = []
    answer = None
    audio = bytearray()
    rate = None
    while True:
        remaining = TIMEOUT - (time.perf_counter() - started)
        if remaining <= 0:
            raise TimeoutError("Native WebSocket turn deadline")
        event = json.loads(socket.recv(timeout=remaining))
        kind = event.get("type")
        events.append({"type": kind, "ms": (time.perf_counter() - started) * 1000})
        if kind == "error":
            raise RuntimeError(str(event.get("reason_code") or event.get("message")))
        if kind == "transcription":
            raise RuntimeError("Native dialogue emitted a separate transcription")
        if kind == "response_text":
            answer = event.get("text")
        if kind == "audio_response":
            rate = event["sample_rate"]
            audio.extend(base64.b64decode(event["audio"], validate=True))
        if kind == "complete":
            _verify_native(event, mode)
            break
    if rate != 24000 or not audio:
        raise RuntimeError("Missing 24 kHz native audio")
    first_audio = next(
        event["ms"] for event in events if event["type"] == "audio_response"
    )
    return {
        "text": answer,
        "generation_mode": mode,
        **{
            key: event.get(key)
            for key in (
                "pipeline_id",
                "generation_count",
                "model_revision",
                "timings_ms",
                "peak_reserved_mib",
                "has_image",
            )
        },
        "audio_ready_ms": first_audio,
        "events": events,
    }, wav_bytes(bytes(audio), rate)


def _stream_text(client, body):
    answer = []
    done = False
    event = ""
    with client.stream("POST", CHAT, json=body) as response:
        if not response.is_success:
            response.read()
            require_ok(response)
        for line in response.iter_lines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            if line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
                if event == "error":
                    raise RuntimeError(f"Cascade text error: {data}")
                if event == "content":
                    answer.append(data["text"])
                done = done or event == "done"
    if not done or not answer:
        raise RuntimeError("Cascade text response incomplete")
    return "".join(answer)


def _cascade(client, session_id, recording, image, history, attachments):
    """Compare the existing ASR, Direct/materials and native speech endpoints."""
    if image is not None:
        result = require_ok(
            client.post(
                MATERIALS,
                params={"session_id": session_id, "name": "input.png"},
                headers={"Content-Type": "image/png"},
                content=image,
            )
        )
        attachments.append(result.json()["id"])
    transcription = require_ok(
        client.post(
            f"{AUDIO}/transcribe",
            params={
                "session_id": session_id,
                "sample_rate": 16000,
                "language": "pl",
                "prefer_native": "true",
            },
            headers={"Content-Type": "application/octet-stream"},
            content=recording,
        )
    ).json()
    if transcription.get("pipeline") != "ollama_audio":
        raise RuntimeError("Cascade did not use Omni ASR")
    question = transcription["text"]
    answer = _stream_text(
        client,
        {
            "session_id": session_id,
            "content": question,
            "history": history,
            "model": MODEL,
            "material_ids": attachments[-1:],
            "stream": True,
            "temperature": 0,
            "max_tokens": 128,
            "seed": 42,
            "think": False,
        },
    )
    output = require_ok(
        client.post(
            f"{AUDIO}/speak",
            json={
                "session_id": session_id,
                "text": answer,
                "language": "pl",
                "prefer_native": True,
            },
        )
    ).content
    history.extend(
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    )
    return {"text": answer, "transcript": question}, output


def _transport(client, surface, arm):
    if surface == "full" and arm != "cascade":
        scheme = "wss" if client.base_url.scheme == "https" else "ws"
        endpoint = str(client.base_url.copy_with(scheme=scheme)).rstrip("/")
        try:
            return connect(
                endpoint + "/ws/audio",
                origin=str(client.base_url).rstrip("/"),
                proxy=None,
                open_timeout=10,
                close_timeout=5,
                max_size=35_000_000,
            )
        except OSError as exc:
            raise RuntimeError(f"Full WebSocket connection failed: {exc}") from exc
    return nullcontext()


def run_case(client, fixtures, output, surface, arm, case):
    sid = f"omni-bench-{uuid4().hex}"
    history = []
    attachments = []
    rows = []
    try:
        with _transport(client, surface, arm) as socket:
            if socket is not None:
                socket.send(json.dumps({"command": "voice_mode", "mode": "direct"}))
                event = json.loads(socket.recv(timeout=10))
                if event.get("type") != "voice_mode" or event.get("mode") != "direct":
                    raise RuntimeError("Full did not enter Direct voice mode")
            for index, turn in enumerate(case["turns"], 1):
                recording = pcm((fixtures / turn["wav"]).read_bytes(), 16000)
                image = (
                    (fixtures / turn["image"]).read_bytes() if "image" in turn else None
                )
                start = time.perf_counter()
                if arm == "cascade":
                    row, speech = _cascade(
                        client, sid, recording, image, history, attachments
                    )
                elif socket is None:
                    row, speech = _native_http(client, sid, recording, image, arm)
                else:
                    row, speech = _native_ws(socket, recording, image, arm)
                row.setdefault("audio_ready_ms", (time.perf_counter() - start) * 1000)
                audio = pcm(speech, 24000)
                file = output / f"{surface}-{arm}-{case['id']}-{index}.wav"
                file.write_bytes(speech)
                row.update(
                    wav=file.name,
                    sha256=digest(file),
                    audio_duration_s=len(audio) / 48000,
                    turn=index,
                    text_exact=(
                        exact(row["text"], case["expected"])
                        if index == len(case["turns"])
                        and isinstance(row.get("text"), str)
                        else None
                    ),
                )
                rows.append(row)
    finally:
        for material in attachments:
            client.delete(f"{MATERIALS}/{material}", params={"session_id": sid})
    return rows


def run_matrix(fixtures, output, urls, cases, arms):
    output.mkdir(parents=True)
    audio = output / "audio"
    audio.mkdir()
    write_json(
        output / "identity.json",
        {
            "manifest_sha256": digest(fixtures / "manifest.json"),
            "cases": [case["id"] for case in cases],
            "arms": arms,
            "set_B": "closed",
            "protocol": "Studio HTTP and Full WS for B, composed app HTTP cascade for A",
        },
    )
    with (output / "rows.jsonl").open("x", encoding="utf-8", buffering=1) as log:
        for surface, url in urls.items():
            with httpx.Client(
                base_url=url, headers={"Origin": url}, timeout=TIMEOUT, trust_env=False
            ) as client:
                for arm in arms:
                    run_arm(client, fixtures, output, audio, log, surface, arm, cases)


def run_arm(client, fixtures, output, audio, log, surface, arm, cases):
    latencies = []
    failed = 0
    with ResourceSampler() as resources:
        for case in cases:
            row = {
                "surface": surface,
                "arm": arm,
                "case": case["id"],
                "expected": case["expected"],
            }
            try:
                row["turns"] = run_case(client, fixtures, audio, surface, arm, case)
                latencies.append(row["turns"][-1]["audio_ready_ms"])
            except (
                ValueError,
                RuntimeError,
                TimeoutError,
                httpx.HTTPError,
                WebSocketException,
                wave.Error,
                EOFError,
            ) as exc:
                row["error"] = str(exc)
                failed += 1
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(surface, arm, case["id"], row.get("error", "WAV"), flush=True)
    write_json(
        output / f"{surface}-{arm}-summary.json",
        {
            "total": len(cases),
            "errors": failed,
            "audio_ready_median_ms": statistics.median(latencies)
            if latencies
            else None,
            "resources": resources.summary(),
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--studio", help="Local Studio HTTP origin")
    parser.add_argument("--full", help="Local Full HTTP and WebSocket origin")
    parser.add_argument("--arm", action="append", choices=ARMS)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    urls = {
        key: url.rstrip("/")
        for key in ("studio", "full")
        if (url := getattr(args, key))
    }
    if not urls or any(
        httpx.URL(url).host not in {"localhost", "127.0.0.1", "::1"}
        for url in urls.values()
    ):
        parser.error("Specify at least one loopback origin")
    manifest = verify(args.fixtures)
    cases = [
        case for case in manifest["cases"] if not args.case or case["id"] in args.case
    ]
    if not cases or (args.case and {case["id"] for case in cases} != set(args.case)):
        parser.error("Unknown scenario ID")
    run_matrix(args.fixtures, args.output, urls, cases, args.arm or ARMS)


if __name__ == "__main__":
    main()
