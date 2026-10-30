"""One environment-scoped root for mutable provider state.

The historical development root is preserved; no state or credentials are copied.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_runtime_state_root(
    project_root: Path,
    *,
    environment_role: str = "dev",
    storage_prefix: str = "",
    override: str = "",
) -> Path:
    root = project_root.resolve()
    role = environment_role.strip().lower()
    if role not in {"dev", "preprod", "prod"}:
        raise ValueError("Runtime state requires dev|preprod|prod environment")
    legacy = root / ".venom_runtime"
    if override:
        configured = Path(override).expanduser()
        selected = (
            configured if configured.is_absolute() else root / configured
        ).resolve()
        if role != "dev" and (
            selected == legacy.resolve() or selected in legacy.resolve().parents
        ):
            raise ValueError("Runtime state overlaps the development root")
        return selected
    if role == "dev":
        return legacy
    prefix = storage_prefix.strip() or role
    if not all(char.isalnum() or char in {"-", "_"} for char in prefix):
        raise ValueError("Runtime state namespace must be a single directory name")
    selected = (legacy / prefix).resolve()
    if selected == legacy.resolve() or selected in legacy.resolve().parents:
        raise ValueError("Runtime state overlaps the development root")
    return selected


def runtime_state_root(project_root: Path | None = None) -> Path:
    # Imported lazily so the pure path resolver can also be used before bootstrap.
    from venom_core.config import SETTINGS

    return resolve_runtime_state_root(
        project_root or Path(__file__).resolve().parents[2],
        environment_role=str(SETTINGS.ENVIRONMENT_ROLE),
        storage_prefix=str(SETTINGS.STORAGE_PREFIX),
        override=os.environ.get("VENOM_RUNTIME_STATE_ROOT", "")
        or str(getattr(SETTINGS, "VENOM_RUNTIME_STATE_ROOT", "")),
    )
