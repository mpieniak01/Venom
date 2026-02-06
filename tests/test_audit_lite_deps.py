import subprocess
import sys
from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_audit(
    tmp_path: Path, import_smoke: bool = False
) -> subprocess.CompletedProcess:
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "audit_lite_deps.py"
    cmd = [sys.executable, str(script_path)]
    if import_smoke:
        cmd.append("--import-smoke")
    return subprocess.run(
        cmd,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def test_audit_detects_missing_runtime_dependency(tmp_path: Path):
    _write(tmp_path / "requirements-ci-lite.txt", "pytest==9.0.2\n")
    _write(tmp_path / "config/pytest-groups/ci-lite.txt", "tests/test_sample.py\n")
    _write(
        tmp_path / "tests/test_sample.py",
        "from venom_core.core.dispatcher import TaskDispatcher\n",
    )
    _write(
        tmp_path / "venom_core/core/dispatcher.py",
        "from venom_core.agents.researcher import ResearcherAgent\n",
    )
    _write(
        tmp_path / "venom_core/agents/researcher.py",
        "from venom_core.execution.skills.github_skill import GitHubSkill\n",
    )
    _write(
        tmp_path / "venom_core/execution/skills/github_skill.py",
        "from github import Github\n",
    )

    result = _run_audit(tmp_path)
    assert result.returncode == 1
    assert "BRAKUJĄCE ZALEŻNOŚCI RUNTIME" in result.stdout
    assert "github -> pygithub" in result.stdout


def test_audit_ignores_type_checking_only_imports(tmp_path: Path):
    _write(tmp_path / "requirements-ci-lite.txt", "pytest==9.0.2\n")
    _write(tmp_path / "config/pytest-groups/ci-lite.txt", "tests/test_sample.py\n")
    _write(
        tmp_path / "tests/test_sample.py",
        "from venom_core.core.dispatcher import TaskDispatcher\n",
    )
    _write(
        tmp_path / "venom_core/core/dispatcher.py",
        "from venom_core.agents.researcher import ResearcherAgent\n",
    )
    _write(
        tmp_path / "venom_core/agents/researcher.py",
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from venom_core.execution.skills.github_skill import GitHubSkill\n",
    )

    result = _run_audit(tmp_path)
    assert result.returncode == 0
    assert "Wszystkie testy czyste" in result.stdout
