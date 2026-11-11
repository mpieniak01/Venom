"""Generate blinded dev comparisons for the pinned Omni model and PEFT adapters."""

import json
import os
import random
import re
import sys
from collections import defaultdict
from contextlib import nullcontext
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from time import monotonic
from unittest.mock import patch

from scripts.academy.omni_pl_chat_data import read_jsonl, sha256, validate_splits
from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN, verify_snapshot
from scripts.academy.omni_pl_chat_p1 import _verify_boundary, _write_json

MAX_PROMPT_TOKENS = 4096
MAX_NEW_TOKENS = 512
GENERATION_SEED = 42
BLIND_SEED = 742
_ADAPTER_FILES = ("adapter_config.json", "adapter_model.safetensors")


def validate_dev_cases(cases: list[dict]) -> None:
    if not 1 <= len(cases) <= 512:
        raise ValueError("expected one to 512 evaluation cases")
    validate_splits(cases)
    for row in cases:
        if row["split"] != "dev":
            raise ValueError("automated evaluation accepts only the dev split")
        task = row.get("task")
        if not isinstance(task, str) or not task.strip() or task == "total":
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


def _predict(model, processor, messages: list[dict], eos: set[int]) -> dict:
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
            max_new_tokens=MAX_NEW_TOKENS,
            generation_mode="text",
            do_sample=False,
            return_dict_in_generate=True,
        )
        ids = result.sequences[0, prompt_len : int(result.sequence_lengths[0])].tolist()
        if ids and ids[-1] in eos:
            finish = "stop"
        elif len(ids) >= MAX_NEW_TOKENS:
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


def _generate(
    root: Path,
    base,
    model,
    processor,
    cases: list[dict],
    variants: list[str],
    mapping: dict[str, dict[str, str]],
) -> None:
    import torch

    backbone = import_module(type(base.model.language_model).__module__)
    eos = base.generation_config.eos_token_id or base.config.text_config.eos_token_id
    eos_ids = {eos} if isinstance(eos, int) else set(eos or ())
    eos_ids.add(base.config.text_end_token_id)
    results: dict[str, dict] = defaultdict(dict)
    with (
        (root / "raw.jsonl").open("x", encoding="utf-8") as raw,
        (root / "blind.jsonl").open("x", encoding="utf-8") as blind,
        torch.inference_mode(),
        patch.object(
            backbone, "can_use_lfm3_conv", new=lambda *_args, **_kwargs: False
        ),
    ):
        for tag in variants:
            if tag != "base":
                model.set_adapter(tag)
            with model.disable_adapter() if tag == "base" else nullcontext():
                for case in cases:
                    cid = case["record_id"]
                    label = next(
                        key for key, value in mapping[cid].items() if value == tag
                    )
                    item = _predict(model, processor, case["messages"], eos_ids)
                    raw.write(
                        json.dumps(
                            {"case": cid, "model": tag, "label": label, **item},
                            ensure_ascii=False,
                            allow_nan=False,
                        )
                        + "\n"
                    )
                    raw.flush()
                    results[cid][label] = item["response"]
                    if len(results[cid]) == len(variants):
                        blind.write(
                            json.dumps(
                                {
                                    "case": case,
                                    "answers": dict(sorted(results.pop(cid).items())),
                                },
                                ensure_ascii=False,
                                allow_nan=False,
                            )
                            + "\n"
                        )
                        blind.flush()
            print(json.dumps({"variant": tag, "cases": len(cases)}), flush=True)
        os.fsync(raw.fileno())
        os.fsync(blind.fileno())


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

    base, model, processor = _load_model(snapshot, adapters)
    _write_json(root / "unblind.json", mapping)
    _generate(root, base, model, processor, cases, variants, mapping)
    if sha256(cases_path) != cases_hash:
        raise ValueError("evaluation data changed during the run")
    _write_json(
        root / "manifest.json",
        {
            "models": {"base": {"base": True}, **adapter_info},
            "model_repo": pin["repo"],
            "revision": pin["revision"],
            "snapshot_manifest_sha256": sha256(SNAPSHOT_PIN),
            "data_sha256": cases_hash,
            "evaluated_ids": [case["record_id"] for case in cases],
            "max_prompt_tokens": MAX_PROMPT_TOKENS,
            "max_new_tokens": MAX_NEW_TOKENS,
            "seed": GENERATION_SEED,
            "blind_seed": BLIND_SEED,
            "engine": {
                name: version(name) for name in ("torch", "transformers", "peft")
            },
            "template": "vendor",
            "generation_mode": "text",
            "do_sample": False,
            "enable_thinking": False,
            "outputs": {
                name: sha256(root / name)
                for name in ("raw.jsonl", "blind.jsonl", "unblind.json")
            },
        },
    )


if __name__ == "__main__":
    main()
