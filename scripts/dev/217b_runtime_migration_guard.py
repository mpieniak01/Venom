#!/usr/bin/env python3
"""217B: Guard migracji pakietu runtime — blokuje wydanie jeśli stary pakiet nadal aktywny.

Sprawdza trzy warunki:
1. Główny entrypoint runtime wskazuje na services.multi_runtime (nie gemma4_audio_runtime).
2. Skrypt startowy używa nowego module path.
3. Testy pierwszej klasy nie importują starego pakietu.

Uruchomienie:
  python scripts/dev/217b_runtime_migration_guard.py
  python scripts/dev/217b_runtime_migration_guard.py --strict  # exit 1 jeśli błędy
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CHECKS: list[tuple[str, bool, str]] = []


def check(description: str, condition: bool, detail: str = "") -> None:
    CHECKS.append((description, condition, detail))


def run_guards() -> None:
    # 1. New package entrypoint uses services.multi_runtime
    new_main = REPO_ROOT / "services/multi_runtime/main.py"
    if new_main.exists():
        content = new_main.read_text()
        check(
            "services/multi_runtime/main.py entrypoint = services.multi_runtime.main:app",
            "services.multi_runtime.main:app" in content,
            "entrypoint string not updated"
            if "gemma4_audio_runtime" in content
            else "",
        )
    else:
        check("services/multi_runtime/main.py exists", False, "file not found")

    # 2. Startup script uses new module path
    service_sh = REPO_ROOT / "scripts/llm/multi_runtime_service.sh"
    if service_sh.exists():
        sh_content = service_sh.read_text()
        check(
            "multi_runtime_service.sh spawns services.multi_runtime.main",
            "services.multi_runtime.main" in sh_content
            and "services.gemma4_audio_runtime.main" not in sh_content,
            sh_content,
        )
    else:
        check("scripts/llm/multi_runtime_service.sh exists", False, "file not found")

    # 3. Primary test files no longer import old package
    old_imports_in_tests = []
    for test_file in (REPO_ROOT / "tests").glob("*.py"):
        if "__pycache__" in str(test_file):
            continue
        content = test_file.read_text(encoding="utf-8")
        if (
            "services.gemma4_audio_runtime" in content
            or "services/gemma4_audio_runtime" in content
        ):
            old_imports_in_tests.append(test_file.name)
    check(
        "Primary test files have no direct imports from services.gemma4_audio_runtime",
        len(old_imports_in_tests) == 0,
        f"Still importing old package: {old_imports_in_tests}"
        if old_imports_in_tests
        else "",
    )

    # 4. Old shim files exist (confirming they are shims, not removed prematurely)
    shim_files = [
        "services/gemma4_audio_runtime/engine.py",
        "services/gemma4_audio_runtime/main.py",
    ]
    for shim in shim_files:
        path = REPO_ROOT / shim
        if path.exists():
            content = path.read_text()
            is_shim = "services.multi_runtime" in content
            check(
                f"{shim} is a compatibility shim (imports from multi_runtime)",
                is_shim,
                "still contains implementation, not a shim" if not is_shim else "",
            )

    # 5. New engine has renamed classes
    engine_new = REPO_ROOT / "services/multi_runtime/engine.py"
    if engine_new.exists():
        engine_content = engine_new.read_text()
        check(
            "services/multi_runtime/engine.py has class MultiRuntimeEngine",
            "class MultiRuntimeEngine" in engine_content,
        )
        check(
            "services/multi_runtime/engine.py has class MultiRuntimeDaemon",
            "class MultiRuntimeDaemon" in engine_content,
        )
        check(
            "services/multi_runtime/engine.py has no class Gemma4AudioEngine (renamed)",
            "class Gemma4AudioEngine" not in engine_content,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="217B: guard migracji runtime")
    parser.add_argument("--strict", action="store_true", help="Exit 1 jeśli błędy")
    args = parser.parse_args()

    run_guards()

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    failed = sum(1 for _, ok, _ in CHECKS if not ok)

    print(f"\n217B migration guard — wyniki ({passed}/{len(CHECKS)} passed):\n")
    for desc, ok, detail in CHECKS:
        status = "✅" if ok else "❌"
        suffix = f"\n     {detail}" if detail and not ok else ""
        print(f"  {status} {desc}{suffix}")

    if failed == 0:
        print(
            "\n✅ Guard: migracja Fazy 2 kompletna — services.multi_runtime jest aktywnym runtime."
        )
        sys.exit(0)
    else:
        print(f"\n❌ Guard: {failed} warunek(ów) niespełnionych.")
        if args.strict:
            sys.exit(1)


if __name__ == "__main__":
    main()
