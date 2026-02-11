from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID, uuid4

from venom_core.config import SETTINGS
from venom_core.core.hidden_prompts import build_hidden_prompts_context
from venom_core.core.models import TaskRequest
from venom_core.core.orchestrator.constants import (
    MAX_CONTEXT_CHARS,
    MAX_HIDDEN_PROMPTS_IN_CONTEXT,
)
from venom_core.core.retrieval_policy import get_policy_manager
from venom_core.core.slash_commands import parse_slash_command, resolve_forced_intent
from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger
from venom_core.utils.text import trim_to_char_limit

if TYPE_CHECKING:
    from venom_core.core.orchestrator.orchestrator_core import Orchestrator

logger = get_logger(__name__)


def format_extra_context(extra_context: Any) -> str:
    """Formatuje dodatkowy kontekst do czytelnego bloku tekstu."""
    sections: list[str] = []

    def add_section(label: str, items: Optional[list[str]]) -> None:
        cleaned = [item.strip() for item in (items or []) if item and item.strip()]
        if not cleaned:
            return
        section = [f"{label}:"]
        section.extend(f"- {item}" for item in cleaned)
        sections.append("\n".join(section))

    add_section("Pliki", extra_context.files)
    add_section("Linki", extra_context.links)
    add_section("Ścieżki", extra_context.paths)
    add_section("Notatki", extra_context.notes)

    return "\n\n".join(sections)


class ContextBuilder:
    """Handles context preparation, including slash commands, history, and hidden prompts."""

    def __init__(self, orch: "Orchestrator"):
        self.orch = orch

    async def preprocess_request(self, task_id: UUID, request: TaskRequest) -> None:
        """Parsuje slash commands i aktualizuje request/context."""
        forced_tool = request.forced_tool
        forced_provider = request.forced_provider
        forced_intent = request.forced_intent

        if not forced_tool and not forced_provider:
            parsed = parse_slash_command(request.content)
            if parsed and parsed.cleaned != request.content:
                request.content = parsed.cleaned
                forced_tool = parsed.forced_tool
                forced_provider = parsed.forced_provider
                if not forced_intent:
                    forced_intent = parsed.forced_intent

                if parsed.session_reset:
                    await self._handle_session_reset(task_id, request)

                # Update local variables to reflect changes in request
                request.forced_tool = forced_tool
                request.forced_provider = forced_provider
                request.forced_intent = forced_intent

        if forced_tool and not forced_intent:
            forced_intent = resolve_forced_intent(forced_tool)
            request.forced_intent = forced_intent

        if forced_tool or forced_provider or forced_intent:
            self._update_forced_route_context(
                task_id, forced_tool, forced_provider, forced_intent
            )

    async def _handle_session_reset(self, task_id: UUID, request: TaskRequest) -> None:
        await asyncio.sleep(0)
        request.session_id = request.session_id or f"session-{uuid4()}"
        self.orch.state_manager.update_context(
            task_id,
            {
                "session_history": [],
                "session_history_full": [],
                "session_summary": None,
            },
        )
        if self.orch.session_handler.session_store and request.session_id:
            try:
                self.orch.session_handler.session_store.clear_session(
                    request.session_id
                )
            except Exception as exc:
                logger.warning("Nie udalo sie wyczyscic SessionStore: %s", exc)
        self.orch.state_manager.add_log(
            task_id, "Wyczyszczono kontekst sesji (/clear)."
        )

    def _update_forced_route_context(
        self,
        task_id: UUID,
        tool: Optional[str],
        provider: Optional[str],
        intent: Optional[str],
    ) -> None:
        self.orch.state_manager.update_context(
            task_id,
            {
                "forced_route": {
                    "tool": tool,
                    "provider": provider,
                    "intent": intent,
                }
            },
        )
        if self.orch.request_tracer:
            if tool or provider:
                self.orch.request_tracer.set_forced_route(
                    task_id,
                    forced_tool=tool,
                    forced_provider=provider,
                    forced_intent=intent,
                )
            self.orch.request_tracer.add_step(
                task_id,
                "DecisionGate",
                "forced_route",
                status="ok",
                details=f"tool={tool}, provider={provider}, intent={intent}",
            )

    async def build_context(
        self, task_id: UUID, request: TaskRequest, fast_path: bool
    ) -> str:
        """Buduje pełny kontekst (prompt + historia + extra context)."""
        full_context = await self.prepare_context(task_id, request)
        session_block = self.orch._build_session_context_block(
            request,
            task_id,
            include_memory=not fast_path,
        )

        if session_block:
            full_context = session_block + "\n\n" + full_context

        # Trimming
        full_context, trimmed = trim_to_char_limit(full_context, MAX_CONTEXT_CHARS)
        if trimmed:
            self.orch.state_manager.add_log(
                task_id,
                f"Obcięto kontekst do {MAX_CONTEXT_CHARS} znaków (historia/przygotowanie promptu).",
            )

        runtime_info = get_active_llm_runtime()
        runtime_limit = self.orch._get_runtime_context_char_limit(runtime_info)
        if runtime_limit < MAX_CONTEXT_CHARS:
            full_context, trimmed = trim_to_char_limit(full_context, runtime_limit)
            if trimmed:
                self.orch.state_manager.add_log(
                    task_id,
                    f"Obcięto kontekst do {runtime_limit} znaków (limit runtime).",
                )

        return full_context

    async def prepare_context(self, task_id: UUID, request: TaskRequest) -> str:
        """Przygotowuje kontekst zadania."""
        context = request.content

        if request.images:
            self.orch.state_manager.add_log(
                task_id, f"Analizuję {len(request.images)} obrazów..."
            )

            for i, image in enumerate(request.images, 1):
                try:
                    description = await self.orch.eyes.analyze_image(
                        image,
                        prompt=(
                            "Opisz szczegółowo co widzisz na tym obrazie, "
                            "szczególnie zwróć uwagę na tekst, błędy lub problemy."
                        ),
                    )
                    context += f"\n\n[OBRAZ {i}]: {description}"
                    self.orch.state_manager.add_log(
                        task_id, f"Obraz {i} przeanalizowany pomyślnie"
                    )
                except Exception as exc:
                    logger.error("Błąd podczas analizy obrazu %s: %s", i, exc)
                    self.orch.state_manager.add_log(
                        task_id, f"Nie udało się przeanalizować obrazu {i}: {exc}"
                    )

        if request.extra_context:
            extra_block = self.format_extra_context(request.extra_context)
            if extra_block:
                context += f"\n\n[DODATKOWE DANE]\n{extra_block}"

        return context

    async def enrich_context_with_lessons(
        self, task_id: UUID, context: str, intent: Optional[str] = None
    ) -> str:
        """
        Dodaje lekcje (Lessons) do kontekstu.
        
        Args:
            task_id: ID zadania
            context: Kontekst do wzbogacenia
            intent: Opcjonalnie intencja dla RAG Boost (Phase B)
        
        Returns:
            Wzbogacony kontekst
            
        Note:
            Phase B currently applies only lessons_limit dynamically.
            vector_limit and max_hops are recorded in telemetry but not
            functionally applied (reserved for Phase C when orchestrator-driven
            GraphRAG searches are added).
        """
        # Determine lessons limit based on intent (Phase B: RAG Retrieval Boost)
        limit = None
        boost_metadata = {}
        
        if intent:
            try:
                policy_manager = get_policy_manager()
                policy = policy_manager.get_policy(intent)
                limit = policy.lessons_limit
                
                # Build telemetry metadata
                boost_metadata = {
                    "retrieval_boost.enabled": policy_manager.enabled,
                    "retrieval_boost.mode": policy.mode,
                    "retrieval_boost.intent": intent,
                    "retrieval_boost.lessons_limit": policy.lessons_limit,
                    "retrieval_boost.vector_limit": policy.vector_limit,
                    "retrieval_boost.max_hops": policy.max_hops,
                }
                
                # Log RAG boost telemetry if enabled
                if policy.mode == "boost":
                    self.orch.state_manager.add_log(
                        task_id,
                        f"📊 RAG Boost: aktywny dla {intent} (lessons_limit={limit})"
                    )
                    # Store telemetry in context
                    self.orch.state_manager.update_context(task_id, boost_metadata)
                    
                    # Add to tracer if available
                    if self.orch.request_tracer:
                        self.orch.request_tracer.add_step(
                            task_id,
                            "RAGBoost",
                            "policy_applied",
                            status="ok",
                            details=json.dumps(boost_metadata, ensure_ascii=False),
                        )
            except Exception as e:
                logger.warning(f"Failed to get retrieval policy for intent {intent}: {e}")
        
        return await self.orch.lessons_manager.add_lessons_to_context(
            task_id, context, limit=limit
        )

    def format_extra_context(self, extra_context: Any) -> str:
        """Formatuje dodatkowy kontekst do czytelnego bloku tekstu (delegacja)."""
        return format_extra_context(extra_context)

    async def add_hidden_prompts(self, task_id: UUID, context: str, intent: str) -> str:
        """Dodaje hidden prompts do kontekstu."""
        await asyncio.sleep(0)
        runtime_info = get_active_llm_runtime()
        runtime_limit = self.orch._get_runtime_context_char_limit(runtime_info)
        include_hidden = True
        max_ctx_raw = getattr(SETTINGS, "VLLM_MAX_MODEL_LEN", None)
        max_ctx = int(max_ctx_raw) if isinstance(max_ctx_raw, int) else 0
        if runtime_info.provider == "vllm" and max_ctx and max_ctx <= 512:
            include_hidden = False

        hidden_context = (
            build_hidden_prompts_context(
                intent=intent, limit=MAX_HIDDEN_PROMPTS_IN_CONTEXT
            )
            if include_hidden
            else ""
        )

        if hidden_context:
            context = hidden_context + "\n\n" + context

        if hidden_context:
            hidden_prompts_log = f"Dołączono {len(hidden_context.splitlines()) // 3} hidden prompts do kontekstu"
        elif not include_hidden:
            hidden_prompts_log = "Pominięto hidden prompts (mały kontekst vLLM)"
        else:
            hidden_prompts_log = (
                "Nie znaleziono pasujących hidden prompts dla tej intencji."
            )
        self.orch.state_manager.add_log(task_id, hidden_prompts_log)

        if runtime_limit < MAX_CONTEXT_CHARS:
            context, trimmed = trim_to_char_limit(context, runtime_limit)
            if trimmed:
                self.orch.state_manager.add_log(
                    task_id,
                    f"Obcięto kontekst do {runtime_limit} znaków (limit runtime).",
                )

        if self.orch.request_tracer:
            self.orch.request_tracer.add_step(
                task_id,
                "DecisionGate",
                "hidden_prompts",
                status="ok",
                details=f"Hidden prompts: {MAX_HIDDEN_PROMPTS_IN_CONTEXT}",
            )

        return context

    def is_perf_test_prompt(self, content: str) -> bool:
        """Sprawdź, czy treść zadania pochodzi z testów wydajności."""
        default_keywords = ("perf", "latency", "benchmark")
        keywords = getattr(self.orch.intent_manager, "PERF_TEST_KEYWORDS", None)
        if not isinstance(keywords, (list, tuple, set)):
            keywords = default_keywords
        normalized = (content or "").lower()
        return any(keyword in normalized for keyword in keywords)

    async def complete_perf_test_task(self, task_id: UUID) -> None:
        """Zakończ zadanie testu wydajności."""
        from venom_core.core import metrics as metrics_module
        from venom_core.core.models import TaskStatus
        from venom_core.core.tracer import TraceStatus

        result_text = "✅ Backend perf pipeline OK"
        self.orch.state_manager.add_log(
            task_id,
            "⚡ Wykryto prompt testu wydajności – pomijam kosztowne agentów i zamykam zadanie natychmiast.",
        )
        await self.orch.state_manager.update_status(
            task_id, TaskStatus.COMPLETED, result=result_text
        )
        self.orch.state_manager.add_log(
            task_id, f"Zakończono test wydajności: {get_utc_now_iso()}"
        )

        if self.orch.request_tracer:
            self.orch.request_tracer.update_status(task_id, TraceStatus.COMPLETED)
            self.orch.request_tracer.add_step(
                task_id,
                "System",
                "perf_test_shortcut",
                status="ok",
                details="Perf test zakończony bez agentów",
            )

        collector = metrics_module.metrics_collector
        if collector:
            collector.increment_task_completed()

        await self.orch._broadcast_event(
            event_type="TASK_COMPLETED",
            message=f"Zadanie {task_id} zakończone (perf test)",
            data={"task_id": str(task_id), "result_length": len(result_text)},
        )

        logger.info("Zadanie %s zakończone w trybie perf-test", task_id)
