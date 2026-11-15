"""Adopt explicitly prepared Vast VMs for text training campaigns."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path, PurePosixPath
from typing import Any

from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.infrastructure.providers.vast.client import VastClient, VastError
from venom_core.infrastructure.providers.vast.models import (
    EnvironmentPlan,
    EnvironmentRecord,
    amount,
    now,
)
from venom_core.services.vast_environments import billing
from venom_core.services.vast_environments.lifecycle import Environments
from venom_core.services.vast_environments.ssh import ssh_args
from venom_core.services.vast_environments.store import Journal
from venom_core.utils.runtime_state import runtime_state_root

_CLEANUP_RESERVE_SECONDS = 180
_RECEIPT_SUFFIX = ".academy-text.json"
_CLEANUP_SUFFIX = ".academy-text-cleanup.json"
_MICRO = Decimal(1_000_000)
_BYTES_PER_GB = Decimal(1_000_000_000)
_MISMATCH = "vast.text_instance_mismatch"
_NOT_READY = "vast.text_prepared_instance_required"


def _microusd(value: Decimal) -> int:
    return int((value * _MICRO).to_integral_value(rounding=ROUND_CEILING))


def _budget(plan: EnvironmentPlan, record: EnvironmentRecord, when: datetime) -> dict:
    submitted = record.submitted_at
    if submitted is None or submitted.tzinfo is None or submitted > when:
        raise VastError("vast.text_submission_missing")
    elapsed = Decimal(str((when - submitted).total_seconds()))
    quote = plan.assessment.quote
    hourly, transfer = quote.hourly_usd, quote.transfer_usd
    observed = amount(record.instance.get("dph_total"))
    if (
        hourly is None
        or transfer is None
        or not hourly.is_finite()
        or not transfer.is_finite()
        or hourly <= 0
        or transfer < 0
        or hourly > plan.max_hourly_usd
        or observed is None
        or observed > hourly
        or plan.profile.upload_gb <= 0
    ):
        raise VastError("vast.text_price_unverified")
    return {
        "elapsed": elapsed,
        "hourly": hourly,
        "transfer": transfer,
        "remaining_seconds": max(0, int(plan.profile.duration_minutes * 60 - elapsed)),
        "max_upload_bytes": int(plan.profile.upload_gb * _BYTES_PER_GB),
    }


def _bound_record(
    plan: EnvironmentPlan, record: EnvironmentRecord, instance: dict
) -> None:
    if (
        type(record.instance_id) is not int
        or record.instance_id <= 0
        or type(instance.get("id")) is not int
        or instance["id"] != record.instance_id
        or instance.get("label") != "venom-" + plan.plan_id
    ):
        raise VastError(_MISMATCH)
    for key in ("host_id", "machine_id"):
        expected, observed = plan.assessment.offer.get(key), instance.get(key)
        if (
            type(expected) is not int
            or expected <= 0
            or type(observed) is not int
            or observed != expected
        ):
            raise VastError(_MISMATCH)


def _remote_path(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 512
        and value.startswith("/")
        and value != "/"
        and all(32 <= ord(char) <= 126 for char in value)
        and ".." not in PurePosixPath(value).parts
    )


def _host_values(
    *, repo: str, python: str, root: str, commit: str, sandbox_manifest: str
) -> dict[str, str]:
    values = {
        "repo": repo,
        "python": python,
        "root": root,
        "sandbox_manifest": sandbox_manifest,
    }
    if (
        not all(_remote_path(value) for value in values.values())
        or not isinstance(commit, str)
        or not re.fullmatch(r"[a-f0-9]{40}", commit)
    ):
        raise VastError("vast.text_host_configuration_invalid")
    return {**values, "commit": commit}


def _assert_checks(result: dict) -> None:
    checks = result.get("checks")
    if (
        result.get("status") != "PASS"
        or not isinstance(checks, dict)
        or checks.get("writable") != "PASS"
        or checks.get("readonly") != "PASS"
        or result.get("gpu_used") is not False
        or result.get("model_loaded") is not False
    ):
        raise VastError("vast.text_sandbox_unqualified")


def _qualify_over_ssh(prefix: list[str], host: dict[str, str]) -> dict:
    repo, python = shlex.quote(host["repo"]), shlex.quote(host["python"])
    commit = shlex.quote(host["commit"])
    root = shlex.quote(host["root"])
    manifest = shlex.quote(host["sandbox_manifest"])
    command = (
        f'cd -- {repo} && test "$(git rev-parse HEAD)" = {commit} && '
        'test -z "$(git status --porcelain --untracked-files=no)" && '
        f"test -x {python} && test -d {root} && "
        f"exec {python} -m scripts.remote_training_host.check_sandbox --cases {manifest}"
    )
    try:
        result = subprocess.run(
            [*prefix, command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=150,
        )
        value = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        raise VastError("vast.text_sandbox_unqualified") from None
    if not isinstance(value, dict):
        raise VastError("vast.text_sandbox_unqualified")
    _assert_checks(value)
    return value


class VastTextRental:
    """Use the existing rental journal and only act on its exact prepared lease."""

    def __init__(self, journal: Journal, api_key: Any, *, client_factory=VastClient):
        self.journal = journal
        self.api_key = api_key
        self.client_factory = client_factory

    @classmethod
    def from_settings(cls) -> VastTextRental:
        from venom_core.config import SETTINGS

        return cls(Journal(runtime_state_root() / "vast"), SETTINGS.VAST_API_KEY)

    @contextmanager
    def _service(self) -> Iterator[Environments]:
        client = self.client_factory(self.api_key)
        try:
            yield Environments(client, self.journal)
        finally:
            client.close()

    def _plan(self, plan_id: str) -> EnvironmentPlan:
        plan = self.journal.plan(plan_id)
        profile = plan.profile
        if (
            plan.finish_policy not in {"destroy", "stop"}
            or not profile.vm_required
            or profile.mode != "inspect"
            or not profile.template_hash
            or not profile.template_configuration_sha256
            or plan.assessment.status != "eligible"
        ):
            raise VastError("vast.text_dedicated_vm_required")
        return plan

    def _qualification_path(self, plan: EnvironmentPlan, campaign_id: str) -> Path:
        if plan.finish_policy == "stop":
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", campaign_id):
                raise VastError("vast.text_campaign_invalid")
            return self.journal.path(plan.plan_id, f".{campaign_id}{_RECEIPT_SUFFIX}")
        return self.journal.path(plan.plan_id, _RECEIPT_SUFFIX)

    def _receipt(self, plan: EnvironmentPlan, campaign_id: str) -> dict:
        path = self._qualification_path(plan, campaign_id)
        try:
            if path.is_symlink() or path.stat().st_size > 32_768:
                raise ValueError
            value = json.loads(path.read_text())
        except (OSError, ValueError):
            raise VastError("vast.text_qualification_required") from None
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != 1
            or value.get("plan_sha256") != plan.checksum
            or type(value.get("instance_id")) is not int
            or value["instance_id"] <= 0
            or not isinstance(value.get("sandbox"), dict)
        ):
            raise VastError("vast.text_qualification_required")
        if value.get("campaign_id") != campaign_id:
            raise VastError("vast.text_campaign_mismatch")
        _assert_checks(value["sandbox"])
        _host_values(
            **{
                key: value.get(key, "")
                for key in ("repo", "python", "root", "commit", "sandbox_manifest")
            }
        )
        return value

    def qualify_prepared(
        self,
        plan_id: str,
        *,
        campaign_id: str,
        repo: str,
        python: str,
        root: str,
        commit: str,
        sandbox_manifest: str,
    ) -> dict:
        """Operator entry point after bootstrap and pinning the SSH host key."""
        ensure_data_mutation_allowed("academy_text_vast_qualify")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", campaign_id):
            raise VastError("vast.text_campaign_invalid")
        host = _host_values(
            repo=repo,
            python=python,
            root=root,
            commit=commit,
            sandbox_manifest=sandbox_manifest,
        )
        plan = self._plan(plan_id)
        path = self._qualification_path(plan, campaign_id)
        if path.exists():
            receipt = self._receipt(plan, campaign_id)
            if any(receipt[key] != value for key, value in host.items()):
                raise VastError("vast.text_qualification_changed")
            return receipt
        with self._service() as service:
            record = service.reconcile(plan_id)
        self._verify_running(plan, record)
        checks = _qualify_over_ssh(ssh_args(plan, record.instance), host)
        receipt = {
            "schema_version": 1,
            "campaign_id": campaign_id,
            "plan_sha256": plan.checksum,
            "instance_id": record.instance_id,
            **host,
            "sandbox": checks,
            "qualified_at": now().isoformat(),
        }
        with self.journal.lock(plan_id):
            if path.exists() or path.is_symlink():
                raise VastError("vast.text_qualification_exists")
            fresh = self.journal.record(plan_id)
            self._verify_running(plan, fresh)
            if fresh.instance_id != record.instance_id:
                raise VastError(_MISMATCH)
            self.journal.write(path, receipt)
        return receipt

    @staticmethod
    def _verify_running(plan: EnvironmentPlan, record: EnvironmentRecord) -> None:
        if record.state != "running" or record.pending_action is not None:
            raise VastError(_NOT_READY)
        _bound_record(plan, record, record.instance)
        _budget(plan, record, now())

    def validate(
        self,
        plan_id: str,
        max_seconds: int,
        max_cost_microusd: int,
        *,
        campaign_id: str,
    ) -> dict:
        """Read the local journal without allocating resources or contacting Vast."""
        plan = self._plan(plan_id)
        receipt = self._receipt(plan, campaign_id)
        record = self.journal.record(plan_id)
        self._verify_running(plan, record)
        if record.instance_id != receipt["instance_id"]:
            raise VastError(_MISMATCH)
        quote = _budget(plan, record, now())
        if (
            type(max_seconds) is not int
            or not _CLEANUP_RESERVE_SECONDS < max_seconds <= quote["remaining_seconds"]
        ):
            raise VastError("vast.text_duration_exceeds_plan")
        estimated = (quote["elapsed"] + max_seconds) * quote["hourly"] / 3600 + quote[
            "transfer"
        ]
        if (
            type(max_cost_microusd) is not int
            or not _microusd(estimated) <= max_cost_microusd
            or estimated > plan.max_total_usd
        ):
            raise VastError("vast.text_budget_exceeded")
        return {
            "state": "prepared",
            "instance_id": record.instance_id,
            "currency": "USD",
            "estimated_microusd": _microusd(estimated),
            "hourly_microusd": _microusd(quote["hourly"]),
            "transfer_microusd": _microusd(quote["transfer"]),
            "remaining_seconds": quote["remaining_seconds"],
            "cleanup_reserve_seconds": _CLEANUP_RESERVE_SECONDS,
            "max_upload_bytes": quote["max_upload_bytes"],
            **{key: receipt[key] for key in ("repo", "python", "root", "commit")},
        }

    def acquire(self, plan_id: str, *, campaign_id: str) -> dict:
        plan = self._plan(plan_id)
        receipt = self._receipt(plan, campaign_id)
        with self._service() as service:
            record = service.reconcile(plan_id)
        self._verify_running(plan, record)
        if record.instance_id != receipt["instance_id"]:
            raise VastError(_MISMATCH)
        return {
            "state": "running",
            "instance_id": record.instance_id,
            **{key: receipt[key] for key in ("repo", "python", "root", "commit")},
        }

    def ssh_prefix(self, plan_id: str, *, campaign_id: str) -> list[str]:
        plan = self._plan(plan_id)
        receipt = self._receipt(plan, campaign_id)
        record = self.journal.record(plan_id)
        self._verify_running(plan, record)
        if record.instance_id != receipt["instance_id"]:
            raise VastError(_MISMATCH)
        return ssh_args(plan, record.instance)

    def _observe_closed(
        self, service: Environments, plan: EnvironmentPlan, instance_id: int
    ) -> bool:
        try:
            service.client.instance(instance_id)
        except VastError as error:
            if error.status not in {404, 410}:
                raise
        else:
            return False
        rows = service.client.instances()
        if any(type(row.get("id")) is not int or row["id"] <= 0 for row in rows):
            raise VastError("vast.invalid_inventory")
        if any(
            row["id"] == instance_id or row.get("label") == "venom-" + plan.plan_id
            for row in rows
        ):
            return False
        host_id = plan.assessment.offer["host_id"]
        # The volume API exposes host, not instance ownership. Unmatched storage
        # on the same host cannot be proven safe to delete or ignore.
        if any(
            type(row.get("host_id")) is not int or row["host_id"] == host_id
            for row in service.client.volumes()
        ):
            raise VastError("vast.text_volume_cleanup_unverified")
        return True

    def cleanup(self, plan_id: str, *, campaign_id: str) -> dict:
        """Apply the rental's finish policy and confirm its state with the provider."""
        ensure_data_mutation_allowed("academy_text_vast_cleanup")
        plan = self._plan(plan_id)
        receipt = self._receipt(plan, campaign_id)
        instance_id = receipt["instance_id"]
        # Serialize our cleanup attempts across processes while the native
        # lifecycle service takes its own per-plan journal lock.
        cleanup_locks = Journal(self.journal.root / "academy-text-cleanup-locks")
        with cleanup_locks.lock(plan_id):
            if plan.finish_policy == "stop":
                return self._park(plan, instance_id)
            closed = self._closed_at(plan_id, instance_id)
            result = {"state": "cleanup_pending", "instance_id": instance_id}
            try:
                with self._service() as service:
                    if self._cleanup(service, plan, instance_id):
                        result["state"] = "destroyed"
                    else:
                        result["error"] = "vast.cleanup_unconfirmed"
            except (OSError, VastError) as error:
                result["error"] = (
                    error.code
                    if isinstance(error, VastError)
                    else "vast.cleanup_io_error"
                )
            result["checked_at"] = now().isoformat()
            if result["state"] == "destroyed" and closed is None:
                closed = datetime.fromisoformat(result["checked_at"])
            if closed is not None:
                result["closed_at"] = closed.isoformat()
            self.journal.write(self.journal.path(plan_id, _CLEANUP_SUFFIX), result)
            return result

    def _park(self, plan: EnvironmentPlan, instance_id: int) -> dict:
        with self._service() as service:
            record = service.reconcile(plan.plan_id)
            _bound_record(plan, record, record.instance)
            if record.state != "stopped" and record.pending_action is None:
                service.cleanup(plan.plan_id)
                record = service.reconcile(plan.plan_id)
            _bound_record(plan, record, record.instance)
            stopped = record.state == "stopped" and record.pending_action is None
        return {
            "state": "stopped" if stopped else "cleanup_pending",
            "instance_id": instance_id,
            "checked_at": now().isoformat(),
        }

    def _closed_at(self, plan_id: str, instance_id: int) -> datetime | None:
        path = self.journal.path(plan_id, _CLEANUP_SUFFIX)
        try:
            if path.is_symlink() or path.stat().st_size > 4096:
                return None
            saved = json.loads(path.read_text())
            if not isinstance(saved, dict) or saved.get("instance_id") != instance_id:
                return None
            closed = saved.get("closed_at", saved.get("checked_at"))
            if not isinstance(closed, str):
                return None
            if "closed_at" not in saved and saved.get("state") != "destroyed":
                return None
            observed = datetime.fromisoformat(closed)
            return observed if observed.tzinfo is not None else None
        except (OSError, ValueError):
            return None

    def _cleanup(
        self, service: Environments, plan: EnvironmentPlan, instance_id: int
    ) -> bool:
        record = self.journal.record(plan.plan_id)
        if record.instance_id != instance_id:
            raise VastError(_MISMATCH)
        try:
            current = service.reconcile(plan.plan_id)
        except VastError as error:
            if error.status not in {404, 410}:
                raise
            return self._observe_closed(service, plan, instance_id)
        if current.state == "destroyed":
            return self._observe_closed(service, plan, instance_id)
        _bound_record(plan, current, current.instance)
        if current.pending_action == "destroy":
            return False
        # Export before deletion, as required by the shared Vast lifecycle.
        service.cleanup(plan.plan_id)
        current = service.reconcile(plan.plan_id)
        return current.state == "destroyed" and self._observe_closed(
            service, plan, instance_id
        )

    def cost(self, plan_id: str, *, campaign_id: str) -> dict:
        """Return attributable provider charges separately from quote exposure."""
        plan = self._plan(plan_id)
        receipt = self._receipt(plan, campaign_id)
        record = self.journal.record(plan_id)
        if record.instance_id != receipt["instance_id"] or record.submitted_at is None:
            raise VastError(_MISMATCH)
        checked_at = now()
        closed = self._closed_at(plan_id, receipt["instance_id"])
        end_of_estimate = (
            closed
            if closed is not None and record.submitted_at <= closed <= checked_at
            else checked_at
        )
        quote = _budget(plan, record, end_of_estimate)
        result: dict[str, Any] = {
            "currency": "USD",
            "estimated_microusd": _microusd(
                quote["elapsed"] * quote["hourly"] / 3600 + quote["transfer"]
            ),
            "billed_microusd": None,
            "billing_status": "unavailable",
        }
        try:
            with self._service() as service:
                costs = billing.costs(
                    service.client, plan, record, record.submitted_at, checked_at
                )
        except (VastError, OSError):
            return result
        reported = costs["provider_reported"]
        billed = amount(reported["usd"])
        if billed is not None:
            result["billed_microusd"] = _microusd(billed)
        result["billing_status"] = (
            "partial" if reported["unknown_amounts"] else costs["status"]
        )
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_id")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--sandbox-manifest", required=True)
    finish = parser.add_mutually_exclusive_group(required=True)
    finish.add_argument("--authorize-destroy", action="store_true")
    finish.add_argument("--authorize-stop", action="store_true")
    arguments = vars(parser.parse_args())
    authorization = "stop" if arguments.pop("authorize_stop") else "destroy"
    arguments.pop("authorize_destroy")
    try:
        rental = VastTextRental.from_settings()
        if rental._plan(arguments["plan_id"]).finish_policy != authorization:
            raise VastError("vast.text_finish_policy_mismatch")
        print(json.dumps(rental.qualify_prepared(**arguments)))
    except VastError as error:
        parser.exit(1, error.code + "\n")
    except (OSError, ValueError):
        parser.exit(1, "vast.text_qualification_failed\n")


if __name__ == "__main__":
    main()
