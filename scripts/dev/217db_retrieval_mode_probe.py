#!/usr/bin/env python3
"""217DB probe: retrieval_mode on/off/always diagnostics."""

from __future__ import annotations

from _217db_probe_utils import print_json, request_json


def set_profile(mode: str) -> None:
    request_json("POST", "/daemon/profile", {"retrieval_mode": mode})


def respond(prompt: str) -> dict:
    return request_json(
        "POST",
        "/respond",
        {"messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]},
    )


def main() -> int:
    summary: dict[str, dict[str, object]] = {}
    for mode in ("off", "auto", "always"):
        set_profile(mode)
        response = respond("Jaki jest związek między A i B?")
        summary[mode] = {
            "retrieval_used": response.get("retrieval_used"),
            "retrieval_route": response.get("retrieval_route"),
            "retrieval_context_items": response.get("retrieval_context_items"),
            "degradation_reasons": response.get("degradation_reasons", []),
        }
    print_json(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
