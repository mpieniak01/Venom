"""Coverage tests for ShellSkill - mocked I/O, no Docker required."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from venom_core.config import SETTINGS
from venom_core.core.permission_guard import permission_guard
from venom_core.execution.skills.shell_skill import ShellSkill


@pytest.fixture(autouse=True)
def _allow_shell_for_tests():
    """Grant shell execution permissions for all tests in this module."""
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(40)
    try:
        yield
    finally:
        permission_guard.set_level(previous_level)


@pytest.fixture
def _disable_sandbox(monkeypatch):
    """Disable Docker sandbox via SETTINGS so tests run locally."""
    monkeypatch.setattr(SETTINGS, "ENABLE_SANDBOX", False)


# ---------------------------------------------------------------------------
# Initialization paths
# ---------------------------------------------------------------------------


def test_init_sandbox_disabled_via_settings(monkeypatch):
    """ENABLE_SANDBOX=False forces local mode regardless of use_sandbox arg."""
    monkeypatch.setattr(SETTINGS, "ENABLE_SANDBOX", False)
    skill = ShellSkill(use_sandbox=True)
    assert skill.use_sandbox is False
    assert skill.habitat is None


def test_init_local_mode():
    """use_sandbox=False stays local even when ENABLE_SANDBOX would allow sandbox."""
    skill = ShellSkill(use_sandbox=False)
    assert skill.use_sandbox is False
    assert skill.habitat is None


def test_init_sandbox_fallback_on_docker_error(monkeypatch):
    """When DockerHabitat raises, ShellSkill falls back to local mode."""
    monkeypatch.setattr(SETTINGS, "ENABLE_SANDBOX", True)
    with patch(
        "venom_core.execution.skills.shell_skill.DockerHabitat",
        side_effect=RuntimeError("Docker not available"),
    ):
        skill = ShellSkill(use_sandbox=True)
    assert skill.use_sandbox is False
    assert skill.habitat is None


def test_init_sandbox_success(monkeypatch):
    """When DockerHabitat initialises correctly, use_sandbox stays True."""
    monkeypatch.setattr(SETTINGS, "ENABLE_SANDBOX", True)
    mock_habitat = MagicMock()
    with patch(
        "venom_core.execution.skills.shell_skill.DockerHabitat",
        return_value=mock_habitat,
    ):
        skill = ShellSkill(use_sandbox=True)
    assert skill.use_sandbox is True
    assert skill.habitat is mock_habitat


# ---------------------------------------------------------------------------
# run_shell — local mode
# ---------------------------------------------------------------------------


def test_run_shell_local_success(_disable_sandbox):
    """run_shell in local mode returns success message with output."""
    skill = ShellSkill(use_sandbox=False)
    mock_completed = MagicMock()
    mock_completed.returncode = 0
    mock_completed.stdout = "hello\n"
    mock_completed.stderr = ""
    with patch(
        "venom_core.execution.skills.shell_skill.subprocess.run",
        return_value=mock_completed,
    ):
        result = skill.run_shell("echo hello", timeout=10)
    assert "hello" in result
    assert "pomyślnie" in result


def test_run_shell_local_nonzero_exit(_disable_sandbox):
    """run_shell in local mode includes exit_code on failure."""
    skill = ShellSkill(use_sandbox=False)
    mock_completed = MagicMock()
    mock_completed.returncode = 1
    mock_completed.stdout = ""
    mock_completed.stderr = "error"
    with patch(
        "venom_core.execution.skills.shell_skill.subprocess.run",
        return_value=mock_completed,
    ):
        result = skill.run_shell("exit 1", timeout=10)
    assert "exit_code=" in result or "błąd" in result.lower()


def test_run_shell_local_timeout(_disable_sandbox):
    """run_shell in local mode returns an error string on timeout (via @safe_action)."""
    skill = ShellSkill(use_sandbox=False)

    with patch(
        "venom_core.execution.skills.shell_skill.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="cmd", timeout=1),
    ):
        result = skill.run_shell("sleep 100", timeout=1)
    assert "❌" in result or "przekroczyła limit" in result


def test_run_shell_local_generic_exception(_disable_sandbox):
    """run_shell in local mode handles generic exceptions via safe_action."""
    skill = ShellSkill(use_sandbox=False)
    with patch(
        "venom_core.execution.skills.shell_skill.subprocess.run",
        side_effect=OSError("disk error"),
    ):
        result = skill.run_shell("anything", timeout=5)
    assert "❌" in result


# ---------------------------------------------------------------------------
# run_shell — sandbox mode (mocked DockerHabitat)
# ---------------------------------------------------------------------------


def test_run_shell_sandbox_success(monkeypatch):
    """run_shell in sandbox mode delegates to habitat.execute."""
    monkeypatch.setattr(SETTINGS, "ENABLE_SANDBOX", True)
    mock_habitat = MagicMock()
    mock_habitat.execute.return_value = (0, "sandbox output")
    with patch(
        "venom_core.execution.skills.shell_skill.DockerHabitat",
        return_value=mock_habitat,
    ):
        skill = ShellSkill(use_sandbox=True)
    result = skill.run_shell("echo test", timeout=10)
    assert "sandbox output" in result
    assert "pomyślnie" in result
    mock_habitat.execute.assert_called_once_with("echo test", 10)


def test_run_shell_sandbox_nonzero_exit(monkeypatch):
    """run_shell in sandbox mode propagates nonzero exit_code in message."""
    monkeypatch.setattr(SETTINGS, "ENABLE_SANDBOX", True)
    mock_habitat = MagicMock()
    mock_habitat.execute.return_value = (2, "some error output")
    with patch(
        "venom_core.execution.skills.shell_skill.DockerHabitat",
        return_value=mock_habitat,
    ):
        skill = ShellSkill(use_sandbox=True)
    result = skill.run_shell("bad_cmd", timeout=5)
    assert "exit_code=2" in result
    assert "some error output" in result


def test_run_shell_sandbox_execute_raises(monkeypatch):
    """If habitat.execute raises, safe_action returns error string."""
    monkeypatch.setattr(SETTINGS, "ENABLE_SANDBOX", True)
    mock_habitat = MagicMock()
    mock_habitat.execute.side_effect = RuntimeError("container crashed")
    with patch(
        "venom_core.execution.skills.shell_skill.DockerHabitat",
        return_value=mock_habitat,
    ):
        skill = ShellSkill(use_sandbox=True)
    result = skill.run_shell("anything", timeout=5)
    assert "❌" in result


def test_run_shell_sandbox_habitat_none_raises(monkeypatch):
    """When use_sandbox=True but habitat=None, safe_action returns error string."""
    monkeypatch.setattr(SETTINGS, "ENABLE_SANDBOX", True)
    mock_habitat = MagicMock()
    with patch(
        "venom_core.execution.skills.shell_skill.DockerHabitat",
        return_value=mock_habitat,
    ):
        skill = ShellSkill(use_sandbox=True)
    # Manually clear habitat after init to simulate an inconsistent state
    skill.habitat = None
    result = skill.run_shell("echo test", timeout=5)
    assert "❌" in result


# ---------------------------------------------------------------------------
# get_exit_code_from_output
# ---------------------------------------------------------------------------


def test_get_exit_code_success_message():
    skill = ShellSkill(use_sandbox=False)
    assert skill.get_exit_code_from_output("Komenda wykonana pomyślnie.\n\nOutput:\nok") == 0


def test_get_exit_code_explicit_zero():
    skill = ShellSkill(use_sandbox=False)
    assert skill.get_exit_code_from_output("exit_code=0 done") == 0


def test_get_exit_code_explicit_nonzero():
    skill = ShellSkill(use_sandbox=False)
    assert skill.get_exit_code_from_output("exit_code=127 not found") == 127


def test_get_exit_code_fallback_failure():
    skill = ShellSkill(use_sandbox=False)
    assert skill.get_exit_code_from_output("Some generic failure message") == 1


# ---------------------------------------------------------------------------
# Permission guard — require_shell_permission denied
# ---------------------------------------------------------------------------


def test_run_shell_denied_when_no_permission():
    """run_shell returns error string when shell permission is denied."""
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(0)  # No permissions
    try:
        skill = ShellSkill(use_sandbox=False)
        result = skill.run_shell("echo hello", timeout=5)
        assert "❌" in result or "Odmowa" in result
    finally:
        permission_guard.set_level(previous_level)
