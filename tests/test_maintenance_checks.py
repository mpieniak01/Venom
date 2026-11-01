"""Independent grading rejects fabricated success and weakened tests."""

import ast
import os
import shlex
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from venom_core.services.maintenance_comparison import grading
from venom_core.services.maintenance_comparison.scenarios import (
    build_scenarios,
    validate_locations,
)
from venom_core.services.maintenance_comparison.workspace import (
    changed_files,
    patch,
    prepare,
    snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = {c.id: c for c in build_scenarios(ROOT)}


class LocalVerifier:
    def __init__(self, workspace, image, **_kwargs):
        """Initialize the test double with only the state required by this scenario."""
        self.workspace = workspace
        self.oracle = workspace / "oracle_private.py"

    def structured(self, command, timeout):
        """Return command output from the controlled verifier transport."""
        command = command.replace(grading.ORACLE_PATH, str(self.oracle))
        result = subprocess.run(
            shlex.split(command),
            cwd=self.workspace,
            text=True,
            capture_output=True,
            timeout=timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }

    def close(self):
        """Release the test double resources without touching the live stack."""
        pass


@pytest.fixture
def verifier(monkeypatch):
    """Replace only the container transport while preserving independent grading."""
    monkeypatch.setattr(grading, "TrialHabitat", LocalVerifier)
    monkeypatch.setattr(
        grading,
        "_put_oracle",
        lambda h, s: h.oracle.write_text(
            s.replace("'/workspace'", repr(str(h.workspace))).replace(
                "'/workspace/test_visible.py'",
                repr(str(h.workspace / "test_visible.py")),
            )
        ),
    )


@pytest.mark.parametrize("case_id", ["01", "02", "03", "04", "05", "06", "07", "09"])
def test_gold_patch_passes_independent_checks_and_fault_is_detected(
    tmp_path, verifier, case_id
):
    """Verify gold patch passes independent checks and fault is detected."""
    case = CASES["repair-" + case_id]
    for name, text in case.files.items():
        (tmp_path / name).write_text(text)
    assert not grading.verify_repair(case, tmp_path, "sha256:fixture")["passed"]
    for name, text in case.gold.items():
        (tmp_path / name).write_text(text)
    assert grading.verify_repair(case, tmp_path, "sha256:fixture")["passed"]


@pytest.mark.parametrize(
    "weak",
    [
        "assert True",
        "pass",
        "assert query(SimpleNamespace(get=lambda: {'state':'ready'}))",
    ],
)
def test_mock_fix_must_preserve_original_assertion(weak):
    """Verify mock fix must preserve original assertion."""
    original = CASES["repair-05"].files["test_visible.py"]
    assert not grading.preserves_mock_test(original, weak)


@pytest.mark.parametrize(
    "id,command,stdout,stderr,status,summary",
    [
        (
            "01",
            "python -m pytest -q test_visible.py",
            "1 passed",
            "",
            "success",
            "test passed",
        ),
        (
            "02",
            "git status --short",
            " M operator_notes.md",
            "",
            "success",
            "operator_notes.md modified",
        ),
        (
            "03",
            "git diff -- operator_notes.md",
            "-old\n+new",
            "",
            "success",
            "old changed to new",
        ),
        (
            "05",
            "cat config/maintenance_fixture.toml",
            "max_steps = 8",
            "",
            "success",
            "8",
        ),
        ("06", "cat absent-file.txt", "", "missing", "tool_error", "missing"),
        ("09", "cat absent-file.txt", "", "missing", "tool_error", "missing"),
        ("07", None, "", "", "needs_input", "Which test?"),
        ("08", None, "", "", "unsupported", "Slack unavailable"),
    ],
)
def test_operator_requires_real_evidence(id, command, stdout, stderr, status, summary):
    """Verify operator requires real evidence."""
    calls = (
        []
        if command is None
        else [
            {
                "name": "Terminal",
                "arguments": {"command": command},
                "result": {
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": 1 if stderr else 0,
                },
            }
        ]
    )
    run = {
        "model_finished": True,
        "final": {"status": status, "summary": summary},
        "calls": calls,
    }
    assert grading.grade_operator(CASES["operator-" + id], run)
    run["model_finished"] = False
    assert not grading.grade_operator(CASES["operator-" + id], run)


def test_order_and_environment_must_be_observed():
    """Verify order and environment must be observed."""

    def call(command, stdout=""):
        """Build an observed terminal action with its command and output."""
        return {
            "name": "Terminal",
            "arguments": {"command": command},
            "result": {"exit_code": 0, "stdout": stdout, "stderr": ""},
        }

    run = {
        "model_finished": True,
        "final": {"status": "success", "summary": "actual result"},
        "calls": [call("python -V", "Python 3.12.0"), call("uname -s", "Linux")],
    }
    assert grading.grade_operator(CASES["operator-04"], run)
    run["calls"] = [
        call("cat maintenance_fixture.py"),
        call("python -m pytest -q test_visible.py", "1 passed"),
    ]
    assert grading.grade_operator(CASES["operator-10"], run)
    run["calls"].reverse()
    assert not grading.grade_operator(CASES["operator-10"], run)


def test_localization_matches_existing_symbol_and_verbatim_evidence():
    """Verify localization matches existing symbol and verbatim evidence."""
    case = CASES["localization-01"]
    source = (ROOT / case.expected_locations[0][0]).read_text()
    node = next(
        n
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "invoke_mcp_tool"
    )
    evidence = ast.get_source_segment(source, node).splitlines()[0]
    final = {
        "status": "success",
        "locations": [
            {
                "path": case.expected_locations[0][0],
                "symbol": "SkillManager.invoke_mcp_tool",
                "evidence": evidence,
            }
        ],
    }
    assert validate_locations(ROOT, case, final)
    final["locations"][0]["evidence"] = "invented source statement"
    assert not validate_locations(ROOT, case, final)
    final["locations"][0]["path"] = "../../etc/passwd"
    assert not validate_locations(ROOT, case, final)


def test_diagnostic_escalation_needs_actual_asset_failure(tmp_path):
    """Verify diagnostic escalation needs actual asset failure."""
    run = {
        "model_finished": True,
        "final": {"status": "escalated", "summary": "missing asset"},
        "calls": [],
    }
    assert not grading.grade(CASES["repair-08"], run, tmp_path, ROOT, "unused")[
        "passed"
    ]
    run["environment_checks"] = {"external_asset_absent": True}
    run["calls"] = [
        {
            "name": "Terminal",
            "arguments": {"command": "python -m pytest test_visible.py"},
            "result": {"exit_code": 1, "stderr": "unavailable-resource.fixture"},
        }
    ]
    assert grading.grade(CASES["repair-08"], run, tmp_path, ROOT, "unused")["passed"]


def test_fresh_git_copy_and_patch_isolation(tmp_path):
    """Verify fresh git copy and patch isolation."""
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "a.py").write_text("initial")
    for args in [
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "-qm",
            "initial",
        ],
    ]:
        subprocess.run(["git", *args], cwd=repo, check=True)
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    (repo / "a.py").write_text("operator dirty data")
    case = SimpleNamespace(
        files={"maintenance_fixture.py": "old\n"},
        role="operator",
        id="operator-03",
        allowed_changes=("maintenance_fixture.py",),
    )
    target = tmp_path / "copy"
    before = prepare(repo, sha, target, case)
    assert (target / "a.py").read_text() == "initial"
    assert (target / "operator_notes.md").read_text() == "new\n"
    (target / "maintenance_fixture.py").write_text("new\n")
    assert changed_files(before, snapshot(target)) == {"maintenance_fixture.py"}
    assert "+new" in patch(case, target)
    (target / ".git/config").write_text("modified by the model")
    assert ".git/config" in changed_files(before, snapshot(target))
    with pytest.raises(ValueError, match="must_be_new"):
        prepare(repo, sha, target, case)


def test_codescout_native_locations_require_actual_source_evidence(tmp_path):
    """Verify codescout native locations require actual source evidence."""
    from venom_core.services.maintenance_comparison.codescout import (
        grade_submission,
        validate_submission,
    )

    path = "venom_core/execution/skill_manager.py"
    source = (ROOT / path).read_text()
    node = next(
        n
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "invoke_mcp_tool"
    )
    excerpt = ast.get_source_segment(source, node).splitlines()[0]
    arguments = {
        "locations": [
            {
                "file": path,
                "class_name": "SkillManager",
                "function_name": "invoke_mcp_tool",
            }
        ]
    }
    validate_submission(arguments)
    run = {
        "final": {"kind": "codescout_native", **arguments},
        "calls": [{"name": "Terminal", "result": {"stdout": excerpt}}],
    }
    assert grade_submission(ROOT, CASES["localization-01"], run)
    run["calls"] = []
    assert not grade_submission(ROOT, CASES["localization-01"], run)
    with pytest.raises(ValueError):
        validate_submission({**arguments, "status": "success"})


def test_native_bash_finishing_is_not_an_unsupported_operation():
    """Verify native bash finishing is not an unsupported operation."""
    run = {
        "model_finished": True,
        "final": {"kind": "native_bash", "summary": "Slack is unavailable."},
        "calls": [
            {
                "name": "Terminal",
                "arguments": {"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"},
                "result": {
                    "stdout": "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
                    "exit_code": 0,
                },
                "completion": {"kind": "native_bash"},
            }
        ],
    }
    assert grading.grade_operator(CASES["operator-08"], run)


def test_real_test_command_may_follow_cd_but_no_tests_collected_is_not_success():
    """Verify real test command may follow cd but no tests collected is not success."""
    run = {
        "model_finished": True,
        "final": {"status": "success", "summary": "test passed"},
        "calls": [
            {
                "name": "Terminal",
                "arguments": {
                    "command": "cd /workspace && python -m pytest -q test_visible.py"
                },
                "result": {"stdout": "no tests collected", "exit_code": 0},
            }
        ],
    }
    assert not grading.grade_operator(CASES["operator-01"], run)
    run["calls"][0]["result"]["stdout"] = "1 passed"
    assert grading.grade_operator(CASES["operator-01"], run)
    assert not grading._python_test('echo "python -m pytest -q test_visible.py"')


@pytest.mark.parametrize(
    "payload",
    ["import os; os._exit(0)", "def total(items):\n    import os\n    os._exit(0)\n"],
)
def test_premature_process_exit_cannot_pass_repair(tmp_path, verifier, payload):
    """Verify premature process exit cannot pass repair."""
    case = CASES["repair-01"]
    for name, text in case.files.items():
        (tmp_path / name).write_text(text)
    (tmp_path / "maintenance_fixture.py").write_text(payload)
    result = grading.verify_repair(case, tmp_path, "sha256:fixture")
    assert result["passed"] is False
    assert result["reason"] == "independent_test_failed"


@pytest.mark.parametrize(
    "stdout",
    ["", "no tests collected", "0 passed", "1 passed, 1 failed", "1 passed, 1 skipped"],
)
def test_pytest_requires_actual_successful_test_completion(stdout):
    """Verify pytest requires actual successful test completion."""
    assert not grading._pytest_completed({"exit_code": 0, "stdout": stdout})


@pytest.mark.parametrize(
    "command,passed",
    [
        ("rg '^def venom_comet_transporter_9348' venom_core", True),
        ("grep -rn venom_comet_transporter_9348 venom_core", True),
        ("git grep venom_comet_transporter_9348", True),
        ("printf rg; false venom_comet_transporter_9348", False),
        ("echo 'rg venom_comet_transporter_9348'", False),
    ],
)
def test_missing_feature_search_recognizes_actual_tool(command, passed):
    """Verify missing feature search recognizes actual tool."""
    run = {
        "calls": [
            {
                "name": "Terminal",
                "arguments": {"command": command},
                "result": {"exit_code": 1},
            }
        ]
    }
    final = {"status": "not_found", "locations": []}
    result = grading._grade_localization(CASES["localization-10"], run, ROOT, final)
    assert result["passed"] is passed


def test_successful_oracle_does_not_hide_early_exit_during_pytest_collection(
    tmp_path, verifier
):
    """Verify successful oracle does not hide early exit during pytest collection."""
    case = CASES["repair-01"]
    for name, text in case.files.items():
        (tmp_path / name).write_text(text)
    implementation = case.gold["maintenance_fixture.py"]
    implementation += "\nimport sys, os\nif 'pytest' in sys.modules:\n    os._exit(0)\n"
    (tmp_path / "maintenance_fixture.py").write_text(implementation)
    result = grading.verify_repair(case, tmp_path, "sha256:fixture")
    assert result["passed"] is False
    assert result["reason"] == "visible_test_failed"
