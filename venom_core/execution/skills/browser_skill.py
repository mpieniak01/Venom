"""Moduł: browser_skill - umiejętność przeglądarkowa dla testów E2E."""

import asyncio
from pathlib import Path
from typing import Annotated, Optional

from playwright.async_api import Browser, Page, async_playwright
from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class BrowserSkill:
    """
    Skill do interakcji z przeglądarką.

    Umożliwia agentom wykonywanie testów E2E poprzez kontrolowanie przeglądarki
    (headless Chromium) za pomocą Playwright.
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
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

        logger.info("BrowserSkill zainicjalizowany")

    async def _ensure_browser(self):
        """Upewnia się, że przeglądarka jest uruchomiona."""
        if self._browser is None:
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

    @kernel_function(
        name="visit_page",
        description="Otwiera podany URL w przeglądarce. "
        "Użyj do nawigacji na strony webowe (np. localhost:3000).",
    )
    async def visit_page(
        self,
        url: Annotated[str, "URL strony do odwiedzenia (np. 'http://localhost:3000')"],
        wait_until: Annotated[
            str,
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

            logger.info(f"Odwiedzanie strony: {url}")
            await self._page.goto(url, wait_until=wait_until, timeout=30000)

            # Pobierz tytuł strony
            title = await self._page.title()
            logger.info(f"Strona załadowana: {title}")

            return f"✅ Strona załadowana pomyślnie\nURL: {url}\nTytuł: {title}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas ładowania strony: {str(e)}"
            logger.error(error_msg)
            return error_msg

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

            # Upewnij się że filename ma rozszerzenie .png
            if not filename.endswith(".png"):
                filename = f"{filename}.png"

            screenshot_path = self.screenshots_dir / filename
            logger.info(f"Wykonywanie zrzutu ekranu: {screenshot_path}")

            await self._page.screenshot(path=str(screenshot_path), full_page=full_page)

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
            html = await self._page.content()

            logger.debug(f"Pobrano HTML ({len(html)} znaków)")
            return html

        except Exception as e:
            error_msg = f"❌ Błąd podczas pobierania HTML: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="click_element",
        description="Klika w element na stronie za pomocą selektora CSS. "
        "Użyj do interakcji z przyciskami, linkami itp.",
    )
    async def click_element(
        self,
        selector: Annotated[
            str, "Selektor CSS elementu (np. '#login-button', '.submit-btn')"
        ],
        timeout: Annotated[int, "Timeout w milisekundach (domyślnie 30000)"] = 30000,
    ) -> str:
        """
        Klika w element na stronie.

        Args:
            selector: Selektor CSS elementu
            timeout: Timeout w ms

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            await self._ensure_browser()

            logger.info(f"Klikanie w element: {selector}")
            await self._page.click(selector, timeout=timeout)

            logger.info(f"Kliknięto w element: {selector}")
            return f"✅ Kliknięto w element: {selector}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas klikania w element '{selector}': {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="fill_form",
        description="Wypełnia pole formularza podaną wartością. "
        "Użyj do testowania formularzy (login, rejestracja, itp.).",
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
        Wypełnia pole formularza.

        Args:
            selector: Selektor CSS pola
            value: Wartość do wpisania
            timeout: Timeout w ms

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            await self._ensure_browser()

            logger.info(f"Wypełnianie pola: {selector}")
            await self._page.fill(selector, value, timeout=timeout)

            logger.info(f"Wypełniono pole: {selector}")
            return f"✅ Wypełniono pole: {selector}"

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
            text = await self._page.text_content(selector, timeout=timeout)

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
            str,
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
            await self._page.wait_for_selector(selector, state=state, timeout=timeout)

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
        if self._browser is not None:
            # Musimy uruchomić close w event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Jeśli loop działa, zaplanuj zamknięcie
                    loop.create_task(self._close_browser())
                else:
                    # Jeśli loop nie działa, uruchom synchronicznie
                    loop.run_until_complete(self._close_browser())
            except Exception as e:
                logger.warning(f"Nie można automatycznie zamknąć przeglądarki: {e}")
