"""Testy jednostkowe dla Notifier."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.ui.notifier import Notifier


@pytest.fixture
def mock_webhook_handler():
    """Fixture dla mockowego webhook handler."""
    return AsyncMock()


@pytest.fixture
def notifier(mock_webhook_handler):
    """Fixture dla Notifier."""
    return Notifier(webhook_handler=mock_webhook_handler)


class TestNotifier:
    """Testy dla Notifier."""

    def test_initialization(self, mock_webhook_handler):
        """Test inicjalizacji Notifier."""
        notifier = Notifier(webhook_handler=mock_webhook_handler)

        assert notifier.webhook_handler == mock_webhook_handler
        assert notifier.system is not None
        assert isinstance(notifier._is_wsl, bool)

    def test_initialization_without_webhook(self):
        """Test inicjalizacji bez webhook handler."""
        notifier = Notifier()

        assert notifier.webhook_handler is None

    def test_detect_wsl(self, notifier):
        """Test wykrywania WSL2."""
        # Sprawdź czy wykrycie działa
        assert isinstance(notifier._is_wsl, bool)

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Linux")
    async def test_send_toast_linux_success(self, mock_system, mock_webhook_handler):
        """Test wysyłania powiadomienia na Linux."""
        notifier = Notifier(webhook_handler=mock_webhook_handler)
        notifier._is_wsl = False

        # Mock asyncio subprocess dla notify-send
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_process

            result = await notifier._send_toast_linux(
                title="Test Title",
                message="Test Message",
                urgency="normal",
                timeout=5000,
            )

            assert result is True

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Windows")
    async def test_send_toast_windows_fallback(self, mock_system, mock_webhook_handler):
        """Test wysyłania powiadomienia na Windows (fallback)."""
        notifier = Notifier(webhook_handler=mock_webhook_handler)
        notifier._is_wsl = False

        # Mock subprocess dla PowerShell
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_process

            result = await notifier._send_toast_windows_powershell(
                title="Test Title", message="Test Message"
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_handle_action_success(self, notifier, mock_webhook_handler):
        """Test obsługi akcji z powiadomienia."""
        action_payload = {"action": "test_action", "data": "test_data"}

        await notifier.handle_action(action_payload)

        mock_webhook_handler.assert_called_once_with(action_payload)

    @pytest.mark.asyncio
    async def test_handle_action_no_webhook(self):
        """Test obsługi akcji bez webhook handler."""
        notifier = Notifier()

        action_payload = {"action": "test_action"}

        # Nie powinno rzucić błędu, tylko zalogować warning
        await notifier.handle_action(action_payload)

    @pytest.mark.asyncio
    async def test_handle_action_error(self, notifier, mock_webhook_handler):
        """Test obsługi akcji z błędem."""
        mock_webhook_handler.side_effect = Exception("Test error")

        action_payload = {"action": "test_action"}

        # Nie powinno rzucić błędu, tylko zalogować error
        await notifier.handle_action(action_payload)

    def test_get_status(self, notifier):
        """Test pobierania statusu Notifier."""
        status = notifier.get_status()

        assert "system" in status
        assert "is_wsl" in status
        assert "webhook_handler_set" in status
        assert status["webhook_handler_set"] is True

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Linux")
    async def test_send_toast_linux_notify_not_found(
        self, mock_system, mock_webhook_handler
    ):
        """Test wysyłania powiadomienia gdy notify-send nie jest zainstalowany."""
        notifier = Notifier(webhook_handler=mock_webhook_handler)
        notifier._is_wsl = False

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = FileNotFoundError()

            result = await notifier._send_toast_linux(
                title="Test", message="Test", urgency="normal", timeout=5000
            )

            assert result is False
