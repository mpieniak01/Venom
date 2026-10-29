"""Qualify a local shared wheel against the recorded Windows consumer and Venom."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def verify_artifact(wheel: Path, receipt: dict, peer: dict) -> None:
    if (
        receipt.get("package") != "agent-execution-core"
        or receipt.get("version") != "0.1.0"
    ):
        raise ValueError("unexpected_package")
    if (
        receipt.get("wheel") != wheel.name
        or receipt.get("sha256") != hashlib.sha256(wheel.read_bytes()).hexdigest()
    ):
        raise ValueError("wheel_identity_mismatch")
    if peer.get("receipt") != receipt or len(peer.get("groups", [])) < 2:
        raise ValueError("peer_receipt_missing_or_mismatched")
    if {g.get("group") for g in peer["groups"]} != {
        "library",
        "orchestration",
    } or peer.get("environment") != "windows-host":
        raise ValueError("peer_scope_incomplete")
    if len(peer.get("consumer_head", "")) != 40:
        raise ValueError("peer_consumer_identity_missing")
    if any(group.get("returncode") != 0 for group in peer["groups"]):
        raise ValueError("peer_checks_failed")
    source = receipt.get("source_commit", "")
    if len(source) != 40 or any(c not in "0123456789abcdef" for c in source):
        raise ValueError("source_commit_invalid")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--windows-proof", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("test-results/openrouter/qualification-linux.json"),
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    receipt = json.loads(args.receipt.read_text())
    peer = json.loads(args.windows_proof.read_text())
    verify_artifact(args.wheel, receipt, peer)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    before = subprocess.check_output(["git", "diff", "HEAD", "--binary"], cwd=root)
    rows = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="openrouter-wheel-") as name:
        target = Path(name) / "installed"
        env = dict(
            os.environ,
            PYTHONPATH=os.pathsep.join((str(target), str(root))),
            EXECUTION_CORE_WHEEL_TEST="1",
            EXECUTION_CORE_INSTALLED_ROOT=str(target),
            OPENROUTER_API_KEY="",
        )
        commands = [
            (
                "install",
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    "--no-compile",
                    "--target",
                    str(target),
                    str(args.wheel),
                ],
            ),
            (
                "origin",
                [
                    sys.executable,
                    "-c",
                    'import os,pathlib,agent_execution_core; assert pathlib.Path(agent_execution_core.__file__).resolve().is_relative_to(pathlib.Path(os.environ["EXECUTION_CORE_INSTALLED_ROOT"]).resolve())',
                ],
            ),
            (
                "venom",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_openrouter_runtime.py",
                    "tests/test_openrouter_wheel.py",
                    "tests/test_vast_chat_runtime.py",
                ],
            ),
        ]
        for group, command in commands:
            started = time.monotonic()
            with args.output.with_name(group + ".log").open("w") as log:
                result = subprocess.run(
                    command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT
                )
            rows.append(
                {
                    "group": group,
                    "returncode": result.returncode,
                    "seconds": round(time.monotonic() - started, 2),
                }
            )
            if result.returncode:
                break
    unchanged = (
        before == subprocess.check_output(["git", "diff", "HEAD", "--binary"], cwd=root)
        and head
        == subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
    )
    report = {
        "receipt": receipt,
        "windows_consumer_head": peer.get("consumer_head"),
        "venom_head": head,
        "python": sys.version,
        "groups": rows,
        "sources_unchanged": unchanged,
    }
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    return int(not unchanged or len(rows) != 3 or any(x["returncode"] for x in rows))


if __name__ == "__main__":
    raise SystemExit(main())
