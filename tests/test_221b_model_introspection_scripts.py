"""Tests for 221B model introspection scripts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

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
    "test_221b_model_introspection_probe", "221b_model_introspection_probe.py"
)
benchmark_script = _load_script(
    "test_221b_model_introspection_benchmark",
    "221b_model_introspection_benchmark.py",
)


def test_probe_script_writes_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {"success": True, "snapshot": {"summary": {"runtime_label": "x"}}}
    monkeypatch.setattr(
        probe_script,
        "request_json",
        lambda url, **_kwargs: (200, payload),
    )
    out = tmp_path / "snapshot.json"
    monkeypatch.setattr(
        probe_script,
        "base_url_from_env",
        lambda default: "http://127.0.0.1:8000",
    )
    with patch.object(probe_script.sys, "argv", ["probe", "--output", str(out)]):
        assert probe_script.main() == 0
    assert json.loads(out.read_text(encoding="utf-8")) == payload


def test_probe_script_returns_error_on_non_200(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        probe_script, "request_json", lambda url, **_kwargs: (500, {"error": "boom"})
    )
    monkeypatch.setattr(
        probe_script,
        "base_url_from_env",
        lambda default: "http://127.0.0.1:8000",
    )
    out = tmp_path / "snapshot-error.json"
    with patch.object(probe_script.sys, "argv", ["probe", "--output", str(out)]):
        assert probe_script.main() == 1
    assert not out.exists() or out.read_text(encoding="utf-8").strip() == ""


def test_benchmark_script_produces_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "success": True,
        "snapshot": {
            "summary": {"runtime_label": "x", "provider": "local"},
            "available_packages": ["captum"],
        },
    }
    monkeypatch.setattr(
        benchmark_script,
        "request_json",
        lambda url, **_kwargs: (200, payload),
    )
    monkeypatch.setattr(
        benchmark_script,
        "base_url_from_env",
        lambda default: "http://127.0.0.1:8000",
    )
    out = tmp_path / "benchmark.json"
    with patch.object(
        benchmark_script.sys,
        "argv",
        ["benchmark", "--runs", "2", "--output", str(out)],
    ):
        assert benchmark_script.main() == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["runs"] == 2
    assert report["summary"]["payload_bytes_max"] > 0


def test_benchmark_script_returns_error_on_non_200(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        benchmark_script,
        "request_json",
        lambda url, **_kwargs: (500, {"error": "boom"}),
    )
    monkeypatch.setattr(
        benchmark_script,
        "base_url_from_env",
        lambda default: "http://127.0.0.1:8000",
    )
    out = tmp_path / "benchmark-error.json"
    with patch.object(
        benchmark_script.sys,
        "argv",
        ["benchmark", "--runs", "2", "--output", str(out)],
    ):
        assert benchmark_script.main() == 1
    assert not out.exists() or out.read_text(encoding="utf-8").strip() == ""
