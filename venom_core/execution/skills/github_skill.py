"""Moduł: github_skill - Skill do wyszukiwania i analizy repozytoriów GitHub."""

import os
from datetime import datetime, timedelta
from typing import Annotated, Any, Optional

from github import Auth, Github, GithubException
from semantic_kernel.functions import kernel_function

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Limity dla bezpieczeństwa i wydajności
MAX_REPOS_RESULTS = 5
MAX_README_LENGTH = 8000


class GitHubSkill:
    """
    Skill do wyszukiwania repozytoriów i informacji na GitHub.
    Pozwala agentom znajdować popularne biblioteki, pobierać README i trendy.
    """

    def __init__(self, github_token: Optional[str] = None):
        """
        Inicjalizacja GitHubSkill.

        Args:
            github_token: Token GitHub API (opcjonalny, ale zalecany dla wyższych limitów).
                         Jeśli None, używa zmiennej środowiskowej GITHUB_TOKEN.
        """
        # Spróbuj pobrać token z parametru lub zmiennej środowiskowej
        token = github_token or os.getenv("GITHUB_TOKEN")

        if token:
            auth = Auth.Token(token)
            self.github = Github(auth=auth)
            logger.info("GitHubSkill zainicjalizowany z tokenem (wyższe limity API)")
        else:
            self.github = Github()
            logger.info(
                "GitHubSkill zainicjalizowany bez tokenu (niższe limity API, ~60 req/h)"
            )

    @kernel_function(
        name="search_repos",
        description="Wyszukuje repozytoria na GitHub według zapytania. Zwraca TOP 5 repozytoriów z opisem, gwiazdkami i URL. Użyj gdy użytkownik szuka bibliotek, narzędzi lub przykładów kodu.",
    )
    def search_repos(
        self,
        query: Annotated[str, "Zapytanie do wyszukiwarki GitHub"],
        language: Annotated[
            str, "Język programowania do filtrowania (np. 'Python', 'JavaScript')"
        ] = "",
        sort: Annotated[
            str, "Sortowanie: 'stars' (gwiazdki), 'forks', 'updated'"
        ] = "stars",
    ) -> str:
        """
        Wyszukuje repozytoria na GitHub.

        Args:
            query: Zapytanie do wyszukiwarki
            language: Opcjonalny język programowania do filtrowania
            sort: Kryterium sortowania

        Returns:
            Sformatowana lista TOP 5 repozytoriów
        """
        logger.info(
            f"GitHubSkill: search_repos dla '{query}' (language={language}, sort={sort})"
        )

        try:
            # Buduj zapytanie z filtrem języka
            search_query = query
            if language:
                search_query += f" language:{language}"

            # Wyszukaj repozytoria
            repos: list[Any] = list(
                self.github.search_repositories(
                    query=search_query, sort=sort, order="desc"
                )
            )

            # Ogranicz do TOP 5
            results: list[dict[str, Any]] = []
            for i, repo in enumerate(repos[:MAX_REPOS_RESULTS], 1):
                results.append(
                    {
                        "rank": i,
                        "name": repo.full_name,
                        "description": repo.description or "Brak opisu",
                        "stars": repo.stargazers_count,
                        "forks": repo.forks_count,
                        "url": repo.html_url,
                        "language": repo.language or "Nieznany",
                    }
                )

            if not results:
                return f"Nie znaleziono repozytoriów dla zapytania: {query}"

            # Formatuj wyniki
            output = f"🔍 TOP {len(results)} repozytoriów dla: '{query}'\n\n"
            for r in results:
                output += f"[{r['rank']}] {r['name']}\n"
                output += f"⭐ Gwiazdki: {r['stars']:,} | 🔱 Forki: {r['forks']:,} | 💻 Język: {r['language']}\n"
                output += f"📝 Opis: {r['description']}\n"
                output += f"🔗 URL: {r['url']}\n\n"

            logger.info(f"GitHubSkill: znaleziono {len(results)} repozytoriów")
            return output.strip()

        except GithubException as e:
            logger.error(f"Błąd GitHub API: {e}")
            return f"❌ Błąd GitHub API: {str(e)}"
        except Exception as e:
            logger.error(f"Błąd podczas wyszukiwania repozytoriów: {e}")
            return f"❌ Wystąpił błąd: {str(e)}"

    @kernel_function(
        name="get_readme",
        description="Pobiera treść README.md z repozytorium GitHub bez klonowania. Użyj gdy potrzebujesz szczegółowej dokumentacji lub instrukcji użycia biblioteki.",
    )
    def get_readme(
        self,
        repo_url: Annotated[
            str, "URL repozytorium (np. 'https://github.com/user/repo' lub 'user/repo')"
        ],
    ) -> str:
        """
        Pobiera README.md z repozytorium.

        Args:
            repo_url: URL lub nazwa repozytorium (format: owner/repo)

        Returns:
            Treść README.md lub komunikat o błędzie
        """
        logger.info(f"GitHubSkill: get_readme dla {repo_url}")

        try:
            # Ekstrakcja owner/repo z URL
            repo_name = self._extract_repo_name(repo_url)

            # Pobierz repozytorium
            repo = self.github.get_repo(repo_name)

            # Pobierz README
            readme = repo.get_readme()
            content = readme.decoded_content.decode("utf-8")

            # Ogranicz długość
            if len(content) > MAX_README_LENGTH:
                content = content[:MAX_README_LENGTH] + "\n\n[...README obcięty...]"

            output = f"📄 README.md z repozytorium: {repo.full_name}\n"
            output += f"⭐ Gwiazdki: {repo.stargazers_count:,}\n"
            output += f"🔗 URL: {repo.html_url}\n\n"
            output += f"{'=' * 80}\n\n"
            output += content

            logger.info(f"GitHubSkill: pobrano README ({len(content)} znaków)")
            return output

        except GithubException as e:
            if e.status == 404:
                logger.warning(f"Repozytorium lub README nie znalezione: {repo_url}")
                return f"❌ Nie znaleziono repozytorium lub README dla: {repo_url}"
            logger.error(f"Błąd GitHub API: {e}")
            return f"❌ Błąd GitHub API: {str(e)}"
        except Exception as e:
            logger.error(f"Błąd podczas pobierania README: {e}")
            return f"❌ Wystąpił błąd: {str(e)}"

    @kernel_function(
        name="get_trending",
        description="Wyszukuje popularne/trending projekty w danym temacie lub języku. Użyj gdy użytkownik chce znaleźć nowoczesne, aktywnie rozwijane projekty.",
    )
    def get_trending(
        self,
        topic: Annotated[str, "Temat lub język (np. 'machine-learning', 'python')"],
    ) -> str:
        """
        Wyszukuje popularne projekty w danym temacie.

        Args:
            topic: Temat lub język programowania

        Returns:
            Lista popularnych projektów
        """
        logger.info(f"GitHubSkill: get_trending dla topic='{topic}'")

        try:
            # Wyszukaj repozytoria utworzone w ostatnim roku
            # Dynamicznie oblicz datę sprzed roku
            one_year_ago = datetime.now() - timedelta(days=365)
            date_filter = one_year_ago.strftime("%Y-%m-%d")
            search_query = f"{topic} created:>{date_filter}"

            repos: list[Any] = list(
                self.github.search_repositories(
                    query=search_query, sort="stars", order="desc"
                )
            )

            # Ogranicz do TOP 5
            results: list[dict[str, Any]] = []
            for i, repo in enumerate(repos[:MAX_REPOS_RESULTS], 1):
                results.append(
                    {
                        "rank": i,
                        "name": repo.full_name,
                        "description": repo.description or "Brak opisu",
                        "stars": repo.stargazers_count,
                        "url": repo.html_url,
                        "language": repo.language or "Nieznany",
                        "created": repo.created_at.strftime("%Y-%m-%d"),
                    }
                )

            if not results:
                return f"Nie znaleziono popularnych projektów dla tematu: {topic}"

            # Formatuj wyniki
            output = f"🔥 Popularne projekty w temacie: '{topic}'\n\n"
            for r in results:
                output += f"[{r['rank']}] {r['name']}\n"
                output += f"⭐ Gwiazdki: {r['stars']:,} | 💻 Język: {r['language']} | 📅 Utworzono: {r['created']}\n"
                output += f"📝 Opis: {r['description']}\n"
                output += f"🔗 URL: {r['url']}\n\n"

            logger.info(f"GitHubSkill: znaleziono {len(results)} popularnych projektów")
            return output.strip()

        except GithubException as e:
            logger.error(f"Błąd GitHub API: {e}")
            return f"❌ Błąd GitHub API: {str(e)}"
        except Exception as e:
            logger.error(f"Błąd podczas wyszukiwania popularnych projektów: {e}")
            return f"❌ Wystąpił błąd: {str(e)}"

    def _extract_repo_name(self, repo_url: str) -> str:
        """
        Ekstrakcja nazwy repozytorium (owner/repo) z URL.

        Args:
            repo_url: URL lub nazwa repozytorium

        Returns:
            Nazwa w formacie owner/repo
        """
        # Jeśli już jest w formacie owner/repo
        if "/" in repo_url and not repo_url.startswith("http"):
            return repo_url

        # Ekstrakcja z URL
        parts = repo_url.rstrip("/").split("/")
        if len(parts) >= 2:
            # Ostatnie dwa elementy to owner i repo
            return f"{parts[-2]}/{parts[-1]}"

        raise ValueError(f"Nieprawidłowy format URL repozytorium: {repo_url}")

    def close(self):
        """Zamknięcie połączenia z GitHub API."""
        if hasattr(self, "github") and self.github:
            self.github.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
