"""RAG focus payload shaping for model introspection analysis."""

from __future__ import annotations

import json
import re
from typing import Any

_MAX_ENTITIES = 8
_MAX_EDGES = 12
_MAX_ANSWER_LINKS = 4
_TRACE_RUNTIME_ACTIONS = {
    "request",
    "context_preview",
    "first_chunk",
    "response",
    "retrieval",
    "rag_focus",
}
_STOPWORDS = {"co", "to", "jest", "the", "is", "what"}


def _parse_json_dict(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_entity(entity: Any) -> dict[str, Any] | None:
    if not isinstance(entity, dict):
        return None
    entity_id = entity.get("id")
    label = entity.get("label")
    if not entity_id or not label:
        return None
    return {
        "id": str(entity_id),
        "label": str(label),
        "kind": str(entity.get("kind") or "entity"),
        "active": bool(entity.get("active", False)),
    }


def _normalize_edge(edge: Any) -> dict[str, Any] | None:
    if not isinstance(edge, dict):
        return None
    edge_from = edge.get("from")
    edge_to = edge.get("to")
    if not edge_from or not edge_to:
        return None
    return {
        "from": str(edge_from),
        "to": str(edge_to),
        "label": str(edge.get("label") or "evidence"),
        "active": bool(edge.get("active", False)),
    }


def _assign_edge_ids(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, edge in enumerate(edges[:_MAX_EDGES]):
        with_id = dict(edge)
        with_id["id"] = str(edge.get("id") or f"edge:{index + 1}")
        normalized.append(with_id)
    return normalized


def _iter_step_payloads(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for step in steps:
        details = step.get("details")
        if isinstance(details, str):
            payloads.append(_parse_json_dict(details))
    return payloads


def _collect_entities_from_payload(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_entities: list[dict[str, Any]] = []
    for key in ("entities", "retrieval_entities", "grounded_entities"):
        raw_entities = parsed.get(key)
        if not isinstance(raw_entities, list):
            continue
        for entity in raw_entities:
            normalized = _normalize_entity(entity)
            if normalized is not None:
                normalized_entities.append(normalized)
    return normalized_entities


def _extract_entities_from_trace_steps(
    steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for parsed in _iter_step_payloads(steps):
        entities.extend(_collect_entities_from_payload(parsed))
    deduplicated: dict[str, dict[str, Any]] = {}
    for entity in entities:
        deduplicated[entity["id"]] = entity
    return list(deduplicated.values())[:_MAX_ENTITIES]


def _collect_edges_from_payload(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_edges: list[dict[str, Any]] = []
    for key in ("evidence_edges", "grounding_edges", "retrieval_edges"):
        raw_edges = parsed.get(key)
        if not isinstance(raw_edges, list):
            continue
        for edge in raw_edges:
            normalized = _normalize_edge(edge)
            if normalized is not None:
                normalized_edges.append(normalized)
    return normalized_edges


def _extract_edges_from_trace_steps(
    steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for parsed in _iter_step_payloads(steps):
        edges.extend(_collect_edges_from_payload(parsed))
    deduplicated: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edges:
        deduplicated[(edge["from"], edge["to"], edge["label"])] = edge
    return list(deduplicated.values())[:_MAX_EDGES]


def _extract_active_entity_ids_from_trace_steps(
    steps: list[dict[str, Any]],
) -> list[str]:
    active_ids: list[str] = []
    for step in steps:
        details = step.get("details")
        if not isinstance(details, str):
            continue
        parsed = _parse_json_dict(details)
        raw_ids = parsed.get("active_entity_ids")
        if not isinstance(raw_ids, list):
            continue
        for raw_id in raw_ids:
            if raw_id is not None:
                active_ids.append(str(raw_id))
    deduplicated: list[str] = []
    for entity_id in active_ids:
        if entity_id not in deduplicated:
            deduplicated.append(entity_id)
    return deduplicated


def _extract_grounding_score_from_trace_steps(
    steps: list[dict[str, Any]],
) -> float | None:
    for step in reversed(steps):
        details = step.get("details")
        if not isinstance(details, str):
            continue
        parsed = _parse_json_dict(details)
        raw_score = parsed.get("grounding_score")
        if isinstance(raw_score, (int, float)):
            return max(0.0, min(1.0, float(raw_score)))
    return None


def _extract_query_from_request_details(details: str) -> str | None:
    marker = "prompt="
    if marker not in details:
        return None
    prompt_part = details.split(marker, 1)[1].strip()
    return prompt_part or None


def _extract_user_query_from_context_preview(preview: str) -> str | None:
    if not preview:
        return None
    lines = [line.strip() for line in preview.splitlines() if line.strip()]
    for line in lines:
        if not line.upper().startswith("USER:"):
            continue
        content = line.split(":", 1)[1].strip()
        if content:
            return content
    return None


def _extract_query_from_context_preview_details(details: str) -> str | None:
    parsed = _parse_json_dict(details)
    preview = str(parsed.get("prompt_context_preview") or "")
    return _extract_user_query_from_context_preview(preview)


def _extract_query_from_step(step: dict[str, Any]) -> str | None:
    details = step.get("details")
    if not isinstance(details, str):
        return None
    action = str(step.get("action") or "")
    if action == "request":
        return _extract_query_from_request_details(details)
    if action == "context_preview":
        return _extract_query_from_context_preview_details(details)
    return None


def _extract_query_from_trace_steps(steps: list[dict[str, Any]]) -> str | None:
    for step in reversed(steps):
        query = _extract_query_from_step(step)
        if query:
            return query
    return None


def _extract_response_from_trace_steps(steps: list[dict[str, Any]]) -> str | None:
    for step in reversed(steps):
        if str(step.get("action") or "") != "response":
            continue
        details = step.get("details")
        if not isinstance(details, str):
            continue
        parsed = _parse_json_dict(details)
        response = str(parsed.get("response") or "").strip()
        if response:
            return response
    return None


def _extract_prompt_entities(prompt: str) -> list[dict[str, Any]]:
    tokens = re.findall(r"\w+", prompt, flags=re.UNICODE)
    unique_tokens: list[str] = []
    normalized_set: set[str] = set()
    for token in tokens:
        normalized = token.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in _STOPWORDS or lowered in normalized_set:
            continue
        normalized_set.add(lowered)
        unique_tokens.append(normalized)
    return [
        {
            "id": f"query:{index + 1}",
            "label": label,
            "kind": "query_token",
            "active": index < 3,
        }
        for index, label in enumerate(unique_tokens[:4])
    ]


def _extract_response_entities(
    response_text: str,
    existing_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not response_text:
        return existing_entities
    existing_labels = {entity["label"].lower() for entity in existing_entities}
    words = re.findall(r"\w+", response_text, flags=re.UNICODE)
    response_entities: list[dict[str, Any]] = []
    for word in words:
        label = word.strip()
        lowered = label.lower()
        if len(label) < 4 or lowered in _STOPWORDS or lowered in existing_labels:
            continue
        existing_labels.add(lowered)
        response_entities.append(
            {
                "id": f"response:{len(response_entities) + 1}",
                "label": label,
                "kind": "response_token",
                "active": len(response_entities) < 3,
            }
        )
        if len(existing_entities) + len(response_entities) >= _MAX_ENTITIES:
            break
    return [*existing_entities, *response_entities][:_MAX_ENTITIES]


def _build_context_edges(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for entity in entities[: min(_MAX_EDGES, 6)]:
        edges.append(
            {
                "from": "query",
                "to": entity["id"],
                "label": "context signal",
                "active": True,
            }
        )
    return edges


def _build_answer_evidence_links(
    *,
    answer_text: str,
    entities: list[dict[str, Any]],
    evidence_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not answer_text or not evidence_edges:
        return []
    entity_by_id = {entity["id"]: entity for entity in entities}
    edge_ids = [str(edge.get("id") or "") for edge in evidence_edges]
    fragments = [
        segment.strip()
        for segment in re.split(r"(?<=[.!?])\s+", answer_text)
        if segment.strip()
    ][:_MAX_ANSWER_LINKS]
    links: list[dict[str, Any]] = []
    for index, fragment in enumerate(fragments):
        lowered = fragment.casefold()
        matched_entity_ids = [
            entity["id"]
            for entity in entities
            if entity["label"].casefold() in lowered and entity["label"]
        ]
        matched_edges = [
            str(edge.get("id") or "")
            for edge in evidence_edges
            if edge.get("from") in matched_entity_ids
            or edge.get("to") in matched_entity_ids
        ]
        if not matched_edges:
            matched_edges = edge_ids[:2]
        if not matched_edges:
            continue
        links.append(
            {
                "id": f"link:{index + 1}",
                "fragment": fragment,
                "edge_ids": [edge_id for edge_id in matched_edges if edge_id],
                "entity_ids": [
                    entity_id
                    for entity_id in matched_entity_ids
                    if entity_id in entity_by_id
                ],
            }
        )
    return links


def _build_fallback_entities_from_nodes(nodes_payload: Any) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    if not isinstance(nodes_payload, list):
        return collected
    for node in nodes_payload:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        if not node_id or node_id == "runtime":
            continue
        collected.append(
            {
                "id": node_id,
                "label": str(node.get("label") or node_id),
                "kind": str(node.get("kind") or "entity"),
                "active": True,
            }
        )
        if len(collected) >= _MAX_ENTITIES:
            break
    return collected


def _build_fallback_edges_from_graph(
    *,
    edges_payload: Any,
    entities_payload: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    if not isinstance(edges_payload, list):
        return collected
    entity_ids = {entity["id"] for entity in entities_payload}
    for edge in edges_payload:
        if not isinstance(edge, dict):
            continue
        edge_from = str(edge.get("from") or "")
        edge_to = str(edge.get("to") or "")
        if not edge_from or not edge_to:
            continue
        if edge_from not in entity_ids and edge_to not in entity_ids:
            continue
        collected.append(
            {
                "from": edge_from,
                "to": edge_to,
                "label": str(edge.get("label") or "evidence"),
                "active": True,
            }
        )
        if len(collected) >= _MAX_EDGES:
            break
    return collected


def _build_graph_fallback_payload(
    *,
    prompt: str,
    snapshot: dict[str, Any],
    response_text: str,
) -> dict[str, Any]:
    graph = snapshot.get("graph") if isinstance(snapshot, dict) else None
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    edges = graph.get("edges") if isinstance(graph, dict) else []

    entities = _build_fallback_entities_from_nodes(nodes)
    if not entities:
        entities = _extract_prompt_entities(prompt)

    evidence_edges = _build_fallback_edges_from_graph(
        edges_payload=edges,
        entities_payload=entities,
    )
    if not evidence_edges:
        evidence_edges = _build_context_edges(entities)
    evidence_edges = _assign_edge_ids(evidence_edges)
    active_entity_ids = [entity["id"] for entity in entities if entity.get("active")]
    grounding_score = min(1.0, 0.5 + (0.05 * len(evidence_edges)))
    answer_links = _build_answer_evidence_links(
        answer_text=response_text,
        entities=entities,
        evidence_edges=evidence_edges,
    )
    return {
        "source": "graph_fallback",
        "query": prompt,
        "entities": entities,
        "evidence_edges": evidence_edges,
        "active_entity_ids": active_entity_ids,
        "grounding_score": round(grounding_score, 3),
        "answer_evidence_links": answer_links,
    }


def _build_runtime_trace_payload(
    *,
    prompt: str,
    response_text: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    entities = _extract_entities_from_trace_steps(steps)
    if not entities:
        entities = _extract_prompt_entities(prompt)
    entities = _extract_response_entities(response_text, entities)

    evidence_edges = _extract_edges_from_trace_steps(steps)
    if not evidence_edges:
        evidence_edges = _build_context_edges(entities)
    evidence_edges = _assign_edge_ids(evidence_edges)

    active_entity_ids = _extract_active_entity_ids_from_trace_steps(steps)
    if not active_entity_ids:
        active_entity_ids = [entity["id"] for entity in entities[:3]]

    grounding_score = _extract_grounding_score_from_trace_steps(steps)
    if grounding_score is None:
        grounding_score = min(1.0, 0.6 + (0.03 * len(evidence_edges)))

    answer_links = _build_answer_evidence_links(
        answer_text=response_text,
        entities=entities,
        evidence_edges=evidence_edges,
    )
    return {
        "source": "runtime_trace",
        "query": prompt,
        "entities": entities,
        "evidence_edges": evidence_edges,
        "active_entity_ids": active_entity_ids,
        "grounding_score": round(float(grounding_score), 3),
        "answer_evidence_links": answer_links,
    }


def build_rag_focus_payload(
    *,
    prompt: str,
    snapshot: dict[str, Any],
    process_trace: dict[str, Any] | None,
    response_text: str = "",
) -> dict[str, Any]:
    if not isinstance(process_trace, dict):
        return _build_graph_fallback_payload(
            prompt=prompt,
            snapshot=snapshot,
            response_text=response_text,
        )

    steps_raw = process_trace.get("steps")
    if not isinstance(steps_raw, list):
        return _build_graph_fallback_payload(
            prompt=prompt,
            snapshot=snapshot,
            response_text=response_text,
        )
    trace_steps = [step for step in steps_raw if isinstance(step, dict)]
    if not trace_steps:
        return _build_graph_fallback_payload(
            prompt=prompt,
            snapshot=snapshot,
            response_text=response_text,
        )

    runtime_actions_present = any(
        str(step.get("action") or "") in _TRACE_RUNTIME_ACTIONS for step in trace_steps
    )
    if not runtime_actions_present:
        return _build_graph_fallback_payload(
            prompt=prompt,
            snapshot=snapshot,
            response_text=response_text,
        )

    query_from_trace = _extract_query_from_trace_steps(trace_steps)
    response_from_trace = _extract_response_from_trace_steps(trace_steps)
    normalized_prompt = query_from_trace or prompt
    normalized_response = response_from_trace or response_text
    return _build_runtime_trace_payload(
        prompt=normalized_prompt,
        response_text=normalized_response,
        steps=trace_steps,
    )
