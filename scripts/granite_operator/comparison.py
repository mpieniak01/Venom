"""Paired base/adapter inference on frozen local cases. Never trains or deploys."""

from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

from scripts.granite_operator.comparison_support import (
    DockerTool,
    changed,
    cleanup_owned,
    clone_fixture,
    load_frozen,
    oracle,
    snapshot,
    summarize,
)
from venom_core.services.granite_operator.contract import (
    TrainingProfile,
    digest,
    file_digest,
    final_training_stage,
    inside,
    snapshot_metadata,
    write_json,
)

INFERENCE = {
    "seed": 17,
    "context": 2048,
    "max_new_tokens": 192,
    "max_turns": 6,
    "task_deadline_seconds": 60,
    "tool_timeout_seconds": 8,
    "do_sample": False,
    "bootstrap_cluster": "family",
}


def inference_settings(session):
    """One model copy serves all queued tasks; precision comes from its recipe."""
    from venom_core.services.remote_training.host import is_gemma_model

    profile = getattr(session, "profile", None)
    if is_gemma_model(getattr(profile, "model", None)):
        return {**INFERENCE, "context": profile.context}
    return dict(INFERENCE)


def encode_prompt(session, messages, tools):
    from venom_core.services.remote_training.host import is_gemma_model

    profile = getattr(session, "profile", None)
    if is_gemma_model(getattr(profile, "model", None)):
        from venom_core.services.gemma4_operator.protocol import render_messages

        text = render_messages(
            session.tokenizer,
            messages,
            tools,
            session.gemma_profile,
        )
        return session.tokenizer(text, add_special_tokens=False)["input_ids"]
    return session.tokenizer.apply_chat_template(
        messages,
        tools=tools,
        enable_thinking=False,
        truncate_history_thinking=False,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=False,
    )


def generation_options(session):
    """Pin native tool yield/end IDs; never inherit an unbound generation default."""
    from venom_core.services.remote_training.host import is_gemma_model

    if not is_gemma_model(getattr(getattr(session, "profile", None), "model", None)):
        return {}
    cached = getattr(session, "native_stop_ids", None)
    if cached is None:
        from venom_core.services.gemma4_operator.protocol import STOP_SEQUENCES

        tokenizer = session.tokenizer
        identifiers = []
        for token in STOP_SEQUENCES:
            ident = tokenizer.convert_tokens_to_ids(token)
            if (
                type(ident) is not int
                or ident < 0
                or ident == getattr(tokenizer, "unk_token_id", None)
                or tokenizer.convert_ids_to_tokens(ident) != token
            ):
                raise ValueError("comparison_native_stop_tokens_invalid")
            identifiers.append(ident)
        cached = tuple(dict.fromkeys(identifiers))
        session.native_stop_ids = cached
    return {"eos_token_id": list(cached)}


def parse_calls(session, text, tools):
    from venom_core.services.remote_training.host import is_gemma_model

    profile = getattr(session, "profile", None)
    protocol = getattr(session, "comparison_protocol", None)
    if is_gemma_model(getattr(profile, "model", None)) or protocol == "gemma4":
        from venom_core.services.gemma4_operator.protocol import parse_response

        return parse_response(text, tools)
    from venom_core.services.maintenance_comparison.protocol import granite_calls

    return granite_calls(text)


def generate(session, messages, tools, arm, deadline):
    from scripts.granite_operator.comparison_parallel import generate_batch

    return generate_batch(session, [(messages, tools, arm, deadline)])[0]


def case_messages(case, dataset):
    images = case.get("images", [])
    content = (
        [
            {
                "type": "image",
                "path": str(inside(dataset, image["path"])),
                "sha256": image["sha256"],
            }
            for image in images
        ]
        + [{"type": "text", "text": case["prompt"]}]
        if images
        else case["prompt"]
    )
    return [
        {"role": "system", "content": case["system"]},
        {"role": "user", "content": content},
    ]


def run_case(
    session,
    case,
    dataset,
    output,
    image,
    run_id,
    arm,
    *,
    generator=None,
    task_timeout_seconds=None,
):
    Draft202012Validator = importlib.import_module("jsonschema").Draft202012Validator

    generator = generator or generate

    from venom_core.services.maintenance_comparison.protocol import ProtocolError

    image_inputs = case.get("images", [])
    if image_inputs:
        from venom_core.services.remote_training.host import is_gemma_model

        if not is_gemma_model(
            getattr(getattr(session, "profile", None), "model", None)
        ):
            raise ValueError("comparison_image_backend_unsupported")
    workspace = clone_fixture(
        dataset,
        case,
        output / "trials" / case["id"] / (arm + "-" + uuid.uuid4().hex[:8]),
    )
    before = snapshot(workspace)
    tool = None
    if not case["oracle"].get("no_terminal"):
        tool = DockerTool(workspace, image, run_id)
    messages = case_messages(case, dataset)
    schemas = {
        t["function"]["name"]: t["function"]["parameters"] for t in case["tools"]
    }
    ledger, generations, violations = [], [], []
    finish = None
    intermediate_finishes = []
    followups = case.get("followups", [])
    if (
        not isinstance(followups, list)
        or len(followups) > 4
        or any(not isinstance(x, str) or not x or len(x) > 8192 for x in followups)
    ):
        if tool:
            tool.close()
        raise ValueError("comparison_followups_invalid")
    failure = None
    queue_seconds = 0.0
    started = time.monotonic()
    deadline = started + (
        task_timeout_seconds
        if task_timeout_seconds is not None
        else INFERENCE["task_deadline_seconds"]
    )
    session.torch.cuda.reset_peak_memory_stats()
    try:
        for turn in range(INFERENCE["max_turns"]):
            try:
                generated = generator(session, messages, case["tools"], arm, deadline)
                generations.append(generated)
                wait = generated.get("queue_seconds", 0.0)
                queue_seconds += wait
                deadline += wait
                if time.monotonic() >= deadline:
                    failure = "task_timeout"
                    break
                calls = parse_calls(session, generated["text"], case["tools"])
            except TimeoutError as error:
                queue_seconds += getattr(error, "queue_seconds", 0.0)
                failure = "task_timeout"
                break
            except (ProtocolError, ValueError) as error:
                queue_seconds += getattr(error, "queue_seconds", 0.0)
                failure = str(error)
                break
            if not calls or len(calls) > 4:
                failure = "invalid_call_count"
                break
            if any(
                c.name not in schemas
                or not Draft202012Validator(schemas[c.name]).is_valid(c.arguments)
                for c in calls
            ):
                failure = "invalid_tool_or_arguments"
                break
            if any(c.name == "Finish" for c in calls):
                if len(calls) != 1:
                    failure = "finish_without_observation"
                else:
                    proposed = calls[0].arguments
                    if proposed["status"] == "needs_input" and len(
                        intermediate_finishes
                    ) < len(followups):
                        messages.append(
                            {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": f"clarification_{turn}",
                                        "type": "function",
                                        "function": {
                                            "name": "Finish",
                                            "arguments": proposed,
                                        },
                                    }
                                ],
                            }
                        )
                        messages.append(
                            {
                                "role": "user",
                                "content": followups[len(intermediate_finishes)],
                            }
                        )
                        intermediate_finishes.append(proposed)
                        continue
                    finish = proposed
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": f"eval_{turn}_{index}",
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                        for index, call in enumerate(calls)
                    ],
                }
            )
            for index, call in enumerate(calls):
                if call.name != "Terminal":
                    failure = "unknown_operation"
                    break
                command = call.arguments["command"]
                if case["oracle"].get("no_terminal"):
                    ledger.append({"command": command, "result": None})
                    failure = "unnecessary_tool"
                    break
                remaining = max(1, int(deadline - time.monotonic()))
                result = tool.execute(
                    command, min(INFERENCE["tool_timeout_seconds"], remaining)
                )
                ledger.append({"command": command, "result": result})
                violations.extend(
                    changed(
                        before,
                        snapshot(workspace),
                        case["oracle"].get("mutable_files", []),
                    )
                )
                for pattern in case["oracle"].get("forbidden_command_regexes", []):
                    import re

                    if re.search(pattern, command):
                        violations.append("forbidden_command")
                messages.append(
                    {
                        "role": "tool",
                        "name": "Terminal",
                        "tool_call_id": f"eval_{turn}_{index}",
                        "content": json.dumps(
                            {
                                key: result[key]
                                for key in ("stdout", "stderr", "exit_code")
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                if result.get("workspace_error"):
                    violations.append(result["workspace_error"])
                if result["execution_timed_out"]:
                    failure = "tool_timeout"
                    break
                if result.get("workspace_error"):
                    failure = "tool_workspace_limit"
                    break
                if result.get("execution_killed") and not result["execution_timed_out"]:
                    failure = "tool_killed"
                    break
                if result["execution_timed_out"] or result["output_truncated"]:
                    failure = (
                        "tool_timeout"
                        if result["execution_timed_out"]
                        else "tool_output_limit"
                    )
                    break
            if failure:
                break
        if finish is None and failure is None:
            failure = "turn_limit"
    finally:
        task_seconds = time.monotonic() - started
        if tool:
            tool.close()  # Stop every model-created process before the independent oracle.
    verification = None
    verify_start = time.monotonic()
    if case["oracle"].get("verify_command"):
        verifier = DockerTool(workspace, image, run_id, readonly=True)
        try:
            verification = verifier.execute(case["oracle"]["verify_command"], 10)
        finally:
            verifier.close()
    verdict = oracle(case, workspace, before, ledger, finish, violations, verification)
    expected_clarifications = case["oracle"].get("expected_clarifications")
    if (
        expected_clarifications is not None
        and len(intermediate_finishes) != expected_clarifications
    ):
        verdict["success"] = False
        verdict["errors"] = sorted(set(verdict["errors"] + ["clarification_count"]))
    if failure:
        verdict["success"] = False
        verdict["errors"] = sorted(set(verdict["errors"] + [failure]))
        verdict["success_without_oracle_confirmation"] = bool(
            finish and finish["status"] == "success"
        )
    return {
        "workspace": str(workspace.relative_to(output)),
        "case_id": case["id"],
        "problem_group": case["problem_group"],
        "family": case["family"],
        "language": case["language"],
        "arm": arm,
        "oracle": verdict,
        "finish": finish,
        "intermediate_finishes": intermediate_finishes,
        "failure": failure,
        "task_seconds": task_seconds,
        "queue_seconds": queue_seconds,
        "active_task_seconds": max(0.0, task_seconds - queue_seconds),
        "verifier_seconds": time.monotonic() - verify_start,
        "generation_seconds": sum(g["seconds"] for g in generations),
        "tool_seconds": sum(e["result"]["seconds"] for e in ledger if e["result"]),
        "generated_tokens": sum(g["tokens"] for g in generations),
        "timed_out": failure in {"task_timeout", "tool_timeout"},
        "terminal_calls": len(ledger),
        "generations": generations,
        "tools": ledger,
        "verification": verification,
        "peak_allocated_bytes": session.torch.cuda.max_memory_allocated(),
        "peak_reserved_bytes": session.torch.cuda.max_memory_reserved(),
    }


def worker(request):
    from scripts.granite_operator.comparison_parallel import Execution
    from venom_core.services.granite_operator.engine import Session, require_owner

    request.setdefault("execution", Execution().validate())
    if request.get("adapter_root"):
        from scripts.granite_operator.comparison_host import worker as host_worker

        return host_worker(request)
    require_owner()
    output = Path(request["output"])
    manifest_path = Path(request["cases"])
    manifest, cases = load_frozen(manifest_path)
    training_run = Path(request["training_run"])
    source = json.loads((training_run / "locations.json").read_text())
    receipt = json.loads((training_run / "checkpoint-verification.json").read_text())
    if receipt["status"] != "PASS":
        raise ValueError("comparison_unverified_adapter")
    checkpoint = final_training_stage(training_run) / "checkpoint"
    if (
        file_digest(checkpoint / "adapter_model.safetensors")
        != receipt["adapter_sha256"]
    ):
        raise ValueError("comparison_adapter_changed")
    saved = json.loads((checkpoint / "receipt.json").read_text())
    for name, checksum in saved["files"].items():
        if file_digest(inside(checkpoint, name)) != checksum:
            raise ValueError("comparison_checkpoint_changed")
    original = json.loads((training_run / "train-first/identity.json").read_text())
    snapshot_path = Path(source["snapshot"])
    metadata = snapshot_metadata(snapshot_path)
    if original.get("snapshot_metadata") != metadata:
        raise ValueError("comparison_snapshot_metadata_changed")
    if file_digest(snapshot_path / "config.json") != original["checkpoint_config"]:
        raise ValueError("comparison_base_config_changed")
    for name, checksum in original["weights"].items():
        if Path(name).name != name or file_digest(snapshot_path / name) != checksum:
            raise ValueError("comparison_base_weights_changed")
    if manifest.get("qualification", {}).get("status") != "PASS":
        raise ValueError("comparison_cases_not_qualified")
    profile = TrainingProfile(**source["profile"])
    if profile.context != INFERENCE["context"]:
        raise ValueError("comparison_context_profile_mismatch")
    session = Session(profile, Path(source["snapshot"]), checkpoint)
    session.model.eval()
    session.model.requires_grad_(False)
    session.model.gradient_checkpointing_disable()
    session.torch.set_num_threads(4)
    identity = {
        "dataset_sha256": file_digest(manifest_path),
        "inference": INFERENCE,
        "execution": request["execution"],
        "adapter_sha256": receipt["adapter_sha256"],
        "profile": profile.identity(),
        "base_snapshot": source["snapshot"],
        "snapshot_metadata": metadata,
        "tokenizer_template": digest(session.tokenizer.chat_template),
        "control": "same base with PEFT adapter disabled",
        "source_sha256": {
            p.name: file_digest(p)
            for p in [
                Path(__file__),
                Path(__file__).with_name("comparison_support.py"),
                Path(__file__).with_name("comparison_parallel.py"),
                Path(__file__).with_name("comparison_adaptive.py"),
                Path(__file__).with_name("comparison_host.py"),
                Path(__file__).resolve().parents[2]
                / "venom_core/services/granite_operator/engine.py",
                Path(__file__).resolve().parents[2]
                / "venom_core/services/maintenance_comparison/protocol.py",
            ]
        },
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("torch", "transformers", "peft", "bitsandbytes")
        },
        "python_prefix": __import__("sys").prefix,
        "gpu": session.torch.cuda.get_device_name(0),
        "cuda": session.torch.version.cuda,
        "image": manifest["sandbox_image"],
        "load_seconds": session.load_seconds,
    }
    identity_path = output / "identity.json"
    if identity_path.exists():
        previous = json.loads(identity_path.read_text())
        if {k: v for k, v in previous.items() if k != "load_seconds"} != {
            k: v for k, v in identity.items() if k != "load_seconds"
        }:
            raise ValueError("comparison_resume_identity_changed")
    else:
        write_json(identity_path, identity)
    # Independent warmup; never uses held-out cases or their answers.
    for arm in ("base", "adapter", "adapter", "base"):
        generate(
            session,
            [
                {"role": "system", "content": cases[0]["system"]},
                {
                    "role": "user",
                    "content": "Call Finish with status success and summary ready.",
                },
            ],
            cases[0]["tools"],
            arm,
            time.monotonic() + 30,
        )
    probe = session.tokenizer.apply_chat_template(
        [
            {"role": "system", "content": cases[0]["system"]},
            {
                "role": "user",
                "content": "Call Finish with status success and summary ready.",
            },
        ],
        tools=cases[0]["tools"],
        enable_thinking=False,
        truncate_history_thinking=False,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    ).to("cuda")
    with session.torch.inference_mode():
        enabled = session.model(
            **probe, use_cache=False, logits_to_keep=1
        ).logits.float()
        with session.model.disable_adapter():
            disabled = session.model(
                **probe, use_cache=False, logits_to_keep=1
            ).logits.float()
        delta = float((enabled - disabled).abs().max())
    if not __import__("math").isfinite(delta) or delta <= 0:
        raise RuntimeError("comparison_adapter_has_no_logit_effect")
    write_json(
        output / ("adapter-effect-" + request["run_id"] + ".json"),
        {
            "status": "PASS",
            "maximum_absolute_logit_delta": delta,
            "adapter_sha256": receipt["adapter_sha256"],
        },
    )
    del enabled, disabled, probe
    rows_path = output / "trials.jsonl"
    rows = (
        [json.loads(line) for line in rows_path.read_text().splitlines()]
        if rows_path.exists()
        else []
    )
    from scripts.granite_operator.comparison_host import evaluate_trials

    rows, execution_metrics = evaluate_trials(
        session, cases, manifest, request, output, rows=rows
    )
    load_frozen(manifest_path)
    if len(rows) != len(cases) * 2:
        raise RuntimeError("comparison_incomplete")
    if (
        file_digest(checkpoint / "adapter_model.safetensors")
        != receipt["adapter_sha256"]
    ):
        raise RuntimeError("comparison_adapter_file_changed_during_run")
    final = summarize(rows)
    final.update(
        {
            "status": "COMPLETE",
            "case_count": len(cases),
            "inference": INFERENCE,
            "dataset_sha256": file_digest(manifest_path),
            "execution": request["execution"],
            "execution_metrics": execution_metrics,
            "qualification": "diagnostic_requires_serial_comparison",
        }
    )
    final["paired"]["proposed_promotion_gate_passed"] = False
    write_json(output / "summary.json", final)
    write_json(
        output / "progress.json",
        {"status": "COMPLETE", "completed": len(rows), "total": len(rows)},
    )


def coordinate(args):
    from scripts.granite_operator.comparison_parallel import execution_from_args
    from venom_core.services.granite_operator.cli import require_offline

    execution = execution_from_args(args)
    precision = getattr(args, "inference_precision", "trained")
    if precision != "trained" and not args.adapter_root:
        raise ValueError("comparison_precision_override_requires_adapter_root")
    if args.adapter_root:
        from scripts.granite_operator.comparison_host import adapter_source

        host, _, selected_profile = adapter_source(
            {
                "adapter_root": str(args.adapter_root),
                "host_root": str(args.host_root),
                "expected_adapter_sha256": args.expected_adapter_sha256,
                "inference_precision": precision,
            }
        )
        args.selected_model = getattr(
            selected_profile, "model", "ibm-granite/granite-4.2-3b"
        )
        args.worker_python = Path(host["worker_python"])
        args.admission_db = Path(host["admission_db"])
    require_offline()
    load_frozen(args.cases)
    args.output.mkdir(parents=True, exist_ok=args.resume)
    (args.output / ".gitignore").write_text("*\n")
    if not args.resume and (args.output / "identity.json").exists():
        raise ValueError("comparison_output_exists")
    run_id = uuid.uuid4().hex
    request = {
        key: str(value.absolute())
        for key, value in vars(args).items()
        if isinstance(value, Path)
    }
    request.update(
        {
            "run_id": run_id,
            "resume": args.resume,
            "execution": execution.validate(),
            "expected_adapter_sha256": args.expected_adapter_sha256,
            "inference_precision": precision,
        }
    )
    request_path = args.output / ("request-" + run_id + ".json")
    write_json(request_path, request)
    with contextlib.ExitStack() as guards:
        if args.adapter_root:
            from venom_core.services.remote_training.lifecycle import file_lock

            guards.enter_context(file_lock(args.host_root / "gpu.lock", blocking=False))
        return _coordinate_reserved(args, execution, run_id, request_path)


def _coordinate_reserved(args, execution, run_id, request_path):
    from venom_core.services.remote_training.verification import execution_backend
    from venom_core.services.runtime_admission import RuntimeAdmission

    model = getattr(args, "selected_model", "ibm-granite/granite-4.2-3b")
    _, _, engine = execution_backend(model)
    lease = RuntimeAdmission(args.admission_db, enabled=True).acquire(
        owner=engine,
        run_id=run_id,
        engine=engine,
        model=model,
    )
    child = None
    containers_clean = False

    def quiescent():
        return (child is None or child.poll() is not None) and containers_clean

    try:
        with lease.operation(kind="lifecycle", confirm_quiescent=quiescent):
            try:
                environment = {
                    **os.environ,
                    "VENOM_GRANITE_ADMISSION_DB": str(args.admission_db.resolve()),
                    "VENOM_GRANITE_RUN_ID": run_id,
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                    "TOKENIZERS_PARALLELISM": "false",
                    "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                }
                with (args.output / ("worker-" + run_id + ".log")).open("x") as log:
                    child = subprocess.Popen(
                        [
                            "setpriv",
                            "--pdeathsig",
                            "TERM",
                            "--",
                            str(args.worker_python.absolute()),
                            "-m",
                            "scripts.granite_operator.comparison",
                            "--request",
                            str(request_path),
                        ],
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    try:
                        code = child.wait(timeout=execution.max_seconds)
                    except BaseException:
                        from scripts.granite_operator.remote_inference import terminate

                        terminate(child)
                        raise
                if code:
                    raise RuntimeError("comparison_worker_failed:" + str(code))
            finally:
                containers_clean = cleanup_owned(run_id)
                if not containers_clean:
                    raise RuntimeError("comparison_cleanup_failed")
        write_json(args.output / "status.json", {"status": "PASS", "run_id": run_id})
    except BaseException as error:
        write_json(
            args.output / "status.json",
            {"status": "FAIL", "error": str(error), "run_id": run_id},
        )
        raise
    finally:
        if quiescent():
            lease.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path)
    for name in ("cases", "training-run", "output", "worker-python", "admission-db"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--adapter-root", type=Path)
    parser.add_argument("--host-root", type=Path)
    parser.add_argument("--expected-adapter-sha256")
    parser.add_argument(
        "--inference-precision", choices=("trained", "nf4", "bf16"), default="trained"
    )
    from scripts.granite_operator.comparison_parallel import execution_options

    execution_options(parser)
    args = parser.parse_args()
    if args.request:
        worker(json.loads(args.request.read_text()))
    else:
        imported = args.adapter_root is not None
        required = ("cases", "output") + (
            ("host_root", "expected_adapter_sha256")
            if imported
            else ("training_run", "worker_python", "admission_db")
        )
        if imported and args.training_run:
            parser.error("choose adapter-root or training-run")
        if any(getattr(args, name) is None for name in required):
            parser.error(
                "cases, training-run, output, worker-python and admission-db are required"
            )
        from scripts.granite_operator.remote_inference import termination_signals

        with termination_signals():
            coordinate(args)


if __name__ == "__main__":
    main()
