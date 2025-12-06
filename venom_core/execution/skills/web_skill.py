"""Moduł: web_skill - Plugin Semantic Kernel do wyszukiwania w Internecie."""

from typing import Annotated

import httpx
import trafilatura
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from semantic_kernel.functions import kernel_function

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Limity dla bezpieczeństwa i wydajności
MAX_SEARCH_RESULTS = 5
MAX_SCRAPED_TEXT_LENGTH = 8000  # Maksymalna długość tekstu ze strony (tokeny)
MAX_TOTAL_CONTEXT_LENGTH = 20000  # Maksymalna łączna długość dla wielu stron


class WebSearchSkill:
    """
    Skill do wyszukiwania informacji w Internecie.
    Pozwala agentom wyszukiwać informacje i pobierać treść ze stron WWW.
    """

    def __init__(self):
        """Inicjalizacja WebSearchSkill."""
        logger.info("WebSearchSkill zainicjalizowany")

    @kernel_function(
        name="search",
        description="Wyszukuje informacje w Internecie używając DuckDuckGo. Zwraca listę tytułów, URL i krótkich opisów znalezionych stron.",
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
            # Użyj DuckDuckGo do wyszukiwania
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))

            if not results:
                return f"Nie znaleziono wyników dla zapytania: {query}"

            # Formatuj wyniki
            output = f"Znaleziono {len(results)} wyników dla zapytania: '{query}'\n\n"
            for i, result in enumerate(results, 1):
                title = result.get("title", "Brak tytułu")
                url = result.get("href", "Brak URL")
                snippet = result.get("body", "Brak opisu")

                output += f"[{i}] {title}\n"
                output += f"URL: {url}\n"
                output += f"Opis: {snippet}\n\n"

            logger.info(f"WebSearch: znaleziono {len(results)} wyników")
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
