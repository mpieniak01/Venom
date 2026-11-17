"""Seal Academy development results and keep verified copies outside a GPU host."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import tarfile
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import IO, TYPE_CHECKING, BinaryIO, Iterator, Protocol, Self

from scripts.academy.omni_pl_chat_p1 import CHECKPOINT_FILES
from venom_core.services.remote_training.bundles import MAX_BYTES, canonical
from venom_core.services.remote_training.lifecycle import (
    atomic_json,
    file_lock,
    validate_run_id,
)
from venom_core.services.remote_training.paths import data_directory, operator_path

from .calibration import JUDGES, validate_calibration
from .checkpoint_evaluation import GENERATION_OUTPUTS, GENERATION_SEAL, read_generation
from .evidence import ADAPTER_FILES, WEIGHTS, inspect_checkpoint, latest_checkpoint
from .profiles import MAX_JSON_BYTES, digest, read_json, stable_hash
from .quality_native import evaluation_identity

if TYPE_CHECKING:
    from .campaign import CampaignService

_BUNDLE = "bundle.json"
_ARCHIVE = "evidence.tar"
_RECEIPT = "verified.json"
_ATTEMPT_RE = re.compile(r"attempt-[1-9][0-9]{0,5}[.]log")
_GEN_RE = r"(?:evaluation-[1-9][0-9]{0,5}|checkpoint-evaluations/[1-9][0-9]{0,7})"
_TRAIN_RE = r"training/checkpoint-[1-9][0-9]{0,7}"
_METRIC_FILES = {
    "training/control.json",
    "training/initial.json",
    "training/resume.json",
}
_EVAL_FILES = frozenset(
    (
        *GENERATION_OUTPUTS,
        GENERATION_SEAL,
        "manifest.json",
        "judgments.json",
        "result.json",
        "result-seal.json",
    )
)
_CHECKPOINT_FILES = frozenset((*CHECKPOINT_FILES, "hashes.json"))
_ROOT_FILES = frozenset(
    ("manifest.json", "recipe.json", "result.json", "result-seal.json")
)
_MAX_MEMBERS = 128


class _RegularTarInfo(tarfile.TarInfo):
    @classmethod
    def fromtarfile(cls, archive: tarfile.TarFile) -> Self:
        """Reject extension/link headers before tarfile allocates or recurses."""
        stream = archive.fileobj
        if stream is None:
            raise ValueError("remote_text_evidence_file_invalid")
        offset = stream.tell()
        header = stream.read(tarfile.BLOCKSIZE)
        if len(header) == tarfile.BLOCKSIZE and any(header):
            if header[156:157] != tarfile.REGTYPE:
                raise ValueError("remote_text_evidence_member_invalid")
        stream.seek(offset)
        return super().fromtarfile(archive)


class EvidenceHost(Protocol):
    def fetch(
        self,
        campaign_id: str,
        run_id: str,
        destination: Path,
        max_bytes: int,
        *,
        timeout: int | None = None,
    ) -> dict: ...


def _sha(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("remote_text_evidence_digest_invalid")
    return value


def _attempt(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 999999:
        raise ValueError("remote_text_evidence_attempt_invalid")
    return value


def _step(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 99999999:
        raise ValueError("remote_text_evidence_step_invalid")
    return value


def _trial(state: dict, run_id: str) -> dict:
    validate_run_id(run_id)
    validate_run_id(state["campaign_id"])
    trial = next((row for row in state["trials"] if row["run_id"] == run_id), None)
    if trial is None or not trial.get("result_sha256"):
        raise ValueError("remote_text_evidence_result_unavailable")
    return trial


def _safe_member(name: str) -> bool:
    parent, _, leaf = name.rpartition("/")
    return bool(
        name in _ROOT_FILES
        or name in _METRIC_FILES
        or _ATTEMPT_RE.fullmatch(name)
        or (leaf in _EVAL_FILES and re.fullmatch(_GEN_RE, parent))
        or (leaf in _CHECKPOINT_FILES and re.fullmatch(_TRAIN_RE, parent))
    )


@contextmanager
def _regular(path: Path) -> Iterator[tuple[BinaryIO, int]]:
    with data_directory(path.parent) as directory:
        fd = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("remote_text_evidence_file_invalid")
        yield stream, info.st_size


def _file_identity(path: Path) -> dict:
    with _regular(path) as (stream, size):
        return {"sha256": _digest_stream(stream), "size": size}


def _digest_stream(stream: IO[bytes]) -> str:
    checksum = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        checksum.update(chunk)
    return checksum.hexdigest()


def _generation(attempt: int, step: int | None) -> str:
    return f"evaluation-{attempt}" if step is None else f"checkpoint-evaluations/{step}"


def _expected_steps(trial: dict) -> dict[int, str]:
    return {
        _step(row["step"]): _sha(row["result_sha256"])
        for row in trial.get("checkpoint_evaluations", ())
        if row.get("status") == "succeeded" and row.get("result_sha256")
    }


def _source_entries(
    directory: Path, trial: dict, attempt: int, result: dict
) -> tuple[set[str], int | None]:
    names = set(_ROOT_FILES)
    expected_steps = _expected_steps(trial)
    if result.get("checkpoint_evaluations") and not expected_steps:
        raise ValueError("remote_text_evidence_checkpoint_evaluation_missing")
    steps: list[int | None] = [*expected_steps] if expected_steps else [None]
    for step in steps:
        name = _generation(attempt, step)
        generation = directory / name
        read_generation(generation)
        eval_names = (
            _EVAL_FILES
            if step is not None
            else _EVAL_FILES - {"result.json", "result-seal.json"}
        )
        names.update(f"{name}/{item}" for item in eval_names)
        report = result if step is None else read_json(generation / "result.json")
        expected = report["checkpoint"]
        number = _step(expected["step"])
        if step is not None and step != number:
            raise ValueError("remote_text_evidence_checkpoint_step_mismatch")
        checkpoint = f"training/checkpoint-{number}"
        if not (directory / checkpoint).exists():
            continue
        if inspect_checkpoint(directory / checkpoint)["sha256"] != expected["sha256"]:
            raise ValueError("remote_text_evidence_checkpoint_changed")
        names.update(f"{checkpoint}/{item}" for item in (*ADAPTER_FILES, "hashes.json"))
    latest = latest_checkpoint(directory / "training", resume=True)
    resume_step = None
    if latest is not None:
        resume_path, info = latest
        resume_step = _step(info["step"])
        names.update(
            f"training/{resume_path.name}/{item}" for item in _CHECKPOINT_FILES
        )
    optional = _METRIC_FILES | {f"attempt-{attempt}.log"}
    names.update(name for name in optional if (directory / name).exists())
    return names, resume_step


def _add_metadata(archive: tarfile.TarFile, body: dict) -> None:
    payload = canonical(body)
    info = tarfile.TarInfo(_BUNDLE)
    info.size = len(payload)
    info.mode = 0o600
    archive.addfile(info, io.BytesIO(payload))


def export_run(
    service: CampaignService, campaign_id: str, run_id: str, output: BinaryIO
) -> None:
    """Stream explicit immutable run evidence and any available checkpoint files."""
    state = service.status(campaign_id)
    trial = _trial(state, run_id)
    experiments = service.experiments
    with experiments.run_lock(run_id):
        directory = operator_path(experiments.run_dir(run_id))
        run = read_json(directory / "state.json")
        if run["campaign_id"] != campaign_id or run["status"] != "succeeded":
            raise ValueError("remote_text_evidence_run_identity_mismatch")
        attempt = _attempt(run["attempt"])
        result = read_json(directory / "result.json")
        if digest(directory / "result.json") != _sha(trial["result_sha256"]):
            raise ValueError("remote_text_evidence_result_changed")
        names, resume_step = _source_entries(directory, trial, attempt, result)
        files = {name: _file_identity(directory / name) for name in sorted(names)}
        body = {
            "schema_version": 1,
            "campaign_id": campaign_id,
            "run_id": run_id,
            "attempt": attempt,
            "plan_sha256": _sha(state["plan"]["plan_sha256"]),
            "profile_identity": _sha(state["plan"]["profile_identity"]),
            "result_sha256": trial["result_sha256"],
            "latest_resume_step": resume_step,
            "files": files,
        }
        with tarfile.open(
            fileobj=output, mode="w|", format=tarfile.USTAR_FORMAT
        ) as archive:
            _add_metadata(archive, body)
            for name, entry in files.items():
                with _regular(directory / name) as (stream, size):
                    if size != entry["size"]:
                        raise ValueError("remote_text_evidence_file_changed")
                    info = tarfile.TarInfo(name)
                    info.size = size
                    info.mode = 0o600
                    archive.addfile(info, stream)


def _read_metadata(archive: tarfile.TarFile, member: tarfile.TarInfo) -> dict:
    if member.size > MAX_JSON_BYTES:
        raise ValueError("remote_text_evidence_metadata_too_large")
    stream = archive.extractfile(member)
    if stream is None:
        raise ValueError("remote_text_evidence_file_invalid")
    with stream:
        raw = json.load(stream)
    if not isinstance(raw, dict):
        raise ValueError("remote_text_evidence_metadata_invalid")
    return raw


def _verify_members(
    archive: tarfile.TarFile, files: dict
) -> dict[str, tarfile.TarInfo]:
    members = {}
    for _ in files:
        member = archive.next()
        if (
            member is None
            or not member.isfile()
            or member.issparse()
            or member.name in members
        ):
            raise ValueError("remote_text_evidence_member_invalid")
        entry = files.get(member.name)
        if not isinstance(entry, dict) or member.size != entry.get("size"):
            raise ValueError("remote_text_evidence_member_mismatch")
        stream = archive.extractfile(member)
        if stream is None:
            raise ValueError("remote_text_evidence_file_invalid")
        with stream:
            if _digest_stream(stream) != _sha(entry.get("sha256")):
                raise ValueError("remote_text_evidence_file_changed")
        members[member.name] = member
    # A valid prefix with an unreadable or truncated tail is incomplete.
    source = archive.fileobj
    if source is None:
        raise ValueError("remote_text_evidence_file_invalid")
    source.seek(archive.offset)
    terminator_size = tarfile.BLOCKSIZE * 2
    tail = source.read(tarfile.RECORDSIZE + terminator_size)
    if len(tail) < terminator_size or any(tail) or source.read(1):
        raise ValueError("remote_text_evidence_unlisted_member")
    return members


def _verified_result(
    metadata: Callable[[str], dict],
    name: str,
    result_sha: str,
    files: dict,
    manifest: dict,
) -> dict:
    result_key = f"{name}/result.json" if name else "result.json"
    seal_key = f"{name}/result-seal.json" if name else "result-seal.json"
    if (
        files[result_key]["sha256"] != result_sha
        or metadata(seal_key)["result_sha256"] != result_sha
    ):
        raise ValueError("remote_text_evidence_result_changed")
    result = metadata(result_key)
    if (
        result["run_id"] != manifest["run_id"]
        or result["profile_identity"] != manifest["profile_identity"]
        or result["manifest_sha256"] != stable_hash(manifest)
        or result["dev_sha256"] != manifest["profile"]["dev_sha256"]
        or result.get("historical")
    ):
        raise ValueError("remote_text_evidence_result_identity_mismatch")
    return result


def _verify_generation(
    metadata: Callable[[str], dict],
    name: str,
    files: dict,
    result: dict,
    manifest: dict,
) -> dict:
    seal_name = f"{name}/{GENERATION_SEAL}"
    seal = metadata(seal_name)
    generation = metadata(f"{name}/manifest.json")
    if (
        files[seal_name]["sha256"] != result["generation_sha256"]
        or files[f"{name}/judgments.json"]["sha256"] != result["judgment_sha256"]
        or any(
            files[f"{name}/{key}"]["sha256"] != seal[key]
            for key in (*GENERATION_OUTPUTS, "manifest.json")
        )
        or generation["outputs"] != {key: seal[key] for key in GENERATION_OUTPUTS}
        or generation["generation_mode"] != "text"
        or generation["data_sha256"] != result["dev_sha256"]
        or generation["model_repo"] != manifest["profile"]["model"]
        or generation["models"][f"checkpoint-{_step(result['checkpoint']['step'])}"][
            WEIGHTS
        ]
        != result["checkpoint"]["sha256"]
    ):
        raise ValueError("remote_text_evidence_generation_changed")
    return evaluation_identity(
        generation,
        _sha(manifest["profile"]["calibration_sha256"]),
        calibration=manifest["calibration"],
    )


def _metrics(summaries: dict) -> tuple[float, float]:
    base, candidate = (summaries[name]["total"] for name in ("base", "candidate"))
    count = base["n"]
    if type(count) is not int or count < 1 or candidate["n"] != count:
        raise ValueError("remote_text_evidence_coverage_invalid")
    for row in (base, candidate):
        if any(
            type(row[key]) is not int or not 0 <= row[key] <= count
            for key in ("usable", "critical")
        ):
            raise ValueError("remote_text_evidence_metrics_invalid")
    return (candidate["usable"] - base["usable"]) / count, (
        candidate["critical"] - base["critical"]
    ) / count


def _verified_checkpoint(
    metadata: Callable[[str], dict], files: dict, step: int, expected: str | None
) -> dict | None:
    root = f"training/checkpoint-{step}"
    weights = files.get(f"{root}/{WEIGHTS}")
    if weights is None and expected is not None:
        # Retired weights can leave valid development metrics, but no candidate.
        return None
    receipt = metadata(f"{root}/hashes.json")
    names = ADAPTER_FILES if expected is not None else CHECKPOINT_FILES
    if (
        set(receipt) != set(CHECKPOINT_FILES)
        or (expected is not None and receipt[WEIGHTS] != expected)
        or any(
            files[f"{root}/{name}"]["sha256"] != _sha(receipt[name]) for name in names
        )
        or (
            expected is None
            and metadata(f"{root}/trainer_state.json").get("global_step") != step
        )
    ):
        raise ValueError("remote_text_evidence_checkpoint_changed")
    return {"step": step, "sha256": receipt[WEIGHTS]}


def _checkpoint_row(
    metadata: Callable[[str], dict],
    files: dict,
    name: str,
    result: dict,
    manifest: dict,
    step: int,
) -> dict:
    identity = _verify_generation(metadata, name, files, result, manifest)
    usable, critical = _metrics(result["summaries"])
    if result["checkpoint"]["step"] != step:
        raise ValueError("remote_text_evidence_checkpoint_step_mismatch")
    checkpoint = _verified_checkpoint(
        metadata, files, step, _sha(result["checkpoint"]["sha256"])
    )
    return {
        "step": step,
        "sha256": result["checkpoint"]["sha256"],
        "adapter_available": checkpoint is not None,
        "identity": identity,
        "summaries": result["summaries"],
        "usable_delta": usable,
        "critical_delta": critical,
    }


def _restore_evidence(
    archive: tarfile.TarFile, body: dict, state: dict, trial: dict, max_bytes: int
) -> dict:
    attempt = _attempt(body["attempt"])
    plan = state["plan"]
    if (
        body["schema_version"] != 1
        or body["campaign_id"] != state["campaign_id"]
        or body["run_id"] != trial["run_id"]
        or _sha(body["plan_sha256"]) != plan["plan_sha256"]
        or _sha(body["profile_identity"]) != plan["profile_identity"]
        or _sha(body["result_sha256"]) != trial["result_sha256"]
        or (trial.get("attempt") is not None and attempt != trial["attempt"])
    ):
        raise ValueError("remote_text_evidence_identity_mismatch")
    files = body["files"]
    if (
        not isinstance(files, dict)
        or not _ROOT_FILES <= files.keys()
        or not 1 <= len(files) <= _MAX_MEMBERS
        or any(
            not _safe_member(name)
            or not isinstance(entry, dict)
            or type(entry.get("size")) is not int
            or not 0 <= entry["size"] <= max_bytes
            for name, entry in files.items()
        )
        or sum(entry["size"] for entry in files.values()) > max_bytes
    ):
        raise ValueError("remote_text_evidence_manifest_invalid")
    members = _verify_members(archive, files)

    def metadata(name: str) -> dict:
        return _read_metadata(archive, members[name])

    manifest = metadata("manifest.json")
    if (
        manifest["run_id"] != body["run_id"]
        or manifest["campaign_id"] != body["campaign_id"]
        or manifest["profile_identity"] != body["profile_identity"]
        or manifest["recipe"] != metadata("recipe.json")
        or not isinstance(manifest.get("calibration"), dict)
        or manifest["calibration"].get("judge") not in JUDGES
        or manifest["calibration"].get("dev_sha256")
        != manifest["profile"]["dev_sha256"]
    ):
        raise ValueError("remote_text_evidence_manifest_identity_mismatch")
    if manifest["calibration"]["judge"] != "exact-v1":
        validate_calibration(manifest["calibration"], manifest["profile"]["dev_sha256"])
    result = _verified_result(metadata, "", body["result_sha256"], files, manifest)
    steps = _expected_steps(trial)
    checkpoints = []
    if steps:
        for step, result_sha in steps.items():
            name = _generation(attempt, step)
            report = _verified_result(metadata, name, result_sha, files, manifest)
            checkpoints.append(
                _checkpoint_row(metadata, files, name, report, manifest, step)
            )
    else:
        if result.get("checkpoint_evaluations"):
            raise ValueError("remote_text_evidence_checkpoint_evaluation_missing")
        checkpoints.append(
            _checkpoint_row(
                metadata,
                files,
                _generation(attempt, None),
                result,
                manifest,
                _step(result["checkpoint"]["step"]),
            )
        )
    resume_step = body["latest_resume_step"]
    latest_resume = (
        None
        if resume_step is None
        else _verified_checkpoint(metadata, files, _step(resume_step), None)
    )
    return {
        "campaign_id": body["campaign_id"],
        "run_id": body["run_id"],
        "attempt": attempt,
        "plan_sha256": body["plan_sha256"],
        "profile_identity": body["profile_identity"],
        "result_sha256": body["result_sha256"],
        "summaries": result["summaries"],
        "checkpoints": checkpoints,
        "latest_resume": latest_resume,
    }


def _verify_archive(path: Path, state: dict, trial: dict, max_bytes: int) -> dict:
    try:
        with _regular(path) as (stream, size):
            if not 0 < size <= max_bytes:
                raise ValueError("remote_text_evidence_size_exceeded")
            checksum = _digest_stream(stream)
            stream.seek(0)
            with tarfile.open(
                fileobj=stream, mode="r:", tarinfo=_RegularTarInfo
            ) as archive:
                first = archive.next()
                if (
                    first is None
                    or first.name != _BUNDLE
                    or not first.isfile()
                    or first.issparse()
                ):
                    raise ValueError("remote_text_evidence_manifest_invalid")
                body = _read_metadata(archive, first)
                receipt = _restore_evidence(archive, body, state, trial, max_bytes)
    except (tarfile.TarError, KeyError, TypeError, OverflowError) as exc:
        raise ValueError("remote_text_evidence_bundle_invalid") from exc
    return {
        **receipt,
        "archive_bytes": size,
        "archive_sha256": checksum,
        "archive_name": _ARCHIVE,
    }


def _run_directory(evidence_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    return operator_path(evidence_root / run_id)


def read_run(evidence_root: Path, run_id: str) -> dict:
    """Return the published receipt only while its underlying archive is intact."""
    directory = _run_directory(evidence_root, run_id)
    receipt = read_json(directory / _RECEIPT)
    artifact = _file_identity(directory / _ARCHIVE)
    if (
        receipt["run_id"] != run_id
        or receipt["archive_name"] != _ARCHIVE
        or artifact["size"] != receipt["archive_bytes"]
        or artifact["sha256"] != _sha(receipt["archive_sha256"])
    ):
        raise ValueError("remote_text_evidence_archive_changed")
    return receipt


def artifact_path(evidence_root: Path, run_id: str) -> Path:
    read_run(evidence_root, run_id)
    return _run_directory(evidence_root, run_id) / _ARCHIVE


def stage_candidate(
    evidence_root: Path,
    run_id: str,
    step: int,
    destination: Path,
    *,
    expected_archive_sha256: str,
) -> dict:
    """Restore only the two adapter inputs and their transfer receipt."""
    archive_path = _run_directory(evidence_root, run_id) / _ARCHIVE
    target = operator_path(destination)
    if target.name != f"checkpoint-{_step(step)}":
        raise ValueError("remote_text_evidence_checkpoint_target_invalid")
    target.mkdir(mode=0o700)
    with _regular(archive_path) as (stream, _):
        if _digest_stream(stream) != _sha(expected_archive_sha256):
            raise ValueError("remote_text_evidence_archive_changed")
        stream.seek(0)
        return _restore_candidate(stream, step, target)


def _restore_candidate(stream: BinaryIO, step: int, target: Path) -> dict:
    with tarfile.open(fileobj=stream, mode="r:", tarinfo=_RegularTarInfo) as archive:
        first = archive.next()
        if first is None or first.name != _BUNDLE:
            raise ValueError("remote_text_evidence_manifest_invalid")
        body = _read_metadata(archive, first)
        files = body["files"]
        manifest = _read_metadata(archive, archive.getmember("manifest.json"))
        for name in (*ADAPTER_FILES, "hashes.json"):
            key = f"training/checkpoint-{step}/{name}"
            item = archive.getmember(key)
            if not item.isfile() or item.issparse() or item.size != files[key]["size"]:
                raise ValueError("remote_text_evidence_member_invalid")
            source = archive.extractfile(item)
            if source is None:
                raise ValueError("remote_text_evidence_file_invalid")
            with source, (target / name).open("xb") as output:
                while data := source.read(1024 * 1024):
                    output.write(data)
            if digest(target / name) != files[key]["sha256"]:
                raise ValueError("remote_text_evidence_checkpoint_changed")
    inspect_checkpoint(target)
    return manifest


def _receipt_matches(receipt: dict, state: dict, trial: dict) -> bool:
    return (
        receipt["campaign_id"] == state["campaign_id"]
        and receipt["run_id"] == trial["run_id"]
        and receipt["plan_sha256"] == state["plan"]["plan_sha256"]
        and receipt["profile_identity"] == state["plan"]["profile_identity"]
        and receipt["result_sha256"] == trial["result_sha256"]
        and (trial.get("attempt") is None or receipt["attempt"] == trial["attempt"])
    )


def sync_run(
    host: EvidenceHost,
    state: dict,
    run_id: str,
    evidence_root: Path,
    max_bytes: int,
    *,
    timeout: int | None = None,
) -> dict:
    """Fetch once, verify against the frozen trial and atomically publish the receipt."""
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_BYTES:
        raise ValueError("remote_text_evidence_size_invalid")
    trial = _trial(state, run_id)
    directory = _run_directory(evidence_root, run_id)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / _ARCHIVE
    with file_lock(directory / ".evidence.lock"):
        if (directory / _RECEIPT).exists():
            receipt = read_run(evidence_root, run_id)
        elif path.exists():
            # A crash between archive rename and receipt publication needs no re-download.
            receipt = _verify_archive(path, state, trial, max_bytes)
        else:
            with tempfile.TemporaryDirectory(
                prefix=".incoming-", dir=directory
            ) as staging:
                archive = Path(staging) / _ARCHIVE
                host.fetch(
                    state["campaign_id"], run_id, archive, max_bytes, timeout=timeout
                )
                receipt = _verify_archive(archive, state, trial, max_bytes)
                with _regular(archive) as (stream, _):
                    os.fsync(stream.fileno())
                archive.replace(path)
        if (
            not _receipt_matches(receipt, state, trial)
            or receipt["archive_bytes"] > max_bytes
        ):
            raise ValueError("remote_text_evidence_receipt_conflict")
        if "verified_at" not in receipt:
            receipt["verified_at"] = time.time()
            atomic_json(directory / _RECEIPT, receipt)
        return receipt


def _candidate_rows(receipts: list[dict]) -> list[dict]:
    return [
        {
            "run_id": receipt["run_id"],
            "attempt": receipt["attempt"],
            "result_sha256": receipt["result_sha256"],
            "archive_sha256": receipt["archive_sha256"],
            **checkpoint,
        }
        for receipt in receipts
        for checkpoint in receipt["checkpoints"]
    ]


def summarize(state: dict, receipts: Mapping[str, dict]) -> dict:
    """Report comparable development performance without implying release readiness."""
    trials = state.get("trials", [])
    completed = [trial for trial in trials if trial.get("result_sha256")]
    verified = [
        receipt
        for trial in completed
        if (receipt := receipts.get(trial["run_id"])) is not None
        and _receipt_matches(receipt, state, trial)
    ]
    rows = _candidate_rows(verified)
    comparable = len({stable_hash(row["identity"]) for row in rows}) == 1
    best = (
        max(
            (row for row in rows if row["adapter_available"]),
            key=lambda row: (row["usable_delta"], -row["critical_delta"], -row["step"]),
            default=None,
        )
        if comparable
        else None
    )
    exhaustively_evaluated = (
        comparable
        and state.get("status") == "succeeded"
        and len(verified) == len(completed)
        and all(
            trial["status"] == "skipped" or trial.get("result_sha256")
            for trial in trials
        )
    )
    if best is not None and best["usable_delta"] > 0:
        outcome = "PROVISIONAL"
    elif exhaustively_evaluated and all(row["usable_delta"] <= 0 for row in rows):
        outcome = "NO_IMPROVEMENT"
    else:
        outcome = "INCONCLUSIVE"
    latest = next(
        (row for row in reversed(verified) if row["latest_resume"] is not None), None
    )
    return {
        "outcome": outcome,
        "evidence_scope": "development",
        "best_observed": best,
        "best_qualified": None,
        "qualification_blockers": [
            "independent_final_test_missing",
            "target_runtime_reload_missing",
        ],
        "latest_resume": {"run_id": latest["run_id"], **latest["latest_resume"]}
        if latest
        else None,
        "evaluated_runs": len(completed),
        "verified_runs": len(verified),
        "comparable_evidence": comparable,
        "last_verified_at": max((row["verified_at"] for row in verified), default=None),
    }
