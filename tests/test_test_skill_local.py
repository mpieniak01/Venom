"""Unit tests for TestSkill in local execution mode."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from venom_core.execution.skills.test_skill import TestSkill


@pytest.fixture
def local_test_skill():
    """Fixture for TestSkill with local execution enabled."""
    return TestSkill(allow_local_execution=True)


@pytest.fixture
def temp_test_dir():
    """Fixture for temporary test directory with dummy tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_dummy.py"
        test_file.write_text("""
def test_success():
    assert True

def test_failure():
    assert False
""")
        yield tmpdir


@pytest.mark.asyncio
async def test_run_pytest_local_success(local_test_skill, temp_test_dir):
    """Test running pytest locally on a file that passes."""
    # Create a passing test file
    pass_file = Path(temp_test_dir) / "test_pass.py"
    pass_file.write_text("def test_ok(): assert 1 == 1")

    result = await local_test_skill.run_pytest(test_path=str(pass_file))

    assert "✅" in result or "PRZESZŁY" in result
    assert "Passed: 1" in result
    assert "Failed: 0" in result


@pytest.mark.asyncio
async def test_run_pytest_local_failure(local_test_skill, temp_test_dir):
    """Test capture of local pytest failures."""
    # Create a failing test file
    fail_file = Path(temp_test_dir) / "test_fail.py"
    fail_file.write_text("def test_bad(): assert 1 == 2")

    result = await local_test_skill.run_pytest(test_path=str(fail_file))

    assert "❌" in result or "NIE PRZESZŁY" in result
    assert "Failed: 1" in result
    # Output format varies, simpler check
    assert "FAILED" in result


@pytest.mark.asyncio
async def test_run_linter_local(local_test_skill, temp_test_dir):
    """Test running linter locally."""
    # Create a file with lint issues
    lint_file = Path(temp_test_dir) / "lint_bad.py"
    lint_file.write_text("import os  # Unused import\nx=1  # Bad formatting")

    # This might fail if ruff/flake8 are not installed in the environment running tests
    # But since we are running tests via pytest in this env, dev deps should be there.
    result = await local_test_skill.run_linter(path=str(lint_file))

    # We expect either success (clean) or issues, but not an "Execution Error"
    assert "✅" in result or "⚠️" in result


@pytest.mark.asyncio
async def test_local_execution_disabled_by_default():
    """Verify that local execution is disabled by default."""
    skill = TestSkill(allow_local_execution=False)
    # Mock docker unavailable
    skill.docker_available = False
    skill.habitat = None

    result = await skill.run_pytest(test_path=".")
    assert "Docker sandbox jest niedostępny" in result


@pytest.mark.asyncio
async def test_run_linter_invalid_path_returns_error(local_test_skill):
    result = await local_test_skill.run_linter(path="bad path with spaces")
    assert "Nieprawidłowa ścieżka" in result


@pytest.mark.asyncio
async def test_run_local_linter_binary_timeout_kills_process(local_test_skill):
    class DummyProcess:
        def __init__(self):
            self.returncode = None
            self.killed = False

        async def communicate(self):
            await asyncio.sleep(1)
            return b"", None

        def kill(self):
            self.killed = True
            self.returncode = -9

    process = DummyProcess()

    async def _fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    try:
        result = await local_test_skill._run_local_linter_binary(
            "ruff", ".", timeout=0.01
        )
    finally:
        monkeypatch.undo()

    assert result is None
    assert process.killed is True
