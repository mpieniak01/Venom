"""Immutable operator receipts for full-conversation Academy qualification."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

from venom_core.services.remote_training.lifecycle import atomic_json, file_lock
from venom_core.services.remote_training.paths import operator_path

from .profiles import stable_hash

_GROUPS = frozenset("SKWR")
_LIMITS = {"dev": (96, 24, 72, 16), "final": (48, 12, 36, 8)}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_RECEIPT_FILE = "receipt.json"
_JUDGMENTS_FILE = "judgments.json"


class MissingConversationReview(FileNotFoundError):
    """A checkpoint awaits operator review; carries the exact binding to register."""

    def __init__(self, review_id: str, binding: dict):
        super().__init__("conversation_review_receipt_missing")
        self.review_id = review_id
        self.binding = binding


def score(mode: str, panel: dict, p13: dict, candidate: dict) -> dict:
    """Score complete paired conversations using the offline 0A thresholds."""
    size, _, total_minimum, group_minimum, turns_total = _validate_panel(mode, panel)
    parent_passed, _ = _arm(panel, p13, "p13")
    passed, critical = _arm(panel, candidate, "candidate")
    by_group = Counter(panel[key]["group"] for key in passed)
    lost = sorted(parent_passed - passed)
    failures = _score_failures(
        passed, by_group, critical, lost, total_minimum, group_minimum
    )
    return {
        "mode": mode,
        "status": "PASS" if not failures else "STOP",
        "conversations": size,
        "turns": turns_total,
        "passed": len(passed),
        "minimum": total_minimum,
        "groups": {group: by_group[group] for group in sorted(_GROUPS)},
        "group_minimum": group_minimum,
        "p13_passed": len(parent_passed),
        "retained": len(parent_passed & passed),
        "lost": lost,
        "critical": critical,
        "failures": failures,
    }


def _validate_panel(mode: str, panel: dict) -> tuple[int, int, int, int, int]:
    if mode not in _LIMITS:
        raise ValueError("conversation_review_mode_invalid")
    size, group_size, total_minimum, group_minimum = _LIMITS[mode]
    if not isinstance(panel, dict) or len(panel) != size:
        raise ValueError(f"conversation_review_panel_requires_{size}")
    groups: Counter[str] = Counter()
    turns_total = 0
    for conversation, spec in panel.items():
        group, turn_count = _validate_conversation_spec(conversation, spec)
        groups[group] += 1
        turns_total += turn_count
    if groups != Counter(dict.fromkeys(_GROUPS, group_size)):
        raise ValueError("conversation_review_group_counts_invalid")
    return size, group_size, total_minimum, group_minimum, turns_total


def _validate_conversation_spec(conversation: object, spec: object) -> tuple[str, int]:
    if (
        not isinstance(conversation, str)
        or not conversation.strip()
        or not isinstance(spec, dict)
        or set(spec) != {"group", "turns"}
    ):
        raise ValueError("conversation_review_panel_invalid")
    group, turns = spec["group"], spec["turns"]
    if not isinstance(group, str) or group not in _GROUPS:
        raise ValueError("conversation_review_group_invalid")
    if not isinstance(turns, dict) or not 4 <= len(turns) <= 8:
        raise ValueError("conversation_review_turns_invalid")
    if not all(_valid_criteria(turn, criteria) for turn, criteria in turns.items()):
        raise ValueError("conversation_review_criteria_invalid")
    return group, len(turns)


def _valid_criteria(turn: object, criteria: object) -> bool:
    return (
        isinstance(turn, str)
        and bool(turn.strip())
        and isinstance(criteria, list)
        and bool(criteria)
        and all(isinstance(item, str) and item.strip() for item in criteria)
        and len(criteria) == len(set(criteria))
    )


def _score_failures(
    passed: set[str],
    by_group: Counter,
    critical: list[str],
    lost: list[str],
    total_minimum: int,
    group_minimum: int,
) -> list[str]:
    failures = []
    if len(passed) < total_minimum:
        failures.append("total_below_minimum")
    if any(by_group[group] < group_minimum for group in _GROUPS):
        failures.append("group_below_minimum")
    if critical:
        failures.append("critical_error")
    if lost:
        failures.append("parent_conversation_lost")
    return failures


def _arm(panel: dict, results: dict, arm: str) -> tuple[set[str], list[str]]:
    if not isinstance(results, dict) or results.keys() != panel.keys():
        raise ValueError(f"conversation_review_{arm}_coverage_invalid")
    passed: set[str] = set()
    critical: list[str] = []
    for conversation, spec in panel.items():
        full_pass, turn_critical = _conversation_verdicts(
            conversation, spec, results[conversation], arm
        )
        critical.extend(turn_critical)
        if full_pass:
            passed.add(conversation)
    return passed, sorted(critical)


def _conversation_verdicts(
    conversation: str, spec: dict, records: dict, arm: str
) -> tuple[bool, list[str]]:
    if not isinstance(records, dict) or records.keys() != spec["turns"].keys():
        raise ValueError(f"conversation_review_{arm}_turn_coverage_invalid")
    critical = []
    full_pass = True
    for turn, expected in spec["turns"].items():
        verdict = records[turn]
        if not _valid_verdict(verdict, expected):
            raise ValueError(f"conversation_review_{arm}_verdict_invalid")
        if verdict["critical"]:
            critical.append(f"{conversation}/{turn}")
        full_pass = (
            full_pass and not verdict["critical"] and all(verdict["criteria"].values())
        )
    return full_pass, critical


def _valid_verdict(verdict: object, expected: list[str]) -> bool:
    return (
        isinstance(verdict, dict)
        and set(verdict) == {"criteria", "critical"}
        and type(verdict["critical"]) is bool
        and isinstance(verdict["criteria"], dict)
        and verdict["criteria"].keys() == set(expected)
        and all(type(value) is bool for value in verdict["criteria"].values())
    )


def _payload_sha(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def payload_sha(payload: dict) -> str:
    """Return the canonical JSON SHA-256 used in panel and judgment receipts."""
    return _payload_sha(payload)


def checkpoint_review_id(prefix: str, run_id: str, step: int) -> str:
    """Derive a stable, distinct receipt ID for each campaign checkpoint."""
    key = stable_hash({"run_id": run_id, "step": step})[:20]
    return f"{prefix}-{key}"


def register_review(
    root: Path,
    review_id: str,
    *,
    mode: str,
    panel: dict,
    p13: dict,
    candidate: dict,
    binding: dict,
    p13_identity: dict[str, str],
    candidate_identity: dict[str, str],
    reviewer_id: str,
    reviewer_note: str,
) -> dict:
    """Register a human-reported review once; records are immutable after creation."""
    _validate_registration(
        review_id,
        binding,
        p13_identity,
        candidate_identity,
        reviewer_id,
        reviewer_note,
    )
    report = score(mode, panel, p13, candidate)
    data = {"panel": panel, "p13": p13, "candidate": candidate}
    if binding.get("panel_sha256") is not None and binding[
        "panel_sha256"
    ] != _payload_sha(panel):
        raise ValueError("conversation_review_panel_binding_invalid")
    receipt = {
        "schema_version": 1,
        "review_id": review_id,
        "binding": binding,
        "binding_sha256": stable_hash(binding),
        "panel_sha256": _payload_sha(panel),
        "p13_identity": p13_identity,
        "candidate_identity": candidate_identity,
        "reviewer_id": reviewer_id.strip(),
        "reviewer_note": reviewer_note.strip(),
        "judgments_sha256": _payload_sha(data),
        **report,
    }
    directory = operator_path(root / "conversation-reviews")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = operator_path(directory / review_id)
    with file_lock(directory / ".conversation-review.lock"):
        if target.exists():
            raise ValueError("conversation_review_immutable_conflict")
        with tempfile.TemporaryDirectory(
            prefix=f".{review_id}-", dir=directory
        ) as staging:
            staged = Path(staging) / review_id
            staged.mkdir(mode=0o700)
            atomic_json(staged / _JUDGMENTS_FILE, data)
            atomic_json(staged / _RECEIPT_FILE, receipt)
            os.replace(staged, target)
    return receipt


def register_review_request(root: Path, request: object) -> dict:
    """Register a complete operator request read from the Academy CLI JSON file."""
    fields = {
        "review_id",
        "mode",
        "panel",
        "p13",
        "candidate",
        "binding",
        "p13_identity",
        "candidate_identity",
        "reviewer_id",
        "reviewer_note",
    }
    if not isinstance(request, dict) or set(request) != fields:
        raise ValueError("conversation_review_request_invalid")
    mode = request["mode"]
    binding = request["binding"]
    if not isinstance(binding, dict):
        raise ValueError("conversation_review_binding_required")
    if mode == "dev":
        campaign_id = binding.get("campaign_id")
        if not isinstance(campaign_id, str) or not _ID.fullmatch(campaign_id):
            raise ValueError("conversation_review_campaign_binding_invalid")
        target_root = root / "campaigns" / campaign_id
    elif mode == "final":
        qualification = binding.get("qualification")
        campaign_id = (
            qualification.get("campaign_id")
            if isinstance(qualification, dict)
            else None
        )
        if not isinstance(campaign_id, str) or not _ID.fullmatch(campaign_id):
            raise ValueError("conversation_review_campaign_binding_invalid")
        target_root = root / "local-text-qualification" / campaign_id / "evidence"
    else:
        raise ValueError("conversation_review_campaign_binding_invalid")
    return register_review(
        target_root,
        request["review_id"],
        mode=request["mode"],
        panel=request["panel"],
        p13=request["p13"],
        candidate=request["candidate"],
        binding=request["binding"],
        p13_identity=request["p13_identity"],
        candidate_identity=request["candidate_identity"],
        reviewer_id=request["reviewer_id"],
        reviewer_note=request["reviewer_note"],
    )


def _validate_registration(
    review_id: str,
    binding: dict,
    p13_identity: dict[str, str],
    candidate_identity: dict[str, str],
    reviewer_id: str,
    reviewer_note: str,
) -> None:
    if not _ID.fullmatch(review_id):
        raise ValueError("conversation_review_id_invalid")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        raise ValueError("conversation_review_reviewer_required")
    if not isinstance(reviewer_note, str) or not reviewer_note.strip():
        raise ValueError("conversation_review_note_required")
    if not isinstance(binding, dict) or not binding:
        raise ValueError("conversation_review_binding_required")
    for identity in (p13_identity, candidate_identity):
        _validate_model_identity(identity)
    if (
        binding.get("p13_identity") != p13_identity
        or binding.get("candidate_identity") != candidate_identity
    ):
        raise ValueError("conversation_review_model_binding_invalid")


def _validate_model_identity(identity: dict[str, str]) -> None:
    fields = {"model", "weights_sha256", "config_sha256", "snapshot_sha256"}
    if set(identity) != fields or any(
        not isinstance(value, str) or not value.strip() for value in identity.values()
    ):
        raise ValueError("conversation_review_model_identity_invalid")


def verify_review(
    root: Path, review_id: str, binding: dict, *, require_pass: bool = True
) -> dict:
    """Verify immutable receipt, payload hashes, scorer result and exact final binding."""
    if not _ID.fullmatch(review_id):
        raise ValueError("conversation_review_id_invalid")
    target = operator_path(root / "conversation-reviews" / review_id)
    receipt_path = operator_path(target / _RECEIPT_FILE)
    judgments_path = operator_path(target / _JUDGMENTS_FILE)
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        data = json.loads(judgments_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("conversation_review_payload_invalid") from exc
    required_receipt = {
        "review_id",
        "binding",
        "binding_sha256",
        "panel_sha256",
        "p13_identity",
        "candidate_identity",
        "judgments_sha256",
        "mode",
        "status",
    }
    if (
        not isinstance(receipt, dict)
        or not required_receipt <= receipt.keys()
        or not isinstance(data, dict)
        or not isinstance(receipt.get("binding"), dict)
        or any(
            not isinstance(receipt.get(key), str)
            for key in (
                "binding_sha256",
                "panel_sha256",
                "judgments_sha256",
                "mode",
                "status",
            )
        )
        or any(
            not isinstance(receipt.get(key), dict)
            for key in ("p13_identity", "candidate_identity")
        )
    ):
        raise ValueError("conversation_review_payload_invalid")
    if receipt.get("review_id") != review_id:
        raise ValueError("conversation_review_identity_mismatch")
    if receipt.get("binding") != binding or receipt.get(
        "binding_sha256"
    ) != stable_hash(binding):
        raise ValueError("conversation_review_binding_mismatch")
    if binding.get("p13_identity") != receipt.get("p13_identity") or binding.get(
        "candidate_identity"
    ) != receipt.get("candidate_identity"):
        raise ValueError("conversation_review_model_binding_invalid")
    if (
        set(data) != {"panel", "p13", "candidate"}
        or not isinstance(data.get("panel"), dict)
        or any(not isinstance(data.get(name), dict) for name in ("p13", "candidate"))
    ):
        raise ValueError("conversation_review_payload_invalid")
    if receipt.get("panel_sha256") != _payload_sha(data["panel"]):
        raise ValueError("conversation_review_panel_hash_mismatch")
    if (
        binding.get("panel_sha256") is not None
        and binding["panel_sha256"] != receipt["panel_sha256"]
    ):
        raise ValueError("conversation_review_panel_hash_mismatch")
    if receipt.get("judgments_sha256") != _payload_sha(data):
        raise ValueError("conversation_review_judgments_hash_mismatch")
    rescored = score(receipt["mode"], data["panel"], data["p13"], data["candidate"])
    if any(receipt.get(key) != value for key, value in rescored.items()):
        raise ValueError("conversation_review_score_mismatch")
    if require_pass and receipt["status"] != "PASS":
        raise ValueError("conversation_review_thresholds_failed")
    return receipt


def verify_final_review(
    root: Path,
    review_id: str,
    qualification_binding: dict,
    *,
    candidate_config_sha256: str,
) -> dict:
    """Re-bind an immutable review to final result data when serving qualification."""
    if not isinstance(review_id, str) or not _ID.fullmatch(review_id):
        raise ValueError("conversation_review_id_invalid")
    target = operator_path(root / "conversation-reviews" / review_id)
    try:
        receipt = json.loads(
            operator_path(target / _RECEIPT_FILE).read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise ValueError("conversation_review_receipt_invalid") from exc
    if not isinstance(receipt, dict):
        raise ValueError("conversation_review_receipt_invalid")
    if receipt.get("mode") != "final":
        raise ValueError("conversation_review_final_mode_required")
    binding = receipt.get("binding")
    if (
        not isinstance(binding, dict)
        or binding.get("qualification") != qualification_binding
    ):
        raise ValueError("conversation_review_binding_mismatch")
    parent_spec = qualification_binding.get("parent")
    parent = parent_spec.get("entry") if isinstance(parent_spec, dict) else None
    if not isinstance(parent, dict):
        raise ValueError("conversation_review_parent_binding_invalid")
    candidate = binding.get("candidate_identity")
    p13 = binding.get("p13_identity")
    if not isinstance(candidate, dict) or not isinstance(p13, dict):
        raise ValueError("conversation_review_model_binding_invalid")
    if (
        candidate.get("weights_sha256")
        != qualification_binding.get("checkpoint_sha256")
        or candidate.get("config_sha256") != candidate_config_sha256
        or candidate.get("model") != parent.get("model")
        or candidate.get("snapshot_sha256") != parent.get("snapshot_sha256")
        or p13
        != {
            name: parent.get(name)
            for name in ("model", "weights_sha256", "config_sha256", "snapshot_sha256")
        }
    ):
        raise ValueError("conversation_review_model_binding_invalid")
    return verify_review(root, review_id, binding)
