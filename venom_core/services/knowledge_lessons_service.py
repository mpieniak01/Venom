"""Lesson mutation helpers extracted from knowledge routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def prune_latest_lessons(
    *, lessons_store: Any, count: int, logger: Any
) -> dict[str, Any]:
    deleted = lessons_store.delete_last_n(count)
    logger.info("Pruning: Usunięto %s najnowszych lekcji", deleted)
    return {
        "status": "success",
        "message": f"Usunięto {deleted} najnowszych lekcji",
        "deleted": deleted,
    }


def parse_iso_range(*, start: str, end: str) -> tuple[datetime, datetime]:
    # Workaround for Python < 3.11 which doesn't handle 'Z' suffix in fromisoformat.
    return (
        datetime.fromisoformat(start.replace("Z", "+00:00")),
        datetime.fromisoformat(end.replace("Z", "+00:00")),
    )


def prune_lessons_by_range(
    *,
    lessons_store: Any,
    start: str,
    end: str,
    start_dt: datetime,
    end_dt: datetime,
    logger: Any,
) -> dict[str, Any]:
    deleted = lessons_store.delete_by_time_range(start_dt, end_dt)
    logger.info("Pruning: Usunięto %s lekcji z zakresu %s - %s", deleted, start, end)
    return {
        "status": "success",
        "message": f"Usunięto {deleted} lekcji z zakresu {start} - {end}",
        "deleted": deleted,
        "start": start,
        "end": end,
    }


def prune_lessons_by_tag(
    *, lessons_store: Any, tag: str, logger: Any
) -> dict[str, Any]:
    deleted = lessons_store.delete_by_tag(tag)
    logger.info("Pruning: Usunięto %s lekcji z tagiem '%s'", deleted, tag)
    return {
        "status": "success",
        "message": f"Usunięto {deleted} lekcji z tagiem '{tag}'",
        "deleted": deleted,
        "tag": tag,
    }


def purge_all_lessons(*, lessons_store: Any, logger: Any) -> dict[str, Any]:
    lesson_count = len(lessons_store.lessons)
    success = lessons_store.clear_all()
    if not success:
        raise RuntimeError("Nie udało się wyczyścić bazy lekcji")
    logger.warning("💣 PURGE: Wyczyszczono całą bazę lekcji (%s lekcji)", lesson_count)
    return {
        "status": "success",
        "message": f"💣 Wyczyszczono całą bazę lekcji ({lesson_count} lekcji)",
        "deleted": lesson_count,
    }


def prune_lessons_by_ttl(*, lessons_store: Any, days: int) -> dict[str, Any]:
    deleted = lessons_store.prune_by_ttl(days)
    return {
        "status": "success",
        "message": f"Usunięto {deleted} lekcji starszych niż {days} dni",
        "deleted": deleted,
        "days": days,
    }


def dedupe_lessons(*, lessons_store: Any) -> dict[str, Any]:
    removed = lessons_store.dedupe_lessons()
    return {
        "status": "success",
        "message": f"Usunięto {removed} zduplikowanych lekcji",
        "removed": removed,
    }
