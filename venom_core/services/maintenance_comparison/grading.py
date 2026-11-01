"""Independent checks, separate from editable tests and model declarations."""

import ast
import base64
import re
import secrets
import shlex
import tempfile
from pathlib import Path

from .sandbox import ORACLE_PATH, TrialHabitat
from .scenarios import Scenario, validate_locations

VISIBLE_TEST = "test_visible.py"
OPERATOR_NOTES = "operator_notes.md"
FIXTURE_MODULE = "maintenance_fixture.py"
REGRESSION_TEST = "test_regression.py"


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
    """Recognize Python executables invoked with -m pytest."""
    return bool(
        tokens
        and Path(tokens[0]).name in {"python", "python3"}
        and tokens[1:3] == ["-m", "pytest"]
    )


def _python_test(command: str) -> bool:
    """Detect a Python pytest invocation naming the visible contract test."""
    return any(
        _pytest_tokens(tokens) and VISIBLE_TEST in [Path(t).name for t in tokens[3:]]
        for tokens in _shell_commands(command)
    )


def _passed_visible(call: dict) -> bool:
    """Require a real successful visible-test invocation and its completion summary."""
    stdout = call["result"].get("stdout", "")
    return (
        _python_test(call["arguments"]["command"])
        and "1 passed" in stdout
        and "failed" not in stdout.lower()
    )


def _git_status(texts, summary):
    """Match the reported dirty file against observed Git status output."""
    observed = any(
        "git status" in command and OPERATOR_NOTES in stdout
        for command, stdout, _ in texts
    )
    interpreted = OPERATOR_NOTES in summary and any(
        word in summary.lower() for word in ["modified", "zmien", "modyfik", "dirty"]
    )
    return observed and interpreted


def _git_diff(texts, summary):
    """Require the expected old and new lines in the observed file diff."""
    observed = any(
        "git diff" in command
        and OPERATOR_NOTES in command
        and "+new" in stdout
        and "-old" in stdout
        for command, stdout, _ in texts
    )
    return observed and "new" in summary and "old" in summary


def _environment(texts):
    """Check that tool output contains the requested Python and Linux metadata."""
    python = any(
        "python" in command and any(c.isdigit() for c in stdout) and "." in stdout
        for command, stdout, _ in texts
    )
    linux = any(
        "uname" in command and "Linux" in stdout for command, stdout, _ in texts
    )
    return python and linux


def _missing_file(calls):
    """Require an actual failed read of the named unavailable file."""
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
    """Check that file inspection precedes a successful visible test run."""
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
        and any(FIXTURE_MODULE in token for token in tokens[1:])
    ]
    tests = [
        i
        for i, (tokens, call) in enumerate(events)
        if _pytest_tokens(tokens) and _passed_visible(call)
    ]
    return bool(reads and tests and min(reads) < max(tests))


def _flaky_result(run: dict) -> bool:
    """Evaluate the explicitly requested repeated-test diagnostic separately from repair."""
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
    """Score operator behavior using real calls and evidence for the requested case."""
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
    """Apply the case-specific operation, argument and completion criteria."""
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
    """Install root-owned read-only verifier source outside the writable workspace."""
    encoded = base64.b64encode(source.encode()).decode("ascii")
    result = habitat.container.exec_run(
        [
            "python",
            "-c",
            f"import base64,pathlib,sys; p=pathlib.Path({ORACLE_PATH!r}); p.write_bytes(base64.b64decode(sys.argv[1])); p.chmod(0o444)",
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


def _copy_proposed_files(case: Scenario, workspace: Path, target: Path) -> dict | None:
    """Copy only permitted regular repair files into the independent verifier copy."""
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
            and name == VISIBLE_TEST
            and not preserves_mock_test(initial, text)
        ):
            return {"passed": False, "reason": "mock_test_semantics_changed"}
        if name not in case.allowed_changes and text != initial:
            return {"passed": False, "reason": "protected_test_modified"}
        (target / name).write_text(text)
    regression = workspace / REGRESSION_TEST
    if case.id == "repair-07":
        if (
            regression.is_symlink()
            or not regression.is_file()
            or regression.stat().st_size > 1_048_576
        ):
            return {"passed": False, "reason": "regression_test_missing"}
        (target / regression.name).write_text(regression.read_text())
    return None


def _pytest_completed(result: dict) -> bool:
    """Require successful, untruncated pytest completion with passed tests and no errors."""
    stdout = result.get("stdout", "")
    return (
        result.get("exit_code") == 0
        and re.search(r"(?<!\d)[1-9]\d* passed\b", stdout) is not None
        and re.search(r"\b(?:failed|errors?|skipped|xfailed|xpassed)\b", stdout.lower())
        is None
        and not result.get("output_truncated", False)
        and not result.get("execution_timed_out", False)
    )


def _verify_regression(habitat, case, target) -> dict | None:
    """Require the added regression test to pass after repair and fail before it."""
    if case.id != "repair-07":
        return None
    regression_check = habitat.structured(f"python -m pytest -q {REGRESSION_TEST}", 15)
    if not _pytest_completed(regression_check):
        return {
            "passed": False,
            "reason": "regression_test_failed",
            "check": regression_check,
        }
    (target / FIXTURE_MODULE).write_text(case.files[FIXTURE_MODULE])
    fails_before = habitat.structured(f"python -m pytest -q {REGRESSION_TEST}", 15)
    if (
        fails_before.get("exit_code") != 1
        or re.search(r"[1-9]\d* failed\b", fails_before.get("stdout", "")) is None
    ):
        return {
            "passed": False,
            "reason": "regression_does_not_detect_fault",
            "check": fails_before,
        }
    return None


def verify_repair(case: Scenario, workspace: Path, image: str) -> dict:
    """Require completed assertions and tests, not merely a successful exit code."""
    with tempfile.TemporaryDirectory(prefix="venom-maintenance-check-") as temp:
        target = Path(temp)
        copy_error = _copy_proposed_files(case, workspace, target)
        if copy_error is not None:
            return copy_error
        habitat = TrialHabitat(target, image, read_only_workspace=True)
        try:
            nonce = secrets.token_hex(24)
            _put_oracle(
                habitat,
                "import sys,runpy\nsys.path.insert(0, '/workspace')\nfrom maintenance_fixture import *\n"
                + (case.oracle or "")
                + "\nrunpy.run_path('/workspace/test_visible.py')['test_contract']()\n"
                + f"print({nonce!r})\n",
            )
            observed = habitat.structured(f"python -B {ORACLE_PATH}", 15)
            if (
                observed.get("exit_code") != 0
                or nonce not in observed.get("stdout", "").splitlines()
            ):
                return {
                    "passed": False,
                    "reason": "independent_test_failed",
                    "check": observed,
                }
            visible = habitat.structured(f"python -m pytest -q {VISIBLE_TEST}", 15)
            if not _pytest_completed(visible):
                return {
                    "passed": False,
                    "reason": "visible_test_failed",
                    "check": visible,
                }
            regression_error = _verify_regression(habitat, case, target)
            if regression_error is not None:
                return regression_error
            return {
                "passed": True,
                "reason": "independent_tests_pass",
                "check": observed,
                "visible_check": visible,
            }
        finally:
            habitat.close()


def _negative_search(command: str) -> bool:
    """Recognize rg, grep or git grep searching for the absent feature identifier."""
    for tokens in _shell_commands(command):
        if not tokens:
            continue
        search = Path(tokens[0]).name in {"rg", "grep"} or tokens[:2] == ["git", "grep"]
        if search and any(
            "venom_comet_transporter_9348" in token for token in tokens[1:]
        ):
            return True
    return False


def _grade_localization(
    case: Scenario, run: dict, source_repo: Path, final: dict
) -> dict:
    """Check source locations and observed search evidence against the scenario contract."""
    if final.get("kind") == "codescout_native":
        from .codescout import grade_submission

        valid = grade_submission(source_repo, case, run)
    else:
        valid = validate_locations(source_repo, case, final)
    if case.id == "localization-10":
        valid = valid and any(
            c["name"] == "Terminal"
            and _negative_search(c["arguments"].get("command", ""))
            and c["result"].get("exit_code") == 1
            for c in run["calls"]
        )
    return {"passed": valid, "reason": "localization_evidence"}


def _grade_diagnostic(case: Scenario, run: dict, final: dict) -> dict:
    """Require observed environmental failure or a justified insufficient-data escalation."""
    evidence = case.id != "repair-08" or (
        run.get("environment_checks", {}).get("external_asset_absent") is True
        and any(
            c["name"] == "Terminal"
            and c["result"].get("exit_code") not in {0, None}
            and (
                "unavailable-resource.fixture" in str(c["result"])
                or VISIBLE_TEST in c["arguments"].get("command", "")
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


def grade(
    case: Scenario, run: dict, workspace: Path, source_repo: Path, image: str
) -> dict:
    """Dispatch independent evaluation by role without trusting the model success claim."""
    if not run["model_finished"]:
        return {"passed": False, "reason": run["status"]}
    final = run.get("final") or {}
    if case.role == "operator":
        return {"passed": grade_operator(case, run), "reason": "operator_contract"}
    if case.role == "localization":
        return _grade_localization(case, run, source_repo, final)
    if not case.oracle:
        return _grade_diagnostic(case, run, final)
    if final.get("status") != "success" and final.get("kind") != "native_bash":
        return {"passed": False, "reason": "model_did_not_claim_completion"}
    return verify_repair(case, workspace, image)
