from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "dev" / "stack_stability_audit.py"
    spec = importlib.util.spec_from_file_location("stack_stability_audit", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_audit_detects_stale_pid_and_missing_manifest(tmp_path: Path):
    module = _load_module()
    (tmp_path / ".venom.pid").write_text("999999\n", encoding="utf-8")
    (tmp_path / ".web-next.pid").write_text("888888\n", encoding="utf-8")
    (tmp_path / ".env.dev").write_text(
        "API_OPTIONAL_MODULES=manifest:/tmp/missing-module.json\n", encoding="utf-8"
    )
    report = module.run_audit(
        root=tmp_path,
        env_file=tmp_path / ".env.dev",
        backend_port=8000,
        web_port=3000,
    )
    assert report["ok"] is False
    assert "api_pid_file_stale" in report["issues"]
    assert "web_pid_file_stale" in report["issues"]
    assert any(
        str(item).startswith("optional_module_invalid:") for item in report["issues"]
    )


def test_run_audit_ok_for_matching_pid_and_port(tmp_path: Path, monkeypatch):
    module = _load_module()
    pid = os.getpid()
    (tmp_path / ".venom.pid").write_text(f"{pid}\n", encoding="utf-8")
    (tmp_path / ".web-next.pid").write_text(f"{pid}\n", encoding="utf-8")

    valid_manifest = tmp_path / "modules" / "x" / "module.json"
    valid_manifest.parent.mkdir(parents=True, exist_ok=True)
    valid_manifest.write_text("{}", encoding="utf-8")
    (tmp_path / ".env.dev").write_text(
        f"API_OPTIONAL_MODULES=manifest:{valid_manifest}\n", encoding="utf-8"
    )

    monkeypatch.setattr(module, "_port_pids", lambda _root, _port: [pid])
    report = module.run_audit(
        root=tmp_path,
        env_file=tmp_path / ".env.dev",
        backend_port=8000,
        web_port=3000,
    )
    assert report["ok"] is True
    assert report["issues"] == []


def test_cli_json_output(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "stack_stability_audit.py"
    (tmp_path / ".env.dev").write_text("API_OPTIONAL_MODULES=\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--env-file",
            str(tmp_path / ".env.dev"),
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["env_file"] == str((tmp_path / ".env.dev").resolve())
    assert "api" in payload
    assert "web" in payload


def test_run_audit_accepts_descendant_pid_bound_to_port(tmp_path: Path, monkeypatch):
    module = _load_module()
    parent_pid = 11111
    child_pid = 22222
    (tmp_path / ".venom.pid").write_text(f"{parent_pid}\n", encoding="utf-8")
    (tmp_path / ".web-next.pid").write_text(f"{parent_pid}\n", encoding="utf-8")
    (tmp_path / ".env.dev").write_text("API_OPTIONAL_MODULES=\n", encoding="utf-8")

    monkeypatch.setattr(module, "_process_name", lambda _pid: "python")
    monkeypatch.setattr(
        module.os.path, "exists", lambda path: path == f"/proc/{parent_pid}"
    )
    monkeypatch.setattr(module, "_port_pids", lambda _root, _port: [child_pid])
    monkeypatch.setattr(
        module,
        "_pid_and_descendant_pids",
        lambda _pid: {parent_pid, child_pid},
    )

    report = module.run_audit(
        root=tmp_path,
        env_file=tmp_path / ".env.dev",
        backend_port=8000,
        web_port=3000,
    )
    assert report["ok"] is True
    assert "api_pid_not_bound_to_expected_port" not in report["issues"]
    assert "web_pid_not_bound_to_expected_port" not in report["issues"]


def test_pid_context_matches_port_when_same_process_group(monkeypatch):
    module = _load_module()
    root_pid = 30000
    port_pid = 30099

    monkeypatch.setattr(module, "_pid_and_descendant_pids", lambda _pid: {root_pid})
    monkeypatch.setattr(
        module,
        "_pid_group_id",
        lambda pid: 777 if pid in {root_pid, port_pid} else None,
    )

    assert module._pid_context_matches_port(root_pid, [port_pid]) is True
