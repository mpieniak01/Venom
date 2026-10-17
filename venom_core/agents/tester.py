"""Moduł: tester - agent QA do testów E2E."""

from pathlib import Path
from typing import Any, Optional

from venom_core.agents.base import BaseAgent
from venom_core.execution.agent_contracts import (
    CompletionOptions as OpenAIChatPromptExecutionSettings,
)
from venom_core.execution.agent_contracts import ConversationHistory as ChatHistory
from venom_core.execution.agent_contracts import (
    ConversationMessage as ChatMessageContent,
)
from venom_core.execution.agent_contracts import MessageRole as AuthorRole
from venom_core.execution.maf_runtime import AgentRuntime as Kernel
from venom_core.execution.skills.browser_skill import BrowserSkill
from venom_core.perception.eyes import Eyes
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class TesterAgent(BaseAgent):
    """
    Agent Tester (QA Engineer dla testów E2E).

    Jego rolą jest weryfikacja działania aplikacji webowych poprzez:
    - Testowanie scenariuszy użytkownika (E2E)
    - Weryfikację wizualną interfejsu
    - Raportowanie błędów UI/UX
    """

    SYSTEM_PROMPT = """Jesteś ekspertem QA/Tester odpowiedzialnym za testy End-to-End aplikacji webowych.

TWOJA ROLA:
- Testujesz aplikacje webowe poprzez interakcję z przeglądarką
- Weryfikujesz czy interfejs użytkownika działa poprawnie
- Sprawdzasz scenariusze biznesowe krok po kroku
- Raportujesz błędy wizualne i funkcjonalne

MASZ DOSTĘP DO NARZĘDZI:
- BrowserSkill: visit_page, click_element, fill_form, get_text_content, take_screenshot, wait_for_element
- Eyes (integracja): możesz prosić o analizę screenshotów aby zweryfikować wizualne aspekty

ZASADY TESTOWANIA:
1. Zawsze rozpoczynaj od załadowania strony (visit_page)
2. Czekaj na załadowanie kluczowych elementów (wait_for_element)
3. Wykonuj akcje użytkownika krok po kroku
4. Weryfikuj rezultaty (get_text_content, take_screenshot)
5. W razie błędu - rób screenshot i opisz dokładnie co jest nie tak

PRZYKŁADOWY SCENARIUSZ TESTOWY:
Zadanie: "Przetestuj formularz logowania"
Kroki:
1. visit_page("http://localhost:3000/login")
2. wait_for_element("#username")
3. fill_form("#username", "testuser")
4. fill_form("#password", "testpass123")
5. click_element("#login-button")
6. wait_for_element(".welcome-message")
7. get_text_content(".welcome-message") - sprawdź czy zawiera "Witaj"
8. take_screenshot("login-success.png")

RAPORTOWANIE BŁĘDÓW:
Jeśli coś nie działa:
- Opisz dokładnie co się stało
- Podaj selektor elementu który sprawia problem
- Zrób screenshot
- Zasugeruj możliwą przyczynę (np. "Przycisk nie reaguje - prawdopodobnie brak handlera onClick")

Bądź systematyczny i dokładny. Każdy test powinien być powtarzalny.
"""

    def __init__(
        self,
        kernel: Kernel,
        browser_skill: Optional[BrowserSkill] = None,
        eyes: Optional[Eyes] = None,
    ):
        """
        Inicjalizacja TesterAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            browser_skill: Instancja BrowserSkill (jeśli None, zostanie utworzona)
            eyes: Instancja Eyes do analizy wizualnej (opcjonalne)
        """
        super().__init__(kernel)

        # Zarejestruj skille
        self.browser_skill = browser_skill or BrowserSkill()
        self.eyes = eyes or Eyes()

        # Zarejestruj BrowserSkill w kernelu
        self.kernel.add_plugin(self.browser_skill, plugin_name="BrowserSkill")

        # Ustawienia LLM
        self.execution_settings = OpenAIChatPromptExecutionSettings(
            service_id="default",
            max_tokens=2000,
            temperature=0.3,  # Niższa temperatura dla precyzji testów
            top_p=0.9,
        )

        # Service do chat completion
        self.chat_service: Any = self.kernel.get_service(service_id="default")

        logger.info("TesterAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza zadanie testowe.

        Args:
            input_text: Opis zadania testowego (np. "Przetestuj formularz logowania na localhost:3000")

        Returns:
            Raport z testów
        """
        logger.info(f"TesterAgent rozpoczyna pracę: {input_text[:100]}...")

        # Utwórz historię czatu
        chat_history = ChatHistory()

        # Dodaj prompt systemowy
        chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=self.SYSTEM_PROMPT,
            )
        )

        # Dodaj zadanie użytkownika
        chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.USER,
                content=input_text,
            )
        )

        try:
            # Wykonaj interakcję z kernelem (auto-calling functions)
            result = await self._invoke_chat_with_fallbacks(
                chat_service=self.chat_service,
                chat_history=chat_history,
                settings=self.execution_settings,
                enable_functions=True,
            )

            response = str(result.content)

            # Sprawdź czy agent wspomina o screenshocie
            if "screenshot" in response.lower() or ".png" in response.lower():
                # Sprawdź czy screenshot został zapisany i czy można go przeanalizować
                screenshots_dir = Path(self.browser_skill.screenshots_dir)
                screenshots = sorted(screenshots_dir.glob("*.png"))
                if screenshots:
                    # Weź ostatni screenshot
                    latest_screenshot = screenshots[-1]
                    logger.info(
                        f"Znaleziono screenshot do analizy: {latest_screenshot}"
                    )

                    try:
                        # Przeanalizuj wizualnie jeśli Eyes jest dostępny
                        visual_analysis = await self.eyes.analyze_image(
                            str(latest_screenshot),
                            "Opisz co widzisz na tym screenshocie strony webowej. "
                            "Zwróć uwagę na: layout, widoczne elementy, błędy wizualne, komunikaty.",
                        )

                        response += (
                            f"\n\n📸 Analiza wizualna ({latest_screenshot.name}):\n"
                            f"{visual_analysis}"
                        )
                    except Exception as e:
                        logger.warning(f"Nie można przeanalizować screenshota: {e}")

            logger.info("TesterAgent zakończył pracę")
            return response

        except Exception as e:
            error_msg = f"❌ Błąd podczas testowania: {str(e)}"
            logger.error(error_msg)
            return error_msg

        finally:
            # Zawsze zamknij przeglądarkę po testach
            try:
                await self.browser_skill.close_browser()
            except Exception as e:
                logger.warning(f"Nie można zamknąć przeglądarki: {e}")

    @staticmethod
    def _scenario_text(
        step: dict[str, Any], name: str, *, allow_empty: bool = False
    ) -> str:
        value = step.get(name)
        if not isinstance(value, str) or (not allow_empty and not value.strip()):
            raise ValueError(f"invalid_scenario_field:{name}")
        return value

    async def run_e2e_scenario(self, url: str, scenario_steps: list[dict]) -> str:
        """
        Wykonuje zdefiniowany scenariusz E2E.

        Args:
            url: URL aplikacji do testowania
            scenario_steps: Lista kroków scenariusza, np.:
                [
                    {"action": "visit", "url": "..."},
                    {"action": "click", "selector": "..."},
                    {"action": "fill", "selector": "...", "value": "..."},
                    {"action": "verify_text", "selector": "...", "expected": "..."},
                ]

        Returns:
            Raport z wykonania scenariusza
        """
        logger.info(f"Wykonywanie scenariusza E2E dla: {url}")
        report_lines = [f"📋 Raport z testu E2E: {url}\n"]

        try:
            for i, step in enumerate(scenario_steps, 1):
                action = step.get("action") or ""
                report_lines.append(f"{i}. {action.upper()}")

                if action == "visit":
                    result = await self.browser_skill.visit_page(step.get("url", url))
                    report_lines.append(f"   {result}")

                elif action == "click":
                    selector = self._scenario_text(step, "selector")
                    result = await self.browser_skill.click_element(selector)
                    report_lines.append(f"   {result}")

                elif action == "fill":
                    selector = self._scenario_text(step, "selector")
                    value = self._scenario_text(step, "value", allow_empty=True)
                    result = await self.browser_skill.fill_form(selector, value)
                    report_lines.append(f"   {result}")

                elif action == "verify_text":
                    selector = self._scenario_text(step, "selector")
                    expected = self._scenario_text(step, "expected")
                    actual = await self.browser_skill.get_text_content(selector)

                    if expected in actual:
                        report_lines.append(f"   ✅ Tekst OK: '{expected}' znaleziony")
                    else:
                        report_lines.append(
                            f"   ❌ BŁĄD: Oczekiwano '{expected}', otrzymano '{actual}'"
                        )

                elif action == "screenshot":
                    filename = step.get("filename", f"step_{i}.png")
                    result = await self.browser_skill.take_screenshot(filename)
                    report_lines.append(f"   {result}")

                elif action == "wait":
                    selector = self._scenario_text(step, "selector")
                    result = await self.browser_skill.wait_for_element(selector)
                    report_lines.append(f"   {result}")

                else:
                    report_lines.append(f"   ⚠️ Nieznana akcja: {action}")

            report_lines.append("\n✅ Scenariusz zakończony pomyślnie")

        except Exception as e:
            report_lines.append(f"\n❌ Scenariusz przerwany: {str(e)}")
            logger.error(f"Błąd w scenariuszu E2E: {e}")

        finally:
            await self.browser_skill.close_browser()

        return "\n".join(report_lines)
