#!/usr/bin/env python3
"""Manage voice route/decoder profile via local Venom API."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def _request_json(
    *,
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url=url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:  # nosec B310
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read or update voice route / audio decoder profile."
    )
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8000",
        help="Base URL of Venom API (default: http://127.0.0.1:8000).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("show", help="Show active voice route profile.")

    set_parser = subparsers.add_parser("set", help="Set voice route profile.")
    set_parser.add_argument(
        "--voice-route-profile",
        choices=["auto", "gemma4", "runtime_lokalny", "venom-agent", "chat_tekstowy"],
        required=True,
    )
    set_parser.add_argument(
        "--audio-decoder-profile",
        choices=["auto", "gemma_native", "faster_whisper", "hybrid"],
        required=True,
    )
    set_parser.add_argument(
        "--audio-decoder-chain",
        default="",
        help="Optional chain, e.g. gemma_native,faster_whisper",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    endpoint = f"{args.api_base.rstrip('/')}/api/v1/audio/routes/profile"
    try:
        if args.command == "show":
            payload = _request_json(url=endpoint, method="GET")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        payload = {
            "voice_route_profile": args.voice_route_profile,
            "audio_decoder_profile": args.audio_decoder_profile,
            "audio_decoder_chain": [
                part.strip()
                for part in args.audio_decoder_chain.split(",")
                if part.strip()
            ],
        }
        result = _request_json(url=endpoint, method="POST", payload=payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
