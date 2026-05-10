#!/usr/bin/env python3
"""Local audio smoke test for Venom voice loop."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from venom_core.config import SETTINGS  # noqa: E402
from venom_core.perception.audio_engine import AudioEngine  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Venom local audio smoke test")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the running Venom backend.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Optional audio file to transcribe locally through the backend audio engine.",
    )
    parser.add_argument(
        "--tts-model-path",
        type=Path,
        help="Optional Piper model path override for the local smoke transcription engine.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the collected status as pretty JSON.",
    )
    return parser.parse_args()


def _fetch_audio_status(base_url: str) -> dict[str, object]:
    response = httpx.get(f"{base_url.rstrip('/')}/api/v1/audio/status", timeout=30.0)
    response.raise_for_status()
    return response.json()


def _print_human_summary(status: dict[str, object]) -> None:
    print("Audio status")
    print(f"  enabled: {status.get('enabled')}")
    print(f"  stt_backend: {status.get('stt_backend')} ready={status.get('stt_ready')}")
    print(f"  tts_backend: {status.get('tts_backend')} ready={status.get('tts_ready')}")
    deps = status.get("dependencies") or {}
    if isinstance(deps, dict):
        print(
            "  dependencies: "
            + ", ".join(f"{name}={value}" for name, value in sorted(deps.items()))
        )

    latest = status.get("latest_voice_session") or {}
    if isinstance(latest, dict) and latest:
        print(f"  latest_session: {latest.get('session_id')}")
        print(f"  transcription: {latest.get('transcription')}")
        print(f"  response_text: {latest.get('response_text')}")
        timings = latest.get("timings_ms") or {}
        if isinstance(timings, dict) and timings:
            print(
                "  timings_ms: "
                + ", ".join(
                    f"{name}={value}" for name, value in sorted(timings.items())
                )
            )


def _run_local_transcribe(
    file_path: Path, tts_model_path: Path | None = None
) -> dict[str, object]:
    engine = AudioEngine(
        whisper_model_size=SETTINGS.WHISPER_MODEL_SIZE,
        tts_model_path=str(tts_model_path or SETTINGS.TTS_MODEL_PATH or "") or None,
        device=SETTINGS.AUDIO_DEVICE,
    )
    # Warm up models before the actual transcription so the smoke test reflects
    # the real interactive path.
    try:
        import asyncio

        asyncio.run(engine.warmup())
    except Exception:
        pass
    text = engine.transcribe_file(str(file_path), language="pl")
    return {
        "text": text,
        "whisper_model_size": engine.whisper.model_size,
        "tts_model_path": engine.voice.model_path,
        "tts_fallback": engine.voice.is_fallback_mode,
    }


def main() -> int:
    args = _parse_args()
    status = _fetch_audio_status(args.base_url)

    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        _print_human_summary(status)

    if args.file:
        file_path = args.file.expanduser().resolve()
        if not file_path.exists():
            print(f"File not found: {file_path}", file=sys.stderr)
            return 2
        payload = _run_local_transcribe(file_path, args.tts_model_path)
        print("Transcription smoke")
        print(f"  file: {file_path}")
        print(f"  text: {payload.get('text')}")
        print(f"  whisper_model_size: {payload.get('whisper_model_size')}")
        print(f"  tts_fallback: {payload.get('tts_fallback')}")
        if args.tts_model_path:
            print(f"  tts_model_path: {args.tts_model_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
