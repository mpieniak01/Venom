"""Register a transferred experiment arm in an already configured training supervisor."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from venom_core.services.functiongemma.execution import preflight
from venom_core.services.functiongemma.profile import INITIAL_WEIGHTS_DIRECTORY
from venom_core.services.granite_operator.contract import file_digest
from venom_core.services.remote_training.bundles import extract_bundle, verify_bundle
from venom_core.services.remote_training.host import load_host
from venom_core.services.remote_training.lifecycle import JobStore, file_lock
from venom_core.services.remote_training.paths import operator_path

from .weights import hashes


def register(root, bundle, plan_path, weights):
    """Register a prepared arm with a verified warm start and leave execution pending."""
    root, bundle, plan_path, weights = map(
        operator_path, (root, bundle, plan_path, weights)
    )
    plan = json.loads(plan_path.read_text())
    if plan["bundle_sha256"] != file_digest(bundle):
        raise ValueError("transferred bundle differs from the local plan")
    manifest = verify_bundle(
        bundle, expected_run_id=plan["run_id"], expected_identity=plan["identity"]
    )
    if manifest["kind"] != "input":
        raise ValueError("experiment requires an input bundle")
    host = load_host(root)
    store = JobStore(root)
    run = operator_path(store.directory(plan["run_id"]))
    run.mkdir(exist_ok=True, mode=0o700)
    expected_weights = plan["recipe"]["initial_weights"]
    if hashes(weights) != expected_weights:
        raise ValueError("transferred warm start differs from the recipe")
    with file_lock(run / ".transfer.lock"):
        if (run / "state.json").exists():
            old = store.status(plan["run_id"])
            if old["status"] != "prepared" or old["attempt"] != 0:
                raise ValueError("run already has attempts")
        warm = operator_path(run / INITIAL_WEIGHTS_DIRECTORY)
        warm.mkdir(exist_ok=True)
        for name in expected_weights:
            target = operator_path(warm / name)
            if not target.exists():
                os.link(weights / name, target)
        extract_bundle(
            bundle,
            run / "input",
            expected_run_id=plan["run_id"],
            expected_identity=plan["identity"],
        )
        recipe, encoded = preflight(host, run / "input", plan["identity"])
        if recipe.budget(len(encoded["records"]["train"])) != plan["budget"]:
            raise ValueError("transferred training budget changed")
        state = store.prepare(manifest)
    return {
        "run_id": plan["run_id"],
        "status": state["status"],
        "attempt": state["attempt"],
    }


def main():
    """Parse the verified bundle, launch plan, and checkpoint directory for registration."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "bundle", "plan", "weights"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(register(args.root, args.bundle, args.plan, args.weights)))


if __name__ == "__main__":
    main()
