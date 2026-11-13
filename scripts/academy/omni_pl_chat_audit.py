"""Measure a reviewed replay/fresh mixture offline using Omni's actual mask."""

import json
import re
import sys
import unicodedata
from pathlib import Path

from scripts.academy.omni_pl_chat_data import read_jsonl, sha256, validate_splits
from scripts.academy.omni_pl_chat_evaluate import validate_dev_cases
from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN, audit
from scripts.academy.omni_pl_chat_p1 import _verify_boundary, _write_json

GROUPS = ("replay", "fresh")
MAX_INPUT_BYTES = 8 * 1024 * 1024
_SKILL = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = dict(pairs)
    if len(pairs) != len(result):
        raise ValueError("audit JSON must not contain duplicate keys")
    return result


def read_taxonomy(path: Path, record_ids: set[str]) -> dict[str, dict[str, str]]:
    """Read an exact and unambiguous classification for the frozen training IDs."""
    doc = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
    )
    if (
        not isinstance(doc, dict)
        or doc.keys() != {"schema_version", "records"}
        or type(doc["schema_version"]) is not int
        or doc["schema_version"] != 1
        or not isinstance(doc["records"], dict)
    ):
        raise ValueError("audit taxonomy requires a v1 record mapping")
    labels = doc["records"]
    if labels.keys() != record_ids:
        raise ValueError("audit taxonomy must label exactly every training record")
    for label in labels.values():
        if (
            not isinstance(label, dict)
            or label.keys() != {"group", "skill"}
            or label["group"] not in GROUPS
            or not isinstance(label["skill"], str)
            or _SKILL.fullmatch(label["skill"]) is None
        ):
            raise ValueError(
                "audit taxonomy requires a replay/fresh group and skill slug"
            )
    return labels


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _messages(messages: list[dict], *, include_system: bool = False) -> tuple:
    return tuple(
        (msg["role"], _normalize(msg["content"]))
        for msg in messages
        if msg["role"] != "system" or include_system
    )


def leakage_counts(train: list[dict], dev: list[dict]) -> dict:
    """Count distinct exact matches. Roles remain attached to every prefix turn."""
    prefixes = {
        _messages(row["messages"][:turn])
        for row in train
        for turn in row["supervision"]
    }
    prompts = {_messages(row["messages"]) for row in dev}
    train_users = {prompt[-1][1] for prompt in prefixes}
    dev_users = {prompt[-1][1] for prompt in prompts}
    train_conversations = {
        _messages(row["messages"], include_system=True) for row in train
    }
    return {
        "normalization": "nfkc_casefold_whitespace_v1",
        "supervised_prefix_matches": len(prefixes & prompts),
        "final_user_matches": len(train_users & dev_users),
        "duplicate_train_records": len(train) - len(train_conversations),
    }


def _bucket(observations: list[dict]) -> dict:
    return {
        "records": len(observations),
        "supervised_tokens": sum(row["supervised"] for row in observations),
        "input_tokens": sum(row["tokens"] for row in observations),
        "max_input_tokens": max((row["tokens"] for row in observations), default=0),
        "max_supervised_tokens": max(
            (row["supervised"] for row in observations), default=0
        ),
    }


def _buckets(observations: list[dict], labels: dict) -> tuple[dict, dict]:
    groups = {group: [] for group in GROUPS}
    skills: dict[str, dict[str, list[dict]]] = {}
    for row in observations:
        label = labels[row["record_id"]]
        group, skill = label["group"], label["skill"]
        if skill not in skills:
            skills[skill] = {name: [] for name in GROUPS}
        groups[group].append(row)
        skills[skill][group].append(row)
    return (
        {group: _bucket(rows) for group, rows in groups.items()},
        {
            skill: {group: _bucket(rows) for group, rows in skills[skill].items()}
            for skill in sorted(skills)
        },
    )


def build_audit(
    snapshot: Path,
    train_path: Path,
    dev_path: Path,
    taxonomy_path: Path,
    max_tokens: int,
) -> dict:
    """Build the private-input/public-count report without exposing any record text."""
    if not 32 <= max_tokens <= 4096:
        raise ValueError("audit max_tokens must fit the Academy recipe")
    sources = {
        name: path
        for name, path in (
            ("train", train_path),
            ("dev", dev_path),
            ("taxonomy", taxonomy_path),
        )
    }
    if any(
        path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES
        for path in sources.values()
    ):
        raise ValueError("audit inputs must be bounded regular files")
    hashes = {f"{name}_sha256": sha256(path) for name, path in sources.items()}
    train = read_jsonl(train_path)
    dev = read_jsonl(dev_path)
    if not 1 <= len(train) <= 2048 or any(row.get("split") != "train" for row in train):
        raise ValueError("audit requires one to 2048 train records")
    validate_splits(train)
    validate_dev_cases(dev)
    for key in ("record_id", "group_id"):
        if {row[key] for row in train} & {row[key] for row in dev}:
            raise ValueError(
                "audit train and dev must have disjoint record and group IDs"
            )
    labels = read_taxonomy(taxonomy_path, {row["record_id"] for row in train})
    observations, metadata = audit(snapshot, train, max_tokens)
    if any(sha256(path) != hashes[f"{name}_sha256"] for name, path in sources.items()):
        raise ValueError("audit input changed during tokenization")
    groups, skills = _buckets(observations, labels)
    files = metadata["files"]
    return {
        "schema_version": 1,
        "model": metadata["repo"],
        "revision": metadata["revision"],
        "snapshot_sha256": sha256(SNAPSHOT_PIN),
        **hashes,
        "tokenization": {
            "template_sha256": files["chat_template.jinja"]["sha256"],
            "tokenizer_sha256": files["tokenizer.json"]["sha256"],
            "tokenizer_config_sha256": files["tokenizer_config.json"]["sha256"],
            "model_config_sha256": files["config.json"]["sha256"],
            "transformers": metadata["transformers"],
            "tokenizers": metadata["tokenizers"],
            "max_tokens": max_tokens,
        },
        "totals": _bucket(observations),
        "groups": groups,
        "skills": skills,
        "leakage": leakage_counts(train, dev),
    }


def main() -> None:
    dev = Path("/inputs/dev.jsonl")
    taxonomy = Path("/inputs/taxonomy.json")
    _verify_boundary((str(dev), str(taxonomy)))
    report = build_audit(
        Path("/inputs/model"),
        Path("/inputs/train.jsonl"),
        dev,
        taxonomy,
        int(sys.argv[1]),
    )
    _write_json(Path("/out/audit.json"), report)


if __name__ == "__main__":
    main()
