"""Run the Academy text campaign worker on a prepared, verified SSH host."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Annotated, BinaryIO, Callable

from pydantic import Field, TypeAdapter

from venom_core.services.remote_training.client import validate_run_id
from venom_core.services.remote_training.paths import data_directory, operator_path
from venom_core.services.remote_training.transport import (
    MAX_RPC_BYTES,
    TransportError,
    decode_reply,
    execute_ssh,
)

from .campaign import CampaignService
from .campaign_schema import CampaignId, CampaignSpec, Digest
from .profiles import load_profile
from .service import ExperimentService

_MODULE = "venom_core.services.training_experiments.remote_text_host"
_MAX_ARCHIVE_BYTES = 2**40
_CAMPAIGN_ID: TypeAdapter[str] = TypeAdapter(Annotated[CampaignId, Field(strict=True)])
_DIGEST: TypeAdapter[str] = TypeAdapter(Annotated[Digest, Field(strict=True)])
_ACTIONS = {
    "plan": {"spec", "expected_profile_identity"},
    "start": {"campaign_id", "plan_sha256", "cutoff_at"},
    "status": {"campaign_id"},
    "resume": {"campaign_id"},
    "stop": {"campaign_id"},
    "fetch": {"campaign_id", "run_id"},
}


def _remote_path(value: str, field: str) -> str:
    path = PurePosixPath(value)
    if (
        not path.is_absolute()
        or len(path.parts) < 3
        or path.as_posix() != value
        or ".." in path.parts
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError(f"remote_text_{field}_invalid")
    return value


def _payload_bytes(payload: dict) -> bytes:
    raw = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
    if len(raw) > MAX_RPC_BYTES:
        raise ValueError("remote_text_rpc_too_large")
    return raw


class RemoteTextHost:
    """Use a trusted prefix from the provider's strict SSH configuration."""

    def __init__(
        self,
        ssh_prefix: list[str],
        python: str,
        repo: str,
        root: str,
        *,
        request_timeout: int = 60,
        expected_commit: str | None = None,
        executor: Callable[..., tuple[int, bytes]] = execute_ssh,
    ) -> None:
        if (
            not ssh_prefix
            or ssh_prefix[0] != "ssh"
            or "StrictHostKeyChecking=yes" not in ssh_prefix
            or "BatchMode=yes" not in ssh_prefix
        ):
            raise ValueError("remote_text_ssh_unverified")
        if not re.fullmatch(
            r"(?:/[A-Za-z0-9_.-]+)+/(?:python(?:3(?:\.\d+)?)?|rpc-python)", python
        ):
            raise ValueError("remote_text_python_invalid")
        if type(request_timeout) is not int or not 1 <= request_timeout <= 60:
            raise ValueError("remote_text_request_timeout_invalid")
        if expected_commit is not None and not re.fullmatch(
            r"[a-f0-9]{40}", expected_commit
        ):
            raise ValueError("remote_text_commit_invalid")
        self._ssh = [ssh_prefix[0], "-T", *ssh_prefix[1:]]
        self._repo = _remote_path(repo, "repo")
        self._python = _remote_path(python, "python")
        self._root = _remote_path(root, "root")
        self._request_timeout = request_timeout
        self._expected_commit = expected_commit
        self._execute = executor

    def _command(self, action: str) -> list[str]:
        command = shlex.join(
            [self._python, "-m", _MODULE, "--root", self._root, action]
        )
        steps = [f"cd {shlex.quote(self._repo)}"]
        if self._expected_commit is not None:
            steps.extend(
                [
                    f'test "$(git rev-parse --verify HEAD)" = {self._expected_commit}',
                    "tracked_status=$(git status --porcelain --untracked-files=no)",
                    'test -z "$tracked_status"',
                ]
            )
        optuna = shlex.quote(f"{self._repo}/.venv-optuna/bin/python")
        steps.append(
            f"exec env RUNTIME_ADMISSION_ENABLED=true VENOM_OPTUNA_PYTHON={optuna} {command}"
        )
        return [*self._ssh, " && ".join(steps)]

    def _request(self, action: str, payload: dict) -> dict:
        return decode_reply(
            *self._execute(
                self._command(action),
                _payload_bytes(payload),
                self._request_timeout,
                MAX_RPC_BYTES,
            )
        )

    def plan(self, spec: dict, *, expected_profile_identity: str | None = None) -> dict:
        return self._request(
            "plan",
            {"spec": spec, "expected_profile_identity": expected_profile_identity},
        )

    def start(
        self, campaign_id: str, plan_sha256: str, *, cutoff_at: float | None = None
    ) -> dict:
        return self._request(
            "start",
            {
                "campaign_id": campaign_id,
                "plan_sha256": plan_sha256,
                "cutoff_at": cutoff_at,
            },
        )

    def status(self, campaign_id: str) -> dict:
        return self._request("status", {"campaign_id": campaign_id})

    def resume(self, campaign_id: str) -> dict:
        return self._request("resume", {"campaign_id": campaign_id})

    def stop(self, campaign_id: str) -> dict:
        return self._request("stop", {"campaign_id": campaign_id})

    def fetch(
        self,
        campaign_id: str,
        run_id: str,
        destination: Path,
        max_bytes: int,
        *,
        timeout: int | None = None,
    ) -> dict:
        """Download into a private temporary file and publish on complete transfer."""
        seconds = 120 if timeout is None else timeout
        if type(seconds) is not int or not 1 <= seconds <= 600:
            raise ValueError("remote_text_fetch_timeout_invalid")
        if type(max_bytes) is not int or not 1 <= max_bytes <= _MAX_ARCHIVE_BYTES:
            raise ValueError("remote_text_fetch_limit_invalid")
        destination = operator_path(destination)
        payload = _payload_bytes({"campaign_id": campaign_id, "run_id": run_id})
        with tempfile.NamedTemporaryFile(mode="w+b", dir=destination.parent) as partial:
            code, _ = self._execute(
                self._command("fetch"), payload, seconds, max_bytes, sink=partial
            )
            size = partial.tell()
            if code != 0 or not 0 < size <= max_bytes:
                raise TransportError("remote_text_fetch_failed", retryable=True)
            partial.flush()
            partial.seek(0)
            sha256 = hashlib.file_digest(partial, "sha256").hexdigest()
            os.fsync(partial.fileno())
            # Link publishes once and preserves evidence from a previous attempt.
            with data_directory(destination.parent) as directory_fd:
                os.link(partial.name, destination.name, dst_dir_fd=directory_fd)
                os.fsync(directory_fd)
        return {"sha256": sha256, "size": size}


def _plan(service: CampaignService, payload: dict) -> dict:
    spec = CampaignSpec.model_validate(payload.get("spec"))
    if spec.review_mode != "automatic":
        raise ValueError("remote_text_automatic_review_required")
    expected = payload.get("expected_profile_identity")
    if expected is not None:
        _, identity = load_profile(service.experiments.root, spec.profile_id)
        if identity != _DIGEST.validate_python(expected):
            raise ValueError("remote_text_profile_changed")
    return service.plan(spec)


def _dispatch(service: CampaignService, action: str, payload: dict) -> dict:
    if action == "plan":
        return _plan(service, payload)
    campaign_id = _CAMPAIGN_ID.validate_python(payload.get("campaign_id"))
    if action == "status":
        return service.status(campaign_id)
    if action == "start":
        cutoff = payload.get("cutoff_at")
        if (
            not isinstance(cutoff, (int, float))
            or isinstance(cutoff, bool)
            or not math.isfinite(cutoff)
            or cutoff <= 0
        ):
            raise ValueError("remote_text_cutoff_required")
        return service.start(
            campaign_id,
            _DIGEST.validate_python(payload.get("plan_sha256")),
            cutoff_at=cutoff,
        )
    state = service.status(campaign_id)
    if state.get("cutoff_at") is None:
        raise ValueError("remote_text_campaign_not_started")
    if action == "resume":
        return service.resume(campaign_id)
    return service.stop(campaign_id)


def _error_code(error: Exception) -> str:
    code = str(error).partition(":")[0]
    if re.fullmatch(r"(?:remote_text|experiment|campaign)_[a-z0-9_]{1,80}", code):
        return code
    if isinstance(error, FileNotFoundError):
        return "remote_text_not_found"
    return "remote_text_operation_failed"


def serve(root: Path, action: str, raw: bytes, output: BinaryIO) -> int:
    """Read one bounded request. The artifact response is a binary stream."""
    try:
        if len(raw) > MAX_RPC_BYTES:
            raise ValueError("remote_text_rpc_too_large")
        payload = json.loads(raw)
        if (
            action not in _ACTIONS
            or not isinstance(payload, dict)
            or set(payload) - _ACTIONS[action]
        ):
            raise ValueError("remote_text_rpc_invalid")
        service = CampaignService(ExperimentService(root))
        if action == "fetch":
            from .remote_text_evidence import export_run

            export_run(
                service,
                _CAMPAIGN_ID.validate_python(payload.get("campaign_id")),
                validate_run_id(payload.get("run_id")),
                output,
            )
            return 0
        reply = _payload_bytes(
            {"ok": True, "result": _dispatch(service, action, payload)}
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        OverflowError,
    ) as error:
        if action == "fetch":
            return 1
        reply = _payload_bytes({"ok": False, "error": _error_code(error)})
    output.write(reply)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("action", choices=sorted(_ACTIONS))
    args = parser.parse_args(argv)
    return serve(
        args.root,
        args.action,
        sys.stdin.buffer.read(MAX_RPC_BYTES + 1),
        sys.stdout.buffer,
    )


if __name__ == "__main__":
    raise SystemExit(main())
