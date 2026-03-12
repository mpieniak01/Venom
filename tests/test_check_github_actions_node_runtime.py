from __future__ import annotations

from pathlib import Path

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
""".strip()

    issues = mod.validate_workflow(Path("wf.yml"), content)

    assert len(issues) == 3
    assert "upload-artifact@v5" in issues[0]
    assert "download-artifact@v5" in issues[1]
    assert mod.FORCE_NODE24_ENV in issues[2]


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
""".strip(),
        encoding="utf-8",
    )
    (workflow_dir / "bad.yml").write_text(
        """
jobs:
  sample:
    steps:
      - uses: actions/upload-artifact@v5
""".strip(),
        encoding="utf-8",
    )

    issues = mod.run_check(workflow_dir)

    assert len(issues) == 2
    assert any("bad.yml" in issue for issue in issues)
