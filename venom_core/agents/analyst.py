"""Moduł: analyst - agent analityczny audytujący wydajność i koszty."""

from datetime import datetime
from typing import Dict, List, Union

from semantic_kernel import Kernel

from venom_core.agents.base import BaseAgent
from venom_core.core.model_router import ComplexityScore, ServiceId
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class TaskMetrics:
    """Metryki pojedynczego zadania."""

    def __init__(
        self,
        task_id: str,
        complexity: ComplexityScore,
        selected_service: Union[ServiceId, str],  # Accept both ServiceId and str
        success: bool,
        cost_usd: float = 0.0,
        duration_seconds: float = 0.0,
        tokens_used: int = 0,
    ):
        """
        Inicjalizacja metryk zadania.

        Args:
            task_id: Identyfikator zadania
            complexity: Ocena złożoności
            selected_service: Wybrany serwis (ServiceId lub string)
            success: Czy zadanie się udało
            cost_usd: Koszt w USD
            duration_seconds: Czas wykonania w sekundach
            tokens_used: Liczba użytych tokenów
        """
        self.task_id = task_id
        self.complexity = complexity
        # Normalize to ServiceId if string provided
        if isinstance(selected_service, str):
            try:
                self.selected_service = ServiceId(selected_service)
            except ValueError:
                # If not a valid ServiceId, keep as string for flexibility
                self.selected_service = selected_service
        else:
            self.selected_service = selected_service
        self.success = success
        self.cost_usd = cost_usd
        self.duration_seconds = duration_seconds
        self.tokens_used = tokens_used
        self.timestamp = datetime.now()


class AnalystAgent(BaseAgent):
    """Agent analityczny - audytor wewnętrzny systemu."""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja Analyst Agent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)

        # Storage dla metryk
        self.metrics_history: List[TaskMetrics] = []

        # Statystyki per serwis
        self.service_stats: Dict[str, dict] = {}

        # Liczniki
        self.total_tasks = 0
        self.successful_tasks = 0
        self.failed_tasks = 0
        self.total_cost_usd = 0.0
        self.total_tokens = 0

        logger.info("AnalystAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza żądanie analizy.

        Args:
            input_text: Treść zapytania analitycznego

        Returns:
            Raport z analizy
        """
        logger.info("AnalystAgent generuje raport analityczny")

        # Generuj raport
        report = self.generate_report()

        return report

    def record_task(self, metrics: TaskMetrics) -> None:
        """
        Rejestruje metryki wykonanego zadania.

        Args:
            metrics: Metryki zadania
        """
        self.metrics_history.append(metrics)

        # Aktualizuj liczniki globalne
        self.total_tasks += 1
        if metrics.success:
            self.successful_tasks += 1
        else:
            self.failed_tasks += 1

        self.total_cost_usd += metrics.cost_usd
        self.total_tokens += metrics.tokens_used

        # Aktualizuj statystyki per serwis
        # Handle both ServiceId enum and string
        if isinstance(metrics.selected_service, ServiceId):
            service_key = metrics.selected_service.value
        else:
            service_key = str(metrics.selected_service)

        if service_key not in self.service_stats:
            self.service_stats[service_key] = {
                "tasks_count": 0,
                "success_count": 0,
                "fail_count": 0,
                "total_cost": 0.0,
                "total_tokens": 0,
                "avg_duration": 0.0,
            }

        stats = self.service_stats[service_key]
        stats["tasks_count"] += 1
        if metrics.success:
            stats["success_count"] += 1
        else:
            stats["fail_count"] += 1
        stats["total_cost"] += metrics.cost_usd
        stats["total_tokens"] += metrics.tokens_used

        # Aktualizuj średni czas (moving average)
        n = stats["tasks_count"]
        stats["avg_duration"] = (
            stats["avg_duration"] * (n - 1) + metrics.duration_seconds
        ) / n

        logger.info(
            f"Zarejestrowano metryki zadania {metrics.task_id}: "
            f"service={service_key}, success={metrics.success}, "
            f"cost=${metrics.cost_usd:.6f}"
        )

    def analyze_routing_efficiency(self) -> dict:
        """
        Analizuje efektywność routingu modeli.

        Returns:
            Dict z analizą efektywności
        """
        if not self.metrics_history:
            return {"message": "Brak danych do analizy"}

        # Analiza per complexity level
        complexity_analysis = {}
        for complexity in ComplexityScore:
            tasks = [
                m for m in self.metrics_history if m.complexity == complexity
            ]

            if not tasks:
                continue

            success_rate = sum(1 for t in tasks if t.success) / len(tasks)
            avg_cost = sum(t.cost_usd for t in tasks) / len(tasks)
            # Handle both ServiceId and string
            services_used = set()
            for t in tasks:
                if isinstance(t.selected_service, ServiceId):
                    services_used.add(t.selected_service.value)
                else:
                    services_used.add(str(t.selected_service))

            complexity_analysis[complexity.value] = {
                "tasks_count": len(tasks),
                "success_rate": round(success_rate * 100, 2),
                "avg_cost_usd": round(avg_cost, 6),
                "services_used": list(services_used),
            }

        # Znajdź przypadki overprovisioning (LOW complexity -> expensive model)
        overprovisioned = [
            m
            for m in self.metrics_history
            if m.complexity == ComplexityScore.LOW
            and (m.selected_service if isinstance(m.selected_service, str) else m.selected_service.value) != ServiceId.LOCAL.value
        ]

        # Znajdź przypadki underprovisioning (HIGH complexity -> LOCAL model failing)
        underprovisioned = [
            m
            for m in self.metrics_history
            if m.complexity == ComplexityScore.HIGH
            and (m.selected_service if isinstance(m.selected_service, str) else m.selected_service.value) == ServiceId.LOCAL.value
            and not m.success
        ]

        return {
            "complexity_analysis": complexity_analysis,
            "overprovisioned_tasks": len(overprovisioned),
            "underprovisioned_tasks": len(underprovisioned),
            "optimization_opportunities": len(overprovisioned),
        }

    def get_cost_breakdown(self) -> dict:
        """
        Zwraca breakdown kosztów per serwis.

        Returns:
            Dict z breakdownem kosztów
        """
        breakdown = {}
        for service, stats in self.service_stats.items():
            cost_per_task = (
                stats["total_cost"] / stats["tasks_count"]
                if stats["tasks_count"] > 0
                else 0
            )

            breakdown[service] = {
                "total_cost_usd": round(stats["total_cost"], 6),
                "tasks_count": stats["tasks_count"],
                "cost_per_task_usd": round(cost_per_task, 6),
                "success_rate": round(
                    stats["success_count"] / stats["tasks_count"] * 100, 2
                )
                if stats["tasks_count"] > 0
                else 0,
            }

        return breakdown

    def generate_recommendations(self) -> List[str]:
        """
        Generuje rekomendacje optymalizacyjne.

        Returns:
            Lista rekomendacji
        """
        recommendations = []

        if not self.metrics_history:
            return ["Zbierz więcej danych przed generowaniem rekomendacji"]

        # Analiza efektywności routingu
        routing_analysis = self.analyze_routing_efficiency()

        # Rekomendacja 1: Overprovisioning
        if routing_analysis.get("overprovisioned_tasks", 0) > 5:
            recommendations.append(
                f"⚠️ Wykryto {routing_analysis['overprovisioned_tasks']} przypadków overprovisioning. "
                "Proste zadania można przekierować do lokalnego modelu."
            )

        # Rekomendacja 2: Underprovisioning
        if routing_analysis.get("underprovisioned_tasks", 0) > 3:
            recommendations.append(
                f"⚠️ Wykryto {routing_analysis['underprovisioned_tasks']} przypadków underprovisioning. "
                "Złożone zadania wymagają mocniejszego modelu."
            )

        # Rekomendacja 3: Success rate
        if self.total_tasks > 10:
            success_rate = self.successful_tasks / self.total_tasks
            if success_rate < 0.8:
                recommendations.append(
                    f"⚠️ Niska skuteczność zadań ({success_rate*100:.1f}%). "
                    "Rozważ dostosowanie kryteriów routingu."
                )

        # Rekomendacja 4: Cost optimization
        if self.total_cost_usd > 1.0:
            local_tasks = self.service_stats.get(ServiceId.LOCAL.value, {}).get(
                "tasks_count", 0
            )
            local_ratio = local_tasks / self.total_tasks if self.total_tasks > 0 else 0

            if local_ratio < 0.5:
                savings_potential = self.total_cost_usd * 0.3
                recommendations.append(
                    f"💰 Tylko {local_ratio*100:.1f}% zadań używa lokalnego modelu. "
                    f"Potencjalne oszczędności: ${savings_potential:.2f}"
                )

        if not recommendations:
            recommendations.append("✅ Routing działa optymalnie, brak rekomendacji")

        return recommendations

    def generate_report(self) -> str:
        """
        Generuje pełny raport analityczny.

        Returns:
            Sformatowany raport tekstowy
        """
        if not self.metrics_history:
            return "📊 RAPORT ANALITYCZNY\n\nBrak danych do wygenerowania raportu."

        # Nagłówek
        report = ["📊 RAPORT ANALITYCZNY VENOM STRATEGIST\n"]
        report.append(f"Data wygenerowania: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Sekcja 1: Statystyki ogólne
        report.append("=" * 60)
        report.append("STATYSTYKI OGÓLNE")
        report.append("=" * 60)
        report.append(f"Łączna liczba zadań: {self.total_tasks}")
        report.append(f"Zadania zakończone sukcesem: {self.successful_tasks}")
        report.append(f"Zadania nieudane: {self.failed_tasks}")
        success_rate = (
            self.successful_tasks / self.total_tasks * 100 if self.total_tasks > 0 else 0
        )
        report.append(f"Skuteczność: {success_rate:.1f}%")
        report.append(f"Łączny koszt: ${self.total_cost_usd:.4f}")
        report.append(f"Łączna liczba tokenów: {self.total_tokens:,}")

        avg_cost = self.total_cost_usd / self.total_tasks if self.total_tasks > 0 else 0
        report.append(f"Średni koszt zadania: ${avg_cost:.4f}\n")

        # Sekcja 2: Breakdown per serwis
        report.append("=" * 60)
        report.append("BREAKDOWN PER SERWIS")
        report.append("=" * 60)

        cost_breakdown = self.get_cost_breakdown()
        for service, stats in cost_breakdown.items():
            report.append(f"\n🔹 {service.upper()}")
            report.append(f"   Liczba zadań: {stats['tasks_count']}")
            report.append(f"   Koszt całkowity: ${stats['total_cost_usd']:.6f}")
            report.append(f"   Koszt per zadanie: ${stats['cost_per_task_usd']:.6f}")
            report.append(f"   Skuteczność: {stats['success_rate']:.1f}%")

        # Sekcja 3: Analiza routingu
        report.append("\n" + "=" * 60)
        report.append("ANALIZA EFEKTYWNOŚCI ROUTINGU")
        report.append("=" * 60)

        routing_analysis = self.analyze_routing_efficiency()
        if "complexity_analysis" in routing_analysis:
            for complexity, data in routing_analysis["complexity_analysis"].items():
                report.append(f"\n📌 {complexity}")
                report.append(f"   Liczba zadań: {data['tasks_count']}")
                report.append(f"   Skuteczność: {data['success_rate']:.1f}%")
                report.append(f"   Średni koszt: ${data['avg_cost_usd']:.6f}")
                report.append(f"   Używane serwisy: {', '.join(data['services_used'])}")

        # Sekcja 4: Rekomendacje
        report.append("\n" + "=" * 60)
        report.append("REKOMENDACJE OPTYMALIZACYJNE")
        report.append("=" * 60)

        recommendations = self.generate_recommendations()
        for i, rec in enumerate(recommendations, 1):
            report.append(f"{i}. {rec}")

        report.append("\n" + "=" * 60)

        return "\n".join(report)

    def get_summary(self) -> dict:
        """
        Zwraca podsumowanie metryk w formie dict.

        Returns:
            Dict z kluczowymi metrykami
        """
        return {
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate": round(
                self.successful_tasks / self.total_tasks * 100, 2
            )
            if self.total_tasks > 0
            else 0,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_tokens": self.total_tokens,
            "services_used": list(self.service_stats.keys()),
        }
