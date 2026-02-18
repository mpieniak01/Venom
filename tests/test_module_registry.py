from __future__ import annotations

import json
import types

from fastapi import APIRouter, FastAPI

from venom_core.services import module_registry


class _Settings:
    FEATURE_MODULE_EXAMPLE = False
    API_OPTIONAL_MODULES = ""
    CORE_MODULE_API_VERSION = "1"
    CORE_RUNTIME_VERSION = "1.5.0"


def test_builtin_manifest_is_empty_by_default():
    manifests = list(module_registry.iter_api_module_manifests(_Settings()))
    assert manifests == []


def test_include_optional_api_routers_respects_feature_flag():
    app = FastAPI()
    included = module_registry.include_optional_api_routers(app, _Settings())
    assert included == []
    assert all("/api/v1/module-example" not in route.path for route in app.routes)


def test_core_boot_without_optional_modules_keeps_core_routes_only():
    app = FastAPI()

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    included = module_registry.include_optional_api_routers(app, _Settings())
    paths = {route.path for route in app.routes}

    assert included == []
    assert "/healthz" in paths
    assert all("/api/v1/module-example" not in path for path in paths)


def test_include_optional_api_routers_includes_module_from_manifest_file(
    monkeypatch, tmp_path
):
    router = APIRouter(prefix="/module-example")

    @router.get("/health")
    async def health():
        return {"ok": True}

    module = types.ModuleType("x_module_example")
    module.router = router

    def _fake_import(name: str):
        if name == "x_module_example":
            return module
        return __import__(name)

    monkeypatch.setattr(module_registry.importlib, "import_module", _fake_import)

    manifest_path = tmp_path / "module.json"
    manifest_path.write_text(
        json.dumps(
            {
                "module_id": "module_example",
                "backend": {
                    "router_import": "x_module_example:router",
                    "feature_flag": "FEATURE_MODULE_EXAMPLE",
                    "module_api_version": 1,
                    "min_core_version": "1.5.0",
                },
            }
        ),
        encoding="utf-8",
    )
    settings = _Settings()
    settings.FEATURE_MODULE_EXAMPLE = True
    settings.API_OPTIONAL_MODULES = f"manifest:{manifest_path}"
    app = FastAPI()

    included = module_registry.include_optional_api_routers(app, settings)
    assert "module_example" in included
    assert any("/module-example/health" == route.path for route in app.routes)


def test_include_optional_api_routers_loads_extra_manifest(monkeypatch):
    router = APIRouter(prefix="/x-test")

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    module = types.ModuleType("x_test_mod")
    module.router = router

    def _fake_import(name: str):
        if name == "x_test_mod":
            return module
        return __import__(name)

    monkeypatch.setattr(module_registry.importlib, "import_module", _fake_import)

    settings = _Settings()
    settings.API_OPTIONAL_MODULES = "x_test|x_test_mod:router"

    app = FastAPI()
    included = module_registry.include_optional_api_routers(app, settings)
    assert "x_test" in included

    paths = {route.path for route in app.routes}
    assert "/x-test/ping" in paths


def test_core_boot_with_one_optional_module_manifest(monkeypatch):
    router = APIRouter(prefix="/mod-one")

    @router.get("/status")
    async def status():
        return {"ok": True}

    module = types.ModuleType("x_mod_one")
    module.router = router

    def _fake_import(name: str):
        if name == "x_mod_one":
            return module
        return __import__(name)

    monkeypatch.setattr(module_registry.importlib, "import_module", _fake_import)

    settings = _Settings()
    settings.API_OPTIONAL_MODULES = "mod_one|x_mod_one:router"
    app = FastAPI()

    included = module_registry.include_optional_api_routers(app, settings)
    paths = {route.path for route in app.routes}

    assert included == ["mod_one"]
    assert "/mod-one/status" in paths


def test_include_optional_api_routers_skips_api_version_mismatch(monkeypatch):
    router = APIRouter(prefix="/x-test")

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    module = types.ModuleType("x_test_mod_v2")
    module.router = router

    def _fake_import(name: str):
        if name == "x_test_mod_v2":
            return module
        return __import__(name)

    monkeypatch.setattr(module_registry.importlib, "import_module", _fake_import)

    settings = _Settings()
    settings.API_OPTIONAL_MODULES = "x_test|x_test_mod_v2:router||2|1.5.0"

    app = FastAPI()
    included = module_registry.include_optional_api_routers(app, settings)
    assert included == []


def test_include_optional_api_routers_skips_when_core_too_old(monkeypatch):
    router = APIRouter(prefix="/x-test")

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    module = types.ModuleType("x_test_mod_core")
    module.router = router

    def _fake_import(name: str):
        if name == "x_test_mod_core":
            return module
        return __import__(name)

    monkeypatch.setattr(module_registry.importlib, "import_module", _fake_import)

    settings = _Settings()
    settings.CORE_RUNTIME_VERSION = "1.5.0"
    settings.API_OPTIONAL_MODULES = "x_test|x_test_mod_core:router|||2.0.0"

    app = FastAPI()
    included = module_registry.include_optional_api_routers(app, settings)
    assert included == []


def test_validate_optional_modules_config_returns_errors():
    settings = _Settings()
    settings.API_OPTIONAL_MODULES = "broken_entry,no_colon|module.path"
    errors = module_registry.validate_optional_modules_config(settings)
    assert len(errors) == 2


def test_include_optional_api_routers_loads_manifest_path(monkeypatch, tmp_path):
    router = APIRouter(prefix="/mod-manifest")

    @router.get("/health")
    async def health():
        return {"ok": True}

    module = types.ModuleType("x_mod_manifest")
    module.router = router

    def _fake_import(name: str):
        if name == "x_mod_manifest":
            return module
        return __import__(name)

    monkeypatch.setattr(module_registry.importlib, "import_module", _fake_import)

    manifest_path = tmp_path / "module.json"
    manifest_path.write_text(
        json.dumps(
            {
                "module_id": "mod_manifest",
                "backend": {
                    "router_import": "x_mod_manifest:router",
                    "module_api_version": 1,
                    "min_core_version": "1.5.0",
                },
            }
        ),
        encoding="utf-8",
    )

    settings = _Settings()
    settings.API_OPTIONAL_MODULES = str(manifest_path)
    app = FastAPI()
    included = module_registry.include_optional_api_routers(app, settings)

    assert "mod_manifest" in included
    assert any(route.path == "/mod-manifest/health" for route in app.routes)


def test_validate_optional_modules_config_manifest_missing_file():
    settings = _Settings()
    settings.API_OPTIONAL_MODULES = "manifest:/tmp/not-existing-module.json"
    errors = module_registry.validate_optional_modules_config(settings)
    assert len(errors) == 1
    assert "manifest not found" in errors[0]
