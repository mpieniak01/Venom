"""Optional API module registry for extension-ready router loading."""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
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
    module_root: str | None = None
    feature_flag: str | None = None
    module_api_version: str | None = None
    min_core_version: str | None = None


def _is_enabled(manifest: ApiModuleManifest, settings: object) -> bool:
    if not manifest.feature_flag:
        return True
    return bool(getattr(settings, manifest.feature_flag, False))


def _load_router(
    router_import: str, module_root: str | None = None
) -> APIRouter | None:
    try:
        module_path, attr = router_import.split(":", maxsplit=1)
    except ValueError:
        logger.warning("Invalid router import format: %s", router_import)
        return None

    inserted_path: str | None = None
    try:
        if module_root:
            root_path = str(Path(module_root).resolve())
            if root_path not in sys.path:
                sys.path.insert(0, root_path)
                inserted_path = root_path
        module = importlib.import_module(module_path)
        router = getattr(module, attr, None)
        if isinstance(router, APIRouter):
            return router
        logger.warning("Router %s is missing or invalid.", router_import)
        return None
    except Exception as exc:
        logger.warning("Failed to import optional router %s: %s", router_import, exc)
        return None
    finally:
        if inserted_path is not None and inserted_path in sys.path:
            try:
                sys.path.remove(inserted_path)
            except ValueError:
                pass


def _parse_version(value: str) -> tuple[int, ...]:
    tokens = []
    for token in value.strip().split("."):
        if not token:
            continue
        try:
            tokens.append(int(token))
        except ValueError:
            break
    return tuple(tokens)


def _is_compatible(manifest: ApiModuleManifest, settings: object) -> bool:
    core_api = str(getattr(settings, "CORE_MODULE_API_VERSION", "1") or "1").strip()
    if manifest.module_api_version and manifest.module_api_version != core_api:
        logger.warning(
            "Skipping module %s: module_api_version=%s, core_api_version=%s",
            manifest.module_id,
            manifest.module_api_version,
            core_api,
        )
        return False

    if manifest.min_core_version:
        core_runtime = str(
            getattr(settings, "CORE_RUNTIME_VERSION", "1.5.0") or "1.5.0"
        ).strip()
        if _parse_version(core_runtime) < _parse_version(manifest.min_core_version):
            logger.warning(
                "Skipping module %s: requires core >= %s, current=%s",
                manifest.module_id,
                manifest.min_core_version,
                core_runtime,
            )
            return False
    return True


def _builtin_manifests() -> list[ApiModuleManifest]:
    return []


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
    module_api_version = parts[3] if len(parts) > 3 and parts[3] else None
    min_core_version = parts[4] if len(parts) > 4 and parts[4] else None
    return ApiModuleManifest(
        module_id=module_id,
        router_import=router_import,
        module_root=None,
        feature_flag=feature_flag,
        module_api_version=module_api_version,
        min_core_version=min_core_version,
    )


def _looks_like_manifest_path(item: str) -> bool:
    normalized = item.strip()
    if normalized.startswith("manifest:"):
        return True
    return "|" not in normalized and normalized.endswith(".json")


def _parse_manifest_file(raw_item: str) -> ApiModuleManifest | None:
    source = raw_item.strip()
    path_text = source[len("manifest:") :] if source.startswith("manifest:") else source
    manifest_path = Path(path_text).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = Path.cwd() / manifest_path

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "Failed to read optional module manifest %s: %s", manifest_path, exc
        )
        return None

    module_id = str(payload.get("module_id", "")).strip()
    backend = payload.get("backend") if isinstance(payload.get("backend"), dict) else {}
    router_import = str(backend.get("router_import", "")).strip()
    feature_flag = str(backend.get("feature_flag", "")).strip() or None
    module_api_version = str(backend.get("module_api_version", "")).strip() or None
    min_core_version = str(backend.get("min_core_version", "")).strip() or None

    if not module_id or not router_import:
        logger.warning(
            "Invalid optional module manifest %s: required module_id/backend.router_import missing",
            manifest_path,
        )
        return None

    return ApiModuleManifest(
        module_id=module_id,
        router_import=router_import,
        module_root=str(manifest_path.parent),
        feature_flag=feature_flag,
        module_api_version=module_api_version,
        min_core_version=min_core_version,
    )


def _extra_manifests(settings: object) -> list[ApiModuleManifest]:
    raw = str(getattr(settings, "API_OPTIONAL_MODULES", "") or "").strip()
    if not raw:
        return []
    manifests: list[ApiModuleManifest] = []
    for item in raw.split(","):
        manifest = (
            _parse_manifest_file(item)
            if _looks_like_manifest_path(item)
            else _parse_extra_manifest(item)
        )
        if manifest is not None:
            manifests.append(manifest)
    return manifests


def validate_optional_modules_config(settings: object = SETTINGS) -> list[str]:
    raw = str(getattr(settings, "API_OPTIONAL_MODULES", "") or "").strip()
    if not raw:
        return []
    errors: list[str] = []
    for raw_item in raw.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if _looks_like_manifest_path(item):
            path_text = (
                item[len("manifest:") :] if item.startswith("manifest:") else item
            )
            manifest_path = Path(path_text).expanduser()
            if not manifest_path.is_absolute():
                manifest_path = Path.cwd() / manifest_path
            if not manifest_path.exists():
                errors.append(
                    "optional module manifest not found: " + str(manifest_path)
                )
                continue
            parsed = _parse_manifest_file(item)
            if parsed is None:
                errors.append(
                    "invalid optional module manifest (required module_id/backend.router_import): "
                    + str(manifest_path)
                )
            continue
        parts = [part.strip() for part in item.split("|")]
        if len(parts) < 2:
            errors.append(
                "invalid optional module entry (expected: manifest:/path/module.json or module_id|module.path:router[|FEATURE|API|CORE]): "
                + item
            )
            continue
        if ":" not in parts[1]:
            errors.append(
                "invalid router import (expected module.path:router): " + parts[1]
            )
    return errors


def iter_api_module_manifests(
    settings: object = SETTINGS,
) -> Iterable[ApiModuleManifest]:
    yield from _builtin_manifests()
    yield from _extra_manifests(settings)


def include_optional_api_routers(
    app: FastAPI, settings: object = SETTINGS
) -> list[str]:
    for error in validate_optional_modules_config(settings):
        logger.warning("Optional module config warning: %s", error)

    included: list[str] = []
    for manifest in iter_api_module_manifests(settings):
        if not _is_enabled(manifest, settings):
            continue
        if not _is_compatible(manifest, settings):
            continue
        router = _load_router(manifest.router_import, manifest.module_root)
        if router is None:
            continue
        app.include_router(router)
        included.append(manifest.module_id)
    if included:
        logger.info("Included optional API modules: %s", ", ".join(included))
    return included
