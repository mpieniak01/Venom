"""Moduł: routes/system_metrics - Endpoint /metrics wydzielony z system.py."""

from fastapi import APIRouter, HTTPException

from venom_core.core import metrics as metrics_module
from venom_core.utils.ttl_cache import TTLCache

router = APIRouter(prefix="/api/v1", tags=["system"])

_metrics_cache = TTLCache[dict](ttl_seconds=1.0)


@router.get("/metrics")
async def get_metrics():
    """
    Zwraca metryki systemowe.

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
