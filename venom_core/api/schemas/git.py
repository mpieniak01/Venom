"""Schemas for git API endpoints."""

from typing import Optional

from pydantic import BaseModel


class InitRepoRequest(BaseModel):
    """Payload dla inicjalizacji repozytorium."""

    url: Optional[str] = None
