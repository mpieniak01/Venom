"""Check video and realtime speech on an isolated llama.cpp LFM3-Omni server."""

from __future__ import annotations

import argparse
import base64
import json
import time
import wave
from pathlib import Path

import httpx
from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from scripts.ollama_bench.lfm3_cases import MEDIA
from scripts.ollama_bench.run_lfm3 import (
    OMNI,
    ResourceSampler,
    encode,
    error_text,
    wav_details,
    write_row,
)


def video(client: httpx.Client, prompt: str, media: Path) -> dict:
    content = [
        {"type": "text", "text": prompt},
        {
            "type": "input_video",
            "input_video": {"data": "data:video/mp4;base64," + encode(media)},
        },
    ]
    request = {
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": 96,
        "stream": True,
    }
    start = time.perf_counter()
    first_s = None
    answer: list[str] = []
    timings = {}
    with client.stream("POST", "/v1/chat/completions", json=request) as response:
        if response.is_error:
            response.read()
        response.raise_for_status()
        for line in response.iter_lines():
            if line == "data: [DONE]":
                break
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if "error" in event:
                raise RuntimeError(str(event["error"]))
            for choice in event["choices"]:
                if text := choice["delta"].get("content"):
                    first_s = (
                        first_s if first_s is not None else time.perf_counter() - start
                    )
                    answer.append(text)
            timings.update(event.get("timings", {}))
        else:
            raise RuntimeError("SSE response ended without [DONE]")
    return {
        "status": "REVIEW" if answer else "FAIL",
        "answer": "".join(answer),
        "first_s": first_s,
        "total_s": time.perf_counter() - start,
        "timings": timings,
    }


def realtime(port: int, input_file: Path, output_file: Path) -> dict:
    with wave.open(str(input_file)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (
            16000,
            1,
            2,
        ):
            raise ValueError("Expected 16 kHz PCM16 mono input")
        samples = wav.readframes(wav.getnframes())
    with connect(f"ws://127.0.0.1:{port}/v1/realtime", open_timeout=10) as socket:
        event = json.loads(socket.recv(timeout=10))
        if event["type"] != "session.created":
            raise RuntimeError(str(event))
        output_rate = event["session"]["audio"]["output"]["format"]["rate"]
        socket.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "instructions": "Powtórz głosem po polsku obie czynności z nagrania. Niczego nie wykonuj.",
                        "output_modalities": ["audio"],
                        "max_output_tokens": 400,
                    },
                }
            )
        )
        for offset in range(0, len(samples), 3200):
            encoded = base64.b64encode(samples[offset : offset + 3200]).decode("ascii")
            socket.send(
                json.dumps({"type": "input_audio_buffer.append", "audio": encoded})
            )
        start = time.perf_counter()
        socket.send(json.dumps({"type": "response.create"}))
        chunks = []
        events = []
        first_s = None
        deadline = start + 120
        while True:
            timeout = max(0, deadline - time.perf_counter())
            event = json.loads(socket.recv(timeout=timeout))
            elapsed = time.perf_counter() - start
            kind = event["type"]
            if kind == "error":
                raise RuntimeError(str(event["error"]))
            events.append({"type": kind, "elapsed_s": elapsed})
            if kind == "response.output_audio.delta":
                first_s = elapsed if first_s is None else first_s
                chunks.append(base64.b64decode(event["delta"], validate=True))
            if kind == "response.done":
                response_status = event["response"]["status"]
                break
    if not chunks or response_status != "completed":
        return {"status": "FAIL", "response_status": response_status, "events": events}
    with wave.open(str(output_file), "wb") as wav:
        wav.setparams((1, 2, output_rate, 0, "NONE", "not compressed"))
        wav.writeframes(b"".join(chunks))
    return {
        "status": "REVIEW",
        "chunks": len(chunks),
        "first_audio_s": first_s,
        "total_s": elapsed,
        "events": events,
        "wav": str(output_file),
        **wav_details(output_file),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=11436)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.port not in range(1, 65536) or args.port == 11434 or args.repeats < 1:
        parser.error("Use a separate port and a positive repetition count.")
    args.output.mkdir(parents=True, exist_ok=True)
    results = args.output / "results.jsonl"
    results.touch(exist_ok=False)
    with httpx.Client(
        base_url=f"http://127.0.0.1:{args.port}", timeout=120, trust_env=False
    ) as client:
        props = client.get("/props")
        props.raise_for_status()
        write_row(
            results, model=OMNI, case="METADATA", status="INFO", props=props.json()
        )
        warmup = client.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Reply OK."}],
                "max_tokens": 8,
            },
        )
        warmup.raise_for_status()
        for case in (item for item in MEDIA if item.id in {"M11", "M12"}):
            for trial in range(1, args.repeats + 1):
                with ResourceSampler() as sample:
                    try:
                        row = video(client, case.prompt, args.fixtures / case.media[0])
                    except (
                        httpx.HTTPError,
                        KeyError,
                        OSError,
                        RuntimeError,
                        ValueError,
                    ) as exc:
                        row = {"status": "BLOCKED", "error": error_text(exc)}
                write_row(
                    results,
                    model=OMNI,
                    case=case.id,
                    trial=trial,
                    expected=case.expected,
                    prompt=case.prompt,
                    media=case.media,
                    resources=sample.summary(),
                    **row,
                )
    for trial in range(1, args.repeats + 1):
        with ResourceSampler() as sample:
            try:
                row = realtime(
                    args.port,
                    args.fixtures / "intent.wav",
                    args.output / f"realtime-{trial}.wav",
                )
            except (
                KeyError,
                OSError,
                RuntimeError,
                ValueError,
                wave.Error,
                WebSocketException,
            ) as exc:
                row = {"status": "BLOCKED", "error": error_text(exc)}
        write_row(
            results,
            model=OMNI,
            case="M13",
            trial=trial,
            resources=sample.summary(),
            **row,
        )
        if row["status"] == "REVIEW":
            streaming = row["chunks"] > 1 and row["first_audio_s"] < row["total_s"]
            write_row(
                results,
                model=OMNI,
                case="M14",
                trial=trial,
                status="PASS" if streaming else "FAIL",
                chunks=row["chunks"],
                first_audio_s=row["first_audio_s"],
                total_s=row["total_s"],
            )
        else:
            write_row(
                results,
                model=OMNI,
                case="M14",
                trial=trial,
                status="BLOCKED",
                error=row.get("error", "No complete audio response"),
            )


if __name__ == "__main__":
    main()
