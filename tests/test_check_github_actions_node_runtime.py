from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts import check_github_actions_node_runtime as mod


def test_validate_workflow_accepts_node24_ready_actions():
    content = """
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"
jobs:
  sample:
    steps:
      - uses: actions/upload-artifact@v6
      - uses: actions/download-artifact@v7
      - uses: actions/cache@v5
""".strip()

    issues = mod.validate_workflow(Path("wf.yml"), content)

    assert issues == []


def test_validate_workflow_flags_deprecated_versions_and_missing_env():
    content = """
jobs:
  sample:
    steps:
      - uses: actions/upload-artifact@v5
      - uses: actions/download-artifact@v5
      - uses: actions/cache@v4
""".strip()

    issues = mod.validate_workflow(Path("wf.yml"), content)

    assert len(issues) == 4
    assert "upload-artifact@v5" in issues[0]
    assert "download-artifact@v5" in issues[1]
    assert "actions/cache@v4" in issues[2]
    assert mod.FORCE_NODE24_ENV in issues[3]


def test_run_check_scans_workflow_directory(tmp_path: Path):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ok.yml").write_text(
        """
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"
jobs:
  sample:
    steps:
      - uses: actions/upload-artifact@v6
      - uses: actions/cache@v5
""".strip(),
        encoding="utf-8",
    )
    (workflow_dir / "bad.yml").write_text(
        """
jobs:
  sample:
    steps:
      - uses: actions/upload-artifact@v5
      - uses: actions/cache@v4
""".strip(),
        encoding="utf-8",
    )

    issues = mod.run_check(workflow_dir)

    assert len(issues) == 3
    assert any("bad.yml" in issue for issue in issues)


def _runtime_contract(tmp_path):
    import json

    (tmp_path / "web-next").mkdir()
    (tmp_path / "docker").mkdir()
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "web-next/.nvmrc").write_text("24.22.0\n")
    engines = {"node": ">=24.22.0 <25", "npm": ">=11.19.1 <12"}
    (tmp_path / "web-next/package.json").write_text(
        json.dumps({"engines": engines, "packageManager": "npm@11.19.1"})
    )
    (tmp_path / "web-next/package-lock.json").write_text(
        json.dumps({"packages": {"": {"engines": engines}}})
    )
    (tmp_path / "docker/frontend.Dockerfile").write_text(
        "ARG NODE_IMAGE=node:24.22.0-alpine@sha256:" + "a" * 64
    )
    (tmp_path / ".github/workflows/ci.yml").write_text(
        'uses: actions/setup-node@v6\nnode-version-file: "web-next/.nvmrc"'
    )
    return tmp_path


def test_project_node_runtime_accepts_coherent_pinned_consumers(tmp_path):
    assert mod.validate_project_runtime(_runtime_contract(tmp_path)) == []


def test_project_node_runtime_rejects_drift_in_each_consumer(tmp_path):
    import json

    root = _runtime_contract(tmp_path)
    package_path = root / "web-next/package.json"
    package = json.loads(package_path.read_text())
    package["engines"]["node"] = ">=20.0.0"
    package["engines"]["npm"] = ">=10.0.0"
    package_path.write_text(json.dumps(package))
    (root / "docker/frontend.Dockerfile").write_text("FROM node:20-alpine")
    (root / ".github/workflows/ci.yml").write_text(
        'uses: actions/setup-node@v6\nnode-version: "20"'
    )
    issues = mod.validate_project_runtime(root)
    assert len(issues) == 5


def test_project_node_runtime_rejects_unsupported_major_and_unpinned_npm(tmp_path):
    import json

    root = _runtime_contract(tmp_path)
    (root / "web-next/.nvmrc").write_text("20.19.0")
    package_path = root / "web-next/package.json"
    package = json.loads(package_path.read_text())
    package.pop("packageManager")
    package_path.write_text(json.dumps(package))
    issues = mod.validate_project_runtime(root)
    assert any("Node 24" in item for item in issues)
    assert any("npm 11" in item for item in issues)


def test_project_node_runtime_fails_closed_without_files(tmp_path):
    assert mod.validate_project_runtime(tmp_path)


@pytest.mark.parametrize(
    "selected_valid", [False, True], ids=["selected-invalid", "selected-valid"]
)
def test_cli_honors_selected_workflow_directory(
    tmp_path, monkeypatch, capsys, selected_valid
):
    """The selected directory alone controls project workflow pin validation."""
    root = _runtime_contract(tmp_path)
    selected = root / "custom-workflows"
    selected.mkdir()
    valid = 'uses: actions/setup-node@v6\nnode-version-file: "web-next/.nvmrc"'
    invalid = 'uses: actions/setup-node@v6\nnode-version: "24.22.0"'
    (root / ".github/workflows/ci.yml").write_text(invalid if selected_valid else valid)
    (selected / "selected.yml").write_text(valid if selected_valid else invalid)
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        sys, "argv", ["node-runtime-guard", "--workflow-dir", str(selected)]
    )

    assert mod.main() == (0 if selected_valid else 1)
    output = capsys.readouterr().out
    if selected_valid:
        assert "passed" in output
    else:
        assert "selected.yml: setup-node must consume web-next/.nvmrc" in output
        assert "ci.yml:" not in output
