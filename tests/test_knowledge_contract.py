from venom_core.core.knowledge_contract import (
    KnowledgeContextMapV1,
    KnowledgeKind,
    KnowledgeLinkV1,
    KnowledgeRecordV1,
    KnowledgeSource,
    ProvenanceV1,
    RetentionV1,
)


def test_knowledge_record_v1_serialization():
    record = KnowledgeRecordV1(
        record_id="memory:123",
        kind=KnowledgeKind.MEMORY_ENTRY,
        session_id="s1",
        task_id="t1",
        user_id="u1",
        content="test",
        metadata={"k": "v"},
        provenance=ProvenanceV1(source=KnowledgeSource.VECTOR_STORE),
        retention=RetentionV1(scope="global", ttl_days=None, expires_at=None),
        created_at="2026-02-12T00:00:00+00:00",
    )
    payload = record.model_dump()
    assert payload["kind"] == "memory_entry"
    assert payload["provenance"]["source"] == "vector_store"
    assert payload["retention"]["scope"] == "global"


def test_knowledge_context_map_v1_contains_links():
    record = KnowledgeRecordV1(
        record_id="lesson:1",
        kind=KnowledgeKind.LESSON,
        session_id="s1",
        task_id="t1",
        user_id=None,
        content="lesson content",
        metadata={},
        provenance=ProvenanceV1(source=KnowledgeSource.LESSONS_STORE),
        retention=RetentionV1(scope="task"),
        created_at="2026-02-12T00:00:00+00:00",
    )
    link = KnowledgeLinkV1(
        relation="session->lesson",
        source_id="session:s1",
        target_id="lesson:1",
    )
    context = KnowledgeContextMapV1(session_id="s1", records=[record], links=[link])
    assert context.records[0].kind == KnowledgeKind.LESSON
    assert context.links[0].relation == "session->lesson"
