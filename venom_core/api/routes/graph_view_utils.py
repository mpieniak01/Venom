"""Wspólne transformacje widoku grafu (overview/focus/full) dla endpointów API."""

from collections import deque
from typing import Any


def _node_id(node: dict[str, Any]) -> str:
    return str(node.get("data", {}).get("id", ""))


def _edge_nodes(edge: dict[str, Any]) -> tuple[str, str]:
    data = edge.get("data", {})
    return str(data.get("source", "")), str(data.get("target", ""))


def _edge_subset_by_allowed(
    edges: list[dict[str, Any]], allowed: set[str]
) -> list[dict[str, Any]]:
    return [
        edge
        for edge in edges
        if _edge_nodes(edge)[0] in allowed and _edge_nodes(edge)[1] in allowed
    ]


def _focus_node_ids(
    edges: list[dict[str, Any]], seed_id: str, max_hops: int
) -> set[str]:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        source, target = _edge_nodes(edge)
        if not source or not target:
            continue
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)

    visited: set[str] = {seed_id}
    queue: deque[tuple[str, int]] = deque([(seed_id, 0)])
    while queue:
        node_id, hops = queue.popleft()
        if hops >= max_hops:
            continue
        for neighbour in adjacency.get(node_id, set()):
            if neighbour in visited:
                continue
            visited.add(neighbour)
            queue.append((neighbour, hops + 1))
    return visited


def _remove_isolates(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    connected: set[str] = set()
    for edge in edges:
        source, target = _edge_nodes(edge)
        if source:
            connected.add(source)
        if target:
            connected.add(target)

    filtered_nodes = [node for node in nodes if _node_id(node) in connected]
    allowed = {_node_id(node) for node in filtered_nodes}
    filtered_edges = _edge_subset_by_allowed(edges, allowed)
    return filtered_nodes, filtered_edges


def apply_graph_view(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    view: str,
    seed_id: str | None,
    max_hops: int,
    include_isolates: bool,
    limit_nodes: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Aplikuje wspólną semantykę view-mode dla grafu."""
    current_nodes = list(nodes)
    current_edges = list(edges)

    if view == "overview":
        cap = limit_nodes if limit_nodes is not None else min(len(current_nodes), 200)
        current_nodes = current_nodes[:cap]
        allowed = {_node_id(node) for node in current_nodes}
        current_edges = _edge_subset_by_allowed(current_edges, allowed)
    elif view == "focus" and current_nodes:
        resolved_seed = seed_id or _node_id(current_nodes[0])
        focus_ids = _focus_node_ids(current_edges, resolved_seed, max_hops)
        current_nodes = [node for node in current_nodes if _node_id(node) in focus_ids]
        allowed = {_node_id(node) for node in current_nodes}
        current_edges = _edge_subset_by_allowed(current_edges, allowed)
        if limit_nodes is not None and limit_nodes > 0:
            current_nodes = current_nodes[:limit_nodes]
            allowed = {_node_id(node) for node in current_nodes}
            current_edges = _edge_subset_by_allowed(current_edges, allowed)

    if not include_isolates:
        current_nodes, current_edges = _remove_isolates(current_nodes, current_edges)

    return current_nodes, current_edges
