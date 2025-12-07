"""Testy dla ModelRouter."""

import pytest

from venom_core.core.model_router import (
    ComplexityScore,
    ModelRouter,
    ServiceId,
)


class TestModelRouter:
    """Testy dla klasy ModelRouter."""

    def test_initialization(self):
        """Test inicjalizacji routera."""
        router = ModelRouter()
        assert router.enable_routing is True
        assert router.force_local is False

    def test_initialization_with_force_local(self):
        """Test inicjalizacji z wymuszeniem lokalnego modelu."""
        router = ModelRouter(force_local=True)
        assert router.force_local is True

    def test_assess_complexity_low_simple_pattern(self):
        """Test oceny złożoności - prosty wzorzec."""
        router = ModelRouter()
        task = "Napisz funkcję sumującą a+b"
        score = router.assess_complexity(task)
        assert score == ComplexityScore.LOW

    def test_assess_complexity_low_short_task(self):
        """Test oceny złożoności - krótkie zadanie."""
        router = ModelRouter()
        task = "Hello world"
        score = router.assess_complexity(task)
        assert score == ComplexityScore.LOW

    def test_assess_complexity_high_keywords(self):
        """Test oceny złożoności - słowa kluczowe wysokiej złożoności."""
        router = ModelRouter()
        task = "Zaprojektuj architekturę mikroserwisów dla systemu bankowego"
        score = router.assess_complexity(task)
        assert score == ComplexityScore.HIGH

    def test_assess_complexity_medium_keywords(self):
        """Test oceny złożoności - słowa kluczowe średniej złożoności."""
        router = ModelRouter()
        task = "Stwórz REST API z bazą danych do zarządzania użytkownikami i dodaj testy integracyjne"
        score = router.assess_complexity(task)
        assert score == ComplexityScore.MEDIUM

    def test_assess_complexity_medium_length(self):
        """Test oceny złożoności - średnia długość."""
        router = ModelRouter()
        task = "X" * 300  # Zadanie dłuższe niż 200 znaków
        score = router.assess_complexity(task)
        assert score == ComplexityScore.MEDIUM

    def test_select_service_low_complexity(self):
        """Test wyboru serwisu dla niskiej złożoności."""
        router = ModelRouter()
        service = router.select_service(ComplexityScore.LOW)
        assert service == ServiceId.LOCAL

    def test_select_service_medium_complexity(self):
        """Test wyboru serwisu dla średniej złożoności."""
        router = ModelRouter()
        service = router.select_service(ComplexityScore.MEDIUM)
        assert service == ServiceId.CLOUD_FAST

    def test_select_service_high_complexity(self):
        """Test wyboru serwisu dla wysokiej złożoności."""
        router = ModelRouter()
        service = router.select_service(ComplexityScore.HIGH)
        assert service == ServiceId.CLOUD_HIGH

    def test_select_service_force_local(self):
        """Test wymuszenia lokalnego modelu."""
        router = ModelRouter(force_local=True)
        service = router.select_service(ComplexityScore.HIGH)
        assert service == ServiceId.LOCAL

    def test_select_service_with_override(self):
        """Test override serwisu."""
        router = ModelRouter()
        service = router.select_service(
            ComplexityScore.LOW, override_service="cloud_high"
        )
        assert service == ServiceId.CLOUD_HIGH

    def test_should_use_local_simple_task(self):
        """Test czy prosty task używa lokalnego modelu."""
        router = ModelRouter()
        assert router.should_use_local("prosty skrypt") is True

    def test_should_use_local_complex_task(self):
        """Test czy złożony task nie używa lokalnego modelu."""
        router = ModelRouter()
        assert (
            router.should_use_local(
                "Zaprojektuj architekturę systemu mikroserwisów"
            )
            is False
        )

    def test_should_use_local_force_local(self):
        """Test wymuszenia lokalnego modelu."""
        router = ModelRouter(force_local=True)
        assert (
            router.should_use_local(
                "Zaprojektuj architekturę systemu mikroserwisów"
            )
            is True
        )

    def test_get_routing_info(self):
        """Test pobrania informacji o routingu."""
        router = ModelRouter()
        task = "Napisz funkcję sumującą a+b"
        info = router.get_routing_info(task)

        assert "task_length" in info
        assert info["complexity"] == ComplexityScore.LOW.value
        assert info["selected_service"] == ServiceId.LOCAL.value
        assert info["routing_enabled"] is True
        assert info["force_local"] is False

    def test_routing_disabled(self):
        """Test wyłączonego routingu."""
        router = ModelRouter(enable_routing=False)
        service = router.select_service(ComplexityScore.HIGH)
        assert service == ServiceId.LOCAL

    def test_empty_task(self):
        """Test pustego zadania."""
        router = ModelRouter()
        score = router.assess_complexity("")
        assert score == ComplexityScore.LOW
