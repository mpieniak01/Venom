#!/usr/bin/env python3
"""217DB probe: economy_mode impact on runtime execution."""

from __future__ import annotations

from _217db_probe_utils import print_json, request_json


def set_profile(mode: str) -> None:
    request_json(
        "POST", "/daemon/profile", {"economy_mode": mode, "retrieval_mode": "auto"}
    )


def respond(prompt: str) -> dict:
    return request_json(
        "POST",
        "/respond",
        {"messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]},
    )


def main() -> int:
    summary: dict[str, dict[str, object]] = {}
    for mode in ("off", "auto"):
        set_profile(mode)
        response = respond("Dlaczego to działa?")
        summary[mode] = {
            "economy_mode_activated": response.get("economy_mode_activated"),
            "retrieval_used": response.get("retrieval_used"),
            "assistant_used": response.get("assistant_used"),
            "degradation_reasons": response.get("degradation_reasons", []),
        }
    print_json(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
