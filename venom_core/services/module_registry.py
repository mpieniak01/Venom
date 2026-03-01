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
from venom_core.core.module_data_policy import (
    ModuleDataPolicy,
    parse_module_data_policy_payload,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
MANIFEST_PREFIX = "manifest:"


@dataclass(frozen=True)
class ApiModuleManifest:
    module_id: str
    router_import: str
    data_policy: ModuleDataPolicy
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


def _normalize_api_version(value: str) -> tuple[int, ...]:
    parsed = _parse_version(value)
    if not parsed:
        return ()
    normalized = list(parsed)
    while len(normalized) > 1 and normalized[-1] == 0:
        normalized.pop()
    return tuple(normalized)


def _is_compatible(manifest: ApiModuleManifest, settings: object) -> bool:
    core_api = str(
        getattr(settings, "CORE_MODULE_API_VERSION", "1.0.0") or "1.0.0"
    ).strip()
    if manifest.module_api_version:
        module_api = str(manifest.module_api_version).strip()
        core_norm = _normalize_api_version(core_api)
        module_norm = _normalize_api_version(module_api)
        if core_norm and module_norm:
            if module_norm != core_norm:
                logger.warning(
                    "Skipping module %s: module_api_version=%s, core_api_version=%s",
                    manifest.module_id,
                    manifest.module_api_version,
                    core_api,
                )
                return False
        elif module_api != core_api:
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


def _looks_like_manifest_path(item: str) -> bool:
    normalized = item.strip()
    if normalized.startswith(MANIFEST_PREFIX):
        return True
    return normalized.endswith(".json")


def _resolve_manifest_path(raw_item: str) -> Path:
    source = raw_item.strip()
    path_text = (
        source[len(MANIFEST_PREFIX) :] if source.startswith(MANIFEST_PREFIX) else source
    )
    manifest_path = Path(path_text).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = Path.cwd() / manifest_path
    return manifest_path


def _parse_manifest_file(raw_item: str) -> ApiModuleManifest | None:
    manifest_path = _resolve_manifest_path(raw_item)

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
    data_policy, data_policy_errors = parse_module_data_policy_payload(
        module_id=module_id or "<missing_module_id>",
        payload=backend.get("data_policy"),
    )

    if not module_id or not router_import or data_policy is None:
        details = (
            "; ".join(data_policy_errors) if data_policy_errors else "missing fields"
        )
        logger.warning(
            "Invalid optional module manifest %s: required fields missing or invalid (%s)",
            manifest_path,
            details,
        )
        return None

    return ApiModuleManifest(
        module_id=module_id,
        router_import=router_import,
        data_policy=data_policy,
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
        if not _looks_like_manifest_path(item):
            logger.warning(
                "Invalid API_OPTIONAL_MODULES item (legacy format unsupported): %s",
                item.strip(),
            )
            continue
        manifest = _parse_manifest_file(item)
        if manifest is not None:
            manifests.append(manifest)
    return manifests


def _validate_manifest_item(item: str, errors: list[str]) -> None:
    manifest_path = _resolve_manifest_path(item)
    if not manifest_path.exists():
        errors.append("optional module manifest not found: " + str(manifest_path))
        return

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(
            "failed to read optional module manifest "
            + str(manifest_path)
            + ": "
            + str(exc)
        )
        return

    module_id = str(payload.get("module_id", "")).strip()
    backend = payload.get("backend")
    if not isinstance(backend, dict):
        errors.append(
            "invalid optional module manifest backend object: " + str(manifest_path)
        )
        return
    router_import = str(backend.get("router_import", "")).strip()
    if not module_id or not router_import:
        errors.append(
            "invalid optional module manifest (required module_id/backend.router_import): "
            + str(manifest_path)
        )
    _, policy_errors = parse_module_data_policy_payload(
        module_id=module_id or "<missing_module_id>",
        payload=backend.get("data_policy"),
    )
    errors.extend(policy_errors)


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
            _validate_manifest_item(item, errors)
            continue
        errors.append(
            "invalid optional module entry (legacy format unsupported; use manifest:/path/module.json): "
            + item
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
    config_errors = validate_optional_modules_config(settings)
    if config_errors:
        raise RuntimeError(
            "Invalid optional modules configuration: " + " | ".join(config_errors)
        )

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
