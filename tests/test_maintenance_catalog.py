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


def test_local_extensions_preserve_frozen_catalog_and_same_thirty_cases():
    from venom_core.services.maintenance_comparison.catalog import load_all_models

    root = Path(__file__).resolve().parents[1] / "config/maintenance_comparison"
    frozen, cases = load_catalog(root)
    models, expanded_cases = load_all_models(root)
    assert len(models) == 4
    assert {m["id"] for m in models} == {
        "mini-coder-1.7b",
        "granite-4.2-3b",
        "gemma-4-e2b-it",
        "qwen3.5-9b",
    }
    assert len(baseline(models, cases)) == 120
    assert len(frozen) == 8
    assert expanded_cases == cases
    extra = [
        model for model in models if model["id"] not in {item["id"] for item in frozen}
    ]
    assert {model["id"] for model in extra} == {"gemma-4-e2b-it", "qwen3.5-9b"}
    assert len(baseline(extra, cases)) == 60
    assert all(len(model["revision"]) == 40 for model in extra)


def test_missing_optional_catalog_retains_eight_models(tmp_path):
    import shutil

    from venom_core.services.maintenance_comparison.catalog import load_all_models

    root = Path(__file__).resolve().parents[1] / "config/maintenance_comparison"
    for name in ["models.json", "scenarios.json"]:
        shutil.copyfile(root / name, tmp_path / name)
    assert len(load_all_models(tmp_path)[0]) == 8


@pytest.mark.parametrize("failure", ["count", "duplicate"])
def test_extension_catalog_rejects_inconsistent_or_duplicate_profiles(
    tmp_path, failure
):
    import shutil

    from venom_core.services.maintenance_comparison.catalog import load_all_models

    root = Path(__file__).resolve().parents[1] / "config/maintenance_comparison"
    for name in ["models.json", "scenarios.json", "additional_models.json"]:
        shutil.copyfile(root / name, tmp_path / name)
    path = tmp_path / "additional_models.json"
    data = json.loads(path.read_text())
    if failure == "count":
        data["expected_model_count"] = 3
    else:
        data["models"][0]["id"] = "mini-coder-1.7b"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_all_models(tmp_path)


@pytest.mark.parametrize("selection", [{}, {"unknown": {}}, []])
def test_active_catalog_rejects_empty_or_unknown_models(tmp_path, selection):
    import shutil

    from venom_core.services.maintenance_comparison.catalog import load_all_models

    for name in ["models.json", "scenarios.json"]:
        shutil.copyfile(CATALOG / name, tmp_path / name)
    (tmp_path / "active_models.json").write_text(
        json.dumps({"schema_version": 1, "profile": "test", "models": selection})
    )
    with pytest.raises(ValueError, match="invalid_active_model_selection"):
        load_all_models(tmp_path)


def test_retirement_preserves_historical_profiles_without_enabling_downloads():
    from venom_core.services.maintenance_comparison.catalog import load_all_models

    historical, _ = load_catalog(CATALOG)
    active, _ = load_all_models(CATALOG)
    assert "codescout-4b" in {m["id"] for m in historical}
    assert "codescout-4b" not in {m["id"] for m in active}
    assert all(m["profile"]["attention_implementation"] == "sdpa" for m in active)
    assert all(m["profile"]["use_cache"] for m in active)
    assert (
        next(m for m in active if m["id"] == "qwen3.5-9b")["profile"]["kernel_profile"]
        == "qwen35-deltanet-v1"
    )
