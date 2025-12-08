"""Testy jednostkowe dla DesktopSensor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.perception.desktop_sensor import DesktopSensor, PrivacyFilter


class TestPrivacyFilter:
    """Testy dla PrivacyFilter."""

    def test_is_sensitive_credit_card(self):
        """Test wykrywania numeru karty kredytowej."""
        text = "Mój numer karty to 1234 5678 9012 3456"
        assert PrivacyFilter.is_sensitive(text) is True

    def test_is_sensitive_password(self):
        """Test wykrywania hasła."""
        text = "password: mySecretPass123"
        assert PrivacyFilter.is_sensitive(text) is True

    def test_is_sensitive_api_key(self):
        """Test wykrywania API key."""
        text = "api_key=abc123xyz456"
        assert PrivacyFilter.is_sensitive(text) is True

    def test_is_not_sensitive(self):
        """Test tekstu bez wrażliwych danych."""
        text = "To jest zwykły tekst bez tajemnic"
        assert PrivacyFilter.is_sensitive(text) is False

    def test_sanitize_sensitive(self):
        """Test czyszczenia wrażliwych danych."""
        text = "password: secret123"
        result = PrivacyFilter.sanitize(text)
        assert result == ""

    def test_sanitize_long_text(self):
        """Test obcinania długiego tekstu."""
        text = "a" * 2000
        result = PrivacyFilter.sanitize(text)
        assert len(result) <= 1003  # 1000 + "..."


class TestDesktopSensor:
    """Testy dla DesktopSensor."""

    def test_initialization(self):
        """Test inicjalizacji DesktopSensor."""
        sensor = DesktopSensor()

        assert sensor._is_running is False
        assert sensor.privacy_filter is True
        assert sensor._last_clipboard_content == ""

    def test_initialization_with_callbacks(self):
        """Test inicjalizacji z callbackami."""
        clipboard_callback = AsyncMock()
        window_callback = AsyncMock()

        sensor = DesktopSensor(
            clipboard_callback=clipboard_callback, window_callback=window_callback
        )

        assert sensor.clipboard_callback == clipboard_callback
        assert sensor.window_callback == window_callback

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test uruchamiania i zatrzymywania sensora."""
        sensor = DesktopSensor()

        await sensor.start()
        assert sensor._is_running is True
        assert sensor._monitor_task is not None

        await sensor.stop()
        assert sensor._is_running is False

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test uruchamiania już działającego sensora."""
        sensor = DesktopSensor()

        await sensor.start()
        assert sensor._is_running is True

        # Próba ponownego uruchomienia
        await sensor.start()
        assert sensor._is_running is True

        await sensor.stop()

    @pytest.mark.asyncio
    @patch("pyperclip.paste")
    async def test_check_clipboard_with_content(self, mock_paste):
        """Test sprawdzania schowka z zawartością."""
        clipboard_callback = AsyncMock()
        sensor = DesktopSensor(clipboard_callback=clipboard_callback)

        # Mockuj zawartość schowka
        mock_paste.return_value = "Test clipboard content"

        await sensor._check_clipboard()

        # Sprawdź czy callback został wywołany
        clipboard_callback.assert_called_once()
        call_args = clipboard_callback.call_args[0][0]
        assert call_args["type"] == "clipboard"
        assert call_args["content"] == "Test clipboard content"

    @pytest.mark.asyncio
    @patch("pyperclip.paste")
    async def test_check_clipboard_with_sensitive_data(self, mock_paste):
        """Test sprawdzania schowka z wrażliwymi danymi."""
        clipboard_callback = AsyncMock()
        sensor = DesktopSensor(clipboard_callback=clipboard_callback, privacy_filter=True)

        # Mockuj wrażliwe dane w schowku
        mock_paste.return_value = "password: mySecretPassword123"

        await sensor._check_clipboard()

        # Callback nie powinien być wywołany (dane odrzucone)
        clipboard_callback.assert_not_called()

    @pytest.mark.asyncio
    @patch("pyperclip.paste")
    async def test_check_clipboard_no_change(self, mock_paste):
        """Test sprawdzania schowka bez zmiany."""
        clipboard_callback = AsyncMock()
        sensor = DesktopSensor(clipboard_callback=clipboard_callback)

        mock_paste.return_value = "Same content"
        sensor._last_clipboard_content = "Same content"

        await sensor._check_clipboard()

        # Callback nie powinien być wywołany (brak zmiany)
        clipboard_callback.assert_not_called()

    def test_get_status(self):
        """Test pobierania statusu sensora."""
        sensor = DesktopSensor()

        status = sensor.get_status()

        assert "is_running" in status
        assert "system" in status
        assert "is_wsl" in status
        assert "privacy_filter" in status
        assert status["is_running"] is False
        assert status["privacy_filter"] is True

    @patch("platform.system", return_value="Windows")
    def test_get_active_window_title_windows(self, mock_system):
        """Test pobierania tytułu okna na Windows (mock)."""
        sensor = DesktopSensor()
        sensor._is_wsl = False

        # W testach nie możemy prawdziwie wywołać Windows API
        # Testujemy tylko że metoda nie rzuca błędu
        with patch.object(sensor, "_get_window_title_windows", return_value="Test Window"):
            title = sensor.get_active_window_title()
            assert title == "Test Window"

    def test_detect_wsl(self):
        """Test wykrywania WSL2."""
        sensor = DesktopSensor()

        # Sprawdź czy wykrycie działa (wynik zależny od środowiska)
        assert isinstance(sensor._is_wsl, bool)
