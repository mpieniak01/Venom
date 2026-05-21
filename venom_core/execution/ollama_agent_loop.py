"""Moduł: ollama_agent_loop - zamknięta pętla agentowa przez Ollama /api/chat z tool-calling."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"
_DEFAULT_MODEL = "qwen3.5:9b"
_DEFAULT_MAX_ITERATIONS = 5
_DEFAULT_TIMEOUT = 60


@dataclass
class ToolCall:
    """Pojedyncze wywołanie narzędzia przez LLM."""

    call_id: str
    name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    error: Optional[str] = None
    elapsed_ms: int = 0


@dataclass
class AgentLoopResult:
    """Wynik pełnej pętli agentowej."""

    final_answer: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    iterations: int = 0
    stopped_by: str = "finish"  # "finish" | "max_iter" | "error" | "fast_path"
    evidence: List[str] = field(default_factory=list)

    def has_evidence(self) -> bool:
        return bool(self.evidence)

    def format_trace(self) -> str:
        if not self.tool_calls:
            return "(brak wywołań narzędzi)"
        lines = []
        for tc in self.tool_calls:
            status = "✓" if tc.error is None else "✗"
            lines.append(f"  {status} {tc.name}({tc.arguments}) [{tc.elapsed_ms}ms]")
            if tc.result:
                lines.append(f"    → {tc.result[:200]}")
            if tc.error:
                lines.append(f"    ✗ {tc.error}")
        return "\n".join(lines)


ToolHandler = Callable[[str, Dict[str, Any]], str]


class OllamaAgentLoop:
    """
    Zamknięta pętla agentowa oparta na Ollama /api/chat z tool-calling.

    Format OpenAI-kompatybilny (obsługiwany przez qwen3.5:9b, gpt-oss:20b).

    Pętla:
        1. Zbuduj messages = [system_prompt, user_intent, ...tool_results]
        2. Wywołaj Ollama /api/chat z tools
        3. Jeśli response.tool_calls → wywołaj lokalny handler → dodaj wynik do messages
        4. Powtarzaj do max_iterations lub finish_reason=stop
        5. Zwróć AgentLoopResult z evidence i final_answer
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        ollama_url: str = _DEFAULT_OLLAMA_URL,
        max_iterations: int = _DEFAULT_MAX_ITERATIONS,
        timeout: int = _DEFAULT_TIMEOUT,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_handlers: Optional[Dict[str, ToolHandler]] = None,
        system_prompt: Optional[str] = None,
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.max_iterations = max_iterations
        self.timeout = timeout
        self.tools: List[Dict[str, Any]] = tools or []
        self.tool_handlers: Dict[str, ToolHandler] = tool_handlers or {}
        self.system_prompt = system_prompt or self._default_system_prompt()

    @staticmethod
    def _default_system_prompt() -> str:
        return (
            "Jesteś lokalnym agentem Venom. Odpowiadasz na pytania operatora na podstawie "
            "realnych wyników narzędzi. Zawsze wywołuj narzędzia zamiast zgadywać. "
            "Jeśli narzędzie zwróci wynik, użyj go jako podstawy odpowiedzi. "
            "Nie generuj listy komend jako finalnej odpowiedzi – wywołaj narzędzie i zwróć evidence."
        )

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: ToolHandler,
    ) -> None:
        """Rejestruje narzędzie dostępne dla LLM."""
        self.tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            }
        )
        self.tool_handlers[name] = handler

    def _call_ollama(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Wywołuje Ollama /api/chat i zwraca sparsowany JSON."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if self.tools:
            payload["tools"] = self.tools

        body = json.dumps(payload)
        req = urllib_request.Request(
            self.ollama_url,
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib_error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {err_body[:200]}") from e
        except urllib_error.URLError as e:
            raise RuntimeError(f"Błąd połączenia: {e.reason}") from e
        except TimeoutError as e:
            raise RuntimeError(f"Timeout połączenia ({self.timeout}s)") from e

        if not raw.strip():
            raise RuntimeError("Pusta odpowiedź Ollama")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Nieprawidłowy JSON z Ollama: {e}") from e
        if not isinstance(parsed, dict):
            raise RuntimeError(
                "Nieprawidłowy format odpowiedzi Ollama (oczekiwano obiektu)"
            )
        return parsed

    def _dispatch_tool(
        self, name: str, arguments: Dict[str, Any]
    ) -> tuple[str, Optional[str]]:
        """Wywołuje handler narzędzia. Zwraca (result, error)."""
        handler = self.tool_handlers.get(name)
        if handler is None:
            return "", f"Brak handlera dla narzędzia: {name}"
        try:
            result = handler(name, arguments)
            return str(result), None
        except Exception as e:
            return "", f"Błąd wywołania {name}: {e}"

    def _extract_tool_calls(
        self, response_message: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Ekstrahuje tool_calls z odpowiedzi modelu (format Ollama/OpenAI)."""
        raw = response_message.get("tool_calls")
        if not isinstance(raw, list):
            return []
        return [tc for tc in raw if isinstance(tc, dict)]

    @staticmethod
    def _extract_message(response: Dict[str, Any]) -> Dict[str, Any]:
        message = response.get("message")
        if isinstance(message, dict):
            return message
        return {}

    @staticmethod
    def _parse_tool_arguments(arguments: Any) -> Dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"raw": arguments}
            return {}
        return {}

    def _prepare_tool_call(
        self, tc_raw: Dict[str, Any], iteration: int
    ) -> tuple[str, str, Dict[str, Any]]:
        fn = tc_raw.get("function", {})
        if not isinstance(fn, dict):
            fn = {}
        tool_name = str(fn.get("name", ""))
        tool_args = self._parse_tool_arguments(fn.get("arguments", {}))
        call_id = str(tc_raw.get("id") or f"call_{iteration}_{tool_name}")
        return call_id, tool_name, tool_args

    def _invoke_tool_call(
        self, call_id: str, tool_name: str, tool_args: Dict[str, Any]
    ) -> ToolCall:
        t0 = time.monotonic()
        result_str, error = self._dispatch_tool(tool_name, tool_args)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        logger.info(
            f"Tool {tool_name} [{elapsed_ms}ms]: {(result_str or error or '')[:100]}"
        )
        return ToolCall(
            call_id=call_id,
            name=tool_name,
            arguments=tool_args,
            result=result_str if not error else None,
            error=error,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _append_tool_result_message(
        messages: List[Dict[str, Any]],
        call_id: str,
        result: Optional[str],
        error: Optional[str],
    ) -> None:
        tool_result_content = result if not error else f"Błąd: {error}"
        messages.append(
            {
                "role": "tool",
                "content": tool_result_content,
                "tool_call_id": call_id,
            }
        )

    def _process_tool_calls(
        self,
        raw_tool_calls: List[Dict[str, Any]],
        iteration: int,
        messages: List[Dict[str, Any]],
        all_tool_calls: List[ToolCall],
        evidence: List[str],
    ) -> None:
        for tc_raw in raw_tool_calls:
            call_id, tool_name, tool_args = self._prepare_tool_call(tc_raw, iteration)
            tool_call = self._invoke_tool_call(call_id, tool_name, tool_args)
            all_tool_calls.append(tool_call)
            if tool_call.result:
                evidence.append(f"{tool_name}: {tool_call.result}")
            self._append_tool_result_message(
                messages, call_id, tool_call.result, tool_call.error
            )

    @staticmethod
    def _final_result_from_message(
        message: Dict[str, Any],
        finish_reason: str,
        iterations: int,
        all_tool_calls: List[ToolCall],
        evidence: List[str],
    ) -> AgentLoopResult:
        final_answer = str(message.get("content", ""))
        stopped_by = "finish" if finish_reason != "max_iter" else "max_iter"
        return AgentLoopResult(
            final_answer=final_answer,
            tool_calls=all_tool_calls,
            iterations=iterations,
            stopped_by=stopped_by,
            evidence=evidence,
        )

    def run(self, user_intent: str) -> AgentLoopResult:
        return self._run_agent_loop(user_intent)

    @staticmethod
    def _build_error_result(
        error: Exception,
        iterations: int,
        all_tool_calls: List[ToolCall],
        evidence: List[str],
    ) -> AgentLoopResult:
        return AgentLoopResult(
            final_answer=f"❌ Błąd komunikacji z Ollama: {error}",
            tool_calls=all_tool_calls,
            iterations=iterations,
            stopped_by="error",
            evidence=evidence,
        )

    @staticmethod
    def _build_initial_messages(
        user_intent: str, system_prompt: str
    ) -> List[Dict[str, Any]]:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_intent},
        ]

    def _finalize_after_max_iterations(
        self,
        messages: List[Dict[str, Any]],
        all_tool_calls: List[ToolCall],
        evidence: List[str],
    ) -> AgentLoopResult:
        logger.warning(f"max_iterations={self.max_iterations} osiągnięte")
        try:
            messages.append(
                {
                    "role": "user",
                    "content": "Podsumuj dotychczasowe wyniki narzędzi w jednej krótkiej odpowiedzi.",
                }
            )
            response = self._call_ollama(messages)
            final_answer = self._extract_message(response).get("content", "")
        except Exception as e:
            final_answer = f"⚠️ Przekroczono limit iteracji. Ostatni błąd: {e}"

        return AgentLoopResult(
            final_answer=final_answer,
            tool_calls=all_tool_calls,
            iterations=self.max_iterations,
            stopped_by="max_iter",
            evidence=evidence,
        )

    def _run_agent_loop(self, user_intent: str) -> AgentLoopResult:
        """
        Uruchamia pętlę agentową dla podanego intentu.

        Args:
            user_intent: Treść zapytania użytkownika.

        Returns:
            AgentLoopResult z finalną odpowiedzią i dowodem wykonania.
        """
        messages = self._build_initial_messages(user_intent, self.system_prompt)

        all_tool_calls: List[ToolCall] = []
        evidence: List[str] = []

        logger.info(
            f"OllamaAgentLoop start: model={self.model}, intent={user_intent[:80]!r}"
        )

        for iteration in range(1, self.max_iterations + 1):
            logger.debug(f"Iteracja {iteration}/{self.max_iterations}")

            try:
                response = self._call_ollama(messages)
            except Exception as e:
                logger.error(f"Błąd Ollama: {e}")
                return self._build_error_result(e, iteration, all_tool_calls, evidence)

            message = self._extract_message(response)
            finish_reason = response.get("done_reason", "")
            raw_tool_calls = self._extract_tool_calls(message)

            if not raw_tool_calls:
                logger.info(f"Odpowiedź finalna po {iteration} iteracjach")
                return self._final_result_from_message(
                    message=message,
                    finish_reason=str(finish_reason),
                    iterations=iteration,
                    all_tool_calls=all_tool_calls,
                    evidence=evidence,
                )

            # Dodaj odpowiedź asystenta z tool_calls do historii
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": raw_tool_calls,
                }
            )

            self._process_tool_calls(
                raw_tool_calls=raw_tool_calls,
                iteration=iteration,
                messages=messages,
                all_tool_calls=all_tool_calls,
                evidence=evidence,
            )

        return self._finalize_after_max_iterations(messages, all_tool_calls, evidence)


def build_tool_spec(
    name: str,
    description: str,
    properties: Dict[str, Dict[str, Any]],
    required: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Helper do budowania spec narzędzia w formacie OpenAI/Ollama."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }
