"""Testy jednostkowe dla GhostAgent."""

# ruff: noqa: E402

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from PIL import Image

# Mock pyautogui for headless environment
mock_pyautogui = MagicMock()
sys.modules["pyautogui"] = mock_pyautogui

from venom_core.agents.ghost_agent import ActionStep, GhostAgent


class TestActionStep:
    """Testy dla ActionStep."""

    def test_action_step_initialization(self):
        """Test inicjalizacji ActionStep."""
        step = ActionStep("click", "Kliknij przycisk", {"x": 100, "y": 200})

        assert step.action_type == "click"
        assert step.description == "Kliknij przycisk"
        assert step.params == {"x": 100, "y": 200}
        assert step.status == "pending"
        assert step.result is None

    def test_action_step_without_params(self):
        """Test ActionStep bez parametrów."""
        step = ActionStep("screenshot", "Zrób zrzut")

        assert step.action_type == "screenshot"
        assert step.params == {}


class TestGhostAgent:
    """Testy dla GhostAgent."""

    @pytest.fixture
    def mock_kernel(self):
        """Fixture do tworzenia mock Kernel."""
        return MagicMock()

    @pytest.fixture
    def ghost_agent(self, mock_kernel):
        """Fixture do tworzenia GhostAgent."""
        with (
            patch("venom_core.agents.ghost_agent.VisionGrounding"),
            patch("venom_core.agents.ghost_agent.InputSkill"),
            patch("venom_core.agents.ghost_agent.SETTINGS") as mock_settings,
        ):
            # Mock SETTINGS to enable Ghost Agent in tests
            mock_settings.ENABLE_GHOST_AGENT = True
            mock_settings.GHOST_MAX_STEPS = 20
            mock_settings.GHOST_STEP_DELAY = 1.0
            mock_settings.GHOST_VERIFICATION_ENABLED = True
            mock_settings.GHOST_SAFETY_DELAY = 0.5

            agent = GhostAgent(
                kernel=mock_kernel,
                max_steps=10,
                step_delay=0.1,
                verification_enabled=False,
            )
            return agent

    def test_initialization(self, ghost_agent):
        """Test inicjalizacji GhostAgent."""
        assert ghost_agent.max_steps == 10
        assert ghost_agent.step_delay == pytest.approx(0.1)
        assert ghost_agent.verification_enabled is False
        assert ghost_agent.is_running is False
        assert ghost_agent.emergency_stop is False
        assert len(ghost_agent.action_history) == 0

    @pytest.mark.asyncio
    async def test_process_when_already_running(self, ghost_agent):
        """Test próby uruchomienia gdy agent już działa."""
        ghost_agent.is_running = True

        with patch("venom_core.agents.ghost_agent.SETTINGS") as mock_settings:
            mock_settings.ENABLE_GHOST_AGENT = True
            result = await ghost_agent.process("Otwórz notatnik")

            assert "już działa" in result
            assert "❌" in result

    @pytest.mark.asyncio
    async def test_process_notepad_task(self, ghost_agent):
        """Test zadania otwarcia notatnika."""
        # Mock metod
        ghost_agent.input_skill.keyboard_hotkey = AsyncMock(return_value="✅ OK")
        ghost_agent.input_skill.keyboard_type = AsyncMock(return_value="✅ OK")

        with (
            patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab,
            patch("venom_core.agents.ghost_agent.SETTINGS") as mock_settings,
        ):
            mock_settings.ENABLE_GHOST_AGENT = True
            mock_grab.return_value = Image.new("RGB", (100, 100))

            result = await ghost_agent.process("Otwórz notatnik i napisz 'Hello Venom'")

            assert "RAPORT GHOST AGENT" in result
            assert "Wykonane kroki" in result
            # Sprawdź czy kroki zostały wykonane
            assert len(ghost_agent.action_history) > 0

    @pytest.mark.asyncio
    async def test_create_action_plan_notepad(self, ghost_agent):
        """Test tworzenia planu dla zadania notatnika."""
        plan = await ghost_agent._create_action_plan("Otwórz notatnik")

        assert len(plan) > 0
        # Powinien zawierać hotkey Win+R
        assert any(step.action_type == "hotkey" for step in plan)
        # Powinien zawierać type 'notepad'
        assert any(step.action_type == "type" for step in plan)

    @pytest.mark.asyncio
    async def test_create_action_plan_spotify(self, ghost_agent):
        """Test tworzenia planu dla Spotify."""
        plan = await ghost_agent._create_action_plan(
            "Włącz następną piosenkę w Spotify"
        )

        assert len(plan) > 0
        # Powinien zawierać screenshot i locate
        assert any(step.action_type == "screenshot" for step in plan)
        assert any(step.action_type == "locate" for step in plan)

    @pytest.mark.asyncio
    async def test_execute_plan_screenshot_step(self, ghost_agent):
        """Test wykonania kroku screenshot."""
        plan = [ActionStep("screenshot", "Zrób zrzut", {})]

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (100, 100))

            result = await ghost_agent._execute_plan(plan)

            assert "RAPORT" in result
            assert len(ghost_agent.action_history) == 1
            assert ghost_agent.action_history[0].status == "success"

    @pytest.mark.asyncio
    async def test_execute_plan_click_step(self, ghost_agent):
        """Test wykonania kroku kliknięcia."""
        plan = [ActionStep("click", "Kliknij", {"x": 100, "y": 200})]

        ghost_agent.input_skill.mouse_click = AsyncMock(return_value="✅ Kliknięto")

        result = await ghost_agent._execute_plan(plan)

        assert "RAPORT" in result
        assert len(ghost_agent.action_history) == 1
        assert ghost_agent.action_history[0].status == "success"

    @pytest.mark.asyncio
    async def test_execute_plan_type_step(self, ghost_agent):
        """Test wykonania kroku pisania."""
        plan = [ActionStep("type", "Wpisz tekst", {"text": "Hello"})]

        ghost_agent.input_skill.keyboard_type = AsyncMock(return_value="✅ Wpisano")

        await ghost_agent._execute_plan(plan)

        assert len(ghost_agent.action_history) == 1
        assert ghost_agent.action_history[0].status == "success"

    @pytest.mark.asyncio
    async def test_execute_plan_hotkey_step(self, ghost_agent):
        """Test wykonania kroku hotkey."""
        plan = [ActionStep("hotkey", "Naciśnij Ctrl+S", {"keys": "ctrl+s"})]

        ghost_agent.input_skill.keyboard_hotkey = AsyncMock(return_value="✅ Wykonano")

        await ghost_agent._execute_plan(plan)

        assert len(ghost_agent.action_history) == 1
        assert ghost_agent.action_history[0].status == "success"

    @pytest.mark.asyncio
    async def test_execute_plan_wait_step(self, ghost_agent):
        """Test wykonania kroku oczekiwania."""
        plan = [ActionStep("wait", "Czekaj 0.1s", {"duration": 0.01})]

        await ghost_agent._execute_plan(plan)

        assert len(ghost_agent.action_history) == 1
        assert ghost_agent.action_history[0].status == "success"
        assert "Oczekiwano" in ghost_agent.action_history[0].result

    @pytest.mark.asyncio
    async def test_execute_plan_locate_step(self, ghost_agent):
        """Test wykonania kroku lokalizacji."""
        plan = [ActionStep("locate", "Znajdź przycisk", {"description": "red button"})]

        ghost_agent.vision.locate_element = AsyncMock(return_value=(50, 50))

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (100, 100))

            await ghost_agent._execute_plan(plan)

            assert len(ghost_agent.action_history) == 1
            assert "znaleziony" in ghost_agent.action_history[0].result.lower()

    @pytest.mark.asyncio
    async def test_execute_plan_max_steps_limit(self, ghost_agent):
        """Test limitu maksymalnej liczby kroków."""
        ghost_agent.max_steps = 3
        # Stwórz plan z 5 krokami
        plan = [ActionStep("wait", f"Krok {i}", {"duration": 0.01}) for i in range(5)]

        await ghost_agent._execute_plan(plan)

        # Powinno wykonać tylko 3 kroki
        assert len(ghost_agent.action_history) <= 3

    @pytest.mark.asyncio
    async def test_execute_plan_with_emergency_stop(self, ghost_agent):
        """Test przerwania planu przez emergency stop."""
        plan = [ActionStep("wait", "Krok", {"duration": 0.01}) for _ in range(5)]

        # Aktywuj emergency stop po pierwszym kroku
        async def activate_emergency(*args):
            await asyncio.sleep(0.01)
            ghost_agent.emergency_stop = True

        emergency_task = asyncio.create_task(activate_emergency())

        result = await ghost_agent._execute_plan(plan)
        await emergency_task

        assert "Emergency Stop" in result or len(ghost_agent.action_history) < 5

    def test_generate_report(self, ghost_agent):
        """Test generowania raportu."""
        # Dodaj kilka kroków do historii
        step1 = ActionStep("click", "Krok 1", {})
        step1.status = "success"
        step1.result = "OK"

        step2 = ActionStep("type", "Krok 2", {})
        step2.status = "failed"
        step2.result = "Błąd"

        ghost_agent.action_history = [step1, step2]

        report = ghost_agent._generate_report()

        assert "RAPORT GHOST AGENT" in report
        assert "Wykonane kroki: 2" in report
        assert "Udane: 1" in report
        assert "Nieudane: 1" in report
        assert "Krok 1" in report
        assert "Krok 2" in report

    def test_emergency_stop_trigger(self, ghost_agent):
        """Test aktywacji emergency stop."""
        ghost_agent.is_running = True
        ghost_agent.emergency_stop_trigger()

        assert ghost_agent.emergency_stop is True
        assert ghost_agent.is_running is False

    def test_get_status(self, ghost_agent):
        """Test pobierania statusu agenta."""
        ghost_agent.input_skill.get_screen_size = MagicMock(return_value=(1920, 1080))

        status = ghost_agent.get_status()

        assert "is_running" in status
        assert "emergency_stop" in status
        assert "max_steps" in status
        assert status["max_steps"] == 10
        assert "screen_size" in status
        assert status["screen_size"] == (1920, 1080)

    @pytest.mark.asyncio
    async def test_execute_plan_click_with_located_coords(self, ghost_agent):
        """Test kliknięcia używając współrzędnych z locate."""
        plan = [
            ActionStep("locate", "Znajdź", {"description": "button"}),
            ActionStep("click", "Kliknij", {"use_located": True}),
        ]

        ghost_agent.vision.locate_element = AsyncMock(return_value=(100, 150))
        ghost_agent.input_skill.mouse_click = AsyncMock(return_value="✅ Kliknięto")

        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (200, 200))

            await ghost_agent._execute_plan(plan)

            # Sprawdź czy mouse_click został wywołany z właściwymi współrzędnymi
            ghost_agent.input_skill.mouse_click.assert_called_with(100, 150)

    def test_compute_screen_change_percent(self, ghost_agent):
        pre = (np.zeros((4, 4, 3), dtype=np.uint8),)
        post = np.full((4, 4, 3), 255, dtype=np.uint8)
        percent = ghost_agent._compute_screen_change_percent(pre[0], post)
        assert percent == pytest.approx(100.0)

    def test_verify_locate_step_false_when_result_missing(self, ghost_agent):
        step = ActionStep("locate", "locate")
        step.result = None
        assert ghost_agent._verify_locate_step(step) is False

    def test_verify_step_result_unknown_action_type_assumes_success(self, ghost_agent):
        step = ActionStep("unknown", "Unknown action")
        with patch("venom_core.agents.ghost_agent.ImageGrab.grab") as mock_grab:
            mock_grab.return_value = Image.new("RGB", (100, 100))
            assert ghost_agent._verify_step_result(step, None) is True
