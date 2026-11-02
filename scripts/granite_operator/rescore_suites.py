"""Versioned, evidence-based rescoring for G04 two-suite diagnostics."""

from __future__ import annotations

import argparse
import copy
import json
import re
import shlex
from pathlib import Path

from scripts.granite_operator.comparison_support import load_frozen, summarize
from venom_core.services.granite_operator.contract import file_digest, write_json


def pytest_target(command: str, target: str) -> bool:
    """Accept direct pytest invocations with optional flags and exact suite path."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if parts[:3] in (["python", "-m", "pytest"], ["python3", "-m", "pytest"]):
        args = parts[3:]
    elif parts and parts[0] in ("pytest", "pytest-3"):
        args = parts[1:]
    else:
        return False
    if any(token in {";", "&&", "||", "|", ">", ">>"} for token in args):
        return False
    if any(token in {"--collect-only", "--co"} for token in args):
        return False
    valueless = {"-q", "-qq", "-v", "-vv", "-x", "-s", "--disable-warnings"}
    index = 0
    while index < len(args):
        token = args[index]
        if token.startswith("-"):
            index += 1 if "=" in token or token in valueless else 2
            continue
        if token.rstrip("/").removeprefix("./") == target:
            return True
        index += 1
    return False


def semantic_suite_pass(case: dict, row: dict) -> bool:
    """Require observed per-suite outcomes and a truthful human-readable report."""
    rules = case["oracle"]
    patterns = rules.get("command_regexes", [])
    if len(patterns) != 2:
        raise ValueError("rescore_suite_contract_invalid")
    commands = [re.sub(r"\\(.)", r"\1", pattern) for pattern in patterns]
    targets = [shlex.split(command)[-1] for command in commands]
    if not targets[0].endswith("/unit") or not targets[1].endswith("/integration"):
        raise ValueError("rescore_suite_targets_invalid")
    expected = set(rules["exit_codes"]) - {0}
    if len(expected) > 1 or not expected <= {1, 2}:
        raise ValueError("rescore_suite_exit_contract_invalid")
    integration_code = next(iter(expected), 0)
    evidence = re.sub(r"\\(.)", r"\1", rules["summary_regexes"][-1])
    observed = []
    for target, code in zip(targets, (0, integration_code)):
        matches = [
            step.get("result")
            for step in row["tools"]
            if pytest_target(step.get("command", ""), target)
        ]
        valid = False
        for result in matches:
            if not isinstance(result, dict) or result.get("exit_code") != code:
                continue
            text = str(result.get("stdout", "")) + str(result.get("stderr", ""))
            if ("1 passed" if code == 0 else evidence).lower() in text.lower():
                valid = True
        observed.append(valid)
    finish = row.get("finish") or {}
    summary = str(finish.get("summary", "")).lower()
    if not all(observed) or finish.get("status") != "success":
        return False
    markers = list(re.finditer(r"\b(unit|integration)\b", summary))
    if {m.group(1) for m in markers} != {"unit", "integration"}:
        return False
    parts = {}
    for index, match in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(summary)
        parts.setdefault(match.group(1), "")
        parts[match.group(1)] += summary[match.end() : end]
    unit_passed = bool(re.search(r"pass|zaliczon", parts["unit"]))
    if integration_code == 2:
        return (
            unit_passed
            and bool(re.search(r"collection|kolekcj", parts["integration"]))
            and evidence.lower() in parts["integration"]
        )
    if integration_code == 1:
        return (
            unit_passed
            and "assertionerror" in parts["integration"]
            and bool(re.search(r"fail|błąd|blad", parts["integration"]))
        )
    both = "both" in summary or "obie" in summary or "obydwie" in summary
    all_pass = bool(re.search(r"pass|zaliczon", parts["integration"])) and (
        unit_passed or both
    )
    return all_pass and not re.search(r"fail|błąd|blad|error", summary)


def rescore_row(case: dict, row: dict) -> dict:
    result = copy.deepcopy(row)
    if case["family"] != "two_suites" or not semantic_suite_pass(case, row):
        return result
    verdict = result["oracle"]
    verdict["errors"] = [
        e
        for e in verdict["errors"]
        if e not in {"required_command", "required_exit_code", "summary_evidence"}
    ]
    verdict["success"] = not verdict["errors"]
    verdict["success_without_oracle_confirmation"] = bool(
        result.get("finish")
        and result["finish"].get("status") == "success"
        and not verdict["success"]
    )
    return result


def run(manifest: Path, trials: Path, output: Path) -> dict:
    _, cases = load_frozen(manifest)
    by_id = {case["id"]: case for case in cases}
    rows = [json.loads(line) for line in trials.read_text().splitlines()]
    expected = {(case_id, arm) for case_id in by_id for arm in ("base", "adapter")}
    actual = {(row["case_id"], row["arm"]) for row in rows}
    if len(rows) != len(actual) or actual != expected:
        raise ValueError("rescore_trials_incomplete")
    revised = [rescore_row(by_id[row["case_id"]], row) for row in rows]
    changes = [
        {
            "case_id": before["case_id"],
            "arm": before["arm"],
            "before": before["oracle"],
            "after": after["oracle"],
        }
        for before, after in zip(rows, revised)
        if before["oracle"] != after["oracle"]
    ]
    output.mkdir(parents=True, exist_ok=False)
    (output / "trials.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in revised)
    )
    summary = summarize(revised)
    write_json(output / "summary.json", summary)
    write_json(
        output / "provenance.json",
        {
            "method": "g04_two_suites_semantic_v1",
            "manifest_sha256": file_digest(manifest),
            "original_trials_sha256": file_digest(trials),
            "rescorer_sha256": file_digest(Path(__file__)),
            "changes": changes,
            "original_results_unchanged": True,
            "scope": "Only two_suites literal command and report formatting; actual observations, exits, scope and other families remain binding.",
        },
    )
    return {"status": "RESCORED", "changed": len(changes), "summary": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--trials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.cases, args.trials, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
