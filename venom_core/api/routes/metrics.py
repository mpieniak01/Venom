"""Moduł: routes/metrics - Endpointy API dla metryk i tokenomics."""

from fastapi import APIRouter, HTTPException

from venom_core.core import metrics as metrics_module
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

# Dependency - będzie ustawione w main.py
_token_economist = None


def set_dependencies(token_economist=None):
    """Ustaw zależności dla routera."""
    global _token_economist
    _token_economist = token_economist


@router.get("/tokens")
async def get_token_metrics():
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
            "session_total_tokens": total_tokens,
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


@router.get("/system")
async def get_system_metrics():
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
