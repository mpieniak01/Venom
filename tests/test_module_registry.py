from __future__ import annotations

import types

from fastapi import APIRouter, FastAPI

from venom_core.services import module_registry


class _Settings:
    FEATURE_MODULE_EXAMPLE = False
    API_OPTIONAL_MODULES = ""


def test_builtin_manifest_has_module_example():
    manifests = list(module_registry.iter_api_module_manifests(_Settings()))
    assert any(m.module_id == "module_example" for m in manifests)


def test_include_optional_api_routers_respects_feature_flag():
    app = FastAPI()
    included = module_registry.include_optional_api_routers(app, _Settings())
    assert included == []


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
