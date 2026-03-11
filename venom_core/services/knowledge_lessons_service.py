"""Lesson mutation helpers extracted from knowledge routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from venom_core.api.schemas.knowledge import KnowledgeEntryScope, KnowledgeSourceOrigin


class LoggerLike(Protocol):
    def info(self, msg: str, *args: object) -> None: ...

    def warning(self, msg: str, *args: object) -> None: ...


class LessonsStoreLike(Protocol):
    lessons: Any

    def delete_last_n(self, count: int) -> int: ...

    def delete_by_time_range(self, start_dt: datetime, end_dt: datetime) -> int: ...

    def delete_by_tag(self, tag: str) -> int: ...

    def clear_all(self) -> bool: ...

    def prune_by_ttl(self, days: int) -> int: ...

    def dedupe_lessons(self) -> int: ...


def _mutation_payload(
    *,
    action: str,
    affected_count: int,
    target: str = "knowledge_entry",
    source: str = KnowledgeSourceOrigin.LESSON.value,
    filter_payload: dict[str, Any] | None = None,
    scope: KnowledgeEntryScope = KnowledgeEntryScope.TASK,
) -> dict[str, Any]:
    return {
        "target": target,
        "action": action,
        "source": source,
        "affected_count": affected_count,
        "scope": scope.value,
        "filter": filter_payload or {},
    }


def prune_latest_lessons(
    *, lessons_store: LessonsStoreLike, count: int, logger: LoggerLike
) -> dict[str, Any]:
    deleted = lessons_store.delete_last_n(count)
    logger.info("Pruning: Usunięto %s najnowszych lekcji", deleted)
    return {
        "status": "success",
        "message": f"Usunięto {deleted} najnowszych lekcji",
        "deleted": deleted,
        "mutation": _mutation_payload(
            action="prune_latest",
            affected_count=deleted,
            filter_payload={"count": count},
        ),
    }


def parse_iso_range(*, start: str, end: str) -> tuple[datetime, datetime]:
    # Workaround for Python < 3.11 which doesn't handle 'Z' suffix in fromisoformat.
    return (
        datetime.fromisoformat(start.replace("Z", "+00:00")),
        datetime.fromisoformat(end.replace("Z", "+00:00")),
    )


def prune_lessons_by_range(
    *,
    lessons_store: LessonsStoreLike,
    start: str,
    end: str,
    start_dt: datetime,
    end_dt: datetime,
    logger: LoggerLike,
) -> dict[str, Any]:
    deleted = lessons_store.delete_by_time_range(start_dt, end_dt)
    logger.info("Pruning: Usunięto %s lekcji z zakresu %s - %s", deleted, start, end)
    return {
        "status": "success",
        "message": f"Usunięto {deleted} lekcji z zakresu {start} - {end}",
        "deleted": deleted,
        "start": start,
        "end": end,
        "mutation": _mutation_payload(
            action="prune_range",
            affected_count=deleted,
            filter_payload={"start": start, "end": end},
        ),
    }


def prune_lessons_by_tag(
    *, lessons_store: LessonsStoreLike, tag: str, logger: LoggerLike
) -> dict[str, Any]:
    deleted = lessons_store.delete_by_tag(tag)
    logger.info("Pruning: Usunięto %s lekcji z tagiem '%s'", deleted, tag)
    return {
        "status": "success",
        "message": f"Usunięto {deleted} lekcji z tagiem '{tag}'",
        "deleted": deleted,
        "tag": tag,
        "mutation": _mutation_payload(
            action="prune_tag",
            affected_count=deleted,
            filter_payload={"tag": tag},
        ),
    }


def purge_all_lessons(
    *, lessons_store: LessonsStoreLike, logger: LoggerLike
) -> dict[str, Any]:
    lesson_count = len(lessons_store.lessons)
    success = lessons_store.clear_all()
    if not success:
        raise RuntimeError("Nie udało się wyczyścić bazy lekcji")
    logger.warning("💣 PURGE: Wyczyszczono całą bazę lekcji (%s lekcji)", lesson_count)
    return {
        "status": "success",
        "message": f"💣 Wyczyszczono całą bazę lekcji ({lesson_count} lekcji)",
        "deleted": lesson_count,
        "mutation": _mutation_payload(
            action="purge",
            affected_count=lesson_count,
            filter_payload={"force": True},
            scope=KnowledgeEntryScope.GLOBAL,
        ),
    }


def prune_lessons_by_ttl(
    *, lessons_store: LessonsStoreLike, days: int
) -> dict[str, Any]:
    deleted = lessons_store.prune_by_ttl(days)
    return {
        "status": "success",
        "message": f"Usunięto {deleted} lekcji starszych niż {days} dni",
        "deleted": deleted,
        "days": days,
        "mutation": _mutation_payload(
            action="prune_ttl",
            affected_count=deleted,
            filter_payload={"days": days},
        ),
    }


def dedupe_lessons(*, lessons_store: LessonsStoreLike) -> dict[str, Any]:
    removed = lessons_store.dedupe_lessons()
    return {
        "status": "success",
        "message": f"Usunięto {removed} zduplikowanych lekcji",
        "removed": removed,
        "mutation": _mutation_payload(
            action="dedupe",
            affected_count=removed,
        ),
    }
