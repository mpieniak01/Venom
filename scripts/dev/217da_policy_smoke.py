"""Smoke test for execution policy update and readback."""

from __future__ import annotations

import json

import requests


def main() -> None:
    base_url = "http://127.0.0.1:8014/v1/daemon/profile"
    payload = {
        "execution_mode": "balanced",
        "image_strategy": "vlm_only",
        "retrieval_mode": "auto",
        "audio_output_mode": "off",
        "assistant_mode": "conditional",
        "economy_mode": "auto",
    }

    update_resp = requests.post(base_url, json=payload, timeout=5)
    update_resp.raise_for_status()

    read_resp = requests.get(base_url, timeout=5)
    read_resp.raise_for_status()

    print(
        json.dumps(
            {
                "update": update_resp.json(),
                "profile": read_resp.json().get("profile", {}),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
