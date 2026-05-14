#!/usr/bin/env python3
"""217B Faza 7: Exit guard — weryfikacja stanu po zakończeniu migracji.

Sprawdza:
1. Główny entrypoint runtime wskazuje na services.multi_runtime.main:app.
2. Kod poza shimami nie importuje bezpośrednio services.gemma4_audio_runtime (klas).
3. Helper modeli pierwszej klasy używa neutralnej nazwy (multi_runtime_models).
4. Stary pakiet services.gemma4_audio_runtime jest tylko warstwą shim.

Każdy check kończy się PASS lub FAIL z wyjaśnieniem.
Exit code 0 = wszystkie PASS, 1 = przynajmniej jeden FAIL.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
SHIM_DIR = ROOT / "services" / "gemma4_audio_runtime"


def _check(label: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    line = f"[{status}] {label}"
    if detail:
        line += f"\n       {detail}"
    print(line)
    return passed


def check_entrypoint() -> bool:
    """Main service entrypoint must reference services.multi_runtime."""
    script = ROOT / "scripts" / "llm" / "multi_runtime_service.sh"
    if not script.exists():
        return _check(
            "entrypoint uses services.multi_runtime.main",
            False,
            f"{script} does not exist",
        )
    content = script.read_text()
    ok = (
        "services.multi_runtime.main" in content and "services.multi_runtime" in content
    )
    return _check(
        "entrypoint uses services.multi_runtime.main",
        ok,
        "" if ok else f"{script.name} still references old entrypoint",
    )


def check_no_direct_engine_import_outside_shim() -> bool:
    """Non-shim files should not import Gemma4AudioEngine or Gemma4Daemon directly."""
    hits: list[str] = []
    forbidden = {"Gemma4AudioEngine", "Gemma4Daemon"}
    exclude = {
        ROOT / "services" / "gemma4_audio_runtime" / "engine.py",
        ROOT / "services" / "gemma4_audio_runtime" / "__init__.py",
    }

    for py in ROOT.rglob("*.py"):
        if py in exclude:
            continue
        if ".venv" in py.parts or "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden:
                hits.append(f"{py.relative_to(ROOT)}:{node.lineno} — {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in forbidden:
                hits.append(f"{py.relative_to(ROOT)}:{node.lineno} — .{node.attr}")

    ok = len(hits) == 0
    detail = ("\n       " + "\n       ".join(hits[:5])) if hits else ""
    if len(hits) > 5:
        detail += f"\n       ... and {len(hits) - 5} more"
    return _check(
        "no direct Gemma4AudioEngine/Gemma4Daemon references outside shim",
        ok,
        detail,
    )


def check_shim_is_thin() -> bool:
    """gemma4_audio_runtime files should only re-export — no new logic."""
    thick: list[str] = []
    for shim_file in SHIM_DIR.glob("*.py"):
        content = shim_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        # Check for function/class definitions (sign of logic, not just re-exports)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                thick.append(f"{shim_file.name}:{node.lineno} — {node.name}")

    ok = len(thick) == 0
    detail = ("\n       " + "\n       ".join(thick[:5])) if thick else ""
    return _check(
        "gemma4_audio_runtime shim contains no new function/class definitions",
        ok,
        detail,
    )


def check_multi_runtime_models_is_canonical() -> bool:
    """venom_core/services/multi_runtime_models.py must exist and be non-empty."""
    target = ROOT / "venom_core" / "services" / "multi_runtime_models.py"
    if not target.exists():
        return _check(
            "multi_runtime_models.py is canonical model helper",
            False,
            f"{target.relative_to(ROOT)} does not exist",
        )
    content = target.read_text()
    has_functions = "def multi_runtime" in content
    return _check(
        "multi_runtime_models.py is canonical model helper",
        has_functions,
        "" if has_functions else "File exists but no multi_runtime_* functions found",
    )


def check_multi_runtime_package_exists() -> bool:
    """services/multi_runtime/ package must exist with all core files."""
    pkg = ROOT / "services" / "multi_runtime"
    required = ["__init__.py", "engine.py", "main.py", "schemas.py", "audio.py"]
    missing = [f for f in required if not (pkg / f).exists()]
    ok = len(missing) == 0
    return _check(
        "services/multi_runtime/ package has all core files",
        ok,
        ("Missing: " + ", ".join(missing)) if missing else "",
    )


def check_test_imports_use_multi_runtime() -> bool:
    """Main daemon tests must import from services.multi_runtime, not gemma4_audio_runtime."""
    test_files = [
        ROOT / "tests" / "test_214a_gemma4_daemon.py",
        ROOT / "tests" / "test_214a_daemon_management.py",
    ]
    bad_imports: list[str] = []
    for tf in test_files:
        if not tf.exists():
            continue
        content = tf.read_text()
        if "import services.gemma4_audio_runtime" in content:
            bad_imports.append(tf.name)
        if "from services.gemma4_audio_runtime" in content:
            bad_imports.append(tf.name)

    ok = len(bad_imports) == 0
    return _check(
        "primary test files import from services.multi_runtime",
        ok,
        ("Still importing gemma4_audio_runtime: " + ", ".join(bad_imports))
        if bad_imports
        else "",
    )


def main() -> int:
    print("=" * 60)
    print("217B Exit Guard — migracja multi_runtime")
    print("=" * 60)

    results = [
        check_entrypoint(),
        check_multi_runtime_package_exists(),
        check_multi_runtime_models_is_canonical(),
        check_shim_is_thin(),
        check_no_direct_engine_import_outside_shim(),
        check_test_imports_use_multi_runtime(),
    ]

    passed = sum(results)
    total = len(results)

    print()
    print("=" * 60)
    if all(results):
        print(f"EXIT GUARD: {passed}/{total} PASSED — migracja zakończona poprawnie")
        return 0

    failed = total - passed
    print(f"EXIT GUARD: {failed}/{total} FAILED — sprawdź wyniki powyżej")
    return 1


if __name__ == "__main__":
    sys.exit(main())
