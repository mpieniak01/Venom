"""Paired remote GPU inference with existing local Docker oracles and fixtures."""

from __future__ import annotations

import argparse
import json
import os
import random
import selectors
import shlex
import signal
import subprocess
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from scripts.granite_operator.comparison import INFERENCE, run_case
from scripts.granite_operator.comparison_support import (
    cleanup_owned,
    load_frozen,
    summarize,
)
from venom_core.services.granite_operator.contract import file_digest, write_json
from venom_core.services.remote_training.paths import operator_path
from venom_core.services.remote_training.transport import SSHConfig

MAX_LINE = 1024 * 1024


class RemoteInference:
    """One authenticated SSH stream; only fixed JSON operations cross this boundary."""

    def __init__(self, args, output):
        SSHConfig(
            args.ssh_config, args.host, args.host_root, python=args.remote_python
        ).validate()
        command = [
            args.remote_python,
            "-m",
            "scripts.granite_operator.remote_inference",
            "--host-root",
            args.host_root,
            "--result",
            args.remote_result,
            "--expected-adapter-sha256",
            args.adapter_sha256,
            "--max-seconds",
            str(args.max_seconds),
        ]
        self.error_log = (output / "remote-worker.log").open("ab")
        self.process = subprocess.Popen(
            [
                "ssh",
                "-T",
                "-F",
                str(args.ssh_config),
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ForwardAgent=no",
                "--",
                args.host,
                shlex.join(command),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.error_log,
            start_new_session=True,
            bufsize=0,
        )
        self.healthy = True
        self.buffer = b""
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        try:
            self.ready = self.receive(180)
            if (
                self.ready.get("adapter_sha256") != args.adapter_sha256
                or self.ready.get("inference") != INFERENCE
            ):
                raise ValueError("comparison_remote_identity_mismatch")
        except BaseException:
            self.close()
            raise
        self.torch = SimpleNamespace(cuda=self)

    def receive(self, timeout):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                self.healthy = False
                raise RuntimeError("comparison_remote_timeout")
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("comparison_remote_disconnected")
            self.buffer += chunk
            if len(self.buffer) > MAX_LINE:
                raise ValueError("comparison_remote_response_too_large")
        line, self.buffer = self.buffer.split(b"\n", 1)
        value = json.loads(line)
        if isinstance(value, dict) and value.get("ok") is False:
            if value.get("error") == "comparison_context_limit":
                raise ValueError("comparison_context_limit")
            if value.get("error") == "comparison_task_deadline":
                raise TimeoutError("comparison_task_deadline")
        if (
            not isinstance(value, dict)
            or value.get("ok") is not True
            or not isinstance(value.get("result"), dict)
        ):
            raise RuntimeError("comparison_remote_operation_failed")
        return value["result"]

    def request(self, op, **values):
        raw = (json.dumps({"op": op, **values}, allow_nan=False) + "\n").encode()
        if len(raw) > MAX_LINE:
            raise ValueError("comparison_remote_request_too_large")
        self.process.stdin.write(raw)
        self.process.stdin.flush()
        return self.receive(90)

    def generate(self, _session, messages, tools, arm, deadline):
        remaining = min(60, deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("comparison_task_deadline")
        return self.request(
            "generate", messages=messages, tools=tools, arm=arm, seconds=remaining
        )

    def reset_peak_memory_stats(self):
        self.request("reset_stats")

    def max_memory_allocated(self):
        self.stats = self.request("stats")
        return self.stats["peak_allocated_bytes"]

    def max_memory_reserved(self):
        return self.stats["peak_reserved_bytes"]

    def close(self):
        process = self.process
        if process.poll() is None:
            try:
                if self.healthy and hasattr(self, "ready"):
                    self.request("close")
                process.stdin.close()
                process.wait(timeout=20)
            except (
                OSError,
                RuntimeError,
                ValueError,
                TimeoutError,
                subprocess.TimeoutExpired,
            ):
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        self.selector.close()
        self.error_log.close()


def evaluate(args, factory=RemoteInference):
    manifest, cases = load_frozen(args.cases)
    if manifest.get("qualification", {}).get("status") != "PASS":
        raise ValueError("comparison_cases_not_qualified")
    args.output.mkdir(parents=True, exist_ok=args.resume)
    rows_path = args.output / "trials.jsonl"
    identity = {
        "manifest_sha256": file_digest(args.cases),
        "adapter_sha256": args.adapter_sha256,
        "inference": INFERENCE,
        "host": args.host,
        "remote_result": args.remote_result,
        "benchmark_role": "diagnostic_after_G02_curation",
        "sandbox_image": manifest["sandbox_image"],
        "source_sha256": {
            name: file_digest(Path(__file__).with_name(name))
            for name in [
                "remote_comparison.py",
                "remote_inference.py",
                "comparison.py",
                "comparison_support.py",
            ]
        },
    }
    identity_path = args.output / "identity.json"
    if identity_path.exists():
        if not args.resume or json.loads(identity_path.read_text()) != identity:
            raise ValueError("comparison_resume_identity_changed")
    else:
        write_json(identity_path, identity)
    rows = (
        [json.loads(line) for line in rows_path.read_text().splitlines()]
        if rows_path.exists()
        else []
    )
    done = {(row["case_id"], row["arm"]) for row in rows}
    expected = {(case["id"], arm) for case in cases for arm in ("base", "adapter")}
    if len(done) != len(rows) or not done <= expected:
        raise ValueError("comparison_resume_trials_invalid")
    ordered = cases.copy()
    random.Random(7441).shuffle(ordered)
    run_id = uuid.uuid4().hex
    remote = None
    started = time.monotonic()
    progress = {"status": "RUNNING", "completed": len(rows), "total": len(cases) * 2}
    try:
        remote = factory(args, args.output)
        binding = args.output / "remote-identity.json"
        if binding.exists() and json.loads(binding.read_text()) != remote.ready:
            raise ValueError("comparison_remote_resume_identity_changed")
        write_json(binding, remote.ready)
        write_json(args.output / ("remote-ready-" + run_id + ".json"), remote.ready)
        warmup = [
            {"role": "system", "content": cases[0]["system"]},
            {
                "role": "user",
                "content": "Call Finish with status success and summary ready.",
            },
        ]
        for arm in ("base", "adapter", "adapter", "base"):
            remote.generate(
                remote, warmup, cases[0]["tools"], arm, time.monotonic() + 60
            )
        for index, case in enumerate(ordered):
            arms = ("base", "adapter") if index % 2 == 0 else ("adapter", "base")
            for arm in arms:
                if (case["id"], arm) in done:
                    continue
                if time.monotonic() - started >= args.max_seconds:
                    raise TimeoutError("comparison_session_deadline")
                row = run_case(
                    remote,
                    case,
                    args.cases.parent,
                    args.output,
                    manifest["sandbox_image"],
                    run_id,
                    arm,
                    generator=remote.generate,
                )
                row.update(trial_sequence=len(rows) + 1, pair_order=arms[0] + "-first")
                with rows_path.open("a") as stream:
                    stream.write(
                        json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
                rows.append(row)
                done.add((case["id"], arm))
                progress = {
                    "status": "RUNNING",
                    "completed": len(rows),
                    "total": len(cases) * 2,
                    "last_case": case["id"],
                    "last_arm": arm,
                    "successes": {
                        a: sum(r["oracle"]["success"] for r in rows if r["arm"] == a)
                        for a in ("base", "adapter")
                    },
                    "attempts": {
                        a: sum(r["arm"] == a for r in rows) for a in ("base", "adapter")
                    },
                }
                write_json(args.output / "progress.json", progress)
                print(json.dumps(progress), flush=True)
        load_frozen(args.cases)
        result = {
            **summarize(rows),
            "status": "COMPLETE",
            "case_count": len(cases),
            "inference": INFERENCE,
            "benchmark_role": "diagnostic_after_G02_curation",
            "wall_seconds": time.monotonic() - started,
        }
        write_json(args.output / "summary.json", result)
        write_json(args.output / "progress.json", {**progress, "status": "COMPLETE"})
        return result
    finally:
        try:
            if remote is not None:
                remote.close()
        finally:
            if not cleanup_owned(run_id):
                raise RuntimeError("comparison_sandbox_cleanup_unconfirmed")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cases", type=operator_path, required=True)
    p.add_argument("--output", type=operator_path, required=True)
    p.add_argument("--ssh-config", type=Path, required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--host-root", default="/workspace/data/remote-training")
    p.add_argument(
        "--remote-python", default="/workspace/data/remote-training/rpc-python"
    )
    p.add_argument("--remote-result", required=True)
    p.add_argument("--adapter-sha256", required=True)
    p.add_argument("--max-seconds", type=int, choices=range(60, 14401), default=7200)
    p.add_argument("--resume", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    os.umask(0o077)
    try:
        evaluate(args)
    except (OSError, RuntimeError, ValueError, TimeoutError) as error:
        if args.output.exists():
            write_json(
                args.output / "status.json",
                {"status": "FAIL", "error": type(error).__name__},
            )
        print(json.dumps({"ok": False, "error": type(error).__name__}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
