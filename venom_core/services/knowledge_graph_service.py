"""Knowledge graph helper services extracted from API router."""

from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
from threading import Lock
from typing import Any

from venom_core.memory.graph_store import CodeGraphStore

NODE_TYPE_FILE = "file"
NODE_TYPE_CLASS = "class"
NODE_TYPE_FUNCTION = "function"
NODE_TYPE_METHOD = "method"

_graph_view_counters: Counter[str] = Counter()
_graph_view_counters_lock = Lock()


def normalize_graph_file_path(file_path: str) -> str:
    normalized = file_path.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("invalid_file_path")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("invalid_file_path")
    return str(path)


def resolve_node_presentation(
    node_id: str, node_data: dict[str, Any]
) -> tuple[str, str]:
    node_type = node_data.get("type", "unknown")
    node_name = node_data.get("name", node_id)
    if node_type == NODE_TYPE_FILE:
        return "file", node_data.get("path", node_name)
    if node_type == NODE_TYPE_CLASS:
        file_path = node_data.get("file", "")
        category = (
            "agent"
            if "agents" in file_path or node_data.get("is_agent", False)
            else "class"
        )
        return category, node_name
    if node_type in (NODE_TYPE_FUNCTION, NODE_TYPE_METHOD):
        return "function", node_name
    return "file", node_name


def build_graph_nodes(graph_store: CodeGraphStore, limit: int) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for node_id, node_data in graph_store.graph.nodes(data=True):
        category, label = resolve_node_presentation(node_id, node_data)
        nodes.append(
            {
                "data": {
                    "id": node_id,
                    "label": label,
                    "type": category,
                    "original_type": node_data.get("type", "unknown"),
                    "properties": node_data,
                }
            }
        )
        if len(nodes) >= limit:
            break
    return nodes


def build_graph_edges(
    graph_store: CodeGraphStore, allowed_ids: set[str]
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    edge_id = 0
    for source, target, edge_data in graph_store.graph.edges(data=True):
        if allowed_ids and (source not in allowed_ids or target not in allowed_ids):
            continue
        edge_type = edge_data.get("type", "RELATED")
        edges.append(
            {
                "data": {
                    "id": f"e{edge_id}",
                    "source": source,
                    "target": target,
                    "type": edge_type,
                    "label": edge_type,
                }
            }
        )
        edge_id += 1
    return edges


def increment_graph_view_counter(view: str) -> None:
    with _graph_view_counters_lock:
        _graph_view_counters[view] += 1


def graph_view_counter_snapshot() -> dict[str, int]:
    with _graph_view_counters_lock:
        return dict(_graph_view_counters)
