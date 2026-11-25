"""Build a blinded 0A package from sealed, campaign-bound native generations."""

from __future__ import annotations

import os
import random
import tempfile
from pathlib import Path

from scripts.academy.omni_pl_chat_data import read_jsonl
from venom_core.services.remote_training.lifecycle import atomic_json, file_lock
from venom_core.services.remote_training.paths import operator_path
from venom_core.services.training_experiments.checkpoint_evaluation import (
    _baseline_inputs,
    read_generation,
    verify_generation_pair,
)
from venom_core.services.training_experiments.conversation_numeric import (
    fee_expectation,
    fee_omission,
    numeric_contradiction,
    numeric_expectation,
)
from venom_core.services.training_experiments.conversation_review import (
    _valid_verdict,
    _validate_panel,
    payload_sha,
    prepare_checkpoint_review,
    register_review_request,
    score,
)
from venom_core.services.training_experiments.conversation_text import (
    text_expectation,
    text_proof,
)
from venom_core.services.training_experiments.profiles import (
    digest,
    read_json,
    stable_hash,
)

_GENERATION_SEAL = "generation-seal.json"
_REVIEWER = "reviewer.json"
_PRIVATE = "private.json"


def _find_adapter(manifest: dict, identity: dict) -> str:
    expected = {
        "adapter_config.json": identity["config_sha256"],
        "adapter_model.safetensors": identity["weights_sha256"],
    }
    tags = [tag for tag, hashes in manifest["models"].items() if hashes == expected]
    if len(tags) != 1:
        raise ValueError("conversation_review_generation_adapter_mismatch")
    return tags[0]


def _verified_arm(
    folder: Path, cases: list[dict], identity: dict, data_hash: str
) -> tuple[dict, dict, dict]:
    manifest, seal = read_generation(folder)
    if (
        manifest["model_repo"] != identity["model"]
        or manifest["snapshot_manifest_sha256"] != identity["snapshot_sha256"]
        or manifest["data_sha256"] != data_hash
        or manifest.get("dialogue_protocol") != "own-history-v1"
    ):
        raise ValueError("conversation_review_generation_identity_mismatch")
    tag = _find_adapter(manifest, identity)
    verified, checked_seal = verify_generation_pair(folder, cases, manifest["models"])
    if (verified, checked_seal) != (manifest, seal):
        raise ValueError("conversation_review_generation_changed")
    return _baseline_inputs(folder, manifest, cases, variant=tag), seal, manifest


def _case_index(cases: list[dict], panel: dict) -> dict:
    index = {}
    for case in cases:
        dialogue = case.get("dialogue")
        if not isinstance(dialogue, dict):
            raise ValueError("conversation_review_dialogue_missing")
        conversation, number = dialogue.get("id"), dialogue.get("turn_index")
        if conversation not in panel or type(number) is not int:
            raise ValueError("conversation_review_panel_mapping_invalid")
        turns = sorted(panel[conversation]["turns"])
        if not 1 <= number <= len(turns):
            raise ValueError("conversation_review_panel_mapping_invalid")
        turn = turns[number - 1]
        criteria = case.get("criteria")
        if (
            case.get("review_group") != panel[conversation]["group"]
            or not isinstance(criteria, list)
            or any(not isinstance(item, dict) for item in criteria)
            or [item.get("id") for item in criteria]
            != panel[conversation]["turns"][turn]
        ):
            raise ValueError("conversation_review_panel_mapping_invalid")
        key = (conversation, turn)
        if key in index:
            raise ValueError("conversation_review_panel_mapping_invalid")
        index[key] = case["record_id"]
    expected = {(c, turn) for c, spec in panel.items() for turn in spec["turns"]}
    if set(index) != expected or len(set(index.values())) != len(index):
        raise ValueError("conversation_review_panel_mapping_invalid")
    return index


def prepare_blind_package(
    pending: object,
    panel: dict,
    dataset: Path,
    parent_generation: Path,
    candidate_generation: Path,
) -> tuple[dict, dict]:
    """Create reviewer view and private mapping using only sealed matching inputs.

    The caller must obtain pending from the trusted campaign status. The frozen
    development dataset must contain the complete 0A panel, with review_group
    and dialogue.id/turn_index. The package proves integrity and binding, while
    actual execution provenance depends on trust in the native evaluator.
    """
    if (
        not isinstance(pending, dict)
        or pending.get("conversation_review_status") != "pending"
    ):
        raise ValueError("conversation_review_pending_checkpoint_required")
    binding = pending["conversation_review_binding"]
    if binding["panel_sha256"] != payload_sha(panel):
        raise ValueError("conversation_review_panel_binding_invalid")
    _validate_panel("dev", panel)
    dataset_hash = digest(dataset)
    if dataset_hash != binding["development_identity"]["dataset_sha256"]:
        raise ValueError("conversation_review_dataset_binding_invalid")
    cases = read_jsonl(dataset)
    index = _case_index(cases, panel)
    parent, parent_seal, parent_manifest = _verified_arm(
        parent_generation, cases, binding["p13_identity"], dataset_hash
    )
    candidate, candidate_seal, candidate_manifest = _verified_arm(
        candidate_generation, cases, binding["candidate_identity"], dataset_hash
    )
    ignored = {"models", "outputs", "resumed_generations", "generation_identity_sha256"}
    if {key: value for key, value in parent_manifest.items() if key not in ignored} != {
        key: value for key, value in candidate_manifest.items() if key not in ignored
    }:
        raise ValueError("conversation_review_generation_protocol_mismatch")
    if stable_hash(parent_seal) != binding["p13_record_sha256"]:
        raise ValueError("conversation_review_parent_generation_unbound")
    result_file = candidate_generation / "result.json"
    if digest(result_file) != binding["checkpoint_result_sha256"]:
        raise ValueError("conversation_review_checkpoint_result_unbound")
    result = read_json(result_file)
    if (
        result.get("generation_sha256")
        != digest(candidate_generation / _GENERATION_SEAL)
        or result.get("run_id") != binding["run_id"]
        or result.get("checkpoint", {}).get("step") != binding["step"]
        or result.get("checkpoint", {}).get("sha256")
        != binding["candidate_identity"]["weights_sha256"]
    ):
        raise ValueError("conversation_review_checkpoint_generation_unbound")
    if (
        digest(dataset) != dataset_hash
        or read_generation(candidate_generation)[1] != candidate_seal
        or read_generation(parent_generation)[1] != parent_seal
        or digest(result_file) != binding["checkpoint_result_sha256"]
    ):
        raise ValueError("conversation_review_generation_changed")
    return _render_blind_package(
        panel,
        cases,
        index,
        parent,
        candidate,
        dataset_hash,
        pending["conversation_review_id"],
        stable_hash(binding),
    )


def _operator_criteria(case: dict) -> list[str]:
    """Read selectively required operator judgments from the bound dataset."""
    marked = case.get("operator_criteria", [])
    if not isinstance(marked, list) or any(not isinstance(key, str) for key in marked):
        raise ValueError("conversation_review_operator_criteria_invalid")
    content = {item["id"] for item in case["criteria"] if item.get("kind") == "content"}
    if len(marked) != len(set(marked)) or not set(marked) <= content:
        raise ValueError("conversation_review_operator_criteria_invalid")
    return marked


def _blind_turn(
    case: dict, criteria: list[str], answers: dict, *, allow_cutoff: bool
) -> dict:
    expected = numeric_expectation(case)
    fee = fee_expectation(case)
    text_rule = text_expectation(case)
    operator_criteria = _operator_criteria(case)
    views = {}
    for alias, answer in answers.items():
        view = _review_answer(answer, allow_cutoff=allow_cutoff)
        if proof := numeric_contradiction(view, expected):
            view["numeric_contradiction"] = proof
        if omission := fee_omission(view, fee):
            view["fee_omission"] = omission
        if proof := text_proof(view, text_rule):
            view["text_proof"] = proof
        views[alias] = view
    return {
        "criteria": criteria,
        "criterion_descriptions": {
            criterion["id"]: criterion["description"] for criterion in case["criteria"]
        },
        "answers": views,
        **({"operator_criteria": operator_criteria} if operator_criteria else {}),
    }


def _render_blind_package(
    panel: dict,
    cases: list[dict],
    index: dict,
    parent: dict,
    candidate: dict,
    dataset_hash: str,
    review_id: str,
    binding_hash: str,
    *,
    allow_cutoff: bool = False,
) -> tuple[dict, dict]:
    cases_by_id = {case["record_id"]: case for case in cases}
    rng = random.SystemRandom()
    reviewer, mapping = {}, {}
    for conversation, spec in panel.items():
        aliases = ["A", "B"]
        rng.shuffle(aliases)
        mapping[conversation] = {aliases[0]: "p13", aliases[1]: "candidate"}
        turns = {}
        for turn in sorted(spec["turns"]):
            record_id = index[conversation, turn]
            answers = {
                alias: (parent if arm == "p13" else candidate)[record_id]["answer"]
                for alias, arm in mapping[conversation].items()
            }
            turns[turn] = _blind_turn(
                cases_by_id[record_id],
                spec["turns"][turn],
                answers,
                allow_cutoff=allow_cutoff,
            )
        reviewer[conversation] = {"group": spec["group"], "turns": turns}
    package = {
        "panel_sha256": payload_sha(panel),
        "dataset_sha256": dataset_hash,
        "conversations": reviewer,
    }
    private = {
        "review_id": review_id,
        "binding_sha256": binding_hash,
        "package_sha256": stable_hash(package),
        "aliases": mapping,
    }
    private["manifest_sha256"] = stable_hash(private)
    return package, private


def _review_answer(answer: dict, *, allow_cutoff: bool) -> dict:
    finish = answer.get("finish")
    if (
        (finish != "stop" and not (allow_cutoff and finish == "length"))
        or answer.get("error") is not None
        or not isinstance(answer.get("text"), str)
        or not answer["text"].strip()
    ):
        raise ValueError("conversation_review_generation_incomplete")
    return {
        "text": answer["text"],
        "input_messages": answer["input_messages"],
        **({"finish": "length"} if finish == "length" else {}),
    }


def publish_blind_package(target: Path, package: dict, private: dict) -> Path:
    """Publish both files atomically under a new private directory."""
    target = operator_path(target)
    parent = operator_path(target.parent)
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with file_lock(parent / ".conversation-blind.lock"):
        if target.exists():
            raise ValueError("conversation_review_package_exists")
        with tempfile.TemporaryDirectory(
            prefix=".conversation-blind-", dir=parent
        ) as staging:
            bundle = Path(staging) / "bundle"
            bundle.mkdir(mode=0o700)
            atomic_json(bundle / _REVIEWER, package)
            atomic_json(bundle / _PRIVATE, private)
            atomic_json(
                bundle / "judgments-template.json", _judgments_template(package)
            )
            os.replace(bundle, target)
    return target


def _judgments_template(package: dict) -> dict:
    return {
        "package_sha256": stable_hash(package),
        "reviewer_id": "",
        "reviewer_note": "",
        "judgments": {
            conversation: {
                turn: {alias: _turn_judgment_template(row) for alias in row["answers"]}
                for turn, row in spec["turns"].items()
            }
            for conversation, spec in package["conversations"].items()
        },
    }


def _turn_judgment_template(row: dict) -> dict:
    verdict = {"criteria": dict.fromkeys(row["criteria"]), "critical": None}
    if marked := row.get("operator_criteria"):
        verdict["operator_evidence"] = {
            key: {"quote": "", "reason": ""} for key in marked
        }
    return verdict


def register_blind_review(
    root: Path, pending: dict, package_dir: Path, submitted: object
) -> dict:
    """Unblind complete judgments for exactly the package issued for this checkpoint."""
    package = read_json(package_dir / _REVIEWER)
    private = read_json(package_dir / _PRIVATE)
    _verify_blind_package(pending, package, private)
    panel, arms = _decode_judgments(package, private, submitted)
    assert isinstance(submitted, dict)
    request = prepare_checkpoint_review(pending, panel)
    request.update(
        **arms,
        reviewer_id=submitted["reviewer_id"],
        reviewer_note=submitted["reviewer_note"],
    )
    return register_review_request(
        root,
        request,
        blind_review_sha256=stable_hash(
            {
                "package": private["package_sha256"],
                "private": private,
                "submission": submitted,
            }
        ),
    )


def _verify_blind_package(pending: dict, package: dict, private: dict) -> None:
    _verify_package_seal(package, private)
    binding = pending["conversation_review_binding"]
    if (
        private["review_id"] != pending["conversation_review_id"]
        or private["binding_sha256"] != stable_hash(binding)
        or package["panel_sha256"] != binding["panel_sha256"]
        or package["dataset_sha256"]
        != binding["development_identity"]["dataset_sha256"]
    ):
        raise ValueError("conversation_review_blind_package_mismatch")


def _verify_package_seal(package: dict, private: dict) -> None:
    fields = {
        "review_id",
        "binding_sha256",
        "package_sha256",
        "aliases",
        "manifest_sha256",
    }
    if not isinstance(private, dict) or private.keys() != fields:
        raise ValueError("conversation_review_blind_manifest_invalid")
    manifest = {
        key: value for key, value in private.items() if key != "manifest_sha256"
    }
    if private["manifest_sha256"] != stable_hash(manifest) or private[
        "package_sha256"
    ] != stable_hash(package):
        raise ValueError("conversation_review_blind_package_mismatch")


def _decode_judgments(
    package: dict, private: dict, submitted: object
) -> tuple[dict, dict]:
    if (
        not isinstance(submitted, dict)
        or set(submitted)
        != {"package_sha256", "reviewer_id", "reviewer_note", "judgments"}
        or submitted["package_sha256"] != private["package_sha256"]
    ):
        raise ValueError("conversation_review_blind_submission_invalid")
    panel = {
        conversation: {
            "group": spec["group"],
            "turns": {turn: row["criteria"] for turn, row in spec["turns"].items()},
        }
        for conversation, spec in package["conversations"].items()
    }
    judgments = submitted["judgments"]
    aliases = private["aliases"]
    _require_keys(judgments, panel)
    _require_keys(aliases, panel)
    arms: dict[str, dict] = {"p13": {}, "candidate": {}}
    for conversation, spec in package["conversations"].items():
        for verdicts in arms.values():
            verdicts[conversation] = {}
        _unblind_conversation(arms, conversation, spec, judgments, aliases)
    return panel, arms


def _require_keys(value: object, expected: dict | set) -> None:
    if not isinstance(value, dict) or value.keys() != set(expected):
        raise ValueError("conversation_review_blind_coverage_invalid")


def _unblind_conversation(
    request: dict, conversation: str, spec: dict, judgments: dict, aliases: dict
) -> None:
    alias_map = aliases[conversation]
    turns = judgments[conversation]
    _require_keys(alias_map, {"A", "B"})
    if sorted(alias_map.values()) != ["candidate", "p13"]:
        raise ValueError("conversation_review_blind_alias_invalid")
    _require_keys(turns, spec["turns"])
    for turn, verdicts in turns.items():
        _require_keys(verdicts, alias_map)
        row = spec["turns"][turn]
        for alias, arm in alias_map.items():
            answer = row["answers"][alias]
            verdict = _operator_verdict(verdicts[alias], row, answer["text"])
            request[arm][conversation][turn] = _apply_review_evidence(
                verdict, row["criteria"], answer
            )


def _operator_verdict(verdict: dict, row: dict, answer: str) -> dict:
    marked = row.get("operator_criteria")
    if not marked:
        return verdict
    evidence = verdict.get("operator_evidence") if isinstance(verdict, dict) else None
    if not isinstance(evidence, dict) or evidence.keys() != set(marked):
        raise ValueError("conversation_review_operator_evidence_required")
    if any(not _valid_operator_evidence(item, answer) for item in evidence.values()):
        raise ValueError("conversation_review_operator_evidence_invalid")
    return {key: value for key, value in verdict.items() if key != "operator_evidence"}


def _valid_operator_evidence(item: object, answer: str) -> bool:
    if not isinstance(item, dict) or item.keys() != {"quote", "reason"}:
        return False
    quote, reason = item["quote"], item["reason"]
    return (
        isinstance(quote, str)
        and bool(quote.strip())
        and quote in answer
        and isinstance(reason, str)
        and 1 <= len(reason.strip()) <= 600
    )


def _apply_review_evidence(verdict: dict, criteria: list[str], answer: dict) -> dict:
    failed = {
        answer[key]["criterion"]: False
        for key in ("numeric_contradiction", "fee_omission", "text_proof")
        if key in answer
    }
    if not failed or not _valid_verdict(verdict, criteria):
        return verdict
    return {
        "critical": (
            verdict["critical"]
            or "numeric_contradiction" in answer
            or answer.get("text_proof", {}).get("critical", False)
        ),
        "criteria": {**verdict["criteria"], **failed},
    }


def _diagnostic_manifest(run: Path) -> dict:
    manifest = read_json(run / "generation-acceptance.json")
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("status") != "complete"
    ):
        raise ValueError("conversation_review_diagnostic_generation_incomplete")
    return manifest


def _diagnostic_folder(run: Path, entry: dict) -> Path:
    step = entry["step"]
    if type(step) is not int or not 1 <= step <= 10000:
        raise ValueError("conversation_review_diagnostic_step_invalid")
    relative = f"checkpoint-evaluations/{step}"
    if entry["path"] != relative:
        raise ValueError("conversation_review_diagnostic_path_invalid")
    return run / relative


def _diagnostic_arm(
    run: Path, entry: dict, cases: list[dict], dataset_hash: str
) -> dict:
    folder = _diagnostic_folder(run, entry)
    seal_path = folder / _GENERATION_SEAL
    expected = entry["generation_seal_sha256"]
    if digest(seal_path) != expected:
        raise ValueError("conversation_review_diagnostic_seal_mismatch")
    answers, _seal, _manifest = _verified_arm(
        folder, cases, entry["identity"], dataset_hash
    )
    if digest(seal_path) != expected:
        raise ValueError("conversation_review_diagnostic_seal_mismatch")
    return answers


def prepare_diagnostic_review(
    run: Path, panel: dict, dataset: Path
) -> tuple[dict, dict]:
    """Prepare an acceptance package for sealed inference, outside a campaign."""
    manifest = _diagnostic_manifest(run)
    size, _, _, _, turns = _validate_panel("dev", panel)
    dataset_hash = digest(dataset)
    expected = {
        "panel_sha256": payload_sha(panel),
        "dataset_sha256": dataset_hash,
        "conversations": size,
        "turns": turns,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("conversation_review_diagnostic_inputs_mismatch")
    cases = read_jsonl(dataset)
    index = _case_index(cases, panel)
    parent = _diagnostic_arm(run, manifest["parent"], cases, dataset_hash)
    candidate = _diagnostic_arm(run, manifest["candidate"], cases, dataset_hash)
    if digest(dataset) != dataset_hash or _diagnostic_manifest(run) != manifest:
        raise ValueError("conversation_review_diagnostic_inputs_mismatch")
    run_hash = stable_hash(manifest)
    return _render_blind_package(
        panel,
        cases,
        index,
        parent,
        candidate,
        dataset_hash,
        f"diagnostic-{run_hash[:20]}",
        run_hash,
        allow_cutoff=True,
    )


def diagnostic_cutoff_ceiling(run: Path, panel: dict, dataset: Path) -> dict:
    """Determine whether cutoffs alone rule out passing the sealed DEV panel."""
    package, private = prepare_diagnostic_review(run, panel, dataset)
    size, group_size, threshold, group_threshold, turns = _validate_panel("dev", panel)
    cutoff_turns = {"p13": 0, "candidate": 0}
    cutoff_dialogues: dict[str, dict[str, set[str]]] = {
        arm: {group: set() for group in "SKWR"} for arm in cutoff_turns
    }
    for conversation, _turn, alias in _diagnostic_cutoffs(package):
        arm = private["aliases"][conversation][alias]
        group = panel[conversation]["group"]
        cutoff_turns[arm] += 1
        cutoff_dialogues[arm][group].add(conversation)

    arms: dict[str, dict] = {}
    for arm, groups in cutoff_dialogues.items():
        by_group = {group: group_size - len(ids) for group, ids in groups.items()}
        arms[arm] = {
            "cutoff_turns": cutoff_turns[arm],
            "cutoff_dialogue_ids": {
                group: sorted(ids) for group, ids in groups.items()
            },
            "maximum_full_conversations_by_group": by_group,
            "maximum_full_conversations": sum(by_group.values()),
        }
    candidate = arms["candidate"]
    failed_groups = [
        group
        for group, ceiling in candidate["maximum_full_conversations_by_group"].items()
        if ceiling < group_threshold
    ]
    fails_total = candidate["maximum_full_conversations"] < threshold
    return {
        "status": "STOP" if fails_total or failed_groups else "REVIEW",
        "scope": "diagnostic_only",
        "decision_basis": "upper_bound_from_verified_cutoffs",
        "generation_acceptance_sha256": private["binding_sha256"],
        "dataset_sha256": package["dataset_sha256"],
        "panel_sha256": package["panel_sha256"],
        "conversations": size,
        "turns_per_arm": turns,
        "thresholds": {"total": threshold, "per_group": group_threshold},
        "fails_total": fails_total,
        "failed_groups": failed_groups,
        "critical_errors_assessed": False,
        "parent_retention_assessed": False,
        "arms": arms,
    }


def score_diagnostic_review(run: Path, package_dir: Path, submitted: object) -> dict:
    """Score a completed blind diagnostic without publishing a campaign receipt."""
    manifest = _diagnostic_manifest(run)
    package = read_json(package_dir / _REVIEWER)
    private = read_json(package_dir / _PRIVATE)
    _verify_package_seal(package, private)
    run_hash = stable_hash(manifest)
    if (
        private["review_id"] != f"diagnostic-{run_hash[:20]}"
        or private["binding_sha256"] != run_hash
        or any(
            package[key] != manifest[key] for key in ("panel_sha256", "dataset_sha256")
        )
    ):
        raise ValueError("conversation_review_diagnostic_package_mismatch")
    for name in ("parent", "candidate"):
        entry = manifest[name]
        seal = _diagnostic_folder(run, entry) / _GENERATION_SEAL
        if digest(seal) != entry["generation_seal_sha256"]:
            raise ValueError("conversation_review_diagnostic_seal_mismatch")
        read_generation(seal.parent)
    panel, arms = _decode_judgments(package, private, submitted)
    assert isinstance(submitted, dict)
    if any(
        not isinstance(submitted[key], str) or not submitted[key].strip()
        for key in ("reviewer_id", "reviewer_note")
    ):
        raise ValueError("conversation_review_diagnostic_reviewer_required")
    result = score("dev", panel, arms["p13"], arms["candidate"])
    cutoffs = _diagnostic_cutoffs(package)
    _require_failed_cutoffs(submitted["judgments"], cutoffs)
    return {
        "cutoff_answers": len(cutoffs),
        "scope": "diagnostic_only",
        "generation_acceptance_sha256": run_hash,
        "package_sha256": private["package_sha256"],
        "judgments_sha256": stable_hash(submitted),
        "reviewer_id": submitted["reviewer_id"].strip(),
        "reviewer_note": submitted["reviewer_note"].strip(),
        **result,
    }


def _diagnostic_cutoffs(package: dict) -> list[tuple[str, str, str]]:
    return [
        (conversation, turn, alias)
        for conversation, spec in package["conversations"].items()
        for turn, row in spec["turns"].items()
        for alias, answer in row["answers"].items()
        if answer.get("finish") == "length"
    ]


def _require_failed_cutoffs(
    judgments: dict, cutoffs: list[tuple[str, str, str]]
) -> None:
    for conversation, turn, alias in cutoffs:
        verdict = judgments[conversation][turn][alias]
        if not verdict["critical"] and all(verdict["criteria"].values()):
            raise ValueError("conversation_review_cutoff_cannot_pass")
