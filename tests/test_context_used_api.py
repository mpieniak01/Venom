"""Testy jednostkowe dla API context_used."""

import sys
from pathlib import Path
from uuid import uuid4

# Ensure venom_core is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from venom_core.api.routes.tasks import HistoryRequestDetail
from venom_core.core.models import ContextUsed


def test_history_request_detail_with_context_used_dict():
    """Test tworzenia HistoryRequestDetail z kontekstem jako słownik."""
    request_id = uuid4()
    context_data = {
        "lessons": ["lesson-1", "lesson-2"],
        "memory_entries": ["mem-abc", "mem-def"],
    }

    detail = HistoryRequestDetail(
        request_id=request_id,
        prompt="Test prompt",
        status="COMPLETED",
        created_at="2024-12-17T10:00:00",
        steps=[],
        context_used=context_data,
    )

    assert detail.context_used == context_data
    assert len(detail.context_used["lessons"]) == 2
    assert "lesson-1" in detail.context_used["lessons"]


def test_history_request_detail_context_used_none_by_default():
    """Test domyślnej wartości context_used."""
    detail = HistoryRequestDetail(
        request_id=uuid4(),
        prompt="Test",
        status="PENDING",
        created_at="2024-12-17T10:00:00",
        steps=[],
    )

    assert detail.context_used is None


def test_context_used_model_structure():
    """Test struktury modelu Pydantic ContextUsed (jeśli używany bezpośrednio)."""
    # Sprawdzamy czy model ContextUsed (zdefiniowany w models.py) zachowuje się poprawnie
    ctx = ContextUsed(lessons=["L1"], memory_entries=["M1", "M2"])

    assert ctx.lessons == ["L1"]
    assert len(ctx.memory_entries) == 2
