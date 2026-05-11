#!/usr/bin/env python3
"""Experimental direct-audio probe for Gemma 4 via Hugging Face Transformers."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import transformers  # noqa: E402

DEFAULT_MODEL_ID = "google/gemma-4-E2B-it"
TARGET_SAMPLE_RATE = 16_000
CACHE_DIR = ROOT_DIR / "models_cache" / "hf"


@dataclass(slots=True)
class NormalizedAudio:
    source_path: Path
    normalized_path: Path
    sample_rate: int
    channels: int
    duration_sec: float
    sample_count: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Experimental Gemma 4 direct audio ingest probe"
    )
    parser.add_argument(
        "--audio",
        type=Path,
        help="Local audio file to send to Gemma 4. Defaults to the newest voice session recording.",
    )
    parser.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help="Gemma checkpoint to load from Hugging Face.",
    )
    parser.add_argument(
        "--prompt",
        default=(
            "Transcribe the speech in the audio. "
            "Return only the transcription, with no bullets and no extra commentary."
        ),
        help="Instruction sent together with the audio.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=128,
        help="Generation budget for the model.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON report instead of the human-readable summary.",
    )
    parser.add_argument(
        "--normalized-output",
        type=Path,
        help="Optional path where the normalized WAV should be preserved.",
    )
    return parser.parse_args()


def _find_latest_audio() -> Path | None:
    candidates = sorted(
        (
            p
            for p in (ROOT_DIR / "data" / "audio" / "voice_sessions").glob(
                "**/recording.wav"
            )
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _read_audio_fallback(path: Path) -> tuple[np.ndarray, int]:
    try:
        audio, sample_rate = sf.read(str(path), always_2d=True, dtype="float32")
        return audio, int(sample_rate)
    except Exception:
        with tempfile.TemporaryDirectory(prefix="gemma4_audio_ffmpeg_") as tmpdir:
            tmp_path = Path(tmpdir) / "decoded.wav"
            cmd = [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(path),
                "-ac",
                "1",
                "-ar",
                str(TARGET_SAMPLE_RATE),
                "-c:a",
                "pcm_f32le",
                str(tmp_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            audio, sample_rate = sf.read(str(tmp_path), always_2d=True, dtype="float32")
            return audio, int(sample_rate)


def _normalize_audio(source_path: Path, workdir: Path) -> NormalizedAudio:
    audio, sample_rate = _read_audio_fallback(source_path)
    channels = int(audio.shape[1]) if audio.ndim > 1 else 1
    mono = audio.mean(axis=1) if audio.ndim > 1 else audio
    mono = np.asarray(mono, dtype=np.float32)
    if sample_rate != TARGET_SAMPLE_RATE:
        gcd = math.gcd(sample_rate, TARGET_SAMPLE_RATE)
        up = TARGET_SAMPLE_RATE // gcd
        down = sample_rate // gcd
        mono = resample_poly(mono, up, down).astype(np.float32, copy=False)
        sample_rate = TARGET_SAMPLE_RATE
    mono = np.clip(mono, -1.0, 1.0).astype(np.float32, copy=False)

    normalized_path = workdir / f"{source_path.stem}.gemma4_16k_mono.wav"
    sf.write(str(normalized_path), mono, sample_rate, subtype="FLOAT")
    duration_sec = float(len(mono)) / float(sample_rate) if sample_rate else 0.0
    return NormalizedAudio(
        source_path=source_path,
        normalized_path=normalized_path,
        sample_rate=sample_rate,
        channels=channels,
        duration_sec=duration_sec,
        sample_count=int(len(mono)),
    )


def _resolve_model_class() -> type[Any]:
    model_cls = getattr(transformers, "AutoModelForMultimodalLM", None)
    if model_cls is not None:
        return model_cls
    model_cls = getattr(transformers, "AutoModelForImageTextToText", None)
    if model_cls is not None:
        return model_cls
    raise RuntimeError(
        "No compatible multimodal model class found in installed transformers."
    )


def _load_model(model_id: str) -> tuple[Any, Any, str]:
    processor = transformers.AutoProcessor.from_pretrained(
        model_id,
        cache_dir=str(CACHE_DIR),
        local_files_only=True,
    )
    model_class = _resolve_model_class()
    model = model_class.from_pretrained(
        model_id,
        dtype="auto",
        device_map="auto",
        cache_dir=str(CACHE_DIR),
        local_files_only=True,
    )
    return model, processor, model_class.__name__


def _build_messages(audio_path: Path, prompt: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "audio", "path": str(audio_path)},
                {"type": "text", "text": prompt},
            ],
        }
    ]


def _run_inference(
    *,
    model: Any,
    processor: Any,
    messages: list[dict[str, Any]],
    max_new_tokens: int,
) -> str:
    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )
    if hasattr(inputs, "to"):
        inputs = inputs.to(model.device)
    outputs = model.generate(**inputs, max_new_tokens=max_new_tokens)
    decoded = processor.batch_decode(
        outputs,
        skip_special_tokens=False,
        clean_up_tokenization_spaces=False,
    )
    return decoded[0] if decoded else ""


def main() -> int:
    args = _parse_args()
    source_path = (
        args.audio.expanduser().resolve() if args.audio else _find_latest_audio()
    )
    if source_path is None:
        print(
            "No audio file found. Pass --audio or add a recording under data/audio/voice_sessions.",
            file=sys.stderr,
        )
        return 2
    if not source_path.exists():
        print(f"Audio file not found: {source_path}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="gemma4_audio_probe_") as tmpdir_name:
        tmpdir = Path(tmpdir_name)
        try:
            normalized = _normalize_audio(source_path, tmpdir)
            if args.normalized_output:
                output_path = args.normalized_output.expanduser().resolve()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(normalized.normalized_path.read_bytes())
                normalized = NormalizedAudio(
                    source_path=normalized.source_path,
                    normalized_path=output_path,
                    sample_rate=normalized.sample_rate,
                    channels=normalized.channels,
                    duration_sec=normalized.duration_sec,
                    sample_count=normalized.sample_count,
                )
            model, processor, model_class_name = _load_model(args.model_id)
            messages = _build_messages(normalized.normalized_path, args.prompt)
            generated_text = _run_inference(
                model=model,
                processor=processor,
                messages=messages,
                max_new_tokens=args.max_new_tokens,
            )
            report = {
                "ok": True,
                "model_id": args.model_id,
                "model_class": model_class_name,
                "source_audio": str(normalized.source_path),
                "normalized_audio": str(normalized.normalized_path),
                "sample_rate": normalized.sample_rate,
                "channels": normalized.channels,
                "duration_sec": round(normalized.duration_sec, 3),
                "sample_count": normalized.sample_count,
                "generated_text": generated_text,
            }
        except Exception as exc:
            report = {
                "ok": False,
                "model_id": args.model_id,
                "source_audio": str(normalized.source_path),
                "normalized_audio": str(normalized.normalized_path),
                "sample_rate": normalized.sample_rate,
                "channels": normalized.channels,
                "duration_sec": round(normalized.duration_sec, 3),
                "sample_count": normalized.sample_count,
                "error": f"{type(exc).__name__}: {exc}",
            }

        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print("Gemma 4 direct audio ingest probe")
            print(f"  model_id: {report['model_id']}")
            print(f"  source_audio: {report['source_audio']}")
            print(f"  normalized_audio: {report['normalized_audio']}")
            print(
                "  audio_stats: "
                f"sr={report['sample_rate']}Hz, channels={report['channels']}, "
                f"duration={report['duration_sec']}s, samples={report['sample_count']}"
            )
            if report.get("ok"):
                print(f"  model_class: {report['model_class']}")
                print("  generated_text:")
                print(report["generated_text"])
            else:
                print(f"  error: {report['error']}")

        return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
