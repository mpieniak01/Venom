"""Public metadata for optional modules, without importing their packages."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from types import SimpleNamespace
from typing import Any

MANIFEST_PREFIX = "manifest:"


def _manifest_payload(path):
    try:
        if path.stat().st_size > 256 * 1024:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _frontend_path(frontend):
    if not isinstance(frontend, dict):
        return None
    nav = frontend.get("nav_path")
    if (
        not isinstance(nav, str)
        or re.fullmatch(r"/[a-zA-Z0-9][a-zA-Z0-9/_-]*", nav) is None
    ):
        return None
    flag = frontend.get("feature_flag")
    if flag and (
        not isinstance(flag, str)
        or os.getenv(flag, "").lower() not in {"1", "true", "yes", "on"}
    ):
        return None
    return nav


def _manifest_record(item):
    opaque_id = "unavailable-" + hashlib.sha256(item.encode()).hexdigest()[:12]
    record: dict[str, Any] = {
        "module_id": opaque_id,
        "entry_id": opaque_id,
        "display_name": opaque_id,
        "state": "unavailable",
        "reason_code": "manifest_unavailable",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "nav_path": None,
        "integration_provider_import": None,
    }
    if not (item.startswith(MANIFEST_PREFIX) or item.endswith(".json")):
        return record
    data = _manifest_payload(Path(item.removeprefix(MANIFEST_PREFIX)).expanduser())
    if data is None:
        return record
    module_id = data.get("module_id")
    if isinstance(module_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", module_id):
        record["module_id"] = module_id
        label = data.get("display_name")
        record["display_name"] = label[:120] if isinstance(label, str) else module_id
    record["nav_path"] = _frontend_path(data.get("frontend"))
    record["state"], record["reason_code"] = "unverified", "activation_not_observed"
    return record


def module_candidates(settings: object) -> list[tuple[str, dict[str, Any]]]:
    """Read bounded local manifests, never exposing paths or importing packages."""
    entries = str(getattr(settings, "API_OPTIONAL_MODULES", "") or "").split(",")
    items = dict.fromkeys(item.strip() for item in entries if item.strip())
    return [(item, _manifest_record(item)) for item in items]


def module_inventory(settings: object, activated=None):
    """Join runtime activation with bounded local discovery; never import packages."""
    records = (
        list(activated)
        if activated is not None
        else [record for _, record in module_candidates(settings)]
    )
    known = {record["module_id"] for record in records}
    paths = list(islice((Path.cwd() / "modules").glob("*/module.json"), 64))
    metadata_settings = SimpleNamespace(
        API_OPTIONAL_MODULES=",".join(
            MANIFEST_PREFIX + str(path.resolve()) for path in paths
        )
    )
    for _, record in module_candidates(metadata_settings):
        if record["module_id"] in known:
            continue
        known.add(record["module_id"])
        record.update(
            state="disabled",
            reason_code="module_not_registered",
            backend_configured=False,
        )
        records.append(record)
    return records
