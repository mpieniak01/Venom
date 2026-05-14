"""Retrieval hook stage for multi_runtime pipeline."""

from __future__ import annotations

import asyncio
from time import perf_counter

from venom_core.memory.graph_rag_service import GraphRAGService
from venom_core.memory.vector_store import VectorStore

from ..retrieval_policy_resolver import RetrievalPolicyResolver
from .base import StageContext


class RetrievalStage:
    name = "retrieval"

    def __init__(self, resolver: RetrievalPolicyResolver | None = None):
        self._resolver = resolver or RetrievalPolicyResolver()

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        mode = str(context.state["policy"].retrieval_mode)

        if mode == "off":
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.retrieval_context_items = 0
            context.diagnostics.retrieval_route = "none"
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        text = str(context.text_content or "").strip()
        route = context.state.get("route")
        primary_modality = getattr(route, "primary_modality", None)
        decision = self._resolver.resolve(
            text=text,
            mode=mode,
            primary_modality=primary_modality,
            economy_mode=context.state["policy"].economy_mode,
        )
        context.state["retrieval_policy_decision"] = decision

        if not decision.should_use:
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.retrieval_context_items = 0
            context.diagnostics.retrieval_route = "none"
            if "economy" in str(decision.reason or "").lower():
                context.diagnostics.economy_mode_activated = True
                context.diagnostics.add_degradation(str(decision.reason or ""))
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        route_name = decision.route_hint
        retrieval_context = ""
        try:
            if route_name == "graph":
                graph_result = asyncio.run(
                    GraphRAGService().local_search(text, max_hops=2, limit=4)
                )
                graph_result = str(graph_result or "").strip()
                if graph_result and "Nie znaleziono" not in graph_result:
                    retrieval_context = graph_result[:2400]
                    context.diagnostics.retrieval_context_items = 1
                else:
                    route_name = "vector_fallback"
            if not retrieval_context:
                results = VectorStore().search(text, limit=3)
                snippets = [
                    str(item.get("text", "")).strip()
                    for item in results
                    if str(item.get("text", "")).strip()
                ]
                limited = snippets[:2]
                retrieval_context = "\n\n".join(limited)
                context.diagnostics.retrieval_context_items = len(limited)
        except Exception as exc:
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.retrieval_context_items = 0
            context.diagnostics.retrieval_route = "none"
            context.diagnostics.add_degradation(
                f"retrieval unavailable: {type(exc).__name__}"
            )
            context.diagnostics.push_trace(self.name, started, outcome="fallback")
            return

        if not retrieval_context:
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.retrieval_context_items = 0
            context.diagnostics.retrieval_route = route_name
            context.diagnostics.push_trace(self.name, started, outcome="empty")
            return

        context.state["retrieval_context"] = retrieval_context
        context.diagnostics.retrieval_used = True
        context.diagnostics.retrieval_route = route_name
        context.diagnostics.push_trace(self.name, started, outcome="ok")
