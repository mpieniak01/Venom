"""Moduł: platform_skill - integracje z platformami zewnętrznymi (GitHub, Discord, Slack)."""

from typing import TYPE_CHECKING, Annotated, Optional

import httpx
from semantic_kernel.functions import kernel_function

if TYPE_CHECKING:
    from github import Github

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class PlatformSkill:
    """
    Skill do integracji z platformami zewnętrznymi.
    Obsługuje GitHub (Issues, PR), Discord, Slack.

    UWAGA: Wymaga konfiguracji tokenów w .env:
    - GITHUB_TOKEN
    - GITHUB_REPO_NAME
    - DISCORD_WEBHOOK_URL (opcjonalne)
    - SLACK_WEBHOOK_URL (opcjonalne)
    """

    def __init__(self):
        """Inicjalizacja PlatformSkill."""
        # Pobierz sekrety i konwertuj SecretStr na string
        self.github_token = None
        if hasattr(SETTINGS, "GITHUB_TOKEN"):
            token = SETTINGS.GITHUB_TOKEN
            # Handle SecretStr
            self.github_token = (
                token.get_secret_value()
                if hasattr(token, "get_secret_value")
                else token
            )
            if not self.github_token:  # Empty string
                self.github_token = None

        self.github_repo_name = getattr(SETTINGS, "GITHUB_REPO_NAME", None)

        # Discord webhook
        self.discord_webhook = None
        if hasattr(SETTINGS, "DISCORD_WEBHOOK_URL"):
            webhook = SETTINGS.DISCORD_WEBHOOK_URL
            self.discord_webhook = (
                webhook.get_secret_value()
                if hasattr(webhook, "get_secret_value")
                else webhook
            )
            if not self.discord_webhook:
                self.discord_webhook = None

        # Slack webhook
        self.slack_webhook = None
        if hasattr(SETTINGS, "SLACK_WEBHOOK_URL"):
            webhook = SETTINGS.SLACK_WEBHOOK_URL
            self.slack_webhook = (
                webhook.get_secret_value()
                if hasattr(webhook, "get_secret_value")
                else webhook
            )
            if not self.slack_webhook:
                self.slack_webhook = None

        # Inicjalizuj klienta GitHub jeśli token dostępny
        self.github_client: Optional["Github"] = None
        if self.github_token:
            try:
                from github import Auth, Github

                self.github_client = Github(auth=Auth.Token(self.github_token))
                # Maskuj token w logach (zabezpieczenie przed krótkimi tokenami)
                if len(self.github_token) > 8:
                    masked_token = (
                        self.github_token[:4] + "..." + self.github_token[-4:]
                    )
                else:
                    masked_token = "***"
                logger.info(
                    f"PlatformSkill: GitHub client zainicjalizowany (token: {masked_token})"
                )
            except ImportError:
                logger.warning(
                    "PlatformSkill: Biblioteka 'PyGithub' nie jest zainstalowana. Funkcje GitHub niedostępne."
                )
            except Exception as e:
                logger.error(f"Błąd inicjalizacji GitHub client: {e}")
        else:
            logger.warning(
                "PlatformSkill: GITHUB_TOKEN nie skonfigurowany - funkcje GitHub niedostępne"
            )

        logger.info("PlatformSkill zainicjalizowany")

    @kernel_function(
        name="get_assigned_issues",
        description="Pobiera Issues przypisane do bota z GitHub (domyślnie otwarte).",
    )
    async def get_assigned_issues(
        self,
        state: Annotated[str, "Stan Issues: 'open', 'closed', 'all'"] = "open",
        assignee: Annotated[
            Optional[str], "Nazwa użytkownika przypisanego (None = wszystkie)"
        ] = None,
    ) -> str:
        """
        Pobiera Issues z GitHub.

        Args:
            state: Stan Issues ('open', 'closed', 'all')
            assignee: Filtruj po przypisanym użytkowniku (None = wszystkie)

        Returns:
            Sformatowany tekst z listą Issues lub komunikat błędu
        """
        if not self.github_client or not self.github_repo_name:
            return "❌ Błąd: GitHub nie skonfigurowany (brak GITHUB_TOKEN lub GITHUB_REPO_NAME)"

        try:
            repo = self.github_client.get_repo(self.github_repo_name)
            issues_list = []

            # Pobierz Issues (jeśli assignee nie podany, pobierz wszystkie)
            if assignee:
                issues = repo.get_issues(state=state, assignee=assignee)
            else:
                issues = repo.get_issues(state=state)

            for issue in issues:
                # Pomiń Pull Requesty (GitHub API zwraca PR jako Issues)
                if issue.pull_request:
                    continue

                issue_data = {
                    "number": issue.number,
                    "title": issue.title,
                    "body": issue.body or "",
                    "state": issue.state,
                    "created_at": issue.created_at.isoformat(),
                    "updated_at": issue.updated_at.isoformat(),
                    "labels": [label.name for label in issue.labels],
                    "assignees": [assignee.login for assignee in issue.assignees],
                    "url": issue.html_url,
                }
                issues_list.append(issue_data)

            logger.info(f"Pobrano {len(issues_list)} Issues (state={state})")

            if not issues_list:
                return f"ℹ️ Brak Issues w stanie '{state}'"

            # Formatuj wynik
            result = f"Znaleziono {len(issues_list)} Issues:\n\n"
            for issue in issues_list:
                result += f"#{issue['number']}: {issue['title']}\n"
                result += f"  Stan: {issue['state']}, Labels: {', '.join(issue['labels']) or 'brak'}\n"
                result += f"  URL: {issue['url']}\n"
                if issue["body"]:
                    body_preview = (
                        issue["body"][:200] + "..."
                        if len(issue["body"]) > 200
                        else issue["body"]
                    )
                    result += f"  Opis: {body_preview}\n"
                result += "\n"

            return result

        except Exception as e:
            # Handle PyGithub exceptions by name to avoid importing the class
            if type(e).__name__ == "GithubException":
                error_msg = f"❌ Błąd GitHub API: {getattr(e, 'status', 'Unknown')} - {getattr(e, 'data', {}).get('message', str(e))}"
                logger.error(error_msg)
                return error_msg

            error_msg = f"❌ Błąd podczas pobierania Issues: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="get_issue_details",
        description="Pobiera szczegóły konkretnego Issue z GitHub (w tym komentarze).",
    )
    async def get_issue_details(
        self,
        issue_number: Annotated[int, "Numer Issue do pobrania"],
    ) -> str:
        """
        Pobiera szczegóły Issue z GitHub.

        Args:
            issue_number: Numer Issue

        Returns:
            Szczegóły Issue lub komunikat błędu
        """
        if not self.github_client or not self.github_repo_name:
            return "❌ Błąd: GitHub nie skonfigurowany (brak GITHUB_TOKEN lub GITHUB_REPO_NAME)"

        try:
            repo = self.github_client.get_repo(self.github_repo_name)
            issue = repo.get_issue(issue_number)

            # Pobierz komentarze
            comments = []
            for comment in issue.get_comments():
                comments.append(
                    {
                        "author": comment.user.login,
                        "created_at": comment.created_at.isoformat(),
                        "body": comment.body,
                    }
                )

            result = f"Issue #{issue.number}: {issue.title}\n"
            result += f"Stan: {issue.state}\n"
            result += f"Utworzono: {issue.created_at.isoformat()}\n"
            result += f"Labels: {', '.join([label.name for label in issue.labels]) or 'brak'}\n"
            result += f"Assignees: {', '.join([a.login for a in issue.assignees]) or 'brak'}\n"
            result += f"URL: {issue.html_url}\n\n"
            result += f"Opis:\n{issue.body or 'Brak opisu'}\n\n"

            if comments:
                result += f"Komentarze ({len(comments)}):\n"
                for i, comment in enumerate(comments, 1):
                    result += f"{i}. {comment['author']} ({comment['created_at']}):\n"
                    result += f"{comment['body']}\n\n"
            else:
                result += "Brak komentarzy.\n"

            logger.info(f"Pobrano szczegóły Issue #{issue_number}")
            return result

        except Exception as e:
            if type(e).__name__ == "GithubException":
                error_msg = f"❌ Błąd GitHub API: {getattr(e, 'status', 'Unknown')} - {getattr(e, 'data', {}).get('message', str(e))}"
                logger.error(error_msg)
                return error_msg

            error_msg = f"❌ Błąd podczas pobierania Issue: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="create_pull_request",
        description="Tworzy Pull Request na GitHub z obecnego brancha.",
    )
    async def create_pull_request(
        self,
        branch: Annotated[str, "Nazwa brancha źródłowego (head)"],
        title: Annotated[str, "Tytuł Pull Requesta"],
        body: Annotated[str, "Opis Pull Requesta (może zawierać 'Closes #123')"],
        base: Annotated[str, "Branch docelowy (default: main)"] = "main",
    ) -> str:
        """
        Tworzy Pull Request na GitHub.

        Args:
            branch: Branch źródłowy (head)
            title: Tytuł PR
            body: Opis PR (może zawierać 'Closes #123' aby linkować Issue)
            base: Branch docelowy (default: main)

        Returns:
            URL Pull Requesta lub komunikat błędu
        """
        if not self.github_client or not self.github_repo_name:
            return "❌ Błąd: GitHub nie skonfigurowany (brak GITHUB_TOKEN lub GITHUB_REPO_NAME)"

        try:
            repo = self.github_client.get_repo(self.github_repo_name)

            # Utwórz Pull Request
            pr = repo.create_pull(
                title=title,
                body=body,
                head=branch,
                base=base,
            )

            result = f"✅ Utworzono Pull Request #{pr.number}: {pr.title}\n"
            result += f"URL: {pr.html_url}\n"
            result += f"Branch: {branch} → {base}\n"

            logger.info(f"Utworzono PR #{pr.number}: {title}")
            return result

        except Exception as e:
            if type(e).__name__ == "GithubException":
                error_msg = f"❌ Błąd GitHub API: {getattr(e, 'status', 'Unknown')} - {getattr(e, 'data', {}).get('message', str(e))}"
                logger.error(error_msg)
                return error_msg

            error_msg = f"❌ Błąd podczas tworzenia PR: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="comment_on_issue",
        description="Dodaje komentarz do Issue na GitHub.",
    )
    async def comment_on_issue(
        self,
        issue_number: Annotated[int, "Numer Issue"],
        text: Annotated[str, "Treść komentarza"],
    ) -> str:
        """
        Dodaje komentarz do Issue.

        Args:
            issue_number: Numer Issue
            text: Treść komentarza

        Returns:
            Potwierdzenie lub komunikat błędu
        """
        if not self.github_client or not self.github_repo_name:
            return "❌ Błąd: GitHub nie skonfigurowany (brak GITHUB_TOKEN lub GITHUB_REPO_NAME)"

        try:
            repo = self.github_client.get_repo(self.github_repo_name)
            issue = repo.get_issue(issue_number)

            comment = issue.create_comment(text)

            result = f"✅ Dodano komentarz do Issue #{issue_number}\n"
            result += f"URL: {comment.html_url}\n"

            logger.info(f"Dodano komentarz do Issue #{issue_number}")
            return result

        except Exception as e:
            if type(e).__name__ == "GithubException":
                error_msg = f"❌ Błąd GitHub API: {getattr(e, 'status', 'Unknown')} - {getattr(e, 'data', {}).get('message', str(e))}"
                logger.error(error_msg)
                return error_msg

            error_msg = f"❌ Błąd podczas dodawania komentarza: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="send_notification",
        description="Wysyła powiadomienie na Discord lub Slack przez Webhook.",
    )
    async def send_notification(
        self,
        message: Annotated[str, "Treść wiadomości do wysłania"],
        channel: Annotated[str, "Kanał: 'discord' lub 'slack'"] = "discord",
    ) -> str:
        """
        Wysyła powiadomienie przez Webhook.

        Args:
            message: Treść wiadomości
            channel: Typ kanału ('discord' lub 'slack')

        Returns:
            Potwierdzenie lub komunikat błędu
        """
        webhook_url = None

        if channel.lower() == "discord":
            webhook_url = self.discord_webhook
        elif channel.lower() == "slack":
            webhook_url = self.slack_webhook
        else:
            return f"❌ Nieznany kanał: {channel}. Użyj 'discord' lub 'slack'"

        if not webhook_url:
            return f"❌ Webhook URL nie skonfigurowany dla {channel} ({channel.upper()}_WEBHOOK_URL)"

        try:
            # Przygotuj payload w zależności od platformy
            if channel.lower() == "discord":
                payload = {"content": message}
            else:  # slack
                payload = {"text": message}

            # Wyślij request
            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=payload, timeout=10.0)
                response.raise_for_status()

            result = f"✅ Wysłano powiadomienie na {channel}"
            logger.info(result)
            return result

        except httpx.HTTPStatusError as e:
            error_msg = f"❌ Błąd HTTP {e.response.status_code} podczas wysyłania na {channel}: {e.response.text}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = (
                f"❌ Błąd podczas wysyłania powiadomienia na {channel}: {str(e)}"
            )
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="get_configuration_status",
        description="Sprawdza i zwraca raport o dostępnych integracjach platformowych (GitHub, Slack, Discord).",
    )
    def get_configuration_status(self) -> str:
        """
        Sprawdza status konfiguracji platform zewnętrznych.

        Returns:
            Sformatowany raport tekstowy o dostępnych integracjach
        """
        report = "[Konfiguracja PlatformSkill]\n\n"

        # GitHub
        if self.github_token and self.github_repo_name:
            # Sprawdź czy klient jest zainicjalizowany (bez wykonywania zapytania API)
            if self.github_client:
                report += f"- GitHub: ✅ AKTYWNY (repo: {self.github_repo_name})\n"
            else:
                report += (
                    "- GitHub: ⚠️ SKONFIGUROWANY (ale klient nie zainicjalizowany)\n"
                )
        else:
            missing = []
            if not self.github_token:
                missing.append("GITHUB_TOKEN")
            if not self.github_repo_name:
                missing.append("GITHUB_REPO_NAME")
            report += f"- GitHub: ❌ BRAK KONFIGURACJI (brak: {', '.join(missing)})\n"

        # Slack
        if self.slack_webhook:
            report += "- Slack: ✅ AKTYWNY\n"
        else:
            report += "- Slack: ❌ BRAK KLUCZA (SLACK_WEBHOOK_URL)\n"

        # Discord
        if self.discord_webhook:
            report += "- Discord: ✅ AKTYWNY\n"
        else:
            report += "- Discord: ❌ BRAK KLUCZA (DISCORD_WEBHOOK_URL)\n"

        logger.info("Wygenerowano raport konfiguracji PlatformSkill")
        return report

    def check_connection(self) -> dict:
        """
        Sprawdza status połączenia z platformami zewnętrznymi.

        Returns:
            Dict ze statusem każdej platformy
        """
        status: dict[str, dict[str, object]] = {
            "github": {
                "configured": bool(self.github_token and self.github_repo_name),
                "connected": False,
            },
            "discord": {
                "configured": bool(self.discord_webhook),
            },
            "slack": {
                "configured": bool(self.slack_webhook),
            },
        }

        # Sprawdź połączenie z GitHub
        if status["github"]["configured"]:
            try:
                user = self.github_client.get_user()
                user.login  # Trigger API call
                status["github"]["connected"] = True
            except Exception as e:
                logger.error(f"Błąd połączenia z GitHub: {e}")
                status["github"]["error"] = str(e)

        return status
