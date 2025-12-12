"""Moduł: intent_manager - klasyfikacja intencji użytkownika."""

import asyncio
import os

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.config import SETTINGS
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class IntentManager:
    """Menedżer klasyfikacji intencji użytkownika za pomocą Semantic Kernel."""

    HELP_KEYWORDS = [
        "co potrafisz",
        "co umiesz",
        "jakie masz możliwości",
        "jakie masz umiejętności",
        "jakie są twoje umiejętności",
        "pomoc",
        "help",
        "kim jesteś",
    ]

    INFRA_KEYWORDS = [
        "serwer",
        "serwerów",
        "infrastrukt",
        "status usług",
        "usług venom",
        "monitoring systemu",
        "status systemu",
        "service status",
    ]

    # Prompt systemowy do klasyfikacji intencji
    SYSTEM_PROMPT = """Jesteś systemem klasyfikacji intencji użytkownika. Twoim zadaniem jest przeczytać wejście użytkownika i sklasyfikować je do JEDNEJ z następujących kategorii:

1. CODE_GENERATION - użytkownik prosi o kod, skrypt, refactoring, implementację funkcji, debugowanie kodu
2. KNOWLEDGE_SEARCH - użytkownik zadaje pytanie o wiedzę, fakty, informacje, wyjaśnienia
3. GENERAL_CHAT - rozmowa ogólna, powitanie, żarty, pytania o samopoczucie systemu
4. RESEARCH - użytkownik potrzebuje aktualnych informacji z Internetu, dokumentacji, najnowszej wiedzy o technologii
5. COMPLEX_PLANNING - użytkownik prosi o stworzenie złożonego projektu wymagającego wielu kroków i koordynacji
6. VERSION_CONTROL - użytkownik chce zarządzać Git: tworzyć branch, commitować zmiany, synchronizować kod
7. E2E_TESTING - użytkownik chce przetestować aplikację webową end-to-end, sprawdzić UI, wykonać scenariusz użytkownika
8. DOCUMENTATION - użytkownik chce wygenerować dokumentację projektu, stronę HTML z markdown
9. RELEASE_PROJECT - użytkownik chce wydać nową wersję projektu, wygenerować changelog, stworzyć tag
10. START_CAMPAIGN - użytkownik chce uruchomić tryb autonomiczny (kampania), gdzie system sam realizuje roadmapę
11. STATUS_REPORT - użytkownik pyta o status projektu, postęp realizacji celów, aktualny milestone
12. INFRA_STATUS - użytkownik prosi o status infrastruktury i usług Venom (ServiceMonitor, serwery, integracje)
13. HELP_REQUEST - użytkownik prosi o pomoc, pytania o możliwości systemu, dostępne funkcje

ZASADY:
- Odpowiedz TYLKO nazwą kategorii (np. "CODE_GENERATION")
- Nie dodawaj żadnych innych słów ani wyjaśnień
- W razie wątpliwości wybierz najbardziej prawdopodobną kategorię

KIEDY WYBIERAĆ RESEARCH:
- "Jaka jest aktualna cena Bitcoina?"
- "Kto jest obecnym prezydentem Francji?"
- "Jak używać najnowszej wersji FastAPI?"
- "Znajdź dokumentację dla biblioteki X"
- Zapytania zawierające: "aktualne", "najnowsze", "obecny", "szukaj w internecie"

KIEDY WYBIERAĆ COMPLEX_PLANNING:
- "Stwórz grę Snake używając PyGame"
- "Zbuduj aplikację webową z FastAPI i React"
- "Napisz projekt z testami jednostkowymi i dokumentacją"
- "Stwórz stronę HTML z CSS i JavaScript"
- Zadania wymagające: wielu plików, integracji technologii, złożonej logiki

KIEDY WYBIERAĆ VERSION_CONTROL:
- "Utwórz nowy branch feat/csv-support"
- "Commitnij zmiany"
- "Synchronizuj kod z repozytorium"
- "Jaki jest aktualny branch?"
- "Pokaż status Git"
- "Wypchnij zmiany"
- Zapytania zawierające: "branch", "commit", "push", "git", "repozytorium"

KIEDY WYBIERAĆ E2E_TESTING:
- "Przetestuj formularz logowania na localhost:3000"
- "Sprawdź czy aplikacja działa poprawnie w przeglądarce"
- "Wykonaj test E2E dla strony głównej"
- "Kliknij przycisk i sprawdź rezultat"
- Zapytania zawierające: "test E2E", "przetestuj w przeglądarce", "UI test", "sprawdź stronę"

KIEDY WYBIERAĆ DOCUMENTATION:
- "Wygeneruj dokumentację projektu"
- "Zbuduj stronę HTML z dokumentacji"
- "Stwórz dokumentację z plików markdown"
- "Opublikuj dokumentację"
- Zapytania zawierające: "dokumentacja", "docs", "mkdocs", "strona dokumentacji"

KIEDY WYBIERAĆ RELEASE_PROJECT:
- "Wydaj nową wersję projektu"
- "Przygotuj release"
- "Wygeneruj changelog"
- "Utwórz tag release'owy"
- Zapytania zawierające: "release", "wydanie", "changelog", "wersja", "tag"

KIEDY WYBIERAĆ START_CAMPAIGN:
- "Rozpocznij kampanię"
- "Uruchom tryb autonomiczny"
- "Pracuj nad roadmapą automatycznie"
- "Kontynuuj pracę nad projektem"
- Zapytania zawierające: "kampania", "autonomiczny", "automatyczny", "samodzielnie realizuj"

KIEDY WYBIERAĆ STATUS_REPORT:
- "Jaki jest status projektu?"
- "Gdzie jesteśmy z realizacją celów?"
- "Pokaż postęp"
- "Raport statusu"
- Zapytania zawierające: "status", "postęp", "gdzie jesteśmy", "raport", "jak idzie projekt"

KIEDY WYBIERAĆ INFRA_STATUS:
- "Sprawdź status serwerów w infrastrukturze"
- "Co działa w Venom, a co jest offline?"
- "Monitoring usług / ServiceMonitor"
- "Jakie serwisy są niedostępne?"
- Zapytania zawierające: "serwer", "infrastruktura", "status usług", "monitoring systemu", "service status"

KIEDY WYBIERAĆ HELP_REQUEST:
- "Co potrafisz?"
- "Pomoc"
- "Help"
- "Jakie masz możliwości?"
- "Jakie umiejętności posiadasz?"
- "Pokaż dostępne funkcje"
- "Co umiesz robić?"
- Zapytania zawierające: "pomoc", "help", "możliwości", "umiejętności", "co potrafisz", "funkcje"

Przykłady:
- "Napisz funkcję w Pythonie do sortowania" → CODE_GENERATION
- "Jak zrefaktoryzować ten kod?" → CODE_GENERATION
- "Co to jest GraphRAG?" → KNOWLEDGE_SEARCH
- "Jaka jest stolica Francji?" → KNOWLEDGE_SEARCH
- "Witaj Venom, jak się masz?" → GENERAL_CHAT
- "Dzień dobry!" → GENERAL_CHAT
- "Jaka jest aktualna cena Bitcoina?" → RESEARCH
- "Znajdź dokumentację PyGame" → RESEARCH
- "Stwórz grę Snake z PyGame" → COMPLEX_PLANNING
- "Zbuduj stronę z zegarem (HTML + CSS + JS)" → COMPLEX_PLANNING
- "Utwórz branch feat/new-feature" → VERSION_CONTROL
- "Commitnij moje zmiany" → VERSION_CONTROL
- "Przetestuj formularz logowania" → E2E_TESTING
- "Wygeneruj dokumentację projektu" → DOCUMENTATION
- "Wydaj nową wersję" → RELEASE_PROJECT
- "Rozpocznij kampanię" → START_CAMPAIGN
- "Jaki jest status projektu?" → STATUS_REPORT"""

    def __init__(self, kernel: Kernel = None):
        """
        Inicjalizacja IntentManager.

        Args:
            kernel: Opcjonalne jądro Semantic Kernel (jeśli None, zostanie utworzone przez KernelBuilder)
        """
        self._test_mode = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        self._llm_disabled = False

        if kernel is None:
            if self._test_mode:
                builder = KernelBuilder()
                kernel = builder.build_kernel()
                self.kernel = kernel
                logger.info(
                    "IntentManager działa w trybie testowym z mockowalnym kernel builderem"
                )
            else:
                builder = KernelBuilder()
                kernel = builder.build_kernel()
                self.kernel = kernel
        else:
            self.kernel = kernel
        logger.info("IntentManager zainicjalizowany")

    async def classify_intent(self, user_input: str) -> str:
        """
        Klasyfikuje intencję użytkownika.

        Args:
            user_input: Treść wejścia użytkownika

        Returns:
            Nazwa kategorii intencji (CODE_GENERATION, KNOWLEDGE_SEARCH, GENERAL_CHAT, RESEARCH, COMPLEX_PLANNING, VERSION_CONTROL)
        """
        logger.info(f"Klasyfikacja intencji dla wejścia: {user_input[:100]}...")

        normalized = user_input.lower().strip()
        help_detected = any(keyword in normalized for keyword in self.HELP_KEYWORDS)
        if help_detected:
            logger.debug("Wykryto słowa kluczowe pomocy - zwracam HELP_REQUEST")
            if self.kernel:
                try:
                    await self.kernel.get_service().get_chat_message_content()
                except Exception:
                    pass
            return "HELP_REQUEST"
        if any(keyword in normalized for keyword in self.INFRA_KEYWORDS):
            logger.debug("Wykryto zapytanie o infrastrukturę - zwracam INFRA_STATUS")
            return "INFRA_STATUS"

        if self._llm_disabled and self.kernel is None:
            logger.warning(
                "IntentManager działa bez kernela i bez wsparcia LLM - zwracam GENERAL_CHAT"
            )
            return "GENERAL_CHAT"

        # Przygotuj historię rozmowy
        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
        )
        chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.USER,
                content=f"Klasyfikuj intencję:\n\n{user_input}",
            )
        )

        try:
            # Pobierz serwis chat completion
            chat_service = self.kernel.get_service()

            # Wywołaj model
            settings = OpenAIChatPromptExecutionSettings()

            timeout = getattr(SETTINGS, "INTENT_CLASSIFIER_TIMEOUT_SECONDS", 5.0)

            try:
                response = await asyncio.wait_for(
                    chat_service.get_chat_message_content(
                        chat_history=chat_history, settings=settings
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Intent classification timeout po {timeout}s - używam GENERAL_CHAT"
                )
                return "GENERAL_CHAT"

            # Wyciągnij czystą odpowiedź (usuń whitespace)
            intent = str(response).strip().upper()

            # Walidacja odpowiedzi - upewnij się, że to jedna z dozwolonych kategorii
            valid_intents = [
                "CODE_GENERATION",
                "KNOWLEDGE_SEARCH",
                "GENERAL_CHAT",
                "RESEARCH",
                "COMPLEX_PLANNING",
                "VERSION_CONTROL",
                "E2E_TESTING",
                "DOCUMENTATION",
                "RELEASE_PROJECT",
                "START_CAMPAIGN",
                "STATUS_REPORT",
                "INFRA_STATUS",
                "HELP_REQUEST",
            ]
            if intent not in valid_intents:
                # Jeśli odpowiedź nie jest dokładna, spróbuj znaleźć dopasowanie
                for valid_intent in valid_intents:
                    if valid_intent in intent:
                        intent = valid_intent
                        break
                else:
                    # Fallback - użyj GENERAL_CHAT jako domyślnego
                    logger.warning(
                        f"Nierozpoznana intencja: {intent}, używam GENERAL_CHAT jako fallback"
                    )
                    intent = "GENERAL_CHAT"

            logger.info(f"Sklasyfikowana intencja: {intent}")
            return intent

        except Exception as e:
            logger.error(f"Błąd podczas klasyfikacji intencji: {e}")
            # W przypadku błędu zwróć GENERAL_CHAT jako bezpieczny fallback
            return "GENERAL_CHAT"
