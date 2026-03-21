from __future__ import annotations

import json
from pathlib import Path

import pytest

from venom_core.api.routes import learning as learning_route


@pytest.mark.asyncio
async def test_get_learning_logs_reads_sync_when_aiofiles_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "requests.jsonl"
    log_path.write_text(
        "\n".join(
            [
                json.dumps({"task_id": "a", "intent": "GENERAL_CHAT", "success": True}),
                json.dumps({"task_id": "b", "intent": "GENERAL_CHAT", "success": True}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(learning_route, "LEARNING_LOG_PATH", log_path)
    monkeypatch.setattr(learning_route, "aiofiles", None)
    monkeypatch.setattr(learning_route, "ensure_learning_log_boot_id", lambda: None)

    payload = await learning_route.get_learning_logs(limit=10)

    assert payload["count"] == 2
    assert [item["task_id"] for item in payload["items"]] == ["b", "a"]


@pytest.mark.asyncio
async def test_get_learning_logs_sync_fallback_applies_filters_and_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "requests.jsonl"
    log_path.write_text(
        "\n".join(
            [
                "{invalid-json",
                json.dumps(
                    {
                        "task_id": "a",
                        "intent": "GENERAL_CHAT",
                        "success": True,
                        "tags": ["GENERAL_CHAT", "llm_only"],
                    }
                ),
                json.dumps(
                    {
                        "task_id": "b",
                        "intent": "GENERAL_CHAT",
                        "success": False,
                        "tags": ["GENERAL_CHAT", "failure"],
                    }
                ),
                json.dumps(
                    {
                        "task_id": "c",
                        "intent": "FILE_OPERATION",
                        "success": True,
                        "tags": ["FILE_OPERATION"],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(learning_route, "LEARNING_LOG_PATH", log_path)
    monkeypatch.setattr(learning_route, "aiofiles", None)
    monkeypatch.setattr(learning_route, "ensure_learning_log_boot_id", lambda: None)

    payload = await learning_route.get_learning_logs(
        limit=1,
        intent="GENERAL_CHAT",
        success=True,
        tag="llm_only",
    )

    assert payload["count"] == 1
    assert payload["items"][0]["task_id"] == "a"
