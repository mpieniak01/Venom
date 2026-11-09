#!/usr/bin/env python3
"""Export deterministic HTTP contracts without starting application lifespans."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Require explicit destinations for contracts other than the shared core."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", choices=("core", "studio", "module"), default="core"
    )
    parser.add_argument("--module-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if (args.profile == "module") != (args.module_manifest is not None):
        parser.error("--module-manifest is required only for --profile module")
    if args.output is None:
        if args.profile != "core":
            parser.error("--output is required for Studio/module exports")
        args.output = REPO_ROOT / "openapi/openapi.json"
    if (
        args.profile != "core"
        and args.output.resolve() == (REPO_ROOT / "openapi/openapi.json").resolve()
    ):
        parser.error("Studio/module exports cannot overwrite the core contract")
    return args


def isolated_environment(directory: Path) -> dict[str, str]:
    """Do not inherit application flags, credentials, pytest state or dotenv files."""
    environment = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "WINDIR")
        if key in os.environ
    }
    environment.update(
        ENV_FILE=os.devnull,
        API_OPTIONAL_MODULES="",
        HOME=str(directory),
        TMPDIR=str(directory),
        XDG_CACHE_HOME=str(directory / "cache"),
        HF_HUB_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        PYTHONIOENCODING="utf-8",
        PYTHONHASHSEED="0",
    )
    return environment


def module_application(manifest_path: Path) -> Any:
    """Export exactly one validated module, failing if its router cannot load."""
    from fastapi import FastAPI

    from venom_core.services.module_registry import (
        include_optional_api_routers,
        iter_api_module_manifests,
        validate_optional_modules_config,
    )
    from venom_core.version import APP_VERSION

    settings = SimpleNamespace(
        API_OPTIONAL_MODULES="manifest:" + str(manifest_path.resolve()),
        CORE_RUNTIME_VERSION=APP_VERSION,
    )
    errors = validate_optional_modules_config(settings)
    if errors:
        raise ValueError("; ".join(errors))
    manifests = list(iter_api_module_manifests(settings))
    if len(manifests) != 1:
        raise ValueError("Expected exactly one module manifest")
    manifest = manifests[0]
    if manifest.feature_flag:
        setattr(settings, manifest.feature_flag, True)
    app = FastAPI(
        title="Venom module: " + manifest.module_id,
        version=manifest.module_api_version or APP_VERSION,
    )
    if include_optional_api_routers(app, settings) != [manifest.module_id]:
        raise ValueError(f"Module router could not load: {manifest.module_id}")
    return app


def application_schema(profile: str, manifest: Path | None = None) -> dict[str, Any]:
    """Read route metadata only; never enter lifespan or invoke an endpoint."""
    if profile == "core":
        from venom_core.main import app
    elif profile == "studio":
        from venom_core.studio_main import app
    elif profile == "module" and manifest is not None:
        app = module_application(manifest)
    else:
        raise ValueError("Unknown contract profile or missing module manifest")
    return app.openapi()


def export_schema(
    profile: str = "core", manifest: Path | None = None
) -> dict[str, Any]:
    """Import the selected application in a fresh process and temporary workspace."""
    with TemporaryDirectory(prefix="venom-openapi-") as temporary:
        directory = Path(temporary)
        output = directory / "schema.json"
        command = [
            sys.executable,
            "-I",
            str(Path(__file__).resolve()),
            "--worker",
            "--profile",
            profile,
            "--output",
            str(output),
        ]
        if manifest is not None:
            command.extend(("--module-manifest", str(manifest.resolve())))
        subprocess.run(
            command,
            cwd=directory,
            env=isolated_environment(directory),
            check=True,
            timeout=90,
            capture_output=True,
            text=True,
        )
        return json.loads(output.read_text(encoding="utf-8"))


def write_schema(schema: dict[str, Any], output: Path, indent: int = 2) -> None:
    """Preserve deterministic route registration order and schema array order."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=indent) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    """Write an isolated contract and surface exporter failures to quality gates."""
    args = parse_args(argv)
    try:
        schema = (
            application_schema(args.profile, args.module_manifest)
            if args.worker
            else export_schema(args.profile, args.module_manifest)
        )
        write_schema(schema, args.output, args.indent)
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or exc.stdout or str(exc), file=sys.stderr)
        return 1
    print(f"OpenAPI ({args.profile}) exported to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
