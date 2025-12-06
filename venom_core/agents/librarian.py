"""Moduł: librarian - agent zarządzający wiedzą o strukturze projektu."""

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class LibrarianAgent(BaseAgent):
    """Agent specjalizujący się w nawigacji po plikach i strukturze projektu."""

    SYSTEM_PROMPT = """Jesteś bibliotekarzem projektu (Librarian). Twoim zadaniem jest zarządzanie wiedzą o strukturze plików w workspace.

TWOJE NARZĘDZIA:
- list_files: Lista plików i katalogów
- file_exists: Sprawdzenie czy plik istnieje
- read_file: Odczyt zawartości pliku

ZASADY:
- Zawsze używaj dostępnych narzędzi do sprawdzania struktury plików
- Odpowiadaj jasno i zwięźle
- Jeśli użytkownik pyta o strukturę, użyj list_files
- Jeśli użytkownik pyta o konkretny plik, użyj file_exists lub read_file
- Wszystkie operacje są ograniczone do workspace - jest to bezpieczne

Przykłady:
Żądanie: "Jakie mam pliki?"
Akcja: Użyj list_files(".") i pokaż wynik

Żądanie: "Czy istnieje plik test.py?"
Akcja: Użyj file_exists("test.py") i odpowiedz

Żądanie: "Co jest w pliku config.json?"
Akcja: Użyj read_file("config.json") i pokaż zawartość"""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja LibrarianAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)

        # Zarejestruj FileSkill
        file_skill = FileSkill()
        self.kernel.add_plugin(file_skill, plugin_name="FileSkill")

        logger.info("LibrarianAgent zainicjalizowany z FileSkill")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza pytania o strukturę plików.

        Args:
            input_text: Pytanie użytkownika

        Returns:
            Odpowiedź z informacjami o plikach
        """
        logger.info(f"LibrarianAgent przetwarza żądanie: {input_text[:100]}...")

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
            chat_service = self.kernel.get_service()

            # Włącz automatyczne wywoływanie funkcji
            settings = OpenAIChatPromptExecutionSettings(
                function_choice_behavior="auto"
            )

            # Wywołaj model z możliwością auto-wywołania funkcji
            response = await chat_service.get_chat_message_content(
                chat_history=chat_history, settings=settings
            )

            result = str(response).strip()
            logger.info(f"LibrarianAgent wygenerował odpowiedź ({len(result)} znaków)")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania przez LibrarianAgent: {e}")
            raise
