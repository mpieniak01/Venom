"""Moduł: coder - agent generujący kod."""

from semantic_kernel import Kernel
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class CoderAgent(BaseAgent):
    """Agent specjalizujący się w generowaniu kodu."""

    SYSTEM_PROMPT = """Jesteś ekspertem programowania (Senior Developer). Twoim zadaniem jest generować czysty, udokumentowany kod w odpowiedzi na żądanie użytkownika.

ZASADY:
- Generuj tylko kod - nie dodawaj zbędnych wyjaśnień
- Kod powinien być otoczony blokiem markdown (```python, ```bash, itp.)
- Kod powinien być kompletny i gotowy do użycia
- Dodaj komentarze wyjaśniające tylko wtedy, gdy logika jest złożona
- Używaj dobrych praktyk programistycznych i konwencji nazewnictwa

Przykłady:
Żądanie: "Napisz funkcję Hello World w Python"
Odpowiedź:
```python
def hello_world():
    \"\"\"Wyświetla Hello World.\"\"\"
    print("Hello World")
```

Żądanie: "Skrypt Bash do listowania plików"
Odpowiedź:
```bash
#!/bin/bash
# Lista wszystkich plików w katalogu
ls -la
```"""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja CoderAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)
        logger.info("CoderAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Generuje kod na podstawie żądania użytkownika.

        Args:
            input_text: Opis zadania programistycznego

        Returns:
            Wygenerowany kod w bloku markdown
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

            # Wywołaj model
            response = await chat_service.get_chat_message_content(
                chat_history=chat_history, settings=None
            )

            result = str(response).strip()
            logger.info(f"CoderAgent wygenerował odpowiedź ({len(result)} znaków)")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas generowania kodu: {e}")
            return f"Błąd podczas generowania kodu: {str(e)}"
