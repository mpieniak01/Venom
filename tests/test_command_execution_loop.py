"""PR242: testy pomocnicze command-execution loop (read-only + guard + evidence)."""

from unittest.mock import MagicMock, patch

from venom_core.agents.local_agent_cli import LocalAgent, LocalAgentConfig


def _agent(tmp_path, *, allow_exec: bool = False) -> LocalAgent:
    config = LocalAgentConfig(workspace=str(tmp_path), allow_exec=allow_exec)
    return LocalAgent(config)


def test_command_loop_git_status_fast_path_has_evidence(tmp_path):
    agent = _agent(tmp_path, allow_exec=False)
    with patch.object(agent.git_skill, "get_short_status") as mock_status:
        mock_status.return_value = "## main...origin/main\n M a.py"
        with patch("venom_core.agents.local_agent_cli.asyncio") as mock_asyncio:
            mock_asyncio.run.return_value = "## main...origin/main\n M a.py"
            result = agent.handle_intent("sprawdz status git")

    assert result.stopped_by == "fast_path"
    assert result.has_evidence()
    assert result.evidence[0].startswith("REPO_ROOT=")
    assert "## main...origin/main" in result.evidence[0]


def test_command_loop_blocks_destructive_before_executor(tmp_path):
    agent = _agent(tmp_path, allow_exec=True)
    with patch("subprocess.run") as mock_run:
        output = agent._handle_shell_exec("shell_exec", {"command": "rm -rf /tmp/x"})
    assert "destrukcyjna" in output
    mock_run.assert_not_called()


def test_command_loop_blocks_shell_metacharacters_before_executor(tmp_path):
    agent = _agent(tmp_path, allow_exec=True)
    with patch("subprocess.run") as mock_run:
        output = agent._handle_shell_exec(
            "shell_exec", {"command": "python --version; whoami"}
        )
    assert "metaznaki" in output
    mock_run.assert_not_called()


def test_command_loop_read_only_python_version_returns_output(tmp_path):
    agent = _agent(tmp_path, allow_exec=True)
    completed = MagicMock()
    completed.stdout = "Python 3.12.3\n"
    completed.stderr = ""
    completed.returncode = 0

    with patch("subprocess.run", return_value=completed) as mock_run:
        output = agent._handle_shell_exec("shell_exec", {"command": "python --version"})

    assert "Python 3.12.3" in output
    mock_run.assert_called_once()
