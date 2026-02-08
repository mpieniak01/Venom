"""Moduł: routes/system_config - Endpointy zarządzania konfiguracją runtime."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from venom_core.services.config_manager import config_manager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get(
    "/config/runtime",
    responses={
        500: {"description": "Błąd wewnętrzny podczas pobierania konfiguracji runtime"},
    },
)
async def get_runtime_config(mask_secrets: bool = True):
    """
    Zwraca aktualną konfigurację runtime (whitelist parametrów z .env).
    """
    try:
        config = config_manager.get_config(mask_secrets=mask_secrets)
        return {"status": "success", "config": config}

    except Exception as e:
        logger.exception("Błąd podczas pobierania konfiguracji")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


class ConfigUpdateRequest(BaseModel):
    """Request do aktualizacji konfiguracji."""

    updates: dict


@router.post(
    "/config/runtime",
    responses={
        500: {
            "description": "Błąd wewnętrzny podczas aktualizacji konfiguracji runtime"
        },
    },
)
async def update_runtime_config(request: ConfigUpdateRequest):
    """
    Aktualizuje konfigurację runtime (zapis do .env z backupem).
    """
    try:
        result = config_manager.update_config(request.updates)
        return result

    except Exception as e:
        logger.exception("Błąd podczas aktualizacji konfiguracji")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get(
    "/config/backups",
    responses={
        500: {
            "description": "Błąd wewnętrzny podczas pobierania listy backupów konfiguracji"
        },
    },
)
async def get_config_backups(limit: int = 20):
    """
    Zwraca listę backupów .env.
    """
    try:
        backups = config_manager.get_backup_list(limit=limit)
        return {"status": "success", "backups": backups, "count": len(backups)}

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy backupów")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


class RestoreBackupRequest(BaseModel):
    """Request do przywrócenia backupu."""

    backup_filename: str


@router.post(
    "/config/restore",
    responses={
        500: {
            "description": "Błąd wewnętrzny podczas przywracania backupu konfiguracji"
        },
    },
)
async def restore_config_backup(request: RestoreBackupRequest):
    """
    Przywraca .env z backupu.
    """
    try:
        result = config_manager.restore_backup(request.backup_filename)
        return result

    except Exception as e:
        logger.exception("Błąd podczas przywracania backupu")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
