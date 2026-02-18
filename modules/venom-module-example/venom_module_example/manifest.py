"""Module Example manifest metadata helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModuleExampleManifest:
    module_id: str
    display_name: str
    schema_version: int
    enabled_by_default: bool
    backend: dict[str, Any]
    frontend: dict[str, Any]


def load_manifest() -> ModuleExampleManifest:
    """Load canonical metadata from module.json."""
    package_dir = Path(__file__).resolve().parent
    candidates = [
        package_dir / "module.json",
        package_dir.parent / "module.json",
    ]
    manifest_path = next((path for path in candidates if path.exists()), None)
    if manifest_path is None:
        raise FileNotFoundError("module.json not found in package or module root")
    raw = json.loads(manifest_path.read_text())
    return ModuleExampleManifest(
        module_id=str(raw.get("module_id", "module_example")),
        display_name=str(raw.get("display_name", "Module Example")),
        schema_version=int(raw.get("schema_version", 1)),
        enabled_by_default=bool(raw.get("enabled_by_default", False)),
        backend=dict(raw.get("backend") or {}),
        frontend=dict(raw.get("frontend") or {}),
    )


MANIFEST = load_manifest()
