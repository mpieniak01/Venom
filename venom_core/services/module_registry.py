"""Optional API module registry for extension-ready router loading."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Iterable

from fastapi import FastAPI
from fastapi.routing import APIRouter

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ApiModuleManifest:
    module_id: str
    router_import: str
    feature_flag: str | None = None


def _is_enabled(manifest: ApiModuleManifest, settings: object) -> bool:
    if not manifest.feature_flag:
        return True
    return bool(getattr(settings, manifest.feature_flag, False))


def _load_router(router_import: str) -> APIRouter | None:
    try:
        module_path, attr = router_import.split(":", maxsplit=1)
    except ValueError:
        logger.warning("Invalid router import format: %s", router_import)
        return None

    try:
        module = importlib.import_module(module_path)
        router = getattr(module, attr, None)
        if isinstance(router, APIRouter):
            return router
        logger.warning("Router %s is missing or invalid.", router_import)
        return None
    except Exception as exc:
        logger.warning("Failed to import optional router %s: %s", router_import, exc)
        return None


def _builtin_manifests() -> list[ApiModuleManifest]:
    return [
        ApiModuleManifest(
            module_id="module_example",
            router_import="venom_core.api.routes.module_example:router",
            feature_flag="FEATURE_MODULE_EXAMPLE",
        )
    ]


def _parse_extra_manifest(raw_item: str) -> ApiModuleManifest | None:
    item = raw_item.strip()
    if not item:
        return None
    parts = [part.strip() for part in item.split("|")]
    if len(parts) < 2:
        logger.warning("Invalid API_OPTIONAL_MODULES item: %s", item)
        return None
    module_id = parts[0]
    router_import = parts[1]
    feature_flag = parts[2] if len(parts) > 2 and parts[2] else None
    return ApiModuleManifest(
        module_id=module_id,
        router_import=router_import,
        feature_flag=feature_flag,
    )


def _extra_manifests(settings: object) -> list[ApiModuleManifest]:
    raw = str(getattr(settings, "API_OPTIONAL_MODULES", "") or "").strip()
    if not raw:
        return []
    manifests: list[ApiModuleManifest] = []
    for item in raw.split(","):
        manifest = _parse_extra_manifest(item)
        if manifest is not None:
            manifests.append(manifest)
    return manifests


def iter_api_module_manifests(
    settings: object = SETTINGS,
) -> Iterable[ApiModuleManifest]:
    yield from _builtin_manifests()
    yield from _extra_manifests(settings)


def include_optional_api_routers(
    app: FastAPI, settings: object = SETTINGS
) -> list[str]:
    included: list[str] = []
    for manifest in iter_api_module_manifests(settings):
        if not _is_enabled(manifest, settings):
            continue
        router = _load_router(manifest.router_import)
        if router is None:
            continue
        app.include_router(router)
        included.append(manifest.module_id)
    if included:
        logger.info("Included optional API modules: %s", ", ".join(included))
    return included
