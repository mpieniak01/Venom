"""Policy resolver for retrieval routing in the multi_runtime pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RetrievalRoute = Literal["graph", "vector"]


@dataclass(slots=True)
class RetrievalPolicyDecision:
    mode: str
    should_use: bool
    route_hint: RetrievalRoute
    reason: str | None = None


class RetrievalPolicyResolver:
    """Resolve whether retrieval should run and which route should be preferred."""

    _graph_hints = (
        "związek",
        "zwiazek",
        "powiaz",
        "powiąz",
        "relac",
        "między",
        "miedzy",
        "between",
        "relationship",
        "compare",
        "porown",
        "porówn",
        "zależ",
        "zalezn",
        "dependency",
        "edge",
        "graph",
    )

    _vector_hints = (
        "co to",
        "dlaczego",
        "jak",
        "kiedy",
        "gdzie",
        "przypomnij",
        "znajd",
        "sprawdz",
        "wyjaś",
        "wyjas",
        "explain",
        "why",
        "what",
        "how",
    )

    def _should_use_graph(self, normalized_text: str) -> bool:
        return any(token in normalized_text for token in self._graph_hints)

    def _should_use_auto(self, normalized_text: str) -> bool:
        return (
            "?" in normalized_text
            or len(normalized_text) >= 48
            or any(token in normalized_text for token in self._vector_hints)
        )

    def resolve(
        self,
        *,
        text: str,
        mode: str,
        primary_modality: str | None,
        economy_mode: str | None,
        request_overrides: dict[str, Any] | None = None,
    ) -> RetrievalPolicyDecision:
        normalized_text = str(text or "").strip().lower()
        normalized_mode = str(mode or "off").strip().lower()
        modality = str(primary_modality or "text").strip().lower()
        normalized_economy = str(economy_mode or "off").strip().lower()

        if normalized_mode == "off":
            return RetrievalPolicyDecision(
                mode=normalized_mode,
                should_use=False,
                route_hint="vector",
                reason="retrieval disabled",
            )

        if not normalized_text:
            return RetrievalPolicyDecision(
                mode=normalized_mode,
                should_use=False,
                route_hint="vector",
                reason="empty text content",
            )

        if modality == "image" and normalized_mode != "always":
            return RetrievalPolicyDecision(
                mode=normalized_mode,
                should_use=False,
                route_hint="vector",
                reason="image-only request skips auto retrieval",
            )

        if normalized_mode == "auto":
            if normalized_economy == "auto":
                return RetrievalPolicyDecision(
                    mode=normalized_mode,
                    should_use=False,
                    route_hint="vector",
                    reason="economy mode suppresses auto retrieval",
                )
            if not self._should_use_auto(normalized_text):
                return RetrievalPolicyDecision(
                    mode=normalized_mode,
                    should_use=False,
                    route_hint="vector",
                    reason="auto retrieval heuristics did not match",
                )

        preferred_route: RetrievalRoute = (
            "graph" if self._should_use_graph(normalized_text) else "vector"
        )
        return RetrievalPolicyDecision(
            mode=normalized_mode,
            should_use=True,
            route_hint=preferred_route,
            reason=(
                "graph relationship query"
                if preferred_route == "graph"
                else "vector semantic query"
            ),
        )
