"""Moduł: web_skill - Plugin Semantic Kernel do wyszukiwania w Internecie."""

from typing import Annotated

import httpx
import trafilatura
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.utils.helpers import extract_secret_value
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Limity dla bezpieczeństwa i wydajności
MAX_SEARCH_RESULTS = 5
MAX_SCRAPED_TEXT_LENGTH = 8000  # Maksymalna długość tekstu ze strony (tokeny)
MAX_TOTAL_CONTEXT_LENGTH = 20000  # Maksymalna łączna długość dla wielu stron
MAX_CONTENT_PREVIEW_LENGTH = 200  # Maksymalna długość podglądu opisu w wynikach


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
            try:
                from tavily import TavilyClient

                self.tavily_client = TavilyClient(api_key=tavily_key)
                logger.info("WebSearchSkill zainicjalizowany z Tavily AI Search")
            except ImportError:
                logger.warning(
                    "tavily-python nie jest zainstalowane. Używam DuckDuckGo jako fallback."
                )
            except Exception as e:
                logger.warning(
                    f"Błąd inicjalizacji Tavily client: {e}. Używam DuckDuckGo jako fallback."
                )
        else:
            logger.info(
                "WebSearchSkill zainicjalizowany z DuckDuckGo (brak TAVILY_API_KEY)"
            )

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
            # LOW-COST ROUTING: W trybie LOCAL lub ECO zawsze używaj DuckDuckGo (darmowe)
            use_free_search = self.ai_mode == "LOCAL" or self.ai_mode == "ECO"

            # Użyj Tavily jeśli dostępny i nie jesteśmy w trybie LOCAL/ECO
            if self.tavily_client and not use_free_search:
                try:
                    response = self.tavily_client.search(
                        query=query,
                        max_results=max_results,
                        include_answer=True,
                        include_raw_content=False,
                    )

                    # Formatuj wyniki Tavily
                    output = f"Znaleziono wyniki dla zapytania: '{query}'\n"
                    output += "(źródło: Tavily AI Search)\n\n"

                    # Dodaj AI-generated answer jeśli dostępny
                    if response.get("answer"):
                        output += f"📋 Podsumowanie AI:\n{response['answer']}\n\n"

                    results = response.get("results", [])
                    if not results:
                        return f"Nie znaleziono wyników dla zapytania: {query}"

                    output += f"🔍 Źródła ({len(results)}):\n\n"
                    for i, result in enumerate(results[:max_results], 1):
                        title = result.get("title", "Brak tytułu")
                        url = result.get("url", "Brak URL")
                        content = result.get("content", "Brak opisu")

                        output += f"[{i}] {title}\n"
                        output += f"URL: {url}\n"
                        # Użyj stałej zamiast hardcoded wartości
                        output += f"Opis: {content[:MAX_CONTENT_PREVIEW_LENGTH]}...\n\n"

                    logger.info(
                        f"WebSearch (Tavily): znaleziono {len(results)} wyników"
                    )
                    return output.strip()

                except Exception as tavily_error:
                    logger.warning(
                        f"Błąd Tavily: {tavily_error}. Przełączam na DuckDuckGo."
                    )
                    # Informuj agenta o fallback
                    fallback_note = "⚠️ Tavily niedostępny, użyto DuckDuckGo\n\n"
                    # Fallback do DuckDuckGo poniżej

            # Fallback: Użyj DuckDuckGo
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))

            if not results:
                return f"Nie znaleziono wyników dla zapytania: {query}"

            # Formatuj wyniki DuckDuckGo
            output = ""
            # Dodaj notatkę o fallback jeśli była próba użycia Tavily
            if self.tavily_client and "fallback_note" in locals():
                output += fallback_note
            output += f"Znaleziono {len(results)} wyników dla zapytania: '{query}'\n"
            output += "(źródło: DuckDuckGo)\n\n"
            for i, result in enumerate(results, 1):
                title = result.get("title", "Brak tytułu")
                url = result.get("href", "Brak URL")
                snippet = result.get("body", "Brak opisu")

                output += f"[{i}] {title}\n"
                output += f"URL: {url}\n"
                output += f"Opis: {snippet}\n\n"

            logger.info(f"WebSearch (DuckDuckGo): znaleziono {len(results)} wyników")
            return output.strip()

        except Exception as e:
            logger.error(f"Błąd podczas wyszukiwania: {e}")
            return f"Wystąpił błąd podczas wyszukiwania: {str(e)}"

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
            # Najpierw spróbuj trafilatura (lepsze czyszczenie)
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=False,
                )

                if text and len(text.strip()) > 100:
                    # Ogranicz długość
                    if len(text) > MAX_SCRAPED_TEXT_LENGTH:
                        text = (
                            text[:MAX_SCRAPED_TEXT_LENGTH] + "\n\n[...tekst obcięty...]"
                        )

                    logger.info(
                        f"WebScrape: pobrano {len(text)} znaków z {url} (trafilatura)"
                    )
                    return f"Treść ze strony {url}:\n\n{text}"

            # Fallback do BeautifulSoup jeśli trafilatura zawiodła
            logger.warning(
                f"Trafilatura nie zwróciła wyników dla {url}, próbuję BeautifulSoup"
            )

            response = httpx.get(url, timeout=10, follow_redirects=True)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Usuń skrypty, style, itp.
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Pobierz tekst
            text = soup.get_text(separator="\n", strip=True)

            # Usuń puste linie
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            text = "\n".join(lines)

            # Ogranicz długość
            if len(text) > MAX_SCRAPED_TEXT_LENGTH:
                text = text[:MAX_SCRAPED_TEXT_LENGTH] + "\n\n[...tekst obcięty...]"

            if len(text.strip()) < 50:
                return f"Strona {url} nie zawiera wystarczającej ilości tekstu lub jest niedostępna."

            logger.info(
                f"WebScrape: pobrano {len(text)} znaków z {url} (BeautifulSoup)"
            )
            return f"Treść ze strony {url}:\n\n{text}"

        except httpx.TimeoutException:
            logger.error(f"Timeout podczas pobierania {url}")
            return f"Przekroczono limit czasu podczas pobierania {url}"
        except httpx.HTTPStatusError as e:
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
                title = result.get("title", "Brak tytułu")

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
