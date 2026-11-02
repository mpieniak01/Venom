"""Detached Granite coordinator; each model stage runs in a fresh child."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from venom_core.services.granite_operator.cli import qualification, require_offline
from venom_core.services.granite_operator.contract import (
    file_digest,
    inside,
    require_qualification,
    write_json,
)

from .bundles import validate_identity
from .host import binding, load_host
from .paths import operator_path
from .worker_support import normalized, preflight


def require_interpreter(host: dict) -> None:
    """Model execution uses the ABI-qualified environment, not the SSH runtime."""
    if (
        sys.version_info[:3] != (3, 14, 8)
        or Path(sys.executable).absolute() != Path(host["worker_python"]).absolute()
    ):
        raise ValueError("remote_training_requires_qualified_py314_worker_interpreter")


def interrupted(_signum, _frame):
    """Unwind and reap workers before releasing the host ledger."""
    raise InterruptedError("remote_training_stop_requested")


def _relay_available(stream) -> None:
    """Relay a finite snapshot of the stage log into the supervisor stream."""
    remaining = os.fstat(stream.fileno()).st_size - stream.tell()
    while remaining > 0:
        data = stream.read(min(65536, remaining))
        if not data:
            break
        sys.stdout.write(data.decode(errors="replace"))
        sys.stdout.flush()
        remaining -= len(data)


def _wait_stage(child, timeout, log_path, offset):
    deadline = time.monotonic() + timeout
    with log_path.open("rb") as stream:
        stream.seek(offset)
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(child.args, timeout)
                try:
                    return child.wait(timeout=min(0.2, remaining))
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= deadline:
                        raise
                finally:
                    _relay_available(stream)
        except BaseException:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)
            raise
        finally:
            _relay_available(stream)


def run_stage(host, request, result, *, run_id, timeout, children):
    """Fixed reviewed worker only; retain the GPU lease fd in all descendants."""
    name = request["stage"]
    path = result / (name + ".request.json")
    write_json(path, request)
    environment = {
        **os.environ,
        "VENOM_GRANITE_ADMISSION_DB": host["admission_db"],
        "VENOM_GRANITE_RUN_ID": run_id,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "PYTHONPATH": host["code_root"],
    }
    lock_fd = int(os.environ["REMOTE_TRAINING_GPU_LOCK_FD"])
    argv = [
        "setpriv",
        "--pdeathsig",
        "TERM",
        "--",
        host["worker_python"],
        "-m",
        "venom_core.services.granite_operator.worker",
        str(path),
    ]
    log_path = result / "logs/training.log"
    with log_path.open("ab") as log:
        offset = log.tell()
        child = subprocess.Popen(
            argv,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            pass_fds=(lock_fd,),
        )
        children.append(child)
        code = _wait_stage(child, timeout, log_path, offset)
    if code:
        raise RuntimeError("remote_training_stage_failed:" + name)
    return json.loads((Path(request["output"]) / "metrics.json").read_text())


def proof_for(run_root: Path, host: dict, identity: dict) -> Path:
    """Reuse only this run's still-valid native smoke artifacts on this host."""
    proof = json.loads((run_root / "qualification-proof.json").read_text())
    if proof["binding"] != binding(host, identity):
        raise ValueError("remote_training_new_host_qualification_required")
    path = inside(run_root, proof["qualification"])
    receipt = json.loads(path.read_text())
    if (
        json.loads((path.parent / "status.json").read_text()).get("state")
        != "succeeded"
    ):
        raise ValueError("remote_training_qualification_attempt_failed")
    require_qualification(receipt, receipt.get("fingerprint"))
    for name, checksum in receipt["artifacts"].items():
        if file_digest(inside(path.parent, name)) != checksum:
            raise ValueError("remote_training_qualification_changed")
    return path


def execute(request: dict) -> dict:
    """Qualification, controlled updates and resume preserve the native G01 contract."""
    host_root = operator_path(request["host_root"])
    run_root = operator_path(request["run_root"])
    attempt = operator_path(request["attempt_root"])
    if not run_root.is_relative_to(host_root / "runs") or not attempt.is_relative_to(
        run_root / "attempts"
    ):
        raise ValueError("remote_training_request_paths_invalid")
    host = load_host(host_root)
    result = attempt / "result"
    result.mkdir(mode=0o700)
    (result / "logs").mkdir()
    identity = request["manifest"]["identity"]
    validate_identity(identity)
    run_id = request["run_id"]
    write_json(result / "identity.json", identity)
    write_json(
        result / "status.json", {"state": "failed", "run_id": run_id, "exit_code": 1}
    )
    started = time.monotonic()
    children: list[subprocess.Popen] = []
    lease = None
    try:
        require_interpreter(host)
        require_offline()
        if shutil.disk_usage(result).free < 10 * 1024**3:
            raise ValueError("remote_training_free_disk_insufficient")
        from .remote_env import runtime_receipt

        environment_check = runtime_receipt(Path(host["code_root"]))
        if not environment_check["ok"]:
            write_json(result / "environment.json", environment_check)
            raise ValueError("remote_training_environment_unqualified")
        input_root = run_root / "input"
        manifest = json.loads((input_root / ".bundle-manifest.json").read_text())
        if manifest != request["manifest"]:
            raise ValueError("remote_training_input_changed")
        from .bundles import verify_directory

        verify_directory(input_root, manifest)
        profile, document = preflight(host, input_root, identity)
        for name, value in [
            ("profile.json", profile.identity()),
            ("data-manifest.json", document),
        ]:
            write_json(result / name, value)
        fingerprint = binding(host, identity)
        write_json(
            result / "environment.json",
            {
                "host_binding": fingerprint,
                "host_id": host["host_id"],
                "python": sys.version,
                "qualified": False,
            },
        )
        stage = request["stage"]
        qualified = None if stage == "smoke" else proof_for(run_root, host, identity)
        timeout = request["timeout_seconds"]
        if timeout > identity["limits"]["max_seconds"]:
            raise ValueError("remote_training_time_budget_invalid")
        from venom_core.services.runtime_admission import RuntimeAdmission

        lease = RuntimeAdmission(Path(host["admission_db"]), enabled=True).acquire(
            owner="granite-training",
            run_id=run_id,
            engine="granite-training",
            model=profile.model,
        )
        with lease.operation(
            kind="lifecycle",
            confirm_quiescent=lambda: all(
                child.poll() is not None for child in children
            ),
        ):

            def stage_call(name, updates, checkpoint=None):
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError("remote_training_budget_exhausted")
                body = {
                    "stage": name,
                    "updates": updates,
                    "checkpoint": str(checkpoint) if checkpoint else None,
                    "profile": profile.identity(),
                    "data_root": str(input_root),
                    "manifest": str(input_root / "data-manifest.json"),
                    "snapshot": host["snapshot"],
                    "output": str(result / "stages" / name),
                    "dataset": identity["dataset"],
                    "qualification": str(qualified) if qualified else None,
                }
                return run_stage(
                    host,
                    body,
                    result,
                    run_id=run_id,
                    timeout=remaining,
                    children=children,
                )

            if stage == "smoke":
                checkpoint = request.get("checkpoint")
                if checkpoint:
                    previous = inside(
                        run_root, str(Path(checkpoint) / "receipt.json")
                    ).parent
                    step = json.loads((previous / "receipt.json").read_text())["step"]
                    if step != 16 or previous.parent.name != "smoke-first":
                        raise ValueError(
                            "remote_training_smoke_resume_requires_first_checkpoint"
                        )
                    first = json.loads((previous.parent / "metrics.json").read_text())
                    (result / "stages").mkdir(exist_ok=True)
                    shutil.copytree(previous.parent, result / "stages/smoke-first")
                else:
                    first = stage_call("smoke-first", 16)
                final = stage_call(
                    "smoke-resume", 4, result / "stages/smoke-first/checkpoint"
                )
                hashes = {
                    str(path.relative_to(result)): file_digest(path)
                    for path in (result / "stages").rglob("*")
                    if path.is_file()
                }
                receipt = qualification(final, first, hashes)
                write_json(result / "qualification.json", receipt)
                require_qualification(receipt, final["fingerprint"])
                qualified = result / "qualification.json"
                write_json(
                    run_root / "qualification-proof.json",
                    {
                        "binding": fingerprint,
                        "qualification": str(qualified.relative_to(run_root)),
                    },
                )
                last_stage = result / "stages/smoke-resume"
            else:
                updates = identity["limits"]["max_updates"]
                if type(updates) is not int or not 1 <= updates <= 128:
                    raise ValueError("remote_training_update_budget_invalid")
                checkpoint = request.get("checkpoint")
                if checkpoint:
                    checkpoint = inside(
                        run_root, str(Path(checkpoint) / "receipt.json")
                    ).parent
                    steps = json.loads((checkpoint / "receipt.json").read_text())[
                        "step"
                    ]
                    remaining = updates - steps
                    if remaining <= 0:
                        raise ValueError("remote_training_checkpoint_budget_exhausted")
                    final = stage_call("train-resume", remaining, checkpoint)
                    last_stage = result / "stages/train-resume"
                else:
                    count = min(12, updates)
                    final = stage_call("train-first", count)
                    last_stage = result / "stages/train-first"
                    if updates > count:
                        final = stage_call(
                            "train-resume", updates - count, last_stage / "checkpoint"
                        )
                        last_stage = result / "stages/train-resume"
                if qualified is None:
                    raise ValueError("remote_training_smoke_required")
                shutil.copyfile(qualified, result / "qualification.json")
        environment = json.loads((last_stage / "identity.json").read_text())
        environment.update(
            host_binding=fingerprint, host_id=host["host_id"], qualified=True
        )
        final["wall_seconds"] = time.monotonic() - started
        final["cost"] = {"status": "not_measured", "source": None, "period": None}
        normalized(
            result,
            last_stage,
            identity,
            profile.identity(),
            document,
            final,
            environment,
            run_id=run_id,
        )
        return {"status": "PASS", "result": str(result)}
    except BaseException as exc:
        write_json(
            result / "status.json",
            {
                "state": "stopped" if isinstance(exc, InterruptedError) else "failed",
                "run_id": run_id,
                "exit_code": 1,
                "error_type": type(exc).__name__,
            },
        )
        raise
    finally:
        if lease and all(child.poll() is not None for child in children):
            lease.release()


def main():
    if len(sys.argv) != 2:
        raise SystemExit(2)
    signal.signal(signal.SIGTERM, interrupted)
    request_path = operator_path(sys.argv[1])
    if request_path.name != "request.json":
        raise ValueError("remote_training_request_path_invalid")
    request = json.loads(request_path.read_text())
    execute(request)


if __name__ == "__main__":
    main()
