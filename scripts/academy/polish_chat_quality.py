"""Audit Polish chat cases and export only reviewed examples into Academy schemas."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

from scripts.academy.omni_pl_chat_data import sha256, validate_splits, write_jsonl
from scripts.academy.omni_pl_chat_evaluate import validate_dev_cases
from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.config import SETTINGS
from venom_core.services.chat_grounding import grounding_kind
from venom_core.services.studio_normal_chat import prepare_studio_normal

CASES = (
    Path(__file__).resolve().parents[2]
    / "data/training/polish-chat-quality/cases.jsonl"
)
CATEGORY_COUNTS = {
    "practical": 10,
    "information": 8,
    "writing": 6,
    "conversation": 4,
    "technical": 4,
}
CAPABILITIES = {"model", "web", "weather", "wiki"}
_SOURCE_URL = re.compile(r"https://[^\s<>\"]+")


def read_cases(path: Path = CASES) -> list[dict]:
    with path.open(encoding="utf-8") as source:
        cases = [json.loads(line) for line in source if line.strip()]
    if len(cases) != 32:
        raise ValueError("expected exactly 32 cases")
    validate_splits(cases)
    if Counter(row.get("category") for row in cases) != CATEGORY_COUNTS:
        raise ValueError("case category quotas differ from manifest")
    if sum(len(row["messages"]) >= 3 for row in cases) < 12:
        raise ValueError("at least 12 cases need conversation history")
    for row in cases:
        if row.get("source_basis") != "authored_from_research_taxonomy":
            raise ValueError("do not label authored prompts as real user transcripts")
        if row.get("capability") not in CAPABILITIES:
            raise ValueError("invalid capability")
        if not isinstance(row.get("max_new_tokens"), int) or row[
            "max_new_tokens"
        ] not in (384, 512, 768):
            raise ValueError("generation budget must be declared before scoring")
        if row["capability"] == "model" and row["max_new_tokens"] != 512:
            raise ValueError(
                "model-only cases must match the pinned 512-token GPU evaluator"
            )
        if row["capability"] != "model" and not row.get("source_expectation"):
            raise ValueError("tool case needs an explicit source expectation")
        if len(row["messages"]) > 9:
            raise ValueError(
                "this suite targets conversations of up to five user turns"
            )
    validate_dev_cases(cases)
    return cases


def export_model_cases(path: Path) -> int:
    """Write the model-only subset for the existing pinned Omni GPU evaluator."""
    cases = read_cases()
    rows = [
        {
            key: row[key]
            for key in (
                "record_id",
                "group_id",
                "split",
                "task",
                "language",
                "messages",
                "criteria",
            )
        }
        for row in cases
        if row["capability"] == "model"
    ]
    validate_dev_cases(rows)
    if path.exists():
        raise FileExistsError(path)
    write_jsonl(path, rows)
    return len(rows)


def _source_urls(context: str) -> list[str]:
    urls: list[str] = []
    for raw in _SOURCE_URL.findall(context):
        candidate = raw.rstrip(".,;)]}")
        parsed = urlparse(candidate)
        if parsed.scheme == "https" and parsed.hostname and candidate not in urls:
            urls.append(candidate)
    return urls


async def capture_tool_cases(directory: Path) -> dict:
    """Freeze public source context produced by Studio Normal for nine tool cases."""
    if directory.exists():
        raise FileExistsError(directory)
    configured = Path(SETTINGS.CHAT_PUBLIC_SOURCES_CONFIG)
    config_path = (
        configured
        if configured.is_absolute()
        else Path(__file__).resolve().parents[2] / configured
    )
    config_sha256 = sha256(config_path)
    cases = [row for row in read_cases() if row["capability"] != "model"]
    if len(cases) != 9:
        raise ValueError("expected nine source cases")
    generated: list[dict] = []
    evidence: list[dict] = []

    async def no_notes():
        raise AssertionError("source evaluation must not retrieve private notes")

    for case in cases:
        turns = case["messages"]
        history = [
            {
                **turn,
                "request_id": f"{case['record_id']}-{index // 2}",
                "status": "COMPLETED",
            }
            for index, turn in enumerate(turns[:-1])
        ]
        store = SimpleNamespace(get_history=lambda _session_id: history)
        request = SimpleChatRequest(
            content=turns[-1]["content"],
            studio_normal=True,
            session_id=case["record_id"],
            max_tokens=case["max_new_tokens"],
        )
        prepared, context = await prepare_studio_normal(request, store, no_notes)
        route = grounding_kind(request.content)
        source_state = (
            "not_routed"
            if not route
            else "retrieved"
            if "[PUBLIC_SOURCES]" in context
            else "unavailable"
        )
        input_messages = [
            {"role": "system", "content": context},
            *(
                {"role": turn.role, "content": turn.content}
                for turn in prepared.history
            ),
            {"role": "user", "content": prepared.content},
        ]
        generated.append(
            {
                key: case[key]
                for key in (
                    "record_id",
                    "group_id",
                    "split",
                    "task",
                    "language",
                    "criteria",
                )
            }
            | {"messages": input_messages, "max_new_tokens": prepared.max_tokens}
        )
        evidence.append(
            {
                "record_id": case["record_id"],
                "capability": case["capability"],
                "route": route,
                "source_state": source_state,
                "source_urls": _source_urls(context)
                if source_state == "retrieved"
                else [],
                "history_turns": len(prepared.history),
                "source_expectation": case["source_expectation"],
                "system_context": context,
            }
        )
    validate_dev_cases(generated)
    if sha256(config_path) != config_sha256:
        raise ValueError("public source configuration changed during capture")
    directory.mkdir(parents=True)
    dev_path = directory / "tool-dev.jsonl"
    evidence_path = directory / "source-evidence.jsonl"
    write_jsonl(dev_path, generated)
    write_jsonl(evidence_path, evidence)
    manifest = {
        "schema_version": 1,
        "mode": "studio_normal_context_with_direct_omni_gpu_generation",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_ids": [row["record_id"] for row in generated],
        "cases_sha256": sha256(CASES),
        "source_config_sha256": config_sha256,
        "tool_dev_sha256": sha256(dev_path),
        "source_evidence_sha256": sha256(evidence_path),
        "grounding_code_sha256": sha256(
            Path(__file__).resolve().parents[2]
            / "venom_core/services/chat_grounding.py"
        ),
        "studio_normal_code_sha256": sha256(
            Path(__file__).resolve().parents[2]
            / "venom_core/services/studio_normal_chat.py"
        ),
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "cases": len(generated),
        "source_states": dict(Counter(row["source_state"] for row in evidence)),
        "directory": str(directory),
    }


def export_reviewed_train(source: Path, destination: Path) -> int:
    """Reject unreviewed or leaking examples before Academy training ingest."""
    with source.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if not rows:
        raise ValueError("no reviewed training examples")
    cases = read_cases()
    eval_groups = {row["group_id"] for row in cases}
    eval_prompts = {
        tuple(
            message["content"].casefold().strip()
            for message in row["messages"]
            if message["role"] == "user"
        )
        for row in cases
    }
    for row in rows:
        if row.get("split") != "train" or row.get("quality_status") != "accepted":
            raise ValueError("training export requires accepted train records")
        if row.get("group_id") in eval_groups:
            raise ValueError("training group overlaps the quality evaluation")
        if row.get("source_repo") in (None, "") or row.get("license") in (None, ""):
            raise ValueError("training example needs a source and license")
        if row.get("source_revision") in (None, "") or row.get("source_record_id") in (
            None,
            "",
        ):
            raise ValueError("training example needs pinned source identity")
        if not row.get("review_note") or not row.get("reviewer_id"):
            raise ValueError("training example needs documented human review")
        prompt = tuple(
            message["content"].casefold().strip()
            for message in row["messages"]
            if message["role"] == "user"
        )
        if prompt in eval_prompts:
            raise ValueError("training prompt overlaps the quality evaluation")
    validate_splits(rows, cases)
    if destination.exists():
        raise FileExistsError(destination)
    write_jsonl(destination, rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    export = sub.add_parser("export-model")
    export.add_argument("destination", type=Path)
    reviewed = sub.add_parser("export-reviewed-train")
    reviewed.add_argument("source", type=Path)
    reviewed.add_argument("destination", type=Path)
    capture = sub.add_parser("capture-tools")
    capture.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        print(f"Validated {len(read_cases())} quality cases")
    elif args.command == "export-model":
        print(f"Exported {export_model_cases(args.destination)} model-only cases")
    elif args.command == "capture-tools":
        print(json.dumps(asyncio.run(capture_tool_cases(args.directory))))
    else:
        print(
            f"Exported {export_reviewed_train(args.source, args.destination)} reviewed training records"
        )


if __name__ == "__main__":
    main()
