import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set

# Konfiguracja
DENY_LIST = {
    "transformers",
    "torch",
    "playwright",
    "lancedb",
    "graphrag",
    "onnxruntime",
    "faster_whisper",
    "piper",
    "cv2",
    "PIL",
    "matplotlib",
    "seaborn",
}

ALLOWED_PACKAGES = set()


def load_requirements(req_path: str):
    """Wczytuje dozwolone pakiety z requirements-ci-lite.txt"""
    with open(req_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Uproszczone parsowanie nazwy pakietu (np. "fastapi>=0.112.0" -> "fastapi")
            pkg_name = (
                line.split(">=")[0]
                .split("==")[0]
                .split("<")[0]
                .split("[")[0]
                .strip()
                .lower()
            )
            ALLOWED_PACKAGES.add(pkg_name)

    # Dodaj standardowe biblioteki/narzędzia, które mogą być używane a nie są w reqs (np. framework testowy)
    ALLOWED_PACKAGES.add("unittest")
    ALLOWED_PACKAGES.add("typing")
    ALLOWED_PACKAGES.add("pathlib")
    ALLOWED_PACKAGES.add("os")
    ALLOWED_PACKAGES.add("sys")
    ALLOWED_PACKAGES.add("json")
    ALLOWED_PACKAGES.add("asyncio")
    ALLOWED_PACKAGES.add("datetime")
    ALLOWED_PACKAGES.add("re")
    ALLOWED_PACKAGES.add("logging")
    ALLOWED_PACKAGES.add("collections")
    ALLOWED_PACKAGES.add("uuid")
    ALLOWED_PACKAGES.add("contextlib")


class ImportVisitor(ast.NodeVisitor):
    def __init__(self):
        self.imports = set()
        self.in_function = False

    def visit_Import(self, node):
        if not self.in_function:
            for alias in node.names:
                self.imports.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if not self.in_function and node.module:
            self.imports.add(node.module.split(".")[0])
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        old_in_func = self.in_function
        self.in_function = True
        self.generic_visit(node)
        self.in_function = old_in_func

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_If(self, node):
        # Ignore imports inside 'if TYPE_CHECKING:'
        is_type_checking = False
        try:
            if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                is_type_checking = True
            elif (
                isinstance(node.test, ast.Attribute)
                and node.test.attr == "TYPE_CHECKING"
            ):
                is_type_checking = True
        except Exception:
            pass

        if not is_type_checking:
            self.generic_visit(node)


def get_imports_from_file(file_path: Path) -> Set[str]:
    """Parsuje plik i zwraca zbiór importowanych modułów (tylko top-level)."""
    if not file_path.exists():
        return set()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except Exception as e:
        print(f"⚠️  Błąd parsowania {file_path}: {e}")
        return set()

    visitor = ImportVisitor()
    visitor.visit(tree)
    return visitor.imports


def resolve_venom_module(module_name: str, root_dir: Path) -> Path:
    """Zamienia import 'venom_core.xxx' na ścieżkę pliku."""
    parts = module_name.split(".")
    path = root_dir.joinpath(*parts)

    # Sprawdź czy to pakiet (folder) czy moduł (plik.py)
    if path.is_dir() and (path / "__init__.py").exists():
        return path / "__init__.py"

    py_file = path.with_suffix(".py")
    if py_file.exists():
        return py_file

    return None


CHECKED_FILES = set()
MAX_RECURSION = 3


def audit_file(file_path: Path, root_dir: Path, depth=0) -> Dict[str, List[str]]:
    """Rekurencyjnie sprawdza importy w pliku."""
    if depth > MAX_RECURSION:
        return {}

    file_str = str(file_path)
    if file_str in CHECKED_FILES:
        return {}
    CHECKED_FILES.add(file_str)

    imports = get_imports_from_file(file_path)
    issues = {"forbidden": [], "missing": []}

    for imp in imports:
        imp_lower = imp.lower()

        # 1. Sprawdź DENY_LIST
        if imp_lower in DENY_LIST:
            issues["forbidden"].append(
                f"{imp} (found in {file_path.relative_to(root_dir)})"
            )
            continue

        # 2. Jeśli to venom_core, wejdź głębiej
        # Dla rekurencji musimy znaleźć lokalne importy top-level
        if imp_lower == "venom_core":
            pass  # generic handle

    if depth < MAX_RECURSION:
        # Precyzyjne szukanie venom_core imports
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read())
                visitor = ImportVisitor()
                visitor.visit(tree)
                # visitor.imports ma top-level

                # Musimy sparsować dokładne from ... import
                # Quick hack: iterujemy po nodach znowu tylko dla venom_core
                # (Wiem, mało wydajne, ale proste)
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.ImportFrom)
                        and node.module
                        and node.module.startswith("venom_core")
                    ):
                        # Check scope manually? No, rely on visitor results?
                        # Visitor gives top-level modules like 'venom_core'
                        # But we need 'venom_core.memory.vector_store'
                        pass
            except Exception:
                pass

        # Better recursion logic:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        class VenomImportVisitor(ast.NodeVisitor):
            def __init__(self):
                self.venom_paths = []
                self.in_function = False

            def visit_ImportFrom(self, node):
                if (
                    not self.in_function
                    and node.module
                    and node.module.startswith("venom_core")
                ):
                    self.venom_paths.append(node.module)
                self.generic_visit(node)

            def visit_FunctionDef(self, node):
                old = self.in_function
                self.in_function = True
                self.generic_visit(node)
                self.in_function = old

            def visit_AsyncFunctionDef(self, node):
                self.visit_FunctionDef(node)

        v_visitor = VenomImportVisitor()
        v_visitor.visit(tree)

        for mod_name in v_visitor.venom_paths:
            resolved = resolve_venom_module(mod_name, root_dir)
            if resolved:
                sub_issues = audit_file(resolved, root_dir, depth + 1)
                issues["forbidden"].extend(sub_issues.get("forbidden", []))

    return issues


def main():
    root_dir = Path(os.getcwd())
    req_path = root_dir / "requirements-ci-lite.txt"
    config_path = root_dir / "config/pytest-groups/ci-lite.txt"

    if not req_path.exists() or not config_path.exists():
        print("❌ Brak plików konfiguracyjnych!")
        sys.exit(1)

    load_requirements(req_path)

    with open(config_path, "r") as f:
        test_files = [line.strip() for line in f if line.strip()]

    print(f"🔍 Rozpoczynam audyt {len(test_files)} plików testowych...\n")

    total_issues = 0

    for test_file in test_files:
        path = root_dir / test_file
        print(f"Checking {test_file}...")

        # Reset checked files for each test root to ensure full path coverage for that test
        # (Though caching is efficient, we want to report the chain for each test if needed,
        # but global cache is faster. Using global set for speed.)
        # CHECKED_FILES.clear() # uncomment for verbose per-file analysis

        issues = audit_file(path, root_dir)

        if issues["forbidden"]:
            print("  ❌ ZNALEZIONO NIEDOZWOLONE PAKIETY:")
            for issue in set(issues["forbidden"]):
                print(f"     - {issue}")
            total_issues += 1
        else:
            print("  ✅ OK")

    if total_issues > 0:
        print(
            f"\n🚫 Audyt zakończony porażką. Znaleziono problemy w {total_issues} plikach."
        )
        sys.exit(1)
    else:
        print("\n✨ Wszystkie testy czyste! Żaden nie importuje ciężkich pakietów.")
        sys.exit(0)


if __name__ == "__main__":
    main()
