"""Module Example provider loader (external-ready module package)."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import uuid4

from venom_core.config import SETTINGS, Settings
from venom_core.utils.logger import get_logger
from venom_module_example.api.schemas import (
    ContentCandidate,
    DraftBundle,
    DraftVariant,
    ModuleExampleAuditEntry,
    PublishQueueItem,
    PublishResult,
)

logger = get_logger(__name__)


class ModuleExampleProvider(Protocol):
    def list_candidates(
        self,
        *,
        channel: str | None = None,
        language: str | None = None,
        limit: int = 20,
        min_score: float = 0.0,
    ) -> list[ContentCandidate]: ...

    def generate_drafts(
        self,
        *,
        candidate_id: str,
        channels: list[str],
        languages: list[str],
        tone: str | None = None,
    ) -> DraftBundle: ...

    def queue_draft(
        self,
        *,
        draft_id: str,
        target_channel: str,
        target_repo: str | None = None,
        target_path: str | None = None,
    ) -> PublishQueueItem: ...

    def publish(
        self,
        *,
        item_id: str,
        actor: str,
        confirm_publish: bool,
    ) -> PublishResult: ...

    def list_queue(self) -> list[PublishQueueItem]: ...

    def list_audit(self) -> list[ModuleExampleAuditEntry]: ...


class StubModuleExampleProvider:
    """Safe public fallback provider for modular mode."""

    def __init__(self):
        self._queue: dict[str, PublishQueueItem] = {}
        self._audit: list[ModuleExampleAuditEntry] = []
        self._drafts: dict[str, DraftBundle] = {}

    def list_candidates(
        self,
        *,
        channel: str | None = None,
        language: str | None = None,
        limit: int = 20,
        min_score: float = 0.0,
    ) -> list[ContentCandidate]:
        _ = channel, language
        items = [
            ContentCandidate(
                id="c-001",
                title="Observability lessons learned in AI ops",
                source="oss_stub",
                url="https://example.local/observability",
                topic="observability",
                score=0.82,
                freshness_hours=6,
            ),
            ContentCandidate(
                id="c-002",
                title="How to structure engineering changelogs",
                source="oss_stub",
                url="https://example.local/changelog",
                topic="engineering",
                score=0.73,
                freshness_hours=12,
            ),
        ]
        return [i for i in items if i.score >= min_score][: max(1, limit)]

    def generate_drafts(
        self,
        *,
        candidate_id: str,
        channels: list[str],
        languages: list[str],
        tone: str | None = None,
    ) -> DraftBundle:
        bundle_id = f"d-{uuid4().hex[:10]}"
        channels = channels or ["x"]
        languages = languages or ["pl"]
        variants = []
        for channel in channels:
            for language in languages:
                variants.append(
                    DraftVariant(
                        id=f"v-{uuid4().hex[:10]}",
                        channel=channel,
                        language=language,
                        content=(
                            f"[{language}/{channel}] Draft for {candidate_id}. "
                            "Edit before publishing."
                        ),
                        tone=tone,
                    )
                )
        bundle = DraftBundle(id=bundle_id, candidate_id=candidate_id, variants=variants)
        self._drafts[bundle_id] = bundle
        self._audit.append(
            ModuleExampleAuditEntry(
                id=f"a-{uuid4().hex[:10]}",
                action="draft_generated",
                actor="system",
                entity_id=bundle_id,
                details=f"candidate={candidate_id}",
            )
        )
        return bundle

    def queue_draft(
        self,
        *,
        draft_id: str,
        target_channel: str,
        target_repo: str | None = None,
        target_path: str | None = None,
    ) -> PublishQueueItem:
        if draft_id not in self._drafts:
            raise ValueError(f"Unknown draft: {draft_id}")
        now = datetime.now(UTC)
        item = PublishQueueItem(
            id=f"q-{uuid4().hex[:10]}",
            draft_id=draft_id,
            target_channel=target_channel,
            target_repo=target_repo,
            target_path=target_path,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        self._queue[item.id] = item
        self._audit.append(
            ModuleExampleAuditEntry(
                id=f"a-{uuid4().hex[:10]}",
                action="queued",
                actor="system",
                entity_id=item.id,
                details=f"channel={target_channel}",
            )
        )
        return item

    def publish(
        self,
        *,
        item_id: str,
        actor: str,
        confirm_publish: bool,
    ) -> PublishResult:
        item = self._queue.get(item_id)
        if item is None:
            raise ValueError(f"Unknown queue item: {item_id}")
        if not confirm_publish:
            raise ValueError("confirm_publish=true is required")
        item.status = "published"
        item.updated_at = datetime.now(UTC)
        self._audit.append(
            ModuleExampleAuditEntry(
                id=f"a-{uuid4().hex[:10]}",
                action="published",
                actor=actor,
                entity_id=item_id,
                details=f"channel={item.target_channel}",
            )
        )
        return PublishResult(
            item_id=item_id,
            status="published",
            message="Published successfully",
            published_at=item.updated_at,
        )

    def list_queue(self) -> list[PublishQueueItem]:
        return sorted(self._queue.values(), key=lambda item: item.created_at)

    def list_audit(self) -> list[ModuleExampleAuditEntry]:
        return list(self._audit)


_provider_instance: ModuleExampleProvider | None = None
_provider_lock = Lock()


def reset_module_example_provider_cache() -> None:
    global _provider_instance
    with _provider_lock:
        _provider_instance = None


def _load_extension_provider(settings: Settings) -> ModuleExampleProvider | None:
    module_path = settings.MODULE_EXAMPLE_EXTENSION_MODULE.strip()
    if not module_path:
        logger.warning("MODULE_EXAMPLE_MODE=extension but no module configured.")
        return None
    try:
        module = importlib.import_module(module_path)
        factory = getattr(module, "create_provider", None)
        if not callable(factory):
            logger.warning(
                "Module %s does not expose callable create_provider().", module_path
            )
            return None
        provider = factory()
        return provider
    except Exception as exc:
        logger.warning(
            "Failed to load Module Example extension module %s: %s", module_path, exc
        )
        return None


def get_module_example_provider(
    settings: Settings = SETTINGS,
) -> ModuleExampleProvider | None:
    mode = (settings.MODULE_EXAMPLE_MODE or "disabled").strip().lower()
    if mode == "disabled":
        return None

    global _provider_instance
    with _provider_lock:
        if _provider_instance is not None:
            return _provider_instance

        if mode == "extension":
            provider = _load_extension_provider(settings)
            if provider is None:
                provider = StubModuleExampleProvider()
        else:
            provider = StubModuleExampleProvider()

        _provider_instance = provider
        return _provider_instance
