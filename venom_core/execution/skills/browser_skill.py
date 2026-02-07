"""Moduł: browser_skill - umiejętność przeglądarkowa dla testów E2E."""

import ipaddress
import os
import re
import time
from importlib import import_module
from pathlib import Path
from typing import Annotated, Any, Literal, Optional
from urllib.parse import urlparse

from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

Browser = Any
Page = Any

logger = get_logger(__name__)

# Stała dla opóźnienia stabilizacji DOM
DOM_STABILIZATION_DELAY_MS = 500
MAX_SCREENSHOT_FILENAME_LEN = 128
ALLOWED_SCREENSHOT_CHARS = re.compile(r"^[A-Za-z0-9._-]+$")
ALLOWED_BROWSER_SCHEMES = {"http", "https"}


class BrowserSkill:
    """
    Skill do interakcji z przeglądarką.

    Umożliwia agentom wykonywanie testów E2E poprzez kontrolowanie przeglądarki
    (headless Chromium) za pomocą Playwright.

    UWAGA: Zasoby przeglądarki (browser, page, Playwright) muszą być zamykane jawnie przez użytkownika
    poprzez wywołanie metody `close_browser()`. Destruktor nie zamyka zasobów automatycznie ze względu
    na ograniczenia asynchronicznego czyszczenia w Pythonie. Brak jawnego zamknięcia może prowadzić do
    wycieków pamięci lub pozostawienia procesów przeglądarki.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Inicjalizacja BrowserSkill.

        Args:
            workspace_root: Katalog roboczy (domyślnie z SETTINGS)
        """
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.screenshots_dir = self.workspace_root / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        # Playwright context - będzie zainicjalizowany przy pierwszym użyciu
        self._playwright = None
        self._browser: Optional["Browser"] = None
        self._page: Optional["Page"] = None

        logger.info("BrowserSkill zainicjalizowany")

    @staticmethod
    def _is_local_or_private_host(hostname: str) -> bool:
        """Sprawdza czy host jest lokalny/prywatny."""
        lowered = hostname.lower().strip()
        if lowered in {"localhost", "0.0.0.0", "::1"}:
            return True
        try:
            ip = ipaddress.ip_address(lowered)
        except ValueError:
            return False
        return ip.is_loopback or ip.is_private or ip.is_link_local

    def _get_allowed_hosts(self) -> set[str]:
        """Pobiera opcjonalną allowlistę hostów z ENV."""
        raw = os.getenv("VENOM_BROWSER_ALLOWED_HOSTS", "")
        hosts = {
            host.strip().lower()
            for host in raw.split(",")
            if host and host.strip()
        }
        return hosts

    def _validate_url_policy(self, normalized_url: str) -> list[str]:
        """
        Zwraca listę ostrzeżeń polityki URL (warn-only / block zależnie od konfiguracji).
        """
        warnings: list[str] = []
        parsed = urlparse(normalized_url)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()

        if scheme not in ALLOWED_BROWSER_SCHEMES:
            warnings.append(
                f"Niedozwolony schemat URL: '{scheme}'. Dozwolone: http/https."
            )
            return warnings

        if not host:
            warnings.append("Brak hosta w URL.")
            return warnings

        if self._is_local_or_private_host(host):
            return warnings

        allowed_hosts = self._get_allowed_hosts()
        if host not in allowed_hosts:
            warnings.append(
                "Host nie jest lokalny i nie znajduje się na allowliście "
                "(VENOM_BROWSER_ALLOWED_HOSTS)."
            )

        return warnings

    @staticmethod
    def _sanitize_screenshot_filename(filename: str) -> str:
        """Sanityzuje nazwę pliku screenshotu (bez katalogów)."""
        if not filename or not filename.strip():
            raise ValueError("Nazwa pliku nie może być pusta")

        candidate = filename.strip()
        if Path(candidate).name != candidate:
            raise ValueError("Nazwa pliku nie może zawierać separatorów katalogów")
        if candidate in {".", ".."}:
            raise ValueError("Niedozwolona nazwa pliku")

        if not candidate.endswith(".png"):
            candidate = f"{candidate}.png"

        if len(candidate) > MAX_SCREENSHOT_FILENAME_LEN:
            raise ValueError("Nazwa pliku screenshotu jest zbyt długa")
        if not ALLOWED_SCREENSHOT_CHARS.fullmatch(candidate):
            raise ValueError(
                "Nazwa pliku może zawierać tylko: litery, cyfry, '.', '_' i '-'"
            )

        return candidate

    async def _ensure_browser(self):
        """Upewnia się, że przeglądarka jest uruchomiona."""
        if self._browser is None:
            try:
                async_playwright = getattr(
                    import_module("playwright.async_api"), "async_playwright"
                )
            except ImportError as e:
                logger.error(
                    "Playwright nie jest zainstalowany. Zainstaluj 'playwright'."
                )
                raise RuntimeError("Playwright is not installed") from e

            self._playwright = await async_playwright().start()
            # Uruchom headless Chromium
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            logger.info("Przeglądarka Chromium uruchomiona (headless)")

        if self._page is None:
            # Utwórz nowy context i page
            context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Venom E2E Test)",
            )
            self._page = await context.new_page()
            logger.info("Nowa karta przeglądarki utworzona")

    async def _close_browser(self):
        """Zamyka przeglądarkę i czyści zasoby."""
        if self._page:
            await self._page.close()
            self._page = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        logger.info("Przeglądarka zamknięta")

    def _require_page(self) -> "Page":
        """Zwraca aktywną stronę lub podnosi błąd, gdy przeglądarka nie jest gotowa."""
        if not self._page:
            raise RuntimeError("Przeglądarka nie jest zainicjalizowana")
        return self._page

    async def _capture_verification_screenshot(self, action_type: str) -> Path:
        """
        Wykonuje zrzut ekranu weryfikacyjny po akcji.

        Args:
            action_type: Typ akcji (np. 'click', 'fill')

        Returns:
            Ścieżka do zapisanego screenshota
        """
        timestamp = int(time.time())
        screenshot_name = f"{action_type}_verification_{timestamp}.png"
        screenshot_path = self.screenshots_dir / screenshot_name

        # Poczekaj chwilę na zmianę DOM (React, Vue, itp.)
        page = self._require_page()
        await page.wait_for_timeout(DOM_STABILIZATION_DELAY_MS)
        await page.screenshot(path=str(screenshot_path))

        return screenshot_path

    @kernel_function(
        name="visit_page",
        description="Otwiera podany URL w przeglądarce. "
        "Użyj do nawigacji na strony webowe (np. localhost:3000).",
    )
    async def visit_page(
        self,
        url: Annotated[str, "URL strony do odwiedzenia (np. 'http://localhost:3000')"],
        wait_until: Annotated[
            Literal["commit", "domcontentloaded", "load", "networkidle"],
            "Stan oczekiwania: 'load', 'domcontentloaded', 'networkidle' (domyślnie 'load')",
        ] = "load",
    ) -> str:
        """
        Otwiera stronę w przeglądarce.

        Args:
            url: URL do odwiedzenia
            wait_until: Stan oczekiwania na załadowanie strony

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            await self._ensure_browser()

            normalized_url = self._ensure_url_scheme(url)
            policy_warnings = self._validate_url_policy(normalized_url)
            policy_mode = os.getenv("VENOM_BROWSER_URL_POLICY_MODE", "warn").lower()
            if policy_warnings:
                warning_text = " | ".join(policy_warnings)
                if policy_mode == "block":
                    logger.warning("Browser URL policy BLOCK: %s", warning_text)
                    return f"❌ URL zablokowany przez politykę bezpieczeństwa: {warning_text}"
                logger.warning("Browser URL policy WARN: %s", warning_text)
            logger.info(f"Odwiedzanie strony: {normalized_url}")
            page = self._require_page()
            await page.goto(normalized_url, wait_until=wait_until, timeout=30000)

            # Pobierz tytuł strony
            title = await page.title()
            logger.info(f"Strona załadowana: {title}")

            return (
                f"✅ Strona załadowana pomyślnie\nURL: {normalized_url}\nTytuł: {title}"
            )

        except Exception as e:
            error_msg = f"❌ Błąd podczas ładowania strony: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @staticmethod
    def _ensure_url_scheme(url: str) -> str:
        """Dodaje schemat do URL, jeśli go brakuje."""
        if not url:
            return url
        parsed = urlparse(url)
        if parsed.scheme:
            return url
        lowered = url.lower()
        # Sprawdź localhost i lokalne adresy IP
        if lowered.startswith("localhost") or lowered.startswith("0.0.0.0"):
            return f"http://{url}"

        # Wydziel host bez portu, np. z "192.168.1.1:8080" → "192.168.1.1"
        host = lowered.split(":", 1)[0]

        # Sprawdź czy wygląda jak adres IP (wszystkie części są numeryczne)
        parts = host.split(".")
        if len(parts) == 4 and all(part.isdigit() for part in parts):
            try:
                # Waliduj czy oktety są w prawidłowym zakresie
                octets = [int(part) for part in parts]
                if all(0 <= octet <= 255 for octet in octets):
                    # Sprawdź czy to prywatny/lokalny adres IP
                    if octets[0] == 127:  # Loopback
                        return f"http://{url}"
                    if octets[0] == 192 and octets[1] == 168:  # Private class C
                        return f"http://{url}"
                    if octets[0] == 10:  # Private class A
                        return f"http://{url}"
                    if octets[0] == 172 and 16 <= octets[1] <= 31:  # Private class B
                        return f"http://{url}"
            except (ValueError, IndexError):
                # Jeśli parsowanie IP się nie powiedzie, traktujemy URL jako zwykłą nazwę hosta
                pass
        return f"https://{url}"

    @kernel_function(
        name="take_screenshot",
        description="Wykonuje zrzut ekranu aktualnej strony. "
        "Użyj do weryfikacji wizualnej lub debugowania.",
    )
    async def take_screenshot(
        self,
        filename: Annotated[
            str, "Nazwa pliku (np. 'homepage.png'). Zostanie zapisany w screenshots/"
        ],
        full_page: Annotated[
            bool, "Czy zrobić zrzut całej strony (True) czy tylko viewport (False)"
        ] = False,
    ) -> str:
        """
        Wykonuje zrzut ekranu strony.

        Args:
            filename: Nazwa pliku do zapisu
            full_page: Czy zrobić zrzut całej strony

        Returns:
            Ścieżka do zapisanego pliku lub komunikat błędu
        """
        try:
            await self._ensure_browser()

            filename = self._sanitize_screenshot_filename(filename)

            screenshot_path = self.screenshots_dir / filename
            logger.info(f"Wykonywanie zrzutu ekranu: {screenshot_path}")

            page = self._require_page()
            await page.screenshot(path=str(screenshot_path), full_page=full_page)

            logger.info(f"Zrzut ekranu zapisany: {screenshot_path}")
            return f"✅ Zrzut ekranu zapisany: {screenshot_path}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas wykonywania zrzutu ekranu: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="get_html_content",
        description="Pobiera zawartość HTML aktualnej strony (DOM). "
        "Użyj do weryfikacji elementów strony.",
    )
    async def get_html_content(self) -> str:
        """
        Pobiera zawartość HTML strony.

        Returns:
            HTML strony lub komunikat błędu
        """
        try:
            await self._ensure_browser()

            logger.info("Pobieranie zawartości HTML")
            page = self._require_page()
            html = await page.content()

            logger.debug(f"Pobrano HTML ({len(html)} znaków)")
            return html

        except Exception as e:
            error_msg = f"❌ Błąd podczas pobierania HTML: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="click_element",
        description="Klika w element na stronie za pomocą selektora CSS. "
        "Użyj do interakcji z przyciskami, linkami itp. Automatycznie wykonuje zrzut ekranu weryfikacyjny.",
    )
    async def click_element(
        self,
        selector: Annotated[
            str, "Selektor CSS elementu (np. '#login-button', '.submit-btn')"
        ],
        timeout: Annotated[int, "Timeout w milisekundach (domyślnie 30000)"] = 30000,
    ) -> str:
        """
        Klika w element na stronie i wykonuje zrzut ekranu weryfikacyjny.

        Args:
            selector: Selektor CSS elementu
            timeout: Timeout w ms

        Returns:
            Komunikat o wyniku operacji wraz ze ścieżką do zrzutu ekranu
        """
        try:
            await self._ensure_browser()

            logger.info(f"Klikanie w element: {selector}")
            page = self._require_page()
            await page.click(selector, timeout=timeout)

            # Wykonaj automatyczny zrzut ekranu weryfikacyjny
            screenshot_path = await self._capture_verification_screenshot("click")

            logger.info(
                f"Kliknięto w element: {selector}, zrzut ekranu: {screenshot_path}"
            )
            return f"✅ Kliknięto w element: {selector}\nZrzut ekranu weryfikacyjny: {screenshot_path}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas klikania w element '{selector}': {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="fill_form",
        description="Wypełnia pole formularza podaną wartością. "
        "Użyj do testowania formularzy (login, rejestracja, itp.). Automatycznie wykonuje zrzut ekranu weryfikacyjny.",
    )
    async def fill_form(
        self,
        selector: Annotated[
            str, "Selektor CSS pola formularza (np. '#username', 'input[name=email]')"
        ],
        value: Annotated[str, "Wartość do wpisania w pole"],
        timeout: Annotated[int, "Timeout w milisekundach (domyślnie 30000)"] = 30000,
    ) -> str:
        """
        Wypełnia pole formularza i wykonuje zrzut ekranu weryfikacyjny.

        Args:
            selector: Selektor CSS pola
            value: Wartość do wpisania
            timeout: Timeout w ms

        Returns:
            Komunikat o wyniku operacji wraz ze ścieżką do zrzutu ekranu
        """
        try:
            await self._ensure_browser()

            logger.info(f"Wypełnianie pola: {selector}")
            page = self._require_page()
            await page.fill(selector, value, timeout=timeout)

            # Wykonaj automatyczny zrzut ekranu weryfikacyjny
            screenshot_path = await self._capture_verification_screenshot("fill")

            logger.info(f"Wypełniono pole: {selector}, zrzut ekranu: {screenshot_path}")
            return f"✅ Wypełniono pole: {selector}\nZrzut ekranu weryfikacyjny: {screenshot_path}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas wypełniania pola '{selector}': {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="get_text_content",
        description="Pobiera tekstową zawartość elementu za pomocą selektora CSS. "
        "Użyj do weryfikacji treści na stronie.",
    )
    async def get_text_content(
        self,
        selector: Annotated[str, "Selektor CSS elementu (np. 'h1', '.message')"],
        timeout: Annotated[int, "Timeout w milisekundach (domyślnie 30000)"] = 30000,
    ) -> str:
        """
        Pobiera tekst z elementu.

        Args:
            selector: Selektor CSS elementu
            timeout: Timeout w ms

        Returns:
            Tekst elementu lub komunikat błędu
        """
        try:
            await self._ensure_browser()

            logger.info(f"Pobieranie tekstu z elementu: {selector}")
            page = self._require_page()
            text = await page.text_content(selector, timeout=timeout)

            logger.info(f"Pobrano tekst z elementu: {selector}")
            return text or ""

        except Exception as e:
            error_msg = f"❌ Błąd podczas pobierania tekstu z '{selector}': {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="wait_for_element",
        description="Czeka aż element pojawi się na stronie. "
        "Użyj do synchronizacji testów z dynamiczną zawartością.",
    )
    async def wait_for_element(
        self,
        selector: Annotated[str, "Selektor CSS elementu do oczekiwania"],
        state: Annotated[
            Literal["attached", "detached", "visible", "hidden"],
            "Stan elementu: 'attached', 'detached', 'visible', 'hidden' (domyślnie 'visible')",
        ] = "visible",
        timeout: Annotated[int, "Timeout w milisekundach (domyślnie 30000)"] = 30000,
    ) -> str:
        """
        Czeka na pojawienie się elementu.

        Args:
            selector: Selektor CSS elementu
            state: Oczekiwany stan elementu
            timeout: Timeout w ms

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            await self._ensure_browser()

            logger.info(f"Oczekiwanie na element: {selector} (stan: {state})")
            page = self._require_page()
            await page.wait_for_selector(selector, state=state, timeout=timeout)

            logger.info(f"Element znaleziony: {selector}")
            return f"✅ Element znaleziony: {selector}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas oczekiwania na element '{selector}': {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="close_browser",
        description="Zamyka przeglądarkę i czyści zasoby. "
        "Użyj po zakończeniu testów E2E.",
    )
    async def close_browser(self) -> str:
        """
        Zamyka przeglądarkę.

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            await self._close_browser()
            return "✅ Przeglądarka zamknięta"

        except Exception as e:
            error_msg = f"❌ Błąd podczas zamykania przeglądarki: {str(e)}"
            logger.error(error_msg)
            return error_msg

    def __del__(self):
        """Destruktor - upewnia się, że przeglądarka jest zamknięta."""
        # Note: __del__ może nie być wywoływany przed zniszczeniem obiektu.
        # Zalecane jest jawne wywołanie close_browser() po użyciu.
        if self._browser is not None:
            logger.warning(
                "BrowserSkill: Przeglądarka nie została zamknięta jawnie. "
                "Zalecane jest wywołanie close_browser() po użyciu."
            )
