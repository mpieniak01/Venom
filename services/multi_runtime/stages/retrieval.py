"""Retrieval hook stage for multi_runtime pipeline."""

from __future__ import annotations

import asyncio
from time import perf_counter

from venom_core.memory.graph_rag_service import GraphRAGService
from venom_core.memory.vector_store import VectorStore

from .base import StageContext


class RetrievalStage:
    name = "retrieval"

    @staticmethod
    def _should_use_graph(query: str) -> bool:
        normalized = query.lower()
        return any(
            token in normalized
            for token in (
                "związek",
                "zwiazek",
                "powiaz",
                "relac",
                "między",
                "miedzy",
                "between",
                "relationship",
                "compare",
                "porown",
            )
        )

    def _should_use_auto(self, text: str, context: StageContext) -> bool:
        normalized = text.lower()
        route = context.state.get("route")
        if getattr(route, "primary_modality", None) == "image":
            return False
        return (
            "?" in text
            or len(text) >= 48
            or any(
                token in normalized
                for token in (
                    "co to",
                    "dlaczego",
                    "jak",
                    "kiedy",
                    "gdzie",
                    "przypomnij",
                    "znajd",
                    "sprawdz",
                    "explain",
                    "why",
                    "what",
                )
            )
        )

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        mode = str(context.state["policy"].retrieval_mode)

        if mode == "off":
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        text = str(context.text_content or "").strip()
        should_use = mode == "always" or (
            mode == "auto" and self._should_use_auto(text, context)
        )
        if not should_use:
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        if context.state["policy"].economy_mode == "auto" and mode == "auto":
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.economy_mode_activated = True
            context.diagnostics.add_degradation("economy_mode skipped auto retrieval")
            context.diagnostics.push_trace(self.name, started, outcome="degraded")
            return

        route = "vector"
        retrieval_context = ""
        try:
            if self._should_use_graph(text):
                route = "graph"
                graph_result = asyncio.run(
                    GraphRAGService().local_search(text, max_hops=2, limit=4)
                )
                graph_result = str(graph_result or "").strip()
                if graph_result and "Nie znaleziono" not in graph_result:
                    retrieval_context = graph_result[:2400]
                    context.diagnostics.retrieval_context_items = 1
                else:
                    route = "vector_fallback"
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
            context.diagnostics.add_degradation(
                f"retrieval unavailable: {type(exc).__name__}"
            )
            context.diagnostics.push_trace(self.name, started, outcome="fallback")
            return

        if not retrieval_context:
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.push_trace(self.name, started, outcome="empty")
            return

        context.state["retrieval_context"] = retrieval_context
        context.diagnostics.retrieval_used = True
        context.diagnostics.retrieval_route = route
        context.diagnostics.push_trace(self.name, started, outcome="ok")
