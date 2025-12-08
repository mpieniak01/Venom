"""Testy jednostkowe dla InputSkill (GUI Automation)."""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock pyautogui before importing InputSkill (for headless environments)
mock_pyautogui = MagicMock()
mock_pyautogui.FAILSAFE = True
mock_pyautogui.PAUSE = 0.1
mock_pyautogui.size = MagicMock(return_value=(1920, 1080))
sys.modules["pyautogui"] = mock_pyautogui

from venom_core.execution.skills.input_skill import InputSkill


class TestInputSkill:
    """Testy dla InputSkill."""

    @pytest.fixture
    def input_skill(self):
        """Fixture do tworzenia InputSkill."""
        with patch("pyautogui.size", return_value=(1920, 1080)):
            skill = InputSkill(safety_delay=0.1)
            return skill

    def test_initialization(self, input_skill):
        """Test inicjalizacji InputSkill."""
        assert input_skill.safety_delay == 0.1
        assert input_skill.screen_width == 1920
        assert input_skill.screen_height == 1080

    @pytest.mark.asyncio
    async def test_mouse_click_success(self, input_skill):
        """Test udanego kliknięcia myszy."""
        with patch("pyautogui.moveTo") as mock_move, patch(
            "pyautogui.click"
        ) as mock_click, patch("time.sleep"):
            result = await input_skill.mouse_click(100, 100)

            assert "✅" in result
            assert "Kliknięto" in result
            mock_move.assert_called_once()
            mock_click.assert_called_once()

    @pytest.mark.asyncio
    async def test_mouse_click_invalid_coordinates(self, input_skill):
        """Test kliknięcia z nieprawidłowymi współrzędnymi."""
        result = await input_skill.mouse_click(-10, 50)
        assert "❌" in result
        assert "Nieprawidłowe współrzędne" in result

        result = await input_skill.mouse_click(50, 2000)
        assert "❌" in result
        assert "Nieprawidłowe współrzędne" in result

    @pytest.mark.asyncio
    async def test_mouse_click_double(self, input_skill):
        """Test podwójnego kliknięcia."""
        with patch("pyautogui.moveTo"), patch(
            "pyautogui.doubleClick"
        ) as mock_double, patch("time.sleep"):
            result = await input_skill.mouse_click(100, 100, double=True)

            assert "✅" in result
            mock_double.assert_called_once()

    @pytest.mark.asyncio
    async def test_keyboard_type_success(self, input_skill):
        """Test wpisywania tekstu."""
        with patch("pyautogui.write") as mock_write, patch("time.sleep"):
            result = await input_skill.keyboard_type("Hello World")

            assert "✅" in result
            assert "Wpisano tekst" in result
            mock_write.assert_called_once_with("Hello World", interval=0.05)

    @pytest.mark.asyncio
    async def test_keyboard_type_empty_text(self, input_skill):
        """Test wpisywania pustego tekstu."""
        result = await input_skill.keyboard_type("")
        assert "❌" in result
        assert "Brak tekstu" in result

    @pytest.mark.asyncio
    async def test_keyboard_hotkey_success(self, input_skill):
        """Test wykonywania skrótu klawiszowego."""
        with patch("pyautogui.hotkey") as mock_hotkey, patch("time.sleep"):
            result = await input_skill.keyboard_hotkey("ctrl+s")

            assert "✅" in result
            assert "Wykonano skrót" in result
            mock_hotkey.assert_called_once_with("ctrl", "s")

    @pytest.mark.asyncio
    async def test_keyboard_hotkey_empty(self, input_skill):
        """Test wykonywania pustego skrótu."""
        result = await input_skill.keyboard_hotkey("")
        assert "❌" in result
        assert "Brak klawiszy" in result

    @pytest.mark.asyncio
    async def test_get_mouse_position(self, input_skill):
        """Test pobierania pozycji myszy."""
        with patch("pyautogui.position", return_value=(500, 300)):
            result = await input_skill.get_mouse_position()
            assert "500, 300" in result or "(500, 300)" in result

    @pytest.mark.asyncio
    async def test_take_screenshot(self, input_skill):
        """Test robienia zrzutu ekranu."""
        mock_screenshot = MagicMock()
        mock_screenshot.size = (1920, 1080)

        with patch("pyautogui.screenshot", return_value=mock_screenshot):
            result = await input_skill.take_screenshot()
            assert "✅" in result
            assert "1920x1080" in result

    def test_validate_coordinates(self, input_skill):
        """Test walidacji współrzędnych."""
        assert input_skill._validate_coordinates(100, 100) is True
        assert input_skill._validate_coordinates(0, 0) is True
        assert input_skill._validate_coordinates(1919, 1079) is True

        assert input_skill._validate_coordinates(-1, 100) is False
        assert input_skill._validate_coordinates(100, -1) is False
        assert input_skill._validate_coordinates(2000, 100) is False
        assert input_skill._validate_coordinates(100, 2000) is False

    def test_get_screen_size(self, input_skill):
        """Test pobierania rozmiaru ekranu."""
        width, height = input_skill.get_screen_size()
        assert width == 1920
        assert height == 1080
