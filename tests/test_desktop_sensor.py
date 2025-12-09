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
        sensor = DesktopSensor(
            clipboard_callback=clipboard_callback, privacy_filter=True
        )

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

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Windows")
    async def test_get_active_window_title_windows(self, mock_system):
        """Test pobierania tytułu okna na Windows (mock)."""
        sensor = DesktopSensor()
        sensor._is_wsl = False

        # W testach nie możemy prawdziwie wywołać Windows API
        # Testujemy tylko że metoda nie rzuca błędu
        with patch.object(
            sensor, "_get_window_title_windows", return_value="Test Window"
        ):
            title = await sensor.get_active_window_title()
            assert title == "Test Window"

    def test_detect_wsl(self):
        """Test wykrywania WSL2."""
        sensor = DesktopSensor()

        # Sprawdź czy wykrycie działa (wynik zależny od środowiska)
        assert isinstance(sensor._is_wsl, bool)


class TestDesktopSensorRecording:
    """Testy dla funkcji nagrywania DesktopSensor."""

    @patch("pynput.mouse.Listener")
    @patch("pynput.keyboard.Listener")
    def test_start_recording_success(self, mock_keyboard_listener, mock_mouse_listener):
        """Test pomyślnego uruchomienia nagrywania."""
        # Mock listenery
        mock_mouse_instance = MagicMock()
        mock_keyboard_instance = MagicMock()
        mock_mouse_listener.return_value = mock_mouse_instance
        mock_keyboard_listener.return_value = mock_keyboard_instance

        sensor = DesktopSensor()
        sensor.start_recording()

        assert sensor.is_recording() is True
        assert sensor._recorded_actions == []
        mock_mouse_instance.start.assert_called_once()
        mock_keyboard_instance.start.assert_called_once()

    @patch("pynput.mouse.Listener")
    @patch("pynput.keyboard.Listener")
    def test_start_recording_already_running(
        self, mock_keyboard_listener, mock_mouse_listener
    ):
        """Test ponownego uruchomienia nagrywania."""
        mock_mouse_instance = MagicMock()
        mock_keyboard_instance = MagicMock()
        mock_mouse_listener.return_value = mock_mouse_instance
        mock_keyboard_listener.return_value = mock_keyboard_instance

        sensor = DesktopSensor()
        sensor.start_recording()

        # Próba ponownego uruchomienia
        sensor.start_recording()

        assert sensor.is_recording() is True

    @patch("pynput.mouse.Listener")
    @patch("pynput.keyboard.Listener")
    def test_stop_recording(self, mock_keyboard_listener, mock_mouse_listener):
        """Test zatrzymania nagrywania."""
        mock_mouse_instance = MagicMock()
        mock_keyboard_instance = MagicMock()
        mock_mouse_listener.return_value = mock_mouse_instance
        mock_keyboard_listener.return_value = mock_keyboard_instance

        sensor = DesktopSensor()
        sensor.start_recording()

        # Dodaj kilka akcji
        sensor._recorded_actions = [
            {"timestamp": "2024-01-01T00:00:00", "event_type": "mouse_click"},
            {"timestamp": "2024-01-01T00:00:01", "event_type": "keyboard_press"},
        ]

        actions = sensor.stop_recording()

        assert sensor.is_recording() is False
        assert len(actions) == 2
        assert sensor._recorded_actions == []
        mock_mouse_instance.stop.assert_called_once()
        mock_keyboard_instance.stop.assert_called_once()

    def test_stop_recording_not_started(self):
        """Test zatrzymania nagrywania gdy nie było uruchomione."""
        sensor = DesktopSensor()

        actions = sensor.stop_recording()

        assert actions == []
        assert sensor.is_recording() is False

    @patch("pynput.mouse.Listener")
    @patch("pynput.keyboard.Listener")
    def test_recording_mouse_click(self, mock_keyboard_listener, mock_mouse_listener):
        """Test nagrywania kliknięć myszy."""
        sensor = DesktopSensor()

        # Przechwyć callback on_click
        on_click_callback = None

        def capture_mouse_listeners(**kwargs):
            nonlocal on_click_callback
            on_click_callback = kwargs.get("on_click")
            return MagicMock()

        mock_mouse_listener.side_effect = capture_mouse_listeners
        mock_keyboard_listener.return_value = MagicMock()

        sensor.start_recording()

        # Symuluj kliknięcie myszy
        if on_click_callback:
            on_click_callback(100, 200, "Button.left", True)

        assert len(sensor._recorded_actions) == 1
        action = sensor._recorded_actions[0]
        assert action["event_type"] == "mouse_click"
        assert action["payload"]["x"] == 100
        assert action["payload"]["y"] == 200
        assert action["payload"]["pressed"] is True

    @patch("pynput.mouse.Listener")
    @patch("pynput.keyboard.Listener")
    def test_recording_keyboard_with_privacy_filter(
        self, mock_keyboard_listener, mock_mouse_listener
    ):
        """Test nagrywania klawiatury z filtrem prywatności."""
        sensor = DesktopSensor(privacy_filter=True)

        # Przechwyć callback on_press
        on_press_callback = None

        def capture_keyboard_listeners(**kwargs):
            nonlocal on_press_callback
            on_press_callback = kwargs.get("on_press")
            return MagicMock()

        mock_keyboard_listener.side_effect = capture_keyboard_listeners
        mock_mouse_listener.return_value = MagicMock()

        sensor.start_recording()

        # Symuluj wciśnięcie klawisza funkcyjnego (powinien być zapisany)
        class MockKey:
            def __init__(self, name):
                self.name = name

        if on_press_callback:
            on_press_callback(MockKey("enter"))

        # Sprawdź że klawisz funkcyjny został zapisany
        assert len(sensor._recorded_actions) == 1
        action = sensor._recorded_actions[0]
        assert action["event_type"] == "keyboard_press"
        assert action["payload"]["key"] == "enter"

    @patch("pynput.mouse.Listener")
    @patch("pynput.keyboard.Listener")
    def test_recording_keyboard_without_privacy_filter(
        self, mock_keyboard_listener, mock_mouse_listener
    ):
        """Test nagrywania klawiatury bez filtra prywatności."""
        sensor = DesktopSensor(privacy_filter=False)

        # Przechwyć callback on_press
        on_press_callback = None

        def capture_keyboard_listeners(**kwargs):
            nonlocal on_press_callback
            on_press_callback = kwargs.get("on_press")
            return MagicMock()

        mock_keyboard_listener.side_effect = capture_keyboard_listeners
        mock_mouse_listener.return_value = MagicMock()

        sensor.start_recording()

        # Symuluj wciśnięcie zwykłego klawisza
        class MockKey:
            def __init__(self, char):
                self.char = char

        if on_press_callback:
            on_press_callback(MockKey("a"))

        # Sprawdź że klawisz został zapisany
        assert len(sensor._recorded_actions) == 1
        action = sensor._recorded_actions[0]
        assert action["event_type"] == "keyboard_press"

    def test_is_recording(self):
        """Test metody is_recording."""
        sensor = DesktopSensor()

        assert sensor.is_recording() is False

        sensor._recording_mode = True
        assert sensor.is_recording() is True
