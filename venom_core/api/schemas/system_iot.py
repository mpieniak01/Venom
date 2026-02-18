"""Schemas for system IoT API endpoints."""

from typing import Optional

from pydantic import BaseModel


class IoTStatusResponse(BaseModel):
    """Response with IoT bridge status."""

    connected: bool
    cpu_temp: Optional[str] = None
    memory: Optional[str] = None
    disk: Optional[str] = None
    message: Optional[str] = None
