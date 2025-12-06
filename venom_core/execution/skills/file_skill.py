"""Moduł: file_skill - zarządzanie operacjami plikowymi z sandboxingiem."""

from pathlib import Path
from typing import Annotated

from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class FileSkill:
    """
    Skill do bezpiecznych operacji plikowych.
    Wszystkie operacje są ograniczone do WORKSPACE_ROOT.
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
        """
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

        return safe_path

    @kernel_function(
        name="write_file",
        description="Zapisuje treść do pliku w workspace. Tworzy katalogi jeśli nie istnieją.",
    )
    def write_file(
        self,
        file_path: Annotated[
            str,
            "Ścieżka do pliku względem workspace (np. 'test.py', 'subdir/file.txt')",
        ],
        content: Annotated[str, "Treść do zapisania w pliku"],
    ) -> str:
        """
        Zapisuje treść do pliku.

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

            # Zapisz plik
            safe_path.write_text(content, encoding="utf-8")

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
    def read_file(
        self,
        file_path: Annotated[str, "Ścieżka do pliku względem workspace"],
    ) -> str:
        """
        Odczytuje treść pliku.

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

            content = safe_path.read_text(encoding="utf-8")
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
        description="Listuje pliki i katalogi w workspace.",
    )
    def list_files(
        self,
        directory: Annotated[
            str, "Katalog względem workspace (domyślnie '.', czyli root workspace)"
        ] = ".",
    ) -> str:
        """
        Listuje pliki i katalogi.

        Args:
            directory: Katalog względem workspace (domyślnie '.')

        Returns:
            Lista plików i katalogów w formacie tekstowym

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

            # Zbierz pliki i katalogi
            items = []
            for item in sorted(safe_path.iterdir()):
                stat_result = item.stat()
                item_type = "katalog" if item.is_dir() else "plik"
                relative_path = item.relative_to(self.workspace_root)
                size = stat_result.st_size if item.is_file() else "-"
                items.append(f"  [{item_type}] {relative_path} ({size} bajtów)")

            if not items:
                return f"Katalog '{directory}' jest pusty"

            result = f"Zawartość katalogu '{directory}':\n" + "\n".join(items)
            logger.info(f"Wylistowano {len(items)} elementów w: {safe_path}")
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
            "True" jeśli istnieje, "False" jeśli nie

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

    pass
