import pytest

from venom_core.skills.mcp.skill_adapter import (
    FileSkillMcpAdapter,
    GitSkillMcpAdapter,
    GoogleCalendarSkillMcpAdapter,
)


def test_git_skill_adapter_lists_mcp_like_tools(tmp_path):
    adapter = GitSkillMcpAdapter(workspace_root=str(tmp_path / "repo"))

    tools = adapter.list_tools()
    names = {tool.name for tool in tools}

    assert "init_repo" in names
    assert "get_status" in names

    init_repo = next(tool for tool in tools if tool.name == "init_repo")
    assert init_repo.input_schema["type"] == "object"
    assert "url" in init_repo.input_schema["properties"]


@pytest.mark.asyncio
async def test_git_skill_adapter_invokes_tool_successfully(tmp_path):
    workspace = tmp_path / "repo"
    adapter = GitSkillMcpAdapter(workspace_root=str(workspace))

    init_result = await adapter.invoke_tool("init_repo", {})
    assert "Zainicjalizowano nowe repozytorium Git" in init_result

    status_result = await adapter.invoke_tool("get_status", {})
    assert isinstance(status_result, str)
    assert status_result
    assert (workspace / ".git").exists()


@pytest.mark.asyncio
async def test_git_skill_adapter_raises_on_missing_required_argument(tmp_path):
    adapter = GitSkillMcpAdapter(workspace_root=str(tmp_path / "repo"))

    with pytest.raises(ValueError, match="Missing required arguments"):
        await adapter.invoke_tool("checkout", {})


@pytest.mark.asyncio
async def test_git_skill_adapter_raises_on_unknown_tool(tmp_path):
    adapter = GitSkillMcpAdapter(workspace_root=str(tmp_path / "repo"))

    with pytest.raises(ValueError, match="Unknown tool"):
        await adapter.invoke_tool("not_existing_tool", {})


def test_file_skill_adapter_lists_mcp_like_tools(tmp_path):
    adapter = FileSkillMcpAdapter(workspace_root=str(tmp_path / "workspace"))
    names = {tool.name for tool in adapter.list_tools()}
    assert "read_file" in names
    assert "list_files" in names
    assert "file_exists" in names


@pytest.mark.asyncio
async def test_file_skill_adapter_invokes_file_exists(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "example.txt").write_text("hello", encoding="utf-8")

    adapter = FileSkillMcpAdapter(workspace_root=str(workspace))
    result = await adapter.invoke_tool("file_exists", {"file_path": "example.txt"})
    assert result == "True"


def test_calendar_skill_adapter_lists_tools_without_credentials():
    adapter = GoogleCalendarSkillMcpAdapter(
        credentials_path="/tmp/missing_credentials.json",
        token_path="/tmp/missing_token.pickle",
        venom_calendar_id="venom-work",
    )
    names = {tool.name for tool in adapter.list_tools()}
    assert "read_agenda" in names
    assert "schedule_task" in names


@pytest.mark.asyncio
async def test_calendar_skill_adapter_returns_graceful_message_without_credentials():
    adapter = GoogleCalendarSkillMcpAdapter(
        credentials_path="/tmp/missing_credentials.json",
        token_path="/tmp/missing_token.pickle",
        venom_calendar_id="venom-work",
    )
    result = await adapter.invoke_tool("read_agenda", {})
    assert "nie jest skonfigurowany" in result.lower()
