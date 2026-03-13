from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.services import module_registry


def _write_manifest(
    path: Path, *, module_id: str, router_import: str, include_data_policy: bool = True
) -> None:
    backend: dict[str, object] = {
        "router_import": router_import,
        "feature_flag": "FEATURE_X_MODULE",
        "module_api_version": "1.0.0",
        "min_core_version": "1.5.0",
    }
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


@pytest.mark.smoke
def test_preprod_optional_modules_manifest_contract_smoke(tmp_path: Path) -> None:
    routes_file = tmp_path / "x_module" / "api" / "routes.py"
    routes_file.parent.mkdir(parents=True)
    routes_file.write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "router = APIRouter(prefix='/x-module')",
                "@router.get('/health')",
                "async def health() -> dict[str, bool]:",
                "    return {'ok': True}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_ok = tmp_path / "module-ok.json"
    _write_manifest(
        manifest_ok,
        module_id="x_module",
        router_import="x_module.api.routes:router",
        include_data_policy=True,
    )

    settings_ok = SimpleNamespace(
        FEATURE_X_MODULE=True,
        API_OPTIONAL_MODULES=f"manifest:{manifest_ok}",
        CORE_MODULE_API_VERSION="1.0.0",
        CORE_RUNTIME_VERSION="1.8.0",
        ENVIRONMENT_ROLE="preprod",
        STORAGE_PREFIX="preprod",
        ALLOW_DATA_MUTATION=False,
    )
    app = FastAPI()
    included = module_registry.include_optional_api_routers(app, settings_ok)
    assert included == ["x_module"]

    health = TestClient(app).get("/x-module/health")
    assert health.status_code == 200
    assert health.json() == {"ok": True}

    manifest_bad = tmp_path / "module-bad.json"
    _write_manifest(
        manifest_bad,
        module_id="x_bad",
        router_import="x_module.api.routes:router",
        include_data_policy=False,
    )
    settings_bad = SimpleNamespace(
        FEATURE_X_MODULE=True,
        API_OPTIONAL_MODULES=f"manifest:{manifest_bad}",
        CORE_MODULE_API_VERSION="1.0.0",
        CORE_RUNTIME_VERSION="1.8.0",
        ENVIRONMENT_ROLE="preprod",
        STORAGE_PREFIX="preprod",
        ALLOW_DATA_MUTATION=False,
    )

    with pytest.raises(RuntimeError, match="backend.data_policy"):
        module_registry.include_optional_api_routers(FastAPI(), settings_bad)
