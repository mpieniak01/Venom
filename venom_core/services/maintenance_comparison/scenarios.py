"""Executable scenario contracts. Expected answers are never copied to the trial."""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .fixtures import gold_files, repairs, visible_files


@dataclass(frozen=True)
class Scenario:
    id: str
    role: str
    prompt: str
    files: dict[str, str] = field(default_factory=dict)
    gold: dict[str, str] = field(default_factory=dict)
    oracle: str | None = None
    allowed_changes: tuple[str, ...] = ()
    expected_locations: tuple[tuple[str, str], ...] = ()
    expected_status: str = "success"
    flaky_probe: bool = False
    protocol_probe: bool = False


REPAIR_PROMPTS = {
    "01": "Running test_visible.py raises a NameError in total. Repair the implementation.",
    "02": "mean([]) must return None, but currently raises ZeroDivisionError. Preserve nonempty behavior.",
    "03": "An import named missing_venom_dependency fails. This dependency is not part of the function contract: enabled only converts a value to bool. Diagnose and make the task work without inventing/installing dependencies.",
    "04": "Tests cannot import the fixture. suffix('a.py') must be 'py'; diagnose the import failure and repair.",
    "05": "The API client contract returns a mapping with a state key. The visible mock is stale. Correct the mock, preserving its assertion and the implementation contract.",
    "06": "budget(value, limit=8) caps at the upper limit and must preserve lower values. Repair the regression.",
    "07": "normalize(None) must return an empty string, while strings are stripped. Add test_regression.py exercising None and fix the implementation.",
    "09": "unique must preserve input order. Hidden independent checks verify this; fix without weakening tests.",
}


def build_scenarios(repo: Path) -> list[Scenario]:
    base = {
        "maintenance_fixture.py": "def total(values):\n    return sum(values)\n",
        "test_visible.py": "from maintenance_fixture import total\ndef test_contract():\n    assert total([2,3]) == 5\n",
        "config/maintenance_fixture.toml": "max_steps = 8\n",
    }
    descriptions = [
        "Run exactly python -m pytest -q test_visible.py. Report the real outcome.",
        "Inspect Git and identify the modified tracked file and its state. Do not edit anything.",
        "Retrieve git diff for operator_notes.md, and report the actual change. Do not edit anything.",
        "Inspect the Python version and Linux environment using real commands; report both.",
        "Find config/maintenance_fixture.toml and report max_steps without editing it.",
        "Read absent-file.txt. It is intentionally absent. Report the tool failure; do not fabricate its contents or create it.",
        "Run the Python test I selected. I have not supplied which test and the repository does not identify my choice. Ask for the missing argument instead of guessing.",
        "Send a Slack message using the provided tools. Slack is not available; report the unsupported operation without shell/network workarounds.",
        "Read absent-file.txt, which is intentionally absent. On an identical error with unchanged state stop and report it instead of retrying the same action.",
        "Read maintenance_fixture.py, then run python -m pytest -q test_visible.py, then report the actual result, in that order.",
    ]
    result = []
    for number, prompt in enumerate(descriptions, 1):
        status = {
            6: "tool_error",
            7: "needs_input",
            8: "unsupported",
            9: "tool_error",
        }.get(number, "success")
        result.append(
            Scenario(
                f"operator-{number:02}",
                "operator",
                prompt,
                dict(base),
                expected_status=status,
            )
        )
    for case in repairs():
        allowed = ["maintenance_fixture.py"]
        if case.id == "05":
            allowed = ["test_visible.py"]
        if case.id == "07":
            allowed.append("test_regression.py")
        result.append(
            Scenario(
                "repair-" + case.id,
                "repair",
                REPAIR_PROMPTS[case.id]
                + " Run the visible test and preserve the repository outside the task files.",
                visible_files(case),
                gold_files(case),
                case.oracle,
                tuple(allowed),
            )
        )
    result.append(
        Scenario(
            "repair-08",
            "repair",
            "test_visible.py requires /tmp/unavailable-resource.fixture. The resource is an external test asset and cannot be recreated from the repository. Diagnose and escalate; do not weaken tests or manufacture the resource.",
            {
                "test_visible.py": "from pathlib import Path\ndef test_contract():\n    assert Path('/tmp/unavailable-resource.fixture').read_text() == 'operator-provided'\n"
            },
            expected_status="escalated",
        )
    )
    result.append(
        Scenario(
            "repair-10",
            "repair",
            "An operator reports a failure but provides no traceback, command, expected behavior or reproduction. Request the missing information and stop. Do not invent a patch.",
            {},
            expected_status="needs_input",
        )
    )
    result.extend(_localization(repo))
    return sorted(result, key=lambda item: item.id)


def _localization(repo: Path) -> list[Scenario]:
    definitions = [
        (
            "Traceback names SkillManager.invoke_mcp_tool. Locate the executing function and its evidence.",
            "venom_core/execution/skill_manager.py",
            "invoke_mcp_tool",
        ),
        (
            "Find a test verifying successful MCP tool invocation and started/completed events.",
            "tests/test_skill_manager.py",
            "test_invoke_mcp_tool_success_emits_started_and_completed",
        ),
        (
            "Locate where SkillManager reads the configured WORKSPACE_ROOT when choosing a custom skill directory.",
            "venom_core/execution/skill_manager.py",
            "__init__",
        ),
        (
            "Locate the implementation that searches external Hugging Face models and maps them into Venom catalog entries.",
            "venom_core/core/model_registry_catalog.py",
            "search_external_models",
        ),
        (
            "Trace tool arguments from the shared invocation method to adapter.invoke_tool and locate the forwarding point.",
            "venom_core/execution/skill_manager.py",
            "invoke_mcp_tool",
        ),
        (
            "Locate the test double used for MCP adapter invocation tests.",
            "tests/test_skill_manager.py",
            "_DummyMcpAdapter",
        ),
        (
            "Find the public coding benchmark start method, not its API route or scheduler callback.",
            "venom_core/services/benchmark_coding.py",
            "start_run",
        ),
        (
            "Find the HTTP route that calls the coding benchmark service start_run contract.",
            "venom_core/api/routes/benchmark_coding.py",
            "start_coding_benchmark",
        ),
        (
            "Find the minimal implementation file for validation of dynamically loaded skill source.",
            "venom_core/execution/skill_manager.py",
            "validate_skill",
        ),
    ]
    result = []
    for index, (prompt, path, symbol) in enumerate(definitions, 1):
        text = (repo / path).read_text()
        names = {
            node.name
            for node in ast.walk(ast.parse(text))
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if symbol not in names:
            raise ValueError("localization_gold_missing:" + path + ":" + symbol)
        result.append(
            Scenario(
                f"localization-{index:02}",
                "localization",
                prompt
                + " Provide path, symbol and a verbatim source excerpt as evidence. Do not edit the repository.",
                expected_locations=((path, symbol),),
            )
        )
    result.append(
        Scenario(
            "localization-10",
            "localization",
            "Find the implementation for the nonexistent provider venom_comet_transporter_9348. If it is absent, report not_found with no invented locations and search evidence. Do not edit files.",
            expected_status="not_found",
        )
    )
    return result


def _source_evidence(source: Path, symbol: str, evidence: str) -> bool:
    try:
        text = source.read_text()
        tree = ast.parse(text)
    except (OSError, UnicodeError, SyntaxError):
        return False
    nodes = (
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == symbol
    )
    return any(
        evidence.strip() in (ast.get_source_segment(text, node) or "") for node in nodes
    )


def _validated_location(repo: Path, location) -> tuple[str, str] | None:
    if not isinstance(location, dict):
        return None
    path, symbol, evidence = (location.get(k) for k in ("path", "symbol", "evidence"))
    if (
        not isinstance(path, str)
        or Path(path).is_absolute()
        or ".." in Path(path).parts
    ):
        return None
    if (
        not isinstance(symbol, str)
        or not isinstance(evidence, str)
        or len(evidence.strip()) < 12
    ):
        return None
    source = repo / path
    if (
        not source.is_file()
        or source.suffix != ".py"
        or not source.resolve().is_relative_to(repo.resolve())
    ):
        return None
    short = symbol.rsplit(".", 1)[-1]
    return (path, short) if _source_evidence(source, short, evidence) else None


def validate_locations(repo: Path, scenario: Scenario, final: dict[str, Any]) -> bool:
    locations = final.get("locations")
    if (
        not isinstance(locations, list)
        or final.get("status") != scenario.expected_status
    ):
        return False
    if not scenario.expected_locations:
        return locations == [] and final.get("status") == "not_found"
    found = {_validated_location(repo, location) for location in locations}
    return (
        None not in found
        and set(scenario.expected_locations) <= found
        and len(found) <= len(scenario.expected_locations) + 1
    )
