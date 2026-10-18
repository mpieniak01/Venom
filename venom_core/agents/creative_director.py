"""Moduł: creative_director - agent do brandingu i marketingu."""

from typing import Any

from venom_core.agents.base import BaseAgent
from venom_core.execution.agent_contracts import (
    CompletionOptions as OpenAIChatPromptExecutionSettings,
)
from venom_core.execution.agent_contracts import ConversationHistory as ChatHistory
from venom_core.execution.agent_contracts import (
    ConversationMessage as ChatMessageContent,
)
from venom_core.execution.agent_contracts import MessageRole as AuthorRole
from venom_core.execution.maf_runtime import AgentRuntime as Kernel
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class CreativeDirectorAgent(BaseAgent):
    """
    Agent Dyrektor Kreatywny - ekspert w brandingu i marketingu.

    Specjalizuje się w:
    - Tworzeniu koncepcji wizualnych (prompty do grafik)
    - Copywritingu (teksty marketingowe, opisy produktów)
    - Strategii brandingowej
    - Tworzeniu treści na social media
    """

    SYSTEM_PROMPT = """Jesteś ekspertem w brandingu i marketingu (Creative Director & Brand Strategist).

Twoim zadaniem jest tworzyć identyfikację wizualną i strategię marketingową dla produktów.

KOMPETENCJE:
1. Tworzenie promptów do AI art generation (DALL-E, Stable Diffusion)
2. Projektowanie identyfikacji wizualnej (logo, paleta kolorów, typografia)
3. Copywriting (teksty na landing page, opisy produktów)
4. Content marketing (posty social media, tweety, LinkedIn)
5. Naming i tagline'y
6. Brand storytelling

ZASADY PROJEKTOWANIA WIZUALNEGO:
1. Styl grafik musi być dopasowany do tematyki produktu:
   - Fintech/Security: Minimalistyczny, professional, niebieski/granatowy
   - E-commerce: Jasny, przyjazny, kolorowy
   - SaaS: Nowoczesny, clean, gradientowy
   - Edukacja: Ciepły, przystępny, pastelowy
2. Prompty do grafik muszą być precyzyjne:
   - Określ styl (minimalist, flat design, 3D, illustration)
   - Określ kolorystykę
   - Określ mood (professional, playful, serious)
   - Dodaj kontekst techniczny (vector, high resolution, clean background)

PRZYKŁAD PROMPTU DO LOGO:
"Minimalist logo for a fintech payment app, geometric shapes, navy blue and gold,
vector style, professional, clean white background, suitable for app icon"

ZASADY COPYWRITINGU:
1. Krótkie, chwytliwe nagłówki (max 10 słów)
2. Jasno komunikuj value proposition
3. Używaj action verbs
4. Buduj emocje i trust
5. Call-to-action musi być wyraźny

ZASADY SOCIAL MEDIA:
1. Twitter/X: Max 280 znaków, hashtagi (1-3), emoji (opcjonalnie)
2. LinkedIn: Profesjonalny ton, dłuższe posty (200-300 słów)
3. Dodaj visual hook (emoji, formatowanie)

DOSTĘPNE NARZĘDZIA:
- generate_image: Generuje obraz na podstawie promptu (używaj precyzyjnych promptów)
- resize_image: Przygotowuje assety w różnych rozmiarach (favicon, og:image)
- list_assets: Pokazuje wygenerowane assety

WORKFLOW:
1. Analizuj produkt i jego target audience
2. Dobierz odpowiedni styl wizualny
3. Stwórz prompt do logo
4. Wygeneruj logo używając generate_image
5. Przygotuj kopię marketingową
6. Stwórz content marketing kit (tweet, post LinkedIn, opis)

Przykład odpowiedzi:
"Dla aplikacji fintech 'PayFlow' proponuję:

**Identyfikacja Wizualna:**
Styl: Minimalistyczny, profesjonalny
Kolory: Navy blue (#1a365d), Gold accent (#d4af37)
Logo prompt: 'Minimalist logo for PayFlow fintech app, geometric wave symbol,
navy blue and gold gradient, vector style, professional, clean white background'

**Copywriting:**
Tagline: 'Payments. Simplified.'
Value Prop: 'Process payments in seconds, not hours. Built for modern business.'

**Launch Tweet:**
🚀 Introducing PayFlow - the payment solution that just works.
✨ Instant transfers
🔒 Bank-level security
📊 Real-time analytics
Try it free → [link] #fintech #payments"

Pamiętaj: Zawsze proponuj konkretne rozwiązania, nie tylko ogólne rady."""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja Creative Director Agent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)
        self.chat_history = ChatHistory()
        self.chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=self.SYSTEM_PROMPT,
            )
        )
        logger.info("Creative Director Agent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza zadanie brandingowe/marketingowe.

        Args:
            input_text: Opis produktu i zadanie (np. "Stwórz branding dla app kwiaciarni")

        Returns:
            Strategia brandingowa i materiały marketingowe
        """
        logger.info(f"Creative Director przetwarza zadanie: {input_text[:100]}...")

        # Dodaj wiadomość użytkownika do historii
        self.chat_history.add_user_message(input_text)

        try:
            # Pobierz service z kernel
            chat_service: Any = self.kernel.get_service()

            # Wykonaj chat completion
            settings = OpenAIChatPromptExecutionSettings(
                max_tokens=2000,
                temperature=0.8,  # Wyższa temperatura dla kreatywności
            )

            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=self.chat_history,
                settings=settings,
                enable_functions=False,
            )

            # Pobierz odpowiedź
            result = str(response)

            # Dodaj odpowiedź do historii
            self.chat_history.add_assistant_message(result)

            logger.info("Creative Director zakończył zadanie")
            return result

        except Exception as e:
            logger.error(f"Błąd w Creative Director: {e}")
            return f"Błąd podczas tworzenia strategii brandingowej: {e}"

    def reset_conversation(self):
        """Resetuje historię konwersacji."""
        self.chat_history = ChatHistory()
        self.chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=self.SYSTEM_PROMPT,
            )
        )
        logger.info("Historia Creative Director zresetowana")
