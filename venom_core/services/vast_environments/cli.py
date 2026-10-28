"""Explicit terminal actions; no credentials in arguments or output."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from venom_core.infrastructure.providers.vast.client import VastClient, VastError
from venom_core.infrastructure.providers.vast.images import resolve_image
from venom_core.infrastructure.providers.vast.models import WorkloadProfile, now
from venom_core.services.vast_chat_cli import detach_plan
from venom_core.services.vast_environments.assessment import search_filters
from venom_core.services.vast_environments.billing import costs
from venom_core.services.vast_environments.cleanup_zero import (
    ZeroCheckError,
    cleanup_zero,
    trial_zero,
    verify_zero,
)
from venom_core.services.vast_environments.evaluation import compare
from venom_core.services.vast_environments.history import entries
from venom_core.services.vast_environments.history import report as qualification_report
from venom_core.services.vast_environments.lifecycle import Environments
from venom_core.services.vast_environments.operations import monitor, workload
from venom_core.services.vast_environments.recipes import RECIPES, prepare
from venom_core.services.vast_environments.store import Journal

INVALID_INPUT = "vast.invalid_input"
DEFAULT_STATE = ".venom_runtime/vast"
SSH_PROFILE_ROOT = Path(__file__).resolve().parents[3] / "secrets" / "ssh"


def utc_argument(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError
        return result
    except ValueError:
        raise argparse.ArgumentTypeError("vast.utc_offset_required") from None


def ssh_profile(path: Path) -> dict:
    try:
        # Profiles belong to the existing secret store, never to arbitrary CLI paths.
        root = SSH_PROFILE_ROOT.resolve(strict=True)
        resolved = path.expanduser().resolve(strict=True)
        if not resolved.is_relative_to(root) or resolved.suffix != ".json":
            raise ValueError
        if not resolved.is_file():
            raise ValueError
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError, RuntimeError):
        raise VastError("vast.invalid_ssh_profile") from None
    if not isinstance(value, dict) or any(
        not isinstance(value.get(key), str) or not value[key].strip()
        for key in ("identity_file", "known_hosts")
    ):
        raise VastError("vast.invalid_ssh_profile")
    return value


def _add_offer_commands(sub) -> None:
    for command in ("offers", "assess", "plan"):
        item = sub.add_parser(command)
        item.add_argument("--profile", type=Path, required=True)
        item.add_argument("--retest", action="store_true")
        item.add_argument(
            "--sort",
            choices=[
                "balanced",
                "price",
                "network",
                "reliability",
                "performance",
                "value",
            ],
        )
        item.add_argument("--country", action="append")
        item.add_argument("--any-gpu", action="store_true")
        preferences = item.add_mutually_exclusive_group()
        preferences.add_argument("--prefer-country", action="append")
        preferences.add_argument("--no-country-preference", action="store_true")
        item.add_argument("--min-download-mbps", type=float)
        item.add_argument("--min-upload-mbps", type=float)
        item.add_argument("--min-reliability", type=float)
        item.add_argument("--min-dlperf", type=float)
        item.add_argument("--min-gpu-mem-bw-gb-s", type=float)
        if command != "offers":
            item.add_argument("--offer", type=int, required=True)
        if command == "plan":
            item.add_argument("--max-hourly", type=Decimal, required=True)
            item.add_argument("--max-total", type=Decimal, required=True)
            item.add_argument(
                "--ssh-profile",
                type=Path,
                default=Path("secrets/ssh/vast/connection.json"),
            )
            item.add_argument(
                "--finish", choices=["manual", "stop", "destroy"], default="manual"
            )


def _add_record_commands(sub) -> None:
    for command in (
        "create",
        "status",
        "reconcile",
        "start",
        "stop",
        "destroy",
        "export",
        "cleanup",
        "wait",
        "monitor",
        "inspect",
        "qualify",
        "report",
        "provision",
        "ready",
        "benchmark",
        "costs",
    ):
        item = sub.add_parser(command)
        item.add_argument("--plan", required=True)
        if command in {"inspect", "provision", "qualify"}:
            item.add_argument("--accept-new-host-key", action="store_true")
        if command in {"wait", "monitor"}:
            item.add_argument(
                "--timeout", type=int, default=120 if command == "wait" else 600
            )
        if command == "costs":
            item.add_argument(
                "--from-utc",
                type=utc_argument,
                default=None,
            )
            item.add_argument("--to-utc", type=utc_argument, default=None)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Vast.ai environment operations")
    root.add_argument("--env-file", type=Path)
    root.add_argument("--state-dir", type=Path, default=Path(DEFAULT_STATE))
    root.add_argument("--json", action="store_true")
    root.add_argument("--locale", choices=["en", "pl", "de"], default="pl")
    sub = root.add_subparsers(dest="command", required=True)
    image = sub.add_parser("resolve-image")
    image.add_argument("--image", required=True)
    image.add_argument("--arch", choices=["amd64", "arm64"], required=True)
    sub.add_parser("recipes")
    sub.add_parser("qualifications")
    recipe = sub.add_parser("prepare")
    recipe.add_argument("--profile", type=Path)
    recipe.add_argument("--image")
    recipe.add_argument("--arch", choices=["amd64", "arm64"])
    recipe.add_argument("--model")
    recipe.add_argument("--model-digest")
    recipe.add_argument("--disk-gb", type=int)
    recipe.add_argument("--download-gb", type=Decimal)
    recipe.add_argument("--install-package", action="append")
    recipe.add_argument("--worker-task", action="append", choices=["vision", "audio"])
    recipe.add_argument(
        "--capability", action="append", choices=["json", "vision", "tools"]
    )
    recipe.add_argument("--recipe", choices=list(RECIPES), required=True)
    recipe.add_argument("--template-hash")
    recipe.add_argument("--output", type=Path, required=True)
    templates = sub.add_parser("templates")
    templates.add_argument("--hash")
    templates.add_argument("--recommended", action="store_true")
    history = sub.add_parser("host-results")
    history.add_argument("--machine", type=int, required=True)
    for command in ("chat-attach", "chat-detach", "chat-status"):
        item = sub.add_parser(command)
        item.add_argument("--api-base", default="http://127.0.0.1:8800")
        if command == "chat-attach":
            item.add_argument("--plan", required=True)
    for command in ("account", "list", "volumes", "verify-zero"):
        sub.add_parser(command)
    _add_offer_commands(sub)
    _add_record_commands(sub)
    for command in ("trial-zero", "cleanup-zero"):
        item = sub.add_parser(command)
        item.add_argument("--plan", required=True)
        item.add_argument("--timeout", type=int, default=120)
        item.add_argument("--api-base", default="http://127.0.0.1:8800")
        if command == "trial-zero":
            item.add_argument("--accept-new-host-key", action="store_true")
    item = sub.add_parser("compare")
    item.add_argument("reports", type=Path, nargs="+")
    return root


def workload_profile(args) -> WorkloadProfile:
    profile = WorkloadProfile.model_validate_json(
        args.profile.read_text(encoding="utf-8")
    )
    overrides = {
        field: getattr(args, argument)
        for field, argument in (
            ("sort_by", "sort"),
            ("countries", "country"),
            ("preferred_countries", "prefer_country"),
            ("min_download_mbps", "min_download_mbps"),
            ("min_upload_mbps", "min_upload_mbps"),
            ("min_reliability", "min_reliability"),
            ("min_dlperf", "min_dlperf"),
            ("min_gpu_mem_bw_gb_s", "min_gpu_mem_bw_gb_s"),
        )
        if getattr(args, argument, None) is not None
    }
    if getattr(args, "any_gpu", False):
        overrides["gpu_names"] = []
    if args.no_country_preference:
        overrides["preferred_countries"] = []
    return WorkloadProfile.model_validate({**profile.model_dump(), **overrides})


def _prepare_action(args, service: Environments):
    values = (
        json.loads(args.profile.read_text(encoding="utf-8"))
        if args.profile
        else {"name": "venom-" + args.recipe}
    )
    for argument, field in (
        ("image", "image"),
        ("arch", "cpu_arch"),
        ("model", "model"),
        ("model_digest", "model_digest"),
        ("disk_gb", "disk_gb"),
        ("download_gb", "download_gb"),
        ("install_package", "worker_packages"),
        ("worker_task", "worker_tasks"),
    ):
        if getattr(args, argument) is not None:
            values[field] = getattr(args, argument)
    values["mode"] = args.recipe
    if args.capability is not None:
        values.setdefault("runtime", {})["capabilities"] = args.capability
    if values.get("image") and "@sha256:" not in values["image"]:
        with httpx.Client(
            timeout=25, follow_redirects=False, trust_env=False
        ) as registry:
            resolved = resolve_image(
                values["image"], values.get("cpu_arch", ""), registry
            )
            values["image"] = resolved["image"]
            metadata = resolved.get("runtime_metadata") or {}
            values.setdefault("runtime", {}).update(
                image_cuda=metadata.get("cuda", ""),
                image_min_cuda=metadata.get("min_cuda", ""),
                image_metadata_source=metadata.get("source", "operator"),
            )
    profile = WorkloadProfile.model_validate(values)
    return prepare(
        service.client, profile, args.recipe, args.template_hash, args.output
    )


def _offer_action(args, service: Environments):
    command = args.command
    profile = workload_profile(args)
    if command == "offers":
        return [
            row.model_dump(mode="json")
            for row in service.search(profile, retest=args.retest)
        ]
    if command == "assess":
        rows = service.client.offers(
            profile.disk_gb,
            {**search_filters(profile), "ask_contract_id": {"eq": args.offer}},
        )
        selected = [row for row in rows if row.get("id") == args.offer]
        if len(selected) != 1:
            raise VastError("vast.offer_expired")
        return service.assess(profile, selected[0], retest=args.retest).model_dump(
            mode="json"
        )
    ssh = ssh_profile(args.ssh_profile)
    return service.plan(
        profile,
        args.offer,
        args.max_hourly,
        args.max_total,
        Path(ssh["identity_file"]),
        Path(ssh["known_hosts"]),
        args.finish,
        retest=args.retest,
    ).model_dump(mode="json")


def _cost_action(args, service: Environments):
    plan = service.journal.plan(args.plan)
    with service.journal.lock(args.plan):
        record = service.journal.record(args.plan)
        end = args.to_utc or now()
        start = args.from_utc or end - timedelta(days=7)
        result = costs(service.client, plan, record, start, end)
        record.reports["costs"] = result
        service.journal.save_record(record)
    return result


def _offline(args):
    if args.command == "qualifications":
        return entries(Journal(args.state_dir))
    if args.command == "report":
        return qualification_report(Journal(args.state_dir), args.plan)
    if args.command == "recipes":
        return RECIPES
    if args.command == "resolve-image":
        with httpx.Client(
            timeout=25, follow_redirects=False, trust_env=False
        ) as registry:
            return resolve_image(args.image, args.arch, registry)
    reports = []
    for path in args.reports:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(INVALID_INPUT)
        report = document.get("result", document)
        if not isinstance(report, dict):
            raise ValueError(INVALID_INPUT)
        reports.append(report)
    return compare(reports)


def _record_action(args, service: Environments):
    command = args.command
    if command in {"start", "stop", "destroy"}:
        return service.change(args.plan, command).model_dump(mode="json")
    if command == "export":
        return service.export(args.plan)
    methods = {
        "create": service.create,
        "status": service.reconcile,
        "reconcile": service.reconcile,
        "cleanup": service.cleanup,
    }
    return methods[command](args.plan).model_dump(mode="json")


def dispatch(args, service: Environments):
    command = args.command
    if command == "verify-zero":
        return verify_zero(service)
    if command == "cleanup-zero":
        return cleanup_zero(
            service,
            args.plan,
            args.timeout,
            before_destroy=lambda plan: detach_plan(plan, args.api_base),
        )
    if command == "trial-zero":
        return trial_zero(
            service,
            args.plan,
            args.timeout,
            accept_new_host_key=args.accept_new_host_key,
            before_destroy=lambda plan: detach_plan(plan, args.api_base),
        )
    if command in {"recipes", "resolve-image", "compare", "qualifications", "report"}:
        return _offline(args)
    if command in {"account", "list", "volumes"}:
        methods = {
            "account": service.client.account,
            "list": service.client.instances,
            "volumes": service.client.volumes,
        }
        return methods[command]()
    if command == "templates":
        return service.client.templates(args.hash, args.recommended)
    if command == "host-results":
        return service.client.benchmarks(args.machine)
    if command in {"offers", "assess", "plan"}:
        return _offer_action(args, service)
    if command in {
        "create",
        "status",
        "reconcile",
        "start",
        "stop",
        "destroy",
        "export",
        "cleanup",
    }:
        return _record_action(args, service)
    if command == "wait":
        return service.wait(args.plan, args.timeout).model_dump(mode="json")
    if command == "monitor":
        return monitor(service, args.plan, args.timeout)
    if command in {"inspect", "provision", "ready", "benchmark", "qualify"}:
        return workload(
            service, args.plan, command, getattr(args, "accept_new_host_key", False)
        )
    handlers = {"prepare": _prepare_action, "costs": _cost_action}
    handler = handlers.get(command)
    if handler is None:
        raise VastError("vast.invalid_action")
    return handler(args, service)


def _run(args, client_factory):
    if args.command in {"chat-attach", "chat-detach", "chat-status"}:
        from venom_core.services.vast_chat_cli import admin

        return admin(args.command, args.api_base, getattr(args, "plan", None))
    if args.command in {
        "recipes",
        "resolve-image",
        "compare",
        "qualifications",
        "report",
    }:
        return _offline(args)
    from venom_core.config import Settings

    options: dict[str, Any] = {"_env_file": os.environ.get("ENV_FILE") or ".env.dev"}
    client = (client_factory or VastClient)(Settings(**options).VAST_API_KEY)
    try:
        return dispatch(args, Environments(client, Journal(args.state_dir)))
    finally:
        client.close()


def _error_output(exc: Exception) -> dict[str, Any]:
    error = exc.code if isinstance(exc, VastError) else INVALID_INPUT
    result = {"ok": False, "error": error}
    if isinstance(exc, VastError):
        result.update(http_status=exc.status, outcome_unknown=exc.ambiguous)
    if isinstance(exc, ZeroCheckError):
        result["report"] = exc.report
    return result


def main(argv=None, client_factory=None) -> int:
    # Local operator CLI only: this function is not an HTTP route or LLM tool.
    args = parser().parse_args(argv)
    if args.env_file:
        os.environ["ENV_FILE"] = str(args.env_file.expanduser().resolve())
    try:
        output = {"ok": True, "result": _run(args, client_factory)}
    except (
        VastError,
        ValidationError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        output = _error_output(exc)
    if not args.json:
        labels = json.loads(
            (Path(__file__).parent / "messages.json").read_text(encoding="utf-8")
        )
        print(labels[args.locale]["ok" if output["ok"] else "error"])
    print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    return 0 if output["ok"] else 1
