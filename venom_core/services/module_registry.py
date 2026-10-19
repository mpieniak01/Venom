"""Optional API module registry for extension-ready router loading."""

from __future__ import annotations

import importlib
import json
import re
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, TypeGuard

from fastapi import FastAPI
from fastapi.routing import APIRouter

from venom_core.config import SETTINGS
from venom_core.core.module_data_policy import (
    ModuleDataPolicy,
    parse_module_data_policy_payload,
)
from venom_core.services.module_observations import module_candidates
from venom_core.services.module_runtime import include_isolated_router
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
    conversation_provider_import: str | None = None
    integration_provider_import: str | None = None


_FACTORY_IMPORT = re.compile(
    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*",
    re.ASCII,
)


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


def _valid_factory_import(value: object) -> TypeGuard[str | None]:
    return value is None or (
        isinstance(value, str) and _FACTORY_IMPORT.fullmatch(value) is not None
    )


def _parse_manifest_file(raw_item: str) -> ApiModuleManifest | None:
    manifest_path = _resolve_manifest_path(raw_item)

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "Failed to read optional module manifest %s: %s", manifest_path, exc
        )
        return None

    if not isinstance(payload, dict):
        logger.warning(
            "Invalid optional module manifest %s: manifest must be a JSON object",
            manifest_path,
        )
        return None

    module_id = str(payload.get("module_id", "")).strip()
    backend_payload = payload.get("backend")
    backend: dict[str, object]
    if isinstance(backend_payload, dict):
        backend = backend_payload
    else:
        backend = {}
    router_import = str(backend.get("router_import", "")).strip()
    feature_flag = str(backend.get("feature_flag", "")).strip() or None
    module_api_version = str(backend.get("module_api_version", "")).strip() or None
    min_core_version = str(backend.get("min_core_version", "")).strip() or None
    integration_import = backend.get("integration_provider_import")
    if not _valid_factory_import(integration_import):
        return None
    conversation_import = backend.get("conversation_provider_import")
    if not _valid_factory_import(conversation_import):
        logger.warning("Invalid conversation provider import for module %s", module_id)
        return None
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
        conversation_provider_import=conversation_import,
        integration_provider_import=integration_import,
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

    if not isinstance(payload, dict):
        errors.append(
            "invalid optional module manifest (must be JSON object): "
            + str(manifest_path)
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
    integration_import = backend.get("integration_provider_import")
    if not _valid_factory_import(integration_import):
        errors.append(
            "invalid optional module integration_provider_import: " + module_id
        )
    conversation_import = backend.get("conversation_provider_import")
    if not _valid_factory_import(conversation_import):
        errors.append(
            "invalid optional module conversation_provider_import: " + module_id
        )
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


def _candidate_manifest(
    item: str, record: dict[str, Any], seen_modules: set[str], settings: object
) -> ApiModuleManifest | None:
    entry_settings = type("ModuleSettings", (), {"API_OPTIONAL_MODULES": item})()
    if validate_optional_modules_config(entry_settings):
        record["state"], record["reason_code"] = "unavailable", "invalid_manifest"
        return None
    manifest = _parse_manifest_file(item)
    if manifest is None:
        record["state"], record["reason_code"] = "unavailable", "invalid_manifest"
        return None
    if manifest.module_id in seen_modules:
        record["module_id"] = manifest.module_id
        record["state"], record["reason_code"] = "unavailable", "duplicate_module"
        return None
    seen_modules.add(manifest.module_id)
    if not _is_enabled(manifest, settings):
        record["state"], record["reason_code"] = "disabled", "feature_disabled"
        return None
    if not _is_compatible(manifest, settings):
        record["state"], record["reason_code"] = "unavailable", "incompatible_module"
        return None
    return manifest


def _register_optional_router(
    app: FastAPI, manifest: ApiModuleManifest, record: dict[str, Any]
) -> bool:
    router = _load_router(manifest.router_import, manifest.module_root)
    if router is None:
        record["state"], record["reason_code"] = "unavailable", "router_import_failed"
        return False
    previous_routes = list(app.router.routes)
    try:
        include_isolated_router(app, router, record)
    except Exception:
        app.router.routes[:] = previous_routes
        record["state"], record["reason_code"] = (
            "unavailable",
            "router_registration_failed",
        )
        return False
    record.update(
        integration_provider_import=manifest.integration_provider_import,
        module_root=manifest.module_root,
        state="loaded",
        reason_code="router_loaded",
    )
    return True


def include_optional_api_routers(
    app: FastAPI, settings: object = SETTINGS
) -> list[str]:
    included: list[str] = []
    diagnostics = []
    seen_modules: set[str] = set()
    for item, record in module_candidates(settings):
        diagnostics.append(record)
        manifest = _candidate_manifest(item, record, seen_modules, settings)
        if manifest is not None and _register_optional_router(app, manifest, record):
            included.append(manifest.module_id)
    app.state.optional_module_diagnostics = diagnostics
    if included:
        logger.info("Included optional API modules: %s", ", ".join(included))
    _install_conversation_provider_lifespan(app, settings)
    return included


def _eligible_conversation_manifests(
    settings: object, diagnostics: list[dict[str, Any]] | None
) -> Iterable[ApiModuleManifest]:
    eligible = None
    if diagnostics is not None:
        eligible = {
            (entry["module_id"], entry.get("module_root"))
            for entry in diagnostics
            if entry["state"] == "loaded"
        }
    for manifest in iter_api_module_manifests(settings):
        if not manifest.conversation_provider_import:
            continue
        if (
            eligible is not None
            and (manifest.module_id, manifest.module_root) not in eligible
        ):
            continue
        if _is_enabled(manifest, settings) and _is_compatible(manifest, settings):
            yield manifest


def _load_conversation_factory(manifest: ApiModuleManifest) -> Callable[[Any], Any]:
    root = str(Path(manifest.module_root).resolve()) if manifest.module_root else None
    inserted = bool(root and root not in sys.path)
    if inserted:
        assert root is not None
        sys.path.insert(0, root)
    try:
        assert manifest.conversation_provider_import is not None
        module_path, name = manifest.conversation_provider_import.split(":")
        factory = getattr(importlib.import_module(module_path), name)
        if not callable(factory):
            raise ValueError("invalid_conversation_provider_factory")
        return factory
    finally:
        if inserted and root in sys.path:
            sys.path.remove(root)


def _record_import_failure(
    module_id: str, diagnostics: list[dict[str, Any]] | None
) -> None:
    logger.warning("Optional conversation provider import failed: %s", module_id)
    for entry in diagnostics or []:
        if entry["module_id"] == module_id and entry["state"] == "loaded":
            entry["conversation_error"] = "provider_import_failed"
            entry["conversation_retry_after"] = time.monotonic() + 30.0


def _conversation_provider_factories(
    settings: object, diagnostics: list[dict[str, Any]] | None = None
) -> dict[str, Callable[[Any], Any]]:
    factories = {}
    for manifest in _eligible_conversation_manifests(settings, diagnostics):
        diagnostic = next(
            (
                entry
                for entry in diagnostics or []
                if entry["module_id"] == manifest.module_id
                and entry["state"] == "loaded"
            ),
            None,
        )
        if (
            diagnostic
            and diagnostic.get("conversation_retry_after", 0) > time.monotonic()
        ):
            continue
        try:
            factory = _load_conversation_factory(manifest)
        except Exception:
            _record_import_failure(manifest.module_id, diagnostics)
            continue
        factories[manifest.module_id] = factory
        if diagnostic:
            diagnostic.pop("conversation_error", None)
            diagnostic.pop("conversation_retry_after", None)
    return factories


def _install_conversation_provider_lifespan(app: FastAPI, settings: object) -> None:
    from venom_core.services.conversation_providers import (
        ConversationProviderRegistry,
        set_conversation_registry,
    )

    if getattr(app.state, "conversation_provider_lifespan_installed", False):
        return
    app.state.conversation_provider_lifespan_installed = True
    app.state.conversation_providers = None
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application) as state:
            registry = ConversationProviderRegistry(
                application,
                factories=lambda: _conversation_provider_factories(
                    settings,
                    getattr(application.state, "optional_module_diagnostics", None),
                ),
                isolate_failures=True,
            )
            application.state.conversation_providers = registry
            previous = None
            installed = False
            try:
                await registry.refresh()
                previous = set_conversation_registry(registry)
                installed = True
                yield state
            finally:
                if installed:
                    set_conversation_registry(
                        previous
                        if previous is not None and not previous.closed
                        else None
                    )
                await registry.close()

    app.router.lifespan_context = lifespan
