"""Moduł: file_skill - zarządzanie operacjami plikowymi z sandboxingiem."""

import os
from pathlib import Path
from typing import Annotated, Optional

import aiofiles
from semantic_kernel.functions import kernel_function

from venom_core.execution.skills.base_skill import (
    BaseSkill,
    async_safe_action,
    safe_action,
)


class FileSkill(BaseSkill):
    """
    Skill do bezpiecznych operacji plikowych.
    Wszystkie operacje są ograniczone do WORKSPACE_ROOT.

    Rozszerza BaseSkill o:
    - write_file
    - read_file
    - list_files
    - file_exists
    """

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Inicjalizacja FileSkill.
        """
        super().__init__(workspace_root)

    @kernel_function(
        name="write_file",
        description="Zapisuje treść do pliku w workspace. Tworzy katalogi jeśli nie istnieją.",
    )
    @async_safe_action
    async def write_file(
        self,
        file_path: Annotated[
            str,
            "Ścieżka do pliku względem workspace (np. 'test.py', 'subdir/file.txt')",
        ],
        content: Annotated[str, "Treść do zapisania w pliku"],
    ) -> str:
        """
        Zapisuje treść do pliku asynchronicznie.
        """
        safe_path = self.validate_path(file_path)

        # Utwórz katalogi nadrzędne jeśli nie istnieją
        safe_path.parent.mkdir(parents=True, exist_ok=True)

        # Zapisz plik asynchronicznie
        async with aiofiles.open(safe_path, "w", encoding="utf-8") as f:
            await f.write(content)

        self.logger.info(f"Zapisano plik: {safe_path}")
        return f"Plik '{file_path}' został pomyślnie zapisany ({len(content)} znaków)"

    @kernel_function(
        name="read_file",
        description="Odczytuje treść pliku z workspace.",
    )
    @async_safe_action
    async def read_file(
        self,
        file_path: Annotated[str, "Ścieżka do pliku względem workspace"],
    ) -> str:
        """
        Odczytuje treść pliku asynchronicznie.
        """
        safe_path = self.validate_path(file_path)

        if not safe_path.exists():
            raise FileNotFoundError(f"Plik '{file_path}' nie istnieje")

        if not safe_path.is_file():
            raise IOError(f"'{file_path}' nie jest plikiem")

        # Odczytaj plik asynchronicznie
        async with aiofiles.open(safe_path, "r", encoding="utf-8") as f:
            content = await f.read()

        self.logger.info(f"Odczytano plik: {safe_path} ({len(content)} znaków)")
        return content

    @kernel_function(
        name="list_files",
        description="Listuje pliki i katalogi w workspace. Może listować rekurencyjnie z konfigurowalną głębokością.",
    )
    @safe_action
    def list_files(
        self,
        directory: Annotated[
            str, "Katalog względem workspace (domyślnie '.', czyli root workspace)"
        ] = ".",
        recursive: Annotated[
            bool, "Czy listować rekurencyjnie (domyślnie False)"
        ] = False,
        max_depth: Annotated[int, "Maksymalna głębokość rekurencji (domyślnie 3)"] = 3,
    ) -> str:
        """
        Listuje pliki i katalogi w podanym katalogu.
        """
        safe_path = self.validate_path(directory)
        if not safe_path.exists():
            return f"Katalog '{directory}' nie istnieje"
        if not safe_path.is_dir():
            return f"'{directory}' nie jest katalogiem"
        if recursive:
            return self._list_files_recursive(directory, safe_path, max_depth)
        return self._list_files_flat(directory, safe_path)

    def _list_files_recursive(
        self, directory: str, safe_path: Path, max_depth: int
    ) -> str:
        items = [
            f"Zawartość katalogu '{directory}' (rekurencyjnie, max {max_depth} poziomy):\n"
        ]
        skipped_files = 0

        for root, dirs, files in os.walk(safe_path):
            depth = self._get_relative_depth(root, safe_path)
            if depth > max_depth:
                dirs.clear()
                continue
            indent = "  " * depth
            self._append_recursive_dirs(items, dirs, root, depth, max_depth)
            if depth >= max_depth:
                dirs.clear()
            skipped_files += self._append_recursive_files(items, files, root, indent)

        if skipped_files > 0:
            self.logger.warning(f"Pominięto {skipped_files} niedostępnych plików")
        if len(items) == 1:
            items.append("  (katalog pusty)")
        self.logger.info(
            f"Wylistowano {len(items) - 1} elementów w: {safe_path} (recursive=True)"
        )
        return "\n".join(items)

    def _list_files_flat(self, directory: str, safe_path: Path) -> str:
        items = []
        for item in sorted(safe_path.iterdir()):
            stat_result = item.stat()
            item_type = "katalog" if item.is_dir() else "plik"
            relative_path = item.relative_to(self.workspace_root)
            size = str(stat_result.st_size) if item.is_file() else "-"
            items.append(f"  [{item_type}] {relative_path} ({size} bajtów)")

        if not items:
            return f"Katalog '{directory}' jest pusty"

        items.insert(0, f"Zawartość katalogu '{directory}':")
        self.logger.info(
            f"Wylistowano {len(items) - 1} elementów w: {safe_path} (recursive=False)"
        )
        return "\n".join(items)

    def _get_relative_depth(self, root: str, safe_path: Path) -> int:
        try:
            return len(Path(root).relative_to(safe_path).parts)
        except ValueError:
            return 0

    def _append_recursive_dirs(
        self,
        items: list[str],
        dirs: list[str],
        root: str,
        depth: int,
        max_depth: int,
    ) -> None:
        if depth >= max_depth:
            return
        indent = "  " * depth
        for dir_name in sorted(dirs):
            dir_path = Path(root) / dir_name
            rel_path = dir_path.relative_to(self.workspace_root)
            items.append(f"{indent}[katalog] {rel_path}/")

    def _append_recursive_files(
        self, items: list[str], files: list[str], root: str, indent: str
    ) -> int:
        skipped = 0
        for file_name in sorted(files):
            file_path = Path(root) / file_name
            try:
                stat_result = file_path.stat()
                size = str(stat_result.st_size)
                rel_path = file_path.relative_to(self.workspace_root)
                items.append(f"{indent}[plik] {rel_path} ({size} bajtów)")
            except Exception:
                skipped += 1
        return skipped

    @kernel_function(
        name="file_exists",
        description="Sprawdza czy plik lub katalog istnieje w workspace.",
    )
    def file_exists(
        self,
        file_path: Annotated[str, "Ścieżka do pliku/katalogu względem workspace"],
    ) -> str:
        # Ten wrapper manualny symuluje safe_action dla synchronicznej metody
        # (metody kernel_function w SK mogą być sync lub async)
        try:
            safe_path = self.validate_path(file_path)
            exists = safe_path.exists()
            self.logger.info(f"Sprawdzono istnienie: {safe_path} = {exists}")
            return "True" if exists else "False"
        except Exception as e:
            # Używamy logiki z BaseSkill.safe_action
            if hasattr(self, "logger"):
                self.logger.error(f"Błąd w file_exists: {e}", exc_info=True)
            return f"❌ Wystąpił błąd: {str(e)}"
