"""Validated experiment inputs; planned rows never masquerade as results."""

import json
from collections import Counter
from pathlib import Path

ROLES = {"operator": 8, "repair": 20, "localization": 12}


def load_catalog(root: Path) -> tuple[list[dict], list[dict]]:
    models = json.loads((root / "models.json").read_text())["models"]
    cases = json.loads((root / "scenarios.json").read_text())["cases"]
    if len(models) != 8 or len({m["id"] for m in models}) != 8:
        raise ValueError("eight_unique_models_required")
    for model in models:
        sha = model["revision"]
        if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("checkpoint_revision_required")
        if not model["roles"] or not set(model["roles"]) <= ROLES.keys():
            raise ValueError("invalid_model_roles")
    if Counter(c["role"] for c in cases) != {r: 10 for r in ROLES}:
        raise ValueError("ten_cases_per_role_required")
    if len({c["id"] for c in cases}) != 30:
        raise ValueError("unique_case_ids_required")
    return models, cases


def baseline(models: list[dict], cases: list[dict]) -> list[dict]:
    return [
        {
            "model": m["id"],
            "revision": m["revision"],
            "case": c["id"],
            "role": c["role"],
            "status": "planned",
        }
        for m in models
        for c in cases
        if c["role"] in m["roles"]
    ]
