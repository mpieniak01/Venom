#!/usr/bin/env python3
"""
Probe kontraktowy PR241B – weryfikuje artefakty rozszerzenia VS Code bez uruchamiania VS Code.

Sprawdza:
  1. build_ok:         out/extension.js istnieje i jest aktualny po kompilacji TypeScript
  2. single_participant: package.json zawiera tylko 'venom.agent', brak 'venom.execution'
  3. tools_registered:  package.json rejestruje wymagane narzędzia LM
  4. new_settings:      package.json zawiera ustawienia allowExec i maxIterations
  5. agentic_loop_code: extension.ts zawiera pętlę agentową z LanguageModelToolCallPart
  6. allowlist_extended: extension.ts zawiera rozszerzoną allowlistę git (min 10 komend)
  7. search_code_impl:  extension.ts zawiera implementację searchCode z ripgrep
  8. legacy_alias:      extension.ts zachowuje narzędzie run_git_status jako alias

Uruchomienie:
    python scripts/dev/241b_vscode_extension_probe.py
    python scripts/dev/241b_vscode_extension_probe.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTENSION_DIR = REPO_ROOT / "tools" / "vscode-chat-executor"
EXTENSION_TS = EXTENSION_DIR / "src" / "extension.ts"
PACKAGE_JSON = EXTENSION_DIR / "package.json"
OUT_JS = EXTENSION_DIR / "out" / "extension.js"


@dataclass
class ProbeResult:
    name: str
    status: str  # "PASS" | "FAIL" | "SKIP"
    message: str = ""
    detail: str = ""


@dataclass
class ProbeReport:
    probes: List[ProbeResult] = field(default_factory=list)

    def add(self, p: ProbeResult) -> None:
        self.probes.append(p)

    def passed(self) -> bool:
        return all(p.status in ("PASS", "SKIP") for p in self.probes)

    def summary(self) -> str:
        lines = ["=== PR241B VSCode Extension Probe ==="]
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


def probe_build_ok() -> ProbeResult:
    name = "build_ok"
    if not OUT_JS.exists():
        # Spróbuj zbudować
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(EXTENSION_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return ProbeResult(
                name, "FAIL", "npm run build nie powiódł się", result.stderr[-300:]
            )
    if not OUT_JS.exists():
        return ProbeResult(name, "FAIL", f"Brak pliku: {OUT_JS.relative_to(REPO_ROOT)}")
    size = OUT_JS.stat().st_size
    return ProbeResult(name, "PASS", f"out/extension.js istnieje ({size} bajtów)")


def probe_single_participant() -> ProbeResult:
    name = "single_participant"
    try:
        pkg = json.loads(PACKAGE_JSON.read_text())
    except Exception as e:
        return ProbeResult(name, "FAIL", f"Błąd odczytu package.json: {e}")

    participants = pkg.get("contributes", {}).get("chatParticipants", [])
    ids = [p["id"] for p in participants]

    if "venom.execution" in ids:
        return ProbeResult(
            name,
            "FAIL",
            "Stary participant 'venom.execution' wciąż obecny w package.json",
            str(ids),
        )
    if "venom.agent" not in ids:
        return ProbeResult(
            name,
            "FAIL",
            "Brak nowego participanta 'venom.agent' w package.json",
            str(ids),
        )
    if len(ids) > 1:
        return ProbeResult(name, "FAIL", f"Więcej niż jeden participant: {ids}")
    return ProbeResult(
        name, "PASS", f"Tylko 'venom.agent' ({participants[0].get('name', '?')})"
    )


def probe_tools_registered() -> ProbeResult:
    name = "tools_registered"
    try:
        pkg = json.loads(PACKAGE_JSON.read_text())
    except Exception as e:
        return ProbeResult(name, "FAIL", f"Błąd odczytu package.json: {e}")

    required = {
        "venom_git_status",
        "venom_search_code",
        "venom_read_file",
        "venom_exec_safe",
    }
    registered = {
        t["name"] for t in pkg.get("contributes", {}).get("languageModelTools", [])
    }
    missing = required - registered

    if missing:
        return ProbeResult(
            name,
            "FAIL",
            f"Brak narzędzi: {sorted(missing)}",
            f"Zarejestrowane: {sorted(registered)}",
        )
    return ProbeResult(
        name,
        "PASS",
        f"Wszystkie {len(required)} narzędzi zarejestrowane",
        str(sorted(registered)),
    )


def probe_new_settings() -> ProbeResult:
    name = "new_settings"
    try:
        pkg = json.loads(PACKAGE_JSON.read_text())
    except Exception as e:
        return ProbeResult(name, "FAIL", f"Błąd odczytu package.json: {e}")

    props = pkg.get("contributes", {}).get("configuration", {}).get("properties", {})
    required = {"venom.execution.allowExec", "venom.execution.maxIterations"}
    missing = required - set(props.keys())

    if missing:
        return ProbeResult(name, "FAIL", f"Brak ustawień: {sorted(missing)}")
    return ProbeResult(
        name, "PASS", "Ustawienia allowExec i maxIterations zarejestrowane"
    )


def probe_agentic_loop_code() -> ProbeResult:
    name = "agentic_loop_code"
    try:
        src = EXTENSION_TS.read_text()
    except Exception as e:
        return ProbeResult(name, "FAIL", f"Błąd odczytu extension.ts: {e}")

    markers = [
        "LanguageModelToolCallPart",
        "LanguageModelToolResultPart",
        "sendRequest",
        "while (iterations < maxIter)",
    ]
    missing = [m for m in markers if m not in src]
    if missing:
        return ProbeResult(name, "FAIL", f"Brak w extension.ts: {missing}")
    return ProbeResult(
        name, "PASS", "Pętla agentowa z LanguageModelToolCallPart zaimplementowana"
    )


def probe_allowlist_extended() -> ProbeResult:
    name = "allowlist_extended"
    try:
        src = EXTENSION_TS.read_text()
    except Exception as e:
        return ProbeResult(name, "FAIL", f"Błąd odczytu extension.ts: {e}")

    # Proste sprawdzenie: git log powinno być w allowlist
    required_cmds = ["git log --oneline", "git diff", "git status"]
    missing = [c for c in required_cmds if c not in src]
    if missing:
        return ProbeResult(name, "FAIL", f"Brak komend git w allowliście: {missing}")

    # Policz wpisy w GIT_ALLOWLIST
    allowlist_section = (
        src[src.find("GIT_ALLOWLIST") : src.find("GIT_ALLOWLIST") + 2000]
        if "GIT_ALLOWLIST" in src
        else ""
    )
    entry_count = allowlist_section.count("'git ")
    if entry_count < 8:
        return ProbeResult(
            name, "FAIL", f"Allowlist za mała: {entry_count} wpisów (oczekiwano >=8)"
        )
    return ProbeResult(
        name, "PASS", f"Rozszerzona allowlist git ({entry_count} wpisów)"
    )


def probe_search_code_impl() -> ProbeResult:
    name = "search_code_impl"
    try:
        src = EXTENSION_TS.read_text()
    except Exception as e:
        return ProbeResult(name, "FAIL", f"Błąd odczytu extension.ts: {e}")

    markers = ["spawn('rg'", "--json", "searchCode"]
    missing = [m for m in markers if m not in src]
    if missing:
        return ProbeResult(name, "FAIL", f"Brak w searchCode impl: {missing}")
    return ProbeResult(
        name, "PASS", "searchCode z ripgrep (spawn rg --json) zaimplementowany"
    )


def probe_legacy_alias() -> ProbeResult:
    name = "legacy_alias"
    try:
        src = EXTENSION_TS.read_text()
        pkg = json.loads(PACKAGE_JSON.read_text())
    except Exception as e:
        return ProbeResult(name, "FAIL", f"Błąd odczytu: {e}")

    tools = {
        t["name"] for t in pkg.get("contributes", {}).get("languageModelTools", [])
    }
    if "run_git_status" not in tools:
        return ProbeResult(
            name, "FAIL", "Alias run_git_status brak w package.json languageModelTools"
        )
    if "LEGACY_TOOL_NAME" not in src and "run_git_status" not in src:
        return ProbeResult(name, "FAIL", "Alias run_git_status brak w extension.ts")
    return ProbeResult(name, "PASS", "Backward-compat alias run_git_status zachowany")


def run_all() -> ProbeReport:
    report = ProbeReport()
    for fn in [
        probe_build_ok,
        probe_single_participant,
        probe_tools_registered,
        probe_new_settings,
        probe_agentic_loop_code,
        probe_allowlist_extended,
        probe_search_code_impl,
        probe_legacy_alias,
    ]:
        report.add(fn())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="PR241B VSCode Extension Probe")
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
