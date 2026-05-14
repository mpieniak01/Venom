#!/usr/bin/env python3
"""217DB probe: image_strategy behavior and OCR/VLM routing."""

from __future__ import annotations

from _217db_probe_utils import print_json, request_json

PLACEHOLDER_IMAGE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4"
    "////fwAJ+wP9fYzWxQAAAABJRU5ErkJggg=="
)


def set_profile(strategy: str) -> None:
    request_json("POST", "/daemon/profile", {"image_strategy": strategy})


def respond(prompt: str) -> dict:
    return request_json(
        "POST",
        "/respond",
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "data": PLACEHOLDER_IMAGE},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
        },
    )


def main() -> int:
    summary: dict[str, dict[str, object]] = {}
    for strategy in ("vlm_only", "ocr_first", "hybrid"):
        set_profile(strategy)
        response = respond("Opisz obraz i wyciągnij tekst.")
        summary[strategy] = {
            "selected_image_strategy": response.get("selected_image_strategy"),
            "execution_trace": response.get("execution_trace", []),
            "degradation_reasons": response.get("degradation_reasons", []),
            "component_snapshot_size": len(response.get("component_snapshot", [])),
        }
    print_json(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
