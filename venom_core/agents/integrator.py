"""Moduł: integrator - agent zarządzający wersjonowaniem i DevOps."""

from typing import Any, Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.execution.skills.platform_skill import PlatformSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class IntegratorAgent(BaseAgent):
    """
    Agent specjalizujący się w zarządzaniu wersjonowaniem i DevOps.
    Odpowiedzialny za operacje Git, tworzenie semantycznych commitów,
    zarządzanie branchami i synchronizację kodu.
    """

    SYSTEM_PROMPT = """Jesteś ekspertem DevOps i Release Engineer (Integrator). Twoim zadaniem jest zarządzanie repozytorium Git, tworzenie semantycznych commitów, Pull Requestów oraz integracja z platformami zewnętrznymi (GitHub, Discord).

MASZ DOSTĘP DO GIT:
- init_repo: Inicjalizuj lub klonuj repozytorium
- checkout: Przełącz branch lub utwórz nowy
- get_status: Sprawdź status zmian
- get_diff: Zobacz szczegóły zmian
- add_files: Stage'uj pliki do commita
- commit: Utwórz commit
- push: Wypchnij zmiany do remote
- get_last_commit_log: Zobacz historię commitów
- get_current_branch: Sprawdź aktualny branch

MASZ DOSTĘP DO PLATFORM (GitHub, Discord, Slack):
- get_assigned_issues: Pobierz Issues przypisane do bota
- get_issue_details: Pobierz szczegóły Issue (z komentarzami)
- create_pull_request: Utwórz Pull Request
- comment_on_issue: Dodaj komentarz do Issue
- send_notification: Wyślij powiadomienie na Discord/Slack

ZASADY TWORZENIA COMMITÓW (Conventional Commits):
Format: <typ>(<zakres>): <opis>

Typy:
- feat: Nowa funkcjonalność
- fix: Naprawa błędu
- docs: Zmiany w dokumentacji
- style: Formatowanie, białe znaki (bez zmian w logice)
- refactor: Refaktoryzacja kodu
- test: Dodanie lub poprawka testów
- chore: Zmiany w buildzie, zależnościach

Przykłady:
- "feat(git): add GitSkill implementation"
- "fix(docker): resolve permission denied in habitat"
- "docs(readme): update installation instructions"
- "refactor(auth): simplify login logic"

WORKFLOW GIT:
1. Użytkownik prosi o pracę na nowym branchu -> użyj checkout z create_new=True
2. Po zmianach w kodzie -> sprawdź get_status i get_diff
3. Jeśli są zmiany -> przeanalizuj diff i wygeneruj semantyczną wiadomość commita
4. Stage'uj pliki (add_files) -> commit -> push

WORKFLOW ISSUE-TO-PR:
1. Gdy otrzymasz polecenie sprawdzenia Issues -> użyj get_assigned_issues()
2. Jeśli znajdziesz nowe zadanie -> użyj get_issue_details(issue_number) aby przeczytać pełny kontekst
3. Poproś Architekta o stworzenie planu naprawy (przekaż mu opis Issue)
4. Po zakończeniu pracy (fix zaimplementowany):
   a) Utwórz Pull Request: create_pull_request(branch, title, body)
   b) W body PR dodaj "Closes #123" aby linkować Issue
   c) Dodaj komentarz do Issue: comment_on_issue(issue_number, "Naprawiono w PR #X")
   d) Wyślij powiadomienie: send_notification("🚀 PR #X gotowy do review")

BEZPIECZEŃSTWO:
- NIE używaj git push --force (może to nadpisać historię)
- Sprawdź zawsze status przed commitowaniem
- W razie konfliktów merge - zgłoś błąd i poproś człowieka o pomoc

KIEDY DZIAŁAĆ:
- Gdy użytkownik prosi: "Pracuj na branchu X", "Commitnij zmiany", "Synchronizuj kod"
- Gdy Architekt zleca ci zadanie wersjonowania
- Gdy wykryjesz zmiany w workspace, które należy zapisać
- Gdy otrzymasz polecenie sprawdzenia Issues lub stworzenia PR

Przykłady:
Żądanie: "Utwórz nowy branch feat/csv-support"
Akcja: checkout(branch_name="feat/csv-support", create_new=True)

Żądanie: "Commitnij zmiany"
Akcja:
1. get_status() - sprawdź co się zmieniło
2. get_diff() - zobacz szczegóły
3. Przeanalizuj zmiany i wygeneruj wiadomość w formacie Conventional Commits
4. add_files(["."])
5. commit(message="feat(core): add new feature")
6. push()

Żądanie: "Sprawdź czy są nowe Issues do naprawy"
Akcja:
1. get_assigned_issues(state="open")
2. Dla każdego nowego Issue -> get_issue_details(issue_number)
3. Raportuj znalezione zadania

Żądanie: "Jaki jest aktualny branch?"
Akcja: get_current_branch()"""

    def __init__(self, kernel: Kernel, skill_manager: Optional[Any] = None):
        """
        Inicjalizacja IntegratorAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)
        self.skill_manager = skill_manager

        # Dodaj GitSkill do kernela
        self.git_skill = GitSkill()
        kernel.add_plugin(self.git_skill, plugin_name="git")

        # Dodaj PlatformSkill do kernela
        self.platform_skill = PlatformSkill()
        kernel.add_plugin(self.platform_skill, plugin_name="platform")

        logger.info("IntegratorAgent zainicjalizowany z GitSkill i PlatformSkill")

    async def _invoke_git_tool(
        self, tool_name: str, arguments: Optional[dict[str, Any]] = None
    ) -> str:
        """
        Wywołuje narzędzie Git przez wspólną ścieżkę SkillManager (Etap C),
        a gdy nie jest dostępna - używa legacy GitSkill bezpośrednio.
        """
        payload = arguments or {}
        if self.skill_manager is not None:
            result = await self.skill_manager.invoke_mcp_tool(
                "git",
                tool_name,
                payload,
                is_external=False,
            )
            return str(result)

        method = getattr(self.git_skill, tool_name)
        result = await method(**payload)
        return str(result)

    async def process(self, input_text: str) -> str:
        """
        Przetwarza żądanie związane z operacjami Git i DevOps.

        Args:
            input_text: Treść zadania (żądanie użytkownika lub Architekta)

        Returns:
            Wynik operacji Git/DevOps
        """
        try:
            logger.info(f"IntegratorAgent przetwarza żądanie: {input_text[:100]}...")

            # Utwórz chat service
            chat_service: Any = self.kernel.get_service(service_id="chat")

            # Utwórz historię czatu
            history = ChatHistory()
            history.add_message(
                ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
            )
            history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=input_text)
            )

            # Ustaw opcje wykonania
            settings = OpenAIChatPromptExecutionSettings(
                temperature=0.3,  # Niska temperatura - precyzyjne operacje Git
                max_tokens=2000,
                function_choice_behavior=FunctionChoiceBehavior.Auto(),  # Automatyczne wywoływanie funkcji
            )

            # Wykonaj request do LLM z włączoną obsługą funkcji
            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=history,
                settings=settings,
                enable_functions=True,
            )

            result = str(response)
            logger.info("IntegratorAgent zakończył przetwarzanie")

            return result

        except Exception as e:
            error_msg = f"❌ Błąd w IntegratorAgent: {str(e)}"
            logger.error(error_msg)
            return error_msg

    async def generate_commit_message(self, diff: str) -> str:
        """
        Generuje semantyczną wiadomość commita na podstawie diff.

        Args:
            diff: Różnice w kodzie (output z git diff)

        Returns:
            Wiadomość commita w formacie Conventional Commits
        """
        try:
            logger.info("Generowanie semantycznej wiadomości commita...")

            prompt = f"""Przeanalizuj poniższe zmiany w kodzie i wygeneruj TYLKO wiadomość commita w formacie Conventional Commits.

ZMIANY:
{diff[:2000]}

FORMAT: <typ>(<zakres>): <opis>

Wygeneruj TYLKO samą wiadomość commita, bez dodatkowych wyjaśnień.
Przykład: "feat(git): add GitSkill implementation"
"""

            # Utwórz chat service
            chat_service: Any = self.kernel.get_service(service_id="chat")

            # Utwórz historię czatu
            history = ChatHistory()
            history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=prompt)
            )

            # Ustaw opcje wykonania
            settings = OpenAIChatPromptExecutionSettings(
                temperature=0.3,
                max_tokens=100,
            )

            # Wykonaj request
            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=history,
                settings=settings,
                enable_functions=False,
            )

            message = str(response).strip()
            logger.info(f"Wygenerowano wiadomość commita: {message}")

            return message

        except Exception as e:
            logger.error(f"Błąd podczas generowania wiadomości commita: {e}")
            return "chore: update code"  # Fallback

    async def poll_issues(self) -> list:
        """
        Pobiera nowe otwarte Issues z GitHub.

        Returns:
            Lista dict z danymi Issues (lub pusta lista jeśli błąd/brak Issues)
        """
        try:
            logger.info("Sprawdzanie nowych Issues na GitHub...")

            # Pobierz otwarte Issues
            result = await self.platform_skill.get_assigned_issues(state="open")

            if result.startswith("❌"):
                logger.warning(f"Nie można pobrać Issues: {result}")
                return []

            if result.startswith("ℹ️"):
                logger.info("Brak nowych Issues")
                return []

            issues = self._parse_issues_output(result)
            logger.info(f"Znaleziono Issues:\n{result}")
            return issues

        except Exception as e:
            logger.error(f"Błąd podczas pollowania Issues: {e}")
            return []

    def _parse_issues_output(self, raw_output: str) -> list:
        """Konwertuje tekstową odpowiedź PlatformSkill na listę opisów Issues."""

        issues: list[str] = []
        if not raw_output:
            return issues

        for line in raw_output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            # Pomijamy nagłówki/narrację
            if stripped.lower().startswith("znaleziono") or stripped.startswith("ℹ️"):
                continue

            if stripped.startswith("#") or stripped[0].isdigit():
                issues.append(stripped)

        return issues

    async def handle_issue(self, issue_number: int) -> str:
        """
        Obsługuje konkretne Issue: pobiera szczegóły, tworzy branch, deleguje do Architekta.

        Args:
            issue_number: Numer Issue do obsłużenia
        Returns:
            Status obsługi Issue
        """
        try:
            logger.info(f"Rozpoczynam obsługę Issue #{issue_number}")

            # 1. Pobierz szczegóły Issue
            issue_details = await self.platform_skill.get_issue_details(issue_number)

            if issue_details.startswith("❌"):
                return f"❌ Nie można pobrać Issue #{issue_number}: {issue_details}"

            logger.info(f"Szczegóły Issue #{issue_number}:\n{issue_details}")

            # 2. Utwórz branch dla Issue
            branch_name = f"issue-{issue_number}"
            checkout_result = await self._invoke_git_tool(
                "checkout",
                {"branch_name": branch_name, "create_new": True},
            )
            logger.info(f"Branch utworzony: {checkout_result}")

            # 3. Zwróć szczegóły Issue aby Orchestrator mógł przekazać do Architekta
            return f"✅ Issue #{issue_number} gotowe do przetworzenia na branchu {branch_name}\n\n{issue_details}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas obsługi Issue #{issue_number}: {str(e)}"
            logger.error(error_msg)
            return error_msg

    async def finalize_issue(
        self, issue_number: int, branch_name: str, pr_title: str, pr_body: str
    ) -> str:
        """
        Finalizuje obsługę Issue: tworzy PR, komentuje Issue, wysyła powiadomienie.

        Args:
            issue_number: Numer Issue
            branch_name: Nazwa brancha z poprawką
            pr_title: Tytuł Pull Requesta
            pr_body: Opis Pull Requesta

        Returns:
            Status finalizacji
        """
        try:
            logger.info(f"Finalizacja Issue #{issue_number}")

            # 1. Upewnij się że zmiany są spushowane
            push_result = await self._invoke_git_tool("push")
            logger.info(f"Push: {push_result}")

            # 2. Utwórz Pull Request
            pr_body_with_link = f"{pr_body}\n\nCloses #{issue_number}"
            pr_result = await self.platform_skill.create_pull_request(
                branch=branch_name,
                title=pr_title,
                body=pr_body_with_link,
                base="main",
            )

            if pr_result.startswith("❌"):
                return f"❌ Nie można utworzyć PR: {pr_result}"

            logger.info(f"PR utworzony: {pr_result}")

            # 3. Dodaj komentarz do Issue
            comment_text = f"🤖 Automatyczna naprawa utworzona.\n\n{pr_result}"
            comment_result = await self.platform_skill.comment_on_issue(
                issue_number=issue_number,
                text=comment_text,
            )
            logger.info(f"Komentarz dodany: {comment_result}")

            # 4. Wyślij powiadomienie na Discord (jeśli skonfigurowane)
            notification_msg = f"🚀 Pull Request gotowy do review: {pr_title}\n\nIssue: #{issue_number}\nBranch: {branch_name}"
            notification_result = await self.platform_skill.send_notification(
                message=notification_msg,
                channel="discord",
            )
            logger.info(f"Powiadomienie: {notification_result}")

            return f"✅ Issue #{issue_number} sfinalizowane:\n{pr_result}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas finalizacji Issue #{issue_number}: {str(e)}"
            logger.error(error_msg)
            return error_msg
