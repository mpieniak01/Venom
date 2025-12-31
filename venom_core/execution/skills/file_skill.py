"""Moduł: file_skill - zarządzanie operacjami plikowymi z sandboxingiem."""

import os
from pathlib import Path
from typing import Annotated

import aiofiles
from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class FileSkill:
    """
    Skill do bezpiecznych operacji plikowych.
    Wszystkie operacje są ograniczone do WORKSPACE_ROOT.

    UWAGA: Metody tego skill nie są thread-safe. System Venom jest zaprojektowany
    do sekwencyjnego przetwarzania zadań przez Orchestrator. Jeśli wiele agentów
    próbowałoby jednocześnie zapisywać do tego samego pliku, może dojść do
    race conditions. W przyszłości można dodać file locking używając fcntl/msvcrt.
    """

    def __init__(self, workspace_root: str = None):
        """
        Inicjalizacja FileSkill.

        Args:
            workspace_root: Katalog roboczy (domyślnie z SETTINGS.WORKSPACE_ROOT)
        """
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        logger.info(f"FileSkill zainicjalizowany z workspace: {self.workspace_root}")

        # Upewnij się, że katalog workspace istnieje
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def _validate_path(self, file_path: str) -> Path:
        """
        Waliduje ścieżkę i upewnia się, że jest w workspace.

        Args:
            file_path: Ścieżka do pliku (relatywna do workspace)

        Returns:
            Zwalidowana bezwzględna ścieżka

        Raises:
            SecurityError: Jeśli ścieżka próbuje wyjść poza workspace
            ValueError: Jeśli ścieżka jest pusta
        """
        # Sprawdź czy ścieżka nie jest pusta
        if not file_path or not file_path.strip():
            raise ValueError("Ścieżka pliku nie może być pusta")

        # Połącz ze workspace root i rozwiąż
        safe_path = (self.workspace_root / file_path).resolve()

        # Sprawdź czy ścieżka jest wewnątrz workspace
        try:
            safe_path.relative_to(self.workspace_root)
        except ValueError:
            error_msg = (
                f"Odmowa dostępu: ścieżka '{file_path}' próbuje wyjść poza workspace"
            )
            logger.error(error_msg)
            raise SecurityError(error_msg)

        # Sprawdź symlinki - nie pozwalaj na operacje na symlinkach wskazujących poza workspace
        if safe_path.is_symlink():
            real_path = safe_path.resolve()
            try:
                real_path.relative_to(self.workspace_root)
            except ValueError:
                error_msg = (
                    f"Odmowa dostępu: symlink '{file_path}' wskazuje poza workspace"
                )
                logger.error(error_msg)
                raise SecurityError(error_msg)

        return safe_path

    @kernel_function(
        name="write_file",
        description="Zapisuje treść do pliku w workspace. Tworzy katalogi jeśli nie istnieją.",
    )
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

        Args:
            file_path: Ścieżka do pliku względem workspace
            content: Treść do zapisania

        Returns:
            Komunikat potwierdzający zapis

        Raises:
            SecurityError: Jeśli ścieżka jest nieprawidłowa
            IOError: Jeśli nie można zapisać pliku
        """
        try:
            safe_path = self._validate_path(file_path)

            # Utwórz katalogi nadrzędne jeśli nie istnieją
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            # Zapisz plik asynchronicznie
            async with aiofiles.open(safe_path, "w", encoding="utf-8") as f:
                await f.write(content)

            logger.info(f"Zapisano plik: {safe_path}")
            return (
                f"Plik '{file_path}' został pomyślnie zapisany ({len(content)} znaków)"
            )

        except SecurityError:
            raise
        except Exception as e:
            error_msg = f"Błąd podczas zapisu pliku '{file_path}': {e}"
            logger.error(error_msg)
            raise IOError(error_msg) from e

    @kernel_function(
        name="read_file",
        description="Odczytuje treść pliku z workspace.",
    )
    async def read_file(
        self,
        file_path: Annotated[str, "Ścieżka do pliku względem workspace"],
    ) -> str:
        """
        Odczytuje treść pliku asynchronicznie.

        Args:
            file_path: Ścieżka do pliku względem workspace

        Returns:
            Treść pliku

        Raises:
            SecurityError: Jeśli ścieżka jest nieprawidłowa
            FileNotFoundError: Jeśli plik nie istnieje
            IOError: Jeśli nie można odczytać pliku
        """
        try:
            safe_path = self._validate_path(file_path)

            if not safe_path.exists():
                raise FileNotFoundError(f"Plik '{file_path}' nie istnieje")

            if not safe_path.is_file():
                raise IOError(f"'{file_path}' nie jest plikiem")

            # Odczytaj plik asynchronicznie
            async with aiofiles.open(safe_path, "r", encoding="utf-8") as f:
                content = await f.read()

            logger.info(f"Odczytano plik: {safe_path} ({len(content)} znaków)")
            return content

        except (SecurityError, FileNotFoundError):
            raise
        except Exception as e:
            error_msg = f"Błąd podczas odczytu pliku '{file_path}': {e}"
            logger.error(error_msg)
            raise IOError(error_msg) from e

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

        Args:
            directory: Katalog względem workspace (domyślnie '.')
            recursive: Czy listować rekurencyjnie
            max_depth: Maksymalna głębokość rekurencji (domyślnie 3)

        Returns:
            Lista plików i katalogów w formacie tekstowym.
            Jeśli recursive=False, pokazuje tylko bezpośrednie elementy.
            Jeśli recursive=True, pokazuje strukturę do max_depth poziomów głębokości.

        Raises:
            SecurityError: Jeśli ścieżka jest nieprawidłowa
            IOError: Jeśli nie można odczytać katalogu
        """
        try:
            safe_path = self._validate_path(directory)

            if not safe_path.exists():
                return f"Katalog '{directory}' nie istnieje"

            if not safe_path.is_dir():
                return f"'{directory}' nie jest katalogiem"

            items = []

            if recursive:
                # Listowanie rekurencyjne z limitem głębokości
                items.append(
                    f"Zawartość katalogu '{directory}' (rekurencyjnie, max {max_depth} poziomy):\n"
                )

                # Licznik pominiętych plików
                skipped_files = 0

                for root, dirs, files in os.walk(safe_path):
                    # Oblicz głębokość relatywną (0 = root, 1 = pierwszy poziom, itd.)
                    try:
                        depth = len(Path(root).relative_to(safe_path).parts)
                    except ValueError:
                        depth = 0

                    # Ogranicz głębokość - nie wchodź głębiej niż max_depth
                    if depth > max_depth:
                        dirs.clear()  # Nie schodź głębiej
                        continue

                    indent = "  " * depth

                    # Dodaj katalogi (tylko jeśli nie przekroczymy limitu przy wejściu do nich)
                    if depth < max_depth:
                        for dir_name in sorted(dirs):
                            dir_path = Path(root) / dir_name
                            rel_path = dir_path.relative_to(self.workspace_root)
                            items.append(f"{indent}[katalog] {rel_path}/")
                    else:
                        # Na maksymalnej głębokości - nie pokazuj już katalogów (bo i tak nie możemy do nich wejść)
                        dirs.clear()

                    # Dodaj pliki na tym poziomie
                    for file_name in sorted(files):
                        file_path = Path(root) / file_name
                        try:
                            stat_result = file_path.stat()
                            size = stat_result.st_size
                            rel_path = file_path.relative_to(self.workspace_root)
                            items.append(f"{indent}[plik] {rel_path} ({size} bajtów)")
                        except Exception:
                            # Zlicz pominięte pliki zamiast logować każdy osobno
                            skipped_files += 1
                            continue

                # Podsumowanie pominiętych plików
                if skipped_files > 0:
                    logger.warning(f"Pominięto {skipped_files} niedostępnych plików")

                if len(items) == 1:  # Tylko nagłówek
                    items.append("  (katalog pusty)")

            else:
                # Listowanie płaskie (nie-rekurencyjne)
                for item in sorted(safe_path.iterdir()):
                    stat_result = item.stat()
                    item_type = "katalog" if item.is_dir() else "plik"
                    relative_path = item.relative_to(self.workspace_root)
                    size = stat_result.st_size if item.is_file() else "-"
                    items.append(f"  [{item_type}] {relative_path} ({size} bajtów)")

                if not items:
                    return f"Katalog '{directory}' jest pusty"

                items.insert(0, f"Zawartość katalogu '{directory}':")

            result = "\n".join(items)
            logger.info(
                f"Wylistowano {len(items) - 1} elementów w: {safe_path} (recursive={recursive})"
            )
            return result

        except SecurityError:
            raise
        except Exception as e:
            error_msg = f"Błąd podczas listowania katalogu '{directory}': {e}"
            logger.error(error_msg)
            raise IOError(error_msg) from e

    @kernel_function(
        name="file_exists",
        description="Sprawdza czy plik lub katalog istnieje w workspace.",
    )
    def file_exists(
        self,
        file_path: Annotated[str, "Ścieżka do pliku/katalogu względem workspace"],
    ) -> str:
        """
        Sprawdza czy plik istnieje.

        Args:
            file_path: Ścieżka do pliku względem workspace

        Returns:
            String "True" jeśli istnieje, "False" jeśli nie.
            UWAGA: Zwraca string zamiast boolean, ponieważ Semantic Kernel
            wymaga serializowalnych typów dla function calling przez LLM.

        Raises:
            SecurityError: Jeśli ścieżka jest nieprawidłowa
        """
        try:
            safe_path = self._validate_path(file_path)
            exists = safe_path.exists()
            logger.info(f"Sprawdzono istnienie: {safe_path} = {exists}")
            return "True" if exists else "False"

        except SecurityError:
            raise


class SecurityError(Exception):
    """Wyjątek rzucany przy próbie dostępu poza workspace."""

