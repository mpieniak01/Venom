"""Public metadata for optional modules, without importing their packages."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def module_candidates(settings: object) -> list[tuple[str, dict[str, Any]]]:
    """Report configured entries even when their package/manifest has disappeared.

    Never expose the configuration entry, filesystem path or exception to clients.
    The digest keeps unavailable entries stable without disclosing private paths.
    """
    entries = str(getattr(settings, "API_OPTIONAL_MODULES", "") or "").split(",")
    result = []
    seen = set()
    for raw in entries:
        item = raw.strip()
        if not item or item in seen:
            continue
        seen.add(item)
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
        if item.startswith("manifest:") or item.endswith(".json"):
            path = Path(item.removeprefix("manifest:")).expanduser()
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            if isinstance(data, dict):
                module_id = data.get("module_id")
                if isinstance(module_id, str) and re.fullmatch(
                    r"[A-Za-z0-9_-]{1,80}", module_id
                ):
                    record["module_id"] = module_id
                    label = data.get("display_name")
                    record["display_name"] = (
                        label[:120] if isinstance(label, str) else module_id
                    )
                frontend = data.get("frontend")
                nav = frontend.get("nav_path") if isinstance(frontend, dict) else None
                if isinstance(nav, str) and re.fullmatch(
                    r"/[a-zA-Z0-9][a-zA-Z0-9/_-]*", nav
                ):
                    flag = (
                        frontend.get("feature_flag")
                        if isinstance(frontend, dict)
                        else None
                    )
                    if not flag or (
                        isinstance(flag, str)
                        and os.getenv(flag, "").lower() in {"1", "true", "yes", "on"}
                    ):
                        record["nav_path"] = nav
                record["state"] = "unverified"
                record["reason_code"] = "activation_not_observed"
        result.append((item, record))
    return result
