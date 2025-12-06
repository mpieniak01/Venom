"""Moduł: chat - agent do rozmów ogólnych."""

from semantic_kernel import Kernel
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ChatAgent(BaseAgent):
    """Agent specjalizujący się w rozmowach ogólnych i odpowiadaniu na pytania."""

    SYSTEM_PROMPT = """Jesteś przyjaznym asystentem AI o imieniu Venom. Odpowiadasz na pytania użytkownika w sposób pomocny, zwięzły i naturalny.

ZASADY:
- Odpowiadaj bezpośrednio na pytanie użytkownika
- Bądź zwięzły ale kompletny
- Używaj naturalnego, przyjaznego języka
- Jeśli użytkownik się wita, odpowiedz uprzejmie
- Jeśli pytanie dotyczy wiedzy, odpowiedz na podstawie swojej wiedzy
- Jeśli nie wiesz odpowiedzi, szczerze to przyznaj

Przykłady:
Pytanie: "Cześć Venom, jak się masz?"
Odpowiedź: "Cześć! Świetnie się mam, dziękuję. Gotowy do pomocy!"

Pytanie: "Jaka jest stolica Francji?"
Odpowiedź: "Stolicą Francji jest Paryż."

Pytanie: "Opowiedz kawał"
Odpowiedź: "Dlaczego programiści wolą ciemny motyw? Bo światło przyciąga błędy! 😄"
"""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja ChatAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)
        logger.info("ChatAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Odpowiada na pytanie lub prowadzi rozmowę z użytkownikiem.

        Args:
            input_text: Pytanie lub wiadomość od użytkownika

        Returns:
            Odpowiedź na pytanie lub wiadomość
        """
        logger.info(f"ChatAgent przetwarza żądanie: {input_text[:100]}...")

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
            logger.info(f"ChatAgent wygenerował odpowiedź ({len(result)} znaków)")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas generowania odpowiedzi: {e}")
            return f"Błąd podczas generowania odpowiedzi: {str(e)}"
