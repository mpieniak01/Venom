"""Moduł: researcher - agent badawczy, synteza wiedzy z Internetu."""

import asyncio
import os
import re
from typing import Any, List, Tuple

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


def _first_non_none(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
    return {}


def _grounding_chunk_sources(grounding_metadata: dict[str, Any]) -> list[str]:
    sources: list[str] = []
    chunks = (
        _first_non_none(grounding_metadata, ("grounding_chunks", "groundingChunks"))
        or []
    )
    for idx, chunk_raw in enumerate(chunks, 1):
        chunk = _as_dict(chunk_raw)
        web = _as_dict(chunk.get("web"))
        title = (
            web.get("title") or chunk.get("title") or chunk.get("uri") or "Brak tytułu"
        )
        uri = web.get("uri") or chunk.get("uri") or ""
        if uri:
            sources.append(f"[{idx}] {title} - {uri}")
        elif title and title != "Brak tytułu":
            sources.append(f"[{idx}] {title}")
    return sources


def _grounding_query_sources(
    response_metadata: dict[str, Any], grounding_metadata: dict[str, Any]
) -> list[str]:
    web_queries = (
        _first_non_none(grounding_metadata, ("web_search_queries", "webSearchQueries"))
        or _first_non_none(
            response_metadata, ("web_search_queries", "webSearchQueries")
        )
        or []
    )
    return [f"[{idx}] Zapytanie: {query}" for idx, query in enumerate(web_queries, 1)]


def _render_sources_section(sources: list[str]) -> str:
    if not sources:
        return ""
    return "\n\n---\n📚 Źródła (Google Grounding):\n" + "\n".join(sources)


def format_grounding_sources(response_metadata: dict[str, Any]) -> str:
    """
    Formatuje źródła z Google Grounding do czytelnej formy.

    Args:
        response_metadata: Metadane odpowiedzi z API (grounding_metadata, web_search_queries)

    Returns:
        Sformatowana sekcja ze źródłami lub pusty string jeśli brak
    """
    if not response_metadata:
        return ""

    grounding_metadata = _as_dict(
        _first_non_none(response_metadata, ("grounding_metadata", "groundingMetadata"))
    )
    chunk_sources = _grounding_chunk_sources(grounding_metadata)
    if chunk_sources:
        return _render_sources_section(chunk_sources)
    query_sources = _grounding_query_sources(response_metadata, grounding_metadata)
    return _render_sources_section(query_sources)


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

        # W testach nie chcemy rejestrować ciężkich pluginów (GitHub/HF)
        self._testing_mode = bool(os.getenv("PYTEST_CURRENT_TEST"))

        # Zarejestruj WebSearchSkill
        self.web_skill = WebSearchSkill()
        self.kernel.add_plugin(self.web_skill, plugin_name="WebSearchSkill")

        if not self._testing_mode:
            # Integracje zewnętrzne są opcjonalne w profilach lite.
            try:
                from venom_core.execution.skills.github_skill import GitHubSkill

                github_skill = GitHubSkill()
                self.kernel.add_plugin(github_skill, plugin_name="GitHubSkill")
            except ImportError as e:
                logger.warning(
                    f"GitHubSkill niedostępny (brak zależności PyGithub): {e}"
                )

            try:
                from venom_core.execution.skills.huggingface_skill import (
                    HuggingFaceSkill,
                )

                hf_skill = HuggingFaceSkill()
                self.kernel.add_plugin(hf_skill, plugin_name="HuggingFaceSkill")
            except ImportError as e:
                logger.warning(
                    f"HuggingFaceSkill niedostępny (brak huggingface_hub): {e}"
                )

        # Zarejestruj MemorySkill
        memory_skill = MemorySkill()
        self.kernel.add_plugin(memory_skill, plugin_name="MemorySkill")

        # Tracking źródła danych (dla UI badge)
        self._last_search_source = "duckduckgo"  # domyślnie DuckDuckGo

        if self._testing_mode:
            logger.info(
                "ResearcherAgent zainicjalizowany w trybie testowym (WebSearch + Memory)"
            )
        else:
            logger.info(
                "ResearcherAgent zainicjalizowany z WebSearchSkill, GitHubSkill, HuggingFaceSkill i MemorySkill"
            )

    @staticmethod
    def _extract_grounding_metadata_from_response(response: Any) -> dict[str, Any]:
        inner_content = getattr(response, "inner_content", None)
        if inner_content is None:
            return {}

        candidates = getattr(inner_content, "candidates", None)
        if not candidates:
            return {}

        first_candidate = candidates[0]
        grounding_raw = getattr(first_candidate, "grounding_metadata", None)
        if grounding_raw is None and isinstance(first_candidate, dict):
            grounding_raw = _first_non_none(
                first_candidate, ("grounding_metadata", "groundingMetadata")
            )

        grounding_metadata = _as_dict(grounding_raw)
        if not grounding_metadata:
            return {}
        return {"grounding_metadata": grounding_metadata}

    @staticmethod
    def _configure_google_grounding(settings: Any) -> None:
        # Aktualna dokumentacja Gemini API: Google Search tool.
        extension_data = getattr(settings, "extension_data", None)
        if not isinstance(extension_data, dict):
            extension_data = {}
            setattr(settings, "extension_data", extension_data)
        extension_data["tools"] = [{"google_search": {}}]

    async def process(self, input_text: str) -> str:
        """
        Przetwarza pytanie badawcze i syntetyzuje wiedzę.

        Args:
            input_text: Pytanie lub temat do zbadania

        Returns:
            Podsumowanie znalezionej wiedzy z przykładami
        """
        logger.info(f"ResearcherAgent przetwarza zapytanie: {input_text[:100]}...")

        auto_summary = None
        if not self._testing_mode:
            auto_summary = await self._search_scrape_and_summarize(input_text)
            if auto_summary:
                logger.info("ResearcherAgent: użyto ścieżki search->scrape->summary")
                return auto_summary

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
            chat_service: Any = self.kernel.get_service()

            # Lokalny endpoint (vLLM/Ollama) nie wspiera jeszcze narzędzi w naszej konfiguracji.
            from venom_core.utils.llm_runtime import get_active_llm_runtime

            runtime = get_active_llm_runtime()
            use_google_grounding = runtime.provider in {"google", "google-gemini"}
            allow_functions = runtime.provider not in ("vllm", "ollama", "local")
            if use_google_grounding:
                # Google Search grounding wymaga własnego toola; wyłączamy kernel tools.
                allow_functions = False

            settings = self._create_execution_settings(
                default_settings={"max_tokens": 800},
                function_choice_behavior=(
                    FunctionChoiceBehavior.Auto() if allow_functions else None
                ),
            )
            if use_google_grounding:
                self._configure_google_grounding(settings)

            # Wywołaj model; function calling tylko gdy provider to wspiera
            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=chat_history,
                settings=settings,
                enable_functions=allow_functions,
            )

            result = str(response).strip()

            # Sprawdź czy odpowiedź zawiera metadane Google Grounding
            response_metadata: dict[str, Any] = {}
            if hasattr(response, "metadata"):
                response_metadata.update(_as_dict(getattr(response, "metadata") or {}))
            response_metadata.update(
                self._extract_grounding_metadata_from_response(response)
            )

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

    async def _search_scrape_and_summarize(self, query: str) -> str | None:
        if self._testing_mode:
            return None
        if not query or not query.strip():
            return None

        # Uruchom synchroniczne operacje I/O w puli wątków
        search_output = await asyncio.to_thread(
            self.web_skill.search, query, max_results=3
        )
        urls = self._extract_urls(search_output)
        if not urls:
            return None

        scraped: List[Tuple[str, str]] = []
        for url in urls[:2]:
            content = await asyncio.to_thread(self.web_skill.scrape_text, url)
            if content:
                scraped.append((url, content))

        if not scraped:
            return None

        summary = await self._summarize_sources(query, scraped)
        sources_block = "\n".join(f"- {url}" for url, _ in scraped)
        return f"{summary}\n\nŹródła:\n{sources_block}"

    @staticmethod
    def _extract_urls(search_output: str) -> List[str]:
        if not search_output:
            return []
        return re.findall(r"URL:\s*(\S+)", search_output)

    async def _summarize_sources(
        self, query: str, sources: List[Tuple[str, str]]
    ) -> str:
        chat_service: Any = self.kernel.get_service()
        trimmed_sources = []
        for url, content in sources:
            snippet = content.strip()
            if len(snippet) > 2000:
                snippet = snippet[:2000] + "\n[...obcięto...]"
            trimmed_sources.append((url, snippet))

        summary_prompt = "Stwórz zwięzłe streszczenie na podstawie źródeł.\n"
        summary_prompt += f"Zapytanie: {query}\n\nŹródła:\n"
        for idx, (url, snippet) in enumerate(trimmed_sources, 1):
            summary_prompt += f"[{idx}] {url}\n{snippet}\n\n"

        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content="Jesteś badaczem. Odpowiedz krótko i rzeczowo po polsku.",
            )
        )
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=summary_prompt)
        )

        settings = OpenAIChatPromptExecutionSettings(max_tokens=1200)
        response = await self._invoke_chat_with_fallbacks(
            chat_service=chat_service,
            chat_history=chat_history,
            settings=settings,
            enable_functions=False,
        )
        return str(response).strip()
