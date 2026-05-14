#!/usr/bin/env python3
"""217DB probe: assistant_mode execution and fallback behavior."""

from __future__ import annotations

from _217db_probe_utils import print_json, request_json


def set_profile(mode: str) -> None:
    request_json(
        "POST",
        "/daemon/profile",
        {
            "assistant_mode": mode,
            "retrieval_mode": "off",
            "economy_mode": "off",
        },
    )


def respond(prompt: str) -> dict:
    return request_json(
        "POST",
        "/respond",
        {"messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]},
    )


def main() -> int:
    summary: dict[str, dict[str, object]] = {}
    for mode in ("off", "attached", "conditional"):
        set_profile(mode)
        response = respond("Napisz krótką odpowiedź testową.")
        summary[mode] = {
            "assistant_used": response.get("assistant_used"),
            "selected_policy": response.get("selected_policy"),
            "degradation_reasons": response.get("degradation_reasons", []),
        }
    print_json(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
