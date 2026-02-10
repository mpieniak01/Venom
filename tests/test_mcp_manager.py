import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.helpers.url_fixtures import http_url
from venom_core.core.permission_guard import permission_guard
from venom_core.skills.mcp_manager_skill import McpManagerSkill, McpToolMetadata


@pytest.fixture
def manager(tmp_path):
    # Mock settings patches if needed, or rely on tmp_path being passed to deps if refactored.
    # Here we mock the root paths after init to point to tmp
    m = McpManagerSkill()
    m.mcp_root = tmp_path / "mcp"
    m.repos_root = m.mcp_root / "_repos"
    m.custom_skills_dir = tmp_path / "custom"

    m.repos_root.mkdir(parents=True)
    m.custom_skills_dir.mkdir(parents=True)
    return m


@pytest.fixture(autouse=True)
def _allow_shell_for_mcp_tests():
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(40)
    try:
        yield
    finally:
        permission_guard.set_level(previous_level)


@pytest.mark.asyncio
async def test_import_flow(manager):
    # Mock internal methods
    manager._run_shell = AsyncMock()
    manager._introspect_tools = AsyncMock(
        return_value=[
            McpToolMetadata(name="test_tool", description="desc", input_schema={})
        ]
    )

    # Mock generator
    manager.generator.generate_skill_code = MagicMock(return_value="print('hello')")

    result = await manager.import_mcp_tool(
        repo_url=http_url("git.fake", path="/repo"),
        tool_name="fake_tool",
        install_command="pip install .",
        server_entrypoint="python server.py",
    )

    # Assertions
    assert "Sukces" in result

    # Check shell calls
    calls = manager._run_shell.call_args_list
    assert len(calls) >= 3  # clone, venv, install deps

    # Verify clone
    assert "git clone" in calls[0][0][0]

    # Verify pip install uses venv pip
    # The command uses absolute path, so just check it calls pip install .
    # Sequence: 0=clone, 1=venv, 2=upgrade pip, 3=install deps
    if len(calls) > 3:
        install_cmd = calls[3][0][0]
    else:
        # Fallback if upgrade pip was skipped or different flow (should not happen based on code)
        install_cmd = calls[-1][0][0]

    assert "pip install ." in install_cmd
    assert "/bin/pip" in install_cmd  # ensure it uses venv binary

    # Verify file creation
    output_file = manager.custom_skills_dir / "mcp_fake_tool.py"
    assert output_file.exists()
    assert output_file.read_text() == "print('hello')"


@pytest.mark.asyncio
async def test_import_flow_resolves_server_path_and_custom_install(manager):
    async def fake_run_shell(cmd, cwd=None):
        if cmd.startswith("git clone"):
            repo_dir = manager.repos_root / "custom_tool"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "server.py").write_text("print('ok')", encoding="utf-8")

    manager._run_shell = AsyncMock(side_effect=fake_run_shell)
    manager._introspect_tools = AsyncMock(
        return_value=[McpToolMetadata(name="ping", description="d", input_schema={})]
    )
    manager.generator.generate_skill_code = MagicMock(return_value="print('ok')")

    await manager.import_mcp_tool(
        repo_url=http_url("git.fake", path="/repo"),
        tool_name="custom_tool",
        install_command="pip install -r requirements.txt",
        server_entrypoint="python server.py",
    )

    install_calls = [args[0] for args, _kwargs in manager._run_shell.call_args_list]
    assert any("/bin/pip install -r requirements.txt" in cmd for cmd in install_calls)

    introspect_args = manager._introspect_tools.await_args
    assert introspect_args.args[0].endswith("/bin/python")
    assert introspect_args.args[1][0].endswith("/custom_tool/server.py")


@pytest.mark.asyncio
async def test_introspect_failure(manager):
    manager._run_shell = AsyncMock()
    manager._introspect_tools = AsyncMock(return_value=[])  # Empty list

    result = await manager.import_mcp_tool(repo_url="R", tool_name="T")

    assert "⚠️ Nie wykryto żadnych narzędzi" in result


@pytest.mark.asyncio
async def test_introspect_tools_propagates_exception(manager, monkeypatch):
    class FailingContext:
        async def __aenter__(self):
            raise RuntimeError("boom")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "venom_core.skills.mcp_manager_skill._MCP_AVAILABLE", True, raising=False
    )
    monkeypatch.setattr(
        "venom_core.skills.mcp_manager_skill.StdioServerParameters",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        "venom_core.skills.mcp_manager_skill.stdio_client",
        lambda *_args, **_kwargs: FailingContext(),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await manager._introspect_tools(
            command="python3",
            args=["server.py"],
            cwd=manager.repos_root,
            env={},
        )


@pytest.mark.asyncio
async def test_introspect_tools_fails_cleanly_without_mcp(manager, monkeypatch):
    monkeypatch.setattr(
        "venom_core.skills.mcp_manager_skill._MCP_AVAILABLE", False, raising=False
    )

    with pytest.raises(RuntimeError, match="mcp"):
        await manager._introspect_tools(
            command="python3",
            args=["server.py"],
            cwd=manager.repos_root,
            env={},
        )


@pytest.mark.asyncio
async def test_run_shell_raises_runtime_error_on_nonzero_exit(manager, monkeypatch):
    class FailingProcess:
        returncode = 1

        async def communicate(self):
            return b"", b"permission denied"

    async def _fake_subprocess_shell(*_args, **_kwargs):
        return FailingProcess()

    monkeypatch.setattr(
        "venom_core.skills.mcp_manager_skill.asyncio.create_subprocess_shell",
        _fake_subprocess_shell,
    )

    with pytest.raises(RuntimeError, match="permission denied"):
        await manager._run_shell("echo fail")


def test_optional_import_path_marks_mcp_available_when_module_exists(monkeypatch):
    fake_mcp = types.ModuleType("mcp")
    fake_mcp.ClientSession = object
    fake_mcp.StdioServerParameters = object

    fake_mcp_client = types.ModuleType("mcp.client")
    fake_stdio = types.ModuleType("mcp.client.stdio")
    fake_stdio.stdio_client = lambda *_args, **_kwargs: object()

    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", fake_mcp_client)
    monkeypatch.setitem(sys.modules, "mcp.client.stdio", fake_stdio)

    module_path = (
        Path(__file__).resolve().parents[1] / "venom_core/skills/mcp_manager_skill.py"
    )
    spec = importlib.util.spec_from_file_location("mcp_manager_skill_cov", module_path)
    assert spec and spec.loader

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._MCP_AVAILABLE is True
