"""Verify v4 accuracy and repeated-request evidence; no inference during verification."""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from venom_core.config import SETTINGS

from .profiles import digest, stable_hash

if TYPE_CHECKING:
    from .local_semantic_judge import QualificationV4

ERROR = "experiment_judge_v4_audit_invalid"
FILES = frozenset(
    {
        "development/panel.json",
        "development/gold.json",
        "holdout/panel.json",
        "holdout/gold.json",
        "legacy/qualification-panel.json",
        "legacy/qualification-gold.json",
        "legacy/qualification-manifest.json",
        "legacy/judge-protocol.json",
        "legacy/judge-result.json",
        "legacy/judge-qualification-receipt.json",
        "options.json",
        "preregister.json",
        "prompt-proposal.txt",
        "prompt-change.diff",
        "execution-order.json",
    }
)
DECISION_FIELDS = ("atoms", "unsupported", "injection", "polish_ok", "natural_ok")


def require(condition: bool) -> None:
    if not condition:
        raise ValueError(ERROR)


def implementation_hashes() -> dict[str, str]:
    from . import local_semantic_judge as judge

    return {
        "judge": digest(Path(judge.__file__)),
        "v4_verifier": digest(Path(__file__)),
        "audit_runner": digest(Path(__file__).with_name("semantic_judge_audit.py")),
        "provenance": digest(Path(__file__).with_name("semantic_judge_provenance.py")),
    }


def control_files(root: Path, expected: str) -> dict:
    from . import local_semantic_judge as judge

    controls = root / "controls"
    manifest = judge._bound_json(controls, "frozen-manifest.json", expected)
    require(set(manifest["files"]) == FILES)
    require(manifest["status"] == "frozen_before_any_inference")
    for name, checksum in manifest["files"].items():
        require(isinstance(checksum, str) and digest(controls / name) == checksum)
    options = judge._bound_json(
        controls, "options.json", manifest["files"]["options.json"]
    )
    require(options == judge.OPTIONS)
    require(
        (controls / "prompt-proposal.txt").read_text(encoding="utf8")
        == judge.PROMPT_V4 + "\n"
    )
    return manifest


def _control(root: Path, manifest: dict, name: str) -> dict:
    from . import local_semantic_judge as judge

    return judge._bound_json(root / "controls", name, manifest["files"][name])


def execution_order(root: Path, manifest: dict) -> list[dict]:
    order = _control(root, manifest, "execution-order.json")
    first, held = (
        order["phase1_legacy_and_development"],
        order["phase2_holdout_stability"],
    )
    require(len(first) == 108 and len(held) == 72)
    require(Counter(row["split"] for row in first) == {"legacy": 60, "development": 48})
    require(all(row["split"] == "holdout" for row in held))
    require(all(type(row["repeat"]) is int and row["repeat"] == 1 for row in first))
    require(Counter(row["repeat"] for row in held) == {1: 24, 2: 24, 3: 24})
    require(all(type(row["repeat"]) is int for row in held))
    require(len({(row["split"], row["answer_id"]) for row in first}) == 108)
    require(len({(row["answer_id"], row["repeat"]) for row in held}) == 72)
    for repeat in (1, 2, 3):
        require(
            all(
                row["repeat"] == repeat for row in held[(repeat - 1) * 24 : repeat * 24]
            )
        )
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(held):
        groups[row["answer_id"]].append(index)
    require(len(groups) == 24 and all(len(value) == 3 for value in groups.values()))
    require(
        all(b - a > 1 for value in groups.values() for a, b in zip(value, value[1:]))
    )
    return first + held


def jobs_for(root: Path, manifest: dict, split: str) -> tuple[dict, dict]:
    from . import local_semantic_judge as judge

    require(split in {"legacy", "development", "holdout"})
    suffix = "qualification-" if split == "legacy" else ""
    panel = _control(root, manifest, f"{split}/{suffix}panel.json")
    gold = _control(root, manifest, f"{split}/{suffix}gold.json")
    expected_families, expected_answers = {
        "legacy": (12, 60),
        "development": (12, 48),
        "holdout": (6, 24),
    }[split]
    require(len(panel["cases"]) == expected_families)
    require(len({case["id"] for case in panel["cases"]}) == expected_families)
    jobs = {}
    for case in panel["cases"]:
        criteria = case["criteria"]
        atom_ids = {criterion["id"] for criterion in criteria}
        require(bool(atom_ids) and len(atom_ids) == len(criteria))
        for answer in case["answers"]:
            ident = answer["id"]
            require(isinstance(ident, str) and ident not in jobs)
            require(isinstance(answer["text"], str) and bool(answer["text"]))
            jobs[ident] = case, answer
    require(len(jobs) == expected_answers)
    if split == "legacy":
        positives, negatives = gold["accepted"], gold["rejected"]
        require(isinstance(positives, list) and isinstance(negatives, dict))
        require(len(positives) == len(set(positives)) == 24)
        require(len(negatives) == len(set(negatives)) == 36)
        require(not set(positives) & set(negatives))
        require(set(positives) | set(negatives) == jobs.keys())
    else:
        require(gold["answers"].keys() == jobs.keys())
        positive_families: Counter = Counter()
        for ident, item in gold["answers"].items():
            case, _ = jobs[ident]
            require(item["case_id"] == case["id"])
            require(set(item["decision"]) == set(DECISION_FIELDS))
            decision = judge._Decision.model_validate(
                {**item["decision"], "reason": "frozen gold"}
            )
            require(
                decision.atoms.keys()
                == {criterion["id"] for criterion in case["criteria"]}
            )
            require(
                "unclear" not in decision.atoms.values()
                and decision.unsupported != "unclear"
            )
            require(item["expected"] in {"positive", "negative"})
            positive = item["expected"] == "positive"
            require(judge._supported(decision) == positive)
            if positive:
                positive_families[case["id"]] += 1
        require(
            positive_families
            == dict.fromkeys((case["id"] for case in panel["cases"]), 2)
        )
        require(all(len(case["answers"]) == 4 for case in panel["cases"]))
    return jobs, gold


def request_for(model: str, case: dict, answer: dict) -> dict:
    """Identical material serialization for the runner and offline verifier."""
    from . import local_semantic_judge as judge

    material = {
        "messages": case["messages"],
        "criteria": [
            {"description": c["description"], "id": c["id"]} for c in case["criteria"]
        ],
        "evidence": case.get("evidence", []),
        "candidate": answer["text"],
    }
    return judge._request(
        model, material, [c["id"] for c in case["criteria"]], judge=judge.JUDGE_V4
    )


def _legacy_decisions(jobs: dict, gold: dict, decisions: dict) -> None:
    from . import local_semantic_judge as judge

    positives, negatives = set(gold["accepted"]), set(gold["rejected"])
    require(
        {key for key, value in decisions.items() if judge._supported(value)}
        == positives
    )
    styles = judge._style_checks(gold, positives, negatives)
    require(len(styles) == 24)
    for ident, expected in styles.items():
        require((decisions[ident].polish_ok, decisions[ident].natural_ok) == expected)
    semantics = gold["expected_semantics"]
    challenges = set(gold["challenge_cases"])
    require(len(semantics) == 6 and len(challenges) == 3)
    challenge_answers = {
        ident for ident, (case, _) in jobs.items() if case["id"] in challenges
    }
    require(
        len(challenge_answers & positives) == 6
        and len(challenge_answers & negatives) == 12
    )
    require(not semantics.keys() - (challenge_answers & negatives))
    require(
        all(
            judge._semantic_check(decisions[ident], expected)
            for ident, expected in semantics.items()
        )
    )


def verify_rows(
    root: Path,
    manifest: dict,
    pin: QualificationV4,
    rows: list[dict],
    *,
    phase1: bool = False,
) -> dict:
    from . import local_semantic_judge as judge
    from . import semantic_judge_provenance as provenance

    protocol = judge._bound_json(root, "judge-protocol.json", pin.protocol_sha256)
    seen: dict[str, set[str]] = {
        key: set() for key in ("call_id", "server_time", "raw_response")
    }
    previous_end = 0
    order = execution_order(root, manifest)[: 108 if phase1 else 180]
    require(len(rows) == len(order))
    splits = (
        ("legacy", "development") if phase1 else ("legacy", "development", "holdout")
    )
    inputs = {split: jobs_for(root, manifest, split) for split in splits}
    actual: dict[str, dict] = {split: {} for split in splits}
    repeated: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for index, (entry, row) in enumerate(zip(order, rows, strict=True), 1):
        require(type(row["index"]) is int and row["index"] == index)
        require({key: row[key] for key in entry} == entry)
        split, ident = entry["split"], entry["answer_id"]
        jobs, gold = inputs[split]
        require(ident in jobs)
        case, answer = jobs[ident]
        require(case["id"] == entry["case_id"])
        call = judge._bound_json(
            root / "judge-calls", f"{index:03d}.json", row["call_sha256"]
        )
        previous_end = provenance.verify_call(
            call, protocol, pin.protocol_sha256, seen, previous_end
        )
        expected_request = request_for(pin.model, case, answer)
        request_sha = stable_hash(expected_request)
        require(
            call["request"] == expected_request
            and call["request_sha256"] == request_sha
        )
        require(row["request_sha256"] == request_sha)
        decision = judge._decode(
            call["response"], [c["id"] for c in case["criteria"]], pin.model
        )
        require(decision is not None)
        assert decision is not None
        require(
            decision.unsupported != "unclear"
            and "unclear" not in decision.atoms.values()
        )
        require(decision.model_dump() == row["decision"])
        actual[split][ident] = decision
        if split != "legacy":
            vector = {key: getattr(decision, key) for key in DECISION_FIELDS}
            require(vector == gold["answers"][ident]["decision"])
            if split == "holdout":
                repeated[ident].append((request_sha, vector))
    for split, (jobs, _) in inputs.items():
        require(actual[split].keys() == jobs.keys())
    _legacy_decisions(inputs["legacy"][0], inputs["legacy"][1], actual["legacy"])
    if not phase1:
        require(len(repeated) == 24)
        require(
            all(
                len(values) == 3 and all(value == values[0] for value in values)
                for values in repeated.values()
            )
        )
    return {
        "legacy_correct": 60,
        "development_correct": 48,
        "holdout_correct": 0 if phase1 else 72,
        "stable_groups": 0 if phase1 else 24,
    }


def verify_audit(pin: QualificationV4) -> None:
    from . import local_semantic_judge as judge

    try:
        location = os.environ.get(
            "VENOM_ACADEMY_JUDGE_V4_AUDIT_ROOT",
            SETTINGS.VENOM_ACADEMY_JUDGE_V4_AUDIT_ROOT,
        ).strip()
        require(
            bool(location) and Path(location).is_absolute() and Path(location).is_dir()
        )
        root = Path(location)
        protocol = judge._bound_json(root, "judge-protocol.json", pin.protocol_sha256)
        result = judge._bound_json(root, "judge-result.json", pin.result_sha256)
        manifest = control_files(root, pin.accuracy_manifest_sha256)
        require(manifest["files"]["legacy/qualification-gold.json"] == pin.gold_sha256)
        require(protocol["judge"] == judge.JUDGE_V4 and protocol["schema_version"] == 4)
        require(
            protocol["system"] == judge.PROMPT_V4
            and protocol["options"] == judge.OPTIONS
        )
        require(
            protocol["model"] == pin.model
            and protocol["model_sha256"] == pin.model_sha256
        )
        require(protocol["ollama"] == {"version": pin.ollama_version})
        require(protocol["accuracy_manifest_sha256"] == pin.accuracy_manifest_sha256)
        require(protocol["implementation_sha256"] == implementation_hashes())
        require(
            result["protocol_sha256"] == pin.protocol_sha256
            and result["status"] == "complete"
        )
        from . import semantic_judge_provenance as provenance

        provenance.verify_legacy(root, manifest, pin)
        metrics = verify_rows(root, manifest, pin, result["rows"])
        require(result["metrics"] == metrics)
        provenance.verify_session(root, protocol, pin, result)
        control_files(root, pin.accuracy_manifest_sha256)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError(ERROR) from exc
