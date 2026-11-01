"""Offline coordinator using the SAME host admission ledger as Venom."""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path

from .contract import (
    file_digest,
    load_dataset,
    load_profile,
    require_qualification,
    select_dataset,
    write_json,
)


def require_offline(ports=(8800, 8801, 8014, 11434)) -> None:
    """Do not race the live API or an independently running model service."""
    for port in ports:
        with socket.socket() as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError("granite_requires_offline_host:port=" + str(port))


def qualification(metrics: dict, first: dict, artifacts: dict) -> dict:
    """Failed probes remain failed receipts; no best-effort success conversion."""
    checks = dict(metrics["checks"])
    checks["updated_adapter"] = (
        checks.get("updated_adapter") is True
        and first["checks"].get("updated_adapter") is True
    )
    checks["frozen_base"] = (
        checks.get("frozen_base") is True and first["checks"].get("frozen_base") is True
    )
    if first["fingerprint"] != metrics["fingerprint"]:
        raise ValueError("granite_smoke_identity_changed")
    receipt = {
        "status": "PASS",
        "fingerprint": metrics["fingerprint"],
        "checks": checks,
        "artifacts": artifacts,
    }
    try:
        require_qualification(receipt, metrics["fingerprint"])
        if checks.get("adapter_effect") is not True:
            raise ValueError("granite_adapter_no_effect")
    except ValueError:
        receipt["status"] = "FAIL"
    return receipt


def _execute_stages(args, profile, train, stage):
    if args.command == "smoke":
        first = stage("smoke-first", 16)
        second = stage("smoke-resume", 4, args.output / "smoke-first/checkpoint")
        artifacts = {
            str(path.relative_to(args.output)): file_digest(path)
            for path in args.output.rglob("*")
            if path.is_file() and path.suffix != ".log"
        }
        receipt = qualification(second, first, artifacts)
        write_json(args.output / "qualification.json", receipt)
        require_qualification(receipt, second["fingerprint"])
    else:
        if not args.qualification:
            raise ValueError("granite_smoke_required")
        receipt = json.loads(args.qualification.read_text())
        require_qualification(receipt, receipt.get("fingerprint"))
        # Equal update count is explicit for comparisons; default domain one epoch.
        updates = (
            args.updates
            if args.updates is not None
            else math.ceil(len(train) / profile.accumulation)
        )
        if not 1 <= updates <= 128:
            raise ValueError("granite_update_budget_invalid")
        first_count = min(12, updates)
        stage("train-first", first_count)
        if updates > first_count:
            stage(
                "train-resume",
                updates - first_count,
                args.output / "train-first/checkpoint",
            )


def run(args):
    """Hold the lease until every worker has exited, including failure cleanup."""
    from venom_core.services.runtime_admission import RuntimeAdmission

    require_offline()
    profile = load_profile(args.profile)
    manifest = json.loads(args.manifest.read_text())
    if manifest.get("context", profile.context) != profile.context:
        raise ValueError("granite_manifest_context_mismatch")
    domain = load_dataset(args.data_root, manifest, "domain")
    hf = load_dataset(args.data_root, manifest, "hf")
    train, _ = select_dataset(domain, hf, args.dataset)
    args.output.mkdir(parents=True, exist_ok=False)
    run_id = uuid.uuid4().hex
    write_json(
        args.output / "locations.json",
        {
            "run_id": run_id,
            "data_root": str(args.data_root.resolve()),
            "manifest": str(args.manifest.resolve()),
            "snapshot": str(args.snapshot.resolve()),
            "worker_python": str(args.worker_python.resolve()),
            "admission_db": str(args.admission_db.resolve()),
            "output": str(args.output.resolve()),
            "profile": profile.identity(),
            "dataset": args.dataset,
        },
    )
    admission = RuntimeAdmission(args.admission_db, enabled=True)
    lease = admission.acquire(
        owner="granite-training",
        run_id=run_id,
        engine="granite-training",
        model=profile.model,
    )
    children = []

    def quiescent():
        return all(child.poll() is not None for child in children)

    def stage(name, updates, checkpoint=None):
        request = {
            "stage": name,
            "updates": updates,
            "checkpoint": str(checkpoint) if checkpoint else None,
            "profile": profile.identity(),
            "data_root": str(args.data_root.resolve()),
            "manifest": str(args.manifest.resolve()),
            "snapshot": str(args.snapshot.resolve()),
            "output": str((args.output / name).resolve()),
            "dataset": args.dataset,
            "qualification": str(args.qualification.resolve())
            if args.qualification
            else None,
        }
        request_path = args.output / (name + ".request.json")
        write_json(request_path, request)
        environment = {
            **os.environ,
            "VENOM_GRANITE_ADMISSION_DB": str(args.admission_db.resolve()),
            "VENOM_GRANITE_RUN_ID": run_id,
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "PYTHONPATH": str(Path(__file__).resolve().parents[3]),
        }
        command = [
            "setpriv",
            "--pdeathsig",
            "TERM",
            "--",
            str(args.worker_python),
            "-m",
            "venom_core.services.granite_operator.worker",
            str(request_path),
        ]
        with (args.output / (name + ".log")).open("w") as log:
            child = subprocess.Popen(
                command, env=environment, stdout=log, stderr=subprocess.STDOUT
            )
            children.append(child)
            try:
                code = child.wait(timeout=args.timeout)
            except BaseException:
                child.terminate()
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=20)
                raise
        if code != 0:
            raise RuntimeError("granite_worker_failed:" + name + ":exit=" + str(code))
        return json.loads((args.output / name / "metrics.json").read_text())

    try:
        with lease.operation(kind="lifecycle", confirm_quiescent=quiescent):
            _execute_stages(args, profile, train, stage)
        write_json(args.output / "status.json", {"status": "PASS", "run_id": run_id})
    except BaseException as error:
        write_json(
            args.output / "status.json",
            {
                "status": "FAIL",
                "run_id": run_id,
                "error": str(error),
            },
        )
        raise
    finally:
        if quiescent():
            lease.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("smoke", "train"))
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--worker-python", type=Path, required=True)
    parser.add_argument(
        "--admission-db",
        type=Path,
        required=True,
        help="Actual Venom host ledger; never invent a separate namespace",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--profile", type=Path, default=Path("config/granite_operator_profile.json")
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Local corpus manifest; defaults to DATA_ROOT/pilot-manifest.json",
    )
    parser.add_argument("--qualification", type=Path)
    parser.add_argument(
        "--dataset", choices=("domain", "hf", "mixed"), default="domain"
    )
    parser.add_argument("--updates", type=int)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    args.manifest = args.manifest or args.data_root / "pilot-manifest.json"
    try:
        run(args)
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
