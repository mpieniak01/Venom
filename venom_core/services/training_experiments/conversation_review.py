"""Immutable operator receipts for full-conversation Academy qualification."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from venom_core.services.remote_training.lifecycle import atomic_json, file_lock
from venom_core.services.remote_training.paths import operator_path

from .profiles import stable_hash

_GROUPS = frozenset("SKWR")
_LIMITS = {"dev": (96, 24, 72, 16), "final": (48, 12, 36, 8)}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


class MissingConversationReview(FileNotFoundError):
    """A checkpoint awaits operator review; carries the exact binding to register."""

    def __init__(self, review_id: str, binding: dict):
        super().__init__("conversation_review_receipt_missing")
        self.review_id = review_id
        self.binding = binding


def score(mode: str, panel: dict, p13: dict, candidate: dict) -> dict:
    """Score complete paired conversations using the offline 0A thresholds."""
    if mode not in _LIMITS:
        raise ValueError("conversation_review_mode_invalid")
    size, group_size, total_minimum, group_minimum = _LIMITS[mode]
    if not isinstance(panel, dict) or len(panel) != size:
        raise ValueError(f"conversation_review_panel_requires_{size}")
    groups: Counter[str] = Counter()
    turns_total = 0
    for conversation, spec in panel.items():
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
        turns_total += len(turns)
        for turn, criteria in turns.items():
            if (
                not isinstance(turn, str)
                or not turn.strip()
                or not isinstance(criteria, list)
                or not criteria
                or not all(isinstance(item, str) and item.strip() for item in criteria)
                or len(criteria) != len(set(criteria))
            ):
                raise ValueError("conversation_review_criteria_invalid")
        groups[group] += 1
    if groups != Counter({group: group_size for group in _GROUPS}):
        raise ValueError("conversation_review_group_counts_invalid")

    parent_passed, _ = _arm(panel, p13, "p13")
    passed, critical = _arm(panel, candidate, "candidate")
    by_group = Counter(panel[key]["group"] for key in passed)
    lost = sorted(parent_passed - passed)
    failures = []
    if len(passed) < total_minimum:
        failures.append("total_below_minimum")
    if any(by_group[group] < group_minimum for group in _GROUPS):
        failures.append("group_below_minimum")
    if critical:
        failures.append("critical_error")
    if lost:
        failures.append("parent_conversation_lost")
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


def _arm(panel: dict, results: dict, arm: str) -> tuple[set[str], list[str]]:
    if not isinstance(results, dict) or results.keys() != panel.keys():
        raise ValueError(f"conversation_review_{arm}_coverage_invalid")
    passed: set[str] = set()
    critical: list[str] = []
    for conversation, spec in panel.items():
        records = results[conversation]
        if not isinstance(records, dict) or records.keys() != spec["turns"].keys():
            raise ValueError(f"conversation_review_{arm}_turn_coverage_invalid")
        full_pass = True
        for turn, expected in spec["turns"].items():
            verdict = records[turn]
            if (
                not isinstance(verdict, dict)
                or set(verdict) != {"criteria", "critical"}
                or type(verdict["critical"]) is not bool
                or not isinstance(verdict["criteria"], dict)
                or verdict["criteria"].keys() != set(expected)
                or not all(
                    type(value) is bool for value in verdict["criteria"].values()
                )
            ):
                raise ValueError(f"conversation_review_{arm}_verdict_invalid")
            if verdict["critical"]:
                critical.append(f"{conversation}/{turn}")
            full_pass = (
                full_pass
                and not verdict["critical"]
                and all(verdict["criteria"].values())
            )
        if full_pass:
            passed.add(conversation)
    return passed, sorted(critical)


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
    if not _ID.fullmatch(review_id):
        raise ValueError("conversation_review_id_invalid")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        raise ValueError("conversation_review_reviewer_required")
    if not isinstance(reviewer_note, str) or not reviewer_note.strip():
        raise ValueError("conversation_review_note_required")
    if not isinstance(binding, dict) or not binding:
        raise ValueError("conversation_review_binding_required")
    for identity in (p13_identity, candidate_identity):
        if set(identity) != {
            "model",
            "weights_sha256",
            "config_sha256",
            "snapshot_sha256",
        }:
            raise ValueError("conversation_review_model_identity_invalid")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in identity.values()
        ):
            raise ValueError("conversation_review_model_identity_invalid")
    if (
        binding.get("p13_identity") != p13_identity
        or binding.get("candidate_identity") != candidate_identity
    ):
        raise ValueError("conversation_review_model_binding_invalid")
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
        target.mkdir(mode=0o700)
        atomic_json(target / "judgments.json", data)
        atomic_json(target / "receipt.json", receipt)
    return receipt


def verify_review(
    root: Path, review_id: str, binding: dict, *, require_pass: bool = True
) -> dict:
    """Verify immutable receipt, payload hashes, scorer result and exact final binding."""
    if not _ID.fullmatch(review_id):
        raise ValueError("conversation_review_id_invalid")
    target = operator_path(root / "conversation-reviews" / review_id)
    receipt_path = operator_path(target / "receipt.json")
    judgments_path = operator_path(target / "judgments.json")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    data = json.loads(judgments_path.read_text(encoding="utf-8"))
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
    if set(data) != {"panel", "p13", "candidate"}:
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
    target = operator_path(root / "conversation-reviews" / review_id)
    receipt = json.loads(
        operator_path(target / "receipt.json").read_text(encoding="utf-8")
    )
    binding = receipt.get("binding")
    if (
        not isinstance(binding, dict)
        or binding.get("qualification") != qualification_binding
    ):
        raise ValueError("conversation_review_binding_mismatch")
    parent = qualification_binding.get("parent", {}).get("entry")
    if not isinstance(parent, dict):
        raise ValueError("conversation_review_parent_binding_invalid")
    candidate = binding.get("candidate_identity", {})
    p13 = binding.get("p13_identity", {})
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
