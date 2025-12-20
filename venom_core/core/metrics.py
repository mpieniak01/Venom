"""Moduł: metrics - zbieranie i raportowanie metryk systemowych."""

import threading
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
            "llm_only_requests": 0,
            "tool_required_requests": 0,
            "learning_logged": 0,
            "feedback_up": 0,
            "feedback_down": 0,
            "tokens_used_session": 0,
            "network_bytes_sent": 0,
            "network_bytes_received": 0,
            "network_connections_active": 0,
        }
        self.tool_usage: Dict[str, int] = {}
        self.agent_usage: Dict[str, int] = {}
        self.start_time = datetime.now()
        self._lock = threading.Lock()

    def increment_task_created(self):
        """Inkrementuje licznik utworzonych zadań."""
        with self._lock:
            self.metrics["tasks_created"] += 1

    def increment_task_completed(self):
        """Inkrementuje licznik ukończonych zadań."""
        with self._lock:
            self.metrics["tasks_completed"] += 1

    def increment_task_failed(self):
        """Inkrementuje licznik nieudanych zadań."""
        with self._lock:
            self.metrics["tasks_failed"] += 1

    def add_tokens_used(self, count: int):
        """
        Dodaje użyte tokeny do sumy.

        Args:
            count: Liczba użytych tokenów
        """
        with self._lock:
            self.metrics["tokens_used_session"] += count

    def increment_llm_only_request(self):
        """Inkrementuje licznik requestów obsłużonych bez tooli."""
        with self._lock:
            self.metrics["llm_only_requests"] += 1

    def increment_tool_required_request(self):
        """Inkrementuje licznik requestów wymagających toola."""
        with self._lock:
            self.metrics["tool_required_requests"] += 1

    def increment_learning_logged(self):
        """Inkrementuje licznik zapisów procesu nauki."""
        with self._lock:
            self.metrics["learning_logged"] += 1

    def increment_feedback_up(self):
        """Inkrementuje licznik pozytywnego feedbacku."""
        with self._lock:
            self.metrics["feedback_up"] += 1

    def increment_feedback_down(self):
        """Inkrementuje licznik negatywnego feedbacku."""
        with self._lock:
            self.metrics["feedback_down"] += 1

    def increment_tool_usage(self, tool_name: str):
        """
        Inkrementuje licznik użycia narzędzia.

        Args:
            tool_name: Nazwa użytego narzędzia
        """
        with self._lock:
            if tool_name not in self.tool_usage:
                self.tool_usage[tool_name] = 0
            self.tool_usage[tool_name] += 1

    def increment_agent_usage(self, agent_name: str):
        """
        Inkrementuje licznik użycia agenta.

        Args:
            agent_name: Nazwa użytego agenta
        """
        with self._lock:
            if agent_name not in self.agent_usage:
                self.agent_usage[agent_name] = 0
            self.agent_usage[agent_name] += 1

    def add_network_bytes_sent(self, bytes_count: int):
        """
        Dodaje wysłane bajty do sumy.

        Args:
            bytes_count: Liczba wysłanych bajtów

        Note:
            Ta metoda musi być wywołana przez kod obsługujący połączenia sieciowe
            (np. w aiohttp middleware lub HTTP client wrapper) aby metryki były
            faktycznie zliczane. Obecnie metryka jest dostępna w API ale wymaga
            instrumentacji kodu sieciowego.
        """
        with self._lock:
            self.metrics["network_bytes_sent"] += bytes_count

    def add_network_bytes_received(self, bytes_count: int):
        """
        Dodaje odebrane bajty do sumy.

        Args:
            bytes_count: Liczba odebranych bajtów

        Note:
            Ta metoda musi być wywołana przez kod obsługujący połączenia sieciowe
            (np. w aiohttp middleware lub HTTP client wrapper) aby metryki były
            faktycznie zliczane. Obecnie metryka jest dostępna w API ale wymaga
            instrumentacji kodu sieciowego.
        """
        with self._lock:
            self.metrics["network_bytes_received"] += bytes_count

    def set_network_connections_active(self, count: int):
        """
        Ustawia liczbę aktywnych połączeń sieciowych.

        Args:
            count: Liczba aktywnych połączeń
        """
        with self._lock:
            self.metrics["network_connections_active"] = count

    def _calculate_success_rate(self) -> float:
        """
        Oblicza wskaźnik sukcesu zadań.

        Returns:
            Wskaźnik sukcesu w procentach (0-100)
        """
        if self.metrics["tasks_created"] == 0:
            return 0.0

        completed = self.metrics["tasks_completed"]
        created = self.metrics["tasks_created"]
        success_rate = (completed / created) * 100
        return round(success_rate, 2)

    def get_metrics(self) -> dict:
        """
        Zwraca wszystkie metryki.

        Returns:
            Słownik z metrykami
        """
        with self._lock:
            uptime_seconds = (datetime.now() - self.start_time).total_seconds()

            return {
                "status": "ok",
                "uptime_seconds": round(uptime_seconds, 2),
                "start_time": self.start_time.isoformat(),
                "tasks": {
                    "created": self.metrics["tasks_created"],
                    "completed": self.metrics["tasks_completed"],
                    "failed": self.metrics["tasks_failed"],
                    "success_rate": self._calculate_success_rate(),
                },
                "routing": {
                    "llm_only": self.metrics["llm_only_requests"],
                    "tool_required": self.metrics["tool_required_requests"],
                    "learning_logged": self.metrics["learning_logged"],
                },
                "feedback": {
                    "up": self.metrics["feedback_up"],
                    "down": self.metrics["feedback_down"],
                },
                "tokens_used_session": self.metrics["tokens_used_session"],
                "network": {
                    "bytes_sent": self.metrics["network_bytes_sent"],
                    "bytes_received": self.metrics["network_bytes_received"],
                    "connections_active": self.metrics["network_connections_active"],
                    "total_bytes": self.metrics["network_bytes_sent"]
                    + self.metrics["network_bytes_received"],
                },
                "tool_usage": self.tool_usage.copy(),
                "agent_usage": self.agent_usage.copy(),
            }


# Globalna instancja - inicjalizowana w main.py podczas startu aplikacji
metrics_collector = None


def init_metrics_collector():
    """Inicjalizuje globalny collector metryk. Wywołać w hooku FastAPI startup."""
    global metrics_collector
    metrics_collector = MetricsCollector()
    logger.info("MetricsCollector initialized")
