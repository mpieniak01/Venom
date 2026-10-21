"""Passive, unauthenticated installation identity; never starts a runtime."""

from fastapi import APIRouter, HTTPException

from venom_core.services.transport_identity import read_transport_identity

router = APIRouter(prefix="/api/v1/transport", tags=["transport"])


@router.get(
    "/identity",
    responses={503: {"description": "The installation identity is unavailable."}},
)
def get_transport_identity() -> dict[str, str | int]:
    try:
        return read_transport_identity()
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail={"reason_code": "TRANSPORT_IDENTITY_UNAVAILABLE"}
        ) from exc
