"""Moduł: complexity_skill - umiejętność oceny złożoności zadań."""

import json
import re
from typing import Annotated, List

from venom_core.execution.agent_contracts import tool_function as kernel_function
from venom_core.ops.work_ledger import TaskComplexity
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ComplexitySkill:
    """
    Skill do oceny złożoności zadań technicznych.

    Analizuje zadania pod kątem czasu wykonania, liczby plików,
    integracji i potencjalnych ryzyk.
    """

    # Słowa kluczowe dla wysokiej złożoności
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
        "kubernetes",
        "docker-compose",
        "multi-tenant",
    ]

    # Słowa kluczowe dla średniej złożoności
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
        "middleware",
        "authentication",
        "authorization",
    ]

    # Wzorce prostych zadań
    SIMPLE_PATTERNS = [
        r"napisz funkcję",
        r"stwórz.*hello world",
        r"prosty.*skrypt",
        r"dodaj.*komentarz",
        r"wyświetl.*tekst",
        r"print",
        r"console\.log",
        r"dodaj.*logging",
    ]

    # Ryzyka związane z różnymi wzorcami
    RISK_PATTERNS = {
        "scope_creep": [
            r"wszystkie funkcje",
            r"kompletny",
            r"pełny system",
            r"end-to-end",
        ],
        "external_dependencies": [
            r"zewnętrzne api",
            r"third-party",
            r"integracja z",
            r"połączenie z",
        ],
        "data_complexity": [
            r"migracja",
            r"duże dane",
            r"big data",
            r"baza danych",
            r"schema",
        ],
        "performance_critical": [
            r"optymalizacja",
            r"performance",
            r"wydajność",
            r"scalability",
        ],
    }

    def __init__(self):
        """Inicjalizacja ComplexitySkill."""
        logger.info("ComplexitySkill zainicjalizowany")

    def _append_risk_once(
        self, risks: List[tuple[str, str]], risk_type: str, risk_description: str
    ) -> None:
        if any(
            existing_description == risk_description
            for _, existing_description in risks
        ):
            return
        risks.append((risk_type, risk_description))

    def _collect_pattern_risks(self, desc_lower: str) -> List[tuple[str, str]]:
        risks: List[tuple[str, str]] = []
        for risk_type, patterns in self.RISK_PATTERNS.items():
            for pattern in patterns:
                if not re.search(pattern, desc_lower):
                    continue
                risk_description = self._get_risk_description(risk_type)
                self._append_risk_once(risks, risk_type, risk_description)
                break
        return risks

    @staticmethod
    def _collect_additional_risks(
        description: str, desc_lower: str
    ) -> List[tuple[str, str]]:
        additional_risks: List[tuple[str, str]] = []
        if len(description) > 500:
            additional_risks.append(
                ("complexity", "Bardzo długi opis zadania - możliwe scope creep")
            )
        if "szybko" in desc_lower or "pilne" in desc_lower or "urgent" in desc_lower:
            additional_risks.append(
                ("time_pressure", "Presja czasowa - ryzyko obniżenia jakości")
            )
        if "wszystkie" in desc_lower or "każdy" in desc_lower:
            additional_risks.append(
                ("scope", "Szeroki zakres - możliwe niedoszacowanie")
            )
        return additional_risks

    @staticmethod
    def _build_risk_recommendation(risks_count: int) -> str:
        if risks_count >= 3:
            return "Wysokie ryzyko - rozważ prototyp lub proof-of-concept najpierw."
        if risks_count == 2:
            return (
                "Średnie ryzyko - zaplanuj dodatkowy czas na nieprzewidziane problemy."
            )
        return "Niskie ryzyko - kontynuuj zgodnie z planem."

    @kernel_function(
        name="estimate_time",
        description="Szacuje czas wykonania zadania technicznego w minutach i zwraca JSON.",
    )
    async def estimate_time(
        self,
        description: Annotated[str, "Opis zadania do oszacowania"],
    ) -> str:
        """
        Szacuje czas wykonania zadania.

        Args:
            description: Opis zadania

        Returns:
            Oszacowanie czasu w formacie JSON i tekstowym
        """
        complexity = self._assess_complexity(description)
        time_estimate = self._complexity_to_time(complexity)

        # Dodatkowe czynniki
        multipliers = []

        if "testy" in description.lower() or "test" in description.lower():
            multipliers.append(("Testy wymagane", 1.3))

        if "dokumentacja" in description.lower():
            multipliers.append(("Dokumentacja wymagana", 1.2))

        if "optymalizacja" in description.lower():
            multipliers.append(("Optymalizacja wymagana", 1.5))

        total_time = time_estimate
        for reason, multiplier in multipliers:
            total_time *= multiplier

        # Zwróć JSON na początku dla łatwego parsowania
        # Format: {"estimated_minutes": int, "complexity": str}
        # Zachowana backward compatibility - parser obsługuje też stary format {"minutes": int}
        # ensure_ascii=False zapewnia prawidłowe wyświetlanie polskich znaków
        time_json = json.dumps(
            {"estimated_minutes": int(total_time), "complexity": complexity.value},
            ensure_ascii=False,
        )

        result = f"{time_json}\n\n"
        result += f"Oszacowany czas: {total_time:.0f} minut ({total_time / 60:.1f}h)\n"
        result += f"Złożoność: {complexity.value}\n"
        result += f"Podstawowy czas: {time_estimate:.0f} minut\n"

        if multipliers:
            result += "Czynniki zwiększające:\n"
            for reason, mult in multipliers:
                result += f"  - {reason}: x{mult}\n"

        return result

    @kernel_function(
        name="estimate_complexity",
        description="Ocenia złożoność zadania technicznego (TRIVIAL/LOW/MEDIUM/HIGH/EPIC).",
    )
    async def estimate_complexity(
        self,
        description: Annotated[str, "Opis zadania do oceny"],
    ) -> str:
        """
        Ocenia złożoność zadania.

        Args:
            description: Opis zadania

        Returns:
            Poziom złożoności z uzasadnieniem
        """
        complexity = self._assess_complexity(description)

        # Analiza kluczowych czynników
        factors = []

        # Szukaj słów kluczowych
        desc_lower = description.lower()

        high_keywords_found = [
            kw for kw in self.HIGH_COMPLEXITY_KEYWORDS if kw in desc_lower
        ]
        if high_keywords_found:
            factors.append(f"Wysokiej złożoności: {', '.join(high_keywords_found[:3])}")

        medium_keywords_found = [
            kw for kw in self.MEDIUM_COMPLEXITY_KEYWORDS if kw in desc_lower
        ]
        if medium_keywords_found:
            factors.append(
                f"Średniej złożoności: {', '.join(medium_keywords_found[:3])}"
            )

        # Szacuj liczbę plików
        file_count = self._estimate_file_count(description)
        if file_count > 0:
            factors.append(f"Szacowana liczba plików: {file_count}")

        result = f"Złożoność: {complexity.value}\n"
        result += f"Szacowany czas: {self._complexity_to_time(complexity):.0f} minut\n"

        if factors:
            result += "\nCzynniki:\n"
            for factor in factors:
                result += f"  - {factor}\n"

        return result

    @kernel_function(
        name="suggest_subtasks",
        description="Proponuje podział dużego zadania na mniejsze podzadania.",
    )
    async def suggest_subtasks(
        self,
        description: Annotated[str, "Opis dużego zadania do podziału"],
    ) -> str:
        """
        Sugeruje podział zadania na podzadania.

        Args:
            description: Opis zadania

        Returns:
            Lista sugerowanych podzadań
        """
        complexity = self._assess_complexity(description)

        # Jeśli zadanie jest proste, nie trzeba dzielić
        if complexity in [TaskComplexity.TRIVIAL, TaskComplexity.LOW]:
            return f"Zadanie ma złożoność {complexity.value} - nie wymaga podziału."

        # Proponuj standardowy podział
        subtasks = []

        desc_lower = description.lower()

        # Zawsze zacznij od planowania
        if complexity in [TaskComplexity.HIGH, TaskComplexity.EPIC]:
            subtasks.append("1. Analiza wymagań i projekt architektury (planowanie)")

        # Implementacja
        if "api" in desc_lower or "endpoint" in desc_lower:
            subtasks.append("2. Implementacja warstwy API (endpoints, routing)")

        if "baza" in desc_lower or "database" in desc_lower or "model" in desc_lower:
            subtasks.append("3. Implementacja modeli danych i logiki biznesowej")

        if not any(kw in desc_lower for kw in ["api", "baza", "database"]):
            subtasks.append("2. Implementacja podstawowej funkcjonalności")

        # Integracje
        if "integracja" in desc_lower or "external" in desc_lower:
            subtasks.append("4. Integracja z zewnętrznymi systemami")

        # Testy
        if complexity in [
            TaskComplexity.MEDIUM,
            TaskComplexity.HIGH,
            TaskComplexity.EPIC,
        ]:
            subtasks.append(f"{len(subtasks) + 1}. Testy jednostkowe i integracyjne")

        # Dokumentacja
        if complexity in [TaskComplexity.HIGH, TaskComplexity.EPIC]:
            subtasks.append(f"{len(subtasks) + 1}. Dokumentacja i przykłady użycia")

        result = f"Zadanie '{description[:50]}...' ma złożoność {complexity.value}\n\n"
        result += "Proponowany podział na podzadania:\n\n"
        result += "\n".join(subtasks)

        if complexity == TaskComplexity.EPIC:
            result += "\n\n⚠️ OSTRZEŻENIE: To zadanie typu EPIC - rozważ podział na osobne PR-y."

        return result

    @kernel_function(
        name="flag_risks",
        description="Identyfikuje potencjalne ryzyka w zadaniu technicznym.",
    )
    async def flag_risks(
        self,
        description: Annotated[str, "Opis zadania do analizy ryzyk"],
    ) -> str:
        """
        Identyfikuje ryzyka w zadaniu.

        Args:
            description: Opis zadania

        Returns:
            Lista zidentyfikowanych ryzyk
        """
        desc_lower = description.lower()

        risks = self._collect_pattern_risks(desc_lower)
        risks.extend(self._collect_additional_risks(description, desc_lower))

        # Wynik
        if not risks:
            return "✅ Nie zidentyfikowano znaczących ryzyk."

        result = "⚠️ Zidentyfikowane ryzyka:\n\n"
        for i, (risk_type, description) in enumerate(risks, 1):
            result += f"{i}. [{risk_type.upper()}] {description}\n"

        result += "\n💡 Rekomendacja: "
        result += self._build_risk_recommendation(len(risks))

        return result

    def _assess_complexity(self, description: str) -> TaskComplexity:
        """
        Wewnętrzna metoda oceny złożoności.

        Args:
            description: Opis zadania

        Returns:
            Poziom złożoności
        """
        if not description:
            return TaskComplexity.TRIVIAL

        desc_lower = description.lower()
        desc_len = len(description)

        # Sprawdź proste wzorce
        for pattern in self.SIMPLE_PATTERNS:
            if re.search(pattern, desc_lower):
                return TaskComplexity.TRIVIAL

        # Zlicz słowa kluczowe wysokiej złożoności
        high_count = sum(1 for kw in self.HIGH_COMPLEXITY_KEYWORDS if kw in desc_lower)

        # Zlicz słowa kluczowe średniej złożoności
        medium_count = sum(
            1 for kw in self.MEDIUM_COMPLEXITY_KEYWORDS if kw in desc_lower
        )

        # Szacuj liczbę plików
        file_count = self._estimate_file_count(description)

        # Logika decyzyjna
        if high_count >= 3 or file_count > 30:
            return TaskComplexity.EPIC

        if high_count >= 2 or (high_count >= 1 and file_count > 10):
            return TaskComplexity.HIGH

        if medium_count >= 2 or file_count > 3:
            return TaskComplexity.MEDIUM

        if medium_count >= 1 or file_count > 1 or desc_len > 200:
            return TaskComplexity.LOW

        return TaskComplexity.TRIVIAL

    def _estimate_file_count(self, description: str) -> int:
        """
        Szacuje liczbę plików do modyfikacji.

        Args:
            description: Opis zadania

        Returns:
            Szacowana liczba plików
        """
        desc_lower = description.lower()
        heurystyki = self._collect_file_count_heuristics(desc_lower)

        # Jeśli nic nie dopasowano, ale tekst jest długi
        if not heurystyki:
            return 2 if len(description) > 300 else 1

        # Używamy max zamiast sumy aby uniknąć nadmiernego zawyżania
        return max(heurystyki)

    @staticmethod
    def _collect_file_count_heuristics(desc_lower: str) -> list[int]:
        keyword_groups: tuple[tuple[tuple[str, ...], int], ...] = (
            (("system", "architektura"), 15),
            (("api", "endpoint"), 5),
            (("baza danych", "database"), 3),
            (("testy", "test"), 3),
            (("model",), 2),
            (("service", "serwis"), 4),
            (("ui", "interfejs"), 5),
        )
        heurystyki: list[int] = []
        for keywords, estimate in keyword_groups:
            if any(keyword in desc_lower for keyword in keywords):
                heurystyki.append(estimate)
        return heurystyki

    def _complexity_to_time(self, complexity: TaskComplexity) -> float:
        """
        Konwertuje złożoność na szacowany czas w minutach.

        Args:
            complexity: Poziom złożoności

        Returns:
            Szacowany czas w minutach
        """
        mapping = {
            TaskComplexity.TRIVIAL: 5,
            TaskComplexity.LOW: 15,
            TaskComplexity.MEDIUM: 45,
            TaskComplexity.HIGH: 120,
            TaskComplexity.EPIC: 300,
        }
        return mapping.get(complexity, 30)

    def _get_risk_description(self, risk_type: str) -> str:
        """
        Zwraca opis ryzyka dla danego typu.

        Args:
            risk_type: Typ ryzyka

        Returns:
            Opis ryzyka
        """
        descriptions = {
            "scope_creep": "Ryzyko rozszerzania zakresu prac - zadanie może 'puchnąć'",
            "external_dependencies": "Zależność od zewnętrznych API/systemów - możliwe opóźnienia",
            "data_complexity": "Złożoność związana z danymi - ryzyko problemów z migracją/schematem",
            "performance_critical": "Wymagana optymalizacja wydajności - trudne do oszacowania",
        }
        return descriptions.get(risk_type, "Niezidentyfikowane ryzyko")
