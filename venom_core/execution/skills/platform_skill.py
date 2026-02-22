"""Moduł: platform_skill - integracje z platformami zewnętrznymi (GitHub, Discord, Slack)."""

from typing import TYPE_CHECKING, Annotated, Optional, cast

import httpx
from semantic_kernel.functions import kernel_function

if TYPE_CHECKING:
    from github import Github

from venom_core.config import SETTINGS
from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
GITHUB_NOT_CONFIGURED_ERROR = (
    "❌ Błąd: GitHub nie skonfigurowany (brak GITHUB_TOKEN lub GITHUB_REPO_NAME)"
)


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
        self.github_token = self._extract_secret_setting("GITHUB_TOKEN")
        self.github_repo_name = getattr(SETTINGS, "GITHUB_REPO_NAME", None)
        self.discord_webhook = self._extract_secret_setting("DISCORD_WEBHOOK_URL")
        self.slack_webhook = self._extract_secret_setting("SLACK_WEBHOOK_URL")

        # Inicjalizuj klienta GitHub jeśli token dostępny
        self.github_client: Optional["Github"] = self._init_github_client(
            self.github_token
        )

        logger.info("PlatformSkill zainicjalizowany")

    @staticmethod
    def _extract_secret_setting(field_name: str) -> Optional[str]:
        if not hasattr(SETTINGS, field_name):
            return None
        field_value = getattr(SETTINGS, field_name)
        value = (
            field_value.get_secret_value()
            if hasattr(field_value, "get_secret_value")
            else field_value
        )
        if not value:
            return None
        return str(value)

    @staticmethod
    def _mask_token(token: str) -> str:
        if len(token) > 8:
            return token[:4] + "..." + token[-4:]
        return "***"

    def _init_github_client(self, token: Optional[str]) -> Optional["Github"]:
        if not token:
            logger.warning(
                "PlatformSkill: GITHUB_TOKEN nie skonfigurowany - funkcje GitHub niedostępne"
            )
            return None
        try:
            from github import Auth, Github

            github_client = Github(auth=Auth.Token(token))
            logger.info(
                "PlatformSkill: GitHub client zainicjalizowany "
                f"(token: {self._mask_token(token)})"
            )
            return github_client
        except ImportError:
            logger.warning(
                "PlatformSkill: Biblioteka 'PyGithub' nie jest zainstalowana. "
                "Funkcje GitHub niedostępne."
            )
            return None
        except Exception as exc:
            logger.error(f"Błąd inicjalizacji GitHub client: {exc}")
            return None

    def _fetch_issues(self, repo, state: str, assignee: Optional[str]):
        if assignee:
            return repo.get_issues(state=state, assignee=assignee)
        return repo.get_issues(state=state)

    def _issue_to_data(self, issue) -> dict[str, object]:
        return {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "state": issue.state,
            "created_at": issue.created_at.isoformat(),
            "updated_at": issue.updated_at.isoformat(),
            "labels": [label.name for label in issue.labels],
            "assignees": [issue_assignee.login for issue_assignee in issue.assignees],
            "url": issue.html_url,
        }

    def _format_issues(self, issues_list: list[dict[str, object]], state: str) -> str:
        if not issues_list:
            return f"ℹ️ Brak Issues w stanie '{state}'"

        result = f"Znaleziono {len(issues_list)} Issues:\n\n"
        for issue_item in issues_list:
            issue_number = cast(int, issue_item["number"])
            issue_title = cast(str, issue_item["title"])
            issue_state = cast(str, issue_item["state"])
            issue_labels = cast(list[str], issue_item["labels"])
            issue_url = cast(str, issue_item["url"])
            issue_body = cast(str, issue_item["body"])

            result += f"#{issue_number}: {issue_title}\n"
            result += (
                f"  Stan: {issue_state}, Labels: {', '.join(issue_labels) or 'brak'}\n"
            )
            result += f"  URL: {issue_url}\n"
            if issue_body:
                body_preview = (
                    issue_body[:200] + "..." if len(issue_body) > 200 else issue_body
                )
                result += f"  Opis: {body_preview}\n"
            result += "\n"
        return result

    def _format_github_error(self, exc: Exception, context: str) -> str:
        if type(exc).__name__ == "GithubException":
            error_msg = (
                f"❌ Błąd GitHub API: {getattr(exc, 'status', 'Unknown')} - "
                f"{getattr(exc, 'data', {}).get('message', str(exc))}"
            )
            logger.error(error_msg)
            return error_msg

        error_msg = f"❌ Błąd podczas {context}: {str(exc)}"
        logger.error(error_msg)
        return error_msg

    @kernel_function(
        name="get_assigned_issues",
        description="Pobiera Issues przypisane do bota z GitHub (domyślnie otwarte).",
    )
    def get_assigned_issues(
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
            return GITHUB_NOT_CONFIGURED_ERROR

        try:
            repo = self.github_client.get_repo(self.github_repo_name)
            issues_list: list[dict[str, object]] = []
            issues = self._fetch_issues(repo, state, assignee)

            for issue in issues:
                # Pomiń Pull Requesty (GitHub API zwraca PR jako Issues)
                if issue.pull_request:
                    continue
                issues_list.append(self._issue_to_data(issue))

            logger.info(f"Pobrano {len(issues_list)} Issues (state={state})")
            return self._format_issues(issues_list, state)

        except Exception as e:
            return self._format_github_error(e, "pobierania Issues")

    @kernel_function(
        name="get_issue_details",
        description="Pobiera szczegóły konkretnego Issue z GitHub (w tym komentarze).",
    )
    def get_issue_details(
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
            return GITHUB_NOT_CONFIGURED_ERROR

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
                for i, comment_item in enumerate(comments, 1):
                    result += f"{i}. {comment_item['author']} ({comment_item['created_at']}):\n"
                    result += f"{comment_item['body']}\n\n"
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
    def create_pull_request(
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
            return GITHUB_NOT_CONFIGURED_ERROR

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
    def comment_on_issue(
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
            return GITHUB_NOT_CONFIGURED_ERROR

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
            async with TrafficControlledHttpClient(
                provider=f"{channel.lower()}_webhook",
                timeout=10.0,
            ) as client:
                await client.apost(webhook_url, json=payload)

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
        if status["github"]["configured"] and self.github_client is not None:
            try:
                user = self.github_client.get_user()
                user.login  # Trigger API call
                status["github"]["connected"] = True
            except Exception as e:
                logger.error(f"Błąd połączenia z GitHub: {e}")
                status["github"]["error"] = str(e)

        return status
