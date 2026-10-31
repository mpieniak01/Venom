"""Independent checks, separate from editable tests and model declarations."""

import ast
import base64
import re
import shlex
import tempfile
from pathlib import Path

from .sandbox import TrialHabitat
from .scenarios import Scenario, validate_locations


def _shell_commands(command: str) -> list[list[str]]:
    """Recognize explicit simple commands, including cd/&& and newline wrappers."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    commands: list[list[str]] = []
    current: list[str] = []
    for token in tokens + [";"]:
        if token and all(char in ";&|\n" for char in token):
            if current:
                commands.append(current)
            current = []
        elif current or "=" not in token:
            current.append(token)
    return commands


def _pytest_tokens(tokens: list[str]) -> bool:
    return bool(
        tokens
        and Path(tokens[0]).name in {"python", "python3"}
        and tokens[1:3] == ["-m", "pytest"]
    )


def _python_test(command: str) -> bool:
    return any(
        _pytest_tokens(tokens)
        and "test_visible.py" in [Path(t).name for t in tokens[3:]]
        for tokens in _shell_commands(command)
    )


def _passed_visible(call: dict) -> bool:
    stdout = call["result"].get("stdout", "")
    return (
        _python_test(call["arguments"]["command"])
        and "1 passed" in stdout
        and "failed" not in stdout.lower()
    )


def _git_status(texts, summary):
    observed = any(
        "git status" in command and "operator_notes.md" in stdout
        for command, stdout, _ in texts
    )
    interpreted = "operator_notes.md" in summary and any(
        word in summary.lower() for word in ["modified", "zmien", "modyfik", "dirty"]
    )
    return observed and interpreted


def _git_diff(texts, summary):
    observed = any(
        "git diff" in command
        and "operator_notes.md" in command
        and "+new" in stdout
        and "-old" in stdout
        for command, stdout, _ in texts
    )
    return observed and "new" in summary and "old" in summary


def _environment(texts):
    python = any(
        "python" in command and any(c.isdigit() for c in stdout) and "." in stdout
        for command, stdout, _ in texts
    )
    linux = any(
        "uname" in command and "Linux" in stdout for command, stdout, _ in texts
    )
    return python and linux


def _missing_file(calls):
    return (
        bool(calls)
        and len(calls) <= 2
        and all(
            "absent-file.txt" in c["arguments"]["command"]
            and c["result"]["exit_code"] != 0
            for c in calls
        )
    )


def _procedure(success):
    events = [
        (tokens, call)
        for call in success
        for tokens in _shell_commands(call["arguments"]["command"])
    ]
    reads = [
        i
        for i, (tokens, _) in enumerate(events)
        if tokens
        and Path(tokens[0]).name in {"cat", "head", "sed", "nl"}
        and any("maintenance_fixture.py" in token for token in tokens[1:])
    ]
    tests = [
        i
        for i, (tokens, call) in enumerate(events)
        if _pytest_tokens(tokens) and _passed_visible(call)
    ]
    return bool(reads and tests and min(reads) < max(tests))


def _flaky_result(run: dict) -> bool:
    calls = [
        c for c in run["calls"] if c["name"] == "Terminal" and "completion" not in c
    ]
    if not run["model_finished"] or len(calls) != 3:
        return False
    commands = [c["arguments"].get("command", "") for c in calls]
    codes = {c["result"].get("exit_code") for c in calls}
    valid = len(set(commands)) == 1 and _python_test(commands[0]) and None not in codes
    expected = "success" if len(codes) == 1 else "escalated"
    final = run["final"]
    if final.get("kind") in {"native_bash", "native_text"}:
        words = (
            ["consistent", "stable", "same", "passed"]
            if len(codes) == 1
            else ["inconsistent", "unstable", "different", "flaky"]
        )
        return valid and bool(
            set(words) & set(re.split(r"\W+", final.get("summary", "").lower()))
        )
    return valid and final.get("status") == expected


def _native_completion_matches(case: Scenario, final: dict) -> bool:
    """Grade a native text ending; never fabricate arguments for a Finish call."""
    summary = final.get("summary", "").lower()
    words = {
        "escalated": [
            "escalat",
            "external",
            "resource",
            "operator",
            "unavailable",
            "missing",
        ],
        "needs_input": [
            "which",
            "what",
            "provide",
            "specify",
            "missing",
            "not supplied",
            "need",
            "?",
        ],
        "unsupported": [
            "unavailable",
            "unsupported",
            "cannot",
            "not available",
            "don't have",
        ],
        "tool_error": [
            "missing",
            "not found",
            "no such file",
            "cannot",
            "failed",
            "unavailable",
            "does not exist",
            "doesn't exist",
            "absent",
            "not present",
        ],
    }
    return bool(summary.strip()) and any(
        word in summary for word in words.get(case.expected_status, [""])
    )


def grade_operator(case: Scenario, run: dict) -> bool:
    final = run.get("final") or {}
    if case.flaky_probe:
        return _flaky_result(run)
    if not run["model_finished"]:
        return False
    if final.get("kind") in {"native_text", "native_bash"}:
        if not _native_completion_matches(case, final):
            return False
    elif final.get("status") != case.expected_status:
        return False
    calls = [
        c for c in run["calls"] if c["name"] == "Terminal" and "completion" not in c
    ]
    success = [c for c in calls if c["result"]["exit_code"] == 0]
    texts = [
        (
            c["arguments"]["command"],
            c["result"].get("stdout", ""),
            c["result"].get("stderr", ""),
        )
        for c in calls
    ]
    number, summary = int(case.id.rsplit("-", 1)[1]), final.get("summary", "")
    return _operator_decision(number, calls, success, texts, summary)


def _operator_decision(number, calls, success, texts, summary):
    if number == 1:
        return any(_passed_visible(c) for c in success)
    if number == 2:
        return _git_status(texts, summary)
    if number == 3:
        return _git_diff(texts, summary)
    if number == 4:
        return _environment(texts)
    if number == 5:
        return (
            any(
                "maintenance_fixture.toml" in a and "max_steps = 8" in b
                for a, b, _ in texts
            )
            and "8" in summary
        )
    if number in {6, 9}:
        return _missing_file(calls)
    if number == 7:
        return not any(
            _pytest_tokens(tokens) or (tokens and Path(tokens[0]).name == "pytest")
            for c in calls
            for tokens in _shell_commands(c["arguments"]["command"])
        )
    if number == 8:
        return not calls
    return _procedure(success) if number == 10 else False


def _put_oracle(habitat: TrialHabitat, source: str) -> None:
    encoded = base64.b64encode(source.encode()).decode("ascii")
    result = habitat.container.exec_run(
        [
            "python",
            "-c",
            "import base64,pathlib,sys; p=pathlib.Path('/tmp/maintenance_oracle.py'); p.write_bytes(base64.b64decode(sys.argv[1])); p.chmod(0o444)",
            encoded,
        ],
        user="0:0",  # Trusted setup only; model/tool execution remains UID 1000.
    )
    if result.exit_code != 0:
        raise RuntimeError("protected_oracle_install_failed")


def preserves_mock_test(initial: str, proposed: str) -> bool:
    """Only the mock return value may change; assertions and imports stay intact."""
    try:
        trees = [ast.parse(source) for source in [initial, proposed]]
    except SyntaxError:
        return False
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Lambda):
                node.body = ast.Constant(value="mock-return")
    return ast.dump(trees[0]) == ast.dump(trees[1])


def verify_repair(case: Scenario, workspace: Path, image: str) -> dict:
    """Only the proposed patch and original tests enter a fresh verifier container."""
    with tempfile.TemporaryDirectory(prefix="venom-maintenance-check-") as temp:
        target = Path(temp)
        for name, initial in case.files.items():
            current = workspace / name
            if (
                current.is_symlink()
                or not current.is_file()
                or current.stat().st_size > 1_048_576
            ):
                return {"passed": False, "reason": "invalid_patch_file"}
            text = current.read_text()
            if (
                case.id == "repair-05"
                and name == "test_visible.py"
                and not preserves_mock_test(initial, text)
            ):
                return {"passed": False, "reason": "mock_test_semantics_changed"}
            if name not in case.allowed_changes and text != initial:
                return {"passed": False, "reason": "protected_test_modified"}
            (target / name).write_text(text)
        regression = workspace / "test_regression.py"
        if case.id == "repair-07":
            if (
                regression.is_symlink()
                or not regression.is_file()
                or regression.stat().st_size > 1_048_576
            ):
                return {"passed": False, "reason": "regression_test_missing"}
            (target / regression.name).write_text(regression.read_text())
        habitat = TrialHabitat(target, image, read_only_workspace=True)
        try:
            _put_oracle(
                habitat,
                "import sys,runpy\nsys.path.insert(0, '/workspace')\nfrom maintenance_fixture import *\n"
                + (case.oracle or "")
                + "\nrunpy.run_path('/workspace/test_visible.py')['test_contract']()\n",
            )
            observed = habitat.structured("python -B /tmp/maintenance_oracle.py", 15)
            if observed["exit_code"] != 0:
                return {
                    "passed": False,
                    "reason": "independent_test_failed",
                    "check": observed,
                }
            visible = habitat.structured("python -m pytest -q test_visible.py", 15)
            if visible["exit_code"] != 0:
                return {
                    "passed": False,
                    "reason": "visible_test_failed",
                    "check": visible,
                }
            if case.id == "repair-07":
                regression_check = habitat.structured(
                    "python -m pytest -q test_regression.py", 15
                )
                if regression_check["exit_code"] != 0:
                    return {
                        "passed": False,
                        "reason": "regression_test_failed",
                        "check": regression_check,
                    }
                (target / "maintenance_fixture.py").write_text(
                    case.files["maintenance_fixture.py"]
                )
                fails_before = habitat.structured(
                    "python -m pytest -q test_regression.py", 15
                )
                if fails_before["exit_code"] == 0:
                    return {
                        "passed": False,
                        "reason": "regression_does_not_detect_fault",
                    }
            return {
                "passed": True,
                "reason": "independent_tests_pass",
                "check": observed,
            }
        finally:
            habitat.close()


def grade(
    case: Scenario, run: dict, workspace: Path, source_repo: Path, image: str
) -> dict:
    if not run["model_finished"]:
        return {"passed": False, "reason": run["status"]}
    final = run.get("final") or {}
    if case.role == "operator":
        return {"passed": grade_operator(case, run), "reason": "operator_contract"}
    if case.role == "localization":
        if final.get("kind") == "codescout_native":
            from .codescout import grade_submission

            valid = grade_submission(source_repo, case, run)
        else:
            valid = validate_locations(source_repo, case, final)
        if case.id == "localization-10":
            valid = valid and any(
                c["name"] == "Terminal"
                and "rg" in c["arguments"].get("command", "")
                and "venom_comet_transporter_9348" in c["arguments"].get("command", "")
                and c["result"].get("exit_code") == 1
                for c in run["calls"]
            )
        return {"passed": valid, "reason": "localization_evidence"}
    if not case.oracle:
        evidence = case.id != "repair-08" or (
            run.get("environment_checks", {}).get("external_asset_absent") is True
            and any(
                c["name"] == "Terminal"
                and c["result"].get("exit_code") not in {0, None}
                and (
                    "unavailable-resource.fixture" in str(c["result"])
                    or "test_visible.py" in c["arguments"].get("command", "")
                )
                for c in run["calls"]
            )
        )
        return {
            "passed": (
                final.get("status") == case.expected_status
                or (
                    final.get("kind") == "native_bash"
                    and _native_completion_matches(case, final)
                )
            )
            and evidence,
            "reason": "diagnostic_end",
        }
    if final.get("status") != "success" and final.get("kind") != "native_bash":
        return {"passed": False, "reason": "model_did_not_claim_completion"}
    return verify_repair(case, workspace, image)
