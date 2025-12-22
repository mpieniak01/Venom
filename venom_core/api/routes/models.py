"""Modul: routes/models - agregacja endpointow API dla zarzadzania modelami AI."""

from fastapi import APIRouter

from venom_core.api.routes.models_config import router as config_router
from venom_core.api.routes.models_dependencies import set_dependencies
from venom_core.api.routes.models_install import router as install_router
from venom_core.api.routes.models_registry import router as registry_router
from venom_core.api.routes.models_registry_ops import router as registry_ops_router
from venom_core.api.routes.models_translation import router as translation_router
from venom_core.api.routes.models_usage import router as usage_router
from venom_core.services.config_manager import config_manager
from venom_core.services.translation_service import translation_service

router = APIRouter()

router.include_router(install_router)
router.include_router(usage_router)
router.include_router(registry_router)
router.include_router(registry_ops_router)
router.include_router(config_router)
router.include_router(translation_router)

__all__ = ["router", "set_dependencies", "config_manager", "translation_service"]
