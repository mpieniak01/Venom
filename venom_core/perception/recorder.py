"""
Moduł: recorder - Rejestrator Demonstracji (Demonstration Recorder).

Odpowiedzialny za nagrywanie demonstracji użytkownika - synchroniczne
rejestrowanie zrzutów ekranu i zdarzeń wejścia (mysz/klawiatura).
"""

import importlib
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

try:  # pragma: no cover - zależne od środowiska testowego
    pynput_module = importlib.import_module("pynput")
    keyboard = pynput_module.keyboard
    mouse = pynput_module.mouse
    PYNPUT_AVAILABLE = True
except Exception:  # pragma: no cover
    PYNPUT_AVAILABLE = False

    class _KeyboardStub:
        class Listener:
            def __init__(self, *_, **__):
                raise RuntimeError("Biblioteka pynput nie jest zainstalowana")

    class _MouseStub:
        class Listener:
            def __init__(self, *_, **__):
                raise RuntimeError("Biblioteka pynput nie jest zainstalowana")

    keyboard = _KeyboardStub
    mouse = _MouseStub

from venom_core.config import SETTINGS
from venom_core.utils import helpers
from venom_core.utils.logger import get_logger

try:  # pragma: no cover - zależne od środowiska testowego
    import mss as _mss_module

    MSS_AVAILABLE = True
except ImportError:  # pragma: no cover
    MSS_AVAILABLE = False

    class _MSSModuleStub:
        """Minimalny stub zapewniający atrybut mss dla patchowania w testach."""

        class mss:
            def __init__(self, *_, **__):
                raise RuntimeError("Biblioteka mss nie jest zainstalowana")

    _mss_module_stub = _MSSModuleStub()

# Utrzymujemy referencję modułową (nawet jeśli to stub) aby testy mogły patchować
mss: Any
if MSS_AVAILABLE:
    mss = _mss_module
else:
    mss = _mss_module_stub

logger = get_logger(__name__)
SESSION_FILE_NAME = "session.json"


@dataclass
class InputEvent:
    """Reprezentacja pojedynczego zdarzenia wejścia."""

    timestamp: float
    event_type: str  # 'mouse_click', 'mouse_move', 'key_press', 'key_release'
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DemonstrationSession:
    """Reprezentacja sesji demonstracyjnej."""

    session_id: str
    start_time: float
    end_time: Optional[float] = None
    events: List[InputEvent] = field(default_factory=list)
    screenshots_dir: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class DemonstrationRecorder:
    """
    Rejestrator Demonstracji - nagrywa działania użytkownika.

    Funkcjonalność:
    - Synchroniczne nagrywanie zrzutów ekranu w momentach akcji
    - Logowanie zdarzeń myszy (kliknięcia, ruchy)
    - Logowanie zdarzeń klawiatury (wpisany tekst, skróty)
    - Zapis sesji do pliku JSON + katalog ze zrzutami
    """

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Inicjalizacja DemonstrationRecorder.

        Args:
            workspace_root: Katalog główny do zapisu sesji
        """
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT)
        self.sessions_dir = self.workspace_root / "demonstrations"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.is_recording = False
        self.current_session: Optional[DemonstrationSession] = None
        self.last_screenshot_time = 0.0
        self.screenshot_cooldown = 0.5  # Minimalne opóźnienie między zrzutami

        # Listenery
        self.mouse_listener: Optional[Any] = None
        self.keyboard_listener: Optional[Any] = None

        # Bufor do przechowywania zrzutów ekranu w pamięci
        self.screenshot_buffer: List[Tuple[float, Image.Image]] = []
        self.max_buffer_size = 100

        logger.info(
            f"DemonstrationRecorder zainicjalizowany (dir: {self.sessions_dir})"
        )

    def _sanitize_session_id(self, value: str) -> str:
        """
        Zwraca bezpieczny identyfikator sesji bez znaków ścieżki.

        Path traversal (../) jest neutralizowane przez zastąpienie podwójnych
        kropek blokiem podkreśleń zanim trafi do regexu.
        """

        value = value.replace("..", "____")
        value = re.sub(r"[\\/]", "_", value)
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", value)

        # Upewnij się, że nazwa nie jest pusta
        if not sanitized.strip("_"):
            return "session"
        return sanitized

    def start_recording(
        self,
        session_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Rozpoczyna nagrywanie demonstracji.

        Args:
            session_name: Opcjonalna nazwa sesji
            metadata: Opcjonalne metadane (np. opis zadania)

        Returns:
            ID sesji
        """
        if self.is_recording:
            if self.current_session:
                logger.warning("Nagrywanie już trwa")
                return self.current_session.session_id
            logger.warning("Nagrywanie oznaczone jako aktywne, ale brak sesji")
            self.is_recording = False

        # Generuj ID sesji
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Sanityzuj session_name aby zapobiec path traversal
        if session_name:
            session_name = self._sanitize_session_id(session_name)

        session_id = session_name or f"demo_{timestamp}"

        # Utwórz sesję
        self.current_session = DemonstrationSession(
            session_id=session_id,
            start_time=time.time(),
            metadata=metadata or {},
        )

        # Utwórz katalog na zrzuty
        screenshots_dir = self.sessions_dir / session_id / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.current_session.screenshots_dir = str(screenshots_dir)

        # Uruchom listenery
        self._start_listeners()
        self.is_recording = True

        logger.info(f"Rozpoczęto nagrywanie sesji: {session_id}")
        return session_id

    def stop_recording(self) -> Optional[str]:
        """
        Zatrzymuje nagrywanie i zapisuje sesję.

        Returns:
            Ścieżka do zapisanej sesji (JSON)
        """
        if not self.is_recording or not self.current_session:
            logger.warning("Nagrywanie nie jest aktywne")
            return None

        # Zatrzymaj listenery
        self._stop_listeners()
        self.is_recording = False

        # Zapisz buforowane zrzuty
        self._flush_screenshot_buffer()

        # Zakończ sesję
        self.current_session.end_time = time.time()

        # Zapisz do JSON
        session_path = self._save_session()

        logger.info(
            f"Zakończono nagrywanie sesji: {self.current_session.session_id} "
            f"(events: {len(self.current_session.events)}, "
            f"duration: {self.current_session.end_time - self.current_session.start_time:.1f}s)"
        )

        self.current_session = None
        return session_path

    def _start_listeners(self):
        """Uruchamia listenery myszy i klawiatury."""
        try:
            # Listener myszy
            self.mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click, on_move=self._on_mouse_move
            )
            self.mouse_listener.start()

            # Listener klawiatury
            self.keyboard_listener = keyboard.Listener(
                on_press=self._on_key_press, on_release=self._on_key_release
            )
            self.keyboard_listener.start()
            logger.debug("Listenery wejścia uruchomione")
        except Exception as e:
            logger.error(f"pynput nie jest dostępny - pomijam start listenerów: {e}")
            self.mouse_listener = None
            self.keyboard_listener = None

    def _stop_listeners(self):
        """Zatrzymuje listenery."""
        if self.mouse_listener:
            self.mouse_listener.stop()
            self.mouse_listener = None

        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener = None

        logger.debug("Listenery wejścia zatrzymane")

    def _on_mouse_click(self, x: int, y: int, button: object, pressed: bool):
        """
        Callback dla kliknięcia myszy.

        Args:
            x: Współrzędna X
            y: Współrzędna Y
            button: Przycisk myszy
            pressed: True jeśli wciśnięty, False jeśli zwolniony
        """
        if not self.is_recording or not self.current_session:
            return

        current_time = time.time()

        # Zdarzenie kliknięcia
        button_name = getattr(button, "name", str(button))
        event = InputEvent(
            timestamp=current_time,
            event_type="mouse_click",
            data={
                "x": x,
                "y": y,
                "button": button_name,
                "pressed": pressed,
            },
        )
        self.current_session.events.append(event)

        # Zrób zrzut ekranu jeśli minął cooldown
        if (
            pressed
            and (current_time - self.last_screenshot_time) > self.screenshot_cooldown
        ):
            self._capture_screenshot(current_time)

        logger.debug(f"Mouse click: {button_name} at ({x}, {y}) pressed={pressed}")

    def _on_mouse_move(self, x: int, y: int):
        """
        Callback dla ruchu myszy.

        Args:
            x: Współrzędna X
            y: Współrzędna Y
        """
        if not self.is_recording:
            return

        # Nie logujemy każdego ruchu - tylko co N pikseli lub co M sekund
        # dla oszczędności miejsca
        # Możemy to włączyć w przyszłości jeśli będzie potrzebne

    def _on_key_press(self, key: object):
        """
        Callback dla wciśnięcia klawisza.

        Args:
            key: Klawisz (pynput.keyboard.Key lub pynput.keyboard.KeyCode)
        """
        if not self.is_recording or not self.current_session:
            return

        current_time = time.time()

        # Konwersja klawisza na string
        key_name = key.char if hasattr(key, "char") else getattr(key, "name", str(key))

        event = InputEvent(
            timestamp=current_time,
            event_type="key_press",
            data={"key": key_name},
        )
        self.current_session.events.append(event)

        logger.debug(f"Key press: {key_name}")

    def _on_key_release(self, key: object):
        """
        Callback dla zwolnienia klawisza.

        Args:
            key: Klawisz
        """
        if not self.is_recording or not self.current_session:
            return

        current_time = time.time()

        key_name = key.char if hasattr(key, "char") else getattr(key, "name", str(key))

        event = InputEvent(
            timestamp=current_time,
            event_type="key_release",
            data={"key": key_name},
        )
        self.current_session.events.append(event)

    def _capture_screenshot(self, timestamp: float):
        """
        Wykonuje zrzut ekranu i dodaje do bufora.

        Args:
            timestamp: Czas zdarzenia
        """
        try:
            mss_factory = getattr(mss, "mss", None)
            if mss_factory is None:
                logger.warning(
                    "Biblioteka mss nie udostępnia mss() - pomijam zrzut ekranu"
                )
                return
            with mss_factory() as sct:
                # Zrób zrzut głównego monitora
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)

                # Konwertuj do PIL Image
                img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

                # Dodaj do bufora
                self.screenshot_buffer.append((timestamp, img))

                # Flush jeśli bufor pełny
                if len(self.screenshot_buffer) >= self.max_buffer_size:
                    self._flush_screenshot_buffer()

                self.last_screenshot_time = timestamp

        except Exception as e:
            logger.error(f"Błąd podczas wykonywania zrzutu ekranu: {e}")

    def _flush_screenshot_buffer(self):
        """Zapisuje buforowane zrzuty ekranu na dysk."""
        if not self.screenshot_buffer or not self.current_session:
            return

        if not self.current_session.screenshots_dir:
            logger.warning("Brak katalogu na zrzuty ekranu - pomijam zapis")
            return
        screenshots_dir = Path(self.current_session.screenshots_dir)

        for timestamp, img in self.screenshot_buffer:
            # Nazwa pliku z timestamp
            filename = f"screenshot_{timestamp:.3f}.png"
            filepath = screenshots_dir / filename

            try:
                img.save(filepath)
                logger.debug(f"Zapisano zrzut: {filename}")
            except Exception as e:
                logger.error(f"Błąd podczas zapisywania zrzutu {filename}: {e}")

        self.screenshot_buffer.clear()

    def _save_session(self) -> Optional[str]:
        """
        Zapisuje sesję do pliku JSON.

        Returns:
            Ścieżka do pliku JSON, lub None jeśli wystąpił błąd
        """
        if not self.current_session:
            logger.error("Brak aktywnej sesji do zapisu")
            return None
        session_dir = self.sessions_dir / self.current_session.session_id
        session_file = session_dir / SESSION_FILE_NAME

        # Konwertuj sesję do dict
        session_dict = asdict(self.current_session)

        # Zapisz do JSON używając helpers (Venom Standard Library)
        if not helpers.write_json(session_file, session_dict, raise_on_error=False):
            logger.error(f"Nie udało się zapisać sesji: {session_file}")
            return None

        logger.info(f"Sesja zapisana: {session_file}")
        return str(session_file)

    def load_session(self, session_id: str) -> Optional[DemonstrationSession]:
        """
        Ładuje sesję z pliku.

        Args:
            session_id: ID sesji do załadowania

        Returns:
            Obiekt DemonstrationSession lub None jeśli nie znaleziono
        """
        # Sanityzuj session_id aby zapobiec path traversal
        session_id = self._sanitize_session_id(session_id)

        session_file = self.sessions_dir / session_id / SESSION_FILE_NAME

        # Weryfikuj że ścieżka jest wewnątrz sessions_dir
        try:
            session_file_resolved = session_file.resolve()
            sessions_dir_resolved = self.sessions_dir.resolve()

            if not str(session_file_resolved).startswith(str(sessions_dir_resolved)):
                logger.error(f"Nieprawidłowa ścieżka sesji: {session_id}")
                return None
        except (OSError, ValueError) as e:
            logger.error(f"Nieprawidłowy ID sesji: {session_id}, błąd: {e}")
            return None

        if not session_file.exists():
            logger.error(f"Sesja nie znaleziona: {session_id}")
            return None

        try:
            # Odczytaj JSON używając helpers (Venom Standard Library)
            session_dict = helpers.read_json(session_file, raise_on_error=True)
            if not isinstance(session_dict, dict):
                logger.error(f"Nieprawidłowy format sesji: {session_id}")
                return None

            # Konwertuj events z dict do InputEvent
            raw_events = session_dict.get("events", [])
            events: List[InputEvent] = []
            if isinstance(raw_events, list):
                for event_dict in raw_events:
                    if isinstance(event_dict, dict):
                        events.append(InputEvent(**event_dict))
            session_dict["events"] = events

            session = DemonstrationSession(**session_dict)
            logger.info(f"Załadowano sesję: {session_id}")
            return session

        except Exception as e:
            logger.error(f"Błąd podczas ładowania sesji {session_id}: {e}")
            return None

    def list_sessions(self) -> List[str]:
        """
        Lista wszystkich zapisanych sesji.

        Returns:
            Lista ID sesji
        """
        sessions = []
        for session_dir in self.sessions_dir.iterdir():
            if session_dir.is_dir() and (session_dir / SESSION_FILE_NAME).exists():
                sessions.append(session_dir.name)

        return sorted(sessions)
