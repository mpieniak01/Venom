#!/usr/bin/env python3
"""Smoke test for Fish Speech runtime scaffold."""

from __future__ import annotations

import asyncio
import os

import httpx

SERVICE_HOST = os.getenv("FISH_SPEECH_HOST", "127.0.0.1")
SERVICE_PORT = int(os.getenv("FISH_SPEECH_PORT", "8024"))
BASE_URL = f"http://{SERVICE_HOST}:{SERVICE_PORT}"


async def main() -> int:
    timeout = httpx.Timeout(10.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        health = await client.get(f"{BASE_URL}/health")
        status = await client.get(f"{BASE_URL}/status")
        tts = await client.post(
            f"{BASE_URL}/v1/tts",
            json={"text": "To jest test fish speech runtime.", "language": "pl"},
        )

    print("health:", health.status_code, health.text)
    print("status:", status.status_code, status.text)
    print("tts:", tts.status_code, tts.text)

    if health.status_code != 200 or status.status_code != 200:
        return 1
    if tts.status_code not in {501, 503}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
