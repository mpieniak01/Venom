"""Prepare and measure the offline Polish benchmark, independently of CI."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import statistics
import time
import wave
from dataclasses import asdict
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import httpx
import numpy as np

from scripts.ollama_bench.lfm3_cases import _resample
from scripts.ollama_bench.omni_pilot import digest, write_json
from scripts.ollama_bench.polish_cases import TOOL_LABELS, VERSION, build_cases
from scripts.ollama_bench.run_lfm3 import (
    CTX,
    OMNI,
    WARM,
    ResourceSampler,
    chat,
    encode,
    error_text,
    json_post,
    wav_details,
    word_error_rate,
    words,
)

ENDPOINT = "http://127.0.0.1:11434"
GEMMA = "gemma4:e4b"
SPLITS = ("validation", "final")
OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": CTX, "num_predict": 128}
SPEECH_SAMPLES = (
    "Pani Łucja przyjedzie do Żyrardowa o siedemnastej.",
    "Zapisz dwadzieścia siedem pomiarów i odłóż próbkę na półkę.",
    "Sprawdź wejście C oraz dokument oznaczony kodem W-29.",
)
TOOL_PROTOCOL = (
    "Skorzystaj z właściwej funkcji odczytu. Jeśli brakuje identyfikatora, "
    "poproś słowami «podaj identyfikator». Po błędzie funkcji odpowiedz "
    "«odczyt niedostępny». Po sukcesie zwróć wyłącznie wartość pola value."
)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Odczytaj {label} dla wskazanego rekordu.",
            "parameters": {
                "type": "object",
                "properties": {"record_id": {"type": "string"}},
                "required": ["record_id"],
                "additionalProperties": False,
            },
        },
    }
    for name, label in TOOL_LABELS.items()
]


def render_image(case, path: Path, font: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (960, 480), "#142338")
    draw = ImageDraw.Draw(image)
    title = ImageFont.truetype(str(font), 38)
    label = ImageFont.truetype(str(font), 27)
    draw.text((35, 32), case.scene_title, font=title, fill="white")
    for index, (name, value) in enumerate(case.scene):
        x, y = (40 + 300 * index, 145) if case.horizontal else (60, 110 + 113 * index)
        width = 270 if case.horizontal else 720
        draw.rectangle(
            (x, y, x + width, y + 95), fill=("#225342", "#624a23", "#314c7a")[index]
        )
        draw.text((x + 14, y + 10), name, font=label, fill="white")
        draw.text((x + 16, y + 45), value, font=title, fill="white")
    image.save(path)


def render_audio(case, path: Path, voice) -> None:
    from piper.config import SynthesisConfig

    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav:
            voice.synthesize_wav(
                case.prompt, wav, SynthesisConfig(noise_scale=0, noise_w_scale=0)
            )
        _resample(buffer.getvalue(), path)
    if not case.noise:
        return
    with wave.open(str(path), "rb") as wav:
        signal = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(
            float
        )
    generator = np.random.default_rng(int(digest(path)[:8], 16))
    rms = np.sqrt(np.mean(signal**2))
    mixed = signal + generator.normal(0, rms * 10 ** (-18 / 20), signal.shape)
    write_pcm(path, np.clip(mixed, -32768, 32767).astype("<i2"), 16000)


def write_pcm(path: Path, audio: np.ndarray, rate: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        wav.writeframes(audio.astype("<i2", copy=False).tobytes())


def prepare(output: Path, voices: dict[str, Path], font: Path) -> None:
    from piper import PiperVoice

    output.mkdir(parents=True)
    for split in SPLITS:
        folder = output / split
        folder.mkdir()
        model = voices[split]
        voice = PiperVoice.load(model, use_cuda=True)
        rows = []
        for case in build_cases(split):
            media = {}
            if case.voice:
                path = folder / f"{case.id}.wav"
                render_audio(case, path, voice)
                media[path.name] = digest(path)
            if case.scene:
                path = folder / f"{case.id}.png"
                render_image(case, path, font)
                media[path.name] = digest(path)
            rows.append({**asdict(case), "media_sha256": media})
        write_json(
            folder / "manifest.json",
            {
                "version": VERSION,
                "split": split,
                "cases": rows,
                "input_voice": {
                    "file": model.name,
                    "sha256": digest(model),
                    "config_sha256": digest(Path(str(model) + ".json")),
                },
                "font_sha256": digest(font),
                "noise_snr_db": 18,
                "recording_origin": "synthetic",
                "promotion": {
                    "minimum_target_improvement_pp": 5,
                    "maximum_control_drop_pp": 2,
                    "checkpoint_selection_split": "validation",
                },
            },
        )
        print(split, len(rows), digest(folder / "manifest.json"), flush=True)
    write_json(
        output / "freeze.json",
        {split: digest(output / split / "manifest.json") for split in SPLITS},
    )


def verify(folder: Path) -> dict:
    manifest_file = folder / "manifest.json"
    freeze = json.loads((folder.parent / "freeze.json").read_text())
    manifest = json.loads(manifest_file.read_text())
    if freeze[manifest["split"]] != digest(manifest_file):
        raise ValueError("Manifest differs from the frozen benchmark")
    for case in manifest["cases"]:
        for name, expected in case["media_sha256"].items():
            if Path(name).name != name or digest(folder / name) != expected:
                raise ValueError(f"Invalid fixture: {name}")
    return manifest


def exact(text: str, expected: list[str]) -> bool:
    return any(words(text) == words(candidate) for candidate in expected)


def preserves(text: str, critical: list[list[str]]) -> bool:
    normalized = f" {' '.join(words(text))} "
    return all(
        any(f" {' '.join(words(value))} " in normalized for value in alternatives)
        for alternatives in critical
    )


def text_result(
    client, model: str, case: dict, question: str, image: str | None
) -> dict:
    user = {"role": "user", "content": question}
    if image is not None:
        user["images"] = [image]
    messages = [{"role": role, "content": text} for role, text in case["history"]]
    if case["document"]:
        messages.insert(0, {"role": "system", "content": case["document"]})
    is_tool = case["group"] == "tools"
    if is_tool:
        messages.insert(0, {"role": "system", "content": TOOL_PROTOCOL})
    messages.append(user)
    options = {"options": OPTIONS, "think": False}
    if is_tool:
        options["tools"] = TOOLS
    first = chat(client, model, messages, **options)
    text = first["message"]["content"]
    if not is_tool:
        return {"answer": text, "pass": exact(text, case["expected"]), "chat": first}
    calls = first["message"]["tool_calls"]
    if case["clarify_tool"]:
        return {
            "answer": text,
            "pass": not calls and exact(text, case["expected"]),
            "tool_call_ok": not calls,
            "chat": first,
        }
    name, record = case["tool"]
    expected = {"name": name, "arguments": {"record_id": record}}
    selected = calls[0].get("function", {}) if len(calls) == 1 else {}
    call_ok = {key: selected.get(key) for key in expected} == expected
    if not call_ok:
        return {"answer": text, "pass": False, "tool_call_ok": False, "chat": first}
    # Return a frozen fixture only after matching a single allowlisted read.
    result = (
        {"ok": False, "error": "odczyt niedostępny"}
        if case["tool_error"]
        else {
            "ok": True,
            "value": case["expected"][0],
        }
    )
    messages.extend(
        (
            first["message"],
            {
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(result, ensure_ascii=False),
            },
        )
    )
    followup = chat(client, model, messages, **options)
    text = followup["message"]["content"]
    return {
        "answer": text,
        "pass": exact(text, case["expected"]) and not followup["message"]["tool_calls"],
        "tool_call_ok": True,
        "chat": first,
        "tool_result": result,
        "followup": followup,
    }


class SpeechProfile:
    def __init__(self, model: str, piper: Path):
        from venom_core.services import ollama_audio

        self.model = model
        self.native = ollama_audio
        self.engine = None
        if model == GEMMA:
            from venom_core.perception.audio_engine import AudioEngine

            self.engine = AudioEngine("medium", str(piper), "cuda", True)

    async def transcribe(self, path: Path) -> str:
        with wave.open(str(path), "rb") as wav:
            pcm, rate = wav.readframes(wav.getnframes()), wav.getframerate()
        if self.engine is not None:
            return await self.engine.transcribe_checked(
                np.frombuffer(pcm, dtype="<i2"), "pl", rate
            )
        return await self.native.transcribe_pcm_audio(
            ENDPOINT, self.model, pcm, rate, "pl"
        )

    async def speak(self, answer: str, path: Path) -> dict:
        start = time.perf_counter()
        if self.engine is not None:
            audio = await self.engine.speak(answer)
            if audio is None or not np.any(audio):
                raise RuntimeError("Piper CUDA produced no signal")
            write_pcm(path, audio, self.engine.voice.output_sample_rate)
        else:
            path.write_bytes(
                await self.native.synthesize_speech(
                    ENDPOINT, self.model, answer, voice=self.native.OMNI_VOICES["pl"]
                )
            )
        return {
            "file": path.name,
            "speech_s": time.perf_counter() - start,
            **wav_details(path),
        }


async def measure(client, model, speech_profile, folder, output, case, mode):
    image = encode(folder / f"{case['id']}.png") if case["scene"] else None
    question = case["prompt"]
    row = {
        "id": case["id"],
        "group": case["group"],
        "mode": mode,
        "noise": case["noise"],
    }
    start = time.perf_counter()
    if mode == "recording":
        question = await speech_profile.transcribe(folder / f"{case['id']}.wav")
        row.update(
            transcript=question,
            asr_s=time.perf_counter() - start,
            wer=word_error_rate(case["prompt"], question),
            critical_ok=preserves(question, case["critical"]),
        )
    row.update(
        text_result(client, model, case, question, image)
        if question.strip()
        else {
            "answer": "",
            "pass": False,
        }
    )
    row["answer_s"] = time.perf_counter() - start
    if mode == "recording" and case["id"].endswith("-1") and row["answer"].strip():
        try:
            row["speech"] = await speech_profile.speak(
                row["answer"], output / f"{case['id']}.wav"
            )
            row["playable_s"] = time.perf_counter() - start
        except (RuntimeError, ValueError, OSError, httpx.HTTPError) as exc:
            row["speech_error"] = error_text(exc)
    return row


def summary(rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(f"{row['group']}/{row['mode']}", []).append(row)
    result = {}
    for name, items in groups.items():
        durations = sorted(row["answer_s"] for row in items if "answer_s" in row)
        recorded = [row for row in items if "wer" in row]
        spoken = sorted(row["playable_s"] for row in items if "playable_s" in row)
        stats = {
            "count": len(items),
            "passed": sum(row.get("pass", False) for row in items),
            "errors": sum("error" in row for row in items),
            "median_answer_s": statistics.median(durations) if durations else None,
            "p95_answer_s": durations[math.ceil(0.95 * len(durations)) - 1]
            if durations
            else None,
        }
        if recorded:
            stats.update(
                asr_count=len(recorded),
                mean_wer=statistics.mean(row["wer"] for row in recorded),
                critical_passed=sum(row["critical_ok"] for row in recorded),
            )
        if spoken:
            stats.update(
                playable_count=len(spoken),
                median_playable_s=statistics.median(spoken),
                p95_playable_s=spoken[math.ceil(0.95 * len(spoken)) - 1],
            )
        if any("tool_call_ok" in row for row in items):
            stats["tool_call_passed"] = sum(
                row.get("tool_call_ok", False) for row in items
            )
        result[name] = stats
    paired = {
        "reference_pass_recording_fail": [],
        "both_fail": [],
        "recording_pass_reference_fail": [],
    }
    references = {row["id"]: row for row in rows if row["mode"] == "reference"}
    for row in (item for item in rows if item["mode"] == "recording"):
        flags = (references[row["id"]].get("pass", False), row.get("pass", False))
        outcome = {
            (True, False): "reference_pass_recording_fail",
            (False, False): "both_fail",
            (False, True): "recording_pass_reference_fail",
        }.get(flags)
        if outcome:
            paired[outcome].append(row["id"])
    return {"groups": result, "paired_voice": paired}


async def run(folder: Path, output: Path, model: str, piper: Path) -> None:
    manifest = verify(folder)
    output.mkdir(parents=True)
    samples = output / "audio"
    samples.mkdir()
    speech_profile = SpeechProfile(model, piper) if model in {OMNI, GEMMA} else None
    rows = []
    with httpx.Client(base_url=ENDPOINT, timeout=120, trust_env=False) as client:
        tags = client.get("/api/tags").raise_for_status().json()["models"]
        identity = next(entry for entry in tags if entry["name"] == model)
        show = json_post(client, "/api/show", model=model)
        write_json(
            output / "identity.json",
            {
                "model": identity,
                "runtime": client.get("/api/version").raise_for_status().json(),
                "manifest_sha256": digest(folder / "manifest.json"),
                "options": OPTIONS,
                "think": False,
                "template_sha256": sha256(
                    show.get("template", "").encode()
                ).hexdigest(),
                "model_parameters": show.get("parameters"),
                "capabilities": show.get("capabilities"),
                "speech": "Omni ASR/TTS"
                if model == OMNI
                else "Whisper medium/Piper CUDA"
                if model == GEMMA
                else None,
                "audio_versions": {
                    name: version(name) for name in ("piper-tts", "faster-whisper")
                },
                "piper_sha256": digest(piper) if model == GEMMA else None,
            },
        )
        with ResourceSampler() as sampler:
            warm = chat(client, model, [WARM], options=OPTIONS)
            write_json(output / "warmup.json", warm)
            for case in manifest["cases"]:
                if speech_profile is None and case["group"] not in {
                    "conversation",
                    "information",
                }:
                    continue
                modes = ("reference", "recording") if case["voice"] else ("reference",)
                for mode in modes:
                    try:
                        row = await measure(
                            client, model, speech_profile, folder, samples, case, mode
                        )
                    except (RuntimeError, ValueError, OSError, httpx.HTTPError) as exc:
                        row = {
                            "id": case["id"],
                            "group": case["group"],
                            "mode": mode,
                            "pass": False,
                            "error": error_text(exc),
                        }
                    rows.append(row)
                    with (output / "rows.jsonl").open("a", encoding="utf-8") as log:
                        log.write(json.dumps(row, ensure_ascii=False) + "\n")
                    print(
                        case["id"], mode, "PASS" if row["pass"] else "FAIL", flush=True
                    )
            listening = []
            if speech_profile is not None:
                for index, phrase in enumerate(SPEECH_SAMPLES, 1):
                    try:
                        result = await speech_profile.speak(
                            phrase, samples / f"fixed-{index}.wav"
                        )
                    except (RuntimeError, ValueError, OSError, httpx.HTTPError) as exc:
                        result = {"error": error_text(exc)}
                    listening.append({"text": phrase, **result})
            write_json(output / "listening.json", listening)
            write_json(
                output / "loaded.json", client.get("/api/ps").raise_for_status().json()
            )
        write_json(
            output / "summary.json", {**summary(rows), "resources": sampler.summary()}
        )
        # Release only the measured runner before starting the next profile.
        json_post(
            client, "/api/generate", model=model, prompt="", stream=False, keep_alive=0
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--final-voice", type=Path, required=True)
    prep.add_argument("--validation-voice", type=Path, required=True)
    prep.add_argument("--font", type=Path, required=True)
    measure_run = commands.add_parser("run")
    measure_run.add_argument("--fixtures", type=Path, required=True)
    measure_run.add_argument("--output", type=Path, required=True)
    measure_run.add_argument("--model", required=True)
    measure_run.add_argument("--piper", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        if digest(args.final_voice) == digest(args.validation_voice):
            raise ValueError("Validation and final must use distinct input voices")
        prepare(
            args.output,
            {"final": args.final_voice, "validation": args.validation_voice},
            args.font,
        )
    else:
        asyncio.run(run(args.fixtures, args.output, args.model, args.piper))


if __name__ == "__main__":
    main()
