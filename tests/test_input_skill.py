"""Testy jednostkowe dla InputSkill (GUI Automation)."""

# ruff: noqa: E402

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock pyautogui before importing InputSkill (for headless environments)
mock_pyautogui = MagicMock()
mock_pyautogui.FAILSAFE = True
mock_pyautogui.PAUSE = 0.1
# Make size() callable and return a tuple
mock_pyautogui.size.return_value = (1920, 1080)
mock_pyautogui.moveTo = MagicMock()
mock_pyautogui.click = MagicMock()
mock_pyautogui.doubleClick = MagicMock()
mock_pyautogui.write = MagicMock()
mock_pyautogui.hotkey = MagicMock()
mock_pyautogui.position = MagicMock(return_value=(500, 300))
mock_pyautogui.screenshot = MagicMock()
mock_pyautogui.FailSafeException = Exception
sys.modules["pyautogui"] = mock_pyautogui

from venom_core.execution.skills.input_skill import InputSkill


class TestInputSkill:
    """Testy dla InputSkill."""

    @pytest.fixture
    def input_skill(self):
        """Fixture do tworzenia InputSkill."""
        # Don't reset the whole mock, just reset call counts
        # Set up return values properly for each test
        mock_pyautogui.size.return_value = (1920, 1080)
        mock_pyautogui.position.return_value = (500, 300)

        # Reset call counts for tracking
        mock_pyautogui.moveTo.reset_mock()
        mock_pyautogui.click.reset_mock()
        mock_pyautogui.doubleClick.reset_mock()
        mock_pyautogui.write.reset_mock()
        mock_pyautogui.hotkey.reset_mock()

        skill = InputSkill(safety_delay=0.1)
        return skill

    def test_initialization(self, input_skill):
        """Test inicjalizacji InputSkill."""
        assert input_skill.safety_delay == pytest.approx(0.1)
        assert input_skill.screen_width == 1920
        assert input_skill.screen_height == 1080

    @pytest.mark.asyncio
    async def test_mouse_click_success(self, input_skill):
        """Test udanego kliknięcia myszy."""
        with patch("time.sleep"):
            result = await input_skill.mouse_click(100, 100)

            assert "✅" in result
            assert "Kliknięto" in result
            mock_pyautogui.moveTo.assert_called()
            mock_pyautogui.click.assert_called()

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
        with patch("time.sleep"):
            result = await input_skill.mouse_click(100, 100, double=True)

            assert "✅" in result
            mock_pyautogui.doubleClick.assert_called()

    @pytest.mark.asyncio
    async def test_keyboard_type_success(self, input_skill):
        """Test wpisywania tekstu."""
        with patch("time.sleep"):
            result = await input_skill.keyboard_type("Hello World")

            assert "✅" in result
            assert "Wpisano tekst" in result
            mock_pyautogui.write.assert_called()

    @pytest.mark.asyncio
    async def test_keyboard_type_empty_text(self, input_skill):
        """Test wpisywania pustego tekstu."""
        result = await input_skill.keyboard_type("")
        assert "❌" in result
        assert "Brak tekstu" in result

    @pytest.mark.asyncio
    async def test_keyboard_hotkey_success(self, input_skill):
        """Test wykonywania skrótu klawiszowego."""
        with patch("time.sleep"):
            result = await input_skill.keyboard_hotkey("ctrl+s")

            assert "✅" in result
            assert "Wykonano skrót" in result
            mock_pyautogui.hotkey.assert_called()

    @pytest.mark.asyncio
    async def test_keyboard_hotkey_empty(self, input_skill):
        """Test wykonywania pustego skrótu."""
        result = await input_skill.keyboard_hotkey("")
        assert "❌" in result
        assert "Brak klawiszy" in result

    @pytest.mark.asyncio
    async def test_get_mouse_position(self, input_skill):
        """Test pobierania pozycji myszy."""
        result = await input_skill.get_mouse_position()
        assert "500" in result and "300" in result

    @pytest.mark.asyncio
    async def test_take_screenshot(self, input_skill):
        """Test robienia zrzutu ekranu."""
        mock_screenshot = MagicMock()
        mock_screenshot.size = (1920, 1080)
        mock_pyautogui.screenshot.return_value = mock_screenshot

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
