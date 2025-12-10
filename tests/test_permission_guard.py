"""Test dla PermissionGuard - AutonomyGate."""

import pytest

from venom_core.core.permission_guard import (
    AutonomyViolation,
    PermissionGuard,
    permission_guard,
)


class TestPermissionGuard:
    """Testy dla PermissionGuard."""

    def setup_method(self):
        """Setup przed każdym testem - reset poziomu do ISOLATED."""
        permission_guard.set_level(0)

    def test_singleton_pattern(self):
        """Test czy PermissionGuard jest singletonem."""
        pg1 = PermissionGuard()
        pg2 = PermissionGuard()
        assert pg1 is pg2
        assert pg1 is permission_guard

    def test_initial_level_is_isolated(self):
        """Test czy domyślny poziom to ISOLATED (0)."""
        assert permission_guard.get_current_level() == 0
        assert permission_guard.get_current_level_name() == "ISOLATED"

    def test_set_valid_levels(self):
        """Test ustawiania prawidłowych poziomów."""
        levels = [0, 10, 20, 30, 40]
        for level in levels:
            result = permission_guard.set_level(level)
            assert result is True
            assert permission_guard.get_current_level() == level

    def test_set_invalid_level(self):
        """Test ustawiania nieprawidłowego poziomu."""
        result = permission_guard.set_level(999)
        assert result is False
        # Poziom nie powinien się zmienić
        assert permission_guard.get_current_level() == 0

    def test_check_permission_allowed(self):
        """Test sprawdzania uprawnień gdy są wystarczające."""
        # ISOLATED (0) może używać FileReadSkill
        permission_guard.set_level(0)
        assert permission_guard.check_permission("FileReadSkill") is True

        # CONNECTED (10) może używać WebSearchSkill
        permission_guard.set_level(10)
        assert permission_guard.check_permission("WebSearchSkill") is True

        # BUILDER (30) może używać FileWriteSkill
        permission_guard.set_level(30)
        assert permission_guard.check_permission("FileWriteSkill") is True

    def test_check_permission_denied(self):
        """Test sprawdzania uprawnień gdy są niewystarczające."""
        permission_guard.set_level(0)  # ISOLATED

        # ISOLATED nie może używać WebSearchSkill (wymaga 10)
        with pytest.raises(AutonomyViolation) as exc_info:
            permission_guard.check_permission("WebSearchSkill")

        error = exc_info.value
        assert error.required_level == 10
        assert error.current_level == 0
        assert error.skill_name == "WebSearchSkill"

    def test_permission_inheritance(self):
        """Test dziedziczenia uprawnień przez wyższe poziomy."""
        permission_guard.set_level(40)  # ROOT

        # ROOT może używać wszystkich skillów
        assert permission_guard.check_permission("FileReadSkill") is True  # 0
        assert permission_guard.check_permission("WebSearchSkill") is True  # 10
        assert permission_guard.check_permission("GeminiSkill") is True  # 20
        assert permission_guard.check_permission("FileWriteSkill") is True  # 30
        assert permission_guard.check_permission("ShellSkill") is True  # 40

    def test_unknown_skill_requires_root(self):
        """Test że nieznany skill wymaga poziomu ROOT (domyślnie)."""
        permission_guard.set_level(30)  # BUILDER

        # UnknownSkill nie jest w konfiguracji, więc wymaga ROOT (40)
        with pytest.raises(AutonomyViolation) as exc_info:
            permission_guard.check_permission("UnknownNewSkill")

        error = exc_info.value
        assert error.required_level == 40

    def test_can_access_network(self):
        """Test sprawdzania dostępu do sieci."""
        permission_guard.set_level(0)  # ISOLATED
        assert permission_guard.can_access_network() is False

        permission_guard.set_level(10)  # CONNECTED
        assert permission_guard.can_access_network() is True

    def test_can_use_paid_api(self):
        """Test sprawdzania dostępu do płatnych API."""
        permission_guard.set_level(10)  # CONNECTED
        assert permission_guard.can_use_paid_api() is False

        permission_guard.set_level(20)  # FUNDED
        assert permission_guard.can_use_paid_api() is True

    def test_can_write_files(self):
        """Test sprawdzania uprawnień do zapisu plików."""
        permission_guard.set_level(20)  # FUNDED
        assert permission_guard.can_write_files() is False

        permission_guard.set_level(30)  # BUILDER
        assert permission_guard.can_write_files() is True

    def test_can_execute_shell(self):
        """Test sprawdzania uprawnień do wykonania shell."""
        permission_guard.set_level(30)  # BUILDER
        assert permission_guard.can_execute_shell() is False

        permission_guard.set_level(40)  # ROOT
        assert permission_guard.can_execute_shell() is True

    def test_get_all_levels(self):
        """Test pobierania wszystkich poziomów."""
        levels = permission_guard.get_all_levels()
        assert len(levels) == 5
        assert 0 in levels
        assert 10 in levels
        assert 20 in levels
        assert 30 in levels
        assert 40 in levels

    def test_level_info(self):
        """Test pobierania informacji o poziomie."""
        level_info = permission_guard.get_level_info(20)  # FUNDED
        assert level_info is not None
        assert level_info.id == 20
        assert level_info.name == "FUNDED"
        assert level_info.color == "#eab308"
        assert level_info.permissions["paid_api_enabled"] is True
        assert level_info.risk_level == "medium"

    def test_autonomy_violation_message(self):
        """Test poprawności komunikatu błędu AutonomyViolation."""
        permission_guard.set_level(0)  # ISOLATED

        with pytest.raises(AutonomyViolation) as exc_info:
            permission_guard.check_permission("ShellSkill")

        error = exc_info.value
        assert "ShellSkill" in str(error)
        assert "ROOT" in str(error) or "40" in str(error)
        assert "ISOLATED" in str(error) or "0" in str(error)
