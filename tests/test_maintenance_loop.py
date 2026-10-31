"""Scripted transports verify infrastructure only, never model quality."""

import asyncio
from types import SimpleNamespace

import pytest

from venom_core.core.permission_guard import permission_guard
from venom_core.services.maintenance_comparison.runner import drive
from venom_core.services.maintenance_comparison.sandbox import TrialTools


class Model:
    profile = {"protocol": "bash"}

    def __init__(self, replies):
        self.replies = iter(replies)

    def generate(self, *_):
        return next(self.replies)


@pytest.fixture
def tools(tmp_path, monkeypatch):
    monkeypatch.setattr(permission_guard, "check_permission", lambda *_: True)
    habitat = SimpleNamespace(
        workspace_path=tmp_path,
        structured=lambda command, timeout: {
            "stdout": "ok",
            "stderr": "",
            "exit_code": 0,
        },
    )
    return TrialTools(habitat, "operator")


def case():
    return SimpleNamespace(role="operator", prompt="Do a task")


def test_model_tool_result_and_bash_completion_round_trip(tools):
    model = Model(["```bash\nprintf ok\n```", "```bash\nprintf finish\n```"])
    original = tools.habitat.structured

    def execute(command, timeout):
        if command == "printf finish":
            return {
                "stdout": 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n{"status":"success","summary":"done"}',
                "stderr": "",
                "exit_code": 0,
            }
        return original(command, timeout)

    tools.habitat.structured = execute
    result = asyncio.run(drive(model, case(), tools))
    assert result["model_finished"] is True
    assert result["tool_call_count"] == 2
    assert result["calls"][0]["result"]["stdout"] == "ok"
    assert result["messages"][3]["role"] == "user"
    assert "<returncode>0</returncode>" in result["messages"][3]["content"]


def test_identical_action_without_progress_is_stopped_by_orchestrator(tools):
    model = Model(["```bash\nprintf ok\n```"] * 8)
    result = asyncio.run(drive(model, case(), tools))
    assert result["status"] == "orchestrator_no_progress"
    assert result["model_finished"] is False
    assert result["tool_call_count"] == 3


def test_native_finish_does_not_require_conversational_response(tools):
    model = Model(
        [
            '<tool_call>{"name":"Finish","arguments":{"status":"success","summary":"done"}}</tool_call>'
        ]
    )
    model.profile = {"protocol": "function_calling"}
    result = asyncio.run(drive(model, case(), tools))
    assert result["model_finished"] is True
    assert result["tool_call_count"] == 1
    assert result["messages"][2]["tool_calls"][0]["function"]["name"] == "Finish"


@pytest.mark.parametrize(
    "response,status",
    [
        ("plain text", "model_format_error"),
        (
            '<tool_call>{"name":"Terminal","arguments":{}}</tool_call>',
            "model_argument_error",
        ),
    ],
)
def test_model_format_and_argument_failures_are_explicit(tools, response, status):
    model = Model([response])
    model.profile = {"protocol": "function_calling"}
    result = asyncio.run(drive(model, case(), tools))
    assert result["status"] == status
    assert result["model_finished"] is False


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"status": "made_up", "summary": "x"},
        {"status": "success", "summary": ""},
        {"status": "success", "summary": "x", "hidden": 1},
    ],
)
def test_completion_validates_actual_arguments(tools, arguments):
    with pytest.raises(ValueError):
        tools.validate_completion(arguments)


def test_total_deadline_prevents_tool_execution_after_slow_generation(
    tools, monkeypatch
):
    from venom_core.services.maintenance_comparison import runner

    now = [0.0]
    monkeypatch.setattr(runner.time, "monotonic", lambda: now[0])

    class SlowModel(Model):
        def generate(self, *_):
            now[0] = 3
            return "```bash\nprintf ok\n```"

    result = asyncio.run(drive(SlowModel([]), case(), tools, seconds=2))
    assert result["status"] == "orchestrator_time_limit"
    assert tools.calls == []


def test_three_failed_correction_test_cycles_stop_the_attempt(tools):
    path = tools.habitat.workspace_path / "changed.py"

    def execute(command, timeout):
        if command.startswith("edit"):
            path.write_text(command)
        return {"stdout": "failure", "stderr": "", "exit_code": 1}

    tools.habitat.structured = execute
    model = Model(
        [
            f"```bash\n{command}\n```"
            for command in [
                "edit1",
                "pytest test_visible.py",
                "edit2",
                "pytest test_visible.py",
                "edit3",
                "pytest test_visible.py",
            ]
        ]
    )
    result = asyncio.run(
        drive(model, SimpleNamespace(role="repair", prompt="fix"), tools)
    )
    assert result["status"] == "orchestrator_correction_cycle_limit"
    assert len(tools.calls) == 6


def test_step_budget_is_independent_of_no_progress_detection(tools):
    model = Model([f"```bash\nprintf {i}\n```" for i in range(8)])
    result = asyncio.run(drive(model, case(), tools))
    assert result["status"] == "orchestrator_step_limit"
    assert result["termination_source"] == "orchestrator"
    assert len(tools.calls) == 8


def test_native_lfm_final_report_does_not_invent_a_finish_call(tools):
    model = Model(
        [
            '<|tool_call_start|>[Terminal(command="printf ok")]<|tool_call_end|>',
            "The command completed with exit code 0.",
        ]
    )
    model.profile = {"protocol": "lfm2_tool"}
    result = asyncio.run(drive(model, case(), tools))
    assert result["model_finished"]
    assert result["final"]["kind"] == "native_text"
    assert "status" not in result["final"]
    assert result["tool_call_count"] == 1


def test_explicit_flaky_mode_allows_three_identical_test_calls(tools):
    model = Model(
        ["```bash\npython -m pytest -q test_visible.py\n```"] * 3
        + ["```bash\nprintf finish\n```"]
    )
    original = tools.habitat.structured

    def execute(command, timeout):
        if command == "printf finish":
            return {
                "stdout": 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n{"status":"success","summary":"three consistent passes"}',
                "exit_code": 0,
                "stderr": "",
            }
        return original(command, timeout)

    tools.habitat.structured = execute
    result = asyncio.run(
        drive(
            model,
            SimpleNamespace(role="operator", prompt="repeat", flaky_probe=True),
            tools,
        )
    )
    assert result["model_finished"]
    assert result["tool_call_count"] == 4


def test_gemma_receives_native_response_mapping(tools):
    model = Model(
        [
            "<start_function_call>call:Terminal{command:<escape>printf ok<escape>}<end_function_call>",
            "<start_function_call>call:Finish{status:<escape>success<escape>,summary:<escape>observed ok<escape>}<end_function_call>",
        ]
    )
    model.profile = {"protocol": "functiongemma"}
    result = asyncio.run(drive(model, case(), tools))
    assert result["model_finished"]
    response = result["messages"][3]
    assert response["content"]["name"] == "Terminal"
    assert response["content"]["response"]["stdout"] == "ok"


def test_probe_cannot_call_unadvertised_finish_in_same_turn(tools):
    model = Model(
        [
            '<tool_call>{"name":"Terminal","arguments":{"command":"printf ok"}}</tool_call><tool_call>{"name":"Finish","arguments":{"status":"success","summary":"speculative"}}</tool_call>'
        ]
    )
    model.profile = {"protocol": "function_calling"}
    result = asyncio.run(
        drive(
            model,
            SimpleNamespace(role="operator", prompt="probe", protocol_probe=True),
            tools,
        )
    )
    assert result["status"] == "model_argument_error"
    assert not result["model_finished"]
    assert result["calls"][-1]["result"]["executed"] is False


def test_native_mini_swe_echo_ends_without_invented_finish_arguments(tools):
    tools.habitat.structured = lambda *_: {
        "stdout": "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n",
        "stderr": "",
        "exit_code": 0,
    }
    model = Model(
        [
            "The requested check passed.\n```mswea_bash_command\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```"
        ]
    )
    result = asyncio.run(drive(model, case(), tools))
    assert result["model_finished"]
    assert result["final"]["kind"] == "native_bash"
    assert "status" not in result["final"]


def test_context_view_is_explicitly_abridged_without_mutating_raw_result():
    from venom_core.services.maintenance_comparison.runner import _model_view

    raw = {"stdout": "a" * 20000, "stderr": "error", "exit_code": 0}
    view = _model_view(raw)
    assert len(raw["stdout"]) == 20000
    assert "model_view_abridged" not in raw
    assert view["model_view_abridged"]
    assert "characters omitted" in view["stdout"]


def test_tool_timeout_is_orchestrator_stop_not_model_format_error(tools):
    tools.habitat.structured = lambda *_: {
        "stdout": "",
        "stderr": "",
        "exit_code": 124,
        "execution_timed_out": True,
    }
    result = asyncio.run(drive(Model(["```bash\nsleep 60\n```"]), case(), tools))
    assert result["status"] == "orchestrator_tool_time_limit"
    assert not result["model_finished"]


def test_codescout_uses_native_names_and_submission_without_added_arguments(tools):
    model = Model(
        [
            '<tool_call>{"name":"terminal","arguments":{"command":"printf ok"}}</tool_call>',
            '<tool_call>{"name":"localization_finish","arguments":{"locations":[]}}</tool_call>',
        ]
    )
    model.profile = {"protocol": "localization"}
    result = asyncio.run(
        drive(model, SimpleNamespace(role="localization", prompt="find absent"), tools)
    )
    assert result["model_finished"]
    assert result["final"] == {"kind": "codescout_native", "locations": []}
    assert result["calls"][0]["name"] == "Terminal"
    assert result["calls"][0]["wire_name"] == "terminal"
    assert result["calls"][-1]["arguments"] == {"locations": []}


def test_changed_tool_observation_is_progress_even_when_files_are_unchanged(tools):
    model = Model(
        ["```bash\nprintf state\n```"] * 3
        + [
            '<tool_call>{"name":"Finish","arguments":{"status":"success","summary":"done"}}</tool_call>'
        ]
    )
    model.profile = {"protocol": "function_calling"}
    model.replies = iter(
        [
            '<tool_call>{"name":"Terminal","arguments":{"command":"printf state"}}</tool_call>'
        ]
        * 3
        + [
            '<tool_call>{"name":"Finish","arguments":{"status":"success","summary":"done"}}</tool_call>'
        ]
    )
    counter = [0]

    def execute(*_):
        counter[0] += 1
        return {"stdout": str(counter[0]), "stderr": "", "exit_code": 0}

    tools.habitat.structured = execute
    result = asyncio.run(drive(model, case(), tools))
    assert result["model_finished"]
    assert result["redundant_repetitions"] == 0


def test_backend_failure_retains_previous_real_tool_observation(tools):
    class Failing(Model):
        def generate(self, *args):
            if self.replies is not None:
                self.replies = None
                return '<tool_call>{"name":"Terminal","arguments":{"command":"printf ok"}}</tool_call>'
            raise RuntimeError("backend unavailable")

    model = Failing([])
    model.profile = {"protocol": "function_calling"}
    result = asyncio.run(drive(model, case(), tools))
    assert result["status"] == "infrastructure_generation:RuntimeError"
    assert result["calls"][0]["result"]["stdout"] == "ok"
    assert result["termination_source"] == "infrastructure"
    assert result["infrastructure_error"]["phase"] == "generation"


def test_tool_infrastructure_failure_records_unknown_execution_instead_of_fake_exit(
    tools,
):
    def unavailable(*_):
        raise OSError("sandbox transport unavailable")

    tools.habitat.structured = unavailable
    model = Model(
        [
            '<tool_call>{"name":"Terminal","arguments":{"command":"printf ok"}}</tool_call>'
        ]
    )
    model.profile = {"protocol": "function_calling"}
    result = asyncio.run(drive(model, case(), tools))
    assert result["status"] == "infrastructure_tool:OSError"
    assert result["calls"][0]["result"]["exit_code"] is None
    assert result["calls"][0]["result"]["execution_state"] == "unknown"
