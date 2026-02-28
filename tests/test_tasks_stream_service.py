from __future__ import annotations

from uuid import uuid4

from venom_core.core.models import TaskStatus, VenomTask
from venom_core.services import tasks_stream_service as svc


class _WithModelDump:
    def model_dump(self):
        return {"k": "v"}


class _WithDict:
    def dict(self):
        return {"d": 1}


class _WithAttrs:
    def __init__(self):
        self.x = 1
        self.y = "z"


def _task_with_runtime(status: TaskStatus = TaskStatus.PROCESSING) -> VenomTask:
    return VenomTask(
        id=uuid4(),
        content="x",
        status=status,
        logs=["l1"],
        result="done",
        context_history={
            "llm_runtime": {
                "provider": "onnx",
                "model": "m",
                "endpoint": "http://e",
                "status": "ready",
            }
        },
    )


def test_runtime_and_context_extractors():
    task = _task_with_runtime()
    assert svc.get_llm_runtime(task)["provider"] == "onnx"
    assert svc.extract_task_context(task)["llm_runtime"]["model"] == "m"
    assert svc.extract_task_context(None) == {}


def test_serialize_context_used_variants():
    task = _task_with_runtime()

    task.context_used = {"a": 1}
    assert svc.serialize_context_used(task) == {"a": 1}

    task.context_used = _WithModelDump()
    assert svc.serialize_context_used(task) == {"k": "v"}

    task.context_used = _WithDict()
    assert svc.serialize_context_used(task) == {"d": 1}

    task.context_used = _WithAttrs()
    assert svc.serialize_context_used(task) == {"x": 1, "y": "z"}

    task.context_used = None
    assert svc.serialize_context_used(task) is None
    assert svc.serialize_context_used(None) is None


def test_stream_event_decisions():
    assert svc.should_emit_stream_event(
        status_changed=False,
        logs_delta=[],
        result_changed=False,
        ticks_since_emit=10,
        heartbeat_every_ticks=10,
    )
    assert not svc.should_emit_stream_event(
        status_changed=False,
        logs_delta=[],
        result_changed=False,
        ticks_since_emit=2,
        heartbeat_every_ticks=10,
    )
    assert (
        svc.resolve_stream_event_name(
            status_changed=False,
            logs_delta=[],
            result_changed=False,
        )
        == "heartbeat"
    )
    assert (
        svc.resolve_stream_event_name(
            status_changed=True,
            logs_delta=[],
            result_changed=False,
        )
        == "task_update"
    )


def test_poll_interval_and_terminal_status():
    assert (
        svc.resolve_poll_interval(
            previous_result=None,
            status=TaskStatus.PROCESSING,
            fast_poll_interval_seconds=0.05,
            poll_interval_seconds=0.25,
        )
        == 0.05
    )
    assert (
        svc.resolve_poll_interval(
            previous_result="x",
            status=TaskStatus.PROCESSING,
            fast_poll_interval_seconds=0.05,
            poll_interval_seconds=0.25,
        )
        == 0.25
    )
    assert svc.is_terminal_status(TaskStatus.COMPLETED)
    assert svc.is_terminal_status(TaskStatus.FAILED)
    assert not svc.is_terminal_status(TaskStatus.PROCESSING)


def test_payload_builders_and_missing_task_payload():
    task = _task_with_runtime(TaskStatus.COMPLETED)

    stream_payload = svc.build_stream_payload(task, ["new"])
    assert stream_payload["task_id"] == str(task.id)
    assert stream_payload["logs"] == ["new"]
    assert stream_payload["llm_provider"] == "onnx"
    assert stream_payload["llm_model"] == "m"

    finished_payload = svc.build_task_finished_payload(task)
    assert finished_payload["status"] == TaskStatus.COMPLETED.value
    assert finished_payload["result"] == "done"

    missing = svc.build_missing_task_payload(task.id)
    assert missing["task_id"] == str(task.id)
    assert missing["event"] == "gone"


def test_build_onnx_task_messages_forced_intent_branch():
    default_messages = svc.build_onnx_task_messages("hello", None)
    assert default_messages[0]["role"] == "system"
    assert "planem krok po kroku" not in default_messages[0]["content"]
    assert default_messages[1] == {"role": "user", "content": "hello"}

    planning_messages = svc.build_onnx_task_messages("hello", "COMPLEX_PLANNING")
    assert "planem krok po kroku" in planning_messages[0]["content"]
