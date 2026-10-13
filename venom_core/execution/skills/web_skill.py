"""Moduł: web_skill - Plugin Semantic Kernel do wyszukiwania w Internecie."""

from importlib import import_module
from typing import Annotated, Any, Optional

import httpx
from httpx import HTTPStatusError as HttpxHTTPStatusError
from httpx import TimeoutException as HttpxTimeoutException
from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient
from venom_core.utils.helpers import extract_secret_value
from venom_core.utils.logger import get_logger

_trafilatura: Any = None
try:  # pragma: no cover - zależne od środowiska
    import trafilatura as _trafilatura_module

    _trafilatura = _trafilatura_module
except Exception:  # pragma: no cover
    pass

trafilatura: Any = _trafilatura

_beautiful_soup_cls: Any = None
try:  # pragma: no cover - zależne od środowiska
    from bs4 import BeautifulSoup as _BeautifulSoupClass

    _beautiful_soup_cls = _BeautifulSoupClass
except Exception:  # pragma: no cover
    pass

BeautifulSoup: Any = _beautiful_soup_cls

DDGS: Any = None
try:  # pragma: no cover - zależne od środowiska
    ddgs_module = import_module("ddgs")
    DDGS = getattr(ddgs_module, "DDGS", None)
except Exception:  # pragma: no cover
    DDGS = None

if DDGS is None:  # pragma: no cover - fallback zależny od środowiska
    try:
        duckduckgo_module = import_module("duckduckgo_search")
        DDGS = getattr(duckduckgo_module, "DDGS", None)
    except Exception:
        DDGS = None

logger = get_logger(__name__)
# Utrzymujemy referencję modułu dla testów patchujących `web_skill.httpx`.
HTTPX_MODULE = httpx

# Staramy się opcjonalnie załadować TavilyClient aby testy mogły go mockować
_ImportedTavilyClient: Any = None
try:  # pragma: no cover - zależne od środowiska
    _ImportedTavilyClient = getattr(import_module("tavily"), "TavilyClient", None)
except Exception:  # pragma: no cover
    pass

# Wystaw symbol na poziomie modułu (nawet jeśli None), aby patchowanie było możliwe
TavilyClient = _ImportedTavilyClient

# Limity dla bezpieczeństwa i wydajności
MAX_SEARCH_RESULTS = 5
MAX_SCRAPED_TEXT_LENGTH = 8000  # Maksymalna długość tekstu ze strony (tokeny)
MAX_TOTAL_CONTEXT_LENGTH = 20000  # Maksymalna łączna długość dla wielu stron
MAX_CONTENT_PREVIEW_LENGTH = 200  # Maksymalna długość podglądu opisu w wynikach
NO_TITLE_TEXT = "Brak tytułu"


class WebSearchSkill:
    """
    Skill do wyszukiwania informacji w Internecie.
    Pozwala agentom wyszukiwać informacje i pobierać treść ze stron WWW.
    Obsługuje Tavily AI Search (gdy skonfigurowany) lub DuckDuckGo (fallback).
    """

    def __init__(self):
        """Inicjalizacja WebSearchSkill."""
        # Sprawdź czy Tavily jest skonfigurowany
        self.tavily_client = None
        tavily_key = None

        # Pobierz AI_MODE dla strategii kosztowej
        self.ai_mode = getattr(SETTINGS, "AI_MODE", "LOCAL")

        if hasattr(SETTINGS, "TAVILY_API_KEY"):
            tavily_key = extract_secret_value(SETTINGS.TAVILY_API_KEY)

        if tavily_key:
            # Prefer dynamic import to respect test patching and runtime changes.
            tavily_cls = _get_tavily_client_class() or TavilyClient
        else:
            tavily_cls = None

        if tavily_key and tavily_cls is not None:
            try:
                self.tavily_client = tavily_cls(api_key=tavily_key)
                logger.info("WebSearchSkill zainicjalizowany z Tavily AI Search")
            except Exception as e:  # pragma: no cover - zależy od środowiska
                logger.warning(
                    f"Błąd inicjalizacji Tavily client: {e}. Używam DuckDuckGo jako fallback."
                )
        elif tavily_key:
            logger.warning(
                "tavily-python nie jest zainstalowane. Używam DuckDuckGo jako fallback."
            )
        else:
            logger.info(
                "WebSearchSkill zainicjalizowany z DuckDuckGo (brak TAVILY_API_KEY)"
            )

    def _truncate_scraped_text(self, text: str) -> str:
        if len(text) > MAX_SCRAPED_TEXT_LENGTH:
            return text[:MAX_SCRAPED_TEXT_LENGTH] + "\n\n[...tekst obcięty...]"
        return text

    def _scrape_with_trafilatura(self, url: str) -> str | None:
        if trafilatura is None:
            return None

        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None

        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        if not text or not text.strip():
            return None

        text = self._truncate_scraped_text(text)
        logger.info(f"WebScrape: pobrano {len(text)} znaków z {url} (trafilatura)")
        return f"Treść ze strony {url}:\n\n{text}"

    def _scrape_with_beautifulsoup(self, url: str) -> str:
        if BeautifulSoup is None:
            return (
                "❌ Brak biblioteki beautifulsoup4. "
                "Doinstaluj zależności aby użyć fallback scrape_text."
            )

        with TrafficControlledHttpClient(provider="web_scrape", timeout=10.0) as client:
            response = client.get(url, follow_redirects=True)

        soup = BeautifulSoup(response.content, "html.parser")
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        text = soup.get_text(separator="\n", strip=True)
        text = "\n".join(line.strip() for line in text.split("\n") if line.strip())
        text = self._truncate_scraped_text(text)

        if not text.strip():
            return (
                f"Strona {url} nie zawiera wystarczającej ilości tekstu "
                "lub jest niedostępna."
            )

        logger.info(f"WebScrape: pobrano {len(text)} znaków z {url} (BeautifulSoup)")
        return f"Treść ze strony {url}:\n\n{text}"

    @kernel_function(
        name="search",
        description="Wyszukuje informacje w Internecie używając Tavily AI Search (jeśli skonfigurowany) lub DuckDuckGo. "
        "Zwraca listę tytułów, URL i krótkich opisów znalezionych stron.",
    )
    def search(
        self,
        query: Annotated[str, "Zapytanie do wyszukiwarki"],
        max_results: Annotated[
            int, "Maksymalna liczba wyników (domyślnie 5)"
        ] = MAX_SEARCH_RESULTS,
    ) -> str:
        """
        Wyszukuje informacje w Internecie.

        Args:
            query: Zapytanie do wyszukiwarki
            max_results: Maksymalna liczba wyników

        Returns:
            Sformatowana lista wyników wyszukiwania
        """
        logger.info(
            f"WebSearch: szukanie '{query[:100]}...' (max {max_results} wyników)"
        )

        try:
            use_free_search = self._should_use_free_search()
            fallback_note = ""

            if self.tavily_client and not use_free_search:
                tavily_result = self._search_with_tavily(query, max_results)
                if tavily_result is not None:
                    return tavily_result
                fallback_note = "⚠️ Tavily niedostępny, użyto DuckDuckGo\n\n"

            return self._search_with_duckduckgo(query, max_results, fallback_note)
        except Exception as e:
            logger.error(f"Błąd podczas wyszukiwania: {e}")
            return f"Wystąpił błąd podczas wyszukiwania: {str(e)}"

    def _should_use_free_search(self) -> bool:
        force_free = getattr(SETTINGS, "LOW_COST_FORCE_DDG", True)
        return force_free and self.ai_mode in ("LOCAL", "ECO")

    def _search_with_tavily(self, query: str, max_results: int) -> str | None:
        client = self.tavily_client
        if client is None:
            return None
        try:
            response = client.search(
                query=query,
                max_results=max_results,
                include_answer=True,
                include_raw_content=False,
            )
        except Exception as tavily_error:
            logger.warning(f"Błąd Tavily: {tavily_error}. Przełączam na DuckDuckGo.")
            return None

        return self._format_tavily_response(query, response, max_results)

    def _format_tavily_response(
        self, query: str, response: dict[str, Any], max_results: int
    ) -> str:
        output = f"Znaleziono wyniki dla zapytania: '{query}'\n(źródło: Tavily AI Search)\n\n"
        if response.get("answer"):
            output += f"📋 Podsumowanie AI:\n{response['answer']}\n\n"

        results = response.get("results", [])
        if not results:
            return f"Nie znaleziono wyników dla zapytania: {query}"

        output += f"🔍 Źródła ({len(results)}):\n\n"
        for i, result in enumerate(results[:max_results], 1):
            title = result.get("title", NO_TITLE_TEXT)
            url = result.get("url", "Brak URL")
            content = result.get("content", "Brak opisu")
            output += f"[{i}] {title}\nURL: {url}\n"
            output += f"Opis: {content[:MAX_CONTENT_PREVIEW_LENGTH]}...\n\n"

        logger.info(f"WebSearch (Tavily): znaleziono {len(results)} wyników")
        return output.strip()

    def _search_with_duckduckgo(
        self, query: str, max_results: int, fallback_note: str = ""
    ) -> str:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return f"Nie znaleziono wyników dla zapytania: {query}"

        output = fallback_note
        output += f"Znaleziono {len(results)} wyników dla zapytania: '{query}'\n"
        output += "(źródło: DuckDuckGo)\n\n"
        for i, result in enumerate(results, 1):
            title = result.get("title", NO_TITLE_TEXT)
            url = result.get("href", "Brak URL")
            snippet = result.get("body", "Brak opisu")
            output += f"[{i}] {title}\nURL: {url}\nOpis: {snippet}\n\n"

        logger.info(f"WebSearch (DuckDuckGo): znaleziono {len(results)} wyników")
        return output.strip()

    @kernel_function(
        name="scrape_text",
        description="Pobiera i oczyszcza tekst ze strony internetowej. Zwraca czysty tekst bez reklam i śmieci HTML.",
    )
    def scrape_text(
        self,
        url: Annotated[str, "URL strony do pobrania"],
    ) -> str:
        """
        Pobiera i oczyszcza tekst ze strony WWW.

        Args:
            url: URL strony do pobrania

        Returns:
            Czysty tekst ze strony lub komunikat o błędzie
        """
        logger.info(f"WebScrape: pobieranie tekstu z {url}")

        try:
            if trafilatura is None and BeautifulSoup is None:
                return (
                    "❌ Brak bibliotek do scrapowania (trafilatura/beautifulsoup4). "
                    "Doinstaluj zależności aby użyć scrape_text."
                )

            text = self._scrape_with_trafilatura(url)
            if text is not None:
                return text

            # Fallback do BeautifulSoup jeśli trafilatura zawiodła
            logger.warning(
                f"Trafilatura nie zwróciła wyników dla {url}, próbuję BeautifulSoup"
            )
            return self._scrape_with_beautifulsoup(url)

        except HttpxTimeoutException:
            logger.error(f"Timeout podczas pobierania {url}")
            return f"Przekroczono limit czasu podczas pobierania {url}"
        except HttpxHTTPStatusError as e:
            logger.error(f"Błąd HTTP podczas pobierania {url}: {e}")
            return f"Błąd HTTP podczas pobierania {url}: {e.response.status_code}"
        except Exception as e:
            logger.error(f"Błąd podczas scrapowania {url}: {e}")
            return f"Nie udało się pobrać treści z {url}: {str(e)}"

    @kernel_function(
        name="search_and_scrape",
        description="Wyszukuje informacje w Internecie i automatycznie pobiera treść z najlepszych wyników. Zwraca skonsolidowaną wiedzę z wielu źródeł.",
    )
    def search_and_scrape(
        self,
        query: Annotated[str, "Zapytanie do wyszukiwarki"],
        num_sources: Annotated[int, "Liczba stron do pobrania (domyślnie 3)"] = 3,
    ) -> str:
        """
        Wyszukuje i pobiera treść z najlepszych wyników.

        Args:
            query: Zapytanie do wyszukiwarki
            num_sources: Liczba stron do pobrania

        Returns:
            Skonsolidowana wiedza z wielu źródeł
        """
        logger.info(
            f"WebSearchAndScrape: szukanie i pobieranie {num_sources} źródeł dla '{query[:100]}...'"
        )

        try:
            # Ogranicz liczbę źródeł
            num_sources = min(num_sources, MAX_SEARCH_RESULTS)

            # Wyszukaj
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=num_sources))

            if not results:
                return f"Nie znaleziono wyników dla zapytania: {query}"

            # Pobierz treść z każdego wyniku
            consolidated = f"Wyniki wyszukiwania dla: '{query}'\n\n"
            total_length = 0

            for i, result in enumerate(results, 1):
                url = result.get("href", "")
                title = result.get("title", NO_TITLE_TEXT)

                if not url:
                    continue

                consolidated += f"\n{'=' * 80}\n"
                consolidated += f"ŹRÓDŁO {i}: {title}\n"
                consolidated += f"URL: {url}\n"
                consolidated += f"{'=' * 80}\n\n"

                # Pobierz treść
                content = self.scrape_text(url)

                # Sprawdź limity
                if total_length + len(content) > MAX_TOTAL_CONTEXT_LENGTH:
                    logger.warning(
                        f"Osiągnięto limit całkowitej długości tekstu po {i} źródłach"
                    )
                    consolidated += "\n[...osiągnięto limit długości, pozostałe źródła pominięte...]\n"
                    break

                consolidated += content + "\n\n"
                total_length += len(content)

            logger.info(
                f"WebSearchAndScrape: pobrano {total_length} znaków z {len(results)} źródeł"
            )
            return consolidated.strip()

        except Exception as e:
            logger.error(f"Błąd podczas search_and_scrape: {e}")
            return f"Wystąpił błąd podczas wyszukiwania i pobierania: {str(e)}"


def _get_tavily_client_class() -> Optional[type]:
    """Ładuje TavilyClient na żądanie."""

    try:  # pragma: no cover - zależne od środowiska
        module = import_module("tavily")
        return getattr(module, "TavilyClient")
    except Exception:  # pragma: no cover
        return None
