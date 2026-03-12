"""Moduł: permission_guard - AutonomyGate - system kontroli uprawnień agenta."""

from typing import Any, Dict, Optional

from venom_core.utils.config_paths import resolve_config_path
from venom_core.utils.logger import get_logger

yaml: Any = None
try:  # pragma: no cover - zależne od środowiska
    import yaml as _yaml

    yaml = _yaml
except ImportError:  # pragma: no cover
    pass

logger = get_logger(__name__)


class AutonomyViolation(Exception):
    """Wyjątek rzucany gdy próba wykonania akcji przekracza uprawnienia."""

    def __init__(
        self,
        message: str,
        required_level: int,
        required_level_name: str,
        current_level: int,
        current_level_name: str,
        skill_name: str,
    ):
        """
        Inicjalizacja wyjątku AutonomyViolation.

        Args:
            message: Wiadomość błędu
            required_level: Wymagany poziom autonomii (0-40)
            required_level_name: Nazwa wymaganego poziomu (np. "BUILDER")
            current_level: Aktualny poziom autonomii
            current_level_name: Nazwa aktualnego poziomu
            skill_name: Nazwa skilla który został zablokowany
        """
        super().__init__(message)
        self.required_level = required_level
        self.required_level_name = required_level_name
        self.current_level = current_level
        self.current_level_name = current_level_name
        self.skill_name = skill_name


class AutonomyLevel:
    """Model reprezentujący poziom autonomii."""

    def __init__(self, data: dict):
        """
        Inicjalizacja AutonomyLevel z danych YAML.

        Args:
            data: Słownik z danymi poziomu
        """
        self.id: int = data["id"]
        self.name: str = data["name"]
        self.description: str = data["description"]
        self.color: str = data["color"]
        self.color_name: str = data["color_name"]
        self.permissions: dict = data["permissions"]
        self.risk_level: str = data["risk_level"]
        self.examples: list = data.get("examples", [])


class PermissionGuard:
    """
    Singleton zarządzający systemem uprawnień AutonomyGate.

    System definiuje 5 poziomów autonomii (0, 10, 20, 30, 40) i kontroluje
    dostęp do skillów oraz zasobów systemowych.
    """

    _instance: Optional["PermissionGuard"] = None
    _initialized: bool = False

    def __new__(cls):
        """Implementacja singletonu."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Inicjalizacja PermissionGuard (wykonywana raz dla singletonu)."""
        if self._initialized:
            return

        self._current_level: int = 0  # Domyślnie ISOLATED
        self._levels: Dict[int, AutonomyLevel] = {}
        self._skill_permissions: Dict[str, int] = {}
        self._state_manager = None

        # Załaduj konfigurację
        self._load_autonomy_matrix()
        self._load_skill_permissions()

        self._initialized = True
        logger.info(
            f"PermissionGuard zainicjalizowany - poziom: {self.get_current_level_name()}"
        )

    def set_state_manager(self, state_manager):
        """
        Ustawia StateManager dla persystencji stanu.

        Args:
            state_manager: Instancja StateManager
        """
        self._state_manager = state_manager
        # Załaduj zapisany poziom autonomii jeśli istnieje
        if hasattr(state_manager, "autonomy_level"):
            self._current_level = state_manager.autonomy_level
            logger.info(
                f"Załadowano poziom autonomii z StateManager: {self.get_current_level_name()}"
            )

    def _load_autonomy_matrix(self):
        """Ładuje macierz autonomii z pliku YAML."""
        config_path = resolve_config_path("autonomy_matrix.yaml")

        if yaml is None:
            raise RuntimeError("Brak zależności PyYAML (pip install PyYAML)")

        if not config_path.exists():
            logger.error(f"Brak pliku konfiguracji: {config_path}")
            # Załaduj domyślną konfigurację bezpieczeństwa (tylko ISOLATED)
            self._load_default_matrix()
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            for level_data in data["levels"]:
                level = AutonomyLevel(level_data)
                self._levels[level.id] = level

            logger.info(f"Załadowano {len(self._levels)} poziomów autonomii")

        except Exception as e:
            logger.error(f"Błąd ładowania autonomy_matrix.yaml: {e}")
            self._load_default_matrix()

    def _load_default_matrix(self):
        """Ładuje domyślną macierz (tylko ISOLATED) jako fallback."""
        logger.warning("Używam domyślnej macierzy autonomii (tylko ISOLATED)")
        self._levels[0] = AutonomyLevel(
            {
                "id": 0,
                "name": "ISOLATED",
                "description": "Tryb bezpieczny - tylko lokalne odczyty",
                "color": "#22c55e",
                "color_name": "green",
                "permissions": {
                    "network_enabled": False,
                    "paid_api_enabled": False,
                    "filesystem_mode": "read_only",
                    "shell_enabled": False,
                },
                "risk_level": "zero",
                "examples": [],
            }
        )

    def _load_skill_permissions(self):
        """Ładuje mapowanie skillów na poziomy uprawnień z pliku YAML."""
        config_path = resolve_config_path("skill_permissions.yaml")

        if yaml is None:
            raise RuntimeError("Brak zależności PyYAML (pip install PyYAML)")

        if not config_path.exists():
            logger.warning(f"Brak pliku konfiguracji: {config_path}")
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self._skill_permissions = yaml.safe_load(f)

            # Filtruj tylko int wartości (ignoruj komentarze)
            self._skill_permissions = {
                k: v for k, v in self._skill_permissions.items() if isinstance(v, int)
            }

            logger.info(
                f"Załadowano uprawnienia dla {len(self._skill_permissions)} skillów"
            )

        except Exception as e:
            logger.error(f"Błąd ładowania skill_permissions.yaml: {e}")

    def get_current_level(self) -> int:
        """
        Zwraca aktualny poziom autonomii.

        Returns:
            ID aktualnego poziomu (0-40)
        """
        return self._current_level

    def get_current_level_name(self) -> str:
        """
        Zwraca nazwę aktualnego poziomu autonomii.

        Returns:
            Nazwa poziomu (np. "ISOLATED", "BUILDER")
        """
        level = self._levels.get(self._current_level)
        return level.name if level else "UNKNOWN"

    def get_level_info(self, level_id: int) -> Optional[AutonomyLevel]:
        """
        Zwraca informacje o danym poziomie.

        Args:
            level_id: ID poziomu (0-40)

        Returns:
            Obiekt AutonomyLevel lub None
        """
        return self._levels.get(level_id)

    def get_all_levels(self) -> Dict[int, AutonomyLevel]:
        """
        Zwraca wszystkie zdefiniowane poziomy.

        Returns:
            Słownik {level_id: AutonomyLevel}
        """
        return self._levels.copy()

    def set_level(self, level_id: int) -> bool:
        """
        Ustawia nowy poziom autonomii.

        Args:
            level_id: Nowy poziom (0, 10, 20, 30, 40)

        Returns:
            True jeśli poziom został zmieniony, False jeśli poziom nieprawidłowy
        """
        if level_id not in self._levels:
            logger.error(
                f"Nieprawidłowy poziom autonomii: {level_id}. Dostępne: {list(self._levels.keys())}"
            )
            return False

        old_level = self._current_level
        old_level_name = self.get_current_level_name()
        self._current_level = level_id
        new_level_name = self.get_current_level_name()

        logger.warning(
            f"🔐 Poziom autonomii zmieniony: {old_level_name} ({old_level}) → {new_level_name} ({level_id})"
        )

        # Synchronizuj z StateManager
        self.sync_state(level_id)

        return True

    def sync_state(self, level_id: int):
        """
        Synchronizuje stan z StateManager i Token Economist.

        Args:
            level_id: Nowy poziom autonomii
        """
        level = self._levels.get(level_id)
        if not level:
            return

        # Persystuj poziom w StateManager
        if self._state_manager:
            # Zapisz poziom autonomii
            self._state_manager.autonomy_level = level_id

            # Jeśli poziom >= 20 (FUNDED), włącz paid mode dla Token Economist
            if level.permissions.get("paid_api_enabled", False):
                self._state_manager.enable_paid_mode()
                logger.info("💰 Paid Mode włączony - dostęp do płatnych API (FUNDED+)")
            else:
                self._state_manager.disable_paid_mode()
                logger.info("🌿 Paid Mode wyłączony - tylko lokalne/darmowe API")

    def check_permission(self, skill_name: str) -> bool:
        """
        Sprawdza czy aktualny poziom autonomii pozwala na użycie danego skilla.

        Args:
            skill_name: Nazwa skilla do sprawdzenia

        Returns:
            True jeśli dozwolone, False w przeciwnym wypadku

        Raises:
            AutonomyViolation: Gdy uprawnienia są niewystarczające
        """
        required_level = self._skill_permissions.get(skill_name, 40)  # Domyślnie ROOT

        if self._current_level >= required_level:
            return True

        # Brak uprawnień - rzuć wyjątek
        required_level_obj = self._levels.get(required_level)
        current_level_obj = self._levels.get(self._current_level)

        raise AutonomyViolation(
            message=f"Brak uprawnień do użycia {skill_name}. "
            f"Wymagany poziom: {required_level_obj.name if required_level_obj else required_level}, "
            f"aktualny: {current_level_obj.name if current_level_obj else self._current_level}",
            required_level=required_level,
            required_level_name=(
                required_level_obj.name if required_level_obj else "UNKNOWN"
            ),
            current_level=self._current_level,
            current_level_name=(
                current_level_obj.name if current_level_obj else "UNKNOWN"
            ),
            skill_name=skill_name,
        )

    def can_access_network(self) -> bool:
        """
        Sprawdza czy aktualny poziom pozwala na dostęp do sieci.

        Returns:
            True jeśli dozwolone
        """
        level = self._levels.get(self._current_level)
        return level.permissions.get("network_enabled", False) if level else False

    def can_use_paid_api(self) -> bool:
        """
        Sprawdza czy aktualny poziom pozwala na użycie płatnych API.

        Returns:
            True jeśli dozwolone
        """
        level = self._levels.get(self._current_level)
        return level.permissions.get("paid_api_enabled", False) if level else False

    def can_write_files(self) -> bool:
        """
        Sprawdza czy aktualny poziom pozwala na zapis plików.

        Returns:
            True jeśli dozwolone
        """
        level = self._levels.get(self._current_level)
        if not level:
            return False
        mode = level.permissions.get("filesystem_mode", "read_only")
        return mode == "read_write"

    def can_execute_shell(self) -> bool:
        """
        Sprawdza czy aktualny poziom pozwala na wykonanie komend shell.

        Returns:
            True jeśli dozwolone
        """
        level = self._levels.get(self._current_level)
        return level.permissions.get("shell_enabled", False) if level else False

    def can_control_desktop_input(self) -> bool:
        """
        Sprawdza czy aktualny poziom pozwala na automatyzację desktop input.

        Jeśli flaga desktop_input_enabled nie jest zdefiniowana w macierzy,
        zachowujemy kompatybilność i fallback do shell_enabled.
        """
        level = self._levels.get(self._current_level)
        if not level:
            return False
        permissions = level.permissions
        if "desktop_input_enabled" in permissions:
            return bool(permissions.get("desktop_input_enabled"))
        return bool(permissions.get("shell_enabled", False))


# Globalna instancja (singleton)
permission_guard = PermissionGuard()
