"""Pure data, provenance and qualification contracts; no model imports."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from itertools import zip_longest
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

MODEL = "ibm-granite/granite-4.2-3b"
REVISION = "4e9c275e232f10211ec88644d106a1f6a1b60e06"
FINISH = "Finish"


def digest(value: Any) -> str:
    """Hash canonical JSON without platform-dependent whitespace."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def file_digest(path: Path) -> str:
    """Hash a file without materializing checkpoint-sized data in memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, data: Any) -> None:
    """Write JSON as data through an owned temporary stream, then replace atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=path.name + ".",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class TrainingProfile:
    """Frozen hyperparameters shared by smoke, training and qualification."""

    model: str = MODEL
    revision: str = REVISION
    quantization: str = "nf4"
    context: int = 2048
    rank: int = 16
    alpha: int = 32
    dropout: float = 0.05
    learning_rate: float = 0.0001
    accumulation: int = 4
    seed: int = 17
    gradient_checkpointing: bool = True

    def validate(self) -> None:
        """Reject unsupported configurations before touching GPU or outputs."""
        if self.model != MODEL or self.revision != REVISION:
            raise ValueError("granite_checkpoint_mismatch")
        if self.quantization not in {"nf4", "bf16"}:
            raise ValueError("granite_precision_invalid")
        for name in ("context", "rank", "alpha", "accumulation", "seed"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError("granite_integer_invalid:" + name)
        if self.context > 4096 or self.rank > 64 or self.accumulation > 32:
            raise ValueError("granite_profile_budget_exceeded")
        if not math.isfinite(self.learning_rate) or not 0 < self.learning_rate <= 0.01:
            raise ValueError("granite_learning_rate_invalid")
        if not math.isfinite(self.dropout) or not 0 <= self.dropout < 1:
            raise ValueError("granite_dropout_invalid")

    def identity(self) -> dict[str, Any]:
        """Expose reproducible configuration, never machine-local secrets."""
        self.validate()
        return asdict(self)


def load_profile(path: Path) -> TrainingProfile:
    """Read and validate the same profile for preparation, intake and training."""
    data = json.loads(path.read_text())
    data.pop("schema_version", None)
    profile = TrainingProfile(**data)
    profile.validate()
    return profile


def inside(root: Path, relative: str) -> Path:
    """Resolve only regular, in-root source files."""
    candidate = root / relative
    if Path(relative).is_absolute() or candidate.is_symlink():
        raise ValueError("granite_data_path_invalid")
    target = candidate.resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError("granite_data_path_invalid")
    return target


def assistant_targets(row: dict[str, Any]) -> set[int]:
    """Keep failed demonstration prefixes as context, never as positive targets."""
    messages = row["messages"]
    available = {
        i for i, message in enumerate(messages) if message.get("role") == "assistant"
    }
    selected = row.get("supervised_assistant_indices")
    if selected is None:
        return available
    if (
        not isinstance(selected, list)
        or not selected
        or any(type(i) is not int for i in selected)
    ):
        raise ValueError("granite_supervision_indices_invalid")
    targets = set(selected)
    if (
        len(targets) != len(selected)
        or not targets <= available
        or len(messages) - 1 not in targets
    ):
        raise ValueError("granite_supervision_indices_invalid")
    return targets


def _validate_header(row: dict[str, Any], split: str) -> list[str]:
    if row.get("split") != split or row.get("training_allowed") != (split == "train"):
        raise ValueError("granite_split_not_allowed")
    if not row.get("problem_group") or str(row["problem_group"]).startswith(
        "venom-maintenance-v1:"
    ):
        raise ValueError("granite_problem_group_invalid")
    if not isinstance(row.get("tools"), list) or not isinstance(
        row.get("messages"), list
    ):
        raise ValueError("granite_structured_conversation_required")
    names = [t["function"]["name"] for t in row["tools"]]
    if len(set(names)) != len(names) or any(not n.isidentifier() for n in names):
        raise ValueError("granite_tool_names_invalid")
    return names


def _consume_observation(message: dict, pending: dict) -> None:
    ident = message.get("tool_call_id")
    if ident not in pending or pending.pop(ident) != message.get("name"):
        raise ValueError("granite_orphan_tool_response")
    if not isinstance(message.get("content"), str):
        raise ValueError("granite_tool_content_invalid")


def _register_calls(message: dict, names: list[str], seen: set, pending: dict) -> None:
    for call in message.get("tool_calls", []):
        function = call["function"]
        ident = call["id"]
        if (
            message["role"] != "assistant"
            or function["name"] not in names
            or ident in seen
        ):
            raise ValueError("granite_call_invalid")
        if not isinstance(function.get("arguments"), dict):
            raise ValueError("granite_arguments_must_be_object")
        seen.add(ident)
        if function["name"] != FINISH:
            pending[ident] = function["name"]


def validate_conversation(row: dict[str, Any], split: str) -> None:
    """Require structured calls and matched observations without repairing labels."""
    names = _validate_header(row, split)
    pending: dict[str, str] = {}
    seen = set()
    for message in row["messages"]:
        role = message.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("granite_role_invalid")
        if role == "tool":
            _consume_observation(message, pending)
            continue
        if pending:
            raise ValueError("granite_missing_tool_response")
        _register_calls(message, names, seen, pending)
    if pending or not row["messages"] or row["messages"][-1]["role"] != "assistant":
        raise ValueError("granite_incomplete_conversation")
    assistant_targets(row)


def load_dataset(
    root: Path, manifest: dict, dataset: str
) -> tuple[list[dict], list[dict]]:
    """Validate immutable dataset receipts, splits and family disjointness."""
    if dataset not in {"domain", "hf"}:
        raise ValueError("granite_dataset_unknown")
    sides = []
    for split in ("train", "validation"):
        key = f"{dataset}/{split}.jsonl"
        spec = manifest["datasets"][key]
        path = inside(root, key)
        if file_digest(path) != spec["sha256"]:
            raise ValueError("granite_dataset_hash_mismatch")
        rows = [
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]
        if len(rows) != spec["rows"] or not rows:
            raise ValueError("granite_dataset_count_mismatch")
        for row in rows:
            validate_conversation(row, split)
        sides.append(rows)
    train, validation = sides
    if {r["problem_group"] for r in train} & {r["problem_group"] for r in validation}:
        raise ValueError("granite_split_leakage")
    if {r["record_id"] for r in train} & {r["record_id"] for r in validation}:
        raise ValueError("granite_duplicate_record")
    return train, validation


def select_dataset(
    domain: tuple[list[dict], list[dict]],
    hf: tuple[list[dict], list[dict]],
    dataset: str,
) -> tuple[list[dict], list[dict]]:
    """Use the same selected train/validation split in every pipeline stage."""
    if dataset == "domain":
        return domain
    if dataset == "hf":
        return hf
    if dataset == "mixed":
        train = [
            row
            for pair in zip_longest(domain[0], hf[0])
            for row in pair
            if row is not None
        ]
        return train, domain[1] + hf[1]
    raise ValueError("granite_dataset_unknown")


def snapshot_metadata(snapshot: Path) -> dict[str, str | None]:
    """Bind tokenizer, template and generation metadata, including absent files."""
    names = (
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "generation_config.json",
        "chat_template.jinja",
        "special_tokens_map.json",
        "vocab.json",
        "vocab.txt",
        "merges.txt",
        "tokenizer.model",
    )
    return {
        name: file_digest(snapshot / name) if (snapshot / name).is_file() else None
        for name in names
    }


def final_training_stage(run: Path) -> Path:
    """Select a completed training layout consistently for verification and eval."""
    stage = run / "train-resume"
    if not stage.exists():
        stage = run / "train-first"
    if not stage.is_dir():
        raise ValueError("granite_training_stage_missing")
    return stage


def require_qualification(receipt: dict, fingerprint: str) -> None:
    """Fail closed: no CLI switch can bypass a missing or stale smoke result."""
    required = {
        "mask",
        "updated_adapter",
        "frozen_base",
        "reload",
        "resume",
        "long_context",
        "tool_loop",
    }
    if receipt.get("status") != "PASS" or receipt.get("fingerprint") != fingerprint:
        raise ValueError("granite_smoke_required")
    checks = receipt.get("checks", {})
    if not required <= checks.keys() or any(checks[k] is not True for k in required):
        raise ValueError("granite_smoke_incomplete")
