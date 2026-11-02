"""Operator-started, private stdio inference bridge; never executes model tools."""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from venom_core.services.granite_operator.contract import digest, file_digest
from venom_core.services.remote_training.host import load_host
from venom_core.services.remote_training.lifecycle import (
    JobStore,
    atomic_json,
    file_lock,
)
from venom_core.services.remote_training.paths import operator_path
from venom_core.services.remote_training.verification import validate_local

MAX_LINE = 1024 * 1024


def trusted_result(host_root: Path, result: Path, expected_hash: str):
    host_root, result = operator_path(host_root), operator_path(result)
    relative = result.relative_to(host_root)
    parts = relative.parts
    if (
        len(parts) != 5
        or parts[0] != "runs"
        or parts[2] != "attempts"
        or parts[4] != "result"
        or not re.fullmatch(r"[0-9]{4,}", parts[3])
    ):
        raise ValueError("remote_inference_result_path_invalid")
    state = JobStore(host_root).attempt_status(parts[1], int(parts[3]))
    if (
        state.get("status") != "succeeded"
        or state.get("stage") != "train"
        or state.get("exit_code") != 0
        or state.get("attempt") != int(parts[3])
    ):
        raise ValueError("remote_inference_training_not_succeeded")
    status = json.loads((result / "status.json").read_text())
    if status.get("state") != "succeeded" or status.get("exit_code") != 0:
        raise ValueError("remote_inference_worker_not_succeeded")
    host = load_host(host_root)
    identity, profile = validate_local(result, host)
    if (
        not re.fullmatch(r"[a-f0-9]{64}", expected_hash)
        or file_digest(result / "adapter_model.safetensors") != expected_hash
    ):
        raise ValueError("remote_inference_adapter_mismatch")
    return host, identity, profile


def validate_request(value):
    if not isinstance(value, dict):
        raise ValueError("remote_inference_invalid_request")
    op = value.get("op")
    if not isinstance(op, str):
        raise ValueError("remote_inference_invalid_request")
    if op in {"ready", "reset_stats", "stats", "close"} and set(value) == {"op"}:
        return value
    if op != "generate" or set(value) != {"op", "messages", "tools", "arm", "seconds"}:
        raise ValueError("remote_inference_invalid_request")
    if not isinstance(value["arm"], str) or value["arm"] not in {"base", "adapter"}:
        raise ValueError("remote_inference_invalid_arm")
    seconds = value["seconds"]
    if (
        type(seconds) not in {int, float}
        or not math.isfinite(seconds)
        or not 0 < seconds <= 60
    ):
        raise ValueError("remote_inference_invalid_deadline")
    if (
        not isinstance(value["messages"], list)
        or not 1 <= len(value["messages"]) <= 128
    ):
        raise ValueError("remote_inference_invalid_messages")
    if any(
        not isinstance(row, dict)
        or row.get("role") not in {"system", "user", "assistant", "tool"}
        for row in value["messages"]
    ):
        raise ValueError("remote_inference_invalid_messages")
    if (
        not isinstance(value["tools"], list)
        or len(value["tools"]) > 32
        or any(not isinstance(row, dict) for row in value["tools"])
    ):
        raise ValueError("remote_inference_invalid_tools")
    return value


def reply(stream, result=None, *, error=None):
    value = {"ok": False, "error": error} if error else {"ok": True, "result": result}
    stream.write(json.dumps(value, allow_nan=False) + "\n")
    stream.flush()


def stats(session):
    return {
        "peak_allocated_bytes": session.torch.cuda.max_memory_allocated(),
        "peak_reserved_bytes": session.torch.cuda.max_memory_reserved(),
    }


def serve(session, identity, expected_hash, source, sink, *, generator=None):
    from scripts.granite_operator.comparison import INFERENCE, generate

    generator = generator or generate
    ready = {
        "status": "ready",
        "identity_sha256": digest(identity),
        "adapter_sha256": expected_hash,
        "inference": INFERENCE,
        "gpu": session.torch.cuda.get_device_name(0),
        "cuda": session.torch.version.cuda,
        "control": "same base with PEFT adapter disabled",
    }
    reply(sink, ready)
    while True:
        raw = source.readline(MAX_LINE + 1)
        if not raw:
            return
        if len(raw) > MAX_LINE or not raw.endswith("\n"):
            reply(sink, error="remote_inference_request_too_large")
            return
        try:
            request = validate_request(json.loads(raw))
            op = request["op"]
            if op == "close":
                reply(sink, {"status": "closed"})
                return
            if op == "ready":
                result = ready
            elif op == "reset_stats":
                session.torch.cuda.reset_peak_memory_stats()
                result = {"reset": True}
            elif op == "stats":
                result = stats(session)
            else:
                with contextlib.redirect_stdout(sys.stderr):
                    result = generator(
                        session,
                        request["messages"],
                        request["tools"],
                        request["arm"],
                        time.monotonic() + request["seconds"],
                    )
            reply(sink, result)
        except TimeoutError:
            reply(sink, error="comparison_task_deadline")
        except (ValueError, TypeError, KeyError) as error:
            code = str(error)
            if not re.fullmatch(
                r"(?:comparison|remote_inference)_[a-z0-9_]{1,100}", code
            ):
                code = "remote_inference_invalid_request"
            reply(sink, error=code)
        except Exception:
            reply(sink, error="remote_inference_generation_failed")
            raise RuntimeError("remote_inference_generation_failed") from None


def worker(request_path: Path):
    from venom_core.services.granite_operator.engine import Session, require_owner

    require_owner()
    request = json.loads(operator_path(request_path).read_text())
    host, identity, profile = trusted_result(
        Path(request["host_root"]), Path(request["result"]), request["expected_hash"]
    )
    # CUDA/model libraries may print diagnostics. Only RPC records use stdout.
    with contextlib.redirect_stdout(sys.stderr):
        session = Session(profile, Path(host["snapshot"]), Path(request["result"]))
        session.model.eval()
        session.model.requires_grad_(False)
        session.model.gradient_checkpointing_disable()
        session.torch.set_num_threads(4)
    try:
        serve(session, identity, request["expected_hash"], sys.stdin, sys.stdout)
    finally:
        if (
            file_digest(Path(request["result"]) / "adapter_model.safetensors")
            != request["expected_hash"]
        ):
            raise ValueError("remote_inference_adapter_changed")


def terminate(child):
    if child.poll() is not None:
        return
    os.killpg(child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=10)


def coordinate(args):
    from venom_core.services.granite_operator.cli import require_offline
    from venom_core.services.remote_training.remote_env import runtime_receipt
    from venom_core.services.remote_training.worker import require_interpreter
    from venom_core.services.runtime_admission import RuntimeAdmission

    host, identity, profile = trusted_result(
        args.host_root, args.result, args.expected_adapter_sha256
    )
    require_interpreter(host)
    require_offline()
    with contextlib.redirect_stdout(sys.stderr):
        if not runtime_receipt(Path(host["code_root"]))["ok"]:
            raise ValueError("remote_inference_runtime_unqualified")
    if not 1 <= args.max_seconds <= 14400:
        raise ValueError("remote_inference_session_limit_invalid")
    run_id = uuid.uuid4().hex
    directory = args.host_root / "evaluations" / run_id
    directory.mkdir(parents=True, mode=0o700)
    request_path = directory / "request.json"
    atomic_json(
        request_path,
        {
            "host_root": str(args.host_root),
            "result": str(args.result),
            "expected_hash": args.expected_adapter_sha256,
        },
    )
    child = None
    admission = RuntimeAdmission(Path(host["admission_db"]), enabled=True)
    with file_lock(args.host_root / "gpu.lock", blocking=False) as lock:
        lease = admission.acquire(
            owner="granite-training",
            run_id=run_id,
            engine="granite-training",
            model=identity["model"],
        )

        def quiescent():
            return child is None or child.poll() is not None

        try:
            with lease.operation(kind="lifecycle", confirm_quiescent=quiescent):
                env = {
                    **os.environ,
                    "PYTHONPATH": host["code_root"],
                    "VENOM_GRANITE_ADMISSION_DB": host["admission_db"],
                    "VENOM_GRANITE_RUN_ID": run_id,
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                    "TOKENIZERS_PARALLELISM": "false",
                    "REMOTE_TRAINING_GPU_LOCK_FD": str(lock),
                }
                child = subprocess.Popen(
                    [
                        "setpriv",
                        "--pdeathsig",
                        "TERM",
                        "--",
                        host["worker_python"],
                        "-m",
                        "scripts.granite_operator.remote_inference",
                        "--request",
                        str(request_path),
                    ],
                    stdin=sys.stdin,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    env=env,
                    pass_fds=(lock,),
                    start_new_session=True,
                )
                try:
                    code = child.wait(timeout=args.max_seconds)
                finally:
                    terminate(child)
                if code:
                    raise RuntimeError("remote_inference_worker_failed")
        finally:
            if quiescent():
                lease.release()
    atomic_json(
        directory / "status.json",
        {"status": "closed", "adapter_sha256": args.expected_adapter_sha256},
    )


def interrupted(_signum, _frame):
    raise InterruptedError("remote_inference_interrupted")


@contextlib.contextmanager
def termination_signals():
    signals = (signal.SIGTERM, signal.SIGHUP)
    previous = {number: signal.getsignal(number) for number in signals}
    try:
        for number in signals:
            signal.signal(number, interrupted)
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=operator_path)
    parser.add_argument("--host-root", type=operator_path)
    parser.add_argument("--result", type=operator_path)
    parser.add_argument("--expected-adapter-sha256")
    parser.add_argument("--max-seconds", type=int, default=7200)
    args = parser.parse_args(argv)
    try:
        with termination_signals():
            if args.request:
                worker(args.request)
            else:
                if (
                    args.host_root is None
                    or args.result is None
                    or not args.expected_adapter_sha256
                ):
                    raise ValueError("remote_inference_arguments_missing")
                coordinate(args)
    except Exception:
        reply(sys.stdout, error="remote_inference_session_failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
