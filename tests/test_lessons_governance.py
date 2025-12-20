"""Testy dla governance lekcji (TTL, dedupe, toggle)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from venom_core.api.routes import memory as memory_routes
from venom_core.config import SETTINGS
from venom_core.memory.lessons_store import Lesson, LessonsStore


def test_prune_by_ttl_removes_old_lessons(tmp_path):
    store = LessonsStore(storage_path=str(tmp_path / "lessons.json"), auto_save=False)
    now = datetime.now(timezone.utc)
    old_lesson = Lesson(
        situation="old",
        action="act",
        result="res",
        feedback="fb",
        timestamp=(now - timedelta(days=5)).isoformat(),
    )
    new_lesson = Lesson(
        situation="new",
        action="act",
        result="res",
        feedback="fb",
        timestamp=now.isoformat(),
    )
    store.add_lesson(old_lesson)
    store.add_lesson(new_lesson)

    deleted = store.prune_by_ttl(3)
    assert deleted == 1
    assert len(store.lessons) == 1


def test_dedupe_lessons_keeps_latest(tmp_path):
    store = LessonsStore(storage_path=str(tmp_path / "lessons.json"), auto_save=False)
    now = datetime.now(timezone.utc)
    older = Lesson(
        situation="dup",
        action="act",
        result="res",
        feedback="fb",
        timestamp=(now - timedelta(days=1)).isoformat(),
        lesson_id=str(uuid4()),
    )
    newer = Lesson(
        situation="dup",
        action="act",
        result="res",
        feedback="fb",
        timestamp=now.isoformat(),
        lesson_id=str(uuid4()),
    )
    store.add_lesson(older)
    store.add_lesson(newer)

    removed = store.dedupe_lessons()
    assert removed == 1
    assert len(store.lessons) == 1
    remaining = next(iter(store.lessons.values()))
    assert remaining.lesson_id == newer.lesson_id


@pytest.mark.asyncio
async def test_toggle_learning_updates_settings(monkeypatch):
    original = SETTINGS.ENABLE_META_LEARNING
    monkeypatch.setattr(memory_routes.config_manager, "update_config", lambda *_: {})
    request = memory_routes.LearningToggleRequest(enabled=not original)
    result = await memory_routes.toggle_learning(request)
    assert result["enabled"] == (not original)
    SETTINGS.ENABLE_META_LEARNING = original
