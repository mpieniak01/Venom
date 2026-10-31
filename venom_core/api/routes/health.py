"""Shared process liveness route for Full and Studio entrypoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz():
    """Prosty endpoint zdrowia – do sprawdzenia, czy Venom żyje."""
    return {"status": "ok", "component": "venom-core"}
