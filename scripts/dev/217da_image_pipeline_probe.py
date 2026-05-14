"""Probe image pipeline behavior via OpenAI-compatible chat endpoint."""

from __future__ import annotations

import json

import requests


def _request_payload(image_data_url: str, text: str | None) -> dict:
    user_content: list[dict[str, object]] = [
        {"type": "image_url", "image_url": image_data_url}
    ]
    if text:
        user_content.insert(0, {"type": "text", "text": text})
    return {
        "model": "multi_runtime",
        "messages": [{"role": "user", "content": user_content}],
        "max_tokens": 64,
    }


def main() -> None:
    base_url = "http://127.0.0.1:8014/v1/chat/completions"
    placeholder_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9fYzWxQAAAABJRU5ErkJggg=="

    image_only = requests.post(
        base_url,
        json=_request_payload(placeholder_image, None),
        timeout=10,
    )
    image_with_text = requests.post(
        base_url,
        json=_request_payload(placeholder_image, "Opisz obraz"),
        timeout=10,
    )

    result = {
        "image_only_status": image_only.status_code,
        "image_text_status": image_with_text.status_code,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
