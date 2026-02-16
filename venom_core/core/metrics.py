"""Moduł: metrics - zbieranie i raportowanie metryk systemowych."""

import threading
from datetime import datetime
from math import ceil, floor
from typing import Dict, List, Optional

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
            "model_params_updates": 0,
            "network_bytes_sent": 0,
            "network_bytes_received": 0,
            "network_connections_active": 0,
            "llm_first_token_ms_total": 0,
            "llm_first_token_samples": 0,
            "policy_blocked_count": 0,
            "ollama_load_duration_ms_total": 0,
            "ollama_prompt_eval_count_total": 0,
            "ollama_eval_count_total": 0,
            "ollama_prompt_eval_duration_ms_total": 0,
            "ollama_eval_duration_ms_total": 0,
            "ollama_runtime_samples": 0,
        }
        self.tool_usage: Dict[str, int] = {}
        self.agent_usage: Dict[str, int] = {}
        self.start_time = datetime.now()
        # Reentrant lock prevents self-deadlocks in methods that call other
        # synchronized helpers (e.g. get_all_provider_metrics -> get_provider_metrics).
        self._lock = threading.RLock()

        # Provider observability metrics
        self.provider_metrics: Dict[
            str, Dict[str, any]
        ] = {}  # provider -> metrics dict

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

    def increment_model_params_update(self):
        """Inkrementuje licznik zmian parametrów generacji."""
        with self._lock:
            self.metrics["model_params_updates"] += 1

    def add_llm_first_token_sample(self, elapsed_ms: int):
        """Dodaje próbkę time-to-first-token (ms)."""
        with self._lock:
            self.metrics["llm_first_token_ms_total"] += max(elapsed_ms, 0)
            self.metrics["llm_first_token_samples"] += 1

    def increment_policy_blocked(self):
        """Inkrementuje licznik żądań zablokowanych przez policy gate."""
        with self._lock:
            self.metrics["policy_blocked_count"] += 1

    def record_ollama_runtime_sample(
        self,
        *,
        load_duration_ms: Optional[float] = None,
        prompt_eval_count: Optional[int] = None,
        eval_count: Optional[int] = None,
        prompt_eval_duration_ms: Optional[float] = None,
        eval_duration_ms: Optional[float] = None,
    ) -> None:
        """Dodaje próbkę metryk runtime zwracanych przez Ollama."""
        with self._lock:
            if load_duration_ms is not None:
                self.metrics["ollama_load_duration_ms_total"] += int(
                    max(load_duration_ms, 0.0)
                )
            if prompt_eval_count is not None:
                self.metrics["ollama_prompt_eval_count_total"] += int(
                    max(prompt_eval_count, 0)
                )
            if eval_count is not None:
                self.metrics["ollama_eval_count_total"] += int(max(eval_count, 0))
            if prompt_eval_duration_ms is not None:
                self.metrics["ollama_prompt_eval_duration_ms_total"] += int(
                    max(prompt_eval_duration_ms, 0.0)
                )
            if eval_duration_ms is not None:
                self.metrics["ollama_eval_duration_ms_total"] += int(
                    max(eval_duration_ms, 0.0)
                )
            self.metrics["ollama_runtime_samples"] += 1

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

    def _init_provider_metrics(self, provider: str) -> None:
        """
        Inicjalizuje strukturę metryk dla providera (internal helper).

        Args:
            provider: Nazwa providera
        """
        if provider not in self.provider_metrics:
            self.provider_metrics[provider] = {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "latency_samples": [],  # Store recent samples for percentile calculation
                "error_codes": {},  # error_code -> count
                "total_cost_usd": 0.0,
                "total_tokens": 0,
                "timeouts": 0,
                "auth_errors": 0,
                "budget_errors": 0,
            }

    def record_provider_request(
        self,
        provider: str,
        success: bool,
        latency_ms: float,
        error_code: Optional[str] = None,
        cost_usd: float = 0.0,
        tokens: int = 0,
    ) -> None:
        """
        Rejestruje pojedynczy request do providera z metrykami.

        Args:
            provider: Nazwa providera
            success: Czy request zakończył się sukcesem
            latency_ms: Latencja w milisekundach
            error_code: Opcjonalny kod błędu
            cost_usd: Koszt requestu w USD
            tokens: Liczba użytych tokenów
        """
        with self._lock:
            self._init_provider_metrics(provider)
            pm = self.provider_metrics[provider]

            pm["total_requests"] += 1
            if success:
                pm["successful_requests"] += 1
            else:
                pm["failed_requests"] += 1

            # Track latency (keep last 1000 samples for percentile calculation)
            pm["latency_samples"].append(latency_ms)
            if len(pm["latency_samples"]) > 1000:
                pm["latency_samples"] = pm["latency_samples"][-1000:]

            # Track error codes
            if error_code:
                if error_code not in pm["error_codes"]:
                    pm["error_codes"][error_code] = 0
                pm["error_codes"][error_code] += 1

                # Increment specific error counters
                if "timeout" in error_code.lower():
                    pm["timeouts"] += 1
                elif "auth" in error_code.lower():
                    pm["auth_errors"] += 1
                elif "budget" in error_code.lower():
                    pm["budget_errors"] += 1

            pm["total_cost_usd"] += cost_usd
            pm["total_tokens"] += tokens

    def _calculate_percentile(
        self, samples: List[float], percentile: float
    ) -> Optional[float]:
        """
        Oblicza percentyl z listy próbek.

        Args:
            samples: Lista wartości
            percentile: Percentyl (0.0-1.0)

        Returns:
            Wartość percentyla lub None jeśli brak danych
        """
        if not samples:
            return None
        sorted_samples = sorted(samples)

        # For tiny sample sets, p99 should stay conservative and report top tail.
        if percentile >= 0.99:
            return round(sorted_samples[-1], 2)

        n = len(sorted_samples)
        rank = percentile * n

        if rank <= 1:
            return round(sorted_samples[0], 2)
        if rank >= n:
            return round(sorted_samples[-1], 2)

        lower = floor(rank)
        upper = ceil(rank)
        lower_value = sorted_samples[lower - 1]
        upper_value = sorted_samples[upper - 1]

        if lower == upper:
            # Exact rank for even-sized distributions: midpoint between adjacent
            # order statistics keeps p50 as a true median.
            next_idx = min(lower, n - 1)
            return round((lower_value + sorted_samples[next_idx]) / 2.0, 2)

        fraction = rank - lower
        value = lower_value + fraction * (upper_value - lower_value)
        return round(value, 2)

    def get_provider_metrics(self, provider: str) -> Optional[Dict]:
        """
        Zwraca metryki dla konkretnego providera.

        Args:
            provider: Nazwa providera

        Returns:
            Dict z metrykami providera lub None jeśli brak danych
        """
        with self._lock:
            if provider not in self.provider_metrics:
                return None

            pm = self.provider_metrics[provider]
            total = pm["total_requests"]

            return {
                "provider": provider,
                "total_requests": total,
                "successful_requests": pm["successful_requests"],
                "failed_requests": pm["failed_requests"],
                "success_rate": round(pm["successful_requests"] / total * 100, 2)
                if total > 0
                else 0.0,
                "error_rate": round(pm["failed_requests"] / total * 100, 2)
                if total > 0
                else 0.0,
                "latency": {
                    "p50_ms": self._calculate_percentile(pm["latency_samples"], 0.50),
                    "p95_ms": self._calculate_percentile(pm["latency_samples"], 0.95),
                    "p99_ms": self._calculate_percentile(pm["latency_samples"], 0.99),
                    "samples": len(pm["latency_samples"]),
                },
                "errors": {
                    "total": pm["failed_requests"],
                    "timeouts": pm["timeouts"],
                    "auth_errors": pm["auth_errors"],
                    "budget_errors": pm["budget_errors"],
                    "by_code": pm["error_codes"].copy(),
                },
                "cost": {
                    "total_usd": round(pm["total_cost_usd"], 4),
                    "total_tokens": pm["total_tokens"],
                },
            }

    def get_all_provider_metrics(self) -> Dict[str, Dict]:
        """
        Zwraca metryki dla wszystkich providerów.

        Returns:
            Dict z metrykami per provider
        """
        with self._lock:
            return {
                provider: self.get_provider_metrics(provider)
                for provider in self.provider_metrics.keys()
            }

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
            samples = self.metrics["llm_first_token_samples"]
            avg_first_token = (
                round(self.metrics["llm_first_token_ms_total"] / samples, 2)
                if samples
                else None
            )
            ollama_samples = self.metrics["ollama_runtime_samples"]
            avg_ollama_load = (
                round(self.metrics["ollama_load_duration_ms_total"] / ollama_samples, 2)
                if ollama_samples
                else None
            )
            avg_ollama_prompt_eval_duration = (
                round(
                    self.metrics["ollama_prompt_eval_duration_ms_total"]
                    / ollama_samples,
                    2,
                )
                if ollama_samples
                else None
            )
            avg_ollama_eval_duration = (
                round(self.metrics["ollama_eval_duration_ms_total"] / ollama_samples, 2)
                if ollama_samples
                else None
            )

            # Calculate policy block rate
            policy_blocked = self.metrics["policy_blocked_count"]
            total_requests = self.metrics["tasks_created"]
            policy_block_rate = (
                round((policy_blocked / total_requests) * 100, 2)
                if total_requests > 0
                else 0.0
            )

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
                "policy": {
                    "blocked_count": policy_blocked,
                    "block_rate": policy_block_rate,
                },
                "models": {
                    "generation_params_updates": self.metrics["model_params_updates"],
                },
                "llm": {
                    "first_token_samples": samples,
                    "first_token_avg_ms": avg_first_token,
                    "ollama_runtime": {
                        "samples": ollama_samples,
                        "load_duration_avg_ms": avg_ollama_load,
                        "prompt_eval_count_total": self.metrics[
                            "ollama_prompt_eval_count_total"
                        ],
                        "eval_count_total": self.metrics["ollama_eval_count_total"],
                        "prompt_eval_duration_avg_ms": avg_ollama_prompt_eval_duration,
                        "eval_duration_avg_ms": avg_ollama_eval_duration,
                    },
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


def get_metrics_collector() -> MetricsCollector:
    """
    Zwraca globalny collector metryk, inicjalizując go leniwie jeśli potrzeba.
    """
    global metrics_collector
    if metrics_collector is None:
        metrics_collector = MetricsCollector()
        logger.info("MetricsCollector lazily initialized")
    return metrics_collector
