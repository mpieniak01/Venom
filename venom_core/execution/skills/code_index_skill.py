"""Moduł: code_index_skill - przeszukiwanie kodu projektu przez ripgrep i AST."""

import ast
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Dict, List, Optional

from semantic_kernel.functions import kernel_function

from venom_core.execution.skills.base_skill import BaseSkill, async_safe_action


@dataclass
class CodeMatch:
    """Pojedyncze trafienie w kodzie."""

    file: str
    line: int
    text: str
    context_before: List[str]
    context_after: List[str]

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "text": self.text,
            "context_before": self.context_before,
            "context_after": self.context_after,
        }

    def format_snippet(self) -> str:
        lines = []
        start = self.line - len(self.context_before)
        for i, c in enumerate(self.context_before):
            lines.append(f"  {start + i}: {c}")
        lines.append(f"→ {self.line}: {self.text}")
        for i, c in enumerate(self.context_after):
            lines.append(f"  {self.line + 1 + i}: {c}")
        return "\n".join(lines)


@dataclass
class FileSymbols:
    """Symbole wyekstrahowane z pliku Python."""

    file: str
    classes: List[str]
    functions: List[str]
    imports: List[str]

    def format_summary(self) -> str:
        parts = [f"Plik: {self.file}"]
        if self.classes:
            parts.append(f"Klasy: {', '.join(self.classes)}")
        if self.functions:
            parts.append(f"Funkcje: {', '.join(self.functions[:20])}")
        if self.imports:
            parts.append(f"Importy: {', '.join(self.imports[:10])}")
        return "\n".join(parts)


class CodeIndexSkill(BaseSkill):
    """
    Skill do przeszukiwania kodu projektu.

    Używa ripgrep do szybkiego przeszukiwania wzorców i Python AST do
    ekstrakcji symboli z plików .py. Nie wymaga wcześniejszego zbudowania
    indeksu – działa na żywo na workspace.
    """

    _RG_BINARY = "rg"
    _DEFAULT_GLOBS = ["*.py", "*.ts", "*.tsx", "*.md", "*.json", "*.yaml", "*.yml"]
    _SKIP_DIRS = [
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "out",
        "dist",
        ".mypy_cache",
        "models_cache",
        "models",
    ]

    def __init__(self, workspace_root: Optional[str] = None):
        super().__init__(workspace_root)
        self._rg_available = self._check_rg()

    def _check_rg(self) -> bool:
        try:
            result = subprocess.run(
                [self._RG_BINARY, "--version"],
                capture_output=True,
                timeout=3,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _build_skip_args(self) -> List[str]:
        args = []
        for d in self._SKIP_DIRS:
            args += ["--glob", f"!{d}"]
            args += ["--glob", f"!**/{d}/**"]
        return args

    def _parse_rg_json_output(self, raw: str, context_lines: int) -> List[CodeMatch]:
        matches: List[CodeMatch] = []
        context_before_by_file: Dict[str, List[str]] = {}
        active_matches_by_file: Dict[str, List[CodeMatch]] = {}

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type")
            data = entry.get("data", {})
            file_path = data.get("path", {}).get("text")
            line_no = data.get("line_number")
            text = data.get("lines", {}).get("text", "").rstrip("\n")

            if (
                entry_type in ("context", "match")
                and file_path
                and isinstance(line_no, int)
            ):
                active = active_matches_by_file.get(file_path, [])
                if active and entry_type == "context":
                    updated_active: List[CodeMatch] = []
                    for m in active:
                        if m.line < line_no <= m.line + context_lines:
                            if len(m.context_after) < context_lines:
                                m.context_after.append(text)
                        if line_no < m.line + context_lines:
                            updated_active.append(m)
                    active_matches_by_file[file_path] = updated_active

            if entry_type == "context" and file_path:
                before = context_before_by_file.setdefault(file_path, [])
                before.append(text)
                if len(before) > context_lines:
                    before.pop(0)
            elif entry_type == "match" and file_path and isinstance(line_no, int):
                before = context_before_by_file.get(file_path, [])
                matches.append(
                    CodeMatch(
                        file=file_path,
                        line=line_no,
                        text=text,
                        context_before=list(before),
                        context_after=[],
                    )
                )
                active_matches_by_file.setdefault(file_path, []).append(matches[-1])
                context_before_by_file[file_path] = []
            elif entry_type == "end":
                context_before_by_file.clear()
                active_matches_by_file.clear()

        return matches

    def _resolve_workspace_path(self, file_path: str) -> Path:
        candidate = (self.workspace_root / file_path).resolve()
        root = self.workspace_root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as e:
            raise ValueError(f"Ścieżka poza workspace: {file_path}") from e
        return candidate

    def search_code(
        self,
        query: str,
        path_glob: Optional[str] = None,
        max_results: int = 10,
        context_lines: int = 2,
        case_sensitive: bool = False,
    ) -> List[CodeMatch]:
        """
        Przeszukuje kod projektu wzorcem (regex lub dosłowny tekst).

        Args:
            query: Wzorzec do wyszukania.
            path_glob: Glob filtrujący pliki, np. "*.py" (opcjonalny).
            max_results: Maksymalna liczba trafień.
            context_lines: Liczba linii kontekstu wokół trafienia.
            case_sensitive: Czy rozróżniać wielkość liter.

        Returns:
            Lista obiektów CodeMatch.
        """
        if not self._rg_available:
            self.logger.warning("ripgrep niedostępny, zwracam pustą listę")
            return []

        cmd = [
            self._RG_BINARY,
            "--json",
            f"--context={context_lines}",
            f"--max-count={max_results}",
        ]
        if not case_sensitive:
            cmd.append("--ignore-case")
        cmd += self._build_skip_args()
        if path_glob:
            cmd += ["--glob", path_glob]
        cmd += [query, str(self.workspace_root)]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode > 1:
                self.logger.error(
                    f"ripgrep błąd (code={result.returncode}): {result.stderr.strip()[:200]}"
                )
                return []
            matches = self._parse_rg_json_output(result.stdout, context_lines)
            return matches[:max_results]
        except subprocess.TimeoutExpired:
            self.logger.error("ripgrep timeout")
            return []
        except Exception as e:
            self.logger.error(f"Błąd ripgrep: {e}")
            return []

    def get_file_symbols(self, file_path: str) -> FileSymbols:
        """
        Ekstrahuje klasy, funkcje i importy z pliku Python przez AST.

        Args:
            file_path: Ścieżka do pliku .py (absolutna lub względem workspace).

        Returns:
            FileSymbols z listami klas, funkcji i importów.
        """
        try:
            path = self._resolve_workspace_path(file_path)
        except ValueError as e:
            self.logger.warning(str(e))
            return FileSymbols(file=file_path, classes=[], functions=[], imports=[])

        classes: List[str] = []
        functions: List[str] = []
        imports: List[str] = []

        if not path.exists() or path.suffix != ".py":
            return FileSymbols(
                file=str(path), classes=classes, functions=functions, imports=imports
            )

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, ast.FunctionDef):
                    functions.append(node.name)
                elif isinstance(node, ast.AsyncFunctionDef):
                    functions.append(node.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imports.append(module)
        except SyntaxError as e:
            self.logger.debug(f"SyntaxError w {path}: {e}")
        except Exception as e:
            self.logger.error(f"Błąd AST {path}: {e}")

        return FileSymbols(
            file=str(path),
            classes=list(dict.fromkeys(classes)),
            functions=list(dict.fromkeys(functions)),
            imports=list(dict.fromkeys(imports)),
        )

    def read_context(
        self,
        file_path: str,
        line: int,
        context_lines: int = 5,
    ) -> str:
        """
        Zwraca fragment pliku wokół wskazanej linii.

        Args:
            file_path: Ścieżka do pliku.
            line: Numer linii (1-indexed).
            context_lines: Liczba linii kontekstu w każdym kierunku.

        Returns:
            Fragment pliku jako tekst z numerami linii.
        """
        try:
            path = self._resolve_workspace_path(file_path)
        except ValueError as e:
            return f"❌ {e}"

        if not path.exists():
            return f"❌ Plik nie istnieje: {file_path}"

        try:
            all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            return f"❌ Błąd odczytu: {e}"

        total = len(all_lines)
        start = max(0, line - context_lines - 1)
        end = min(total, line + context_lines)

        result_lines = []
        for i, text in enumerate(all_lines[start:end], start=start + 1):
            marker = "→" if i == line else " "
            result_lines.append(f"{marker} {i:4d}: {text}")

        return "\n".join(result_lines)

    def format_matches_for_llm(
        self, matches: List[CodeMatch], max_chars: int = 3000
    ) -> str:
        """Formatuje wyniki wyszukiwania do wstawienia w kontekst LLM."""
        if not matches:
            return "Brak wyników."
        parts = []
        total = 0
        for m in matches:
            snippet = f"[{m.file}:{m.line}]\n{m.format_snippet()}"
            if total + len(snippet) > max_chars:
                break
            parts.append(snippet)
            total += len(snippet)
        return "\n\n".join(parts)

    @kernel_function(
        name="search_code",
        description=(
            "Przeszukuje kod projektu wzorcem tekstowym lub regex. "
            "Zwraca trafienia z kontekstem linii i ścieżkami plików."
        ),
    )
    @async_safe_action
    async def search_code_tool(
        self,
        query: Annotated[str, "Wzorzec do wyszukania (tekst lub regex)"],
        path_glob: Annotated[
            Optional[str], "Glob filtrujący pliki, np. '*.py' (opcjonalny)"
        ] = None,
        max_results: Annotated[int, "Maksymalna liczba wyników (domyślnie 10)"] = 10,
    ) -> str:
        matches = self.search_code(
            query=query, path_glob=path_glob, max_results=max_results
        )
        return self.format_matches_for_llm(matches)

    @kernel_function(
        name="get_file_symbols",
        description=(
            "Ekstrahuje symbole (klasy, funkcje, importy) z pliku Python. "
            "Przydatne do szybkiego przeglądu struktury modułu."
        ),
    )
    @async_safe_action
    async def get_file_symbols_tool(
        self,
        file_path: Annotated[str, "Ścieżka do pliku .py"],
    ) -> str:
        symbols = self.get_file_symbols(file_path)
        return symbols.format_summary()

    @kernel_function(
        name="read_file_context",
        description=(
            "Zwraca fragment pliku wokół wskazanej linii z numerami linii. "
            "Używaj po search_code aby zobaczyć pełny kontekst trafienia."
        ),
    )
    @async_safe_action
    async def read_context_tool(
        self,
        file_path: Annotated[str, "Ścieżka do pliku"],
        line: Annotated[int, "Numer linii (1-indexed)"],
        context_lines: Annotated[int, "Liczba linii kontekstu (domyślnie 5)"] = 5,
    ) -> str:
        return self.read_context(
            file_path=file_path, line=line, context_lines=context_lines
        )
