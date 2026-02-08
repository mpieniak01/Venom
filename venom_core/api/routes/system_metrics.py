"""Moduł: routes/metrics - Endpointy API dla metryk i tokenomics."""

from typing import Any

from fastapi import APIRouter, HTTPException

from venom_core.core import metrics as metrics_module
from venom_core.utils.logger import get_logger
from venom_core.utils.ttl_cache import TTLCache

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

TOKEN_METRICS_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": "Metrics collector nie jest dostępny"},
    500: {"description": "Błąd podczas pobierania metryk tokenów"},
}
SYSTEM_METRICS_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": "Metrics collector nie jest dostępny"},
    500: {"description": "Błąd podczas pobierania metryk systemowych"},
}
METRICS_ROOT_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": "Metrics collector nie jest dostępny"},
}

_metrics_cache = TTLCache[dict](ttl_seconds=1.0)
_token_metrics_cache = TTLCache[dict](ttl_seconds=2.0)
_token_economist = None


def set_dependencies(token_economist=None):
    """Ustaw zależności dla routera."""
    global _token_economist
    _token_economist = token_economist
    _token_metrics_cache.clear()


@router.get("/tokens", responses=TOKEN_METRICS_RESPONSES)
def get_token_metrics():
    """
    Pobiera metryki użycia tokenów i koszty.

    Returns:
        Dict z metrykami tokenów:
        - session_total_tokens: Całkowita liczba tokenów w sesji
        - session_cost_usd: Koszt sesji w USD
        - models_breakdown: Podział kosztów według modeli

    Raises:
        HTTPException: 503 jeśli TokenEconomist nie jest dostępny
    """
    cached = _token_metrics_cache.get()
    if cached is not None:
        return cached

    res = _get_token_metrics_impl()
    _token_metrics_cache.set(res)
    return res


def _get_token_metrics_impl():
    """Implementacja pobierania metryk tokenów (bez cache)."""
    collector = metrics_module.metrics_collector
    if _token_economist is None:
        # Zwróć podstawowe metryki z metrics_collector
        if collector is None:
            raise HTTPException(
                status_code=503, detail="Metrics collector nie jest dostępny"
            )

        metrics = collector.get_metrics()
        return {
            "session_total_tokens": metrics.get("tokens_used_session", 0),
            "session_cost_usd": 0.0,  # Nie możemy obliczyć bez TokenEconomist
            "models_breakdown": {},
            "note": "TokenEconomist nie jest dostępny - brak szczegółowych danych o kosztach",
        }

    try:
        # W przyszłości: TokenEconomist powinien przechowywać dane o użyciu per-model
        # Na razie zwracamy podstawowe dane z metrics_collector

        collector = metrics_module.metrics_collector
        if collector is None:
            raise HTTPException(
                status_code=503, detail="Metrics collector nie jest dostępny"
            )

        metrics = collector.get_metrics()
        total_tokens = metrics.get("tokens_used_session", 0)

        # Szacunkowy koszt (zakładając konfigurowalny split i model)
        # W produkcji: TokenEconomist powinien śledzić rzeczywiste użycie per-model
        from venom_core.config import SETTINGS

        split_ratio = SETTINGS.TOKEN_COST_ESTIMATION_SPLIT
        cost_model = SETTINGS.DEFAULT_COST_MODEL

        estimated_cost = _token_economist.calculate_cost(
            usage={
                "input_tokens": int(total_tokens * split_ratio),
                "output_tokens": int(total_tokens * (1 - split_ratio)),
            },
            model_name=cost_model,
        )

        # TODO: W przyszłości dodać śledzenie per-model w TokenEconomist
        # Na razie zwracamy szacunkowe dane
        return {
            "total_tokens": total_tokens,
            "session_total_tokens": total_tokens,  # Dodajemy oba dla kompatybilności
            "session_cost_usd": estimated_cost.get("total_cost_usd", 0.0),
            "models_breakdown": {
                "estimated": {
                    "model": "gpt-3.5-turbo (estimated)",
                    "tokens": total_tokens,
                    "cost_usd": estimated_cost.get("total_cost_usd", 0.0),
                }
            },
            "note": "Koszty są szacunkowe. Śledzenie per-model zostanie dodane w przyszłej wersji.",
        }
    except Exception as e:
        logger.exception("Błąd podczas pobierania metryk tokenów")
        raise HTTPException(
            status_code=500, detail="Błąd podczas pobierania metryk tokenów"
        ) from e


@router.get("/system", responses=SYSTEM_METRICS_RESPONSES)
def get_system_metrics():
    """
    Pobiera metryki systemowe (zadania, uptime, network).

    Returns:
        Dict z metrykami systemowymi

    Raises:
        HTTPException: 503 jeśli metrics_collector nie jest dostępny
    """
    collector = metrics_module.metrics_collector
    if collector is None:
        raise HTTPException(
            status_code=503, detail="Metrics collector nie jest dostępny"
        )

    try:
        metrics = collector.get_metrics()
        return metrics
    except Exception as e:
        logger.exception("Błąd podczas pobierania metryk systemowych")
        raise HTTPException(
            status_code=500, detail="Błąd podczas pobierania metryk systemowych"
        ) from e


@router.get("", responses=METRICS_ROOT_RESPONSES)
def get_metrics():
    """
    Zwraca metryki systemowe (root endpoint).
    Tożsame z /system, ale z krótkim cache (1.0s) dla wysokiej wydajności dashboardu.

    Returns:
        Słownik z metrykami wydajności i użycia

    Raises:
        HTTPException: 503 jeśli MetricsCollector nie jest dostępny
    """
    collector = metrics_module.metrics_collector
    if collector is None:
        raise HTTPException(status_code=503, detail="Metrics collector not initialized")

    cached = _metrics_cache.get()
    if cached is not None:
        return cached

    metrics = collector.get_metrics()
    _metrics_cache.set(metrics)
    return metrics
