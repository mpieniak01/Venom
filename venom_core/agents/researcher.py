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
from venom_core.execution.skills.github_skill import GitHubSkill
from venom_core.execution.skills.huggingface_skill import HuggingFaceSkill
from venom_core.execution.skills.web_skill import WebSearchSkill
from venom_core.memory.memory_skill import MemorySkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def format_grounding_sources(response_metadata: dict) -> str:
    """
    Formatuje źródła z Google Grounding do czytelnej formy.
    
    Args:
        response_metadata: Metadane odpowiedzi z API (grounding_metadata, web_search_queries)
    
    Returns:
        Sformatowana sekcja ze źródłami lub pusty string jeśli brak
    """
    if not response_metadata:
        return ""
    
    sources = []
    
    # Sprawdź grounding_metadata
    grounding_metadata = response_metadata.get("grounding_metadata", {})
    if grounding_metadata and grounding_metadata.get("grounding_chunks"):
        chunks = grounding_metadata.get("grounding_chunks", [])
        for idx, chunk in enumerate(chunks, 1):
            title = chunk.get("title", "Brak tytułu")
            uri = chunk.get("uri", "")
            if uri:
                sources.append(f"[{idx}] {title} - {uri}")
    
    # Sprawdź web_search_queries (alternatywne źródło metadanych)
    web_queries = response_metadata.get("web_search_queries", [])
    if web_queries and not sources:
        for idx, query in enumerate(web_queries, 1):
            sources.append(f"[{idx}] Zapytanie: {query}")
    
    if sources:
        sources_section = "\n\n---\n📚 Źródła (Google Grounding):\n" + "\n".join(sources)
        return sources_section
    
    return ""


class ResearcherAgent(BaseAgent):
    """Agent specjalizujący się w badaniu i syntezie wiedzy z Internetu."""

    SYSTEM_PROMPT = """Jesteś ekspertem badawczym (Researcher). Twoim zadaniem jest znajdowanie i synteza wiedzy z Internetu.

TWOJE NARZĘDZIA:
- search: Wyszukaj informacje w Internecie (DuckDuckGo)
- scrape_text: Pobierz i oczyść treść konkretnej strony WWW
- search_and_scrape: Wyszukaj i automatycznie pobierz treść z najlepszych wyników
- search_repos: Wyszukaj repozytoria na GitHub (biblioteki, narzędzia)
- get_readme: Pobierz README z repozytorium GitHub
- get_trending: Znajdź popularne projekty na GitHub
- search_models: Wyszukaj modele AI na Hugging Face
- get_model_card: Pobierz szczegóły modelu z Hugging Face
- search_datasets: Wyszukaj zbiory danych na Hugging Face
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

        # Zarejestruj GitHubSkill
        github_skill = GitHubSkill()
        self.kernel.add_plugin(github_skill, plugin_name="GitHubSkill")

        # Zarejestruj HuggingFaceSkill
        hf_skill = HuggingFaceSkill()
        self.kernel.add_plugin(hf_skill, plugin_name="HuggingFaceSkill")

        # Zarejestruj MemorySkill
        memory_skill = MemorySkill()
        self.kernel.add_plugin(memory_skill, plugin_name="MemorySkill")
        
        # Tracking źródła danych (dla UI badge)
        self._last_search_source = "duckduckgo"  # domyślnie DuckDuckGo

        logger.info(
            "ResearcherAgent zainicjalizowany z WebSearchSkill, GitHubSkill, HuggingFaceSkill i MemorySkill"
        )

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
            
            # Sprawdź czy odpowiedź zawiera metadane Google Grounding
            response_metadata = {}
            if hasattr(response, 'metadata'):
                response_metadata = response.metadata or {}
            
            # Dodaj źródła jeśli są dostępne
            sources_section = format_grounding_sources(response_metadata)
            if sources_section:
                result += sources_section
                self._last_search_source = "google_grounding"
                logger.info("Dodano źródła z Google Grounding do odpowiedzi")
            else:
                # Jeśli nie ma źródeł z Grounding, oznacz że użyto DuckDuckGo
                self._last_search_source = "duckduckgo"
            
            logger.info(f"ResearcherAgent wygenerował odpowiedź ({len(result)} znaków)")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania przez ResearcherAgent: {e}")
            return f"Wystąpił błąd podczas badania: {str(e)}. Proszę spróbować ponownie lub sformułować pytanie inaczej."
    
    def get_last_search_source(self) -> str:
        """
        Zwraca źródło ostatniego wyszukiwania (dla UI badge).
        
        Returns:
            'google_grounding' lub 'duckduckgo'
        """
        return self._last_search_source
