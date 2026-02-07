"""Testy jednostkowe dla modułu hardware_pi."""

import pytest

from venom_core.infrastructure.hardware_pi import HardwareBridge

TEST_DEVICE_HOST = "rpi.local"
UNREACHABLE_TEST_HOST = "unreachable.invalid"


class TestHardwareBridge:
    """Testy dla HardwareBridge."""

    def test_initialization(self):
        """Test inicjalizacji HardwareBridge."""
        bridge = HardwareBridge(
            host=TEST_DEVICE_HOST,
            port=22,
            username="pi",
            protocol="ssh",
        )

        assert bridge.host == TEST_DEVICE_HOST
        assert bridge.port == 22
        assert bridge.username == "pi"
        assert bridge.protocol == "ssh"
        assert bridge.connected is False
        assert bridge.ssh_client is None

    def test_initialization_http_protocol(self):
        """Test inicjalizacji z protokołem HTTP."""
        bridge = HardwareBridge(
            host=TEST_DEVICE_HOST,
            port=8888,
            protocol="http",
        )

        assert bridge.protocol == "http"
        assert bridge.port == 8888

    @pytest.mark.asyncio
    async def test_connect_without_ssh(self):
        """Test połączenia bez dostępnego SSH."""
        bridge = HardwareBridge(
            host=TEST_DEVICE_HOST,
            port=22,
            username="pi",
            protocol="ssh",
        )

        # Test powinien obsłużyć brak połączenia gracefully
        # W realnym przypadku połączenie się nie powiedzie
        # ale kod nie powinien crashować
        result = await bridge.connect()
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test rozłączania."""
        bridge = HardwareBridge(
            host=TEST_DEVICE_HOST,
            port=22,
            username="pi",
            protocol="ssh",
        )

        # Disconnect powinien działać nawet jeśli nie było połączenia
        await bridge.disconnect()
        assert bridge.connected is False

    @pytest.mark.asyncio
    async def test_execute_command_not_connected(self):
        """Test wykonania komendy bez połączenia."""
        bridge = HardwareBridge(
            host=TEST_DEVICE_HOST,
            port=22,
            username="pi",
            protocol="ssh",
        )

        result = await bridge.execute_command("ls")
        assert result["return_code"] == -1
        assert "Not connected" in result["stderr"]

    @pytest.mark.asyncio
    async def test_read_sensor_not_connected(self):
        """Test odczytu czujnika bez połączenia."""
        bridge = HardwareBridge(
            host=TEST_DEVICE_HOST,
            port=22,
            username="pi",
            protocol="ssh",
        )

        result = await bridge.read_sensor("cpu_temp")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_gpio_not_connected(self):
        """Test ustawienia GPIO bez połączenia."""
        bridge = HardwareBridge(
            host=TEST_DEVICE_HOST,
            port=22,
            username="pi",
            protocol="ssh",
        )

        result = await bridge.set_gpio(17, True)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_system_info_not_connected(self):
        """Test pobierania informacji systemowych bez połączenia."""
        bridge = HardwareBridge(
            host=TEST_DEVICE_HOST,
            port=22,
            username="pi",
            protocol="ssh",
        )

        info = await bridge.get_system_info()
        assert isinstance(info, dict)
        # Bez połączenia info powinno być puste
        assert len(info) == 0

    @pytest.mark.asyncio
    async def test_emergency_procedure_not_connected(self):
        """Test procedury awaryjnej bez połączenia."""
        bridge = HardwareBridge(
            host=TEST_DEVICE_HOST,
            port=22,
            username="pi",
            protocol="ssh",
        )

        # Reset GPIO bez połączenia
        result = await bridge.emergency_procedure("reset_gpio")
        assert result is False

    @pytest.mark.asyncio
    async def test_emergency_procedure_unknown(self):
        """Test nieznanej procedury awaryjnej."""
        bridge = HardwareBridge(
            host=TEST_DEVICE_HOST,
            port=22,
            username="pi",
            protocol="ssh",
        )

        # Nieznana procedura
        result = await bridge.emergency_procedure("unknown_procedure")
        assert result is False


class TestHardwareBridgeHTTP:
    """Testy dla HardwareBridge z protokołem HTTP."""

    def test_initialization_http(self):
        """Test inicjalizacji z HTTP."""
        bridge = HardwareBridge(
            host=TEST_DEVICE_HOST,
            port=8888,
            protocol="http",
        )

        assert bridge.protocol == "http"
        assert bridge.port == 8888

    @pytest.mark.asyncio
    async def test_connect_http_unreachable(self):
        """Test połączenia HTTP z nieosiągalnym hostem."""
        bridge = HardwareBridge(
            host=UNREACHABLE_TEST_HOST,
            port=8888,
            protocol="http",
        )

        result = await bridge.connect()
        assert isinstance(result, bool)
        # Oczekujemy że połączenie się nie powiedzie
        # ale nie powinno crashować
