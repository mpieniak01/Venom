from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path("scripts/check_optional_modules_contracts.py")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_manifest(
    module_dir: Path, *, router_import: str, include_data_policy: bool = True
) -> Path:
    backend: dict[str, object] = {
        "router_import": router_import,
    }
    if include_data_policy:
        backend["data_policy"] = {
            "storage_mode": "core_prefixed",
            "mutation_guard": "core_environment_policy",
            "state_files": ["runtime-state.json"],
        }
    manifest = module_dir / "module.json"
    manifest.write_text(
        json.dumps({"module_id": "x_module", "backend": backend}),
        encoding="utf-8",
    )
    return manifest


def _run_check(manifest: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{REPO_ROOT}:{existing}" if existing else str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
        env=env,
    )


def test_optional_modules_contracts_guard_passes_for_valid_router(
    tmp_path: Path,
) -> None:
    module_dir = tmp_path / "x-module"
    routes_file = module_dir / "x_module" / "api" / "routes.py"
    routes_file.parent.mkdir(parents=True)
    routes_file.write_text(
        "\n".join(
            [
                "from fastapi import APIRouter, Request",
                "from venom_core.core.module_data_policy import ensure_module_mutation_allowed",
                "router = APIRouter()",
                "def _guard(request: Request) -> None:",
                "    ensure_module_mutation_allowed(module_id='x_module', operation_name='x')",
                "@router.post('/mutate')",
                "async def mutate() -> dict[str, bool]:",
                "    return {'ok': True}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = _write_manifest(module_dir, router_import="x_module.api.routes:router")

    result = _run_check(manifest)
    assert result.returncode == 0
    assert "passed" in result.stdout.lower()


def test_optional_modules_contracts_guard_fails_without_data_policy(
    tmp_path: Path,
) -> None:
    module_dir = tmp_path / "x-module"
    routes_file = module_dir / "x_module" / "api" / "routes.py"
    routes_file.parent.mkdir(parents=True)
    routes_file.write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "router = APIRouter()",
                "@router.get('/health')",
                "async def health() -> dict[str, bool]:",
                "    return {'ok': True}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = _write_manifest(
        module_dir,
        router_import="x_module.api.routes:router",
        include_data_policy=False,
    )

    result = _run_check(manifest)
    assert result.returncode == 1
    assert "backend.data_policy" in result.stdout


def test_optional_modules_contracts_guard_fails_when_mutation_guard_missing(
    tmp_path: Path,
) -> None:
    module_dir = tmp_path / "x-module"
    routes_file = module_dir / "x_module" / "api" / "routes.py"
    routes_file.parent.mkdir(parents=True)
    routes_file.write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "router = APIRouter()",
                "@router.post('/mutate')",
                "async def mutate() -> dict[str, bool]:",
                "    return {'ok': True}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = _write_manifest(module_dir, router_import="x_module.api.routes:router")

    result = _run_check(manifest)
    assert result.returncode == 1
    assert "does not call ensure_module_mutation_allowed" in result.stdout
