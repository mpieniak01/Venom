"""Moduł: routes/system - agregator endpointów systemowych."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["system"])
