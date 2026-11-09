"""Run the isolated LFM3/Gemma qualification. No application or system tools run."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from scripts.ollama_bench.lfm3_cases import (
    MEDIA,
    SCHEMA,
    TEXT,
    TTS_TEXTS,
    Case,
    make_fixtures,
)

MODELS = ("lfm3:1.7b", "lfm3-omni:2b", "gemma4:e4b")
OMNI = MODELS[1]
CTX = 4096
WARM = {"role": "user", "content": "Reply OK."}
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "string"}},
                "required": ["item_id"],
            },
        },
    }
    for name, description in (
        ("lookup_item", "Return the catalog color of an item by its ID."),
        ("lookup_stock", "Return the stock count of an item by its ID."),
    )
]


def encode(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def json_post(client: httpx.Client, route: str, **data) -> dict:
    response = client.post(route, json=data)
    response.raise_for_status()
    return response.json()


def chat(client: httpx.Client, model: str, messages: list, **extra) -> dict:
    content: list[str] = []
    thinking: list[str] = []
    calls: list[dict] = []
    first_s = None
    start = time.perf_counter()
    with client.stream(
        "POST",
        "/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": True,
            "think": False,
            "keep_alive": "3m",
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_ctx": CTX,
                "num_predict": 192,
            },
            **extra,
        },
    ) as response:
        if response.is_error:
            response.read()
        response.raise_for_status()
        last = {}
        for line in response.iter_lines():
            chunk = json.loads(line)
            if "error" in chunk:
                raise RuntimeError(chunk["error"])
            message = chunk.get("message", {})
            content.append(message.get("content", ""))
            thinking.append(message.get("thinking", ""))
            calls.extend(message.get("tool_calls", []))
            if first_s is None and (
                content[-1] or thinking[-1] or message.get("tool_calls")
            ):
                first_s = time.perf_counter() - start
            last = chunk
    if not last.get("done"):
        raise RuntimeError("Ollama stream ended without a done event")
    elapsed = time.perf_counter() - start
    eval_ns = last.get("eval_duration", 0)
    return {
        "message": {
            "role": "assistant",
            "content": "".join(content),
            "thinking": "".join(thinking),
            "tool_calls": calls,
        },
        "first_s": first_s,
        "total_s": elapsed,
        "done_reason": last.get("done_reason"),
        "load_s": last.get("load_duration", 0) / 1e9,
        "prompt_tokens": last.get("prompt_eval_count"),
        "generated_tokens": last.get("eval_count"),
        "tokens_s": last["eval_count"] / (eval_ns / 1e9)
        if eval_ns and last.get("eval_count")
        else None,
    }


def valid_call(result: dict) -> bool:
    calls = result["message"]["tool_calls"]
    if len(calls) != 1:
        return False
    function = calls[0].get("function", {})
    return function.get("name") == "lookup_item" and function.get("arguments") == {
        "item_id": "VEN-42"
    }


def run_chat(client: httpx.Client, model: str, case: Case, fixtures: Path) -> dict:
    messages = [{"role": "user", "content": case.prompt}]
    if case.system:
        messages.insert(0, {"role": "system", "content": case.system})
    if case.media:
        # Ollama v0.40.13 uses the native media array for both image and WAV bytes.
        messages[-1]["images"] = [encode(fixtures / name) for name in case.media]
    if case.id == "T09":
        messages[:0] = [
            {"role": "user", "content": "Remember the label mewa-73. Reply OK."},
            {"role": "assistant", "content": "OK."},
            {"role": "user", "content": "What is 2 + 2?"},
            {"role": "assistant", "content": "4."},
        ]
    extra = {"format": SCHEMA} if case.id == "T04" else {}
    if case.id == "T05":
        extra["tools"] = TOOLS
    first = chat(client, model, messages, **extra)
    if case.id != "T05" or not valid_call(first):
        return first
    # Dispatch only the exact allowlisted function with the exact fixture ID.
    tool_result = {"item_id": "VEN-42", "color": "indigo"}
    messages.extend(
        [
            first["message"],
            {
                "role": "tool",
                "tool_name": "lookup_item",
                "content": json.dumps(tool_result),
            },
        ]
    )
    followup = chat(client, model, messages, **extra)
    return {
        **first,
        "total_s": first["total_s"] + followup["total_s"],
        "tool_result": tool_result,
        "followup": followup,
    }


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.casefold())


def word_error_rate(reference: str, answer: str) -> float:
    expected = words(reference)
    costs = list(range(len(expected) + 1))
    for row, token in enumerate(words(answer), 1):
        updated = [row]
        for col, expected_word in enumerate(expected, 1):
            updated.append(
                min(
                    updated[-1] + 1,
                    costs[col] + 1,
                    costs[col - 1] + (token != expected_word),
                )
            )
        costs = updated
    return costs[-1] / len(expected)


def score(case: Case, result: dict) -> tuple[str, dict]:
    answer = result["message"]["content"]
    tokens = words(answer)
    extra = {}
    match case.id:
        case "T01" | "M01":
            passed = {"klucz", "pod", "krzesłem"} <= set(tokens)
        case "T02":
            passed = {"key", "under", "chair"} <= set(tokens)
        case "T03":
            passed = tokens == ["14", "12", "4"]
        case "T04":
            try:
                parsed = json.loads(answer)
            except json.JSONDecodeError:
                parsed = None
            passed = (
                parsed == {"count": 3, "ready": False}
                and type(parsed["count"]) is int
                and parsed["ready"] is False
            )
        case "T05":
            passed = valid_call(result) and words(
                result["followup"]["message"]["content"]
            ) == ["indigo"]
        case "T06":
            passed = (
                "valueerror" in tokens
                and "abc" in tokens
                and bool({"integer", "int", "literal"} & set(tokens))
            )
        case "T07":
            commands = [
                line.strip()
                for line in answer.strip().splitlines()
                if line.strip() and not line.startswith("\x60\x60\x60")
            ]
            passed = commands in (
                ["git diff --name-only HEAD", "pwd"],
                ["git diff HEAD --name-only", "pwd"],
            )
        case "T08":
            passed = tokens == ["cy"]
        case "T09":
            passed = tokens == ["mewa", "73"]
        case (
            "T10" | "T11" | "M02" | "M09" | "M11" | "M12" | "M15" | "M16" | "M16-noise"
        ):
            return "REVIEW", extra
        case "T12":
            passed = tokens == ["12", "14", "16"]
        case "M03" | "M10":
            passed = tokens == ["niebieski"] or tokens == ["niebieskie"]
        case "M04":
            passed = len(re.findall(r"\bVENOM 42\b", answer)) == 1
        case "M05" | "M06":
            extra["wer"] = word_error_rate(case.expected, answer)
            passed = extra["wer"] <= 0.1
        case _:
            raise ValueError(f"No rubric for {case.id}")
    return ("PASS" if passed else "FAIL"), extra


def resources() -> dict:
    sample = {}
    with Path("/proc/meminfo").open() as memory:
        for line in memory:
            key, value, *_ = line.split()
            if key in {"MemAvailable:", "MemTotal:"}:
                sample[key.rstrip(":") + "_mib"] = int(value) / 1024
    with Path("/proc/stat").open() as stats:
        sample["cpu_ticks"] = [int(value) for value in stats.readline().split()[1:9]]
    try:
        gpu = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=3,
        ).splitlines()[0]
        sample["gpu_used_mib"], sample["gpu_percent"] = (
            int(value) for value in gpu.split(",")
        )
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        pass
    return sample


class ResourceSampler:
    def __enter__(self):
        self.samples = [resources()]
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self.collect, daemon=True)
        self.worker.start()
        return self

    def collect(self) -> None:
        while not self.stop.wait(0.25):
            self.samples.append(resources())

    def __exit__(self, *_exc):
        self.stop.set()
        self.worker.join()
        self.samples.append(resources())

    def summary(self) -> dict:
        first, last = self.samples[0], self.samples[-1]
        elapsed = sum(last["cpu_ticks"]) - sum(first["cpu_ticks"])
        idle = sum(last["cpu_ticks"][3:5]) - sum(first["cpu_ticks"][3:5])
        gpu = [item for item in self.samples if "gpu_used_mib" in item]
        return {
            "samples": len(self.samples),
            "host_cpu_percent": 100 * (elapsed - idle) / elapsed if elapsed else None,
            "host_ram_start_mib": first["MemTotal_mib"] - first["MemAvailable_mib"],
            "host_ram_peak_mib": max(
                item["MemTotal_mib"] - item["MemAvailable_mib"] for item in self.samples
            ),
            "gpu_start_mib": first.get("gpu_used_mib"),
            "gpu_peak_mib": max((item["gpu_used_mib"] for item in gpu), default=None),
            "gpu_peak_percent": max(
                (item["gpu_percent"] for item in gpu), default=None
            ),
        }


def run_case(client: httpx.Client, model: str, case: Case, fixtures: Path) -> dict:
    row = {
        "case": case.id,
        "prompt": case.prompt,
        "system": case.system,
        "media": case.media,
        "expected": case.expected,
    }
    try:
        result = run_chat(client, model, case, fixtures)
        row.update(result)
        row["status"], metrics = score(case, result)
        row.update(metrics)
        if case.id in {"M05", "M06"}:
            with wave.open(str(fixtures / case.media[0])) as wav:
                row["input_audio_s"] = wav.getnframes() / wav.getframerate()
            row["rtf"] = row["total_s"] / row["input_audio_s"]
    except (RuntimeError, httpx.HTTPError, ValueError) as exc:
        row.update(status="BLOCKED", error=error_text(exc))
    return row


def error_text(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}: {exc.response.text[:1000]}"
    return str(exc)


def wav_details(output: Path) -> dict:
    with wave.open(str(output)) as wav:
        return {
            "rate_hz": wav.getframerate(),
            "channels": wav.getnchannels(),
            "bits": 8 * wav.getsampwidth(),
            "audio_s": wav.getnframes() / wav.getframerate(),
        }


def finalize_speech_wav(output: Path) -> dict:
    """Rewrite Ollama's open-ended streaming WAV with the received PCM length."""
    with wave.open(str(output)) as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        declared = wav.getnframes()
        pcm = wav.readframes(output.stat().st_size // (channels * width))
    if len(pcm) % (channels * width):
        raise ValueError("Ollama returned a partial PCM frame")
    with wave.open(str(output), "wb") as wav:
        wav.setparams((channels, width, rate, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    return {"stream_header_frames": declared, **wav_details(output)}


def speech(client: httpx.Client, text: str, voice: str, output: Path) -> dict:
    start = time.perf_counter()
    first_s = None
    with client.stream(
        "POST",
        "/v1/audio/speech",
        json={
            "model": OMNI,
            "input": text,
            "voice": voice,
            "response_format": "wav",
        },
    ) as response:
        if response.is_error:
            response.read()
        response.raise_for_status()
        with output.open("wb") as handle:
            for data in response.iter_bytes():
                if first_s is None:
                    first_s = time.perf_counter() - start
                handle.write(data)
    details = finalize_speech_wav(output)
    return {
        "status": "REVIEW" if details["audio_s"] > 0 else "FAIL",
        "first_bytes_s": first_s,
        "total_s": time.perf_counter() - start,
        "wav": str(output),
        **details,
    }


def write_row(path: Path, **row) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        f"{row.get('model', '')} {row.get('case', '')} {row.get('trial', '')} {row.get('status', '')}",
        flush=True,
    )


def qualify(client: httpx.Client, args: argparse.Namespace) -> None:
    target = args.output / "results.jsonl"
    tag_data = client.get("/api/tags")
    tag_data.raise_for_status()
    tags = {item["name"]: item for item in tag_data.json()["models"]}
    for model in args.models:
        if model not in tags:
            write_row(
                target,
                model=model,
                case="SETUP",
                status="BLOCKED",
                error="Model is absent from /api/tags",
            )
            continue
        write_row(
            target,
            model=model,
            case="METADATA",
            status="INFO",
            tag=tags[model],
            show=json_post(client, "/api/show", model=model),
            runtime=client.get("/api/version").json(),
            context=CTX,
        )
        # Keep unload scoped to the explicitly selected isolated test server.
        json_post(client, "/api/generate", model=model, keep_alive=0)
        with ResourceSampler() as cold:
            warm = chat(client, model, [WARM])
        write_row(
            target,
            model=model,
            case="COLD",
            status="INFO",
            **warm,
            resources=cold.summary(),
            ps=client.get("/api/ps").json(),
        )
        cases = TEXT
        if model == OMNI and args.fixtures:
            cases += MEDIA
        for case in cases:
            for trial in range(1, args.repeats + 1):
                with ResourceSampler() as sample:
                    row = run_case(client, model, case, args.fixtures)
                write_row(
                    target, model=model, trial=trial, resources=sample.summary(), **row
                )
        for trial in range(1, args.repeats + 1):
            with ResourceSampler() as sample, ThreadPoolExecutor(max_workers=2) as pool:
                parallel_start = time.perf_counter()
                runs = list(
                    pool.map(
                        lambda case: run_case(client, model, case, args.fixtures),
                        [TEXT[-1], TEXT[-1]],
                    )
                )
            write_row(
                target,
                model=model,
                case="PARALLEL",
                trial=trial,
                status="PASS"
                if all(row["status"] == "PASS" for row in runs)
                else "FAIL",
                runs=runs,
                wall_s=time.perf_counter() - parallel_start,
                resources=sample.summary(),
            )
        if model == OMNI and args.fixtures:
            for trial, prompt in enumerate(TTS_TEXTS, 1):
                for voice in ("female-polish", "male-polish"):
                    try:
                        with ResourceSampler() as sample:
                            row = speech(
                                client,
                                prompt,
                                voice,
                                args.output / f"{voice}-{trial}.wav",
                            )
                    except (
                        httpx.HTTPError,
                        OSError,
                        EOFError,
                        ValueError,
                        wave.Error,
                    ) as exc:
                        row = {"status": "BLOCKED", "error": error_text(exc)}
                    write_row(
                        target,
                        model=model,
                        case="M07/M08",
                        trial=trial,
                        prompt=prompt,
                        expected=prompt,
                        voice=voice,
                        resources=sample.summary(),
                        **row,
                    )
        json_post(client, "/api/generate", model=model, keep_alive=0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11435")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--piper-model", type=Path)
    parser.add_argument("--models", nargs="+", choices=MODELS, default=MODELS)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    endpoint = urlsplit(args.endpoint)
    if (
        endpoint.scheme != "http"
        or endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}
        or not endpoint.port
        or endpoint.port == 11434
        or endpoint.path not in {"", "/"}
    ):
        parser.error(
            "Supply an isolated local HTTP endpoint on a port other than 11434."
        )
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if args.piper_model:
        if not args.fixtures:
            parser.error("--piper-model requires --fixtures")
        make_fixtures(args.fixtures, args.piper_model)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.jsonl").touch(exist_ok=False)
    with httpx.Client(base_url=args.endpoint, timeout=90, trust_env=False) as client:
        qualify(client, args)


if __name__ == "__main__":
    main()
