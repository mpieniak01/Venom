"""Immutable CPU release boundaries; actual training remains a separate job."""

import copy
import json
from pathlib import Path

import pytest

from venom_core.services.gemma4_operator.data_release import build_release
from venom_core.services.gemma4_operator.material import digest
from venom_core.services.gemma4_operator.profile import GemmaProfile

PROFILE = Path(__file__).resolve().parents[1] / "config/gemma4_operator_profile.json"


def row(name, split):
    return {
        "record_id": name,
        "problem_group": name,
        "language": "pl",
        "split": split,
        "training_allowed": split == "train",
        "messages": [
            {"role": "user", "content": name},
            {"role": "assistant", "content": "Checked"},
        ],
        "tools": [],
    }


def splits():
    return {
        "train": [row("training incident", "train")],
        "validation": [row("validation configuration", "validation")],
        "holdout": [row("reserved private scenario", "holdout")],
    }


def test_release_is_bound_deterministic_and_source_preserving():
    source = splits()
    before = copy.deepcopy(source)
    profile = GemmaProfile.load(PROFILE)
    first = build_release(source, profile)
    second = build_release(source, profile)
    assert first == second
    assert source == before
    fingerprint = first.pop("release_sha256")
    assert digest(first) == fingerprint
    assert first["model_profile"] == profile.identity()
    assert first["training_ready"] is False
    assert first["training_started"] is False


def test_holdout_bytes_are_not_in_the_training_release():
    result = build_release(splits(), GemmaProfile.load(PROFILE))
    payload = result["training_payload"]
    assert set(payload["records"]) == {"train", "validation"}
    assert "reserved private scenario" not in json.dumps(result)
    reserve = result["evaluation_reserve"]
    assert reserve["present"] is True
    assert reserve["records"] == 1
    assert reserve["included_in_training_payload"] is False
    assert result["adapter_activation_authorized"] is False


def test_source_change_changes_the_release_fingerprint():
    source = splits()
    profile = GemmaProfile.load(PROFILE)
    first = build_release(source, profile)
    source["train"][0]["messages"][-1]["content"] = "Rechecked"
    second = build_release(source, profile)
    assert first["release_sha256"] != second["release_sha256"]


@pytest.mark.parametrize("missing", ["train", "validation"])
def test_required_split_cannot_disappear(missing):
    source = splits()
    source.pop(missing)
    profile = GemmaProfile.load(PROFILE)
    with pytest.raises(ValueError, match="train_and_validation"):
        build_release(source, profile)


def test_reserve_remains_optional_and_explicit():
    source = splits()
    source.pop("holdout")
    result = build_release(source, GemmaProfile.load(PROFILE))
    assert result["evaluation_reserve"]["present"] is False
    assert result["evaluation_reserve"]["records_sha256"] is None


def test_leaking_groups_are_rejected_before_release():
    source = splits()
    source["holdout"][0]["problem_group"] = source["train"][0]["problem_group"]
    profile = GemmaProfile.load(PROFILE)
    with pytest.raises(ValueError, match="group"):
        build_release(source, profile)
