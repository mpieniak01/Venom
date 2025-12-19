"""Moduł: guardian - agent QA odpowiedzialny za jakość kodu."""

from dataclasses import dataclass
from typing import Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.execution.skills.test_skill import TestSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RepairTicket:
    """Ticket naprawczy generowany przez Guardiana."""

    file_path: str  # Plik wymagający naprawy
    line_number: Optional[int]  # Linia z błędem (jeśli znana)
    error_message: str  # Treść błędu
    cause: str  # Przyczyna błędu (analiza Guardiana)
    suggested_action: str  # Co trzeba zrobić


class GuardianAgent(BaseAgent):
    """
    Agent Strażnik (QA Engineer).

    Jego rolą NIE jest pisanie nowego kodu, ale zapewnienie że kod przechodzi testy.
    Analizuje wyniki testów, diagnozuje problemy i tworzy precyzyjne tickety naprawcze.
    """

    SYSTEM_PROMPT = """Jesteś ekspertem QA/DevOps (Guardian - Strażnik Jakości). Twoim zadaniem jest analiza raportów z testów i precyzyjne wskazywanie co wymaga naprawy.

TWOJA ROLA:
- Analizujesz wyniki testów (pytest, linter)
- Diagnozujesz przyczyny błędów z traceback
- Tworzysz precyzyjne Tickety Naprawcze dla Codera

MASZ DOSTĘP DO NARZĘDZI:
- TestSkill: run_pytest, run_linter
- FileSkill: read_file, file_exists, list_files
- GitSkill: get_status, get_diff

ZASADY:
- NIE piszesz nowego kodu - tylko analizujesz i diagnozujesz
- Nie akceptujesz kodu który nie przechodzi testów
- Twoim celem jest "zielony pasek" (wszystkie testy OK)
- Jeśli test NIE przechodzi, musisz:
  1. Zidentyfikować dokładnie który plik i linia
  2. Wyjaśnić DLACZEGO test nie przechodzi
  3. Wskazać CO trzeba naprawić (bez podawania kodu!)

PRZYKŁAD TICKETU NAPRAWCZEGO:
FILE: src/calculator.py
LINE: 15
ERROR: AssertionError: Expected 10, got 0
CAUSE: Funkcja divide() zwraca 0 zamiast wyniku dzielenia
ACTION: Popraw logikę dzielenia - upewnij się że zwracasz a/b zamiast 0

Bądź konkretny i precyzyjny. Coder potrzebuje jasnych instrukcji.
"""

    def __init__(self, kernel: Kernel, test_skill: TestSkill = None):
        """
        Inicjalizacja GuardianAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            test_skill: Instancja TestSkill (jeśli None, zostanie utworzona)
        """
        super().__init__(kernel)

        # Zarejestruj skille
        self.test_skill = test_skill or TestSkill()
        self.file_skill = FileSkill()
        self.git_skill = GitSkill()

        # Zarejestruj skille w kernelu
        self.kernel.add_plugin(self.test_skill, plugin_name="TestSkill")
        self.kernel.add_plugin(self.file_skill, plugin_name="FileSkill")
        self.kernel.add_plugin(self.git_skill, plugin_name="GitSkill")

        # Ustawienia LLM
        self.execution_settings = OpenAIChatPromptExecutionSettings(
            service_id="default",
            max_tokens=2000,
            temperature=0.3,  # Niższa temperatura dla precyzji
            top_p=0.9,
        )

        # Service do chat completion
        self.chat_service = self.kernel.get_service(service_id="default")

        logger.info("GuardianAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza żądanie analizy testów.

        Args:
            input_text: Kontekst zadania (może zawierać wyniki testów lub prośbę o uruchomienie)

        Returns:
            Analiza i ticket naprawczy lub potwierdzenie sukcesu
        """
        try:
            # Przygotuj historię rozmowy
            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
            )
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=input_text)
            )

            logger.info("Guardian rozpoczyna analizę")

            # Wywołaj LLM z dostępem do funkcji
            response = await self._invoke_chat_with_fallbacks(
                chat_service=self.chat_service,
                chat_history=chat_history,
                settings=self.execution_settings,
                enable_functions=True,
            )

            # Wyciągnij wynik
            result = str(response)

            logger.info(f"Guardian zakończył analizę: {len(result)} znaków")

            return result

        except Exception as e:
            error_msg = f"❌ GuardianAgent napotkał błąd: {str(e)}"
            logger.error(error_msg)
            return error_msg

    async def analyze_test_failure(
        self, test_output: str, file_context: dict = None
    ) -> RepairTicket:
        """
        Analizuje wynik testu i tworzy ticket naprawczy.

        Args:
            test_output: Surowy output z pytest
            file_context: Opcjonalny słownik z treścią plików do analizy

        Returns:
            RepairTicket z diagnozą i sugestią naprawy
        """
        try:
            # Przygotuj prompt do analizy
            prompt = f"""Przeanalizuj wynik testu i stwórz PRECYZYJNY ticket naprawczy.

TEST OUTPUT:
{test_output}

"""

            if file_context:
                prompt += "\nKONTEKST PLIKÓW:\n"
                for file_path, content in file_context.items():
                    prompt += f"\n--- {file_path} ---\n{content[:500]}...\n"

            prompt += """
Odpowiedz w formacie:
FILE: <ścieżka do pliku>
LINE: <numer linii lub UNKNOWN>
ERROR: <treść błędu>
CAUSE: <przyczyna błędu>
ACTION: <co trzeba naprawić>
"""

            # Wywołaj analizę
            result = await self.process(prompt)

            if self._is_llm_failure(result):
                logger.warning(
                    "Guardian otrzymał komunikat błędu z LLM, zwracam ticket awaryjny"
                )
                return self._default_ticket(test_output, result)

            # Sparsuj odpowiedź do RepairTicket
            ticket = self._parse_repair_ticket(result)

            if not ticket.cause or not ticket.suggested_action:
                logger.warning(
                    "Guardian otrzymał niekompletną odpowiedź LLM, zwracam ticket awaryjny"
                )
                return self._default_ticket(test_output, "Niekompletna odpowiedź LLM")

            return ticket

        except Exception as e:
            logger.error(f"Błąd podczas analizy testu: {e}")
            # Zwróć domyślny ticket
            return self._default_ticket(test_output, str(e))

    def _parse_repair_ticket(self, llm_response: str) -> RepairTicket:
        """
        Parsuje odpowiedź LLM do struktury RepairTicket.

        Args:
            llm_response: Odpowiedź od LLM

        Returns:
            Obiekt RepairTicket
        """
        # Domyślne wartości
        file_path = "UNKNOWN"
        line_number = None
        error_message = ""
        cause = ""
        suggested_action = ""

        # Parsuj linie
        lines = llm_response.split("\n")
        for line in lines:
            line = line.strip()

            if line.startswith("FILE:"):
                file_path = line.replace("FILE:", "").strip()
            elif line.startswith("LINE:"):
                line_str = line.replace("LINE:", "").strip()
                if line_str.isdigit():
                    line_number = int(line_str)
            elif line.startswith("ERROR:"):
                error_message = line.replace("ERROR:", "").strip()
            elif line.startswith("CAUSE:"):
                cause = line.replace("CAUSE:", "").strip()
            elif line.startswith("ACTION:"):
                suggested_action = line.replace("ACTION:", "").strip()

        return RepairTicket(
            file_path=file_path,
            line_number=line_number,
            error_message=error_message,
            cause=cause,
            suggested_action=suggested_action,
        )

    def _default_ticket(self, test_output: str, error: str) -> RepairTicket:
        """Buduje ticket awaryjny gdy analiza się nie powiodła."""

        return RepairTicket(
            file_path="UNKNOWN",
            line_number=None,
            error_message=test_output[:200],
            cause="Nie udało się przeanalizować",
            suggested_action=f"Sprawdź ręcznie wynik testu. Szczegóły: {error}",
        )

    def _is_llm_failure(self, response: str) -> bool:
        """Sprawdza czy odpowiedź wskazuje na błąd LLM lub brak wyniku."""

        if not response:
            return True

        normalized = response.strip()

        if normalized.startswith("❌"):
            return True

        # Brak sekcji FILE / ACTION oznacza, że odpowiedź jest niepoprawna
        return "FILE:" not in normalized and "ACTION:" not in normalized
