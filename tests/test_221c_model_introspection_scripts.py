"""Tests for 221C model introspection script."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts" / "dev"


def _load_script(module_name: str, filename: str) -> ModuleType:
    path = SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe_script = _load_script(
    "test_221c_model_introspection_probe", "221c_model_introspection_probe.py"
)


def test_221c_probe_script_writes_analysis_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    payload = {
        "success": True,
        "snapshot": {
            "status": "skipped",
            "analysis": None,
            "skipped_reason": "live_analysis_disabled",
        },
    }
    calls: list[dict[str, object]] = []

    def fake_request_json(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return 200, payload

    monkeypatch.setattr(probe_script, "request_json", fake_request_json)
    monkeypatch.setattr(
        probe_script,
        "base_url_from_env",
        lambda default: "http://127.0.0.1:8000",
    )
    out = tmp_path / "analysis.json"
    with patch.object(
        probe_script.sys,
        "argv",
        ["probe", "--output", str(out)],
    ):
        assert probe_script.main() == 0

    assert (
        calls[0]["url"] == "http://127.0.0.1:8000/api/v1/models/introspection/analyze"
    )
    assert calls[0]["method"] == "POST"
    assert calls[0]["payload"]["live_analysis_enabled"] is False
    assert json.loads(out.read_text(encoding="utf-8")) == payload
