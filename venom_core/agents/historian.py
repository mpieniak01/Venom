"""Moduł: historian - Agent Historyk (Risk Management & Causality Analysis)."""

from typing import Optional

from semantic_kernel import Kernel

from venom_core.agents.base import BaseAgent
from venom_core.core.chronos import ChronosEngine
from venom_core.memory.lessons_store import Lesson, LessonsStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class HistorianAgent(BaseAgent):
    """
    Agent Historyk - zarządza ryzykiem i przyczynowością.

    Odpowiedzialności:
    - Ocena ryzyka przed wykonaniem operacji
    - Rekomendacja tworzenia checkpointów
    - Analiza błędów i aktualizacja LessonsStore
    - Zarządzanie historią zmian
    """

    def __init__(
        self,
        kernel: Kernel,
        chronos_engine: Optional[ChronosEngine] = None,
        lessons_store: Optional[LessonsStore] = None,
    ):
        """
        Inicjalizacja HistorianAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            chronos_engine: Silnik zarządzania czasem
            lessons_store: Magazyn lekcji
        """
        super().__init__(kernel)
        self.chronos = chronos_engine or ChronosEngine()
        self.lessons_store = lessons_store or LessonsStore()

        logger.info("HistorianAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza wejście i zwraca wynik.

        Args:
            input_text: Treść zadania do przetworzenia

        Returns:
            Wynik analizy ryzyka i rekomendacje
        """
        logger.info(f"Historyk analizuje: {input_text[:100]}...")

        try:
            # Ocena ryzyka operacji
            risk_assessment = await self._assess_risk(input_text)

            # Jeśli operacja jest ryzykowna, rekomenduj checkpoint
            if risk_assessment["risk_level"] in ["high", "critical"]:
                checkpoint_recommendation = (
                    f"⚠️ REKOMENDACJA: Utwórz checkpoint przed wykonaniem tej operacji.\n"
                    f"Powód: {risk_assessment['reason']}\n"
                    f"Poziom ryzyka: {risk_assessment['risk_level']}"
                )
                return checkpoint_recommendation

            return (
                f"✓ Operacja ma niskie ryzyko ({risk_assessment['risk_level']}). "
                f"Checkpoint opcjonalny."
            )

        except Exception as e:
            logger.error(f"Błąd w HistorianAgent: {e}")
            return f"Błąd podczas analizy ryzyka: {e}"

    async def _assess_risk(self, operation_description: str) -> dict:
        """
        Ocenia ryzyko operacji na podstawie jej opisu.

        Args:
            operation_description: Opis operacji do wykonania

        Returns:
            Słownik z oceną ryzyka (risk_level, reason)
        """
        # Słowa kluczowe wskazujące na wysokie ryzyko
        high_risk_keywords = [
            "hot_patch",
            "delete",
            "remove",
            "refactor",
            "migration",
            "restructure",
            "drop table",
            "truncate",
            "format",
        ]

        medium_risk_keywords = [
            "modify",
            "update",
            "change",
            "edit",
            "replace",
            "transform",
        ]

        operation_lower = operation_description.lower()

        # Sprawdź poziom ryzyka
        for keyword in high_risk_keywords:
            if keyword in operation_lower:
                return {
                    "risk_level": "high",
                    "reason": f"Operacja zawiera ryzykowną akcję: '{keyword}'",
                }

        for keyword in medium_risk_keywords:
            if keyword in operation_lower:
                return {
                    "risk_level": "medium",
                    "reason": f"Operacja modyfikuje stan: '{keyword}'",
                }

        return {
            "risk_level": "low",
            "reason": "Operacja tylko do odczytu lub bezpieczna",
        }

    async def analyze_failure(
        self, operation: str, error: str, checkpoint_before: Optional[str] = None
    ) -> None:
        """
        Analizuje błąd i zapisuje lekcję w LessonsStore.

        Args:
            operation: Opis operacji, która się nie powiodła
            error: Komunikat błędu
            checkpoint_before: ID checkpointu przed operacją (jeśli był utworzony)
        """
        logger.info(f"Historyk analizuje błąd: {error[:100]}...")

        try:
            # Zapisz lekcję
            lesson = Lesson(
                situation=f"Operacja: {operation}",
                action="Wykonano operację bez wystarczającej walidacji",
                result=f"BŁĄD: {error}",
                feedback=(
                    f"W przyszłości należy {'przywrócić checkpoint ' + checkpoint_before if checkpoint_before else 'utworzyć checkpoint przed podobnymi operacjami'}. "
                    "Rozważ dodatkową walidację przed wykonaniem."
                ),
                tags=["error", "checkpoint", "risk_management"],
                metadata={
                    "checkpoint_id": checkpoint_before,
                    "error_type": type(error).__name__ if isinstance(error, Exception) else "unknown",
                },
            )

            self.lessons_store.add_lesson(lesson)
            logger.info(f"Lekcja zapisana w LessonsStore: {lesson.lesson_id}")

        except Exception as e:
            logger.error(f"Błąd podczas zapisywania lekcji: {e}")

    def recommend_checkpoint(self, operation_name: str) -> bool:
        """
        Sprawdza, czy dla danej operacji powinien być utworzony checkpoint.

        Args:
            operation_name: Nazwa operacji (np. "hot_patch", "migration")

        Returns:
            True jeśli checkpoint jest rekomendowany
        """
        risky_operations = [
            "hot_patch",
            "migration",
            "major_refactor",
            "schema_change",
            "deployment",
        ]

        return operation_name.lower() in risky_operations

    def create_safety_checkpoint(self, name: str, description: str = "") -> Optional[str]:
        """
        Tworzy checkpoint bezpieczeństwa przed ryzykowną operacją.

        Args:
            name: Nazwa checkpointu
            description: Opis checkpointu

        Returns:
            ID utworzonego checkpointu lub None w przypadku błędu
        """
        try:
            checkpoint_id = self.chronos.create_checkpoint(
                name=f"safety_{name}",
                description=f"Checkpoint bezpieczeństwa: {description}",
            )
            logger.info(f"Utworzono checkpoint bezpieczeństwa: {checkpoint_id}")
            return checkpoint_id
        except Exception as e:
            logger.error(f"Nie udało się utworzyć checkpointu bezpieczeństwa: {e}")
            return None

    def get_checkpoint_history(self, limit: int = 10) -> list:
        """
        Pobiera historię ostatnich checkpointów.

        Args:
            limit: Maksymalna liczba checkpointów do pobrania

        Returns:
            Lista ostatnich checkpointów
        """
        try:
            checkpoints = self.chronos.list_checkpoints()
            return checkpoints[:limit]
        except Exception as e:
            logger.error(f"Błąd podczas pobierania historii checkpointów: {e}")
            return []
