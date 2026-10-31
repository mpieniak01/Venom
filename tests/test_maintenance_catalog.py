"""The baseline counts and pinned model identities are executable contracts."""

import json
from collections import Counter
from pathlib import Path

import pytest

from venom_core.services.maintenance_comparison.catalog import baseline, load_catalog

CATALOG = Path(__file__).resolve().parents[1] / "config/maintenance_comparison"


def test_baseline_has_180_planned_rows_and_correct_role_denominators():
    models, cases = load_catalog(CATALOG)
    plan = baseline(models, cases)
    assert len(plan) == 180
    assert Counter(row["role"] for row in plan) == {
        "operator": 70,
        "repair": 50,
        "localization": 60,
    }
    assert {row["status"] for row in plan} == {"planned"}
    assert sum(c["repairable"] for c in cases) == 8


@pytest.mark.parametrize(
    "kind", ["sha", "model_count", "case_count", "duplicate_case", "role"]
)
def test_catalog_rejects_ambiguous_or_incomplete_configuration(tmp_path, kind):
    models = json.loads((CATALOG / "models.json").read_text())
    cases = json.loads((CATALOG / "scenarios.json").read_text())
    if kind == "sha":
        models["models"][0]["revision"] = "main"
    if kind == "model_count":
        models["models"].pop()
    if kind == "case_count":
        cases["cases"].pop()
    if kind == "duplicate_case":
        cases["cases"][0]["id"] = cases["cases"][1]["id"]
    if kind == "role":
        models["models"][0]["roles"] = ["unknown"]
    (tmp_path / "models.json").write_text(json.dumps(models))
    (tmp_path / "scenarios.json").write_text(json.dumps(cases))
    with pytest.raises(ValueError):
        load_catalog(tmp_path)
