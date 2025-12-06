"""Moduł: metrics - zbieranie i raportowanie metryk systemowych."""

from datetime import datetime
from typing import Dict

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    """Zbiera metryki wydajności i użycia systemu."""

    def __init__(self):
        """Inicjalizacja collectora metryk."""
        self.metrics: Dict[str, int] = {
            "tasks_created": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "tokens_used_session": 0,
        }
        self.tool_usage: Dict[str, int] = {}
        self.agent_usage: Dict[str, int] = {}
        self.start_time = datetime.now()

    def increment_task_created(self):
        """Inkrementuje licznik utworzonych zadań."""
        self.metrics["tasks_created"] += 1

    def increment_task_completed(self):
        """Inkrementuje licznik ukończonych zadań."""
        self.metrics["tasks_completed"] += 1

    def increment_task_failed(self):
        """Inkrementuje licznik nieudanych zadań."""
        self.metrics["tasks_failed"] += 1

    def add_tokens_used(self, count: int):
        """
        Dodaje użyte tokeny do sumy.

        Args:
            count: Liczba użytych tokenów
        """
        self.metrics["tokens_used_session"] += count

    def increment_tool_usage(self, tool_name: str):
        """
        Inkrementuje licznik użycia narzędzia.

        Args:
            tool_name: Nazwa użytego narzędzia
        """
        if tool_name not in self.tool_usage:
            self.tool_usage[tool_name] = 0
        self.tool_usage[tool_name] += 1

    def increment_agent_usage(self, agent_name: str):
        """
        Inkrementuje licznik użycia agenta.

        Args:
            agent_name: Nazwa użytego agenta
        """
        if agent_name not in self.agent_usage:
            self.agent_usage[agent_name] = 0
        self.agent_usage[agent_name] += 1

    def get_metrics(self) -> dict:
        """
        Zwraca wszystkie metryki.

        Returns:
            Słownik z metrykami
        """
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()

        return {
            "status": "ok",
            "uptime_seconds": round(uptime_seconds, 2),
            "start_time": self.start_time.isoformat(),
            "tasks": {
                "created": self.metrics["tasks_created"],
                "completed": self.metrics["tasks_completed"],
                "failed": self.metrics["tasks_failed"],
                "success_rate": (
                    round(
                        self.metrics["tasks_completed"]
                        / max(1, self.metrics["tasks_created"])
                        * 100,
                        2,
                    )
                    if self.metrics["tasks_created"] > 0
                    else 0
                ),
            },
            "tokens_used_session": self.metrics["tokens_used_session"],
            "tool_usage": self.tool_usage,
            "agent_usage": self.agent_usage,
        }


# Globalna instancja (będzie inicjalizowana w main.py)
metrics_collector = MetricsCollector()
