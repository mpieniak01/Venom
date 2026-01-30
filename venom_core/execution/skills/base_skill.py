"""Moduł: base_skill - abstrakcyjna klasa bazowa dla wszystkich umiejętności (Skills)."""

from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

T = TypeVar("T")


class SecurityError(Exception):
    """Wyjątek rzucany przy próbie dostępu poza workspace."""

    pass


def safe_action(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Dekorator dla metod skill, zapewniający standardową obsługę błędów.

    Łapie wszystkie wyjątki, loguje je i zwraca sformatowany komunikat błędu (string),
    aby nie przerywać działania LLM.
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Any:
        try:
            return func(self, *args, **kwargs)
        except SecurityError as e:
            # SecurityError jest już zalogowany w _validate_path
            return f"⛔ Odmowa dostępu: {str(e)}"
        except Exception as e:
            if hasattr(self, "logger"):
                self.logger.error(f"Błąd w {func.__name__}: {e}", exc_info=True)
            return f"❌ Wystąpił błąd: {str(e)}"

    return wrapper


def async_safe_action(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Asynchroniczny odpowiednik dekoratora safe_action.
    """

    @wraps(func)
    async def wrapper(self, *args, **kwargs) -> Any:
        try:
            return await func(self, *args, **kwargs)
        except SecurityError as e:
            return f"⛔ Odmowa dostępu: {str(e)}"
        except Exception as e:
            if hasattr(self, "logger"):
                self.logger.error(f"Błąd w {func.__name__}: {e}", exc_info=True)
            return f"❌ Wystąpił błąd: {str(e)}"

    return wrapper


class BaseSkill:
    """
    Klasa bazowa dla wszystkich umiejętności (Skills) w systemie Venom.

    Zapewnia:
    - Automatyczną inicjalizację loggera.
    - Dostęp do workspace_root.
    - Metody pomocnicze do walidacji ścieżek (security).
    """

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Inicjalizacja BaseSkill.

        Args:
            workspace_root: Opcjonalna ścieżka do workspace (domyślnie z SETTINGS).
        """
        self.logger = get_logger(self.__class__.__name__)
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()

        # Upewnij się, że workspace istnieje
        if not self.workspace_root.exists():
            try:
                self.workspace_root.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.logger.warning(
                    f"Nie udało się utworzyć workspace {self.workspace_root}: {e}"
                )

        self.logger.info(f"Zainicjalizowano {self.__class__.__name__}")

    def validate_path(self, file_path: str) -> Path:
        """
        Waliduje ścieżkę i upewnia się, że jest w bezpiecznym obszarze workspace.

        Args:
            file_path: Ścieżka relatywna lub absolutna.

        Returns:
            Bezpieczna, absolutna ścieżka Path.

        Raises:
            SecurityError: Jeśli ścieżka wykracza poza workspace.
            ValueError: Jeśli ścieżka jest pusta.
        """
        if not file_path or not file_path.strip():
            raise ValueError("Ścieżka nie może być pusta")

        # Rozwiąż ścieżkę względem workspace
        safe_path = (self.workspace_root / file_path).resolve()

        # Sprawdź Jailbreak (czy ścieżka jest wewnątrz workspace)
        try:
            safe_path.relative_to(self.workspace_root)
        except ValueError:
            error_msg = f"Próba dostępu poza workspace: {file_path}"
            self.logger.warning(error_msg)
            raise SecurityError(error_msg)

        # Sprawdź symlinki (jeśli istnieją i prowadzą na zewnątrz)
        if safe_path.is_symlink():
            real_path = safe_path.resolve()
            try:
                real_path.relative_to(self.workspace_root)
            except ValueError:
                error_msg = f"Symlink prowadzi poza workspace: {file_path}"
                self.logger.warning(error_msg)
                raise SecurityError(error_msg)

        return safe_path
