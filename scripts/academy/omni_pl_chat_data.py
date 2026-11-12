"""Prepare explicitly reviewed Polish chat examples for the Omni pilot."""

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

SOURCE_REPO = "NASK-PIB/PLLuM-Align"
SOURCE_REVISION = "aa9ae3d4e0d4ffa7b5f52548928de20517122e4b"
SOURCE_LICENSE = "CC-BY-SA-4.0"
SOURCE_HASHES = {
    "dialogs.jsonl": "5d8e4f401cc877a3f111b646bc7e5f27c5d698f15fbc9c80e5695036cc93b609",
    "ranking.jsonl": "391961d653bad73369c641174f733dbbd1c1e369e5d64551fdce1514237f313d",
}
_CONTROL_TEXT = re.compile(r"<\|[^<>]*\|>|</?think>|CONTINUE_FINAL_MESSAGE_TAG")


MAX_DEV_TASK_LENGTH = 128


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(row)
    if not rows:
        raise ValueError(f"{path}: no records")
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def validate_messages(messages: object, final_role: str) -> None:
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a nonempty list")
    expected_role = "user"
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or message.keys() != {"role", "content"}:
            raise ValueError(f"message {index}: expected role and content")
        content = message["content"]
        if (
            not isinstance(content, str)
            or not content.strip()
            or "\x00" in content
            or _CONTROL_TEXT.search(content)
        ):
            raise ValueError(f"message {index}: empty text or model control token")
        role = message["role"]
        if role == "system" and index == 0:
            continue
        if role != expected_role:
            raise ValueError(f"message {index}: expected role {expected_role}")
        expected_role = "assistant" if role == "user" else "user"
    if messages[-1]["role"] != final_role:
        raise ValueError(f"messages must end with {final_role}")


def validate_supervision(messages: list[dict], supervision: object) -> None:
    if (
        not isinstance(supervision, list)
        or not supervision
        or any(
            type(index) is not int
            or not 0 <= index < len(messages)
            or messages[index]["role"] != "assistant"
            for index in supervision
        )
        or supervision != sorted(set(supervision))
    ):
        raise ValueError(
            "supervision must contain distinct sorted assistant message indices"
        )


def _normalized(messages: list[dict]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            message["role"],
            " ".join(
                unicodedata.normalize("NFKC", message["content"]).casefold().split()
            ),
        )
        for message in messages
        if message["role"] != "system"
    )


def validate_splits(*collections: list[dict]) -> None:
    """Reject duplicate IDs, cross-split groups and identical generation prompts."""
    ids: set[str] = set()
    groups: dict[str, str] = {}
    prompts: dict[tuple[tuple[str, str], ...], str] = {}
    for rows in collections:
        for row in rows:
            record_id, group, split = (
                row.get(key) for key in ("record_id", "group_id", "split")
            )
            if (
                not all(
                    isinstance(item, str) and item.strip()
                    for item in (record_id, group)
                )
                or split not in ("train", "dev", "pilot")
                or row.get("language") != "pl"
            ):
                raise ValueError(
                    "expected Polish record with ID, group and known split"
                )
            if record_id in ids:
                raise ValueError(f"duplicate record_id: {record_id}")
            ids.add(record_id)
            if groups.setdefault(group, split) != split:
                raise ValueError(f"group appears in multiple splits: {group}")
            messages = row.get("messages")
            if split == "train":
                validate_messages(messages, "assistant")
                validate_supervision(messages, row.get("supervision"))
                if row.get("quality_status") != "accepted" or any(
                    not isinstance(row.get(key), str) or not row[key].strip()
                    for key in (
                        "source_repo",
                        "source_revision",
                        "source_record_id",
                        "license",
                        "review_note",
                    )
                ):
                    raise ValueError(
                        f"{record_id}: training record needs provenance and explicit review"
                    )
                contexts = (messages[:index] for index in row["supervision"])
            else:
                validate_messages(messages, "user")
                contexts = (messages,)
            for context in contexts:
                if prompts.setdefault(_normalized(context), split) != split:
                    raise ValueError(
                        f"identical generation prompt across splits: {record_id}"
                    )


def extract_candidates(raw_dir: Path) -> tuple[list[dict], dict]:
    candidates = []
    rejections: Counter[str] = Counter()
    seen: set[tuple] = set()
    raw_counts = {}
    for filename, expected_hash in SOURCE_HASHES.items():
        path = raw_dir / filename
        if sha256(path) != expected_hash:
            raise ValueError(f"{path}: source SHA-256 differs from the pinned revision")
        rows = read_jsonl(path)
        raw_counts[filename] = len(rows)
        for row in rows:
            source_id = row.get("id")
            messages = row.get("chosen")
            if filename == "dialogs.jsonl":
                match = re.fullmatch(r"(\d+)_\d+_\d+", str(source_id))
            else:
                if str(source_id).startswith("polqa_"):
                    rejections["benchmark_derived"] += 1
                    continue
                match = re.fullmatch(r"([a-zA-Z0-9_-]+)_\d+", str(source_id))
            if not match:
                rejections["unknown_source_id"] += 1
                continue
            try:
                validate_messages(messages, "assistant")
            except ValueError:
                rejections["invalid_text_or_structure"] += 1
                continue
            identity = _normalized(messages)
            if identity in seen:
                rejections["duplicate_chosen_transcript"] += 1
                continue
            seen.add(identity)
            category = path.stem
            candidates.append(
                {
                    "record_id": f"pllum-align-{category}-{source_id}",
                    "task": "dialogue" if len(messages) > 2 else "single_turn",
                    "language": "pl",
                    "source_repo": SOURCE_REPO,
                    "source_revision": SOURCE_REVISION,
                    "source_record_id": source_id,
                    "license": SOURCE_LICENSE,
                    "group_id": f"pllum-align-{category}-{match[1]}",
                    "messages": messages,
                    "supervision": [len(messages) - 1],
                    "quality_status": "pending_review",
                }
            )
    return candidates, {"raw_counts": raw_counts, "rejected": dict(rejections)}


def apply_reviews(candidates: list[dict], reviews: list[dict]) -> list[dict]:
    """Select by ID and require a recorded reason for every approval."""
    available = {row["record_id"]: row for row in candidates}
    selected = []
    seen = set()
    for review in reviews:
        record_id = review.get("record_id")
        note = review.get("review_note")
        if (
            not isinstance(record_id, str)
            or record_id not in available
            or record_id in seen
        ):
            raise ValueError(f"unknown or duplicate review: {record_id}")
        if not isinstance(note, str) or not note.strip():
            raise ValueError(f"{record_id}: missing review_note")
        seen.add(record_id)
        selected.append(
            {
                **available[record_id],
                "split": "train",
                "quality_status": "accepted",
                "review_note": note,
            }
        )
    validate_splits(selected)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--reviews", type=Path, help="JSONL with approved record_id and review_note"
    )
    parser.add_argument(
        "--eval", dest="evaluation", type=Path, help="Dev and pilot JSONL"
    )
    args = parser.parse_args()
    if args.reviews and not args.evaluation:
        parser.error("--reviews requires --eval for cross-split validation")

    candidates, report = extract_candidates(args.raw_dir)
    selected = (
        apply_reviews(candidates, read_jsonl(args.reviews)) if args.reviews else []
    )
    evaluation = read_jsonl(args.evaluation) if args.evaluation else []
    if any(row.get("split") not in ("dev", "pilot") for row in evaluation):
        raise ValueError("evaluation file must contain only dev and pilot records")
    validate_splits(selected, evaluation)
    args.output.mkdir(parents=True, exist_ok=False)
    write_jsonl(args.output / "candidates.jsonl", candidates)
    if selected:
        write_jsonl(args.output / "train.jsonl", selected)
    report.update(
        source_repo=SOURCE_REPO,
        source_revision=SOURCE_REVISION,
        license=SOURCE_LICENSE,
        source_sha256=SOURCE_HASHES,
        candidates=len(candidates),
        candidate_groups=len({row["group_id"] for row in candidates}),
        approved=len(selected),
        train_sha256=sha256(args.output / "train.jsonl") if selected else None,
        reviews_sha256=sha256(args.reviews) if args.reviews else None,
        evaluation_sha256=sha256(args.evaluation) if args.evaluation else None,
    )
    (args.output / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
