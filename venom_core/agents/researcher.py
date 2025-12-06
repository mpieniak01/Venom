"""Moduł: researcher - agent badawczy, synteza wiedzy z Internetu."""

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.web_skill import WebSearchSkill
from venom_core.memory.memory_skill import MemorySkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ResearcherAgent(BaseAgent):
    """Agent specjalizujący się w badaniu i syntezie wiedzy z Internetu."""

    SYSTEM_PROMPT = """Jesteś ekspertem badawczym (Researcher). Twoim zadaniem jest znajdowanie i synteza wiedzy z Internetu.

TWOJE NARZĘDZIA:
- search: Wyszukaj informacje w Internecie (DuckDuckGo)
- scrape_text: Pobierz i oczyść treść konkretnej strony WWW
- search_and_scrape: Wyszukaj i automatycznie pobierz treść z najlepszych wyników
- memorize: Zapisz ważne informacje do pamięci długoterminowej
- recall: Przywołaj informacje z pamięci

ZASADY:
1. NIE PISZESZ KODU - Twoja rola to dostarczanie FAKTÓW i WIEDZY
2. Gdy otrzymasz pytanie:
   - Najpierw sprawdź pamięć (recall) czy nie masz już tej informacji
   - Jeśli nie ma w pamięci, wyszukaj w Internecie (search lub search_and_scrape)
   - Przeanalizuj wyniki z 2-3 najlepszych źródeł
   - Stwórz ZWIĘZŁE PODSUMOWANIE TECHNICZNE z przykładami kodu jeśli to stosowne
3. Po zebraniu wiedzy:
   - Zapisz ważne informacje do pamięci (memorize) na przyszłość
   - Kategoryzuj wiedzę odpowiednio (documentation, code_example, best_practice, etc.)
4. Jeśli strona nie działa (404, timeout):
   - Spróbuj innego wyniku z wyszukiwania
   - NIE PRZERYWAJ całego procesu z powodu jednego błędu
5. Odpowiadaj zawsze w języku polskim
6. Format odpowiedzi:
   - Krótkie wprowadzenie (1-2 zdania)
   - Kluczowe punkty/fakty (bullet points)
   - Przykłady kodu jeśli to stosowne
   - Źródła (linki)

PRZYKŁAD DOBREJ ODPOWIEDZI:
"Znalazłem informacje o obsłudze kolizji w PyGame:

Kluczowe punkty:
• PyGame używa pygame.Rect.colliderect() do detekcji kolizji prostokątów
• Dla precyzyjnych kolizji można użyć pygame.sprite.collide_mask()
• Grupy sprite'ów mają wbudowane metody kolizji

Przykład kodu:
```python
# Podstawowa kolizja
if player.rect.colliderect(enemy.rect):
    handle_collision()
```

Źródła:
- pygame.org/docs/ref/rect.html
- realpython.com/pygame-tutorial

[Zapisałem tę wiedzę w pamięci pod kategorią 'pygame_collision']"

PAMIĘTAJ: Jesteś BADACZEM, nie programistą. Dostarczasz wiedzę, nie piszesz finalnego kodu."""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja ResearcherAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)

        # Zarejestruj WebSearchSkill
        web_skill = WebSearchSkill()
        self.kernel.add_plugin(web_skill, plugin_name="WebSearchSkill")

        # Zarejestruj MemorySkill
        memory_skill = MemorySkill()
        self.kernel.add_plugin(memory_skill, plugin_name="MemorySkill")

        logger.info("ResearcherAgent zainicjalizowany z WebSearchSkill i MemorySkill")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza pytanie badawcze i syntetyzuje wiedzę.

        Args:
            input_text: Pytanie lub temat do zbadania

        Returns:
            Podsumowanie znalezionej wiedzy z przykładami
        """
        logger.info(f"ResearcherAgent przetwarza zapytanie: {input_text[:100]}...")

        # Przygotuj historię rozmowy
        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
        )
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=input_text)
        )

        try:
            # Pobierz serwis chat completion
            chat_service = self.kernel.get_service()

            # Włącz automatyczne wywoływanie funkcji
            settings = OpenAIChatPromptExecutionSettings(
                function_choice_behavior=FunctionChoiceBehavior.Auto(),
                max_tokens=2000,  # Ogranicz długość odpowiedzi
            )

            # Wywołaj model z możliwością auto-wywołania funkcji
            response = await chat_service.get_chat_message_content(
                chat_history=chat_history, settings=settings
            )

            result = str(response).strip()
            logger.info(f"ResearcherAgent wygenerował odpowiedź ({len(result)} znaków)")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania przez ResearcherAgent: {e}")
            return f"Wystąpił błąd podczas badania: {str(e)}. Proszę spróbować ponownie lub sformułować pytanie inaczej."
