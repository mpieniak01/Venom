#!/usr/bin/env python3
"""Check committed core OpenAPI/types and the shared Studio HTTP contract."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.export_openapi import export_schema, write_schema  # noqa: E402


def studio_contract_errors(core: dict[str, Any], studio: dict[str, Any]) -> list[str]:
    """Require every Studio operation and component to match the Full contract."""
    errors = []
    for path, operations in studio["paths"].items():
        for method, operation in operations.items():
            if core["paths"].get(path, {}).get(method) != operation:
                errors.append(f"Studio/Full operation differs: {method.upper()} {path}")
    for category, components in studio.get("components", {}).items():
        for name, component in components.items():
            if core.get("components", {}).get(category, {}).get(name) != component:
                errors.append(f"Studio/Full component differs: {category}/{name}")
    if core.get("security") != studio.get("security"):
        errors.append("Studio/Full global security differs")
    return errors


def generate_types(schema: Path, output: Path) -> None:
    """Run the lockfile-pinned local generator without npx downloads."""
    cli = REPO_ROOT / "web-next/node_modules/openapi-typescript/bin/cli.js"
    subprocess.run(
        ["node", str(cli), str(schema), "-o", str(output)],
        cwd=REPO_ROOT,
        check=True,
        timeout=90,
    )


def files_match(expected: Path, actual: Path) -> bool:
    """Compare JSON semantically and generated TypeScript byte for byte."""
    if not expected.is_file():
        return False
    if expected.suffix == ".json":
        try:
            expected_json = json.loads(expected.read_text(encoding="utf-8"))
            actual_json = json.loads(actual.read_text(encoding="utf-8"))
            # Python equality conflates JSON booleans and numbers (True == 1).
            return json.dumps(expected_json, sort_keys=True) == json.dumps(
                actual_json, sort_keys=True
            )
        except (ValueError, UnicodeError):
            return False
    return expected.read_bytes() == actual.read_bytes()


def check_contract(directory: Path, *, update: bool = False) -> int:
    """Generate into artifacts first; checks never modify tracked files."""
    schema_path = directory / "openapi.json"
    types_path = directory / "api-types.d.ts"
    protected = {
        (REPO_ROOT / "openapi/openapi.json").resolve(),
        (REPO_ROOT / "web-next/lib/generated/api-types.d.ts").resolve(),
    }
    if any(
        path.resolve() in protected
        for path in (schema_path, types_path, directory / "studio.json")
    ):
        raise ValueError("Artifact directory must not overwrite committed contracts")
    core = export_schema("core")
    studio = export_schema("studio")
    write_schema(core, schema_path)
    write_schema(studio, directory / "studio.json")
    errors = studio_contract_errors(core, studio)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    generate_types(schema_path, types_path)
    targets = (
        (REPO_ROOT / "openapi/openapi.json", schema_path),
        (REPO_ROOT / "web-next/lib/generated/api-types.d.ts", types_path),
    )
    for expected, actual in targets:
        if update:
            expected.parent.mkdir(parents=True, exist_ok=True)
            expected.write_bytes(actual.read_bytes())
        elif not files_match(expected, actual):
            errors.append(
                f"Stale or missing contract: {expected.relative_to(REPO_ROOT)}"
            )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        print(
            "Run make openapi-codegen-types and commit both generated files.",
            file=sys.stderr,
        )
        return 1
    print(
        "OpenAPI core/types and Studio parity: PASS" + (" (updated)" if update else "")
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Expose one check/update workflow to local gates and CI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=REPO_ROOT / "test-results/openapi"
    )
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args(argv)
    try:
        return check_contract(args.output_dir.resolve(), update=args.update)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"OpenAPI contract generation failed: {exc}", file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
