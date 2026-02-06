import argparse
import ast
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
    "pil",
    "matplotlib",
    "seaborn",
}

IMPORT_TO_PACKAGE = {
    "github": "pygithub",
    "git": "gitpython",
    "pil": "pillow",
    "cv2": "opencv-python-headless",
    "dotenv": "python-dotenv",
    "yaml": "pyyaml",
    "bs4": "beautifulsoup4",
    "duckduckgo_search": "duckduckgo-search",
    "tavily": "tavily-python",
    "google_auth_oauthlib": "google-auth-oauthlib",
    "googleapiclient": "google-api-python-client",
    "pydantic_settings": "pydantic-settings",
    "semantic_kernel": "semantic-kernel",
}

PROJECT_INTERNAL_ROOTS = {
    "venom_core",
    "venom_spore",
    "tests",
    "scripts",
    "config",
    "examples",
    "web_next",
    "docs",
    "docs_dev",
    "workspace",
}


@dataclass
class AuditResult:
    forbidden: set[str] = field(default_factory=set)
    missing: set[str] = field(default_factory=set)
    parse_errors: set[str] = field(default_factory=set)

    def merge(self, other: "AuditResult") -> None:
        self.forbidden.update(other.forbidden)
        self.missing.update(other.missing)
        self.parse_errors.update(other.parse_errors)


class ImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.in_function = False
        self.optional_import_guard_depth = 0
        self.top_level_roots: set[str] = set()
        self.venom_modules: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        if not self.in_function and self.optional_import_guard_depth == 0:
            for alias in node.names:
                module_name = alias.name
                self.top_level_roots.add(module_name.split(".")[0])
                if module_name.startswith("venom_core"):
                    self.venom_modules.add(module_name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if (
            not self.in_function
            and self.optional_import_guard_depth == 0
            and node.module
        ):
            self.top_level_roots.add(node.module.split(".")[0])
            if node.module.startswith("venom_core"):
                self.venom_modules.add(node.module)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        old_in_function = self.in_function
        self.in_function = True
        self.generic_visit(node)
        self.in_function = old_in_function

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_If(self, node: ast.If) -> None:
        # Imports guarded with TYPE_CHECKING are runtime-safe and should be ignored.
        if _is_type_checking_guard(node.test):
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        optional_try = _is_optional_import_try(node)
        if optional_try:
            self.optional_import_guard_depth += 1
        for child in node.body:
            self.visit(child)
        if optional_try:
            self.optional_import_guard_depth -= 1

        for child in node.handlers:
            self.visit(child)
        for child in node.orelse:
            self.visit(child)
        for child in node.finalbody:
            self.visit(child)


def _is_type_checking_guard(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    if isinstance(node, ast.Attribute):
        return node.attr == "TYPE_CHECKING"
    return False


def _is_optional_import_try(node: ast.Try) -> bool:
    if not node.handlers:
        return False

    for handler in node.handlers:
        if handler.type is None:
            return True
        if isinstance(handler.type, ast.Name) and handler.type.id in {
            "ImportError",
            "ModuleNotFoundError",
            "Exception",
            "BaseException",
        }:
            return True
        if isinstance(handler.type, ast.Attribute) and handler.type.attr in {
            "ImportError",
            "ModuleNotFoundError",
            "Exception",
            "BaseException",
        }:
            return True
        if isinstance(handler.type, ast.Tuple):
            for element in handler.type.elts:
                if isinstance(element, ast.Name) and element.id in {
                    "ImportError",
                    "ModuleNotFoundError",
                    "Exception",
                    "BaseException",
                }:
                    return True
    return False


def _normalize_requirement_name(raw: str) -> str:
    return raw.strip().lower().replace("_", "-")


def load_requirements(req_path: Path) -> set[str]:
    allowed_packages: set[str] = set()
    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r ") or line.startswith("--requirement "):
            continue

        pkg_name = (
            line.split(">=")[0]
            .split("==")[0]
            .split("<")[0]
            .split("[")[0]
            .split(";")[0]
            .strip()
        )
        if pkg_name:
            allowed_packages.add(_normalize_requirement_name(pkg_name))

    return allowed_packages


def read_ci_lite_tests(config_path: Path) -> list[str]:
    tests: list[str] = []
    for line in config_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tests.append(line)
    return tests


def _stdlib_modules() -> set[str]:
    stdlib = set(getattr(sys, "stdlib_module_names", set()))
    stdlib.update(
        {
            "typing_extensions",
            "pytest",
        }
    )
    return stdlib


def _is_external_import(import_root: str, root_dir: Path, stdlib: set[str]) -> bool:
    normalized = import_root.lower()
    if normalized in stdlib or normalized in PROJECT_INTERNAL_ROOTS:
        return False
    if (root_dir / import_root).is_dir() or (root_dir / f"{import_root}.py").exists():
        return False
    return True


def _map_import_to_requirement(import_root: str) -> str:
    normalized = import_root.lower()
    mapped = IMPORT_TO_PACKAGE.get(normalized, normalized)
    return _normalize_requirement_name(mapped)


def _resolve_venom_module(module_name: str, root_dir: Path) -> Path | None:
    parts = module_name.split(".")
    path = root_dir.joinpath(*parts)
    if path.is_dir() and (path / "__init__.py").exists():
        return path / "__init__.py"
    py_file = path.with_suffix(".py")
    if py_file.exists():
        return py_file
    return None


def _parse_file(file_path: Path) -> tuple[ImportVisitor | None, str | None]:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except Exception as e:
        return None, str(e)

    visitor = ImportVisitor()
    visitor.visit(tree)
    return visitor, None


def audit_file(
    file_path: Path,
    root_dir: Path,
    allowed_packages: set[str],
    stdlib: set[str],
    seen: set[Path] | None = None,
    depth: int = 0,
    max_depth: int = 12,
) -> AuditResult:
    result = AuditResult()

    if seen is None:
        seen = set()
    if depth > max_depth or file_path in seen or not file_path.exists():
        return result
    seen.add(file_path)

    visitor, parse_error = _parse_file(file_path)
    if parse_error:
        result.parse_errors.add(
            f"{file_path.relative_to(root_dir)} -> błąd parsowania: {parse_error}"
        )
        return result
    assert visitor is not None

    for import_root in visitor.top_level_roots:
        import_root_lower = import_root.lower()
        rel_file = file_path.relative_to(root_dir)

        if import_root_lower in DENY_LIST:
            result.forbidden.add(f"{import_root} (found in {rel_file})")
            continue

        if _is_external_import(import_root, root_dir, stdlib):
            requirement_name = _map_import_to_requirement(import_root)
            if requirement_name not in allowed_packages:
                result.missing.add(
                    f"{import_root} -> {requirement_name} (found in {rel_file})"
                )

    for module_name in visitor.venom_modules:
        resolved = _resolve_venom_module(module_name, root_dir)
        if resolved is None:
            continue
        result.merge(
            audit_file(
                resolved,
                root_dir=root_dir,
                allowed_packages=allowed_packages,
                stdlib=stdlib,
                seen=seen,
                depth=depth + 1,
                max_depth=max_depth,
            )
        )

    return result


def _format_timeout_error(test_file: str, timeout_seconds: int) -> str:
    return (
        f"{test_file}: import przekroczył {timeout_seconds}s "
        "(podejrzenie blokującego importu)"
    )


def run_import_smoke_safe(
    root_dir: Path, test_files: list[str], timeout_seconds: int = 30
) -> dict[str, str]:
    failures: dict[str, str] = {}
    for test_file in test_files:
        module_name = test_file.removesuffix(".py").replace("/", ".")
        try:
            process = subprocess.run(
                [sys.executable, "-c", f"import {module_name}"],
                cwd=root_dir,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            failures[test_file] = _format_timeout_error(test_file, timeout_seconds)
            continue
        if process.returncode != 0:
            stderr = process.stderr.strip() or process.stdout.strip() or "unknown error"
            failures[test_file] = stderr
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit zależności dla profilu CI Lite (statyczny + import smoke)."
    )
    parser.add_argument(
        "--requirements",
        default="requirements-ci-lite.txt",
        help="Ścieżka do pliku requirements dla CI lite",
    )
    parser.add_argument(
        "--config",
        default="config/pytest-groups/ci-lite.txt",
        help="Ścieżka do listy testów CI lite",
    )
    parser.add_argument(
        "--import-smoke",
        action="store_true",
        help="Uruchom dodatkowo szybki test importów modułów testowych",
    )
    args = parser.parse_args()

    root_dir = Path.cwd()
    req_path = root_dir / args.requirements
    config_path = root_dir / args.config

    if not req_path.exists() or not config_path.exists():
        print("❌ Brak plików konfiguracyjnych!")
        return 1

    allowed_packages = load_requirements(req_path)
    test_files = read_ci_lite_tests(config_path)
    stdlib = _stdlib_modules()

    print(f"🔍 Rozpoczynam audyt {len(test_files)} plików testowych...\n")

    total_issues = 0
    for test_file in test_files:
        print(f"Checking {test_file}...")
        issues = audit_file(
            root_dir / test_file,
            root_dir=root_dir,
            allowed_packages=allowed_packages,
            stdlib=stdlib,
        )

        if issues.forbidden:
            print("  ❌ ZNALEZIONO NIEDOZWOLONE PAKIETY:")
            for issue in sorted(issues.forbidden):
                print(f"     - {issue}")
            total_issues += 1

        if issues.missing:
            print("  ❌ BRAKUJĄCE ZALEŻNOŚCI RUNTIME W REQUIREMENTS-CI-LITE:")
            for issue in sorted(issues.missing):
                print(f"     - {issue}")
            total_issues += 1

        if issues.parse_errors:
            print("  ❌ BŁĘDY PARSOWANIA PLIKÓW:")
            for issue in sorted(issues.parse_errors):
                print(f"     - {issue}")
            total_issues += 1

        if not (issues.forbidden or issues.missing or issues.parse_errors):
            print("  ✅ OK")

    if args.import_smoke:
        print("\n🧪 Import smoke dla modułów testowych CI lite...")
        smoke_failures = run_import_smoke_safe(root_dir, test_files)
        if smoke_failures:
            total_issues += len(smoke_failures)
            print("  ❌ IMPORT SMOKE FAILED:")
            for test_file, error in sorted(smoke_failures.items()):
                print(f"     - {test_file}")
                print(f"       {error.splitlines()[-1]}")
        else:
            print("  ✅ Import smoke OK")

    if total_issues > 0:
        print(
            f"\n🚫 Audyt zakończony porażką. Znaleziono problemy w {total_issues} przypadkach."
        )
        return 1

    print(
        "\n✨ Wszystkie testy czyste! Brak brakujących zależności i importy są poprawne."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
