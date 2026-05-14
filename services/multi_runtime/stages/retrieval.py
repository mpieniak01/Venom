"""Retrieval hook stage for multi_runtime pipeline."""

from __future__ import annotations

from time import perf_counter

from venom_core.memory.vector_store import VectorStore

from .base import StageContext


class RetrievalStage:
    name = "retrieval"

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

        try:
            results = VectorStore().search(text, limit=3)
        except Exception as exc:
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.add_degradation(
                f"retrieval unavailable: {type(exc).__name__}"
            )
            context.diagnostics.push_trace(self.name, started, outcome="fallback")
            return

        snippets = [
            str(item.get("text", "")).strip()
            for item in results
            if str(item.get("text", "")).strip()
        ]
        if not snippets:
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.push_trace(self.name, started, outcome="empty")
            return

        limited = snippets[:2]
        context.state["retrieval_context"] = "\n\n".join(limited)
        context.diagnostics.retrieval_used = True
        context.diagnostics.retrieval_context_items = len(limited)
        context.diagnostics.push_trace(self.name, started, outcome="ok")
