#!/usr/bin/env python3
"""Manual Direct-chat acceptance against an already selected Vast target.

Without --live this performs only read-only preflight. It never changes targets,
creates resources, installs models or claims browser/Normal-mode acceptance.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

PROMPTS = (
    "Remember this marker: {marker}\nReply briefly confirming you will remember it.",
    "Reply with only the exact marker from the first message, without punctuation.",
    "Reply with one short sentence confirming this test conversation is complete.",
)


class SmokeError(RuntimeError):
    pass


def api_base(value: str) -> str:
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and parsed.port != 0
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("loopback_api_required")
    return value.rstrip("/")


def _json_get(client: httpx.Client, path: str) -> dict[str, Any]:
    response = client.get(path)
    if response.status_code != 200:
        raise SmokeError("preflight_http_failed")
    payload = response.json()
    if not isinstance(payload, dict):
        raise SmokeError("preflight_payload_invalid")
    return payload


def preflight(client: httpx.Client) -> dict[str, str]:
    connection = _json_get(client, "/api/v1/system/vast-chat")
    active = _json_get(client, "/api/v1/system/llm-servers/active")
    runtime = active.get("runtime_id")
    config = active.get("config_hash")
    model = active.get("active_model")
    target = connection.get("target_id")
    if (
        connection.get("available") is not True
        or active.get("active_server") != "vast_ollama"
        or not isinstance(runtime, str)
        or not runtime.startswith("ollama@vast:")
        or not isinstance(target, str)
        or not runtime.startswith(target + ":")
        or not isinstance(config, str)
        or not config
        or not isinstance(model, str)
        or not model
    ):
        raise SmokeError("selected_vast_target_required")
    rows = connection.get("models", [])
    match = (
        next(
            (row for row in rows if isinstance(row, dict) and row.get("name") == model),
            None,
        )
        if isinstance(rows, list)
        else None
    )
    if match is None or not isinstance(match.get("digest"), str) or not match["digest"]:
        raise SmokeError("selected_vast_model_unavailable")
    return {
        "runtime_id": runtime,
        "config_hash": config,
        "model": model,
        "digest": match["digest"],
        "target_id": target,
    }


def _events(response: httpx.Response, deadline: float, clock):
    event = ""
    data: list[str] = []
    size = 0
    for line in response.iter_lines():
        if clock() >= deadline:
            raise SmokeError("stream_deadline_exceeded")
        size += len(line)
        if size > 1_000_000:
            raise SmokeError("stream_limit_exceeded")
        if line == "":
            if data:
                yield event, "\n".join(data)
            event, data = "", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        # Only explicitly delimited events prove a completed stream.
        raise SmokeError("stream_incomplete")


def stream_turn(
    client: httpx.Client,
    identity: dict[str, str],
    session_id: str,
    prompt: str,
    *,
    clock=time.monotonic,
    timeout_seconds: int = 120,
    history: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], str]:
    started = clock()
    first = None
    characters = 0
    chunks: list[str] = []
    done = False
    body = {
        "content": prompt,
        "model": identity["model"],
        "session_id": session_id,
        "max_tokens": 128,
        "temperature": 0,
        "stream": True,
        "expected_runtime_id": identity["runtime_id"],
        "expected_config_hash": identity["config_hash"],
    }
    if history is not None:
        if len(history) > 20 or sum(len(item["content"]) for item in history) > 50000:
            raise SmokeError("conversation_history_limit")
        body["history"] = history
    with client.stream("POST", "/api/v1/llm/simple/stream", json=body) as response:
        if response.status_code != 200:
            raise SmokeError("generation_http_failed")
        if not response.headers.get("content-type", "").startswith("text/event-stream"):
            raise SmokeError("generation_sse_required")
        for event, data in _events(response, started + timeout_seconds, clock):
            try:
                payload = json.loads(data)
            except ValueError:
                raise SmokeError("stream_payload_invalid") from None
            if event == "error":
                raise SmokeError("stream_error")
            if not isinstance(payload, dict) or payload.get("error") is not None:
                raise SmokeError("stream_payload_invalid")
            if event == "content":
                content = payload.get("text")
                if not isinstance(content, str):
                    raise SmokeError("stream_content_invalid")
                if content:
                    first = first if first is not None else clock()
                    characters += len(content)
                    chunks.append(content)
            if event == "done":
                done = True
                break
    if not done or not characters or first is None:
        raise SmokeError("stream_incomplete")
    return {
        "status": "passed",
        "characters": characters,
        "ttft_seconds": first - started,
        "duration_seconds": clock() - started,
        "completed": True,
    }, "".join(chunks)


def run(
    client: httpx.Client,
    *,
    live: bool = False,
    turns: int = 2,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    if turns not in {2, 3}:
        raise ValueError("turns_must_be_two_or_three")
    result: dict[str, Any] = {
        "mode": "live_direct" if live else "read_only_preflight",
        "status": "failed",
        "turns": [],
        "browser_normal_acceptance": "not_tested",
        "resources_created": False,
        "target_changed": False,
    }
    try:
        identity = preflight(client)
        result["identity"] = identity
        if live:
            schema = _json_get(client, "/openapi.json")
            fields = (
                schema.get("components", {})
                .get("schemas", {})
                .get("SimpleChatRequest", {})
                .get("properties", {})
            )
            if not {"expected_runtime_id", "expected_config_hash"} <= fields.keys():
                raise SmokeError("runtime_identity_guard_required")
            if "history" not in fields:
                raise SmokeError("conversation_history_required")
            session = "vast-chat-smoke-" + uuid4().hex
            marker = "cedar-" + uuid4().hex
            history: list[dict[str, str]] = []
            for index, template in enumerate(PROMPTS[:turns]):
                prompt = template.format(marker=marker)
                if preflight(client) != identity:
                    raise SmokeError("runtime_identity_changed")
                turn, answer = stream_turn(
                    client,
                    identity,
                    session,
                    prompt,
                    timeout_seconds=timeout_seconds,
                    history=history,
                )
                result["turns"].append(turn)
                if index == 1:
                    turn["recall_verified"] = answer.strip() == marker
                    if not turn["recall_verified"]:
                        raise SmokeError("conversation_recall_failed")
                history.extend(
                    [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": answer},
                    ]
                )
                if preflight(client) != identity:
                    raise SmokeError("runtime_identity_changed")
        result["status"] = "passed"
    except (SmokeError, ValueError, httpx.HTTPError) as error:
        # No response bodies, prompts, historical content or private endpoints.
        result["error"] = (
            str(error)
            if isinstance(error, SmokeError)
            else "transport_or_payload_failed"
        )
    return result


def main(argv=None, *, transport: httpx.BaseTransport | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", type=api_base, default="http://127.0.0.1:8800")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--turns", type=int, choices=[2, 3], default=2)
    parser.add_argument("--timeout", type=int, choices=range(1, 601), default=120)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    with httpx.Client(
        base_url=args.api_base,
        timeout=args.timeout,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
    ) as client:
        result = run(
            client, live=args.live, turns=args.turns, timeout_seconds=args.timeout
        )
    serialized = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.write_text(serialized)
        args.report.chmod(0o600)
    print(serialized, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
