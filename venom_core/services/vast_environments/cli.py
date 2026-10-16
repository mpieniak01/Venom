"""Explicit terminal actions; no credentials in arguments or output."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from venom_core.infrastructure.providers.vast.client import VastClient, VastError
from venom_core.infrastructure.providers.vast.models import WorkloadProfile, now
from venom_core.services.vast_environments.assessment import assess, search_filters
from venom_core.services.vast_environments.billing import costs
from venom_core.services.vast_environments.evaluation import compare
from venom_core.services.vast_environments.lifecycle import Environments
from venom_core.services.vast_environments.operations import monitor, workload
from venom_core.services.vast_environments.store import Journal

DEFAULT_STATE = ".venom_runtime/vast"


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Vast.ai environment operations")
    root.add_argument("--env-file", type=Path)
    root.add_argument("--state-dir", type=Path, default=Path(DEFAULT_STATE))
    root.add_argument("--json", action="store_true")
    root.add_argument("--locale", choices=["en", "pl", "de"], default="pl")
    sub = root.add_subparsers(dest="command", required=True)
    for command in ("account", "list", "volumes"):
        sub.add_parser(command)
    for command in ("offers", "assess", "plan"):
        item = sub.add_parser(command)
        item.add_argument("--profile", type=Path, required=True)
        item.add_argument(
            "--sort", choices=["balanced", "price", "network", "reliability"]
        )
        item.add_argument("--country", action="append")
        preferences = item.add_mutually_exclusive_group()
        preferences.add_argument("--prefer-country", action="append")
        preferences.add_argument("--no-country-preference", action="store_true")
        item.add_argument("--min-download-mbps", type=float)
        item.add_argument("--min-upload-mbps", type=float)
        item.add_argument("--min-reliability", type=float)
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
        "provision",
        "ready",
        "benchmark",
        "costs",
    ):
        item = sub.add_parser(command)
        item.add_argument("--plan", required=True)
        if command in {"inspect", "provision"}:
            item.add_argument("--accept-new-host-key", action="store_true")
        if command in {"wait", "monitor"}:
            item.add_argument(
                "--timeout", type=int, default=120 if command == "wait" else 600
            )
        if command == "costs":
            item.add_argument(
                "--from-utc",
                type=datetime.fromisoformat,
                default=now() - timedelta(days=7),
            )
            item.add_argument("--to-utc", type=datetime.fromisoformat, default=now())
    item = sub.add_parser("compare")
    item.add_argument("reports", type=Path, nargs="+")
    return root


def workload_profile(args) -> WorkloadProfile:
    profile = WorkloadProfile.model_validate_json(args.profile.read_text())
    overrides = {
        field: getattr(args, argument)
        for field, argument in (
            ("sort_by", "sort"),
            ("countries", "country"),
            ("preferred_countries", "prefer_country"),
            ("min_download_mbps", "min_download_mbps"),
            ("min_upload_mbps", "min_upload_mbps"),
            ("min_reliability", "min_reliability"),
        )
        if getattr(args, argument, None) is not None
    }
    if args.no_country_preference:
        overrides["preferred_countries"] = []
    return WorkloadProfile.model_validate({**profile.model_dump(), **overrides})


def dispatch(args, service: Environments):
    command = args.command
    if command == "account":
        return service.client.account()
    if command == "list":
        return service.client.instances()
    if command == "volumes":
        return service.client.volumes()
    if command in {"offers", "assess", "plan"}:
        profile = workload_profile(args)
        if command == "offers":
            return [row.model_dump(mode="json") for row in service.search(profile)]
        if command == "assess":
            rows = service.client.offers(
                profile.disk_gb, {**search_filters(profile), "id": {"eq": args.offer}}
            )
            selected = [row for row in rows if row.get("id") == args.offer]
            if len(selected) != 1:
                raise VastError("vast.offer_expired")
            return assess(selected[0], profile).model_dump(mode="json")
        ssh = json.loads(args.ssh_profile.read_text())
        return service.plan(
            profile,
            args.offer,
            args.max_hourly,
            args.max_total,
            Path(ssh["identity_file"]),
            Path(ssh["known_hosts"]),
            args.finish,
        ).model_dump(mode="json")
    if command == "create":
        return service.create(args.plan).model_dump(mode="json")
    if command in {"status", "reconcile"}:
        return service.reconcile(args.plan).model_dump(mode="json")
    if command in {"start", "stop", "destroy"}:
        return service.change(args.plan, command).model_dump(mode="json")
    if command == "export":
        return service.export(args.plan)
    if command == "cleanup":
        return service.cleanup(args.plan).model_dump(mode="json")
    if command == "wait":
        return service.wait(args.plan, args.timeout).model_dump(mode="json")
    if command == "monitor":
        return monitor(service, args.plan, args.timeout)
    if command in {"inspect", "provision", "ready", "benchmark"}:
        return workload(
            service, args.plan, command, getattr(args, "accept_new_host_key", False)
        )
    if command == "costs":
        plan = service.journal.plan(args.plan)
        with service.journal.lock(args.plan):
            record = service.journal.record(args.plan)
            result = costs(service.client, plan, record, args.from_utc, args.to_utc)
            record.reports["costs"] = result
            service.journal.save_record(record)
        return result
    if command == "compare":
        reports = [json.loads(path.read_text()) for path in args.reports]
        return compare([r.get("result", r) for r in reports])
    raise VastError("vast.invalid_action")


def main(argv=None, client_factory=None) -> int:
    args = parser().parse_args(argv)
    # Must precede importing Settings, which resolves ENV_FILE at class creation.
    if args.env_file:
        os.environ["ENV_FILE"] = str(args.env_file.expanduser().resolve())
    client = None
    try:
        if args.command == "compare":
            reports = [json.loads(path.read_text()) for path in args.reports]
            result = compare([report.get("result", report) for report in reports])
        else:
            from venom_core.config import Settings

            env_options: dict[str, Any] = {
                "_env_file": os.environ.get("ENV_FILE") or ".env.dev"
            }
            settings = Settings(**env_options)
            client = (client_factory or VastClient)(settings.VAST_API_KEY)
            result = dispatch(args, Environments(client, Journal(args.state_dir)))
        output = {"ok": True, "result": result}
        code = 0
    except (
        VastError,
        ValidationError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        error = exc.code if isinstance(exc, VastError) else "vast.invalid_input"
        output = {"ok": False, "error": error}
        if isinstance(exc, VastError):
            output.update(http_status=exc.status, outcome_unknown=exc.ambiguous)
        code = 1
    finally:
        if client is not None:
            client.close()
    if not args.json:
        labels = json.loads((Path(__file__).parent / "messages.json").read_text())
        print(labels[args.locale]["ok" if output["ok"] else "error"])
    print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    return code
