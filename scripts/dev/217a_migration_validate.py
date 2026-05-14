#!/usr/bin/env python3
"""217A: Walidacja kontraktorów runtime — sprawdza, czy publiczne kontrakty wystawiają multi_runtime.

Testuje warstwy bez uruchamiania serwera (unit-level assertions):
  python scripts/dev/217a_migration_validate.py
  python scripts/dev/217a_migration_validate.py --strict   # exit 1 jeśli błędy
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

CHECKS: list[tuple[str, bool, str]] = []  # (opis, passed, szczegół)


def check(description: str, condition: bool, detail: str = "") -> None:
    CHECKS.append((description, condition, detail))


def run_validations() -> None:
    # --- runtime_names helper ---
    from venom_core.utils.runtime_names import (
        MULTI_RUNTIME_ID,
        is_multi_runtime,
        normalize_runtime_id,
    )

    check(
        "MULTI_RUNTIME_ID == 'multi_runtime'",
        MULTI_RUNTIME_ID == "multi_runtime",
        MULTI_RUNTIME_ID,
    )
    check("is_multi_runtime('multi_runtime')", is_multi_runtime("multi_runtime"))
    check(
        "is_multi_runtime('gemma4_audio') == True (normalizacja legacy)",
        is_multi_runtime("gemma4_audio"),
    )
    check(
        "normalize_runtime_id('gemma4_audio') == 'multi_runtime'",
        normalize_runtime_id("gemma4_audio") == "multi_runtime",
        normalize_runtime_id("gemma4_audio"),
    )

    # --- system_llm_service ---
    from venom_core.services.system_llm_service import (
        allowed_local_servers,
        installed_local_servers,
    )

    full = allowed_local_servers(profile="full", onnx_enabled=False)
    check(
        "allowed_local_servers: multi_runtime present",
        "multi_runtime" in full,
        str(full),
    )
    check(
        "allowed_local_servers: gemma4_audio absent",
        "gemma4_audio" not in full,
        str(full),
    )

    installed = installed_local_servers(
        ollama_installed=False, vllm_installed=False, onnx_installed=False
    )
    check(
        "installed_local_servers: multi_runtime present",
        "multi_runtime" in installed,
        str(installed),
    )
    check(
        "installed_local_servers: gemma4_audio absent",
        "gemma4_audio" not in installed,
        str(installed),
    )

    # --- llm_runtime resolution ---
    from venom_core.utils.llm_runtime import (
        get_active_llm_runtime,
        infer_local_provider,
    )

    check(
        "infer_local_provider(8014 port) == 'multi_runtime'",
        infer_local_provider("http://localhost:8014/v1") == "multi_runtime",
        infer_local_provider("http://localhost:8014/v1"),
    )

    class _Settings8014:
        LLM_SERVICE_TYPE = "local"
        AI_MODE = "LOCAL"
        LLM_MODEL_NAME = "test-model"
        LLM_LOCAL_ENDPOINT = "http://localhost:8014/v1"
        ACTIVE_LLM_SERVER = "gemma4_audio"
        GEMMA4_AUDIO_ENDPOINT = "http://localhost:8014/v1"
        VLLM_ENDPOINT = ""

    runtime = get_active_llm_runtime(_Settings8014())
    check(
        "get_active_llm_runtime(ACTIVE_LLM_SERVER=gemma4_audio).provider == multi_runtime",
        runtime.provider == "multi_runtime",
        runtime.provider,
    )

    # --- llm_server_controller ---
    from types import SimpleNamespace

    from venom_core.core.llm_server_controller import LlmServerController

    cfg = SimpleNamespace(
        VLLM_START_COMMAND="",
        VLLM_STOP_COMMAND="",
        VLLM_RESTART_COMMAND="",
        VLLM_ENDPOINT="http://localhost:8001/v1",
        OLLAMA_START_COMMAND="",
        OLLAMA_STOP_COMMAND="",
        OLLAMA_RESTART_COMMAND="",
        GEMMA4_AUDIO_START_COMMAND="",
        GEMMA4_AUDIO_STOP_COMMAND="",
        GEMMA4_AUDIO_RESTART_COMMAND="",
        GEMMA4_AUDIO_ENDPOINT="http://localhost:8014/v1",
        GEMMA4_AUDIO_HOST="localhost",
        GEMMA4_AUDIO_PORT=8014,
    )
    controller = LlmServerController(cfg)
    names = {srv["name"] for srv in controller.list_servers()}
    providers = {srv["provider"] for srv in controller.list_servers()}
    check(
        "controller: 'multi_runtime' w nazwach serwerów",
        "multi_runtime" in names,
        str(names),
    )
    check(
        "controller: 'gemma4_audio' nieobecne w nazwach",
        "gemma4_audio" not in names,
        str(names),
    )
    check(
        "controller: 'multi_runtime' w providers",
        "multi_runtime" in providers,
        str(providers),
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="217A: walidacja kontraktów runtime")
    parser.add_argument("--strict", action="store_true", help="Exit 1 jeśli błędy")
    args = parser.parse_args()

    try:
        run_validations()
    except Exception as exc:
        print(f"❌ Błąd podczas walidacji: {exc}", file=sys.stderr)
        sys.exit(2)

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    failed = sum(1 for _, ok, _ in CHECKS if not ok)

    print(f"\n217A kontrakt runtime — wyniki ({passed}/{len(CHECKS)} passed):\n")
    for desc, ok, detail in CHECKS:
        status = "✅" if ok else "❌"
        suffix = f"  [{detail}]" if detail and not ok else ""
        print(f"  {status} {desc}{suffix}")

    if failed == 0:
        print(
            "\n✅ Wszystkie kontrakty poprawne — multi_runtime jest jedyną publiczną nazwą."
        )
        sys.exit(0)
    else:
        print(f"\n❌ {failed} kontrakt(y) niespełnione — migracja niekompletna.")
        if args.strict:
            sys.exit(1)


if __name__ == "__main__":
    main()
