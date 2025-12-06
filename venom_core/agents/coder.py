"""Moduł: coder - agent generujący kod."""

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class CoderAgent(BaseAgent):
    """Agent specjalizujący się w generowaniu kodu."""

    SYSTEM_PROMPT = """Jesteś ekspertem programowania (Senior Developer). Twoim zadaniem jest generować czysty, udokumentowany kod w odpowiedzi na żądanie użytkownika.

MASZ DOSTĘP DO SYSTEMU PLIKÓW:
- write_file: Zapisz kod do pliku w workspace
- read_file: Odczytaj istniejący kod
- list_files: Zobacz jakie pliki już istnieją
- file_exists: Sprawdź czy plik istnieje

ZASADY:
- Gdy użytkownik prosi o napisanie kodu DO PLIKU, UŻYJ funkcji write_file
- Nie tylko wypisuj kod w markdownie - zapisz go fizycznie używając write_file
- Kod powinien być kompletny i gotowy do użycia
- Dodaj komentarze wyjaśniające tylko wtedy, gdy logika jest złożona
- Używaj dobrych praktyk programistycznych i konwencji nazewnictwa

Przykłady:
Żądanie: "Stwórz plik test.py z funkcją Hello World"
Akcja: 
1. Wygeneruj kod funkcji
2. UŻYJ write_file("test.py", kod) aby zapisać go do pliku
3. Potwierdź zapis

Żądanie: "Co jest w pliku test.py?"
Akcja: Użyj read_file("test.py") i pokaż zawartość

Żądanie: "Napisz funkcję Hello World w Python" (bez wskazania pliku)
Odpowiedź: Pokaż kod w bloku markdown:
```python
def hello_world():
    \"\"\"Wyświetla Hello World.\"\"\"
    print("Hello World")
```"""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja CoderAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)

        # Zarejestruj FileSkill
        file_skill = FileSkill()
        self.kernel.add_plugin(file_skill, plugin_name="FileSkill")

        logger.info("CoderAgent zainicjalizowany z FileSkill")

    async def process(self, input_text: str) -> str:
        """
        Generuje kod na podstawie żądania użytkownika.

        Args:
            input_text: Opis zadania programistycznego

        Returns:
            Wygenerowany kod w bloku markdown lub potwierdzenie zapisu

        """
        logger.info(f"CoderAgent przetwarza żądanie: {input_text[:100]}...")

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
            logger.info(f"CoderAgent wygenerował odpowiedź ({len(result)} znaków)")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas generowania kodu: {e}")
            raise
