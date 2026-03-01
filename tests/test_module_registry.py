from __future__ import annotations

import json
import types
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI

from venom_core.services import module_registry


class _Settings:
    FEATURE_MODULE_EXAMPLE = False
    FEATURE_TEST = False
    API_OPTIONAL_MODULES = ""
    CORE_MODULE_API_VERSION = "1.0.0"
    CORE_RUNTIME_VERSION = "1.5.0"


def _write_manifest(
    path: Path,
    *,
    module_id: str,
    router_import: str,
    feature_flag: str | None = None,
    module_api_version: str = "1.0.0",
    min_core_version: str = "1.5.0",
    include_data_policy: bool = True,
) -> None:
    backend: dict[str, object] = {
        "router_import": router_import,
        "module_api_version": module_api_version,
        "min_core_version": min_core_version,
    }
    if feature_flag:
        backend["feature_flag"] = feature_flag
    if include_data_policy:
        backend["data_policy"] = {
            "storage_mode": "core_prefixed",
            "mutation_guard": "core_environment_policy",
            "state_files": ["runtime-state.json"],
        }
    path.write_text(
        json.dumps({"module_id": module_id, "backend": backend}),
        encoding="utf-8",
    )


def test_builtin_manifest_is_empty_by_default() -> None:
    manifests = list(module_registry.iter_api_module_manifests(_Settings()))
    assert manifests == []


def test_include_optional_api_routers_includes_module_from_manifest_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    router = APIRouter(prefix="/module-example")

    @router.get("/health")
    async def _health() -> dict[str, bool]:
        return {"ok": True}

    module = types.ModuleType("x_module_example")
    module.router = router

    def _fake_import(name: str):
        if name == "x_module_example":
            return module
        return __import__(name)

    monkeypatch.setattr(module_registry.importlib, "import_module", _fake_import)

    manifest_path = tmp_path / "module.json"
    _write_manifest(
        manifest_path,
        module_id="module_example",
        router_import="x_module_example:router",
        feature_flag="FEATURE_MODULE_EXAMPLE",
    )
    settings = _Settings()
    settings.FEATURE_MODULE_EXAMPLE = True
    settings.API_OPTIONAL_MODULES = f"manifest:{manifest_path}"

    app = FastAPI()
    included = module_registry.include_optional_api_routers(app, settings)
    assert included == ["module_example"]
    assert any(route.path == "/module-example/health" for route in app.routes)


def test_include_optional_api_routers_respects_feature_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    router = APIRouter(prefix="/x-test")

    @router.get("/ping")
    async def _ping() -> dict[str, bool]:
        return {"ok": True}

    module = types.ModuleType("x_test_mod")
    module.router = router

    def _fake_import(name: str):
        if name == "x_test_mod":
            return module
        return __import__(name)

    monkeypatch.setattr(module_registry.importlib, "import_module", _fake_import)

    manifest_path = tmp_path / "module.json"
    _write_manifest(
        manifest_path,
        module_id="x_test",
        router_import="x_test_mod:router",
        feature_flag="FEATURE_TEST",
    )
    settings = _Settings()
    settings.API_OPTIONAL_MODULES = str(manifest_path)

    app = FastAPI()
    included = module_registry.include_optional_api_routers(app, settings)
    assert included == []


def test_include_optional_api_routers_raises_for_legacy_entry() -> None:
    settings = _Settings()
    settings.API_OPTIONAL_MODULES = "x_test|x_test_mod:router"
    app = FastAPI()

    with pytest.raises(RuntimeError, match="legacy format unsupported"):
        module_registry.include_optional_api_routers(app, settings)


def test_include_optional_api_routers_raises_for_missing_data_policy(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "module.json"
    _write_manifest(
        manifest_path,
        module_id="broken_mod",
        router_import="x_mod:router",
        include_data_policy=False,
    )
    settings = _Settings()
    settings.API_OPTIONAL_MODULES = str(manifest_path)
    app = FastAPI()

    with pytest.raises(RuntimeError, match="backend.data_policy"):
        module_registry.include_optional_api_routers(app, settings)


def test_include_optional_api_routers_skips_api_version_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    router = APIRouter(prefix="/x-test")

    @router.get("/ping")
    async def _ping() -> dict[str, bool]:
        return {"ok": True}

    module = types.ModuleType("x_test_mod_v2")
    module.router = router

    def _fake_import(name: str):
        if name == "x_test_mod_v2":
            return module
        return __import__(name)

    monkeypatch.setattr(module_registry.importlib, "import_module", _fake_import)

    manifest_path = tmp_path / "module.json"
    _write_manifest(
        manifest_path,
        module_id="x_test",
        router_import="x_test_mod_v2:router",
        module_api_version="2.0.0",
    )
    settings = _Settings()
    settings.API_OPTIONAL_MODULES = str(manifest_path)
    app = FastAPI()
    included = module_registry.include_optional_api_routers(app, settings)
    assert included == []


def test_validate_optional_modules_config_manifest_missing_file() -> None:
    settings = _Settings()
    settings.API_OPTIONAL_MODULES = "manifest:/tmp/not-existing-module.json"
    errors = module_registry.validate_optional_modules_config(settings)
    assert len(errors) == 1
    assert "manifest not found" in errors[0]


def test_validate_optional_modules_config_requires_data_policy(tmp_path: Path) -> None:
    manifest_path = tmp_path / "broken.json"
    _write_manifest(
        manifest_path,
        module_id="broken_mod",
        router_import="broken.module:router",
        include_data_policy=False,
    )
    settings = _Settings()
    settings.API_OPTIONAL_MODULES = f"manifest:{manifest_path}"
    errors = module_registry.validate_optional_modules_config(settings)
    assert errors
    assert any("backend.data_policy" in err for err in errors)


def test_load_router_returns_none_for_invalid_router_import() -> None:
    assert module_registry._load_router("not-a-router-import") is None


def test_load_router_returns_none_when_attr_is_not_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("x_invalid_router_mod")
    module.not_router = object()

    def _fake_import(name: str):
        if name == "x_invalid_router_mod":
            return module
        return __import__(name)

    monkeypatch.setattr(module_registry.importlib, "import_module", _fake_import)
    assert module_registry._load_router("x_invalid_router_mod:not_router") is None
