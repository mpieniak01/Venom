"""Explicit local or SSH training CLI; GPU execution remains operator controlled."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bundles import verify_bundle
from .client import RemoteClient
from .host import initialize
from .paths import operator_path, python_path
from .transport import SSHConfig, SSHTransport, Transport


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--execution", choices=("local", "remote"), default="remote")
    value.add_argument("--local-root", type=operator_path)
    value.add_argument("--local-python", type=python_path)
    value.add_argument("--ssh-config", type=Path, default=Path.home() / ".ssh/config")
    value.add_argument(
        "--host", help="Existing SSH alias, with a verified known_hosts entry"
    )
    value.add_argument("--remote-root", default="/workspace/data/remote-training")
    value.add_argument("--remote-python", default="python3")
    sub = value.add_subparsers(dest="action", required=True)
    sub.add_parser("host-check")
    plan = sub.add_parser("plan")
    plan.add_argument("--run-id", required=True)
    plan.add_argument("--milestones", type=int, nargs="+", default=[80, 125, 160])
    plan.add_argument("--max-seconds", type=int, default=7200)
    plan.add_argument("--output", type=operator_path, required=True)
    pack = sub.add_parser("pack")
    for flag in ("source", "manifest", "profile", "snapshot", "output"):
        pack.add_argument("--" + flag, type=operator_path, required=True)
    pack.add_argument("--run-id", required=True)
    pack.add_argument("--dataset", choices=("domain", "hf", "mixed"), default="domain")
    pack.add_argument("--updates", type=int, default=100)
    pack.add_argument("--max-seconds", type=int, default=3600)
    host = sub.add_parser("host-init")
    for flag in ("root", "worker-python", "snapshot", "admission-db", "code-root"):
        host.add_argument(
            "--" + flag,
            type=python_path if flag == "worker-python" else operator_path,
            required=True,
        )
    upload = sub.add_parser("upload")
    upload.add_argument("--bundle", type=operator_path, required=True)
    for action in (
        "start",
        "status",
        "attempts",
        "logs",
        "stop",
        "resume",
        "retry",
        "collect",
        "watch",
    ):
        cmd = sub.add_parser(action)
        cmd.add_argument("--run-id", required=True)
        if action == "watch":
            cmd.add_argument("--interval", type=float, default=5)
            cmd.add_argument("--json-lines", action="store_true")
            cmd.add_argument("--max-seconds", type=float, default=3600)
        if action in {"start", "resume"}:
            cmd.add_argument("--until-update", type=int)
        if action == "start":
            cmd.add_argument("--stage", choices=("smoke", "train"), default="smoke")
        if action == "retry":
            cmd.add_argument("--from-attempt", type=int, required=True)
        if action == "resume":
            cmd.add_argument(
                "--checkpoint", required=True, help="Checkpoint relative to this run"
            )
        if action == "collect":
            cmd.add_argument("--output", type=operator_path, required=True)
            cmd.add_argument("--include-checkpoint", action="store_true")
            cmd.add_argument("--attempt", type=int)
    for action in ("inspect-result", "import-result"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--bundle", type=operator_path, required=True)
        cmd.add_argument("--input-bundle", type=operator_path, required=True)
        if action == "import-result":
            cmd.add_argument("--quarantine", type=operator_path, required=True)
            cmd.add_argument("--registry", type=operator_path, required=True)
            cmd.add_argument("--academy-models", type=operator_path)
            cmd.add_argument(
                "--verify-local",
                action="store_true",
                help="Explicit fresh local GPU reload; requires offline target",
            )
            cmd.add_argument("--host-root", type=operator_path)
    return value


def dispatch(args):
    if args.action == "host-check":
        from .local_host import readiness

        if getattr(args, "execution", "remote") != "local" or args.local_root is None:
            raise ValueError("local_training_host_check_requires_local_root")
        return readiness(args.local_root)
    if args.action == "plan":
        from .lifecycle import atomic_json, file_lock
        from .milestones import plan

        document = plan(args.run_id, args.milestones, args.max_seconds)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(
            args.output.with_name(args.output.name + ".lock"), blocking=False
        ):
            if args.output.exists():
                if json.loads(args.output.read_text()) != document:
                    raise ValueError("remote_training_plan_exists")
            else:
                atomic_json(args.output, document)
        return document
    if args.action == "pack":
        from .job import prepare

        return prepare(
            args.source,
            args.manifest,
            args.profile,
            args.snapshot,
            args.output,
            run_id=args.run_id,
            dataset=args.dataset,
            updates=args.updates,
            max_seconds=args.max_seconds,
        )
    if args.action == "host-init":
        configured = initialize(
            args.root,
            worker_python=args.worker_python,
            snapshot=args.snapshot,
            admission_db=args.admission_db,
            code_root=args.code_root,
            execution=args.execution,
        )
        if getattr(args, "execution", "remote") == "local":
            from .local_host import readiness

            return {**configured, "readiness": readiness(args.root)}
        return configured
    if args.action in {"inspect-result", "import-result"}:
        from .artifacts import verify_result_bundle

        source = verify_bundle(args.input_bundle)
        if source["kind"] != "input":
            raise ValueError("remote_training_input_bundle_required")
        if args.action == "inspect-result":
            return verify_result_bundle(
                args.bundle,
                expected_identity=source["identity"],
                expected_run_id=source["run_id"],
            )
        from .importer import import_result

        verifier = None
        if args.verify_local:
            if args.host_root is None:
                raise ValueError("remote_training_local_host_config_required")
            from .verification import verify_local

            def local_reload(adapter, _identity):
                return verify_local(adapter, args.host_root)

            verifier = local_reload
        return import_result(
            args.bundle,
            args.quarantine,
            args.registry,
            source["identity"],
            source["run_id"],
            reload_verifier=verifier,
            academy_models=args.academy_models,
        )
    transport: Transport
    if getattr(args, "execution", "remote") == "local":
        from .local_transport import LocalConfig, LocalTransport

        if args.local_root is None or args.local_python is None:
            raise ValueError("local_training_root_and_interpreter_required")
        if args.host:
            raise ValueError("local_training_ssh_alias_not_allowed")
        if args.action in {"start", "resume", "retry"}:
            from .local_host import readiness

            if readiness(args.local_root).get("ready") is not True:
                raise ValueError("remote_training_local_host_not_ready")
        transport = LocalTransport(LocalConfig(args.local_root, args.local_python))
    else:
        if not args.host:
            raise ValueError("remote_training_ssh_alias_required")
        config = SSHConfig(
            args.ssh_config, args.host, args.remote_root, python=args.remote_python
        )
        transport = SSHTransport(config)
    client = RemoteClient(transport)
    if args.action == "watch":
        from .progress import watch

        return watch(
            client,
            args.run_id,
            interval=args.interval,
            max_seconds=args.max_seconds,
            json_lines=args.json_lines,
        )
    if args.action == "upload":
        manifest = verify_bundle(args.bundle)
        if manifest["kind"] != "input":
            raise ValueError("remote_training_input_bundle_required")
        client.prepare(manifest)
        return client.upload(manifest["run_id"], args.bundle)
    if args.action == "attempts":
        return client.attempt_history(args.run_id)
    if args.action == "start":
        return client.start(
            args.run_id,
            stage=args.stage,
            **(
                {"until_update": args.until_update}
                if args.until_update is not None
                else {}
            ),
        )
    if args.action == "retry":
        return client.retry(args.run_id, from_attempt=args.from_attempt)
    if args.action == "resume":
        return client.resume(
            args.run_id,
            args.checkpoint,
            **(
                {"until_update": args.until_update}
                if args.until_update is not None
                else {}
            ),
        )
    if args.action == "collect":
        return client.collect(
            args.run_id,
            args.output,
            include_checkpoint=args.include_checkpoint,
            **({"attempt": args.attempt} if args.attempt is not None else {}),
        )
    return getattr(client, args.action)(args.run_id)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        # Exception text may originate at a remote host; never print it blindly.
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "remote_training_operation_failed",
                    "type": type(error).__name__,
                }
            )
        )
        return 1
    indent = None if args.action == "watch" and args.json_lines else 2
    print(json.dumps({"ok": True, "result": result}, default=str, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
