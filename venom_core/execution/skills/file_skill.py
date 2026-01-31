"""Moduł: file_skill - zarządzanie operacjami plikowymi z sandboxingiem."""

import os
from pathlib import Path
from typing import Annotated, Optional

import aiofiles  # type: ignore[import-untyped]
from semantic_kernel.functions import kernel_function

from venom_core.execution.skills.base_skill import BaseSkill, async_safe_action


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

        Uwaga: Ta metoda jest synchroniczna (os.walk), więc nie używa @async_safe_action.
        Zamiast tego używamy wewnętrznego try/except lub (lepiej) synchronicznego @safe_action
        jeśli zaimplementujemy go w BaseSkill (mamy safe_action).
        W implementacji BaseSkill mamy safe_action dla metod nie-async.
        """
        # Używamy manualnego try/except bo metoda jest synchroniczna,
        # a safe_action w BaseSkill obsługuje to, ale tutaj dla pewności explicite wewnątrz,
        # lub dodamy dekorator.
        # DODAJEMY DEKORATOR sync z base_skill
        from venom_core.execution.skills.base_skill import safe_action

        @safe_action
        def _list_files_implementation(self, directory, recursive, max_depth):
            safe_path = self.validate_path(directory)

            if not safe_path.exists():
                return f"Katalog '{directory}' nie istnieje"

            if not safe_path.is_dir():
                return f"'{directory}' nie jest katalogiem"

            items = []

            if recursive:
                # Listowanie rekurencyjne
                items.append(
                    f"Zawartość katalogu '{directory}' (rekurencyjnie, max {max_depth} poziomy):\n"
                )
                skipped_files = 0

                for root, dirs, files in os.walk(safe_path):
                    try:
                        depth = len(Path(root).relative_to(safe_path).parts)
                    except ValueError:
                        depth = 0

                    if depth > max_depth:
                        dirs.clear()
                        continue

                    indent = "  " * depth

                    if depth < max_depth:
                        for dir_name in sorted(dirs):
                            dir_path = Path(root) / dir_name
                            rel_path = dir_path.relative_to(self.workspace_root)
                            items.append(f"{indent}[katalog] {rel_path}/")
                    else:
                        dirs.clear()

                    for file_name in sorted(files):
                        file_path = Path(root) / file_name
                        try:
                            stat_result = file_path.stat()
                            size = str(stat_result.st_size)
                            rel_path = file_path.relative_to(self.workspace_root)
                            items.append(f"{indent}[plik] {rel_path} ({size} bajtów)")
                        except Exception:
                            skipped_files += 1
                            continue

                if skipped_files > 0:
                    self.logger.warning(
                        f"Pominięto {skipped_files} niedostępnych plików"
                    )

                if len(items) == 1:
                    items.append("  (katalog pusty)")

            else:
                # Listowanie płaskie
                for item in sorted(safe_path.iterdir()):
                    stat_result = item.stat()
                    item_type = "katalog" if item.is_dir() else "plik"
                    relative_path = item.relative_to(self.workspace_root)
                    size = str(stat_result.st_size) if item.is_file() else "-"
                    items.append(f"  [{item_type}] {relative_path} ({size} bajtów)")

                if not items:
                    return f"Katalog '{directory}' jest pusty"

                items.insert(0, f"Zawartość katalogu '{directory}':")

            result = "\n".join(items)
            self.logger.info(
                f"Wylistowano {len(items) - 1} elementów w: {safe_path} (recursive={recursive})"
            )
            return result

        # Wywołanie wewnętrznej funkcji (hack żeby użyć dekoratora na metodzie która już jest)
        # albo po prostu użyć dekoratora na głównej metodzie.
        # Użyjmy czystszego podejścia: dekorator na metodzie.
        return _list_files_implementation(self, directory, recursive, max_depth)

    # Poprawka: Metoda list_files musi być zrobiona inaczej w Pythonie,
    # nie można wewnątrz metody definiować dekoratora na self.

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
