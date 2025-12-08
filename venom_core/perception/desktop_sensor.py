"""
Moduł: desktop_sensor - Sensor Pulpitu dla świadomości kontekstu pracy użytkownika.

Ten moduł monitoruje aktywność użytkownika (aktywne okno, schowek) w celu
zapewnienia kontekstowej pomocy przez Shadow Agent.
"""

import asyncio
import platform
import re
from datetime import datetime
from typing import Callable, Optional

import pyperclip

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class PrivacyFilter:
    """Filtr prywatności dla wrażliwych danych."""

    # Wzorce regex dla wrażliwych danych
    SENSITIVE_PATTERNS = [
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # Numery kart kredytowych
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Emaile (opcjonalnie)
        r"(?i)(password|hasło|passwd|pwd)[\s:=]+\S+",  # Hasła
        r"(?i)(api[_-]?key|token|secret)[\s:=]+[A-Za-z0-9_\-]+",  # API keys
        r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",  # Adresy IP (opcjonalnie)
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

                # Czekaj przed następnym sprawdzeniem (1 sekunda)
                await asyncio.sleep(1)

            except asyncio.CancelledError:
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
                    sanitized = PrivacyFilter.sanitize(current_content)
                    if not sanitized:
                        return  # Odrzuć wrażliwe dane
                else:
                    sanitized = current_content[:1000]  # Obetnij do 1000 znaków

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
            title = self.get_active_window_title()

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

    def get_active_window_title(self) -> str:
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
                return self._get_window_title_linux()
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

    def _get_window_title_linux(self) -> str:
        """Pobiera tytuł aktywnego okna na Linux (wymaga X11)."""
        try:
            import subprocess

            # Użyj xdotool (jeśli zainstalowane)
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if result.returncode == 0:
                return result.stdout.strip()
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
        try:
            from PIL import ImageGrab

            if self._is_wsl:
                logger.warning("Zrzuty ekranu niedostępne w WSL2 bez satelity")
                return None

            if region:
                img = ImageGrab.grab(bbox=region)
            else:
                img = ImageGrab.grab()

            # Konwertuj do bytes
            from io import BytesIO

            buffer = BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()

        except ImportError:
            logger.error(
                "PIL/Pillow nie jest zainstalowane - zrzuty ekranu niedostępne"
            )
            return None
        except Exception as e:
            logger.error(f"Błąd przy robieniu zrzutu ekranu: {e}")
            return None

    def get_status(self) -> dict:
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
        }
