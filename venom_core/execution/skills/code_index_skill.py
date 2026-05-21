"""Moduł: code_index_skill - przeszukiwanie kodu projektu przez ripgrep i AST."""

import ast
import json
import subprocess
from dataclasses import dataclass, field
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


@dataclass
class _PythonSymbolCollector:
    """Zbiera symbole z drzewa AST bez rozbudowanej logiki w funkcji wywołującej."""

    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)

    def add_node(self, node: ast.AST) -> None:
        if isinstance(node, ast.ClassDef):
            self.classes.append(node.name)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.functions.append(node.name)
            return
        if isinstance(node, ast.Import):
            self.imports.extend(alias.name for alias in node.names)
            return
        if isinstance(node, ast.ImportFrom):
            self.imports.append(node.module or "")


@dataclass
class _RgJsonStreamReducer:
    """Stanowy reduktor liniowego JSON outputu ripgrep."""

    context_lines: int
    matches: List[CodeMatch] = field(default_factory=list)
    context_before_by_file: Dict[str, List[str]] = field(default_factory=dict)
    active_matches_by_file: Dict[str, List[CodeMatch]] = field(default_factory=dict)

    def feed_line(self, raw_line: str) -> None:
        line = raw_line.strip()
        if not line:
            return

        entry = self._parse_entry(line)
        if entry is None:
            return

        entry_type, file_path, line_no, text = self._extract_entry_fields(entry)
        if entry_type == "end":
            self._reset_state()
            return
        if not file_path or not isinstance(line_no, int):
            return

        if entry_type in ("context", "match"):
            self._update_active_matches(file_path, line_no, text)
        if entry_type == "context":
            self._append_context_before(file_path, text)
        elif entry_type == "match":
            self._append_match(file_path, line_no, text)

    def _parse_entry(self, line: str) -> Optional[dict]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(entry, dict):
            return None
        return entry

    @staticmethod
    def _extract_entry_fields(
        entry: dict,
    ) -> tuple[str, Optional[str], Optional[int], str]:
        entry_type = str(entry.get("type", ""))
        data = entry.get("data", {})
        if not isinstance(data, dict):
            data = {}
        path_data = data.get("path", {})
        if not isinstance(path_data, dict):
            path_data = {}
        lines_data = data.get("lines", {})
        if not isinstance(lines_data, dict):
            lines_data = {}
        file_path = path_data.get("text")
        line_no = data.get("line_number")
        text = str(lines_data.get("text", "")).rstrip("\n")
        return (
            entry_type,
            file_path if isinstance(file_path, str) else None,
            line_no if isinstance(line_no, int) else None,
            text,
        )

    def _update_active_matches(self, file_path: str, line_no: int, text: str) -> None:
        active = self.active_matches_by_file.get(file_path, [])
        if not active:
            return

        updated_active: List[CodeMatch] = []
        for match in active:
            if match.line < line_no <= match.line + self.context_lines:
                if len(match.context_after) < self.context_lines:
                    match.context_after.append(text)
            if line_no < match.line + self.context_lines:
                updated_active.append(match)
        self.active_matches_by_file[file_path] = updated_active

    def _append_context_before(self, file_path: str, text: str) -> None:
        before = self.context_before_by_file.setdefault(file_path, [])
        before.append(text)
        if len(before) > self.context_lines:
            before.pop(0)

    def _append_match(self, file_path: str, line_no: int, text: str) -> None:
        before = self.context_before_by_file.get(file_path, [])
        match = CodeMatch(
            file=file_path,
            line=line_no,
            text=text,
            context_before=list(before),
            context_after=[],
        )
        self.matches.append(match)
        self.active_matches_by_file.setdefault(file_path, []).append(match)
        self.context_before_by_file[file_path] = []

    def _reset_state(self) -> None:
        self.context_before_by_file.clear()
        self.active_matches_by_file.clear()


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
        reducer = _RgJsonStreamReducer(context_lines=context_lines)
        for line in raw.splitlines():
            reducer.feed_line(line)
        return reducer.matches

    def _resolve_workspace_path(self, file_path: str) -> Path:
        candidate = (self.workspace_root / file_path).resolve()
        root = self.workspace_root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as e:
            raise ValueError(f"Ścieżka poza workspace: {file_path}") from e
        return candidate

    def _build_search_command(
        self,
        query: str,
        path_glob: Optional[str],
        max_results: int,
        context_lines: int,
        case_sensitive: bool,
    ) -> List[str]:
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
        return cmd

    def _run_search_command(self, cmd: List[str]) -> Optional[str]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            self.logger.error("ripgrep timeout")
            return None
        except Exception as e:
            self.logger.error(f"Błąd ripgrep: {e}")
            return None

        if result.returncode > 1:
            self.logger.error(
                f"ripgrep błąd (code={result.returncode}): {result.stderr.strip()[:200]}"
            )
            return None
        return result.stdout

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

        cmd = self._build_search_command(
            query=query,
            path_glob=path_glob,
            max_results=max_results,
            context_lines=context_lines,
            case_sensitive=case_sensitive,
        )
        raw_output = self._run_search_command(cmd)
        if raw_output is None:
            return []

        matches = self._parse_rg_json_output(raw_output, context_lines)
        return matches[:max_results]

    def get_file_symbols(self, file_path: str) -> FileSymbols:
        return self._collect_file_symbols(file_path)

    def _collect_file_symbols(self, file_path: str) -> FileSymbols:
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
            return self._empty_file_symbols(file_path)

        if not self._is_python_source_file(path):
            return self._empty_file_symbols(str(path))

        return self._extract_file_symbols(path)

    @staticmethod
    def _empty_file_symbols(file_path: str) -> FileSymbols:
        return FileSymbols(file=file_path, classes=[], functions=[], imports=[])

    @staticmethod
    def _is_python_source_file(path: Path) -> bool:
        return path.exists() and path.suffix == ".py"

    @staticmethod
    def _dedupe(values: List[str]) -> List[str]:
        return list(dict.fromkeys(values))

    def _extract_file_symbols(self, path: Path) -> FileSymbols:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as e:
            self.logger.debug(f"SyntaxError w {path}: {e}")
            return self._empty_file_symbols(str(path))
        except Exception as e:
            self.logger.error(f"Błąd AST {path}: {e}")
            return self._empty_file_symbols(str(path))

        collector = _PythonSymbolCollector()
        for node in ast.walk(tree):
            collector.add_node(node)

        return FileSymbols(
            file=str(path),
            classes=self._dedupe(collector.classes),
            functions=self._dedupe(collector.functions),
            imports=self._dedupe(collector.imports),
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
