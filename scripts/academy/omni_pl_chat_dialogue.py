"""Own-history dialogue contract shared by generation and sealed reporting."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import defaultdict


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def validate_dialogues(cases: list[dict]) -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        spec = case.get("dialogue")
        if spec is None:
            continue
        if (
            not isinstance(spec, dict)
            or set(spec) != {"id", "turn_index"}
            or not isinstance(spec["id"], str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", spec["id"]) is None
            or type(spec["turn_index"]) is not int
            or not 1 <= spec["turn_index"] <= 8
        ):
            raise ValueError("invalid dialogue identity")
        previous = groups[spec["id"]]
        if spec["turn_index"] != len(previous) + 1:
            raise ValueError("dialogue turns must be ordered and contiguous")
        messages = case["messages"]
        roles = [message["role"] for message in messages]
        if roles not in (["user"], ["system", "user"]) or (
            previous and roles != ["user"]
        ):
            raise ValueError("dialogue must contain only the current user turn")
        if previous and case["group_id"] != previous[0]["group_id"]:
            raise ValueError("dialogue family must stay in one group")
        previous.append(case)
    if any(not 4 <= len(turns) <= 8 for turns in groups.values()):
        raise ValueError("a dialogue requires 4 to 8 complete turns")


class DialogueHistory:
    """Rebuild each arm from its sealed responses; never substitute gold text."""

    def __init__(self) -> None:
        self.histories: dict[str, list[dict]] = {}
        self.parents: dict[str, str | None] = {}

    def context(self, case: dict) -> dict:
        spec = case.get("dialogue")
        if spec is None:
            return {}
        ident = spec["id"]
        messages = [*self.histories.get(ident, []), *case["messages"]]
        return {
            "input_messages": messages,
            "history_sha256": digest(messages),
            "history_parent_sha256": self.parents.get(ident),
        }

    def remember(self, case: dict, row: dict, expected: dict) -> None:
        if not expected:
            return
        if any(row.get(key) != value for key, value in expected.items()):
            raise ValueError("dialogue receipt history differs from its predecessors")
        ident = case["dialogue"]["id"]
        self.histories[ident] = [
            *expected["input_messages"],
            {"role": "assistant", "content": row["response"]["text"]},
        ]
        self.parents[ident] = digest(
            {key: value for key, value in row.items() if key != "label"}
        )


def blind_answer(row: dict) -> dict:
    """Preserve arm-specific context through reblinding and checkpoint splitting."""
    return {
        **row["response"],
        **{key: row[key] for key in ("input_messages", "history_sha256") if key in row},
    }


def answer_context(case: dict, answer: dict) -> list[dict]:
    """Require actual generated history for a dialogue, even at review time."""
    if "dialogue" not in case:
        return case["messages"]
    messages = answer.get("input_messages")
    if (
        not isinstance(messages, list)
        or not messages
        or messages[-1:] != case["messages"][-1:]
        or answer.get("history_sha256") != digest(messages)
    ):
        raise ValueError("dialogue answer is missing its verified history")
    return messages


def paired_delta(
    left: list[int], right: list[int], groups: list[str] | None = None
) -> dict:
    """Paired mean and a descriptive 95% normal interval, not a promotion test."""
    if not left or len(left) != len(right):
        raise ValueError("paired outcomes require equal nonempty coverage")
    differences = [b - a for a, b in zip(left, right, strict=True)]
    n = len(differences)
    delta = sum(differences) / n
    variance = sum((value - delta) ** 2 for value in differences) / max(n - 1, 1)
    margin = 1.96 * math.sqrt(variance / n)
    return {
        "n": n,
        "gains": differences.count(1),
        "losses": differences.count(-1),
        "usable_delta": delta,
        "interval_95": [max(-1.0, delta - margin), min(1.0, delta + margin)],
        "interval_method": "paired-normal-descriptive; correlated families not modeled",
        "inference_limit": "Intervals describe this small panel; a zero-width bootstrap is not proof of population equivalence.",
        **(
            {"family_bootstrap": _family_bootstrap(differences, groups)}
            if groups is not None
            else {}
        ),
    }


def _family_bootstrap(differences: list[int], groups: list[str]) -> dict:
    if len(groups) != len(differences) or any(not group for group in groups):
        raise ValueError("paired family coverage mismatch")
    members: dict[str, list[int]] = defaultdict(list)
    for group, value in zip(groups, differences, strict=True):
        members[group].append(value)
    families = list(members.values())
    rng = random.Random(20261117)
    estimates = []
    for _ in range(4096):
        sample = [rng.choice(families) for _ in families]
        estimates.append(
            sum(sum(values) for values in sample)
            / sum(len(values) for values in sample)
        )
    estimates.sort()
    return {
        "families": len(families),
        "replicates": 4096,
        "seed": 20261117,
        "interval_95": [estimates[102], estimates[3993]],
        "method": "paired cluster percentile bootstrap; whole group_id families resampled",
        "purpose": "descriptive-only; frozen promotion gate unchanged",
    }


def _dialogue_families(cases: list[dict], conversations: dict) -> dict:
    families: dict[str, set[str]] = defaultdict(set)
    decisions: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        if "dialogue" not in case:
            continue
        ident = case["dialogue"]["id"]
        families[case["group_id"]].add(ident)
        if case.get("decision") in {"accepted", "rejected"}:
            decisions[ident].add(case["decision"])
    result = {}
    for group, ids in families.items():
        branches = {tuple(sorted(decisions[ident])) for ident in ids}
        complete = len(ids) == 2 and branches == {("accepted",), ("rejected",)}
        usable = all(conversations[ident]["all_turns_usable"] for ident in ids)
        result[group] = {
            "conversation_ids": sorted(ids),
            "conversation_count": len(ids),
            "contrast_pair_complete": complete,
            "all_conversations_usable": usable,
            "both_conversations_usable": complete and usable,
        }
    return result


def grouped_scores(cases: list[dict], verdicts: dict, critical: dict) -> dict:
    """Summarize complete dialogues and contrast pairs after unblinding."""
    dialogues: dict[str, list[dict]] = defaultdict(list)
    pairs: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        if "dialogue" in case:
            dialogues[case["dialogue"]["id"]].append(case)
        if "contrast_pair_id" in case:
            pairs[case["contrast_pair_id"]].append(case)
    result: dict[str, dict] = {}
    for role, outcomes in verdicts.items():
        conversations = {}
        for ident, turns in dialogues.items():
            ids = [turn["record_id"] for turn in turns]
            conversations[ident] = {
                "turn_ids": ids,
                "usable_turns": sum(outcomes[key]["usable"] for key in ids),
                "all_turns_usable": all(outcomes[key]["usable"] for key in ids),
                "all_turns_passed": all(outcomes[key]["passed"] for key in ids),
                "critical_case_ids": sorted(set(ids) & set(critical.get(role, []))),
                "scope": turns[0].get("chat_group"),
                "assessment": (
                    "independent_review_required"
                    if turns[0].get("chat_group") in {"W", "R"}
                    else "short_factual_turns_only"
                ),
            }
        pair_scores = {}
        for ident, members in pairs.items():
            decisions = {case.get("decision") for case in members}
            complete = len(members) == 2 and decisions == {"accepted", "rejected"}
            pair_scores[ident] = {
                "complete": complete,
                "both_usable": complete
                and all(outcomes[c["record_id"]]["usable"] for c in members),
                "both_passed": complete
                and all(outcomes[c["record_id"]]["passed"] for c in members),
            }
        result[role] = {
            "conversations": conversations,
            "contrast_pairs": pair_scores,
            "dialogue_families": _dialogue_families(cases, conversations),
        }
    return result
