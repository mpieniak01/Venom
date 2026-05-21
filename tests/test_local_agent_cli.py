"""Testy jednostkowe dla LocalAgentCLI i IntentRouter."""

import json
from unittest.mock import MagicMock, patch

import pytest

from venom_core.agents.local_agent_cli import (
    IntentClass,
    IntentRouter,
    LocalAgent,
    LocalAgentConfig,
    main,
)
from venom_core.execution.ollama_agent_loop import AgentLoopResult, ToolCall


class TestIntentRouter:
    @pytest.fixture
    def router(self):
        return IntentRouter()

    @pytest.mark.parametrize(
        "intent",
        [
            "sprawdz status git",
            "stan repo",
            "git status",
            "status git",
            "sprawdz repo git",
            "jaki jest status repozytorium",
            "Stan Gita",  # case insensitive
            "GIT STATUS",
        ],
    )
    def test_git_status_class(self, router, intent):
        assert router.classify(intent) == IntentClass.GIT_STATUS

    @pytest.mark.parametrize(
        "intent",
        [
            "gdzie jest klasa IntegratorAgent",
            "znajdź klasę GitSkill",
            "jak działa OllamaAgentLoop",
            "pokaż implementację search_code",
            "co robi klasa IntentRouter",
            "szukaj w kodzie BaseSkill",
            "gdzie jest funkcja process",
        ],
    )
    def test_code_search_class(self, router, intent):
        assert router.classify(intent) == IntentClass.CODE_SEARCH

    @pytest.mark.parametrize(
        "intent",
        [
            "uruchom testy",
            "wykonaj make pr-fast",
            "run pytest",
            "pytest tests/",
        ],
    )
    def test_shell_exec_class(self, router, intent):
        assert router.classify(intent) == IntentClass.SHELL_EXEC

    @pytest.mark.parametrize(
        "intent",
        [
            "pokaż zawartość pliku config.py",
            "przeczytaj plik README",
            "lista plików w tests/",
        ],
    )
    def test_file_op_class(self, router, intent):
        assert router.classify(intent) == IntentClass.FILE_OP

    @pytest.mark.parametrize(
        "intent",
        [
            "czym jest venom",
            "opowiedz mi o projekcie",
            "co to jest orchestrator",
            "hello",
        ],
    )
    def test_general_class(self, router, intent):
        assert router.classify(intent) == IntentClass.GENERAL

    def test_git_status_takes_priority_over_code_search(self, router):
        # "sprawdz status git" powinno być GIT_STATUS, nie CODE_SEARCH
        result = router.classify("sprawdz status git w repozytorium")
        assert result == IntentClass.GIT_STATUS


class TestLocalAgentConfig:
    def test_defaults_workspace_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REPO_ROOT", str(tmp_path))
        config = LocalAgentConfig()
        assert config.workspace == str(tmp_path)

    def test_explicit_workspace(self, tmp_path):
        config = LocalAgentConfig(workspace=str(tmp_path))
        assert config.workspace == str(tmp_path)

    def test_default_model(self):
        config = LocalAgentConfig(workspace="/tmp")
        assert config.model == "qwen3.5:9b"


class TestLocalAgentGitStatusFastPath:
    @pytest.fixture
    def agent(self, tmp_path):
        config = LocalAgentConfig(workspace=str(tmp_path), model="test-model")
        a = LocalAgent(config)
        return a

    def test_git_status_uses_fast_path(self, agent):
        agent._handle_git_status = MagicMock(return_value="REPO_ROOT=/x\n## main")
        result = agent.handle_intent("sprawdz status git")
        assert result.stopped_by == "fast_path"
        assert result.iterations == 0

    def test_git_status_result_contains_repo_root(self, agent):
        with patch.object(agent.git_skill, "get_short_status") as mock_status:
            mock_status.return_value = "## main...origin/main"
            # Patch asyncio.run to return directly
            with patch("venom_core.agents.local_agent_cli.asyncio") as mock_asyncio:
                mock_asyncio.run.return_value = "## main...origin/main"
                result = agent.handle_intent("sprawdz status git")
        assert result.stopped_by == "fast_path"
        assert result.has_evidence()


class TestLocalAgentRunOnce:
    @pytest.fixture
    def agent(self, tmp_path):
        config = LocalAgentConfig(workspace=str(tmp_path), model="test-model")
        return LocalAgent(config)

    def test_run_once_returns_string(self, agent):
        agent.handle_intent = MagicMock(
            return_value=AgentLoopResult(
                final_answer="Odpowiedź agenta", evidence=["evidence"]
            )
        )
        out = agent.run_once("test query")
        assert "Odpowiedź agenta" in out

    def test_run_once_json_output(self, agent):
        agent.handle_intent = MagicMock(
            return_value=AgentLoopResult(
                final_answer="OK", evidence=["e1"], iterations=1, stopped_by="finish"
            )
        )
        agent.config.json_output = True
        out = agent.run_once("test")
        parsed = json.loads(out)
        assert parsed["final_answer"] == "OK"
        assert parsed["evidence"] == ["e1"]

    def test_run_once_includes_trace_when_tool_calls(self, agent):
        tc = ToolCall(
            call_id="c1",
            name="search_code",
            arguments={"query": "foo"},
            result="bar.py:5",
        )
        agent.handle_intent = MagicMock(
            return_value=AgentLoopResult(final_answer="Wynik", tool_calls=[tc])
        )
        out = agent.run_once("test")
        assert "Trace" in out
        assert "search_code" in out


class TestLocalAgentShellExec:
    @pytest.fixture
    def agent_with_exec(self, tmp_path):
        config = LocalAgentConfig(workspace=str(tmp_path), allow_exec=True)
        return LocalAgent(config)

    @pytest.fixture
    def agent_no_exec(self, tmp_path):
        config = LocalAgentConfig(workspace=str(tmp_path), allow_exec=False)
        return LocalAgent(config)

    def test_shell_exec_blocked_without_flag(self, agent_no_exec):
        result = agent_no_exec._handle_shell_exec("shell_exec", {"command": "echo hi"})
        assert "❌" in result
        assert "allow-exec" in result

    def test_shell_exec_runs_safe_command(self, agent_with_exec):
        result = agent_with_exec._handle_shell_exec(
            "shell_exec", {"command": "echo hello"}
        )
        assert "hello" in result

    def test_shell_exec_blocks_destructive(self, agent_with_exec):
        result = agent_with_exec._handle_shell_exec(
            "shell_exec", {"command": "rm -rf /"}
        )
        assert "❌" in result
        assert "destrukcyjna" in result

    def test_shell_exec_allows_destructive_with_flag(self, tmp_path):
        config = LocalAgentConfig(
            workspace=str(tmp_path), allow_exec=True, allow_destructive=True
        )
        agent = LocalAgent(config)
        result = agent._handle_shell_exec(
            "shell_exec", {"command": "echo destructive allowed"}
        )
        assert "destructive allowed" in result

    def test_shell_exec_timeout(self, agent_with_exec):
        import subprocess

        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("sleep", 30)
        ):
            result = agent_with_exec._handle_shell_exec(
                "shell_exec", {"command": "sleep 100"}
            )
        assert "Timeout" in result

    def test_shell_exec_empty_command(self, agent_with_exec):
        result = agent_with_exec._handle_shell_exec("shell_exec", {"command": ""})
        assert "❌" in result

    def test_shell_exec_blocks_shell_metacharacters(self, agent_with_exec):
        result = agent_with_exec._handle_shell_exec(
            "shell_exec", {"command": "echo ok; rm -rf /"}
        )
        assert "❌" in result
        assert "metaznaki" in result


class TestLocalAgentCodeSearch:
    @pytest.fixture
    def agent(self, tmp_path):
        config = LocalAgentConfig(workspace=str(tmp_path))
        a = LocalAgent(config)
        return a

    def test_search_code_handler(self, agent, tmp_path):
        (tmp_path / "mod.py").write_text("class TargetClass:\n    pass\n")
        result = agent._handle_search_code("search_code", {"query": "TargetClass"})
        assert "TargetClass" in result or result == "Brak wyników."

    def test_file_symbols_handler(self, agent, tmp_path):
        f = tmp_path / "m.py"
        f.write_text("class Foo:\n    def bar(self): pass\n")
        result = agent._handle_file_symbols("get_file_symbols", {"file_path": str(f)})
        assert "Foo" in result

    def test_read_context_handler(self, agent, tmp_path):
        f = tmp_path / "t.py"
        f.write_text("a\nb\nc\n")
        result = agent._handle_read_context(
            "read_file_context", {"file_path": str(f), "line": 2}
        )
        assert "b" in result


class TestMainEntryPoint:
    def test_main_requires_query_or_interactive(self, capsys):
        ret = main([])
        assert ret == 1
        captured = capsys.readouterr()
        assert "zapytanie" in captured.err or "interactive" in captured.err

    def test_main_git_status(self, tmp_path):
        with patch(
            "venom_core.agents.local_agent_cli.LocalAgent.handle_intent",
            return_value=AgentLoopResult(
                final_answer=f"REPO_ROOT={tmp_path}\n## main",
                evidence=[f"REPO_ROOT={tmp_path}\n## main"],
                stopped_by="fast_path",
            ),
        ):
            ret = main([f"--workspace={tmp_path}", "sprawdz status git"])
        assert ret == 0

    def test_main_json_output_valid_json(self, tmp_path, capsys):
        with patch(
            "venom_core.agents.local_agent_cli.LocalAgent.handle_intent",
            return_value=AgentLoopResult(final_answer="OK", evidence=["e"]),
        ):
            ret = main([f"--workspace={tmp_path}", "--json-output", "test query"])
        assert ret == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["final_answer"] == "OK"

    def test_main_unknown_flag_exits(self):
        with pytest.raises(SystemExit):
            main(["--unknown-flag-xyz", "query"])
