from datetime import datetime
from uuid import uuid4

from venom_core.api.routes.tasks import HistoryRequestDetail


def test_history_request_detail_accepts_context_used() -> None:
    ctx_data = {"lessons": ["lesson_1", "lesson_2"], "memory_entries": ["mem_1"]}
    detail = HistoryRequestDetail(
        request_id=uuid4(),
        prompt="test",
        status="COMPLETED",
        created_at=datetime.now().isoformat(),
        steps=[],
        context_used=ctx_data,
    )
    assert detail.context_used == ctx_data
    assert detail.context_used["lessons"][0] == "lesson_1"
