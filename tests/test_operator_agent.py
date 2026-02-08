"""Testy jednostkowe dla modułu operator (OperatorAgent)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.agents.operator import OperatorAgent
from venom_core.infrastructure.hardware_pi import HardwareBridge


class TestOperatorAgent:
    """Testy dla OperatorAgent."""

    @pytest.fixture
    def mock_kernel(self):
        """Mock Semantic Kernel."""
        kernel = MagicMock()
        kernel.get_service = MagicMock()
        return kernel

    @pytest.fixture
    def mock_hardware_bridge(self):
        """Mock HardwareBridge."""
        bridge = MagicMock(spec=HardwareBridge)
        bridge.connected = True
        return bridge

    def test_initialization(self, mock_kernel):
        """Test inicjalizacji OperatorAgent."""
        agent = OperatorAgent(kernel=mock_kernel, hardware_bridge=None)

        assert agent.kernel == mock_kernel
        assert agent.hardware_bridge is None
        assert agent.chat_history is not None
        assert len(agent.chat_history.messages) == 1  # System prompt

    def test_initialization_with_hardware_bridge(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test inicjalizacji z hardware bridge."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        assert agent.hardware_bridge == mock_hardware_bridge

    @pytest.mark.asyncio
    async def test_is_hardware_command_true(self, mock_kernel):
        """Test rozpoznawania komend sprzętowych."""
        agent = OperatorAgent(kernel=mock_kernel)

        # Komendy sprzętowe
        assert agent._is_hardware_command("status Rider-Pi") is True
        assert agent._is_hardware_command("włącz GPIO 17") is True
        assert agent._is_hardware_command("wyłącz pin 4") is True
        assert agent._is_hardware_command("jaka jest temperatura?") is True
        assert agent._is_hardware_command("procedura awaryjna reset") is True

    @pytest.mark.asyncio
    async def test_is_hardware_command_false(self, mock_kernel):
        """Test rozpoznawania komend niesprzętowych."""
        agent = OperatorAgent(kernel=mock_kernel)

        # Komendy niesprzętowe
        assert agent._is_hardware_command("jaki jest status repozytorium?") is False
        assert agent._is_hardware_command("napisz kod w Python") is False
        assert agent._is_hardware_command("zrób research o AI") is False

    @pytest.mark.asyncio
    async def test_handle_hardware_command_no_bridge(self, mock_kernel):
        """Test obsługi komendy sprzętowej bez hardware bridge."""
        agent = OperatorAgent(kernel=mock_kernel, hardware_bridge=None)

        response = await agent._handle_hardware_command("status Rider-Pi")
        assert "nie jest podłączony" in response.lower()

    @pytest.mark.asyncio
    async def test_handle_hardware_command_status(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test komendy statusu Rider-Pi."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        # Mock get_system_info
        mock_hardware_bridge.get_system_info = AsyncMock(
            return_value={
                "cpu_temp": 45.5,
                "memory_usage_percent": 42.0,
            }
        )

        response = await agent._handle_hardware_command("status Rider-Pi")
        assert "45.5" in response
        assert "42" in response

    @pytest.mark.asyncio
    async def test_handle_hardware_command_temperature(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test komendy temperatury."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        # Mock read_sensor
        mock_hardware_bridge.read_sensor = AsyncMock(return_value=47.3)

        response = await agent._handle_hardware_command("jaka jest temperatura?")
        assert "47.3" in response
        assert "stopni" in response.lower()

    @pytest.mark.asyncio
    async def test_handle_hardware_command_gpio_on(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test komendy włączenia GPIO."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        # Mock set_gpio
        mock_hardware_bridge.set_gpio = AsyncMock(return_value=True)

        response = await agent._handle_hardware_command("włącz GPIO 17")
        assert "17" in response
        assert "włączony" in response.lower()

    @pytest.mark.asyncio
    async def test_handle_hardware_command_gpio_off(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test komendy wyłączenia GPIO."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        # Mock set_gpio
        mock_hardware_bridge.set_gpio = AsyncMock(return_value=True)

        response = await agent._handle_hardware_command("wyłącz GPIO 4")
        assert "4" in response
        assert "wyłączony" in response.lower()

    @pytest.mark.asyncio
    async def test_handle_hardware_command_emergency(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test komendy procedury awaryjnej."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        # Mock emergency_procedure
        mock_hardware_bridge.emergency_procedure = AsyncMock(return_value=True)

        response = await agent._handle_hardware_command("procedura awaryjna reset GPIO")
        assert "procedura" in response.lower()

    @pytest.mark.asyncio
    async def test_process_hardware_command(self, mock_kernel, mock_hardware_bridge):
        """Test przetwarzania komendy sprzętowej przez process()."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        mock_hardware_bridge.read_sensor = AsyncMock(return_value=45.0)

        response = await agent.process("temperatura")
        assert isinstance(response, str)
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_summarize_for_voice(self, mock_kernel):
        """Test streszczania dla głosu."""
        agent = OperatorAgent(kernel=mock_kernel)

        # Mock chat service
        mock_chat_service = MagicMock()
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: "Krótkie streszczenie."
        mock_chat_service.get_chat_message_content = AsyncMock(
            return_value=mock_response
        )
        mock_kernel.get_service.return_value = mock_chat_service

        long_text = """
        To jest bardzo długi tekst z wieloma szczegółami technicznymi.
        Zawiera kod:
        ```python
        def hello():
            print("Hello, world!")
        ```
        I wiele innych informacji które nie są potrzebne w odpowiedzi głosowej.
        """

        summary = await agent.summarize_for_voice(long_text)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_clear_history(self, mock_kernel):
        """Test czyszczenia historii."""
        agent = OperatorAgent(kernel=mock_kernel)

        # Dodaj kilka wiadomości
        agent.chat_history.add_user_message("Test 1")
        agent.chat_history.add_assistant_message("Response 1")

        initial_count = len(agent.chat_history.messages)
        assert initial_count > 1

        # Wyczyść historię
        agent.clear_history()

        # Powinna pozostać tylko system message
        assert len(agent.chat_history.messages) == 1

    @pytest.mark.asyncio
    async def test_process_non_hardware_command(self, mock_kernel):
        """Test przetwarzania komendy niesprzętowej."""
        agent = OperatorAgent(kernel=mock_kernel)

        # Mock chat service
        mock_chat_service = MagicMock()
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: "Odpowiedź na pytanie."
        mock_chat_service.get_chat_message_content = AsyncMock(
            return_value=mock_response
        )
        mock_kernel.get_service.return_value = mock_chat_service

        response = await agent.process("Jaki jest status repozytorium?")
        assert isinstance(response, str)
        assert len(response) > 0
