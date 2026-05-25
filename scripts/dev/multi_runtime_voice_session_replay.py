#!/usr/bin/env python3
"""Replay a recorded voice session against the Multi-Runtime service.

The script reuses the latest saved voice session by default and sends its
`recording.wav` path to the local Multi-Runtime daemon.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from venom_core.api.audio_stream import (  # noqa: E402
    VOICE_SESSION_ROOT,
    collect_latest_voice_session_record,
)
from venom_core.config import SETTINGS  # noqa: E402


def _resolve_audio_path(session_dir: Path | None, audio_path: Path | None) -> Path:
    if audio_path is not None:
        return audio_path

    if session_dir is not None:
        candidate = session_dir / "recording.wav"
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"Missing recording.wav in {session_dir}")

    latest = collect_latest_voice_session_record(VOICE_SESSION_ROOT)
    if not latest:
        raise FileNotFoundError("No voice session found in data/audio/voice_sessions")

    candidate = VOICE_SESSION_ROOT / str(latest["session_id"]) / "recording.wav"
    if not candidate.exists():
        raise FileNotFoundError(f"Missing recording.wav in {candidate.parent}")
    return candidate


def _build_payload(
    audio_path: Path,
    *,
    task: str | None,
    question: str | None,
    system_prompt: str | None,
    max_new_tokens: int,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "audio", "path": str(audio_path)}]
    if question:
        content.append({"type": "text", "text": question})
    return {
        "messages": [{"role": "user", "content": content}],
        "task": task,
        "question": question,
        "system_prompt": system_prompt,
        "max_new_tokens": max_new_tokens,
    }


async def _run(args: argparse.Namespace) -> int:
    session_dir = Path(args.session_dir) if args.session_dir else None
    audio_path = Path(args.audio) if args.audio else None
    resolved_audio_path = _resolve_audio_path(session_dir, audio_path)

    base_url = args.base_url.rstrip("/")
    respond_url = (
        f"{base_url}/v1/respond"
        if not base_url.endswith("/v1")
        else f"{base_url}/respond"
    )
    payload = _build_payload(
        resolved_audio_path,
        task=args.task,
        question=args.question,
        system_prompt=args.system_prompt,
        max_new_tokens=args.max_new_tokens,
    )

    print(f"Session audio: {resolved_audio_path}")
    print(f"POST {respond_url}")

    timeout = httpx.Timeout(args.timeout, connect=min(5.0, args.timeout))
    with resolved_audio_path.open("rb") as audio_handle:
        files = {"audio": (resolved_audio_path.name, audio_handle, "audio/wav")}
        data = {"request": json.dumps(payload, ensure_ascii=False)}
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(respond_url, data=data, files=files)

    if response.status_code >= 400:
        print(f"HTTP {response.status_code}")
        print(response.text)
        return 1

    data = response.json()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=SETTINGS.GEMMA4_AUDIO_ENDPOINT)
    parser.add_argument("--session-dir", default="")
    parser.add_argument("--audio", default="")
    parser.add_argument("--task", default="question")
    parser.add_argument("--question", default="")
    parser.add_argument("--system-prompt", default="")
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.session_dir = args.session_dir or None
    args.audio = args.audio or None
    args.question = args.question or None
    args.system_prompt = args.system_prompt or None
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
