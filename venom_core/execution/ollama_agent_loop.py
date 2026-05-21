"""Moduł: ollama_agent_loop - zamknięta pętla agentowa przez Ollama /api/chat z tool-calling."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

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
    stopped_by: str = "finish"  # "finish" | "max_iter" | "error"
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
        result = subprocess.run(
            [
                "curl",
                "-s",
                "--max-time",
                str(self.timeout),
                "-X",
                "POST",
                self.ollama_url,
                "-H",
                "Content-Type: application/json",
                "-d",
                body,
            ],
            capture_output=True,
            text=True,
            timeout=self.timeout + 5,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl błąd {result.returncode}: {result.stderr[:200]}")
        if not result.stdout.strip():
            raise RuntimeError("Pusta odpowiedź Ollama")
        return json.loads(result.stdout)

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
        return response_message.get("tool_calls") or []

    def run(self, user_intent: str) -> AgentLoopResult:
        """
        Uruchamia pętlę agentową dla podanego intentu.

        Args:
            user_intent: Treść zapytania użytkownika.

        Returns:
            AgentLoopResult z finalną odpowiedzią i dowodem wykonania.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_intent},
        ]

        all_tool_calls: List[ToolCall] = []
        evidence: List[str] = []
        iterations = 0
        stopped_by = "finish"

        logger.info(
            f"OllamaAgentLoop start: model={self.model}, intent={user_intent[:80]!r}"
        )

        while iterations < self.max_iterations:
            iterations += 1
            logger.debug(f"Iteracja {iterations}/{self.max_iterations}")

            try:
                response = self._call_ollama(messages)
            except Exception as e:
                logger.error(f"Błąd Ollama: {e}")
                return AgentLoopResult(
                    final_answer=f"❌ Błąd komunikacji z Ollama: {e}",
                    tool_calls=all_tool_calls,
                    iterations=iterations,
                    stopped_by="error",
                    evidence=evidence,
                )

            message = response.get("message", {})
            finish_reason = response.get("done_reason", "")
            raw_tool_calls = self._extract_tool_calls(message)

            if not raw_tool_calls:
                final_answer = message.get("content", "")
                logger.info(f"Odpowiedź finalna po {iterations} iteracjach")
                return AgentLoopResult(
                    final_answer=final_answer,
                    tool_calls=all_tool_calls,
                    iterations=iterations,
                    stopped_by="finish" if finish_reason != "max_iter" else "max_iter",
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

            # Wywołaj każde narzędzie i dodaj wyniki do messages
            for tc_raw in raw_tool_calls:
                fn = tc_raw.get("function", {})
                tc_name = fn.get("name", "")
                tc_args_raw = fn.get("arguments", {})
                if isinstance(tc_args_raw, str):
                    try:
                        tc_args = json.loads(tc_args_raw)
                    except json.JSONDecodeError:
                        tc_args = {"raw": tc_args_raw}
                else:
                    tc_args = tc_args_raw

                call_id = tc_raw.get("id") or f"call_{iterations}_{tc_name}"

                t0 = time.monotonic()
                result_str, error = self._dispatch_tool(tc_name, tc_args)
                elapsed_ms = int((time.monotonic() - t0) * 1000)

                tc = ToolCall(
                    call_id=call_id,
                    name=tc_name,
                    arguments=tc_args,
                    result=result_str if not error else None,
                    error=error,
                    elapsed_ms=elapsed_ms,
                )
                all_tool_calls.append(tc)
                logger.info(
                    f"Tool {tc_name} [{elapsed_ms}ms]: {(result_str or error or '')[:100]}"
                )

                if result_str:
                    evidence.append(f"{tc_name}: {result_str}")

                tool_result_content = result_str if not error else f"Błąd: {error}"
                messages.append(
                    {
                        "role": "tool",
                        "content": tool_result_content,
                        "tool_call_id": call_id,
                    }
                )

        # Przekroczono max_iterations – wymuś ostatnią odpowiedź
        stopped_by = "max_iter"
        logger.warning(f"max_iterations={self.max_iterations} osiągnięte")
        try:
            messages.append(
                {
                    "role": "user",
                    "content": "Podsumuj dotychczasowe wyniki narzędzi w jednej krótkiej odpowiedzi.",
                }
            )
            response = self._call_ollama(messages)
            final_answer = response.get("message", {}).get("content", "")
        except Exception as e:
            final_answer = f"⚠️ Przekroczono limit iteracji. Ostatni błąd: {e}"

        return AgentLoopResult(
            final_answer=final_answer,
            tool_calls=all_tool_calls,
            iterations=iterations,
            stopped_by=stopped_by,
            evidence=evidence,
        )


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
