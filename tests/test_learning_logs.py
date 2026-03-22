"""Unit tests for learning log flow (LLM-only)."""

import json
from types import SimpleNamespace
from uuid import uuid4

from venom_core.core import learning_log as learning_log_mod
from venom_core.core import orchestrator as orchestrator_module
from venom_core.core.orchestrator import Orchestrator


class DummyStateManager:
    def __init__(self):
        self.logs = []

    def add_log(self, task_id, message):
        self.logs.append((str(task_id), message))


class DummyMetricsCollector:
    def __init__(self):
        self.count = 0

    def increment_learning_logged(self):
        self.count += 1


def test_should_log_learning_respects_flags():
    orch = Orchestrator.__new__(Orchestrator)
    request = SimpleNamespace(store_knowledge=True)

    assert (
        orch._should_log_learning(request, "GENERAL_CHAT", tool_required=False) is True
    )
    assert orch._should_log_learning(request, "RESEARCH", tool_required=True) is False
    assert (
        orch._should_log_learning(request, "INFRA_STATUS", tool_required=False) is False
    )
    agent = SimpleNamespace(disable_learning=True)
    assert (
        orch._should_log_learning(
            request, "GENERAL_CHAT", tool_required=False, agent=agent
        )
        is False
    )


def test_append_learning_log_writes_jsonl(tmp_path, monkeypatch):
    log_path = tmp_path / "learning.jsonl"
    monkeypatch.setattr(orchestrator_module, "LEARNING_LOG_PATH", log_path)
    metrics = DummyMetricsCollector()
    monkeypatch.setattr(
        orchestrator_module.metrics_module, "metrics_collector", metrics
    )

    orch = Orchestrator.__new__(Orchestrator)
    orch.state_manager = DummyStateManager()

    task_id = uuid4()
    orch._append_learning_log(
        task_id=task_id,
        intent="GENERAL_CHAT",
        prompt="hello",
        result="world",
        success=True,
        error="",
    )

    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8").strip()
    assert '"intent": "GENERAL_CHAT"' in content
    assert '"tool_required": false' in content
    assert metrics.count == 1
    assert orch.state_manager.logs


def test_append_learning_log_rotates_stale_boot_once_and_keeps_new_entries(
    tmp_path, monkeypatch
):
    log_path = tmp_path / "learning.jsonl"
    meta_path = tmp_path / "learning_meta.json"
    log_path.write_text('{"legacy": true}\n', encoding="utf-8")
    meta_path.write_text(json.dumps({"boot_id": "old-boot"}), encoding="utf-8")

    monkeypatch.setattr(orchestrator_module, "LEARNING_LOG_PATH", log_path)
    monkeypatch.setattr(learning_log_mod, "LEARNING_LOG_PATH", log_path)
    monkeypatch.setattr(learning_log_mod, "LEARNING_LOG_META_PATH", meta_path)
    monkeypatch.setattr(learning_log_mod, "BOOT_ID", "stable-boot")
    monkeypatch.setattr(learning_log_mod, "_ROTATION_LOCK_BOOT_ID", None)

    metrics = DummyMetricsCollector()
    monkeypatch.setattr(
        orchestrator_module.metrics_module, "metrics_collector", metrics
    )

    orch = Orchestrator.__new__(Orchestrator)
    orch.state_manager = DummyStateManager()

    first_task = uuid4()
    second_task = uuid4()
    orch._append_learning_log(
        task_id=first_task,
        intent="GENERAL_CHAT",
        prompt="p1",
        result="r1",
        success=True,
        error="",
    )
    orch._append_learning_log(
        task_id=second_task,
        intent="GENERAL_CHAT",
        prompt="p2",
        result="r2",
        success=True,
        error="",
    )

    rows = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    task_ids = {row["task_id"] for row in rows}

    assert len(rows) == 2
    assert str(first_task) in task_ids
    assert str(second_task) in task_ids
