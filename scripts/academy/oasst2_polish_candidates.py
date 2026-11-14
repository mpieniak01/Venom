"""Prepare reviewed-source Polish OASST2 paths for local human review.

This tool never accepts source answers as training targets automatically.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

from scripts.academy.omni_pl_chat_data import sha256, validate_messages, write_jsonl

SOURCE_REPO = "OpenAssistant/oasst2"
SOURCE_REVISION = "179dd21fc55192153d94adb0e0ce8f69e222bf75"
SOURCE_SHA256 = "9638227b41b0a4fb69afa5d5c4b52e3fb6abfd56c9870d81bae32c9981e769b1"
SOURCE_FILE = "data/train-00000-of-00001-88ba0162028a73fc.parquet"
OUTPUT_ROOT = (
    Path(__file__).resolve().parents[2] / "test-results/polish-chat-candidates"
).resolve()
_COLUMNS = (
    "message_id",
    "parent_id",
    "message_tree_id",
    "role",
    "lang",
    "text",
    "review_result",
    "deleted",
    "rank",
    "synthetic",
)


def _eligible(row: dict) -> bool:
    return (
        row.get("lang") == "pl"
        and row.get("role") in {"prompter", "assistant"}
        and row.get("review_result") is True
        and row.get("deleted") is False
        and row.get("synthetic") is False
        and isinstance(row.get("message_id"), str)
        and isinstance(row.get("message_tree_id"), str)
        and isinstance(row.get("text"), str)
    )


def select_paths(rows: list[dict]) -> list[dict]:
    """Keep one longest Polish path ending in a top-ranked source answer."""
    available = {row["message_id"]: row for row in rows if _eligible(row)}
    chosen: dict[str, dict] = {}
    for leaf in available.values():
        if leaf["role"] != "assistant" or leaf.get("rank") != 0:
            continue
        path: list[dict] = []
        seen: set[str] = set()
        current: dict | None = leaf
        while current is not None:
            message_id = current["message_id"]
            if (
                message_id in seen
                or current["message_tree_id"] != leaf["message_tree_id"]
            ):
                path = []
                break
            seen.add(message_id)
            path.append(current)
            parent = current.get("parent_id")
            current = available.get(parent) if parent is not None else None
            if parent is not None and current is None:
                path = []
                break
        if not path:
            continue
        path.reverse()
        if path[0]["parent_id"] is not None or path[0]["role"] != "prompter":
            continue
        messages = [
            {
                "role": "user" if item["role"] == "prompter" else "assistant",
                "content": item["text"],
            }
            for item in path
        ]
        try:
            validate_messages(messages, "assistant")
        except ValueError:
            continue
        candidate = {
            "record_id": f"oasst2-polish-{leaf['message_id']}",
            "group_id": f"oasst2-tree-{leaf['message_tree_id']}",
            "source_repo": SOURCE_REPO,
            "source_revision": SOURCE_REVISION,
            "source_record_id": leaf["message_id"],
            "license": "Apache-2.0",
            "language": "pl",
            "messages": messages,
            "supervision": [len(messages) - 1],
            "review_flags": (
                ["non_top_rank_context"]
                if any(
                    item["role"] == "assistant" and item.get("rank") != 0
                    for item in path[:-1]
                )
                else []
            ),
            "quality_status": "pending_review",
            "training_eligible": False,
        }
        tree_id = leaf["message_tree_id"]
        previous = chosen.get(tree_id)
        if previous is None or (len(messages), candidate["record_id"]) > (
            len(previous["messages"]),
            previous["record_id"],
        ):
            chosen[tree_id] = candidate
    return sorted(chosen.values(), key=lambda item: item["record_id"])


def prepare(source: Path, output: Path) -> dict:
    """Read a pinned local Parquet file and write an ignored review queue."""
    source = source.resolve()
    output = output.resolve()
    if source.is_symlink() or not source.is_file() or sha256(source) != SOURCE_SHA256:
        raise ValueError("OASST2 source differs from pinned train Parquet")
    if output.suffix != ".jsonl" or not output.is_relative_to(OUTPUT_ROOT):
        raise ValueError(
            "review output must be JSONL under the local candidate directory"
        )
    if output.exists():
        raise FileExistsError(output)
    selected_rows = []
    file = pq.ParquetFile(source)
    for batch in file.iter_batches(columns=list(_COLUMNS), batch_size=8192):
        selected_rows.extend(row for row in batch.to_pylist() if _eligible(row))
    candidates = select_paths(selected_rows)
    if not candidates:
        raise ValueError("no eligible Polish OASST2 paths")
    output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output, candidates)
    return {
        "source_repo": SOURCE_REPO,
        "source_revision": SOURCE_REVISION,
        "source_file": SOURCE_FILE,
        "source_sha256": SOURCE_SHA256,
        "source_polish_reviewed_messages": len(selected_rows),
        "pending_review_dialogues": len(candidates),
        "user_turns": dict(
            sorted(
                Counter(
                    sum(message["role"] == "user" for message in row["messages"])
                    for row in candidates
                ).items()
            )
        ),
        "output": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
