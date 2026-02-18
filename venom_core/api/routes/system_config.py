"""Moduł: routes/system_config - Endpointy zarządzania konfiguracją runtime."""

from fastapi import APIRouter, HTTPException, Request

from venom_core.api.schemas.system import (
    ConfigBackupsResponse,
    ConfigUpdateRequest,
    ConfigUpdateResponse,
    RestoreBackupRequest,
    RestoreBackupResponse,
    RuntimeConfigResponse,
)
from venom_core.services.config_manager import config_manager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])


def require_localhost_request(req: Request) -> None:
    """Dopuszcza wyłącznie żądania administracyjne z localhosta."""
    client_host = req.client.host if req.client else "unknown"
    if client_host not in ["127.0.0.1", "::1", "localhost"]:
        logger.warning(
            "Próba dostępu do endpointu administracyjnego z nieautoryzowanego hosta: %s",
            client_host,
        )
        raise HTTPException(status_code=403, detail="Access denied")


@router.get(
    "/config/runtime",
    response_model=RuntimeConfigResponse,
    responses={
        500: {"description": "Błąd wewnętrzny podczas pobierania konfiguracji runtime"},
    },
)
def get_runtime_config() -> RuntimeConfigResponse:
    """
    Zwraca aktualną konfigurację runtime (whitelist parametrów z .env).
    Sekrety są ZAWSZE maskowane w odpowiedzi API.
    """
    try:
        # Security: Zawsze wymuszaj maskowanie sekretów w API
        config, config_sources = config_manager.get_effective_config_with_sources(
            mask_secrets=True
        )
        return RuntimeConfigResponse(
            status="success", config=config, config_sources=config_sources
        )

    except Exception as e:
        logger.exception("Błąd podczas pobierania konfiguracji")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post(
    "/config/runtime",
    response_model=ConfigUpdateResponse,
    responses={
        500: {
            "description": "Błąd wewnętrzny podczas aktualizacji konfiguracji runtime"
        },
        403: {"description": "Brak uprawnień do zmiany konfiguracji"},
    },
)
def update_runtime_config(
    request: ConfigUpdateRequest, req: Request
) -> ConfigUpdateResponse:
    """
    Aktualizuje konfigurację runtime (zapis do .env z backupem).
    Dostępne tylko z localhost.
    Lokalny administrator ma pełną kontrolę nad parametrami.
    """
    require_localhost_request(req)

    try:
        # User is Admin on Localhost - Allow full configuration
        result = config_manager.update_config(request.updates)
        # Ensure result matches ConfigUpdateResponse schema
        if isinstance(result, dict):
            # Map 'success' boolean to 'status' string
            status = "success" if result.get("success", True) else "error"
            return ConfigUpdateResponse(
                status=status,
                message=result.get("message", "Configuration updated"),
                updated_keys=result.get("changed_keys") or result.get("updated_keys", list(request.updates.keys())),
            )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Błąd podczas aktualizacji konfiguracji")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get(
    "/config/backups",
    response_model=ConfigBackupsResponse,
    responses={
        500: {
            "description": "Błąd wewnętrzny podczas pobierania listy backupów konfiguracji"
        },
        403: {"description": "Brak uprawnień do odczytu listy backupów konfiguracji"},
    },
)
def get_config_backups(req: Request, limit: int = 20) -> ConfigBackupsResponse:
    """
    Zwraca listę backupów .env.
    """
    require_localhost_request(req)

    try:
        backups = config_manager.get_backup_list(limit=limit)
        return ConfigBackupsResponse(
            status="success", backups=backups, count=len(backups)
        )

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy backupów")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post(
    "/config/restore",
    response_model=RestoreBackupResponse,
    responses={
        500: {
            "description": "Błąd wewnętrzny podczas przywracania backupu konfiguracji"
        },
        403: {"description": "Brak uprawnień do przywracania backupu konfiguracji"},
    },
)
def restore_config_backup(
    request: RestoreBackupRequest, req: Request
) -> RestoreBackupResponse:
    """
    Przywraca .env z backupu.
    """
    require_localhost_request(req)

    try:
        result = config_manager.restore_backup(request.backup_filename)
        # Ensure result matches RestoreBackupResponse schema
        if isinstance(result, dict):
            # Map 'success' boolean to 'status' string
            status = "success" if result.get("success", True) else "error"
            # Service doesn't return restored_file, so use the requested filename when successful
            restored_file = request.backup_filename if result.get("success") else ""
            return RestoreBackupResponse(
                status=status,
                message=result.get("message", "Backup restored"),
                restored_file=restored_file,
            )
        return result

    except Exception as e:
        logger.exception("Błąd podczas przywracania backupu")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
