"""Aggregate explicit rubric judgments without matching answer wording.

A judge supplies criterion decisions before model identities are revealed.
This module validates complete coverage; it does not claim to judge semantics.
"""

from collections import defaultdict


def aggregate(cases: list[dict], answers: list[dict], judgments: list[dict]) -> dict:
    """Fail closed on missing grades and keep content separate from format."""
    case_map = {case["record_id"]: case for case in cases}
    if len(case_map) != len(cases) or not cases:
        raise ValueError("cases must have unique IDs")
    answer_map = {}
    labels = None
    for item in answers:
        cid = item["case"]["record_id"]
        if cid not in case_map or cid in answer_map:
            raise ValueError("unknown or duplicate answer case")
        current = set(item["answers"])
        if not current or (labels is not None and current != labels):
            raise ValueError("each case must contain the same anonymous labels")
        labels = current
        answer_map[cid] = item["answers"]
    if answer_map.keys() != case_map.keys():
        raise ValueError("missing answer cases")

    grade_map = {}
    for grade in judgments:
        key = (grade["record_id"], grade["label"])
        if key in grade_map:
            raise ValueError("duplicate judgment")
        grade_map[key] = grade
    required = {(cid, label) for cid in case_map for label in labels}
    if grade_map.keys() != required:
        raise ValueError("missing or unexpected judgments")

    scores = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    verdicts = defaultdict(dict)
    for cid, case in case_map.items():
        criteria = case["criteria"]
        expected = {c["id"]: c["kind"] for c in criteria}
        if (
            not expected
            or len(expected) != len(criteria)
            or set(expected.values()) - {"content", "format"}
            or "content" not in expected.values()
        ):
            raise ValueError("invalid criteria")
        for label, answer in answer_map[cid].items():
            grade = grade_map[cid, label]
            decisions = grade["criteria"]
            if decisions.keys() != expected.keys() or any(
                type(value) is not bool for value in decisions.values()
            ):
                raise ValueError("criterion decisions must be complete booleans")
            if any(
                type(grade[key]) is not bool
                for key in ("polish_ok", "natural_ok", "critical_error")
            ):
                raise ValueError("quality decisions must be booleans")
            if not isinstance(grade.get("reason"), str) or not grade["reason"].strip():
                raise ValueError("judgment needs an explanation")
            valid = answer.get("error") is None and answer.get("finish") == "stop"
            content = all(
                decisions[k] for k, kind in expected.items() if kind == "content"
            )
            form = all(decisions[k] for k, kind in expected.items() if kind == "format")
            semantic = valid and content and not grade["critical_error"]
            usable = semantic and grade["polish_ok"] and grade["natural_ok"]
            passed = usable and form
            verdicts[label][cid] = {
                "semantic": int(semantic),
                "usable": int(usable),
                "passed": int(passed),
            }
            for task in ("total", case["task"]):
                bucket = scores[label][task]
                for key, value in {
                    "n": 1,
                    "semantic": semantic,
                    "usable": usable,
                    "passed": passed,
                    "format": form,
                    "polish": grade["polish_ok"],
                    "natural": grade["natural_ok"],
                    "critical": grade["critical_error"],
                    "runtime_or_length_failure": not valid,
                }.items():
                    bucket[key] += int(value)
    return {
        "summaries": {
            label: {task: dict(v) for task, v in tasks.items()}
            for label, tasks in scores.items()
        },
        "verdicts": dict(verdicts),
    }
