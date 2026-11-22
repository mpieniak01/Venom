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
from venom_core.services.training_experiments.conversation_review import (
    _validate_panel,
    payload_sha,
)
from venom_core.services.training_experiments.profiles import (
    digest,
    read_json,
    stable_hash,
)


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
    pending: dict,
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
    if pending.get("conversation_review_status") != "pending":
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
        != digest(candidate_generation / "generation-seal.json")
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
    rng = random.SystemRandom()
    reviewer, mapping = {}, {}
    for conversation, spec in panel.items():
        aliases = ["A", "B"]
        rng.shuffle(aliases)
        mapping[conversation] = {aliases[0]: "p13", aliases[1]: "candidate"}
        turns = {}
        for turn in sorted(spec["turns"]):
            record_id = index[conversation, turn]
            views = {}
            for alias, arm in mapping[conversation].items():
                answer = (parent if arm == "p13" else candidate)[record_id]["answer"]
                if (
                    answer.get("finish") != "stop"
                    or answer.get("error") is not None
                    or not isinstance(answer.get("text"), str)
                    or not answer["text"].strip()
                ):
                    raise ValueError("conversation_review_generation_incomplete")
                views[alias] = answer
            turns[turn] = {"criteria": spec["turns"][turn], "answers": views}
        reviewer[conversation] = {"group": spec["group"], "turns": turns}
    package = {
        "panel_sha256": payload_sha(panel),
        "dataset_sha256": dataset_hash,
        "conversations": reviewer,
    }
    private = {
        "review_id": pending["conversation_review_id"],
        "binding_sha256": stable_hash(binding),
        "package_sha256": stable_hash(package),
        "aliases": mapping,
    }
    return package, private


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
            atomic_json(bundle / "reviewer.json", package)
            atomic_json(bundle / "private.json", private)
            os.replace(bundle, target)
    return target
