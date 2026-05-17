"""Tests for model introspection RAG focus shaping service."""

from __future__ import annotations

from venom_core.services.model_introspection_rag_focus_service import (
    build_rag_focus_payload,
)


def _snapshot_with_graph() -> dict[str, object]:
    return {
        "graph": {
            "nodes": [
                {"id": "runtime", "label": "runtime", "kind": "runtime"},
                {"id": "model", "label": "gemma3:4b", "kind": "model"},
                {"id": "analysis", "label": "live analysis", "kind": "analysis"},
            ],
            "edges": [
                {"from": "runtime", "to": "model", "label": "active model"},
                {"from": "runtime", "to": "analysis", "label": "prompt execution"},
            ],
        }
    }


def test_build_rag_focus_payload_uses_runtime_trace_when_available() -> None:
    payload = build_rag_focus_payload(
        prompt="Co to jest słońce?",
        snapshot=_snapshot_with_graph(),
        process_trace={
            "steps": [
                {
                    "action": "retrieval",
                    "details": (
                        '{"entities":[{"id":"e1","label":"Słońce","kind":"entity","active":true}],'
                        '"evidence_edges":[{"from":"query","to":"e1","label":"grounded","active":true}],'
                        '"active_entity_ids":["e1"],"grounding_score":0.91}'
                    ),
                }
            ]
        },
    )

    assert payload["source"] == "runtime_trace"
    assert payload["entities"][0]["id"] == "e1"
    assert payload["evidence_edges"][0]["id"].startswith("edge:")
    assert payload["evidence_edges"][0]["label"] == "grounded"
    assert payload["grounding_score"] == 0.91
    assert isinstance(payload["answer_evidence_links"], list)


def test_build_rag_focus_payload_falls_back_to_graph_when_trace_missing() -> None:
    payload = build_rag_focus_payload(
        prompt="Co to jest słońce?",
        snapshot=_snapshot_with_graph(),
        process_trace=None,
    )

    assert payload["source"] == "graph_fallback"
    assert payload["entities"]
    assert payload["evidence_edges"]
    assert isinstance(payload["answer_evidence_links"], list)


def test_build_rag_focus_payload_prefers_runtime_trace_for_request_response_steps() -> (
    None
):
    payload = build_rag_focus_payload(
        prompt="Co to jest słońce?",
        snapshot=_snapshot_with_graph(),
        process_trace={
            "steps": [
                {
                    "action": "request",
                    "details": "session_id=- prompt=Co to jest słońce?",
                },
                {
                    "action": "response",
                    "details": (
                        '{"chunks":1,"total_ms":10,"chars":31,"response":"Słońce to gwiazda naszego układu."}'
                    ),
                },
            ]
        },
        response_text="Słońce to gwiazda naszego układu.",
    )

    assert payload["source"] == "runtime_trace"
    assert payload["query"] == "Co to jest słońce?"
    assert len(payload["entities"]) >= 1
    assert len(payload["evidence_edges"]) >= 1


def test_build_rag_focus_payload_filters_invalid_trace_shapes() -> None:
    payload = build_rag_focus_payload(
        prompt="Co to jest słońce?",
        snapshot=_snapshot_with_graph(),
        process_trace={
            "steps": [
                {
                    "action": "retrieval",
                    "details": (
                        '{"entities":[{"id":"ok","label":"Słońce"}, {"id":"x"}],'
                        '"evidence_edges":[{"from":"query","to":"ok"}, {"from":"query"}],'
                        '"active_entity_ids":["ok", null]}'
                    ),
                }
            ]
        },
    )
    assert payload["source"] == "runtime_trace"
    assert [entity["id"] for entity in payload["entities"]] == ["ok"]
    assert len(payload["evidence_edges"]) == 1
    assert payload["active_entity_ids"] == ["ok"]


def test_build_rag_focus_payload_extracts_query_from_context_preview() -> None:
    payload = build_rag_focus_payload(
        prompt="fallback prompt",
        snapshot=_snapshot_with_graph(),
        process_trace={
            "steps": [
                {
                    "action": "context_preview",
                    "details": (
                        '{"prompt_context_preview":"SYSTEM:\\nRules\\n\\nUSER: Co to jest Księżyc?"}'
                    ),
                },
                {
                    "action": "response",
                    "details": '{"response":"Księżyc to naturalny satelita."}',
                },
            ]
        },
    )
    assert payload["source"] == "runtime_trace"
    assert payload["query"] == "Co to jest Księżyc?"
