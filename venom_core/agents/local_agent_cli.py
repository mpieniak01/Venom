"""
Moduł: local_agent_cli - samodzielny lokalny agent CLI z indeksacją kodu i wykonywaniem komend.

Użycie:
    python -m venom_core.agents.local_agent_cli "zapytanie"
    python -m venom_core.agents.local_agent_cli --interactive
    python -m venom_core.agents.local_agent_cli --allow-exec "uruchom testy"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from venom_core.execution.ollama_agent_loop import (
    AgentLoopResult,
    OllamaAgentLoop,
    build_tool_spec,
)
from venom_core.execution.skills.code_index_skill import CodeIndexSkill
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_MODEL = "qwen3.5:9b"
_DEFAULT_MAX_ITER = 5


class IntentClass(str, Enum):
    GIT_STATUS = "git_status"
    CODE_SEARCH = "code_search"
    SHELL_EXEC = "shell_exec"
    FILE_OP = "file_op"
    GENERAL = "general"


class IntentRouter:
    """
    Klasyfikuje intent użytkownika na jedną z klas wykonawczych.

    Rozszerzenie IntegratorAgent._is_repo_truth_request() na pełny router.
    """

    _GIT_STATUS_MARKERS = (
        "sprawdz status git",
        "sprawdz repo git",
        "stan repo",
        "stan gita",
        "git status",
        "status git",
        "pokaż status git",
        "pokaz status git",
        "jaki jest status repozytorium",
        "jaki jest status repo",
    )

    _CODE_SEARCH_MARKERS = (
        "gdzie jest",
        "gdzie znajduje się",
        "gdzie jest klasa",
        "gdzie jest funkcja",
        "gdzie jest metoda",
        "znajdź klasę",
        "znajdz klase",
        "znajdź funkcję",
        "znajdz funkcje",
        "jak działa",
        "jak dziala",
        "pokaż kod",
        "pokaz kod",
        "pokaż implementację",
        "pokaz implementacje",
        "co robi klasa",
        "co robi funkcja",
        "gdzie zdefiniowana",
        "gdzie zdefiniowany",
        "pokaż plik",
        "pokaz plik",
        "search code",
        "find class",
        "find function",
        "szukaj w kodzie",
    )

    _SHELL_EXEC_MARKERS = (
        "uruchom",
        "wykonaj",
        "wywołaj",
        "wywolaj",
        "run ",
        "exec ",
        "uruchom testy",
        "sprawdź port",
        "sprawdz port",
        "zainstaluj",
        "zbuduj",
        "build",
        "make ",
        "pytest",
        "pip install",
    )

    _FILE_OP_MARKERS = (
        "pokaż zawartość",
        "pokaz zawartosc",
        "przeczytaj plik",
        "otwórz plik",
        "otworz plik",
        "zmień nazwę",
        "zmien nazwe",
        "stwórz plik",
        "stworz plik",
        "usuń plik",
        "usun plik",
        "wylistuj pliki",
        "lista plików",
        "lista plikow",
    )

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

    def classify(self, intent: str) -> IntentClass:
        n = self._normalize(intent)
        for marker in self._GIT_STATUS_MARKERS:
            if marker in n:
                return IntentClass.GIT_STATUS
        for marker in self._CODE_SEARCH_MARKERS:
            if marker in n:
                return IntentClass.CODE_SEARCH
        for marker in self._SHELL_EXEC_MARKERS:
            if marker in n:
                return IntentClass.SHELL_EXEC
        for marker in self._FILE_OP_MARKERS:
            if marker in n:
                return IntentClass.FILE_OP
        return IntentClass.GENERAL


@dataclass
class LocalAgentConfig:
    model: str = _DEFAULT_MODEL
    workspace: str = ""
    max_iter: int = _DEFAULT_MAX_ITER
    allow_exec: bool = False
    allow_destructive: bool = False
    json_output: bool = False
    interactive: bool = False
    no_think: bool = False

    def __post_init__(self):
        if not self.workspace:
            self.workspace = os.environ.get(
                "REPO_ROOT", os.environ.get("VENOM_WORKSPACE", str(Path.cwd()))
            )


class LocalAgent:
    """
    Samodzielny lokalny agent CLI z indeksacją kodu i wykonywaniem komend.
    """

    _DESTRUCTIVE_PATTERNS = re.compile(
        r"\b(rm\s+-rf|git\s+reset\s+--hard|drop\s+table|truncate|format\s+[a-z]:|mkfs|dd\s+if=)\b",
        re.IGNORECASE,
    )

    def __init__(self, config: LocalAgentConfig):
        self.config = config
        self.router = IntentRouter()
        self.code_index = CodeIndexSkill(workspace_root=config.workspace)
        self.git_skill = GitSkill(workspace_root=config.workspace)

    def _build_agent_loop(self) -> OllamaAgentLoop:
        loop = OllamaAgentLoop(
            model=self.config.model,
            max_iterations=self.config.max_iter,
            system_prompt=self._system_prompt(),
        )
        self._register_tools(loop)
        return loop

    def _system_prompt(self) -> str:
        workspace = self.config.workspace
        exec_mode = (
            "z wykonaniem komend" if self.config.allow_exec else "tryb read-only"
        )
        return (
            f"Jesteś lokalnym agentem Venom ({exec_mode}). "
            f"Workspace: {workspace}. "
            "Odpowiadasz na pytania operatora na podstawie realnych wyników narzędzi. "
            "Zawsze wywołuj narzędzia zamiast zgadywać. "
            "Jeśli narzędzie zwróci wynik, użyj go jako podstawy finalnej odpowiedzi. "
            "Nie generuj listy komend jako finalnej odpowiedzi – wywołaj narzędzie. "
            "Odpowiadaj po polsku, chyba że user pisze po angielsku."
        )

    def _register_tools(self, loop: OllamaAgentLoop) -> None:
        # Git status
        loop.register_tool(
            name="git_short_status",
            description="Zwraca skrócony status repozytorium Git (git status --short --branch).",
            parameters=build_tool_spec("git_short_status", "", {}, [])["function"][
                "parameters"
            ],
            handler=self._handle_git_status,
        )

        # Code search
        loop.register_tool(
            name="search_code",
            description=(
                "Przeszukuje kod projektu wzorcem tekstowym lub regex. "
                "Zwraca trafienia z ścieżkami plików i numerami linii."
            ),
            parameters=build_tool_spec(
                "search_code",
                "",
                {
                    "query": {
                        "type": "string",
                        "description": "Wzorzec lub nazwa symbolu",
                    },
                    "path_glob": {
                        "type": "string",
                        "description": "Glob plików np. '*.py' (opcjonalne)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maks wyników (domyślnie 10)",
                    },
                },
                ["query"],
            )["function"]["parameters"],
            handler=self._handle_search_code,
        )

        # File symbols
        loop.register_tool(
            name="get_file_symbols",
            description="Ekstrahuje klasy, funkcje i importy z pliku Python.",
            parameters=build_tool_spec(
                "get_file_symbols",
                "",
                {
                    "file_path": {
                        "type": "string",
                        "description": "Ścieżka do pliku .py",
                    }
                },
                ["file_path"],
            )["function"]["parameters"],
            handler=self._handle_file_symbols,
        )

        # Read context
        loop.register_tool(
            name="read_file_context",
            description="Zwraca fragment pliku wokół wskazanej linii.",
            parameters=build_tool_spec(
                "read_file_context",
                "",
                {
                    "file_path": {"type": "string", "description": "Ścieżka do pliku"},
                    "line": {"type": "integer", "description": "Numer linii"},
                    "context_lines": {
                        "type": "integer",
                        "description": "Liczba linii kontekstu (domyślnie 5)",
                    },
                },
                ["file_path", "line"],
            )["function"]["parameters"],
            handler=self._handle_read_context,
        )

        # Shell exec (tylko gdy allow_exec)
        if self.config.allow_exec:
            loop.register_tool(
                name="shell_exec",
                description="Wykonuje komendę shell na środowisku lokalnym.",
                parameters=build_tool_spec(
                    "shell_exec",
                    "",
                    {
                        "command": {
                            "type": "string",
                            "description": "Komenda do wykonania",
                        }
                    },
                    ["command"],
                )["function"]["parameters"],
                handler=self._handle_shell_exec,
            )

    def _handle_git_status(self, _name: str, _args: dict) -> str:
        result = asyncio.run(self.git_skill.get_short_status())
        repo_root = str(self.code_index.workspace_root)
        return f"REPO_ROOT={repo_root}\n{result}"

    def _handle_search_code(self, _name: str, args: dict) -> str:
        query = args.get("query", "")
        path_glob = args.get("path_glob")
        max_results = int(args.get("max_results", 10))
        matches = self.code_index.search_code(
            query=query, path_glob=path_glob, max_results=max_results
        )
        return self.code_index.format_matches_for_llm(matches)

    def _handle_file_symbols(self, _name: str, args: dict) -> str:
        symbols = self.code_index.get_file_symbols(args.get("file_path", ""))
        return symbols.format_summary()

    def _handle_read_context(self, _name: str, args: dict) -> str:
        return self.code_index.read_context(
            file_path=args.get("file_path", ""),
            line=int(args.get("line", 1)),
            context_lines=int(args.get("context_lines", 5)),
        )

    def _handle_shell_exec(self, _name: str, args: dict) -> str:
        command = args.get("command", "").strip()
        if not command:
            return "❌ Pusta komenda"
        if not self.config.allow_exec:
            return "❌ Wykonanie komend zablokowane. Użyj --allow-exec."
        if not self.config.allow_destructive and self._DESTRUCTIVE_PATTERNS.search(
            command
        ):
            return "❌ Komenda destrukcyjna zablokowana. Użyj --allow-destructive."
        logger.info(f"shell_exec: {command!r}")
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.config.workspace,
                timeout=30,
            )
            output = result.stdout + (
                f"\nSTDERR: {result.stderr}" if result.stderr.strip() else ""
            )
            return output.strip() or "(brak outputu)"
        except subprocess.TimeoutExpired:
            return "❌ Timeout komendy (30s)"
        except Exception as e:
            return f"❌ Błąd: {e}"

    def handle_intent(self, intent: str) -> AgentLoopResult:
        """Obsługuje intent przez odpowiednią ścieżkę wykonania."""
        intent_class = self.router.classify(intent)
        logger.info(f"Intent class: {intent_class.value} dla: {intent[:60]!r}")

        if intent_class == IntentClass.GIT_STATUS:
            # Fast path – bez LLM dla prostego git status
            raw = self._handle_git_status("git_short_status", {})
            return AgentLoopResult(
                final_answer=raw,
                evidence=[raw],
                iterations=0,
                stopped_by="fast_path",
            )

        # Dla pozostałych intentów – pełna pętla agentowa
        loop = self._build_agent_loop()
        return loop.run(intent)

    def run_once(self, query: str) -> str:
        """Uruchamia agenta dla pojedynczego zapytania i zwraca sformatowaną odpowiedź."""
        result = self.handle_intent(query)

        if self.config.json_output:
            return json.dumps(
                {
                    "final_answer": result.final_answer,
                    "evidence": result.evidence,
                    "iterations": result.iterations,
                    "stopped_by": result.stopped_by,
                    "tool_calls": [tc.to_dict() for tc in result.tool_calls],
                },
                ensure_ascii=False,
                indent=2,
            )

        lines = [result.final_answer]
        if result.tool_calls:
            lines.append("")
            lines.append("--- Trace ---")
            lines.append(result.format_trace())
        return "\n".join(lines)

    def run_interactive(self) -> None:
        """Interaktywna pętla REPL."""
        print(
            f"Venom Local Agent (model: {self.config.model}, workspace: {self.config.workspace})"
        )
        print("Wpisz zapytanie lub 'exit' aby zakończyć.\n")
        while True:
            try:
                query = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nZakończono.")
                break
            if not query:
                continue
            if query.lower() in ("exit", "quit", "q"):
                print("Zakończono.")
                break
            answer = self.run_once(query)
            print(answer)
            print()


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Venom Local Agent CLI – lokalny agent z indeksacją kodu i wykonywaniem komend.",
        prog="venom_core.agents.local_agent_cli",
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Zapytanie do agenta (pomiń dla --interactive)",
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        help=f"Model Ollama (domyślnie: {_DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--workspace",
        default="",
        help="Ścieżka workspace (domyślnie: REPO_ROOT lub CWD)",
    )
    parser.add_argument(
        "--max-iter",
        type=int,
        default=_DEFAULT_MAX_ITER,
        help=f"Maksymalna liczba iteracji agenta (domyślnie: {_DEFAULT_MAX_ITER})",
    )
    parser.add_argument(
        "--allow-exec",
        action="store_true",
        default=False,
        help="Zezwól na wykonywanie komend shell (domyślnie: zablokowane)",
    )
    parser.add_argument(
        "--allow-destructive",
        action="store_true",
        default=False,
        help="Zezwól na komendy destrukcyjne (wymaga --allow-exec)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        default=False,
        help="Tryb interaktywny REPL",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        default=False,
        help="Wyjście w formacie JSON",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)

    config = LocalAgentConfig(
        model=args.model,
        workspace=args.workspace,
        max_iter=args.max_iter,
        allow_exec=args.allow_exec,
        allow_destructive=args.allow_destructive,
        json_output=args.json_output,
        interactive=args.interactive,
    )
    agent = LocalAgent(config)

    if config.interactive:
        agent.run_interactive()
        return 0

    if not args.query:
        print("Błąd: podaj zapytanie lub użyj --interactive", file=sys.stderr)
        return 1

    output = agent.run_once(args.query)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
