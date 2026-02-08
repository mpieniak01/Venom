"""Moduł: memory_service - serwis konsolidacji pamięci."""

import re
from typing import Any, List, Tuple

from semantic_kernel import Kernel
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class MemoryConsolidator:
    """Serwis do konsolidacji pamięci - tworzy podsumowania i lekcje z logów."""

    # Lista wzorców wrażliwych danych do filtrowania
    SENSITIVE_PATTERNS = [
        r"password[:\s=]+\S+",  # password: xxx, password=xxx
        r"api[_\s]?key\s+configured:\s+\S+",  # API key configured: xxx
        r"api[_\s]?key[:\s=]+\S+",  # api_key: xxx, apikey=xxx
        r"token[:\s=]+\S+",  # token: xxx
        r"secret[:\s=]+\S+",  # secret: xxx
        r"\b[A-Za-z0-9]{32,}\b",  # Długie hashe/tokeny (32+ znaków)
    ]

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja MemoryConsolidator.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel do komunikacji z LLM
        """
        self.kernel = kernel
        logger.info("MemoryConsolidator zainicjalizowany")

    def _filter_sensitive_data(self, text: str) -> str:
        """
        Filtruje dane wrażliwe z tekstu przed wysłaniem do LLM.

        Args:
            text: Tekst do filtrowania

        Returns:
            Tekst z zamaskowanymi wrażliwymi danymi
        """
        filtered_text = text
        for pattern in self.SENSITIVE_PATTERNS:
            filtered_text = re.sub(
                pattern, "[FILTERED]", filtered_text, flags=re.IGNORECASE
            )

        return filtered_text

    async def consolidate_daily_logs(self, logs: List[str]) -> dict:
        """
        Konsoliduje dzienne logi/akcje w podsumowanie i lekcje.

        Args:
            logs: Lista logów/akcji z ostatniego okresu

        Returns:
            Dict z kluczami:
            - summary: Podsumowanie tego co zostało zrobione
            - lessons: Lista wyciągniętych lekcji/wniosków
        """
        if not logs:
            logger.warning("Brak logów do konsolidacji")
            return {"summary": "Brak aktywności", "lessons": []}

        logger.info(f"Rozpoczynam konsolidację {len(logs)} logów...")

        # Filtruj dane wrażliwe
        filtered_logs = [self._filter_sensitive_data(log) for log in logs]

        # Połącz logi w jeden tekst
        logs_text = "\n".join(f"- {log}" for log in filtered_logs)

        # Przygotuj prompt dla LLM
        prompt = f"""Przeanalizuj poniższe logi aktywności systemu i:
1. Stwórz krótkie podsumowanie: Co dzisiaj zrobiliśmy?
2. Wyciągnij 3-5 kluczowych lekcji/wniosków (np. "Plik X jest zależny od Y", "Użytkownik preferuje format JSON")

Logi:
{logs_text}

Odpowiedz w formacie:

PODSUMOWANIE:
[Twoje podsumowanie w 2-3 zdaniach]

LEKCJE:
1. [Lekcja 1]
2. [Lekcja 2]
3. [Lekcja 3]
..."""

        # Wywołaj LLM
        try:
            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(
                    role=AuthorRole.USER,
                    content=prompt,
                )
            )

            # Pobierz serwis chat completion
            chat_service: Any = self.kernel.get_service()

            # Wywołaj model
            response = await chat_service.get_chat_message_content(
                chat_history=chat_history, settings=None
            )

            response_text = str(response).strip()

            # Parsuj odpowiedź
            summary, lessons = self._parse_consolidation_response(response_text)

            logger.info(
                f"Konsolidacja zakończona: summary={len(summary)} znaków, lessons={len(lessons)}"
            )

            return {"summary": summary, "lessons": lessons}

        except Exception as e:
            logger.error(f"Błąd podczas konsolidacji logów: {e}")
            # Fallback - prosty mechanizm bez LLM
            return {
                "summary": f"Wykonano {len(logs)} akcji w systemie",
                "lessons": ["Nieudana konsolidacja - brak lekcji"],
            }

    def _parse_consolidation_response(self, response: str) -> Tuple[str, List[str]]:
        """
        Parsuje odpowiedź LLM na podsumowanie i listę lekcji.

        Args:
            response: Tekst odpowiedzi z LLM

        Returns:
            Tuple (summary, lessons)
        """
        summary = ""
        lessons: list[str] = []
        lines = response.split("\n")
        current_section = None

        for raw_line in lines:
            line = raw_line.strip()
            if self._is_summary_header(line):
                current_section = "summary"
                continue
            if self._is_lessons_header(line):
                current_section = "lessons"
                continue
            if current_section == "summary" and line:
                summary += line + " "
                continue
            if current_section == "lessons":
                lesson = self._normalize_lesson_line(line)
                if lesson:
                    lessons.append(lesson)

        summary = summary.strip() or response[:200]
        if not lessons:
            lessons = self._fallback_numbered_lessons(lines)
        return summary, lessons

    def _is_summary_header(self, line: str) -> bool:
        return "PODSUMOWANIE:" in line.upper()

    def _is_lessons_header(self, line: str) -> bool:
        upper = line.upper()
        return "LEKCJE:" in upper or "LESSONS:" in upper

    def _normalize_lesson_line(self, line: str) -> str | None:
        if not line:
            return None
        lesson = re.sub(r"^\d+\.\s*", "", line)
        if not lesson or lesson == "-":
            return None
        return lesson

    def _fallback_numbered_lessons(self, lines: list[str]) -> list[str]:
        lessons: list[str] = []
        for line in lines:
            if not re.match(r"^\d+\.", line.strip()):
                continue
            lesson = re.sub(r"^\d+\.\s*", "", line.strip())
            if lesson:
                lessons.append(lesson)
        return lessons
