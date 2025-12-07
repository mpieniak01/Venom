"""Moduł: model_router - inteligentne zarządzanie routingiem modeli."""

import re
from enum import Enum
from typing import Optional

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ComplexityScore(str, Enum):
    """Poziomy złożoności zadań."""

    LOW = "LOW"  # Proste zadania - lokalny model
    MEDIUM = "MEDIUM"  # Średnie zadania - szybki cloud lub mocny local
    HIGH = "HIGH"  # Złożone zadania - premium cloud (GPT-4o, Claude Opus)


class ServiceId(str, Enum):
    """Identyfikatory dostępnych serwisów LLM."""

    LOCAL = "local_llm"  # Lokalny model (Phi-3, Mistral, Llama)
    CLOUD_FAST = "cloud_fast"  # Szybki cloud (GPT-3.5, Gemini Flash)
    CLOUD_HIGH = "cloud_high"  # Premium cloud (GPT-4o, Claude Opus)


class ModelRouter:
    """Router inteligentnie dobierający model do złożoności zadania."""

    # Słowa kluczowe wskazujące na wysoką złożoność
    HIGH_COMPLEXITY_KEYWORDS = [
        "architektura",
        "system",
        "mikroserwisy",
        "zaprojektuj",
        "optymalizuj",
        "refaktoryzuj",
        "złożony",
        "enterprise",
        "skalowalne",
        "bezpieczeństwo",
        "performance",
        "distributed",
    ]

    # Słowa kluczowe wskazujące na średnią złożoność
    MEDIUM_COMPLEXITY_KEYWORDS = [
        "api",
        "baza danych",
        "serwis",
        "aplikacja",
        "integracja",
        "endpoint",
        "model danych",
        "logika biznesowa",
        "algorytm",
        "testy",
    ]

    # Wzorce wskazujące na prostą implementację
    SIMPLE_PATTERNS = [
        r"napisz funkcję.*sumuj",
        r"stwórz.*hello world",
        r"prosty.*skrypt",
        r"dodaj.*komentarz",
        r"wyświetl.*tekst",
        r"print",
        r"console\.log",
    ]

    def __init__(self, enable_routing: bool = True, force_local: bool = False):
        """
        Inicjalizacja Model Router.

        Args:
            enable_routing: Czy włączyć inteligentny routing (domyślnie True)
            force_local: Wymusza użycie tylko modelu lokalnego (domyślnie False)
        """
        self.enable_routing = enable_routing
        self.force_local = force_local
        logger.info(
            f"ModelRouter zainicjalizowany (routing={enable_routing}, force_local={force_local})"
        )

    def assess_complexity(self, task: str) -> ComplexityScore:
        """
        Ocenia złożoność zadania na podstawie heurystyk.

        Args:
            task: Treść zadania do oceny

        Returns:
            Poziom złożoności (LOW/MEDIUM/HIGH)
        """
        if not task:
            return ComplexityScore.LOW

        task_lower = task.lower()

        # Sprawdź wzorce prostych zadań
        for pattern in self.SIMPLE_PATTERNS:
            if re.search(pattern, task_lower):
                logger.debug(f"Wykryto prosty wzorzec: {pattern}")
                return ComplexityScore.LOW

        # Sprawdź słowa kluczowe wysokiej złożoności
        high_complexity_score = sum(
            1 for keyword in self.HIGH_COMPLEXITY_KEYWORDS if keyword in task_lower
        )

        if high_complexity_score >= 2:
            logger.debug(
                f"Wykryto {high_complexity_score} słów kluczowych wysokiej złożoności"
            )
            return ComplexityScore.HIGH

        # Sprawdź słowa kluczowe średniej złożoności
        medium_complexity_score = sum(
            1 for keyword in self.MEDIUM_COMPLEXITY_KEYWORDS if keyword in task_lower
        )

        if medium_complexity_score >= 2:
            logger.debug(
                f"Wykryto {medium_complexity_score} słów kluczowych średniej złożoności"
            )
            return ComplexityScore.MEDIUM

        # Heurystyka oparta na długości zadania
        if len(task) > 500:
            logger.debug(f"Zadanie długie ({len(task)} znaków) - MEDIUM")
            return ComplexityScore.MEDIUM

        if len(task) > 200:
            logger.debug(f"Zadanie średnie ({len(task)} znaków) - MEDIUM")
            return ComplexityScore.MEDIUM

        # Domyślnie - niski poziom złożoności
        logger.debug(f"Zadanie proste ({len(task)} znaków) - LOW")
        return ComplexityScore.LOW

    def select_service(
        self, score: ComplexityScore, override_service: Optional[str] = None
    ) -> ServiceId:
        """
        Wybiera serwis LLM na podstawie oceny złożoności.

        Args:
            score: Ocena złożoności zadania
            override_service: Opcjonalne wymuszenie konkretnego serwisu

        Returns:
            Identyfikator serwisu do użycia
        """
        # Wymuszenie lokalnego modelu (np. dla testów lub oszczędności)
        if self.force_local:
            logger.info("Force local mode aktywny - używam LOCAL")
            return ServiceId.LOCAL

        # Override przez użytkownika
        if override_service:
            try:
                service = ServiceId(override_service)
                logger.info(f"Override service: {service}")
                return service
            except ValueError:
                logger.warning(
                    f"Nieprawidłowy override service: {override_service}, używam domyślnego"
                )

        # Routing wyłączony - domyślnie LOCAL
        if not self.enable_routing:
            logger.debug("Routing wyłączony - używam LOCAL")
            return ServiceId.LOCAL

        # Inteligentny routing
        routing_map = {
            ComplexityScore.LOW: ServiceId.LOCAL,
            ComplexityScore.MEDIUM: ServiceId.CLOUD_FAST,
            ComplexityScore.HIGH: ServiceId.CLOUD_HIGH,
        }

        selected_service = routing_map[score]
        logger.info(f"Routing: {score} -> {selected_service}")
        return selected_service

    def should_use_local(self, task: str) -> bool:
        """
        Uproszczona metoda sprawdzająca czy zadanie powinno użyć lokalnego modelu.

        Args:
            task: Treść zadania

        Returns:
            True jeśli powinien użyć lokalnego modelu, False w przeciwnym razie
        """
        if self.force_local:
            return True

        if not self.enable_routing:
            return True

        score = self.assess_complexity(task)
        service = self.select_service(score)

        return service == ServiceId.LOCAL

    def get_routing_info(self, task: str) -> dict:
        """
        Zwraca pełne informacje o routingu dla zadania.

        Args:
            task: Treść zadania

        Returns:
            Dict z informacjami o routingu
        """
        score = self.assess_complexity(task)
        service = self.select_service(score)

        return {
            "task_length": len(task),
            "complexity": score.value,
            "selected_service": service.value,
            "routing_enabled": self.enable_routing,
            "force_local": self.force_local,
        }
