from datetime import datetime, timezone

from venom_core.core.knowledge_contract import KnowledgeKind
from venom_core.core.knowledge_ttl import compute_expires_at, resolve_ttl_days


def test_compute_expires_at_returns_none_for_zero_ttl():
    now = datetime(2026, 2, 12, tzinfo=timezone.utc)
    assert compute_expires_at(now, 0) is None
    assert compute_expires_at(now, None) is None


def test_compute_expires_at_for_positive_ttl():
    created = "2026-02-12T00:00:00+00:00"
    expires = compute_expires_at(created, 2)
    assert expires is not None
    assert expires.startswith("2026-02-14T00:00:00")


def test_resolve_ttl_days_returns_int_for_known_kinds():
    assert isinstance(resolve_ttl_days(KnowledgeKind.LESSON, "task"), int)
    assert isinstance(resolve_ttl_days(KnowledgeKind.MEMORY_ENTRY, "global"), int)
    assert isinstance(resolve_ttl_days(KnowledgeKind.SESSION_MESSAGE, "session"), int)
