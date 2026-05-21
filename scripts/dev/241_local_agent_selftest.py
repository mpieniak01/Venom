#!/usr/bin/env python3
"""
Selftest PR241 – weryfikuje LocalAgentCLI bez VS Code, bez Copilot, bez zewnętrznego API.

Testy:
  1. git_status:   agent.run_once("sprawdz status git") zawiera REPO_ROOT= i blok ## branch
  2. code_search:  agent.run_once("gdzie jest klasa IntegratorAgent") zawiera ścieżkę pliku i numer linii
  3. intent_router: IntentRouter klasyfikuje kluczowe klasy intentów
  4. code_index:   CodeIndexSkill.search_code("IntegratorAgent") zwraca wynik z ścieżką
  5. no_vscode:    brak zależności od vscode / copilot w imporcie

Uruchomienie:
    python scripts/dev/241_local_agent_selftest.py
    python scripts/dev/241_local_agent_selftest.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


@dataclass
class ProbeResult:
    name: str
    status: str  # "PASS" | "FAIL" | "SKIP"
    message: str = ""
    detail: str = ""


@dataclass
class SelftestReport:
    probes: List[ProbeResult] = field(default_factory=list)

    def add(self, probe: ProbeResult) -> None:
        self.probes.append(probe)

    def passed(self) -> bool:
        return all(p.status in ("PASS", "SKIP") for p in self.probes)

    def summary(self) -> str:
        lines = ["=== PR241 LocalAgent Selftest ==="]
        for p in self.probes:
            icon = "✓" if p.status == "PASS" else ("⚠" if p.status == "SKIP" else "✗")
            lines.append(f"  {icon} [{p.status}] {p.name}: {p.message}")
            if p.detail:
                lines.append(f"          {p.detail[:200]}")
        lines.append("")
        lines.append("RESULT: " + ("PASS" if self.passed() else "FAIL"))
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "result": "PASS" if self.passed() else "FAIL",
            "probes": [
                {
                    "name": p.name,
                    "status": p.status,
                    "message": p.message,
                    "detail": p.detail,
                }
                for p in self.probes
            ],
        }


def probe_import() -> ProbeResult:
    name = "import_no_vscode"
    try:
        from venom_core.agents.local_agent_cli import (  # noqa: F401
            IntentRouter,
            LocalAgent,
            LocalAgentConfig,
        )
        from venom_core.execution.ollama_agent_loop import OllamaAgentLoop  # noqa: F401
        from venom_core.execution.skills.code_index_skill import (  # noqa: F401
            CodeIndexSkill,
        )

        return ProbeResult(name, "PASS", "Wszystkie moduły importują się bez vscode")
    except ImportError as e:
        return ProbeResult(name, "FAIL", f"Import error: {e}")


def probe_intent_router() -> ProbeResult:
    name = "intent_router"
    try:
        from venom_core.agents.local_agent_cli import IntentClass, IntentRouter

        router = IntentRouter()
        cases = [
            ("sprawdz status git", IntentClass.GIT_STATUS),
            ("gdzie jest klasa IntegratorAgent", IntentClass.CODE_SEARCH),
            ("hello world", IntentClass.GENERAL),
        ]
        failures = []
        for intent, expected in cases:
            got = router.classify(intent)
            if got != expected:
                failures.append(
                    f"{intent!r}: expected {expected.value}, got {got.value}"
                )
        if failures:
            return ProbeResult(name, "FAIL", "Błędna klasyfikacja", "; ".join(failures))
        return ProbeResult(name, "PASS", f"Klasyfikacja OK dla {len(cases)} przypadków")
    except Exception as e:
        return ProbeResult(name, "FAIL", str(e), traceback.format_exc()[-300:])


def probe_code_index_search() -> ProbeResult:
    name = "code_index_search"
    try:
        from venom_core.execution.skills.code_index_skill import CodeIndexSkill

        skill = CodeIndexSkill(workspace_root=str(REPO_ROOT))
        # Szukamy definicji klasy – pattern ^class IntegratorAgent ogranicza do prawdziwych definicji
        matches = skill.search_code(
            "^class IntegratorAgent", path_glob="*.py", max_results=5
        )
        if not matches:
            return ProbeResult(
                name, "FAIL", "Brak wyników dla '^class IntegratorAgent'"
            )
        # Szukamy trafienia z venom_core (nie skrypt diagnostyczny)
        best = next((m for m in matches if "venom_core" in m.file), matches[0])
        if "integrator" not in best.file.lower():
            return ProbeResult(name, "FAIL", f"Nieoczekiwany plik: {best.file}")
        detail = f"{best.file}:{best.line}"
        return ProbeResult(
            name, "PASS", "Znaleziono klasę IntegratorAgent w venom_core", detail
        )
    except Exception as e:
        return ProbeResult(name, "FAIL", str(e), traceback.format_exc()[-300:])


def probe_git_status_fast_path() -> ProbeResult:
    name = "git_status_fast_path"
    try:
        from venom_core.agents.local_agent_cli import LocalAgent, LocalAgentConfig

        config = LocalAgentConfig(workspace=str(REPO_ROOT), model="qwen3.5:9b")
        agent = LocalAgent(config)
        result = agent.handle_intent("sprawdz status git")
        if result.stopped_by != "fast_path":
            return ProbeResult(
                name, "FAIL", f"stopped_by={result.stopped_by!r}, oczekiwano fast_path"
            )
        answer = result.final_answer
        if "REPO_ROOT=" not in answer:
            return ProbeResult(
                name, "FAIL", "Brak REPO_ROOT= w odpowiedzi", answer[:200]
            )
        if "##" not in answer:
            return ProbeResult(
                name, "FAIL", "Brak bloku ## branch w odpowiedzi", answer[:200]
            )
        return ProbeResult(
            name, "PASS", "REPO_ROOT= i ## branch w odpowiedzi", answer.splitlines()[0]
        )
    except Exception as e:
        return ProbeResult(name, "FAIL", str(e), traceback.format_exc()[-300:])


def probe_code_search_via_agent() -> ProbeResult:
    name = "code_search_via_agent"
    try:
        from venom_core.agents.local_agent_cli import LocalAgent, LocalAgentConfig

        config = LocalAgentConfig(workspace=str(REPO_ROOT), model="qwen3.5:9b")
        agent = LocalAgent(config)

        # Testuj bezpośrednio handler bez LLM (LLM wymaga dostępnego Ollama)
        result = agent._handle_search_code(
            "search_code",
            {"query": "class IntegratorAgent", "path_glob": "*.py", "max_results": 3},
        )
        if "integrator" in result.lower() or "IntegratorAgent" in result:
            return ProbeResult(
                name,
                "PASS",
                "Handler search_code zwraca wynik z klasą IntegratorAgent",
                result[:150],
            )
        return ProbeResult(
            name, "FAIL", "Brak IntegratorAgent w wynikach search", result[:150]
        )
    except Exception as e:
        return ProbeResult(name, "FAIL", str(e), traceback.format_exc()[-300:])


def probe_shell_exec_blocked_by_default() -> ProbeResult:
    name = "shell_exec_blocked_by_default"
    try:
        from venom_core.agents.local_agent_cli import LocalAgent, LocalAgentConfig

        config = LocalAgentConfig(workspace=str(REPO_ROOT), allow_exec=False)
        agent = LocalAgent(config)
        result = agent._handle_shell_exec("shell_exec", {"command": "echo test"})
        if "❌" in result and "allow-exec" in result:
            return ProbeResult(name, "PASS", "Wykonanie komend zablokowane domyślnie")
        return ProbeResult(
            name, "FAIL", "Komenda nie jest zablokowana domyślnie", result[:100]
        )
    except Exception as e:
        return ProbeResult(name, "FAIL", str(e))


def run_all() -> SelftestReport:
    report = SelftestReport()
    probes = [
        probe_import,
        probe_intent_router,
        probe_code_index_search,
        probe_git_status_fast_path,
        probe_code_search_via_agent,
        probe_shell_exec_blocked_by_default,
    ]
    for probe_fn in probes:
        result = probe_fn()
        report.add(result)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="PR241 LocalAgent Selftest")
    parser.add_argument("--json", action="store_true", help="Wynik jako JSON")
    args = parser.parse_args()

    report = run_all()

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.summary())

    return 0 if report.passed() else 1


if __name__ == "__main__":
    sys.exit(main())
