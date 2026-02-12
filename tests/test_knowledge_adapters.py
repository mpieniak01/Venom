from types import SimpleNamespace

from venom_core.core.knowledge_adapters import (
    from_lesson,
    from_session_store_entry,
    from_vector_entry,
)


def test_adapter_from_session_store_entry_legacy_fallback():
    entry = {
        "role": "user",
        "content": "hello",
        "request_id": "r1",
        "timestamp": "2026-02-12T00:00:00+00:00",
    }
    record = from_session_store_entry("s1", entry)
    assert record.session_id == "s1"
    assert record.task_id == "r1"
    assert record.provenance.source.value == "session_store"
    assert record.retention.scope == "session"


def test_adapter_from_lesson_with_metadata():
    lesson = SimpleNamespace(
        lesson_id="l1",
        timestamp="2026-02-12T00:00:00+00:00",
        situation="sit",
        action="act",
        result="res",
        feedback="fb",
        tags=["a"],
        metadata={
            "task_id": "t1",
            "session_id": "s1",
            "provenance_source": "orchestrator",
            "retention_scope": "task",
        },
        to_dict=lambda: {
            "lesson_id": "l1",
            "timestamp": "2026-02-12T00:00:00+00:00",
            "situation": "sit",
            "action": "act",
            "result": "res",
            "feedback": "fb",
            "tags": ["a"],
            "metadata": {
                "task_id": "t1",
                "session_id": "s1",
                "provenance_source": "orchestrator",
                "retention_scope": "task",
            },
        },
    )
    record = from_lesson(lesson)
    assert record.record_id == "lesson:l1"
    assert record.task_id == "t1"
    assert record.provenance.source.value == "orchestrator"


def test_adapter_from_vector_entry_with_legacy_source():
    entry = {
        "id": "m1",
        "text": "memory",
        "metadata": {
            "session_id": "s1",
            "source": "vector_store",
            "timestamp": "2026-02-12T00:00:00+00:00",
        },
    }
    record = from_vector_entry(entry)
    assert record.record_id == "memory:m1"
    assert record.session_id == "s1"
    assert record.provenance.source.value == "vector_store"
