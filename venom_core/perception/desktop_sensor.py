"""
Moduł: desktop_sensor - Sensor Pulpitu dla świadomości kontekstu pracy użytkownika.

Ten moduł monitoruje aktywność użytkownika (aktywne okno, schowek) w celu
zapewnienia kontekstowej pomocy przez Shadow Agent.
"""

import asyncio
import platform
import re
import threading
from datetime import datetime
from io import BytesIO
from typing import Any, Callable, Dict, List, Optional

try:
    from PIL import ImageGrab

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

import pyperclip

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class PrivacyFilter:
    """Filtr prywatności dla wrażliwych danych."""

    # Wzorce regex dla wrażliwych danych
    SENSITIVE_PATTERNS = [
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # Numery kart kredytowych (basic pattern - może dawać false positives, brak walidacji Luhn)
        r"(?i)(password|hasło|passwd|pwd)[\s:=]+\S+",  # Hasła
        r"(?i)(api[_-]?key|token|secret)[\s:=]+[A-Za-z0-9_\-]+",  # API keys
        r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",  # Klucze prywatne
    ]

    @classmethod
    def is_sensitive(cls, text: str) -> bool:
        """
        Sprawdza czy tekst zawiera wrażliwe dane.

        Args:
            text: Tekst do sprawdzenia

        Returns:
            True jeśli wykryto wrażliwe dane
        """
        for pattern in cls.SENSITIVE_PATTERNS:
            if re.search(pattern, text):
                return True
        return False

    @classmethod
    def sanitize(cls, text: str, max_length: int = 1000) -> str:
        """
        Oczyszcza tekst z wrażliwych danych i obcina do max_length.

        Args:
            text: Tekst do oczyszczenia
            max_length: Maksymalna długość tekstu

        Returns:
            Oczyszczony tekst
        """
        if cls.is_sensitive(text):
            logger.warning("Wykryto wrażliwe dane w schowku - odrzucam")
            return ""

        # Obetnij tekst jeśli za długi
        if len(text) > max_length:
            text = text[:max_length] + "..."

        return text


class DesktopSensor:
    """
    Sensor Pulpitu - monitoruje aktywność użytkownika.

    Funkcje:
    - Monitor schowka (clipboard)
    - Wykrywanie aktywnego okna (z limitacjami na WSL2)
    - Filtrowanie wrażliwych danych
    """

    # Klawisze bezpieczne do logowania (funkcyjne/nawigacyjne)
    SAFE_KEYS = {
        "enter",
        "tab",
        "space",
        "backspace",
        "delete",
        "esc",
        "up",
        "down",
        "left",
        "right",
        "home",
        "end",
        "page_up",
        "page_down",
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
        "f6",
        "f7",
        "f8",
        "f9",
        "f10",
        "f11",
        "f12",
    }

    def __init__(
        self,
        clipboard_callback: Optional[Callable] = None,
        window_callback: Optional[Callable] = None,
        privacy_filter: bool = True,
    ):
        """
        Inicjalizacja Desktop Sensor.

        Args:
            clipboard_callback: Async callback wywoływany przy zmianie schowka
            window_callback: Async callback wywoływany przy zmianie aktywnego okna
            privacy_filter: Czy włączyć filtr prywatności
        """
        self.clipboard_callback = clipboard_callback
        self.window_callback = window_callback
        self.privacy_filter = privacy_filter

        self._is_running = False
        self._last_clipboard_content = ""
        self._last_active_window = ""
        self._monitor_task: Optional[asyncio.Task] = None

        self.system = platform.system()
        logger.info(f"DesktopSensor zainicjalizowany na {self.system}")

        # Sprawdź czy jesteśmy w WSL2
        self._is_wsl = self._detect_wsl()
        if self._is_wsl:
            logger.warning(
                "WSL2 wykryty - funkcje okien mogą wymagać satelity na Windows"
            )

    def _detect_wsl(self) -> bool:
        """
        Wykrywa czy kod działa w WSL2.

        Returns:
            True jeśli WSL2
        """
        try:
            with open("/proc/version", "r") as f:
                version = f.read().lower()
                return "microsoft" in version or "wsl" in version
        except Exception:
            return False

    async def start(self) -> None:
        """Uruchamia monitoring."""
        if self._is_running:
            logger.warning("DesktopSensor już działa")
            return

        self._is_running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("DesktopSensor uruchomiony")

    async def stop(self) -> None:
        """Zatrzymuje monitoring."""
        if not self._is_running:
            logger.warning("DesktopSensor nie działa")
            return

        self._is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("DesktopSensor zatrzymany")

    async def _monitor_loop(self) -> None:
        """Główna pętla monitoringu."""
        while self._is_running:
            try:
                # Monitor schowka
                await self._check_clipboard()

                # Monitor aktywnego okna (jeśli nie WSL)
                if not self._is_wsl:
                    await self._check_active_window()

                # Czekaj przed następnym sprawdzeniem
                await asyncio.sleep(SETTINGS.SHADOW_CHECK_INTERVAL)

            except asyncio.CancelledError:
                # Oczekiwany wyjątek przy anulowaniu taska – ignorujemy
                break
            except Exception as e:
                logger.error(f"Błąd w pętli monitoringu: {e}")
                await asyncio.sleep(5)  # Poczekaj dłużej przy błędzie

    async def _check_clipboard(self) -> None:
        """Sprawdza zmiany w schowku."""
        try:
            # Użyj pyperclip do odczytu schowka
            current_content = pyperclip.paste()

            # Sprawdź czy zawartość się zmieniła
            if current_content and current_content != self._last_clipboard_content:
                self._last_clipboard_content = current_content

                # Filtruj wrażliwe dane
                if self.privacy_filter:
                    sanitized = PrivacyFilter.sanitize(
                        current_content, max_length=SETTINGS.SHADOW_CLIPBOARD_MAX_LENGTH
                    )
                    if not sanitized:
                        return  # Odrzuć wrażliwe dane
                else:
                    sanitized = current_content[: SETTINGS.SHADOW_CLIPBOARD_MAX_LENGTH]

                logger.info(f"Zmiana w schowku: {len(sanitized)} znaków")

                # Wywołaj callback
                if self.clipboard_callback:
                    await self.clipboard_callback(
                        {
                            "type": "clipboard",
                            "content": sanitized,
                            "timestamp": datetime.now().isoformat(),
                            "length": len(current_content),
                        }
                    )

        except Exception as e:
            logger.error(f"Błąd przy sprawdzaniu schowka: {e}")

    async def _check_active_window(self) -> None:
        """Sprawdza aktywne okno (tylko native Linux/Windows)."""
        try:
            title = await self.get_active_window_title()

            if title and title != self._last_active_window:
                self._last_active_window = title
                logger.info(f"Zmiana aktywnego okna: {title}")

                # Wywołaj callback
                if self.window_callback:
                    await self.window_callback(
                        {
                            "type": "window",
                            "title": title,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

        except Exception as e:
            logger.error(f"Błąd przy sprawdzaniu aktywnego okna: {e}")

    async def get_active_window_title(self) -> str:
        """
        Zwraca tytuł aktywnego okna.

        Returns:
            Tytuł aktywnego okna lub pusty string jeśli niedostępne
        """
        if self._is_wsl:
            logger.debug("Funkcja okien niedostępna w WSL2 bez satelity")
            return ""

        try:
            if self.system == "Windows":
                return self._get_window_title_windows()
            elif self.system == "Linux":
                return await self._get_window_title_linux()
            else:
                logger.warning(f"System {self.system} nie jest wspierany")
                return ""
        except Exception as e:
            logger.error(f"Błąd przy pobieraniu tytułu okna: {e}")
            return ""

    def _get_window_title_windows(self) -> str:
        """Pobiera tytuł aktywnego okna na Windows."""
        try:
            import ctypes

            # GetForegroundWindow i GetWindowText z user32.dll
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()

            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)

            return buff.value
        except Exception as e:
            logger.error(f"Błąd przy pobieraniu okna Windows: {e}")
            return ""

    async def _get_window_title_linux(self) -> str:
        """Pobiera tytuł aktywnego okna na Linux (wymaga X11)."""
        try:
            # Użyj xdotool (jeśli zainstalowane)
            process = await asyncio.create_subprocess_exec(
                "xdotool",
                "getactivewindow",
                "getwindowname",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=2
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ""

            if process.returncode == 0:
                return stdout.decode().strip()
            else:
                return ""
        except FileNotFoundError:
            logger.warning("xdotool nie jest zainstalowany - funkcja okien niedostępna")
            return ""
        except Exception as e:
            logger.error(f"Błąd przy pobieraniu okna Linux: {e}")
            return ""

    def capture_screen_region(self, region: Optional[tuple] = None) -> Optional[bytes]:
        """
        Robi zrzut ekranu (opcjonalnie określonego regionu).

        Args:
            region: Tuple (x, y, width, height) lub None dla całego ekranu

        Returns:
            Bytes zawierające obraz PNG lub None przy błędzie
        """
        if not PIL_AVAILABLE:
            logger.error(
                "PIL/Pillow nie jest zainstalowane - zrzuty ekranu niedostępne"
            )
            return None

        try:
            if self._is_wsl:
                logger.warning("Zrzuty ekranu niedostępne w WSL2 bez satelity")
                return None

            if region:
                img = ImageGrab.grab(bbox=region)
            else:
                img = ImageGrab.grab()

            # Konwertuj do bytes
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Błąd przy robieniu zrzutu ekranu: {e}")
            return None

    def start_recording(self) -> None:
        """
        Rozpoczyna tryb nagrywania (recording mode).

        W tym trybie sensor zapisuje wszystkie akcje użytkownika
        które mogą być później odtworzone przez GhostAgent.

        Używa biblioteki pynput do przechwytywania zdarzeń myszy i klawiatury.
        """
        if getattr(self, "_recording_mode", False):
            logger.warning("Nagrywanie już jest włączone")
            return

        self._recording_mode = True
        self._recorded_actions = []
        self._mouse_listener = None
        self._keyboard_listener = None
        self._mouse_move_counter = 0  # Licznik dla próbkowania ruchów myszy
        self._mouse_move_lock = (
            threading.Lock()
        )  # Lock dla thread-safe dostępu do licznika

        try:
            from pynput import keyboard, mouse

            # Callback dla myszy
            def on_click(x, y, button, pressed):
                if self._recording_mode:
                    self._recorded_actions.append(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "event_type": "mouse_click",
                            "payload": {
                                "x": x,
                                "y": y,
                                "button": str(button),
                                "pressed": pressed,
                            },
                        }
                    )

            def on_scroll(x, y, dx, dy):
                if self._recording_mode:
                    self._recorded_actions.append(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "event_type": "mouse_scroll",
                            "payload": {"x": x, "y": y, "dx": dx, "dy": dy},
                        }
                    )

            def on_move(x, y):
                # Zapisuj tylko co 10-ty ruch myszy, aby nie zaśmiecać logów
                if self._recording_mode:
                    with self._mouse_move_lock:
                        self._mouse_move_counter += 1
                        if self._mouse_move_counter % 10 == 0:
                            self._recorded_actions.append(
                                {
                                    "timestamp": datetime.now().isoformat(),
                                    "event_type": "mouse_move",
                                    "payload": {"x": x, "y": y},
                                }
                            )

            # Callback dla klawiatury - bezpieczne logowanie
            def on_press(key):
                if not self._recording_mode:
                    return

                # Bezpieczeństwo: nie loguj normalnych klawiszy jeśli privacy_filter włączony
                # Loguj tylko klawisze funkcyjne i specjalne
                if self.privacy_filter:
                    # Sprawdź czy to klawisz specjalny/funkcyjny
                    try:
                        key_name = key.name if hasattr(key, "name") else None
                        # Użyj stałej klasy SAFE_KEYS
                        if key_name and key_name.lower() in self.SAFE_KEYS:
                            self._recorded_actions.append(
                                {
                                    "timestamp": datetime.now().isoformat(),
                                    "event_type": "keyboard_press",
                                    "payload": {"key": key_name},
                                }
                            )
                    except AttributeError:
                        # Ignoruj zwykłe znaki w trybie bezpiecznym
                        pass
                else:
                    # Bez filtra prywatności - loguj wszystko
                    try:
                        key_str = key.char if hasattr(key, "char") else str(key)
                        self._recorded_actions.append(
                            {
                                "timestamp": datetime.now().isoformat(),
                                "event_type": "keyboard_press",
                                "payload": {"key": key_str},
                            }
                        )
                    except AttributeError:
                        pass

            # Uruchom listenery w osobnych wątkach
            self._mouse_listener = mouse.Listener(
                on_click=on_click, on_scroll=on_scroll, on_move=on_move
            )
            self._keyboard_listener = keyboard.Listener(on_press=on_press)

            self._mouse_listener.start()
            self._keyboard_listener.start()

            logger.info("DesktopSensor: tryb nagrywania WŁĄCZONY (pynput aktywne)")

        except ImportError:
            logger.error("pynput nie jest zainstalowany - nagrywanie akcji niedostępne")
            self._recording_mode = False
            raise
        except Exception as e:
            logger.error(f"Błąd podczas uruchamiania nagrywania: {e}")
            self._recording_mode = False
            raise

    def stop_recording(self) -> List[Dict[str, Any]]:
        """
        Zatrzymuje tryb nagrywania i zwraca nagrane akcje.

        Returns:
            Lista nagranych akcji ze strukturą:
            {
                "timestamp": str (ISO 8601),
                "event_type": str (mouse_click, mouse_scroll, mouse_move, keyboard_press),
                "payload": dict (szczegóły zdarzenia)
            }
        """
        if not getattr(self, "_recording_mode", False):
            logger.warning("Nagrywanie nie jest włączone")
            return []

        self._recording_mode = False

        # Zatrzymaj listenery
        try:
            if hasattr(self, "_mouse_listener") and self._mouse_listener:
                self._mouse_listener.stop()
                self._mouse_listener = None
            if hasattr(self, "_keyboard_listener") and self._keyboard_listener:
                self._keyboard_listener.stop()
                self._keyboard_listener = None
        except Exception as e:
            logger.error(f"Błąd podczas zatrzymywania listenerów: {e}")

        # Zwróć kopię i wyczyść bufor
        actions = getattr(self, "_recorded_actions", []).copy()
        self._recorded_actions = []

        logger.info(f"DesktopSensor: tryb nagrywania WYŁĄCZONY ({len(actions)} akcji)")
        return actions

    def is_recording(self) -> bool:
        """
        Sprawdza czy sensor jest w trybie nagrywania.

        Returns:
            True jeśli nagrywa
        """
        return getattr(self, "_recording_mode", False)

    def get_status(self) -> dict[str, any]:
        """
        Zwraca status sensora.

        Returns:
            Słownik ze statusem
        """
        return {
            "is_running": self._is_running,
            "system": self.system,
            "is_wsl": self._is_wsl,
            "privacy_filter": self.privacy_filter,
            "last_clipboard_length": len(self._last_clipboard_content),
            "last_active_window": self._last_active_window,
            "recording_mode": getattr(self, "_recording_mode", False),
            "recorded_actions_count": len(getattr(self, "_recorded_actions", [])),
        }
