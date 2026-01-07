from datetime import datetime
from uuid import uuid4

from venom_core.api.routes.tasks import HistoryRequestDetail

try:
    # 1. Create dummy context data
    ctx_data = {"lessons": ["lesson_1", "lesson_2"], "memory_entries": ["mem_1"]}

    # 2. Create HistoryRequestDetail with context_used
    detail = HistoryRequestDetail(
        request_id=uuid4(),
        prompt="test",
        status="COMPLETED",
        created_at=datetime.now().isoformat(),
        steps=[],
        context_used=ctx_data,
    )

    # 3. Verify
    print("Context Used verified:", detail.context_used)
    assert detail.context_used == ctx_data
    assert detail.context_used["lessons"][0] == "lesson_1"
    print("SUCCESS: HistoryRequestDetail model accepts context_used")

except Exception as e:
    print(f"FAILED: {e}")
    exit(1)
