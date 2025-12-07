"""Testy dla AnalystAgent."""

import pytest
from unittest.mock import Mock

from venom_core.agents.analyst import AnalystAgent, TaskMetrics
from venom_core.core.model_router import ComplexityScore, ServiceId


@pytest.fixture
def mock_kernel():
    """Fixture: mock kernela."""
    return Mock()


@pytest.fixture
def analyst_agent(mock_kernel):
    """Fixture: instancja AnalystAgent."""
    return AnalystAgent(kernel=mock_kernel)


class TestAnalystAgent:
    """Testy dla klasy AnalystAgent."""

    def test_initialization(self, analyst_agent):
        """Test inicjalizacji agenta."""
        assert analyst_agent.total_tasks == 0
        assert analyst_agent.successful_tasks == 0
        assert analyst_agent.failed_tasks == 0
        assert analyst_agent.total_cost_usd == 0.0
        assert len(analyst_agent.metrics_history) == 0

    def test_record_task_success(self, analyst_agent):
        """Test rejestracji udanego zadania."""
        metrics = TaskMetrics(
            task_id="task_1",
            complexity=ComplexityScore.LOW,
            selected_service=ServiceId.LOCAL,
            success=True,
            cost_usd=0.0,
            duration_seconds=2.5,
            tokens_used=100,
        )

        analyst_agent.record_task(metrics)

        assert analyst_agent.total_tasks == 1
        assert analyst_agent.successful_tasks == 1
        assert analyst_agent.failed_tasks == 0
        assert analyst_agent.total_tokens == 100

    def test_record_task_failure(self, analyst_agent):
        """Test rejestracji nieudanego zadania."""
        metrics = TaskMetrics(
            task_id="task_1",
            complexity=ComplexityScore.HIGH,
            selected_service=ServiceId.CLOUD_HIGH,
            success=False,
            cost_usd=0.05,
            duration_seconds=5.0,
            tokens_used=500,
        )

        analyst_agent.record_task(metrics)

        assert analyst_agent.total_tasks == 1
        assert analyst_agent.successful_tasks == 0
        assert analyst_agent.failed_tasks == 1
        assert analyst_agent.total_cost_usd == 0.05
        assert analyst_agent.total_tokens == 500

    def test_service_stats_tracking(self, analyst_agent):
        """Test śledzenia statystyk per serwis."""
        # Zadanie lokalne
        metrics1 = TaskMetrics(
            task_id="task_1",
            complexity=ComplexityScore.LOW,
            selected_service=ServiceId.LOCAL,
            success=True,
            cost_usd=0.0,
            duration_seconds=1.0,
            tokens_used=50,
        )
        analyst_agent.record_task(metrics1)

        # Zadanie cloud
        metrics2 = TaskMetrics(
            task_id="task_2",
            complexity=ComplexityScore.HIGH,
            selected_service=ServiceId.CLOUD_HIGH,
            success=True,
            cost_usd=0.10,
            duration_seconds=3.0,
            tokens_used=1000,
        )
        analyst_agent.record_task(metrics2)

        # Sprawdź statystyki
        assert ServiceId.LOCAL.value in analyst_agent.service_stats
        assert ServiceId.CLOUD_HIGH.value in analyst_agent.service_stats

        local_stats = analyst_agent.service_stats[ServiceId.LOCAL.value]
        assert local_stats["tasks_count"] == 1
        assert local_stats["success_count"] == 1
        assert local_stats["total_cost"] == 0.0

        cloud_stats = analyst_agent.service_stats[ServiceId.CLOUD_HIGH.value]
        assert cloud_stats["tasks_count"] == 1
        assert cloud_stats["total_cost"] == 0.10

    def test_analyze_routing_efficiency_no_data(self, analyst_agent):
        """Test analizy efektywności bez danych."""
        analysis = analyst_agent.analyze_routing_efficiency()
        assert "message" in analysis
        assert analysis["message"] == "Brak danych do analizy"

    def test_analyze_routing_efficiency_with_data(self, analyst_agent):
        """Test analizy efektywności z danymi."""
        # Dodaj kilka zadań
        for i in range(3):
            metrics = TaskMetrics(
                task_id=f"task_{i}",
                complexity=ComplexityScore.LOW,
                selected_service=ServiceId.LOCAL,
                success=True,
                cost_usd=0.0,
                duration_seconds=1.0,
                tokens_used=100,
            )
            analyst_agent.record_task(metrics)

        analysis = analyst_agent.analyze_routing_efficiency()

        assert "complexity_analysis" in analysis
        assert ComplexityScore.LOW.value in analysis["complexity_analysis"]

        low_analysis = analysis["complexity_analysis"][ComplexityScore.LOW.value]
        assert low_analysis["tasks_count"] == 3
        assert low_analysis["success_rate"] == 100.0

    def test_detect_overprovisioning(self, analyst_agent):
        """Test wykrywania overprovisioning."""
        # Proste zadania używające drogiego modelu
        for i in range(6):
            metrics = TaskMetrics(
                task_id=f"task_{i}",
                complexity=ComplexityScore.LOW,
                selected_service=ServiceId.CLOUD_HIGH,  # Overprovisioning!
                success=True,
                cost_usd=0.05,
                duration_seconds=2.0,
                tokens_used=500,
            )
            analyst_agent.record_task(metrics)

        analysis = analyst_agent.analyze_routing_efficiency()
        assert analysis["overprovisioned_tasks"] > 5

    def test_detect_underprovisioning(self, analyst_agent):
        """Test wykrywania underprovisioning."""
        # Złożone zadania używające słabego modelu i kończące się niepowodzeniem
        for i in range(4):
            metrics = TaskMetrics(
                task_id=f"task_{i}",
                complexity=ComplexityScore.HIGH,
                selected_service=ServiceId.LOCAL,  # Underprovisioning!
                success=False,  # Niepowodzenie
                cost_usd=0.0,
                duration_seconds=10.0,
                tokens_used=2000,
            )
            analyst_agent.record_task(metrics)

        analysis = analyst_agent.analyze_routing_efficiency()
        assert analysis["underprovisioned_tasks"] > 3

    def test_get_cost_breakdown(self, analyst_agent):
        """Test breakdown kosztów."""
        # Zadanie lokalne
        metrics1 = TaskMetrics(
            task_id="task_1",
            complexity=ComplexityScore.LOW,
            selected_service=ServiceId.LOCAL,
            success=True,
            cost_usd=0.0,
            duration_seconds=1.0,
            tokens_used=100,
        )
        analyst_agent.record_task(metrics1)

        # Zadania cloud
        for i in range(3):
            metrics = TaskMetrics(
                task_id=f"task_cloud_{i}",
                complexity=ComplexityScore.MEDIUM,
                selected_service=ServiceId.CLOUD_FAST,
                success=True,
                cost_usd=0.02,
                duration_seconds=2.0,
                tokens_used=300,
            )
            analyst_agent.record_task(metrics)

        breakdown = analyst_agent.get_cost_breakdown()

        assert ServiceId.LOCAL.value in breakdown
        assert ServiceId.CLOUD_FAST.value in breakdown

        local_breakdown = breakdown[ServiceId.LOCAL.value]
        assert local_breakdown["total_cost_usd"] == 0.0
        assert local_breakdown["tasks_count"] == 1

        cloud_breakdown = breakdown[ServiceId.CLOUD_FAST.value]
        assert cloud_breakdown["tasks_count"] == 3
        assert cloud_breakdown["total_cost_usd"] == 0.06

    def test_generate_recommendations_no_data(self, analyst_agent):
        """Test generowania rekomendacji bez danych."""
        recommendations = analyst_agent.generate_recommendations()
        assert len(recommendations) == 1
        assert "więcej danych" in recommendations[0].lower()

    def test_generate_recommendations_overprovisioning(self, analyst_agent):
        """Test rekomendacji przy overprovisioning."""
        # Dodaj dużo zadań z overprovisioning
        for i in range(10):
            metrics = TaskMetrics(
                task_id=f"task_{i}",
                complexity=ComplexityScore.LOW,
                selected_service=ServiceId.CLOUD_HIGH,
                success=True,
                cost_usd=0.05,
                duration_seconds=2.0,
                tokens_used=500,
            )
            analyst_agent.record_task(metrics)

        recommendations = analyst_agent.generate_recommendations()

        # Powinna być rekomendacja o overprovisioning
        overprovisioning_recs = [
            r for r in recommendations if "overprovisioning" in r.lower()
        ]
        assert len(overprovisioning_recs) > 0

    def test_generate_recommendations_low_success_rate(self, analyst_agent):
        """Test rekomendacji przy niskiej skuteczności."""
        # Dodaj 15 zadań: 5 udanych, 10 nieudanych
        for i in range(5):
            metrics = TaskMetrics(
                task_id=f"task_success_{i}",
                complexity=ComplexityScore.MEDIUM,
                selected_service=ServiceId.CLOUD_FAST,
                success=True,
                cost_usd=0.02,
                duration_seconds=2.0,
                tokens_used=300,
            )
            analyst_agent.record_task(metrics)

        for i in range(10):
            metrics = TaskMetrics(
                task_id=f"task_fail_{i}",
                complexity=ComplexityScore.HIGH,
                selected_service=ServiceId.LOCAL,
                success=False,
                cost_usd=0.0,
                duration_seconds=5.0,
                tokens_used=1000,
            )
            analyst_agent.record_task(metrics)

        recommendations = analyst_agent.generate_recommendations()

        # Powinna być rekomendacja o niskiej skuteczności
        success_rate_recs = [
            r for r in recommendations if "skuteczność" in r.lower()
        ]
        assert len(success_rate_recs) > 0

    def test_get_summary(self, analyst_agent):
        """Test podsumowania metryk."""
        # Dodaj kilka zadań
        for i in range(5):
            metrics = TaskMetrics(
                task_id=f"task_{i}",
                complexity=ComplexityScore.LOW,
                selected_service=ServiceId.LOCAL,
                success=True,
                cost_usd=0.0,
                duration_seconds=1.0,
                tokens_used=100,
            )
            analyst_agent.record_task(metrics)

        summary = analyst_agent.get_summary()

        assert summary["total_tasks"] == 5
        assert summary["successful_tasks"] == 5
        assert summary["failed_tasks"] == 0
        assert summary["success_rate"] == 100.0
        assert summary["total_cost_usd"] == 0.0
        assert summary["total_tokens"] == 500

    @pytest.mark.asyncio
    async def test_process(self, analyst_agent):
        """Test metody process generującej raport."""
        # Dodaj kilka zadań
        for i in range(3):
            metrics = TaskMetrics(
                task_id=f"task_{i}",
                complexity=ComplexityScore.LOW,
                selected_service=ServiceId.LOCAL,
                success=True,
                cost_usd=0.0,
                duration_seconds=1.0,
                tokens_used=100,
            )
            analyst_agent.record_task(metrics)

        result = await analyst_agent.process("Generate report")

        # Raport powinien zawierać kluczowe informacje
        assert "RAPORT ANALITYCZNY" in result
        assert "STATYSTYKI OGÓLNE" in result
        assert "3" in result  # Liczba zadań
