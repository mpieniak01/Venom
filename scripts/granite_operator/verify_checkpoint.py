"""Fresh-process final checkpoint verification under the actual host lease."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from venom_core.services.granite_operator.contract import (
    TrainingProfile,
    digest,
    file_digest,
    load_dataset,
    select_dataset,
    write_json,
)


def verify(run: Path):
    from venom_core.services.granite_operator.engine import (
        Session,
        encoded_rows,
        environment_identity,
        require_owner,
    )
    from venom_core.services.granite_operator.worker import tool_loop

    require_owner()
    locations = json.loads((run / "locations.json").read_text())
    profile = TrainingProfile(**locations["profile"])
    manifest = json.loads(Path(locations["manifest"]).read_text())
    domain = load_dataset(Path(locations["data_root"]), manifest, "domain")
    hf = load_dataset(Path(locations["data_root"]), manifest, "hf")
    _, validation = select_dataset(domain, hf, locations.get("dataset", "domain"))
    stage = run / ("train-resume" if (run / "train-resume").exists() else "train-first")
    metrics = json.loads((stage / "metrics.json").read_text())
    session = Session(profile, Path(locations["snapshot"]), stage / "checkpoint")
    fingerprint = digest(
        environment_identity(
            profile, manifest, session.tokenizer, Path(locations["snapshot"])
        )
    )
    if fingerprint != metrics["fingerprint"]:
        raise ValueError("verification_fingerprint_changed")
    rows = encoded_rows(validation, session.tokenizer, profile)
    session.restore(stage / "checkpoint", rows[0], fingerprint)
    if session.step != metrics["global_step"]:
        raise ValueError("verification_step_mismatch")
    result = session.evaluate(rows)
    if abs(result["assistant_nll"] - metrics["validation"]["assistant_nll"]) > 0.001:
        raise ValueError("verification_nll_mismatch")
    # Keep the technical probe schema Terminal/Finish even for HF-only training.
    loop = tool_loop(session, domain[0][0])
    receipt = {
        "status": "PASS" if loop["passed"] else "FAIL",
        "fingerprint": fingerprint,
        "global_step": session.step,
        "worker_python": sys.executable,
        "worker_prefix": sys.prefix,
        "validation": result,
        "tool_loop": loop,
        "adapter_sha256": file_digest(stage / "checkpoint/adapter_model.safetensors"),
        "verifier_sha256": file_digest(Path(__file__)),
    }
    write_json(run / "checkpoint-verification.json", receipt)
    if receipt["status"] != "PASS":
        raise RuntimeError("final_checkpoint_tool_loop_failed")


def coordinate(run: Path, database: Path, worker_python: Path):
    from venom_core.services.granite_operator.cli import require_offline
    from venom_core.services.runtime_admission import RuntimeAdmission

    require_offline()
    if (run / "checkpoint-verification.json").exists():
        raise ValueError("checkpoint_already_verified")
    if json.loads((run / "status.json").read_text())["status"] != "PASS":
        raise ValueError("training_did_not_pass")
    locations = json.loads((run / "locations.json").read_text())
    if database.resolve() != Path(locations["admission_db"]).resolve():
        raise ValueError("verification_requires_same_host_ledger")
    run_id = uuid.uuid4().hex
    lease = RuntimeAdmission(database, enabled=True).acquire(
        owner="granite-training",
        run_id=run_id,
        engine="granite-training",
        model=locations["profile"]["model"],
    )
    child = None

    def quiescent():
        return child is None or child.poll() is not None

    try:
        with lease.operation(kind="lifecycle", confirm_quiescent=quiescent):
            environment = {
                **os.environ,
                "VENOM_GRANITE_ADMISSION_DB": str(database.resolve()),
                "VENOM_GRANITE_RUN_ID": run_id,
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "TOKENIZERS_PARALLELISM": "false",
                "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            }
            with (run / "checkpoint-verification.log").open("w") as log:
                child = subprocess.Popen(
                    [
                        "setpriv",
                        "--pdeathsig",
                        "TERM",
                        "--",
                        str(worker_python.absolute()),
                        "-m",
                        "scripts.granite_operator.verify_checkpoint",
                        "--worker",
                        "--worker-python",
                        str(worker_python.absolute()),
                        "--run",
                        str(run.resolve()),
                        "--admission-db",
                        str(database.resolve()),
                    ],
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    code = child.wait(timeout=600)
                except BaseException:
                    child.terminate()
                    try:
                        child.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=20)
                    raise
            if code:
                raise RuntimeError("checkpoint_verification_worker_failed")
    finally:
        if quiescent():
            lease.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--admission-db", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--worker-python", type=Path, required=True)
    args = parser.parse_args()
    if args.worker:
        verify(args.run)
    else:
        coordinate(args.run, args.admission_db, args.worker_python)


if __name__ == "__main__":
    main()
