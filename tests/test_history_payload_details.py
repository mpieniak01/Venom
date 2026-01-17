import json
from uuid import uuid4

from venom_core.api.routes import tasks
from venom_core.api.routes.tasks import HistoryRequestDetail
from venom_core.core.tracer import TraceStep


def test_extract_context_preview_parses_json():
    step = TraceStep(
        component="SimpleMode",
        action="context_preview",
        status="ok",
        details=json.dumps(
            {"prompt_context_preview": "U: hi", "hidden_prompts_count": 1}
        ),
    )
    preview = tasks._extract_context_preview([step])
    assert preview["prompt_context_preview"] == "U: hi"
    assert preview["hidden_prompts_count"] == 1


def test_history_request_detail_defaults_for_payload():
    detail = HistoryRequestDetail(
        request_id=uuid4(),
        prompt="Test",
        status="PENDING",
        created_at="2024-12-17T10:00:00",
        steps=[],
    )
    assert detail.context_preview is None
    assert detail.generation_params is None
    assert detail.llm_runtime is None
