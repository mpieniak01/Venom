from venom_core.api.schemas.tasks import TaskRequest
from venom_core.services.execution_mode_planner import decide_execution_mode
from venom_core.services.execution_template_planner import resolve_api_skill_template


def test_execution_mode_defaults_to_api_skill() -> None:
    decision = decide_execution_mode(
        TaskRequest(content="hello"), intent="GENERAL_CHAT"
    )
    assert decision.execution_mode == "api_skill"
    assert decision.fallback_reason is None
    assert decision.reason_code is None


def test_execution_mode_selects_browser_automation_for_research_intent() -> None:
    decision = decide_execution_mode(
        TaskRequest(content="find docs"),
        intent="RESEARCH",
    )
    assert decision.execution_mode == "browser_automation"
    assert decision.fallback_reason is None


def test_execution_mode_selects_gui_fallback_for_forced_ui_tool() -> None:
    decision = decide_execution_mode(
        TaskRequest(content="click this", forced_tool="ui"),
        intent="GENERAL_CHAT",
    )
    assert decision.execution_mode == "gui_fallback"
    assert decision.fallback_reason == "forced_gui_tool"
    assert decision.reason_code == "EXECUTION_MODE_GUI_FALLBACK_FORCED_TOOL"


def test_api_skill_template_forced_github_tool() -> None:
    template = resolve_api_skill_template(
        TaskRequest(content="commit", forced_tool="github"),
        intent="VERSION_CONTROL",
    )
    assert template is not None
    assert template.template_id == "github_repo_ops_v1"
    assert template.source == "forced_tool"


def test_api_skill_template_from_file_operation_intent() -> None:
    template = resolve_api_skill_template(
        TaskRequest(content="edit file"),
        intent="FILE_OPERATION",
    )
    assert template is not None
    assert template.template_id == "filesystem_ops_v1"
    assert template.source == "intent"
