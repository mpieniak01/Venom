"""Run inference, isolated tools and oracles together on the selected host."""

from __future__ import annotations

import importlib.metadata
import json
import os
import random
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from scripts.granite_operator.comparison_parallel import Execution, TaskScheduler
from scripts.granite_operator.comparison_support import load_frozen, summarize
from venom_core.services.granite_operator.contract import (
    digest,
    file_digest,
    write_json,
)
from venom_core.services.remote_training.host import is_gemma_model, load_host
from venom_core.services.remote_training.verification import (
    execution_backend,
    validate_local,
)


def adapter_source(request):
    root = Path(request["adapter_root"])
    host = load_host(Path(request["host_root"]))
    identity, profile = validate_local(root, host)
    expected = request["expected_adapter_sha256"]
    if file_digest(root / "adapter_model.safetensors") != expected:
        raise ValueError("comparison_adapter_changed")
    status = json.loads((root / "status.json").read_text())
    if status.get("state") != "succeeded" or status.get("exit_code") != 0:
        raise ValueError("comparison_training_not_succeeded")
    return host, identity, profile


def evaluate_trials(
    session,
    cases,
    manifest,
    request,
    output,
    *,
    rows=None,
    scheduler_factory=TaskScheduler,
):
    from scripts.granite_operator.comparison import run_case

    execution = Execution(**request["execution"])
    execution.validate()
    rows = [] if rows is None else rows
    done = {(r["case_id"], r["arm"]) for r in rows}
    expected = {(c["id"], arm) for c in cases for arm in ("base", "adapter")}
    if len(done) != len(rows) or not done <= expected:
        raise ValueError("comparison_resume_trials_invalid")
    ordered = cases.copy()
    random.Random(7441).shuffle(ordered)
    jobs = []
    for index, case in enumerate(ordered):
        arms = ("base", "adapter") if index % 2 == 0 else ("adapter", "base")
        for arm in arms:
            if (case["id"], arm) not in done:
                jobs.append(
                    (case, arm, arms[0] + "-first", 2 * index + arms.index(arm) + 1)
                )
    if execution.adaptive:
        from scripts.granite_operator.comparison_adaptive import AdaptiveScheduler

        def changed(event):
            with (output / "concurrency-decisions.jsonl").open("a") as stream:
                stream.write(json.dumps({**event, "run_id": request["run_id"]}) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

        scheduler = AdaptiveScheduler(
            session, execution, factory=scheduler_factory, changed=changed
        )
    else:
        scheduler = scheduler_factory(session, execution)
    session.torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()

    def trial(job, runner):
        case, arm, pair_order, sequence = job
        row = run_case(
            runner.trial_session,
            case,
            Path(request["cases"]).parent,
            output,
            manifest["sandbox_image"],
            request["run_id"],
            arm,
            generator=runner.generate,
            task_timeout_seconds=execution.task_seconds,
        )
        return {
            **row,
            "pair_order": pair_order,
            "trial_sequence": sequence,
            "execution_concurrency": runner.execution.concurrency,
            "execution_batch_size": runner.execution.batch_size,
        }

    def completed(row):
        with (output / "trials.jsonl").open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        rows.append(row)
        write_json(
            output / "progress.json",
            {
                "status": "RUNNING",
                "completed": len(rows),
                "total": len(expected),
                "last_case": row["case_id"],
                "last_arm": row["arm"],
                "execution": execution.validate(),
            },
        )

    scheduler.run(jobs, trial, completed)
    if len(rows) != len(expected):
        raise RuntimeError("comparison_incomplete")
    metrics = {
        **scheduler.stats,
        "wall_seconds": time.monotonic() - started,
        "peak_allocated_bytes": session.torch.cuda.max_memory_allocated(),
        "peak_reserved_bytes": session.torch.cuda.max_memory_reserved(),
        "timing_scope": "current_invocation",
        "resumed_trials": len(done),
    }
    write_json(output / ("execution-" + request["run_id"] + ".json"), metrics)
    return rows, metrics


def configure_session(session, profile, adapter_root, snapshot):
    """Preserve the sealed variant and attach its native inference protocol."""
    session.snapshot = Path(snapshot)
    if is_gemma_model(getattr(profile, "model", None)):
        from venom_core.services.gemma4_operator.profile import GemmaProfile

        document = json.loads((Path(adapter_root) / "data-manifest.json").read_text())
        session.gemma_profile = GemmaProfile(**document["model_profile"])
        session.comparison_protocol = "gemma4"


def image_preflight(profile, adapter_root, snapshot, cases, dataset):
    """Qualify every frozen image input on CPU before loading GPU weights."""
    selected = [case for case in cases if case.get("images")]
    if not selected:
        return None, {"image_cases": 0, "gpu_qualified": False}
    if not is_gemma_model(profile.model):
        raise ValueError("comparison_image_backend_unsupported")
    from scripts.granite_operator.comparison import case_messages, inference_settings
    from scripts.granite_operator.comparison_parallel import _image_payload

    probe = SimpleNamespace(profile=profile)
    configure_session(probe, profile, adapter_root, snapshot)
    settings = inference_settings(probe)
    maximum = 0
    for case in selected:
        payload = _image_payload(probe, case_messages(case, dataset), case["tools"])
        count = payload["input_ids"].shape[-1]
        if count + settings["max_new_tokens"] > settings["context"]:
            raise ValueError("comparison_context_limit")
        maximum = max(maximum, count)
    return probe.processor, {
        "image_cases": len(selected),
        "maximum_input_tokens": maximum,
        "processor": type(probe.processor).__name__,
        "gpu_qualified": False,
    }


def inference_profile(profile, precision):
    """Select evaluation precision without altering training provenance or bytes."""
    if precision not in ("trained", "nf4", "bf16"):
        raise ValueError("comparison_inference_precision_invalid")
    result = (
        replace(profile, quantization=precision) if precision != "trained" else profile
    )
    result.validate()
    return result


def warmup_session(session, cases, dataset):
    """Warm text and one frozen image equally in both arms, outside trial timing."""
    from scripts.granite_operator.comparison import case_messages, generate

    probes = [
        (
            "text",
            [
                {"role": "system", "content": cases[0]["system"]},
                {
                    "role": "user",
                    "content": "Call Finish with status success and summary ready.",
                },
            ],
            cases[0]["tools"],
        )
    ]
    image_case = next((case for case in cases if case.get("images")), None)
    if image_case is not None:
        probes.append(
            ("image_text", case_messages(image_case, dataset), image_case["tools"])
        )
    counts = {}
    for modality, messages, tools in probes:
        for arm in ("base", "adapter", "adapter", "base"):
            generate(session, messages, tools, arm, time.monotonic() + 60)
        counts[modality] = 4
    return {"generations": counts, "included_in_trial_timing": False}


def worker(request):
    from scripts.granite_operator.comparison import inference_settings

    execution = Execution(**request["execution"])
    execution.validate()
    host, portable, profile = adapter_source(request)
    session_type, owner_check, _ = execution_backend(profile.model)
    owner_check()
    evaluation_profile = inference_profile(
        profile, request.get("inference_precision", "trained")
    )
    inference = inference_settings(SimpleNamespace(profile=profile))
    if not is_gemma_model(profile.model) and profile.context != inference["context"]:
        raise ValueError("comparison_context_profile_mismatch")
    output = Path(request["output"])
    manifest, cases = load_frozen(Path(request["cases"]))
    if not cases or manifest.get("qualification", {}).get("status") != "PASS":
        raise ValueError("comparison_cases_not_qualified")
    processor, image_inputs = image_preflight(
        profile,
        request["adapter_root"],
        host["snapshot"],
        cases,
        Path(request["cases"]).parent,
    )
    identity = {
        "model": profile.model,
        "revision": profile.revision,
        "loader": profile.identity().get("loader", "AutoModelForCausalLM"),
        "gpu_required": True,
        "cpu_fallback": False,
        "model_copy_count": 1,
        "image_input_preflight": image_inputs,
        "dataset_sha256": file_digest(Path(request["cases"])),
        "adapter_sha256": request["expected_adapter_sha256"],
        "portable_identity_sha256": digest(portable),
        "host_id": host["host_id"],
        "training_precision": profile.quantization,
        "inference_precision": evaluation_profile.quantization,
        "execution": execution.validate(),
        "placement": "model_tools_and_oracle_on_one_host",
        "python_prefix": sys.prefix,
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("torch", "transformers", "peft", "bitsandbytes")
        },
        "inference": inference,
        "source_sha256": {
            p.name: file_digest(p)
            for p in [
                Path(__file__),
                Path(__file__).with_name("comparison_parallel.py"),
                Path(__file__).with_name("comparison_adaptive.py"),
                Path(__file__).with_name("comparison.py"),
                Path(__file__).with_name("comparison_support.py"),
            ]
        },
    }
    identity_path = output / "identity.json"
    if identity_path.exists() and json.loads(identity_path.read_text()) != identity:
        raise ValueError("comparison_resume_identity_changed")
    write_json(identity_path, identity)
    rows_path = output / "trials.jsonl"
    rows = (
        [json.loads(line) for line in rows_path.read_text().splitlines()]
        if rows_path.exists()
        else []
    )
    # Fail before loading CUDA when the selected host lacks the pinned sandbox.
    subprocess.run(
        ["docker", "image", "inspect", manifest["sandbox_image"]],
        check=True,
        capture_output=True,
        timeout=20,
    )
    session = session_type(
        evaluation_profile, Path(host["snapshot"]), Path(request["adapter_root"])
    )
    configure_session(session, profile, request["adapter_root"], host["snapshot"])
    if processor is not None:
        session.processor = processor
    session.model.eval()
    session.model.requires_grad_(False)
    session.model.gradient_checkpointing_disable()
    session.torch.set_num_threads(4)
    write_json(
        output / "warmup.json",
        warmup_session(session, cases, Path(request["cases"]).parent),
    )
    rows, metrics = evaluate_trials(
        session, cases, manifest, request, output, rows=rows
    )
    load_frozen(Path(request["cases"]))
    adapter_source(request)
    final = {
        **summarize(rows),
        "status": "COMPLETE",
        "case_count": len(cases),
        "execution": execution.validate(),
        "execution_metrics": metrics,
        "inference": inference,
        "qualification": "diagnostic_requires_serial_comparison",
        "placement": identity["placement"],
    }
    final["paired"]["proposed_promotion_gate_passed"] = False
    write_json(output / "summary.json", final)
    write_json(
        output / "progress.json",
        {"status": "COMPLETE", "completed": len(rows), "total": len(rows)},
    )
