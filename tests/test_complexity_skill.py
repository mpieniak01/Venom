"""Testy dla ComplexitySkill."""

import json

import pytest

from venom_core.execution.skills.complexity_skill import ComplexitySkill
from venom_core.ops.work_ledger import TaskComplexity


class TestComplexitySkill:
    """Testy dla klasy ComplexitySkill."""

    @pytest.fixture
    def skill(self):
        """Instancja ComplexitySkill."""
        return ComplexitySkill()

    @pytest.mark.asyncio
    async def test_estimate_time_simple(self, skill):
        """Test szacowania czasu dla prostego zadania."""
        result = await skill.estimate_time("Napisz funkcję hello world")

        assert "minut" in result.lower()
        assert "TRIVIAL" in result or "LOW" in result

    @pytest.mark.asyncio
    async def test_estimate_time_complex(self, skill):
        """Test szacowania czasu dla złożonego zadania."""
        result = await skill.estimate_time(
            "Zaprojektuj architekturę mikroserwisów z bazami danych i testami"
        )

        assert "minut" in result.lower() or "godzin" in result.lower()
        assert "MEDIUM" in result or "HIGH" in result or "EPIC" in result

    @pytest.mark.asyncio
    async def test_estimate_complexity_trivial(self, skill):
        """Test oceny złożoności - trywialne."""
        result = await skill.estimate_complexity("Napisz funkcję sumującą a+b")

        assert "TRIVIAL" in result or "LOW" in result

    @pytest.mark.asyncio
    async def test_estimate_complexity_medium(self, skill):
        """Test oceny złożoności - średnie."""
        result = await skill.estimate_complexity(
            "Stwórz REST API z bazą danych i testami"
        )

        assert "MEDIUM" in result or "LOW" in result

    @pytest.mark.asyncio
    async def test_estimate_complexity_high(self, skill):
        """Test oceny złożoności - wysokie."""
        result = await skill.estimate_complexity(
            "Zaprojektuj system mikroserwisów z Kubernetes i monitoring"
        )

        assert "HIGH" in result or "EPIC" in result

    @pytest.mark.asyncio
    async def test_suggest_subtasks_simple_no_split(self, skill):
        """Test sugestii podziału - proste zadanie nie wymaga."""
        result = await skill.suggest_subtasks("Dodaj logging")

        assert "nie wymaga podziału" in result.lower()

    @pytest.mark.asyncio
    async def test_suggest_subtasks_complex_with_split(self, skill):
        """Test sugestii podziału - złożone zadanie."""
        result = await skill.suggest_subtasks(
            "Stwórz REST API z bazą danych, integracją zewnętrzną i testami"
        )

        assert "1." in result or "2." in result
        assert "podział" in result.lower() or "podzadania" in result.lower()

    @pytest.mark.asyncio
    async def test_flag_risks_no_risks(self, skill):
        """Test identyfikacji ryzyk - brak ryzyk."""
        result = await skill.flag_risks("Dodaj funkcję pomocniczą")

        assert "nie zidentyfikowano" in result.lower() or "✅" in result

    @pytest.mark.asyncio
    async def test_flag_risks_scope_creep(self, skill):
        """Test identyfikacji ryzyk - scope creep."""
        result = await skill.flag_risks(
            "Zaimplementuj wszystkie funkcje systemu end-to-end"
        )

        assert "⚠️" in result
        assert "scope" in result.lower() or "zakres" in result.lower()

    @pytest.mark.asyncio
    async def test_flag_risks_external_dependencies(self, skill):
        """Test identyfikacji ryzyk - zewnętrzne zależności."""
        result = await skill.flag_risks("Integracja z zewnętrznym API płatności")

        assert "⚠️" in result
        assert "api" in result.lower() or "zewnętrzne" in result.lower()

    def test_assess_complexity_trivial(self, skill):
        """Test wewnętrznej metody oceny - trywialne."""
        complexity = skill._assess_complexity("print hello")

        assert complexity == TaskComplexity.TRIVIAL

    def test_assess_complexity_low(self, skill):
        """Test wewnętrznej metody oceny - niskie."""
        complexity = skill._assess_complexity(
            "Napisz funkcję walidującą email z testami jednostkowymi"
        )

        assert complexity in [TaskComplexity.TRIVIAL, TaskComplexity.LOW]

    def test_assess_complexity_medium(self, skill):
        """Test wewnętrznej metody oceny - średnie."""
        complexity = skill._assess_complexity(
            "Stwórz REST API endpoint do zarządzania użytkownikami"
        )

        assert complexity in [TaskComplexity.LOW, TaskComplexity.MEDIUM]

    def test_assess_complexity_high(self, skill):
        """Test wewnętrznej metody oceny - wysokie."""
        complexity = skill._assess_complexity(
            "Zaprojektuj architekturę mikroserwisów z bazami danych"
        )

        assert complexity in [
            TaskComplexity.MEDIUM,
            TaskComplexity.HIGH,
            TaskComplexity.EPIC,
        ]

    def test_estimate_file_count_simple(self, skill):
        """Test szacowania liczby plików - proste."""
        count = skill._estimate_file_count("Dodaj funkcję")

        assert count == 0 or count <= 2

    def test_estimate_file_count_with_api(self, skill):
        """Test szacowania liczby plików - z API."""
        count = skill._estimate_file_count("Stwórz REST API z endpointami")

        assert count >= 5

    def test_estimate_file_count_with_database(self, skill):
        """Test szacowania liczby plików - z bazą danych."""
        count = skill._estimate_file_count("Dodaj modele bazy danych")

        assert count >= 2

    def test_complexity_to_time(self, skill):
        """Test konwersji złożoności na czas."""
        assert skill._complexity_to_time(TaskComplexity.TRIVIAL) == 5
        assert skill._complexity_to_time(TaskComplexity.LOW) == 15
        assert skill._complexity_to_time(TaskComplexity.MEDIUM) == 45
        assert skill._complexity_to_time(TaskComplexity.HIGH) == 120
        assert skill._complexity_to_time(TaskComplexity.EPIC) == 300

    @pytest.mark.asyncio
    async def test_estimate_time_json_format(self, skill):
        """Test czy estimate_time zwraca poprawny format JSON."""
        result = await skill.estimate_time("Stwórz REST API endpoint")

        # Sprawdź czy pierwsza linia to JSON
        lines = result.strip().split("\n")
        first_line = lines[0].strip()

        # Spróbuj sparsować JSON
        data = json.loads(first_line)

        # Sprawdź czy zawiera wymagane pola
        assert "estimated_minutes" in data
        assert "complexity" in data

        # Sprawdź typy wartości
        assert isinstance(data["estimated_minutes"], int)
        assert isinstance(data["complexity"], str)
        assert data["estimated_minutes"] > 0

    @pytest.mark.asyncio
    async def test_estimate_time_json_with_multipliers(self, skill):
        """Test czy JSON zawiera prawidłowe wartości z mnożnikami."""
        result = await skill.estimate_time("Stwórz REST API z testami i dokumentacją")

        lines = result.strip().split("\n")
        data = json.loads(lines[0].strip())

        # Z testami i dokumentacją czas powinien być większy
        # Podstawowy czas dla MEDIUM to 45 minut, z mnożnikami: 45 * 1.3 * 1.2 = 70.2
        assert data["estimated_minutes"] >= 45
