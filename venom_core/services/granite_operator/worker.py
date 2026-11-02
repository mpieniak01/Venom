"""Private subprocess entry point. The application owns its runtime lease."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from .contract import (
    TrainingProfile,
    digest,
    file_digest,
    inside,
    load_dataset,
    require_qualification,
    select_dataset,
    write_json,
)
from .engine import Session, encoded_rows, environment_identity, require_owner


def smoke_subset(rows):
    """One original fixture variant per family and language, without relabeling."""
    seen = set()
    result = []
    for row in rows:
        key = (row["problem_group"], row.get("language"))
        if key not in seen:
            result.append(row)
            seen.add(key)
    return result


def tool_loop(session, row):
    """A generated call is executed only if it is the exact harmless probe."""
    from venom_core.services.maintenance_comparison.protocol import granite_calls

    tools = row["tools"]
    messages = [
        row["messages"][0],
        {
            "role": "user",
            "content": "Use Terminal to execute exactly printf 'G01_SMOKE_OK\\n'. "
            "Read its actual output, then call Finish with status success and the observed marker. "
            "This is a training pipeline smoke test; do not run any other command.",
        },
    ]
    trace = []
    observed = False
    for turn in range(4):
        ids = session.tokenizer.apply_chat_template(
            messages,
            tools=tools,
            enable_thinking=False,
            truncate_history_thinking=False,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(session.model.device)
        if hasattr(ids, "keys"):
            ids = ids["input_ids"]
        if ids.shape[-1] + 256 > session.profile.context:
            raise RuntimeError("granite_probe_context_exceeded")
        session.model.eval()
        start = time.monotonic()
        with session.torch.no_grad():
            generated = session.model.generate(
                input_ids=ids,
                attention_mask=session.torch.ones_like(ids),
                max_new_tokens=256,
                do_sample=False,
                use_cache=True,
                pad_token_id=session.tokenizer.pad_token_id,
            )
        text = session.tokenizer.decode(
            generated[0, ids.shape[-1] :], skip_special_tokens=False
        )
        calls = granite_calls(text)
        trace.append({"generated": text, "seconds": time.monotonic() - start})
        if len(calls) != 1:
            return {"passed": False, "reason": "expected_single_call", "trace": trace}
        call = calls[0]
        if call.name == "Finish":
            passed = (
                observed
                and call.arguments.get("status") == "success"
                and "G01_SMOKE_OK" in call.arguments.get("summary", "")
            )
            return {"passed": passed, "trace": trace}
        if (
            call.name != "Terminal"
            or observed
            or call.arguments != {"command": "printf 'G01_SMOKE_OK\\n'"}
        ):
            return {
                "passed": False,
                "reason": "probe_command_not_allowlisted",
                "trace": trace,
            }
        run = subprocess.run(
            ["printf", "G01_SMOKE_OK\n"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        result = {
            "stdout": run.stdout,
            "stderr": run.stderr,
            "exit_code": run.returncode,
        }
        trace[-1]["observation"] = result
        observed = run.stdout == "G01_SMOKE_OK\n"
        ident = "probe_" + str(turn)
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": ident,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "name": "Terminal",
                    "tool_call_id": ident,
                    "content": json.dumps(result),
                },
            ]
        )
    return {"passed": False, "reason": "probe_step_limit", "trace": trace}


def _training_rows(request, domain_train, domain_val, hf_train, hf_val, fingerprint):
    stage = request["stage"]
    if stage.startswith("smoke"):
        # New datasets may add families; keep the qualification workload bounded.
        train = smoke_subset(domain_train)[:32]
        validation = smoke_subset(domain_val)[:8]
        if (len(train), len(validation)) != (32, 8):
            raise ValueError("granite_smoke_sample_count")
    else:
        qualification = json.loads(Path(request["qualification"]).read_text())
        require_qualification(qualification, fingerprint)
        for name, checksum in qualification["artifacts"].items():
            artifact = inside(Path(request["qualification"]).parent, name)
            if file_digest(artifact) != checksum:
                raise ValueError("granite_qualification_artifact_changed")
        train, validation = select_dataset(
            (domain_train, domain_val), (hf_train, hf_val), request["dataset"]
        )
    return train, validation


def run(request: dict):
    require_owner()
    profile = TrainingProfile(**request["profile"])
    data_root = Path(request["data_root"])
    manifest = json.loads(Path(request["manifest"]).read_text())
    if manifest.get("context", profile.context) != profile.context:
        raise ValueError("granite_manifest_context_mismatch")
    domain_train, domain_val = load_dataset(data_root, manifest, "domain")
    hf_train, hf_val = load_dataset(data_root, manifest, "hf")
    snapshot = Path(request["snapshot"])
    output = Path(request["output"])
    output.mkdir(parents=True, exist_ok=False)
    stage = request["stage"]
    adapter = Path(request["checkpoint"]) if request.get("checkpoint") else None
    from transformers import AutoTokenizer

    if stage not in {"smoke-first", "smoke-resume", "train-first", "train-resume"}:
        raise ValueError("granite_stage_unknown")
    if snapshot.name != profile.revision:
        raise ValueError("granite_snapshot_revision_mismatch")
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
    identity = environment_identity(profile, manifest, tokenizer, snapshot)
    fingerprint = digest(identity)
    write_json(output / "identity.json", identity)
    # Validate the native mask on the complete accepted corpus before any update.
    all_encoded = encoded_rows(
        domain_train + domain_val + hf_train + hf_val, tokenizer, profile
    )
    if any(not any(x != -100 for x in row["labels"]) for row in all_encoded):
        raise RuntimeError("granite_empty_corpus_mask")
    train, validation = _training_rows(
        request, domain_train, domain_val, hf_train, hf_val, fingerprint
    )
    session = Session(profile, snapshot, adapter)
    rows = encoded_rows(train, tokenizer, profile)
    val_rows = encoded_rows(validation, tokenizer, profile)
    reload_ok = session.restore(adapter, val_rows[0], fingerprint) if adapter else False
    initial_step = session.step
    initial_validation = session.evaluate(val_rows)
    steps = request["updates"]
    if type(steps) is not int or not 1 <= steps <= 128:
        raise ValueError("granite_update_budget_invalid")
    if profile.row_order == "family_epoch_v1":
        # HF rows have a source identity even when no domain family is supplied.
        families = [row.get("family") or row.get("source_id") for row in train]
        seconds = session.train(rows, steps, families=families)
    else:
        seconds = session.train(rows, steps)
    print(
        json.dumps({"event": "remote_training_stage", "phase": "finalizing"}),
        flush=True,
    )
    validation_result = session.evaluate(val_rows)
    checks = session.checks()
    if not all(checks.values()):
        raise RuntimeError("granite_training_invariants_failed")
    checks["reload"] = reload_ok if adapter else True
    details = {}
    if stage == "smoke-resume":
        details["long_context"] = session.long_context(train[0])
        checks["long_context"] = True
        details["tool_loop"] = tool_loop(session, train[0])
        checks.update(
            {
                "reload": reload_ok,
                "resume": initial_step == 16 and session.step == 20,
                "tool_loop": details["tool_loop"]["passed"],
                "adapter_effect": not session.torch.equal(
                    session.probe(rows[0]), session.probe(rows[0], disable=True)
                ),
            }
        )
    session.save(output / "checkpoint", val_rows[0], fingerprint)
    write_json(
        output / "metrics.json",
        {
            "stage": stage,
            "fingerprint": fingerprint,
            "checks": checks,
            "initial_step": initial_step,
            "global_step": session.step,
            "training_rows": len(train),
            "validation_rows": len(validation),
            "target_tokens": session.target_tokens,
            "training_seconds": seconds,
            "load_seconds": session.load_seconds,
            "initial_validation": initial_validation,
            "validation": validation_result,
            "peak_allocated_bytes": session.torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": session.torch.cuda.max_memory_reserved(),
            "steps": session.logs,
            "details": details,
        },
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    run(json.loads(args.request.read_text()))


if __name__ == "__main__":
    main()
