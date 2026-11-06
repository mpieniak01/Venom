"""Measure full CPU generations before training and verify the serialized expansion."""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import time
from pathlib import Path

from venom_core.services.functiongemma.protocol import render_messages
from venom_core.services.granite_operator.contract import file_digest, write_json

from .score import score_suite
from .weights import EXPANDED_PARAMS, ORIGINAL_PARAMS, hashes


def read(path):
    return json.loads(path.read_text())


def generate(model_path, tokenizer, suites, params, *, capture_logits):
    import torch
    from transformers import AutoModelForCausalLM

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.float32,
    ).eval()
    if sum(p.numel() for p in model.parameters()) != params:
        raise ValueError("loaded parameter count differs from warm start")
    if model.get_input_embeddings().weight is not model.get_output_embeddings().weight:
        raise ValueError("input and output embeddings are no longer tied")
    stop = {
        tokenizer.eos_token_id: "eos",
        tokenizer.convert_tokens_to_ids("<end_of_turn>"): "end_of_turn",
        tokenizer.convert_tokens_to_ids(
            "<start_function_response>"
        ): "start_function_response",
    }
    if len(stop) != 3 or tokenizer.unk_token_id in stop:
        raise ValueError("native stop tokens are not available")
    raw, logits = {}, {}
    with torch.inference_mode():
        for name, cases in suites.items():
            raw[name] = {}
            for case in cases:
                record = case["record"]
                rid = record["record_id"]
                prompt = render_messages(
                    tokenizer,
                    record["messages"][:-1],
                    record["tools"],
                    add_generation_prompt=True,
                )
                encoded = tokenizer(
                    prompt, return_tensors="pt", add_special_tokens=False
                )
                length = encoded.input_ids.shape[1]
                if length + 256 > 2048:
                    raise ValueError("evaluation prompt exceeds the fixed context")
                if capture_logits:
                    logits[rid] = (
                        model(**encoded, logits_to_keep=1).logits[0, -1].clone()
                    )
                started = time.monotonic()
                generated = model.generate(
                    **encoded,
                    do_sample=False,
                    max_new_tokens=256,
                    eos_token_id=list(stop),
                    pad_token_id=tokenizer.pad_token_id,
                )
                output_ids = generated[0, length:].tolist()
                raw[name][rid] = {
                    "record_id": rid,
                    "text": tokenizer.decode(output_ids, skip_special_tokens=False),
                    "token_ids": output_ids,
                    "seconds": time.monotonic() - started,
                    "stop_reason": stop.get(output_ids[-1], "max_new_tokens")
                    if output_ids
                    else "unexpected",
                }
    del model
    gc.collect()
    return raw, logits


async def run(package, output, phase, threads, pilot_receipt):
    import torch
    from loguru import logger
    from transformers import AutoTokenizer

    logger.disable("venom_core")
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    plan_path = package / "evaluation-plan.json"
    plan_sha = file_digest(plan_path)
    plan, readiness, expansion = (
        read(package / name)
        for name in ("evaluation-plan.json", "readiness.json", "widening.json")
    )
    if phase == "development":
        receipt = read(pilot_receipt)
        if (
            receipt["status"] != "PILOT_PARITY_PASS"
            or receipt["plan_sha256"] != plan_sha
            or receipt["weights"] != expansion
        ):
            raise ValueError("development requires pilot parity with the same inputs")
    suites = {}
    for name in plan["phases"][phase]:
        source = package / "evaluation" / (name + ".json")
        if file_digest(source) != plan["suites"][name]["sha256"]:
            raise ValueError(f"unexpected suite checksum: {name}")
        suites[name] = read(source)["cases"]
    output.mkdir(mode=0o700, parents=True)
    tokenizer = AutoTokenizer.from_pretrained(
        readiness["tokenizer_snapshot"],
        local_files_only=True,
        trust_remote_code=False,
    )
    labels = [("268m", "original", ORIGINAL_PARAMS)]
    if phase == "pilot":
        labels.append(("299m", "expanded", EXPANDED_PARAMS))
    collected, statistics = [], {}
    for label, width, params in labels:
        path = package / "weights" / label
        if hashes(path) != expansion[width]:
            raise ValueError(f"warm start checksum changed: {label}")
        raw, logits = generate(
            path, tokenizer, suites, params, capture_logits=phase == "pilot"
        )
        collected.append((raw, logits))
        statistics[label] = {}
        label_output = output / label
        label_output.mkdir()
        result_hashes, case_hashes = {}, {}
        for name, cases in suites.items():
            raw_path = label_output / (name + ".jsonl")
            with raw_path.open("x", encoding="utf-8") as stream:
                for row in raw[name].values():
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            result_hashes[name] = file_digest(raw_path)
            case_hashes[name] = plan["suites"][name]["sha256"]
            report = await score_suite(cases, raw[name])
            write_json(
                label_output / (name + "-verdicts.json"),
                {
                    **report,
                    "case_sha256": case_hashes[name],
                    "raw_sha256": result_hashes[name],
                },
            )
            statistics[label][name] = report["total"]
            print(label, name, report["total"], flush=True)
        write_json(
            label_output / "summary.json",
            {
                "phase": phase,
                "binding": {"evaluation_plan_sha256": plan_sha},
                "results_sha256": result_hashes,
                "case_sha256": case_hashes,
            },
        )
    result = {
        "status": "CPU_BASELINE_COMPLETE",
        "device": "cpu",
        "dtype": "fp32",
        "plan_sha256": plan_sha,
        "weights": expansion,
        "metrics": statistics,
    }
    if phase == "pilot":
        (original, initial_logits), (expanded, final_logits) = collected
        same = {
            rid: row["token_ids"] == expanded["pilot-16"][rid]["token_ids"]
            for rid, row in original["pilot-16"].items()
        }
        diffs = {
            rid: (value - final_logits[rid]).abs().max().item()
            for rid, value in initial_logits.items()
        }
        matched = all(same.values()) and max(diffs.values()) < 1e-3
        result.update(
            status="PILOT_PARITY_PASS" if matched else "PILOT_PARITY_FAILED",
            identical_full_generations=sum(same.values()),
            cases=len(same),
            max_abs_logit_difference=max(diffs.values()),
            pairs={
                rid: {"same_tokens": eq, "logit_diff": diffs[rid]}
                for rid, eq in same.items()
            },
        )
        write_json(output / "result.json", result)
        if not matched:
            raise ValueError("serialized expansion changes pilot behavior")
    else:
        write_json(output / "result.json", result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("pilot", "development"), required=True)
    parser.add_argument("--threads", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--pilot-receipt", type=Path)
    args = parser.parse_args()
    if args.phase == "development" and args.pilot_receipt is None:
        parser.error("--pilot-receipt is required for development")
    asyncio.run(
        run(args.package, args.output, args.phase, args.threads, args.pilot_receipt)
    )


if __name__ == "__main__":
    main()
