"""Testy jednostkowe dla DemonstrationRecorder."""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from venom_core.perception.recorder import (
    DemonstrationRecorder,
    DemonstrationSession,
    InputEvent,
)


class TestInputEvent:
    """Testy dla InputEvent."""

    def test_input_event_initialization(self):
        """Test inicjalizacji InputEvent."""
        event = InputEvent(
            timestamp=time.time(),
            event_type="mouse_click",
            data={"x": 100, "y": 200, "button": "left", "pressed": True},
        )

        assert event.event_type == "mouse_click"
        assert event.data["x"] == 100
        assert event.data["y"] == 200


class TestDemonstrationSession:
    """Testy dla DemonstrationSession."""

    def test_session_initialization(self):
        """Test inicjalizacji DemonstrationSession."""
        session = DemonstrationSession(
            session_id="test_session",
            start_time=time.time(),
        )

        assert session.session_id == "test_session"
        assert session.end_time is None
        assert len(session.events) == 0


class TestDemonstrationRecorder:
    """Testy dla DemonstrationRecorder."""

    @pytest.fixture
    def temp_workspace(self):
        """Fixture: tymczasowy katalog workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def recorder(self, temp_workspace):
        """Fixture: DemonstrationRecorder."""
        return DemonstrationRecorder(workspace_root=temp_workspace)

    def test_initialization(self, recorder, temp_workspace):
        """Test inicjalizacji DemonstrationRecorder."""
        assert recorder.workspace_root == Path(temp_workspace)
        assert recorder.sessions_dir.exists()
        assert not recorder.is_recording
        assert recorder.current_session is None

    def test_start_recording(self, recorder):
        """Test rozpoczęcia nagrywania."""
        session_id = recorder.start_recording(session_name="test_session")

        assert recorder.is_recording
        assert recorder.current_session is not None
        assert recorder.current_session.session_id == "test_session"
        assert session_id == "test_session"

    def test_start_recording_already_running(self, recorder):
        """Test próby rozpoczęcia nagrywania gdy już trwa."""
        session_id1 = recorder.start_recording(session_name="test_session")
        session_id2 = recorder.start_recording(session_name="test_session2")

        # Powinno zwrócić to samo ID
        assert session_id1 == session_id2
        assert recorder.current_session.session_id == "test_session"

    def test_stop_recording(self, recorder):
        """Test zatrzymania nagrywania."""
        with (
            patch.object(recorder, "_start_listeners"),
            patch.object(recorder, "_stop_listeners"),
        ):
            recorder.start_recording(session_name="test_session")
            session_path = recorder.stop_recording()

            assert not recorder.is_recording
            assert recorder.current_session is None
            assert session_path is not None
            assert Path(session_path).exists()

    def test_stop_recording_not_active(self, recorder):
        """Test próby zatrzymania gdy nie nagrywa."""
        session_path = recorder.stop_recording()

        assert session_path is None

    @patch("venom_core.perception.recorder.mouse.Listener")
    @patch("venom_core.perception.recorder.keyboard.Listener")
    def test_listeners_started(
        self, mock_keyboard_listener, mock_mouse_listener, recorder
    ):
        """Test czy listenery są uruchamiane."""
        mock_mouse_instance = MagicMock()
        mock_keyboard_instance = MagicMock()

        mock_mouse_listener.return_value = mock_mouse_instance
        mock_keyboard_listener.return_value = mock_keyboard_instance

        recorder.start_recording(session_name="test_session")

        # Sprawdź czy listenery zostały utworzone i uruchomione
        assert mock_mouse_listener.called
        assert mock_keyboard_listener.called
        assert mock_mouse_instance.start.called
        assert mock_keyboard_instance.start.called

    def test_on_mouse_click(self, recorder):
        """Test callback dla kliknięcia myszy."""
        with patch.object(recorder, "_capture_screenshot"):
            recorder.start_recording(session_name="test_session")

            # Symuluj kliknięcie
            from pynput import mouse

            recorder._on_mouse_click(100, 200, mouse.Button.left, True)

            # Sprawdź czy zdarzenie zostało zarejestrowane
            assert len(recorder.current_session.events) == 1
            event = recorder.current_session.events[0]
            assert event.event_type == "mouse_click"
            assert event.data["x"] == 100
            assert event.data["y"] == 200
            assert event.data["button"] == "left"
            assert event.data["pressed"] is True

    def test_on_key_press(self, recorder):
        """Test callback dla wciśnięcia klawisza."""
        recorder.start_recording(session_name="test_session")

        # Symuluj wciśnięcie klawisza
        from pynput.keyboard import KeyCode

        key = KeyCode.from_char("a")
        recorder._on_key_press(key)

        # Sprawdź czy zdarzenie zostało zarejestrowane
        assert len(recorder.current_session.events) == 1
        event = recorder.current_session.events[0]
        assert event.event_type == "key_press"
        assert event.data["key"] == "a"

    @patch("venom_core.perception.recorder.mss.mss")
    def test_capture_screenshot(self, mock_mss, recorder):
        """Test wykonywania zrzutu ekranu."""
        # Mock mss
        mock_sct = MagicMock()
        mock_mss.return_value.__enter__.return_value = mock_sct

        # Mock screenshot
        mock_screenshot = MagicMock()
        mock_screenshot.size = (1920, 1080)
        mock_screenshot.rgb = b"\x00" * (1920 * 1080 * 3)
        mock_sct.grab.return_value = mock_screenshot
        mock_sct.monitors = [None, {"top": 0, "left": 0, "width": 1920, "height": 1080}]

        recorder.start_recording(session_name="test_session")
        recorder._capture_screenshot(time.time(), "test")

        # Sprawdź czy zrzut został dodany do bufora
        assert len(recorder.screenshot_buffer) == 1

    def test_save_and_load_session(self, recorder):
        """Test zapisywania i ładowania sesji."""
        with (
            patch.object(recorder, "_start_listeners"),
            patch.object(recorder, "_stop_listeners"),
        ):
            # Utwórz sesję
            recorder.start_recording(session_name="test_session")

            # Dodaj zdarzenie
            event = InputEvent(
                timestamp=time.time(),
                event_type="mouse_click",
                data={"x": 100, "y": 200},
            )
            recorder.current_session.events.append(event)

            # Zatrzymaj i zapisz
            session_path = recorder.stop_recording()
            assert session_path is not None

            # Załaduj
            loaded_session = recorder.load_session("test_session")
            assert loaded_session is not None
            assert loaded_session.session_id == "test_session"
            assert len(loaded_session.events) == 1
            assert loaded_session.events[0].data["x"] == 100

    def test_list_sessions(self, recorder):
        """Test listowania sesji."""
        with (
            patch.object(recorder, "_start_listeners"),
            patch.object(recorder, "_stop_listeners"),
        ):
            # Utwórz kilka sesji
            recorder.start_recording(session_name="session1")
            recorder.stop_recording()

            recorder.start_recording(session_name="session2")
            recorder.stop_recording()

            # Listuj
            sessions = recorder.list_sessions()
            assert len(sessions) == 2
            assert "session1" in sessions
            assert "session2" in sessions

    def test_load_nonexistent_session(self, recorder):
        """Test ładowania nieistniejącej sesji."""
        session = recorder.load_session("nonexistent")
        assert session is None

    def test_session_name_sanitization(self, recorder):
        """Test sanityzacji nazw sesji aby zapobiec path traversal."""
        with (
            patch.object(recorder, "_start_listeners"),
            patch.object(recorder, "_stop_listeners"),
        ):
            # Próba path traversal
            session_id = recorder.start_recording(session_name="../../etc/passwd")
            assert session_id == "__________etc_passwd"

            # Nazwa ze spacjami
            recorder.stop_recording()
            session_id = recorder.start_recording(session_name="my session name")
            assert session_id == "my_session_name"

            # Nazwa ze znakami specjalnymi
            recorder.stop_recording()
            session_id = recorder.start_recording(session_name="test@#$%^&*()")
            assert "_" in session_id
            assert "@" not in session_id

    def test_load_session_with_path_traversal_attempt(self, recorder):
        """Test że load_session blokuje próby path traversal."""
        # Próba załadowania sesji z path traversal
        session = recorder.load_session("../../etc/passwd")
        assert session is None

        # Próba ze slashami
        session = recorder.load_session("../../../secret")
        assert session is None
