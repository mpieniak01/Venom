#!/usr/bin/env python3
"""Run repeated /v1/respond calls to audit single-pass voice trace determinism."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


@dataclass
class AuditRun:
    run_index: int
    request_id: str
    trace_id: str
    transcription: str
    transcription_used_for_generation: str
    response_text: str
    duration_ms: int | None
    model: str


PROMPT = (
    "Odpowiedz po polsku na wypowiedź użytkownika z nagrania. "
    "Jeśli to pytanie matematyczne, podaj wyłącznie wynik i krótkie uzasadnienie."
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="246B single-pass trace audit")
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8014",
        help="Base URL for multi_runtime service",
    )
    parser.add_argument(
        "--audio-path",
        required=True,
        help="Path to WAV audio sample",
    )
    parser.add_argument("--runs", type=int, default=3, help="Number of repeated calls")
    parser.add_argument(
        "--output-dir",
        default="test-results/246b",
        help="Directory for JSON/MD reports",
    )
    return parser.parse_args()


def _build_request(audio_name: str) -> dict[str, Any]:
    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "audio", "path": audio_name},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        "task": "question",
        "max_new_tokens": 128,
        "temperature": 0.0,
        "do_sample": False,
        "release_after_response": False,
    }


def _run_once(
    client: httpx.Client,
    respond_url: str,
    audio_path: Path,
    run_index: int,
) -> AuditRun:
    request_payload = _build_request(audio_path.name)
    with audio_path.open("rb") as handle:
        audio_bytes = handle.read()

    response = client.post(
        respond_url,
        data={"request": json.dumps(request_payload, ensure_ascii=False)},
        files={"audio": (audio_path.name, audio_bytes, "audio/wav")},
    )
    response.raise_for_status()

    payload = response.json()
    transcription = str(payload.get("transcription") or "").strip()
    transcription_used = str(
        payload.get("transcription_used_for_generation") or transcription
    ).strip()
    response_text = str(
        payload.get("text")
        or payload.get("response_text")
        or payload.get("generated_text")
        or ""
    ).strip()

    return AuditRun(
        run_index=run_index,
        request_id=str(payload.get("request_id") or "").strip(),
        trace_id=str(payload.get("trace_id") or "").strip(),
        transcription=transcription,
        transcription_used_for_generation=transcription_used,
        response_text=response_text,
        duration_ms=(
            int(payload.get("duration_ms"))
            if payload.get("duration_ms") is not None
            else None
        ),
        model=str(payload.get("model") or "").strip(),
    )


def _report(
    audit_runs: list[AuditRun], audio_hash: str, audio_path: Path
) -> dict[str, Any]:
    transcription_values = [run.transcription_used_for_generation for run in audit_runs]
    response_values = [run.response_text for run in audit_runs]

    unique_transcriptions = sorted({value for value in transcription_values if value})
    unique_responses = sorted({value for value in response_values if value})

    same_transcription = len(unique_transcriptions) == 1
    same_response = len(unique_responses) == 1
    trace_consistent = all(
        run.transcription.strip() == run.transcription_used_for_generation.strip()
        for run in audit_runs
    )
    request_ids_non_empty = all(run.request_id for run in audit_runs)
    request_ids_unique = len(
        {run.request_id for run in audit_runs if run.request_id}
    ) == len(audit_runs)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audio_sample": str(audio_path),
        "audio_hash": audio_hash,
        "runs": [
            {
                "run_index": run.run_index,
                "request_id": run.request_id,
                "trace_id": run.trace_id,
                "transcription": run.transcription,
                "transcription_used_for_generation": run.transcription_used_for_generation,
                "response_text": run.response_text,
                "duration_ms": run.duration_ms,
                "model": run.model,
            }
            for run in audit_runs
        ],
        "summary": {
            "same_transcription_across_runs": same_transcription,
            "same_response_across_runs": same_response,
            "trace_consistent_per_run": trace_consistent,
            "request_ids_non_empty": request_ids_non_empty,
            "request_ids_unique": request_ids_unique,
            "unique_transcriptions": unique_transcriptions,
            "unique_responses": unique_responses,
        },
    }


def _write_outputs(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"246b_single_pass_trace_audit_{stamp}.json"
    md_path = output_dir / f"246b_single_pass_trace_audit_{stamp}.md"

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    summary = payload["summary"]
    lines = [
        "# 246B Single-pass Trace Audit",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- audio_sample: `{payload['audio_sample']}`",
        f"- audio_hash: `{payload['audio_hash']}`",
        f"- same_transcription_across_runs: `{summary['same_transcription_across_runs']}`",
        f"- same_response_across_runs: `{summary['same_response_across_runs']}`",
        f"- trace_consistent_per_run: `{summary['trace_consistent_per_run']}`",
        f"- request_ids_non_empty: `{summary['request_ids_non_empty']}`",
        f"- request_ids_unique: `{summary['request_ids_unique']}`",
        "",
        "## Runs",
        "",
    ]
    for run in payload["runs"]:
        lines.extend(
            [
                f"### Run {run['run_index']}",
                f"- request_id: `{run['request_id']}`",
                f"- trace_id: `{run['trace_id']}`",
                f"- transcription: `{run['transcription']}`",
                (
                    "- transcription_used_for_generation: "
                    f"`{run['transcription_used_for_generation']}`"
                ),
                f"- response_text: `{run['response_text']}`",
                f"- duration_ms: `{run['duration_ms']}`",
                f"- model: `{run['model']}`",
                "",
            ]
        )

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    args = _args()
    audio_path = Path(args.audio_path).expanduser().resolve()
    if not audio_path.exists() or not audio_path.is_file():
        print(f"audio sample missing: {audio_path}", file=sys.stderr)
        return 2

    audio_bytes = audio_path.read_bytes()
    audio_hash = hashlib.sha256(audio_bytes).hexdigest()

    respond_url = f"{args.api_base.rstrip('/')}/v1/respond"
    runs: list[AuditRun] = []
    if args.runs < 1:
        print("--runs must be >= 1", file=sys.stderr)
        return 2

    timeout = httpx.Timeout(180.0, connect=10.0)
    with httpx.Client(timeout=timeout) as client:
        for index in range(1, args.runs + 1):
            runs.append(_run_once(client, respond_url, audio_path, run_index=index))

    payload = _report(runs, audio_hash=audio_hash, audio_path=audio_path)
    json_path, md_path = _write_outputs(payload, Path(args.output_dir))

    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"JSON: {json_path}")
    print(f"MD: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
