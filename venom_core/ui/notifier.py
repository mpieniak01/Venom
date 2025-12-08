"""
Moduł: notifier - System powiadomień dla Venom.

Wysyła natywne powiadomienia systemowe (Windows Toast, Linux notify-send)
z możliwością interakcji (przyciski, akcje).
"""

import asyncio
import platform
import subprocess
from typing import Callable, Dict, Optional

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class Notifier:
    """
    System powiadomień - integracja z natywnym OS.

    Wspiera:
    - Windows 10/11 Toast Notifications
    - Linux notify-send (libnotify)
    - Akcje/przyciski w powiadomieniach (ograniczone wsparcie)
    """

    def __init__(self, webhook_handler: Optional[Callable] = None):
        """
        Inicjalizacja Notifier.

        Args:
            webhook_handler: Async callback do obsługi akcji z powiadomień
        """
        self.webhook_handler = webhook_handler
        self.system = platform.system()
        self._is_wsl = self._detect_wsl()

        logger.info(f"Notifier zainicjalizowany na {self.system} (WSL: {self._is_wsl})")

        # Sprawdź dostępność narzędzi
        self._check_dependencies()

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

    def _check_dependencies(self) -> None:
        """Sprawdza czy wymagane narzędzia są dostępne."""
        if self.system == "Windows":
            # Windows ma wbudowane powiadomienia
            logger.info("Windows Toast Notifications dostępne")
        elif self.system == "Linux" and not self._is_wsl:
            # Sprawdź notify-send
            try:
                result = subprocess.run(
                    ["which", "notify-send"],
                    capture_output=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    logger.info("notify-send dostępne")
                else:
                    logger.warning("notify-send niedostępne - zainstaluj libnotify-bin")
            except Exception as e:
                logger.warning(f"Nie można sprawdzić notify-send: {e}")
        elif self._is_wsl:
            logger.warning(
                "WSL2 wykryty - powiadomienia mogą wymagać satelity na Windows"
            )

    async def send_toast(
        self,
        title: str,
        message: str,
        action_payload: Optional[Dict] = None,
        urgency: str = "normal",
        timeout: int = 5000,
    ) -> bool:
        """
        Wysyła powiadomienie toast.

        Args:
            title: Tytuł powiadomienia
            message: Treść powiadomienia
            action_payload: Dane akcji do wykonania po kliknięciu
            urgency: Pilność ("low", "normal", "critical")
            timeout: Timeout w ms (tylko Linux)

        Returns:
            True jeśli wysłano pomyślnie
        """
        try:
            if self.system == "Windows":
                return await self._send_toast_windows(title, message, action_payload)
            elif self.system == "Linux" and not self._is_wsl:
                return await self._send_toast_linux(title, message, urgency, timeout)
            elif self._is_wsl:
                logger.warning(
                    "Powiadomienia w WSL2 wymagają satelity - próba wysłania przez PowerShell"
                )
                return await self._send_toast_wsl(title, message)
            else:
                logger.warning(f"System {self.system} nie jest wspierany")
                return False

        except Exception as e:
            logger.error(f"Błąd przy wysyłaniu powiadomienia: {e}")
            return False

    async def _send_toast_windows(
        self, title: str, message: str, action_payload: Optional[Dict]
    ) -> bool:
        """
        Wysyła powiadomienie Windows Toast.

        Args:
            title: Tytuł
            message: Treść
            action_payload: Akcja

        Returns:
            True jeśli sukces
        """
        try:
            # Użyj win10toast jeśli dostępne
            try:
                from win10toast import ToastNotifier

                toaster = ToastNotifier()

                # Asynchroniczne uruchomienie
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: toaster.show_toast(
                        title,
                        message,
                        duration=5,
                        threaded=True,
                    ),
                )

                logger.info(f"Wysłano Windows Toast: {title}")
                return True

            except ImportError:
                logger.warning(
                    "win10toast nie jest zainstalowane - fallback do PowerShell"
                )
                return await self._send_toast_windows_powershell(title, message)

        except Exception as e:
            logger.error(f"Błąd przy wysyłaniu Windows Toast: {e}")
            return False

    async def _send_toast_windows_powershell(self, title: str, message: str) -> bool:
        """
        Wysyła powiadomienie przez PowerShell (fallback).

        Args:
            title: Tytuł
            message: Treść

        Returns:
            True jeśli sukces
        """
        try:
            # PowerShell script dla Toast notification
            # Używamy argument list zamiast string interpolation dla bezpieczeństwa
            # XML escaping odbywa się przez PowerShell's SecurityElement
            ps_script = """
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

            $title = [System.Security.SecurityElement]::Escape($args[0])
            $message = [System.Security.SecurityElement]::Escape($args[1])

            $template = @"
            <toast>
                <visual>
                    <binding template="ToastText02">
                        <text id="1">$title</text>
                        <text id="2">$message</text>
                    </binding>
                </visual>
            </toast>
"@

            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml($template)
            $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Venom").Show($toast)
            """

            # Uruchom PowerShell z argumentami (bezpieczniejsze niż string interpolation)
            process = await asyncio.create_subprocess_exec(
                "powershell",
                "-Command",
                ps_script,
                title,
                message,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await process.communicate()

            if process.returncode == 0:
                logger.info(f"Wysłano PowerShell Toast: {title}")
                return True
            else:
                logger.error("PowerShell Toast zakończył się błędem")
                return False

        except Exception as e:
            logger.error(f"Błąd przy wysyłaniu PowerShell Toast: {e}")
            return False

    async def _send_toast_linux(
        self, title: str, message: str, urgency: str, timeout: int
    ) -> bool:
        """
        Wysyła powiadomienie Linux notify-send.

        Args:
            title: Tytuł
            message: Treść
            urgency: Pilność
            timeout: Timeout w ms

        Returns:
            True jeśli sukces
        """
        try:
            cmd = [
                "notify-send",
                "-u",
                urgency,
                "-t",
                str(timeout),
                "-a",
                "Venom",
                title,
                message,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await process.communicate()

            if process.returncode == 0:
                logger.info(f"Wysłano Linux notification: {title}")
                return True
            else:
                logger.error("notify-send zakończył się błędem")
                return False

        except FileNotFoundError:
            logger.error("notify-send nie jest zainstalowane")
            return False
        except Exception as e:
            logger.error(f"Błąd przy wysyłaniu Linux notification: {e}")
            return False

    async def _send_toast_wsl(self, title: str, message: str) -> bool:
        """
        Wysyła powiadomienie z WSL2 do Windows.

        Args:
            title: Tytuł
            message: Treść

        Returns:
            True jeśli sukces
        """
        try:
            # Escapowanie dla PowerShell: podwójne cudzysłowy, wewnątrz podwójnych cudzysłowów " należy zamienić na `"
            def ps_escape(s: str) -> str:
                return s.replace('"', '`"')

            title_escaped = ps_escape(title)
            message_escaped = ps_escape(message)

            # Komenda PowerShell jako jeden argument
            ps_command = f'New-BurntToastNotification -Text "{title_escaped}", "{message_escaped}"'

            process = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-Command",
                ps_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await process.communicate()

            if process.returncode == 0:
                logger.info(f"Wysłano WSL Toast: {title}")
                return True
            else:
                # Fallback do prostszego msg
                logger.warning("BurntToast niedostępne, próba fallback...")
                return False

        except Exception as e:
            logger.error(f"Błąd przy wysyłaniu WSL Toast: {e}")
            return False

    async def handle_action(self, action_payload: Dict) -> None:
        """
        Obsługuje akcję z powiadomienia.

        Args:
            action_payload: Dane akcji
        """
        if not self.webhook_handler:
            logger.warning("Brak webhook handler - akcja ignorowana")
            return

        try:
            await self.webhook_handler(action_payload)
            logger.info(f"Wykonano akcję z powiadomienia: {action_payload}")
        except Exception as e:
            logger.error(f"Błąd przy obsłudze akcji: {e}")

    def get_status(self) -> dict[str, any]:
        """
        Zwraca status Notifier.

        Returns:
            Słownik ze statusem
        """
        return {
            "system": self.system,
            "is_wsl": self._is_wsl,
            "webhook_handler_set": self.webhook_handler is not None,
        }
