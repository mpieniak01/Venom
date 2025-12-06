"""Moduł: critic - agent oceniający jakość i bezpieczeństwo kodu."""

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.core.policy_engine import PolicyEngine
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Temperatura dla LLM Krytyka - niska dla konsystencji ocen
CRITIC_TEMPERATURE = 0.3


class CriticAgent(BaseAgent):
    """Agent krytykujący kod - Senior Developer / QA."""

    SYSTEM_PROMPT = """Jesteś ekspertem w zakresie bezpieczeństwa i jakości kodu (Senior Developer / QA Expert). 
Twoim zadaniem jest OCENA kodu, NIE jego pisanie.

TWOJA ROLA:
- Wykrywaj błędy logiczne
- Identyfikuj luki bezpieczeństwa (np. hardcoded credentials, SQL injection)
- Sprawdzaj poprawność typowania
- Weryfikuj obecność dokumentacji (docstringi)
- Oceniaj czytelność i zgodność z best practices

ZASADY OCENY:
1. Jeśli kod jest BEZPIECZNY i DOBREJ JAKOŚCI → odpowiedz: "APPROVED"
2. Jeśli znajdziesz problemy → wylistuj je precyzyjnie w formie:
   - Opis problemu
   - Lokalizacja (numer linii jeśli możliwe)
   - Sugerowana poprawa
   
PRZYKŁADY PROBLEMÓW DO WYKRYCIA:
❌ Hardcoded API keys (np. api_key = "sk-...")
❌ Hasła w kodzie (np. password = "secret123")
❌ Brak obsługi błędów (try/except)
❌ Brak typowania funkcji
❌ Brak docstringów
❌ SQL queries bez parametryzacji
❌ Niebezpieczne komendy shell (rm -rf, eval)

PAMIĘTAJ: Twoim celem jest POMOC programiście, nie krytykowanie. Bądź konstruktywny."""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja CriticAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)
        self.policy_engine = PolicyEngine()
        logger.info("CriticAgent zainicjalizowany z PolicyEngine")

    async def process(self, input_text: str) -> str:
        """
        Ocenia kod pod kątem jakości i bezpieczeństwa.

        Args:
            input_text: Kod do oceny (może zawierać kontekst w formacie: "USER_REQUEST: ... CODE: ...")

        Returns:
            "APPROVED" lub lista poprawek
        """
        logger.info("CriticAgent rozpoczyna ocenę kodu...")

        # Wyciągnij kod z inputu (jeśli zawiera kontekst)
        code_to_review = self._extract_code(input_text)

        # Najpierw sprawdź PolicyEngine (deterministyczne reguły)
        violations = self.policy_engine.check_safety(code_to_review)

        if violations:
            # Natychmiastowe odrzucenie przy naruszeniach critical
            critical_violations = [v for v in violations if v.severity == "critical"]
            if critical_violations:
                logger.warning(
                    f"PolicyEngine wykrył {len(critical_violations)} krytycznych naruszeń"
                )
                return self._format_policy_violations(violations)

        # Jeśli brak krytycznych naruszeń, zapytaj LLM o dodatkową ocenę
        try:
            llm_review = await self._llm_review(input_text)

            # Jeśli PolicyEngine znalazł średnie/niskie naruszenia, dodaj je do raportu
            if violations:
                policy_report = self._format_policy_violations(violations)
                combined_review = f"{policy_report}\n\nDODATKOWE UWAGI LLM:\n{llm_review}"
                return combined_review

            return llm_review

        except Exception as e:
            logger.error(f"Błąd podczas oceny LLM: {e}")
            # Fallback - jeśli LLM zawiedzie, zwróć przynajmniej wyniki PolicyEngine
            if violations:
                return self._format_policy_violations(violations)
            return "APPROVED"  # W ostateczności zaakceptuj

    async def _llm_review(self, input_text: str) -> str:
        """Ocena kodu przez LLM."""
        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
        )
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=input_text)
        )

        chat_service = self.kernel.get_service()
        settings = OpenAIChatPromptExecutionSettings(temperature=CRITIC_TEMPERATURE)

        response = await chat_service.get_chat_message_content(
            chat_history=chat_history, settings=settings
        )

        result = str(response).strip()
        logger.info(f"CriticAgent zakończył ocenę: {result[:100]}...")
        return result

    def _extract_code(self, input_text: str) -> str:
        """
        Wyciąga kod z inputu który może zawierać kontekst.

        Format wejścia może być:
        - Czysty kod
        - "USER_REQUEST: ... CODE: ..."
        """
        if "CODE:" in input_text:
            parts = input_text.split("CODE:", 1)
            return parts[1].strip() if len(parts) > 1 else input_text
        return input_text

    def _format_policy_violations(self, violations) -> str:
        """Formatuje naruszenia PolicyEngine do czytelnej formy."""
        report = "ODRZUCONO - wykryto naruszenia bezpieczeństwa:\n\n"

        for i, violation in enumerate(violations, 1):
            report += f"{i}. [{violation.severity.upper()}] {violation.message}"
            if violation.line_number:
                report += f" (linia {violation.line_number})"
            report += "\n"

        report += "\nPOPRAW powyższe problemy i wygeneruj kod ponownie."
        return report
