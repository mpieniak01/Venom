"""Testy jednostkowe dla LessonsManager."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from venom_core.core.lessons_manager import LessonsManager
from venom_core.core.models import TaskRequest


class DummyStateManager:
    def __init__(self):
        self.logs = []
        self.task = SimpleNamespace(logs=["a", "b", "c", "d", "e", "f"])

    def add_log(self, task_id, message):
        self.logs.append((str(task_id), message))

    def get_task(self, _task_id):
        return self.task


class DummyLessonsStore:
    def __init__(self):
        self.saved = []

    def search_lessons(self, query, limit, tags=None):
        return [
            SimpleNamespace(
                lesson_id="l1",
                situation="s",
                result="r",
                feedback="f",
            )
        ]

    def add_lesson(self, **kwargs):
        self.saved.append(kwargs)
        return SimpleNamespace(lesson_id="lesson-123")


class DummyBroadcaster:
    def __init__(self):
        self.events = []

    async def broadcast_event(self, **kwargs):
        self.events.append(kwargs)


def test_should_store_and_log_learning_respects_flags(monkeypatch):
    state = DummyStateManager()
    manager = LessonsManager(state_manager=state, lessons_store=DummyLessonsStore())
    req = TaskRequest(content="x", store_knowledge=True)

    monkeypatch.setattr(
        "venom_core.core.lessons_manager.SETTINGS.ENABLE_META_LEARNING", True
    )
    assert manager.should_store_lesson(req, intent="GENERAL_CHAT", agent=None) is True
    assert (
        manager.should_log_learning(
            req, intent="GENERAL_CHAT", tool_required=False, agent=None
        )
        is True
    )

    assert manager.should_store_lesson(req, intent="TIME_REQUEST", agent=None) is False
    assert (
        manager.should_log_learning(req, intent="INFRA_STATUS", tool_required=False)
        is False
    )


@pytest.mark.asyncio
async def test_add_lessons_to_context_adds_block_and_broadcasts(monkeypatch):
    state = DummyStateManager()
    store = DummyLessonsStore()
    broadcaster = DummyBroadcaster()
    manager = LessonsManager(
        state_manager=state, lessons_store=store, event_broadcaster=broadcaster
    )

    monkeypatch.setattr(
        "venom_core.core.lessons_manager.SETTINGS.ENABLE_META_LEARNING", True
    )
    task_id = uuid4()
    output = await manager.add_lessons_to_context(task_id, "oryginalny kontekst")
    assert "LEKCJE Z PRZESZŁOŚCI" in output
    assert broadcaster.events


@pytest.mark.asyncio
async def test_save_task_lesson_success_and_error_paths(monkeypatch):
    state = DummyStateManager()
    store = DummyLessonsStore()
    manager = LessonsManager(
        state_manager=state, lessons_store=store, event_broadcaster=DummyBroadcaster()
    )
    task_id = uuid4()
    req = TaskRequest(content="x", store_knowledge=True)

    monkeypatch.setattr(
        "venom_core.core.lessons_manager.SETTINGS.ENABLE_META_LEARNING", True
    )

    await manager.save_task_lesson(
        task_id=task_id,
        context="context",
        intent="GENERAL_CHAT",
        result="ok",
        success=True,
        request=req,
    )
    await manager.save_task_lesson(
        task_id=task_id,
        context="context",
        intent="GENERAL_CHAT",
        result="fail",
        success=False,
        error="err",
        request=req,
    )
    assert len(store.saved) == 2


def test_append_learning_log_writes_jsonl_and_updates_metrics(tmp_path, monkeypatch):
    state = DummyStateManager()
    manager = LessonsManager(state_manager=state, lessons_store=DummyLessonsStore())
    task_id = uuid4()
    learning_path = tmp_path / "requests.jsonl"

    class DummyCollector:
        def __init__(self):
            self.calls = 0

        def increment_learning_logged(self):
            self.calls += 1

    collector = DummyCollector()

    monkeypatch.setattr(
        "venom_core.core.lessons_manager.LEARNING_LOG_PATH", learning_path
    )
    monkeypatch.setattr(
        "venom_core.core.lessons_manager.ensure_learning_log_boot_id", lambda: None
    )
    monkeypatch.setattr(
        "venom_core.core.lessons_manager.metrics_module.metrics_collector", collector
    )

    manager.append_learning_log(
        task_id=task_id,
        intent="GENERAL_CHAT",
        prompt="prompt",
        result="result",
        success=True,
    )

    assert learning_path.exists()
    assert "GENERAL_CHAT" in learning_path.read_text(encoding="utf-8")
    assert collector.calls == 1
