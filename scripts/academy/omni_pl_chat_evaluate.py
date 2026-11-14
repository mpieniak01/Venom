"""Generate blinded dev comparisons for the pinned Omni model and PEFT adapters."""

import hashlib
import json
import os
import random
import re
import sys
from contextlib import nullcontext
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest.mock import patch

from scripts.academy.omni_pl_chat_data import (
    MAX_DEV_TASK_LENGTH,
    read_jsonl,
    sha256,
    validate_splits,
    write_jsonl,
)
from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN, verify_snapshot
from scripts.academy.omni_pl_chat_p1 import _verify_boundary, _write_json

MAX_PROMPT_TOKENS = 4096
MAX_NEW_TOKENS = 512
GENERATION_SEED = 42
BLIND_SEED = 742
_ADAPTER_FILES = ("adapter_config.json", "adapter_model.safetensors")
_PROGRESS = Path("/progress")
_MAX_RECEIPT_BYTES = 256 * 1024


def validate_dev_cases(cases: list[dict]) -> None:
    if not 1 <= len(cases) <= 512:
        raise ValueError("expected one to 512 evaluation cases")
    validate_splits(cases)
    for row in cases:
        limit = row.get("max_new_tokens", MAX_NEW_TOKENS)
        if type(limit) is not int or not 1 <= limit <= MAX_NEW_TOKENS:
            raise ValueError("case generation limit must be between 1 and 512")
        if row["split"] != "dev":
            raise ValueError("automated evaluation accepts only the dev split")
        task = row.get("task")
        if (
            not isinstance(task, str)
            or not task.strip()
            or task == "total"
            or len(task) > MAX_DEV_TASK_LENGTH
        ):
            raise ValueError("evaluation case requires a task name")
        criteria = row.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise ValueError("evaluation case requires rubric criteria")
        seen = set()
        has_content = False
        for item in criteria:
            if not isinstance(item, dict):
                raise ValueError("rubric criteria must be objects")
            key, kind, description = (
                item.get(name) for name in ("id", "kind", "description")
            )
            if (
                not isinstance(key, str)
                or not key.strip()
                or key in seen
                or kind not in ("content", "format")
                or not isinstance(description, str)
                or not description.strip()
            ):
                raise ValueError("evaluation case contains an invalid rubric criterion")
            seen.add(key)
            has_content |= kind == "content"
        if not has_content:
            raise ValueError("rubric requires a content criterion")


def blind_mapping(cases: list[dict], variants: list[str]) -> dict[str, dict[str, str]]:
    if (
        not 2 <= len(variants) <= 5
        or len(set(variants)) != len(variants)
        or "base" not in variants
        or any(
            tag != "base" and not re.fullmatch(r"checkpoint-[1-9][0-9]{0,4}", tag)
            for tag in variants
        )
    ):
        raise ValueError("supply the base and one to four distinct checkpoint labels")
    rng = random.Random(BLIND_SEED)  # nosec B311: reproducible, non-security ordering
    labels = list("ABCDE"[: len(variants)])
    return {
        case["record_id"]: dict(
            zip(rng.sample(labels, len(labels)), variants, strict=True)
        )
        for case in cases
    }


def verify_adapter(path: Path) -> dict[str, str]:
    receipt = path / "hashes.json"
    files = {name: path / name for name in _ADAPTER_FILES}
    if path.is_symlink() or not path.is_dir():
        raise ValueError("adapter must be a real checkpoint directory")
    if any(
        file.is_symlink() or not file.is_file() for file in (receipt, *files.values())
    ):
        raise ValueError("adapter is missing weights, config, or hash receipt")
    if receipt.stat().st_size > 16 * 1024:
        raise ValueError("adapter hash receipt exceeds the size limit")
    expected = json.loads(receipt.read_text(encoding="utf-8"))
    hashes = {name: sha256(file) for name, file in files.items()}
    if not isinstance(expected, dict) or any(
        expected.get(name) != digest for name, digest in hashes.items()
    ):
        raise ValueError("adapter differs from the saved receipt")
    return hashes


def _predict(
    model,
    processor,
    messages: list[dict],
    eos: set[int],
    *,
    max_new_tokens: int = MAX_NEW_TOKENS,
) -> dict:
    started = monotonic()
    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
        add_generation_prompt=True,
        enable_thinking=False,
    )
    prompt_len = inputs["input_ids"].shape[1]
    if prompt_len > MAX_PROMPT_TOKENS:
        response = {"text": "", "finish": "error", "error": "prompt_too_long"}
        ids = []
    else:
        result = model.generate(
            **inputs.to("cuda"),
            max_new_tokens=max_new_tokens,
            generation_mode="text",
            do_sample=False,
            return_dict_in_generate=True,
        )
        ids = result.sequences[0, prompt_len : int(result.sequence_lengths[0])].tolist()
        if ids and ids[-1] in eos:
            finish = "stop"
        elif len(ids) >= max_new_tokens:
            finish = "length"
        else:
            finish = "unexpected_stop"
        response = {
            "text": processor.tokenizer.decode(ids, skip_special_tokens=True).strip(),
            "finish": finish,
            "error": None if finish != "unexpected_stop" else finish,
        }
    return {
        "prompt_tokens": prompt_len,
        "output_tokens": len(ids),
        "elapsed_seconds": round(monotonic() - started, 3),
        "generated_ids": ids,
        "response": response,
    }


def _load_model(snapshot: Path, adapters: dict[str, Path]):
    import torch
    from peft import PeftModel
    from transformers import AutoModelForMultimodalLM, AutoProcessor

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("Omni evaluation requires a CUDA device with BF16 support")
    free, total = torch.cuda.mem_get_info()
    mib = 2**20
    if free < 6500 * mib:
        raise RuntimeError(f"only {free // mib} MiB free on the GPU")
    torch.cuda.set_per_process_memory_fraction(min(1.0, (free - 1000 * mib) / total))
    torch.manual_seed(GENERATION_SEED)
    processor = AutoProcessor.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=True
    )
    base = AutoModelForMultimodalLM.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=True,
        dtype=torch.bfloat16,
        device_map="cuda",
    ).eval()
    base.generation_config.temperature = None
    base.generation_config.top_k = None
    entries = iter(adapters.items())
    tag, checkpoint = next(entries)
    model = PeftModel.from_pretrained(
        base, checkpoint, adapter_name=tag, is_trainable=False
    ).eval()
    for tag, checkpoint in entries:
        model.load_adapter(checkpoint, adapter_name=tag, is_trainable=False)
    return base, model, processor


def _hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


class GenerationProgress:
    """Persist verified individual generations before publishing a review bundle."""

    def __init__(self, root: Path, identity: dict, mapping: dict[str, dict[str, str]]):
        self.identity = _hash(identity)
        self.directory = root / self.identity
        self.directory.mkdir(mode=0o700, exist_ok=True)
        if self.directory.is_symlink():
            raise ValueError("evaluation progress directory cannot be a symlink")
        self.labels = {
            (case, tag): label
            for case, entries in mapping.items()
            for label, tag in entries.items()
        }
        self.rows = {}
        for key in self.labels:
            stored = self._read(key)
            if stored is not None:
                self.rows[key] = stored
        self.reused = len(self.rows)

    def _path(self, key: tuple[str, str]) -> Path:
        return self.directory / f"{_hash(key)}.json"

    def _read(self, key: tuple[str, str]) -> dict | None:
        path = self._path(key)
        if path.is_symlink():
            raise ValueError("evaluation progress receipt cannot be a symlink")
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_size > _MAX_RECEIPT_BYTES:
            raise ValueError("invalid evaluation progress receipt")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(row := data.get("row"), dict):
            raise ValueError("invalid evaluation progress receipt")
        if (
            data.get("sha256") != _hash([self.identity, row])
            or (row.get("case"), row.get("model")) != key
            or row.get("label") != self.labels[key]
        ):
            raise ValueError("evaluation progress receipt differs from its seal")
        return row

    def save(self, key: tuple[str, str], item: dict) -> None:
        case, tag = key
        row = {**item, "case": case, "model": tag, "label": self.labels[key]}
        _write_json(
            self._path(key), {"row": row, "sha256": _hash([self.identity, row])}
        )
        self.rows[key] = row

    def missing(self, cases: list[dict], tag: str) -> list[dict]:
        return [case for case in cases if (case["record_id"], tag) not in self.rows]

    def publish(self, root: Path, cases: list[dict], variants: list[str]) -> None:
        # Check completeness before publishing any review files.
        raw = [self.rows[case["record_id"], tag] for tag in variants for case in cases]
        blind = []
        for case in cases:
            answers = {
                self.labels[case["record_id"], tag]: self.rows[case["record_id"], tag][
                    "response"
                ]
                for tag in variants
            }
            blind.append({"case": case, "answers": dict(sorted(answers.items()))})
        for filename, rows in (("raw.jsonl", raw), ("blind.jsonl", blind)):
            path = root / filename
            write_jsonl(path, rows)
            with path.open("rb") as stream:
                os.fsync(stream.fileno())


def _generate(
    progress: GenerationProgress,
    base,
    model,
    processor,
    cases: list[dict],
    variants: list[str],
) -> None:
    import torch

    backbone = import_module(type(base.model.language_model).__module__)
    eos = base.generation_config.eos_token_id or base.config.text_config.eos_token_id
    eos_ids = {eos} if isinstance(eos, int) else set(eos or ())
    eos_ids.add(base.config.text_end_token_id)
    with (
        torch.inference_mode(),
        patch.object(
            backbone, "can_use_lfm3_conv", new=lambda *_args, **_kwargs: False
        ),
    ):
        for tag in variants:
            missing = progress.missing(cases, tag)
            if not missing:
                continue
            if tag != "base":
                model.set_adapter(tag)
            with model.disable_adapter() if tag == "base" else nullcontext():
                for case in missing:
                    item = _predict(
                        model,
                        processor,
                        case["messages"],
                        eos_ids,
                        max_new_tokens=case.get("max_new_tokens", MAX_NEW_TOKENS),
                    )
                    progress.save((case["record_id"], tag), item)
            print(json.dumps({"variant": tag, "cases": len(missing)}), flush=True)


def _evaluation_manifest(
    pin: dict, cases_hash: str, cases: list[dict], adapter_info: dict
) -> dict:
    return {
        "models": {"base": {"base": True}, **adapter_info},
        "model_repo": pin["repo"],
        "revision": pin["revision"],
        "snapshot_manifest_sha256": sha256(SNAPSHOT_PIN),
        "data_sha256": cases_hash,
        "evaluated_ids": [case["record_id"] for case in cases],
        "max_prompt_tokens": MAX_PROMPT_TOKENS,
        "max_new_tokens": MAX_NEW_TOKENS,
        "case_max_new_tokens": {
            case["record_id"]: case.get("max_new_tokens", MAX_NEW_TOKENS)
            for case in cases
        },
        "seed": GENERATION_SEED,
        "blind_seed": BLIND_SEED,
        "engine": {name: version(name) for name in ("torch", "transformers", "peft")},
        "template": "vendor",
        "generation_mode": "text",
        "do_sample": False,
        "enable_thinking": False,
    }


def main() -> None:
    _verify_boundary()
    variants = sys.argv[1:]
    snapshot = Path("/inputs/model")
    cases_path = Path("/inputs/train.jsonl")
    root = Path("/out")
    pin = verify_snapshot(snapshot, full=True)
    cases_hash = sha256(cases_path)
    cases = read_jsonl(cases_path)
    validate_dev_cases(cases)
    mapping = blind_mapping(cases, variants)
    adapters = {
        tag: Path("/inputs/adapters") / tag for tag in variants if tag != "base"
    }
    for checkpoint in adapters.values():
        if not os.statvfs(checkpoint).f_flag & os.ST_RDONLY:
            raise ValueError("adapter mount must be read-only")
    adapter_info = {
        tag: verify_adapter(checkpoint) for tag, checkpoint in adapters.items()
    }

    import torch

    manifest = _evaluation_manifest(pin, cases_hash, cases, adapter_info)
    identity = {
        **manifest,
        "python": sys.version,
        "evaluator_files": {
            name: sha256(Path(__file__).with_name(name))
            for name in (
                "omni_pl_chat_evaluate.py",
                "omni_pl_chat_data.py",
                "omni_pl_chat_masks.py",
                "omni_pl_chat_p1.py",
                "omni_pl_chat_recipe.py",
                "omni_pl_chat_adapter.py",
            )
        },
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(),
        "gpu_capability": torch.cuda.get_device_capability(),
        "variants": variants,
    }
    shared = _PROGRESS.is_dir()
    with (
        TemporaryDirectory(dir=root)
        if not shared
        else nullcontext(_PROGRESS) as checkpoint_dir
    ):
        progress = GenerationProgress(Path(checkpoint_dir), identity, mapping)
        if any(progress.missing(cases, tag) for tag in variants):
            base, model, processor = _load_model(snapshot, adapters)
            _generate(progress, base, model, processor, cases, variants)
        if sha256(cases_path) != cases_hash:
            raise ValueError("evaluation data changed during the run")
        progress.publish(root, cases, variants)
    _write_json(root / "unblind.json", mapping)
    _write_json(
        root / "manifest.json",
        {
            **manifest,
            "resumed_generations": progress.reused,
            "generation_identity_sha256": progress.identity,
            "outputs": {
                name: sha256(root / name)
                for name in ("raw.jsonl", "blind.jsonl", "unblind.json")
            },
        },
    )


if __name__ == "__main__":
    main()
