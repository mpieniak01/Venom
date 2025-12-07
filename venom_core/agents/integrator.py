"""Moduł: integrator - agent zarządzający wersjonowaniem i DevOps."""

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class IntegratorAgent(BaseAgent):
    """
    Agent specjalizujący się w zarządzaniu wersjonowaniem i DevOps.
    Odpowiedzialny za operacje Git, tworzenie semantycznych commitów,
    zarządzanie branchami i synchronizację kodu.
    """

    SYSTEM_PROMPT = """Jesteś ekspertem DevOps i Git (Integrator). Twoim zadaniem jest zarządzanie repozytorium Git, tworzenie semantycznych commitów i zapewnienie czystej historii zmian.

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

WORKFLOW:
1. Użytkownik prosi o pracę na nowym branchu -> użyj checkout z create_new=True
2. Po zmianach w kodzie -> sprawdź get_status i get_diff
3. Jeśli są zmiany -> przeanalizuj diff i wygeneruj semantyczną wiadomość commita
4. Stage'uj pliki (add_files) -> commit -> push

BEZPIECZEŃSTWO:
- NIE używaj git push --force (może to nadpisać historię)
- Sprawdź zawsze status przed commitowaniem
- W razie konfliktów merge - zgłoś błąd i poproś człowieka o pomoc

KIEDY DZIAŁAĆ:
- Gdy użytkownik prosi: "Pracuj na branchu X", "Commitnij zmiany", "Synchronizuj kod"
- Gdy Architekt zleca ci zadanie wersjonowania
- Gdy wykryjesz zmiany w workspace, które należy zapisać

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

Żądanie: "Jaki jest aktualny branch?"
Akcja: get_current_branch()"""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja IntegratorAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)

        # Dodaj GitSkill do kernela
        self.git_skill = GitSkill()
        kernel.add_plugin(self.git_skill, plugin_name="git")

        logger.info("IntegratorAgent zainicjalizowany z GitSkill")

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
            chat_service = self.kernel.get_service(type="chat")

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
                function_choice_behavior="auto",  # Automatyczne wywoływanie funkcji
            )

            # Wykonaj request do LLM z włączoną obsługą funkcji
            response = await chat_service.get_chat_message_content(
                chat_history=history,
                settings=settings,
                kernel=self.kernel,
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
            chat_service = self.kernel.get_service(type="chat")

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
            response = await chat_service.get_chat_message_content(
                chat_history=history, settings=settings
            )

            message = str(response).strip()
            logger.info(f"Wygenerowano wiadomość commita: {message}")

            return message

        except Exception as e:
            logger.error(f"Błąd podczas generowania wiadomości commita: {e}")
            return "chore: update code"  # Fallback
