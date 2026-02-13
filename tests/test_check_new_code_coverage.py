from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "check_new_code_coverage.py"
    )
    spec = importlib.util.spec_from_file_location(
        "check_new_code_coverage", script_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summary_payload_contains_uncovered_lines():
    module = _load_module()
    rows = [
        module.FileCoverage(
            path="venom_core/core/x.py",
            covered=1,
            total=3,
            uncovered_lines=[12, 13],
        )
    ]
    payload = module._summary_payload(
        per_file=rows,
        total_covered=1,
        total_coverable=3,
        min_coverage=80.0,
    )
    assert payload["pass"] is False
    assert payload["uncovered_files"][0]["path"] == "venom_core/core/x.py"
    assert payload["uncovered_files"][0]["uncovered_lines"] == [12, 13]
