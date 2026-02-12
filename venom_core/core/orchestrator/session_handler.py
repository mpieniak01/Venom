"""Obsługa kontekstu sesji i historii w Orchestrator."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol
from uuid import UUID

import httpx

from venom_core.config import SETTINGS
from venom_core.core.knowledge_contract import KnowledgeKind
from venom_core.core.knowledge_ttl import compute_expires_at, resolve_ttl_days
from venom_core.core.models import ContextUsed, TaskRequest
from venom_core.memory.memory_skill import MemorySkill
from venom_core.services.session_store import SessionStore
from venom_core.services.translation_service import translation_service
from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger
from venom_core.utils.text import trim_to_char_limit

from .constants import (
    DEFAULT_USER_ID,
    HISTORY_SUMMARY_TRIGGER_CHARS,
    HISTORY_SUMMARY_TRIGGER_MSGS,
    SESSION_FULL_HISTORY_LIMIT,
    SESSION_HISTORY_LIMIT,
    SUMMARY_MAX_CHARS,
    SUMMARY_MODEL_MAX_TOKENS,
    SUMMARY_STRATEGY_DEFAULT,
)

if TYPE_CHECKING:
    from venom_core.core.models import VenomTask
    from venom_core.core.state_manager import StateManager
    from venom_core.core.tracer import RequestTracer

logger = get_logger(__name__)


class MemoryStoreLike(Protocol):
    def search(
        self,
        query: str,
        limit: int = 3,
        collection_name: Optional[str] = None,
    ): ...

    def upsert(self, text: str, metadata: Dict[str, Any], **kwargs: Any) -> Any: ...


class SessionHandler:
    """Zarządza kontekstem sesji, historią i pamięcią."""

    def __init__(
        self,
        state_manager: "StateManager",
        memory_skill: MemorySkill,
        session_store: Optional[SessionStore] = None,
        testing_mode: bool = False,
        request_tracer: Optional["RequestTracer"] = None,
    ):
        """
        Inicjalizacja SessionHandler.

        Args:
            state_manager: Menedżer stanu zadań
            memory_skill: Skill zarządzający pamięcią wektorową
            session_store: Magazyn historii sesji (źródło prawdy)
            testing_mode: Czy uruchomiony w trybie testowym
            request_tracer: Opcjonalny tracer do śledzenia przepływu
        """
        self.state_manager = state_manager
        self.memory_skill = memory_skill
        self.session_store = session_store
        self._testing_mode = testing_mode
        self.request_tracer = request_tracer

    def persist_session_context(self, task_id: UUID, request: TaskRequest) -> None:
        """Zapisuje metadane sesji i preferencji (jeśli dostarczone)."""
        session_context = {
            "session_id": request.session_id,
            "preference_scope": request.preference_scope,
            "tone": request.tone,
            "style_notes": request.style_notes,
            "preferred_language": request.preferred_language,
        }
        filtered = {k: v for k, v in session_context.items() if v}
        if not filtered:
            return
        try:
            self.state_manager.update_context(task_id, {"session": filtered})
            task = self.state_manager.get_task(task_id)
            if task and isinstance(getattr(task, "context_history", {}), dict):
                task.context_history["session"] = filtered
            self.state_manager.add_log(
                task_id,
                f"Sesja: {filtered.get('session_id') or 'brak'}, scope={filtered.get('preference_scope') or 'default'}",
            )
        except Exception as exc:  # pragma: no cover - log only
            logger.warning(f"Nie udało się zapisać kontekstu sesji: {exc}")

    def append_session_history(
        self,
        task_id: UUID,
        role: str,
        content: str,
        session_id: Optional[str],
        policy_blocked: bool = False,
        reason_code: Optional[str] = None,
        user_message: Optional[str] = None,
    ) -> None:
        """Dodaje wpis do historii sesji (ograniczonej do SESSION_HISTORY_LIMIT)."""
        if not content:
            return
        try:
            task = self.state_manager.get_task(task_id)
            if not task:
                return
            if not isinstance(getattr(task, "context_history", {}), dict):
                task.context_history = {}
            short_content = content
            was_trimmed = False  # pełny tekst w historii (bez placeholdera)

            history: List[Dict[str, Any]] = (
                task.context_history.get("session_history") or []
            )[:]
            full_history: List[Dict[str, Any]] = (
                task.context_history.get("session_history_full") or []
            )

            entry: Dict[str, object] = {
                "role": role,
                "content": short_content,
                "session_id": session_id,
                "request_id": str(task_id),
                "timestamp": get_utc_now_iso(),
            }
            if was_trimmed:
                entry["original_length"] = len(content)

            # Add policy fields if present
            if policy_blocked:
                entry["policy_blocked"] = policy_blocked
            if reason_code:
                entry["reason_code"] = reason_code
            if user_message:
                entry["user_message"] = user_message

            history.append(entry)
            full_history.append(entry)

            trimmed = history[-SESSION_HISTORY_LIMIT:]
            trimmed_full = full_history[-SESSION_FULL_HISTORY_LIMIT:]
            task.context_history["session_history"] = trimmed
            task.context_history["session_history_full"] = trimmed_full
            if session_id and self.session_store:
                self.session_store.append_message(
                    session_id,
                    entry,
                    knowledge_metadata=self._build_session_knowledge_metadata(
                        kind=KnowledgeKind.SESSION_MESSAGE,
                        session_id=session_id,
                        request_id=str(task_id),
                        created_at=str(entry["timestamp"]),
                    ),
                )
            self.state_manager.update_context(
                task_id,
                {
                    "session_history": trimmed,
                    "session_history_full": trimmed_full,
                },
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Nie udało się zaktualizować historii sesji: {exc}")

    def build_session_context_block(
        self,
        request: TaskRequest,
        task_id: UUID,
        include_memory: bool = True,
    ) -> str:
        """Buduje blok kontekstu sesji (metadane + historia)."""
        parts: List[str] = []
        meta_block = self._build_session_meta_block(request)
        if meta_block:
            parts.append(meta_block)

        try:
            history_block = self._build_session_history_block(
                request, task_id, include_memory, parts
            )
            if history_block:
                parts.append(history_block)
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Nie udało się zbudować historii sesji: {exc}")

        return "\n\n".join(parts).strip()

    def _build_session_meta_block(self, request: TaskRequest) -> str:
        session_id = request.session_id
        scope = request.preference_scope or "default"
        tone = request.tone
        style_notes = request.style_notes
        preferred_language = request.preferred_language

        meta_lines: List[str] = []
        if session_id:
            meta_lines.append(f"ID sesji: {session_id}")
        meta_lines.append(f"Zakres preferencji: {scope}")
        if tone:
            meta_lines.append(f"Ton: {tone}")
        if style_notes:
            meta_lines.append(f"Styl: {style_notes}")
        if preferred_language:
            meta_lines.append(f"Preferowany język: {preferred_language}")
        return "[KONTEKST SESJI]\n" + "\n".join(meta_lines) if meta_lines else ""

    def _build_session_history_block(
        self,
        request: TaskRequest,
        task_id: UUID,
        include_memory: bool,
        parts: list[str],
    ) -> str:
        task = self.state_manager.get_task(task_id)
        if not task or not isinstance(getattr(task, "context_history", {}), dict):
            return ""

        session_id = request.session_id
        if not self._testing_mode:
            self._ensure_session_summary(task_id, task)
        summary, history = self._load_session_summary_and_history(task, session_id)
        summary = self._ensure_summary_if_needed(
            request, task_id, session_id, summary, history
        )
        if summary:
            parts.append("[STRESZCZENIE SESJI]\n" + summary)
        if not self._testing_mode and include_memory:
            self._attach_memory_block(task_id, task, request, history, parts)
        return self._format_session_history_block(history)

    def _ensure_summary_if_needed(
        self,
        request: TaskRequest,
        task_id: UUID,
        session_id: Optional[str],
        summary: Optional[str],
        history: list[Dict[str, Any]],
    ) -> Optional[str]:
        if summary or not history or not self._should_generate_summary(request):
            return summary
        summary = self._heuristic_summary(history)
        self.state_manager.update_context(task_id, {"session_summary": summary})
        if session_id and self.session_store:
            self.session_store.set_summary(
                session_id,
                summary,
                knowledge_metadata=self._build_session_knowledge_metadata(
                    kind=KnowledgeKind.SESSION_SUMMARY,
                    session_id=session_id,
                    request_id=str(task_id),
                    created_at=get_utc_now_iso(),
                ),
            )
        return summary

    def _format_session_history_block(self, history: list[Dict[str, Any]]) -> str:
        if not history:
            return ""
        lines = []
        for entry in history[-SESSION_HISTORY_LIMIT:]:
            role = entry.get("role", "user")
            msg = entry.get("content", "")
            lines.append(f"{role}: {msg}")
        return "[HISTORIA SESJI]\n" + "\n".join(lines)

    def _load_session_summary_and_history(
        self, task: "VenomTask", session_id: Optional[str]
    ) -> tuple[Optional[str], list[Dict[str, Any]]]:
        summary = None
        history: list[Dict[str, Any]] = []
        if session_id and self.session_store:
            summary = self.session_store.get_summary(session_id)
            history = self.session_store.get_history(session_id, SESSION_HISTORY_LIMIT)
        if not summary:
            summary = task.context_history.get("session_summary")
        if not history:
            history = task.context_history.get("session_history") or []
        return summary, history

    def _attach_memory_block(
        self,
        task_id: UUID,
        task: "VenomTask",
        request: TaskRequest,
        history: list[Dict[str, Any]],
        parts: list[str],
    ) -> None:
        if not self._should_include_memory(request, len(history)):
            return
        memory_block, memory_ids = self._retrieve_relevant_memory(
            request,
            task.context_history.get("session", {}).get("session_id"),
        )
        if memory_block:
            parts.append("[PAMIĘĆ]\n" + memory_block)
        if memory_ids:
            self._update_context_used_memory_entries(task_id, task, memory_ids)

    def _update_context_used_memory_entries(
        self, task_id: UUID, task: "VenomTask", memory_ids: list[str]
    ) -> None:
        current_used = task.context_used
        if isinstance(current_used, dict):
            try:
                task.context_used = ContextUsed(
                    lessons=current_used.get("lessons", []),
                    memory_entries=current_used.get("memory_entries", []),
                )
                current_used = task.context_used
            except Exception as exc:
                logger.warning(f"Błąd migracji context_used: {exc}")
                task.context_used = ContextUsed(memory_entries=memory_ids)
                current_used = task.context_used
        if current_used is not None:
            current_used.memory_entries.extend(memory_ids)
            current_used.memory_entries = list(set(current_used.memory_entries))
        else:
            task.context_used = ContextUsed(memory_entries=memory_ids)
        self.state_manager.update_context(task_id, {"context_used": task.context_used})

    def _should_include_memory(self, request: TaskRequest, history_len: int) -> bool:
        """Heuristic gating for memory retrieval to reduce token usage."""
        if not request.content:
            return False
        text = request.content.lower()
        keywords = (
            "przypomnij",
            "pamietasz",
            "pamiętasz",
            "wczesniej",
            "wcześniej",
            "wroc",
            "wróć",
            "poprzednio",
            "remember",
            "earlier",
            "previous",
            "as before",
            "as earlier",
        )
        if any(key in text for key in keywords):
            return True
        return history_len >= SESSION_HISTORY_LIMIT

    def _should_generate_summary(self, request: TaskRequest) -> bool:
        """Generate a short summary only when explicitly requested."""
        if not request.content:
            return False
        text = request.content.lower()
        keywords = (
            "podsumuj",
            "podsumowanie",
            "streszcz",
            "streszczenie",
            "summary",
            "summarize",
        )
        return any(key in text for key in keywords)

    def _build_session_knowledge_metadata(
        self,
        *,
        kind: KnowledgeKind,
        session_id: str,
        request_id: str,
        created_at: str,
    ) -> dict[str, object]:
        scope = "session"
        ttl_days = resolve_ttl_days(kind, scope)
        return {
            "knowledge_contract_version": "v1",
            "provenance_source": "session_store",
            "provenance_request_id": request_id,
            "provenance_intent": None,
            "retention_scope": scope,
            "retention_expires_at": compute_expires_at(created_at, ttl_days),
            "session_id": session_id,
            "timestamp": created_at,
        }

    def _ensure_session_summary(self, task_id: UUID, task: "VenomTask") -> None:
        """Tworzy streszczenie gdy historia jest długa."""
        try:
            full_history = task.context_history.get("session_history_full") or []
            if not full_history:
                return
            raw_text = "\n".join(
                f"{entry.get('role', '')}: {entry.get('content', '')}"
                for entry in full_history
            )
            if (
                len(full_history) < HISTORY_SUMMARY_TRIGGER_MSGS
                and len(raw_text) < HISTORY_SUMMARY_TRIGGER_CHARS
            ):
                return

            strategy = getattr(SETTINGS, "SUMMARY_STRATEGY", SUMMARY_STRATEGY_DEFAULT)
            if strategy == "heuristic_only":
                summary = self._heuristic_summary(full_history)
            else:
                summary = self._summarize_history_llm(
                    raw_text
                ) or self._heuristic_summary(full_history)
            if not summary:
                return
            self.state_manager.update_context(task_id, {"session_summary": summary})
            session_id = task.context_history.get("session", {}).get("session_id")
            if session_id and self.session_store:
                self.session_store.set_summary(
                    session_id,
                    summary,
                    knowledge_metadata=self._build_session_knowledge_metadata(
                        kind=KnowledgeKind.SESSION_SUMMARY,
                        session_id=session_id,
                        request_id=str(task_id),
                        created_at=get_utc_now_iso(),
                    ),
                )
            # zapisz do pamięci długoterminowej
            self._memory_upsert(
                summary,
                metadata={
                    "type": "summary",
                    "session_id": task.context_history.get("session", {}).get(
                        "session_id"
                    )
                    or "default_session",
                    "user_id": DEFAULT_USER_ID,
                    "pinned": True,
                    "knowledge_contract_version": "v1",
                    "provenance_source": "orchestrator",
                    "provenance_request_id": str(task_id),
                    "provenance_intent": None,
                    "retention_scope": "session",
                    "retention_expires_at": compute_expires_at(
                        get_utc_now_iso(),
                        resolve_ttl_days(KnowledgeKind.SESSION_SUMMARY, "session"),
                    ),
                },
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Nie udało się wygenerować streszczenia sesji: {exc}")

    def _heuristic_summary(self, full_history: list) -> str:
        tail = "\n".join(
            f"{entry.get('role', '')}: {entry.get('content', '')}"
            for entry in full_history[-10:]
        )
        summary, _ = trim_to_char_limit(tail, SUMMARY_MAX_CHARS)
        return f"(Heurystyczne) Podsumowanie ostatnich wiadomości:\n{summary}"

    def _summarize_history_llm(self, history_text: str) -> str:
        """
        Synchroniczne streszczenie przy użyciu aktywnego modelu LLM.

        UWAGA: Ta metoda używa synchronicznego httpx.Client zamiast async,
        ponieważ jest wywoływana z kontekstu synchronicznego (_get_context_for_task).
        Jeśli w przyszłości zostanie przeniesiona do kontekstu async, konieczne będzie:
        - zmienienie sygnatury na `async def _summarize_history_llm(...):`,
        - zamiana `with httpx.Client(...) as client:` na
          `async with httpx.AsyncClient(...) as client:`,
        - dodanie `await` przed wywołaniem `client.post(...)`,
        - wywoływanie tej metody wyłącznie z kontekstu asynchronicznego.
        """
        try:
            history_text = self._trim_history_text_for_summary(history_text)
            strategy = getattr(SETTINGS, "SUMMARY_STRATEGY", SUMMARY_STRATEGY_DEFAULT)
            if strategy == "heuristic_only":
                return ""
            runtime = get_active_llm_runtime()
            model_name = runtime.model_name or SETTINGS.LLM_MODEL_NAME
            if not model_name:
                return ""
            endpoint = self._resolve_summary_endpoint(runtime)
            if not endpoint:
                return ""
            headers = self._build_summary_headers(runtime)
            payload = self._build_summary_payload(model_name, history_text)

            with httpx.Client(timeout=SETTINGS.OPENAI_API_TIMEOUT) as client:
                resp = client.post(endpoint, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
            message = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return message[:SUMMARY_MAX_CHARS] if message else ""
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Streszczenie LLM nieudane: {exc}")
            return ""

    def _trim_history_text_for_summary(self, history_text: str) -> str:
        history_text, was_trimmed = trim_to_char_limit(
            history_text, HISTORY_SUMMARY_TRIGGER_CHARS
        )
        if was_trimmed:
            logger.debug(
                f"Historia przycięta do {HISTORY_SUMMARY_TRIGGER_CHARS} znaków dla streszczenia LLM"
            )
        return history_text

    def _resolve_summary_endpoint(self, runtime: Any) -> str:
        endpoint = runtime.endpoint or ""
        if runtime.provider == "openai":
            endpoint = SETTINGS.OPENAI_CHAT_COMPLETIONS_ENDPOINT
        if not endpoint:
            return ""
        if endpoint.endswith("/v1"):
            return endpoint + "/chat/completions"
        if endpoint.endswith("/chat/completions"):
            return endpoint
        return endpoint.rstrip("/") + "/v1/chat/completions"

    def _build_summary_headers(self, runtime: Any) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if runtime.provider == "openai" and SETTINGS.OPENAI_API_KEY:
            headers["Authorization"] = f"Bearer {SETTINGS.OPENAI_API_KEY}"
        if runtime.service_type == "local" and getattr(
            SETTINGS, "LLM_LOCAL_API_KEY", None
        ):
            headers["Authorization"] = f"Bearer {SETTINGS.LLM_LOCAL_API_KEY}"
        return headers

    def _build_summary_payload(
        self, model_name: str, history_text: str
    ) -> Dict[str, Any]:
        system_prompt = (
            "Jesteś asystentem podsumowującym rozmowę. "
            "Streszczasz krótko po polsku, max 1000 znaków, bez wodolejstwa. "
            "Wylistuj tylko fakty/ustalenia/wnioski, pomiń szczegóły i cytaty. "
            "Nie wymyślaj nowych treści."
        )
        return {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": history_text},
            ],
            "max_tokens": SUMMARY_MODEL_MAX_TOKENS,
            "temperature": 0.2,
        }

    def _memory_upsert(self, text: str, metadata: Dict[str, Any]) -> None:
        if not text:
            return
        try:
            store: Optional[MemoryStoreLike] = getattr(
                self.memory_skill, "vector_store", None
            )
            if store is None:
                return
            store.upsert(text=text, metadata=metadata)
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Nie udało się zapisać do pamięci: {exc}")

    def _retrieve_relevant_memory(
        self, request: TaskRequest, session_id: Optional[str]
    ) -> tuple[str, list[str]]:
        """Pobiera top-3 wpisy z pamięci wektorowej dopasowane do zapytania."""
        if self._testing_mode:
            return "", []
        query = request.content or ""
        if not query.strip():
            return "", []
        try:
            results = self.memory_skill.vector_store.search(query, limit=5)
            top = self._select_relevant_memory_items(results, session_id)
            if not top:
                return "", []
            return self._format_memory_context(top)
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Nie udało się pobrać pamięci: {exc}")
            return "", []

    @staticmethod
    def _select_relevant_memory_items(
        results: list[dict], session_id: Optional[str]
    ) -> list[dict]:
        if not results:
            return []
        if not session_id:
            return results[:3]

        filtered = []
        for item in results:
            meta = item.get("metadata") or {}
            item_session_id = meta.get("session_id")
            if item_session_id and item_session_id != session_id:
                continue
            filtered.append(item)
        return filtered[:3] if filtered else results[:3]

    @staticmethod
    def _format_memory_context(items: list[dict]) -> tuple[str, list[str]]:
        lines: list[str] = []
        ids: list[str] = []
        for idx, item in enumerate(items, 1):
            text = SessionHandler._truncate_memory_text(item.get("text", ""))
            meta = item.get("metadata") or {}
            entry_id = item.get("id") or meta.get("id")
            if entry_id:
                ids.append(str(entry_id))
            lines.append(f"[{idx}] ({meta.get('type', 'fact')}) {text}")
        return "\n".join(lines), ids

    @staticmethod
    def _truncate_memory_text(text: str, limit: int = 400) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

    async def apply_preferred_language(
        self, task_id: UUID, request: TaskRequest, result: str, intent_manager
    ) -> str:
        """Tłumaczy wynik na preferowany język użytkownika."""
        preferred_language = (request.preferred_language or "").strip().lower()
        if not preferred_language or not isinstance(result, str) or not result.strip():
            return result
        if preferred_language not in ("pl", "en", "de"):
            self.state_manager.add_log(
                task_id,
                f"Nieznany preferowany język odpowiedzi: {preferred_language}",
            )
            return result
        detected_language = intent_manager._detect_language(result)
        if detected_language == preferred_language:
            return result
        if not detected_language and not any(ch.isalpha() for ch in result):
            return result
        if self.request_tracer:
            self.request_tracer.add_step(
                task_id,
                "Orchestrator",
                "translate_response",
                status="ok",
                details=f"source={detected_language or 'unknown'}, target={preferred_language}",
            )
        self.state_manager.add_log(
            task_id,
            (
                "Tłumaczenie odpowiedzi "
                f"{detected_language or 'unknown'} -> {preferred_language}"
            ),
        )
        translated = await translation_service.translate_text(
            result,
            preferred_language,
            source_lang=detected_language or None,
        )
        if translated != result:
            self.state_manager.update_context(
                task_id,
                {
                    "translation": {
                        "source": detected_language or "unknown",
                        "target": preferred_language,
                        "applied": True,
                    }
                },
            )
        return translated
