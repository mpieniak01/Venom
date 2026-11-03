"""Bounded offline reference qualification of frozen fixture scenarios.

Only the built-in reference adapter is restricted to in-process file operations.
Injected executors are trusted application adapters, never loaded from case data.
The report does not establish model accuracy, GPU readiness or promotion.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import stat
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .material import SHA256
from .paths import checked_file

Json = dict[str, Any]
Executor = Callable[[Json, Path], Json]
MAX_CASES = 32
MAX_FILES = 128
MAX_FILE_BYTES = 65536
MAX_TOTAL_BYTES = 1048576
MAX_STEPS = 32
_ID = re.compile(r"[a-z0-9][\w-]{0,79}", re.ASCII)
SOURCE_QUALIFICATION = "synthetic_sample_not_final_benchmark"
_MANIFEST_FIELDS = frozenset(
    {"schema_version", "qualification", "cases", "case_count", "files"}
)
_CASE_FIELDS = frozenset(
    {
        "id",
        "problem_group",
        "split",
        "family",
        "language",
        "prompt",
        "fixture",
        "mutable_files",
        "reference_actions",
        "expected_files",
    }
)


def _relative(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "\\" in value
        or ":" in value
    ):
        raise ValueError("gemma_benchmark_relative_path_invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise ValueError("gemma_benchmark_relative_path_invalid")
    return value


def _inventory(root: Path) -> dict[str, Path]:
    result = {}
    for count, path in enumerate(root.rglob("*"), start=1):
        if count > MAX_FILES * 3:
            raise ValueError("gemma_benchmark_inventory_limit")
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError("gemma_benchmark_special_file")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("gemma_benchmark_file_limit")
        result[path.relative_to(root).as_posix()] = path
        if len(result) > MAX_FILES:
            raise ValueError("gemma_benchmark_file_count_limit")
    return result


def _hashes(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("gemma_benchmark_hash_inventory_required")
    for name, checksum in value.items():
        _relative(name)
        if not isinstance(checksum, str) or SHA256.fullmatch(checksum) is None:
            raise ValueError("gemma_benchmark_sha256_invalid")
    return value


def _read_bundle(manifest_path: Path) -> tuple[Json, dict[str, bytes], str]:
    target = checked_file(manifest_path, profile=True)
    inventory = _inventory(target.parent)
    manifest_bytes = target.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS:
        raise ValueError("gemma_benchmark_manifest_invalid")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("gemma_benchmark_schema_version_invalid")
    if manifest["qualification"] != SOURCE_QUALIFICATION:
        raise ValueError("gemma_benchmark_qualification_invalid")
    count = manifest["case_count"]
    if type(count) is not int or not 1 <= count <= MAX_CASES:
        raise ValueError("gemma_benchmark_case_count_invalid")
    expected = _hashes(manifest["files"])
    if target.name in expected or set(inventory) != set(expected) | {target.name}:
        raise ValueError("gemma_benchmark_inventory_mismatch")
    payload = {name: inventory[name].read_bytes() for name in expected}
    if sum(map(len, payload.values())) > MAX_TOTAL_BYTES:
        raise ValueError("gemma_benchmark_bundle_limit")
    for name, data in payload.items():
        if hashlib.sha256(data).hexdigest() != expected[name]:
            raise ValueError("gemma_benchmark_source_hash_mismatch")
    return manifest, payload, hashlib.sha256(manifest_bytes).hexdigest()


def _write_argument(arguments: Json, mutable: set[str]) -> None:
    content = arguments["content"]
    if not isinstance(content, str) or len(content.encode()) > MAX_FILE_BYTES:
        raise ValueError("gemma_benchmark_write_limit")
    if arguments["path"] not in mutable:
        raise ValueError("gemma_benchmark_reference_scope_violation")


def _action(action: Any, mutable: set[str]) -> None:
    if not isinstance(action, dict) or set(action) != {"name", "arguments"}:
        raise ValueError("gemma_benchmark_action_invalid")
    name, arguments = action["name"], action["arguments"]
    if not isinstance(arguments, dict):
        raise ValueError("gemma_benchmark_arguments_invalid")
    fields = {
        "ReadFile": {"path"},
        "WriteFile": {"path", "content"},
        "ListFiles": set(),
        "FilterLog": {"path", "contains"},
    }
    if (
        not isinstance(name, str)
        or name not in fields
        or set(arguments) != fields[name]
    ):
        raise ValueError("gemma_benchmark_operation_not_allowed")
    if "path" in arguments:
        _relative(arguments["path"])
    if name == "WriteFile":
        _write_argument(arguments, mutable)
    if name == "FilterLog" and (
        not isinstance(arguments["contains"], str) or not arguments["contains"]
    ):
        raise ValueError("gemma_benchmark_filter_invalid")


def _case_header(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != _CASE_FIELDS:
        raise ValueError("gemma_benchmark_case_invalid")
    if not isinstance(value["id"], str) or not _ID.fullmatch(value["id"]):
        raise ValueError("gemma_benchmark_case_id_invalid")
    for name in ("problem_group", "family", "language", "prompt"):
        if not isinstance(value[name], str) or not value[name].strip():
            raise ValueError("gemma_benchmark_case_field_invalid")
    if not isinstance(value["split"], str) or value["split"] not in {
        "validation",
        "holdout",
    }:
        raise ValueError("gemma_benchmark_split_invalid")


def _mutable_files(value: Any) -> set[str]:
    if not isinstance(value, list) or len(value) > MAX_FILES:
        raise ValueError("gemma_benchmark_mutable_files_invalid")
    mutable = {_relative(name) for name in value}
    if len(mutable) != len(value):
        raise ValueError("gemma_benchmark_mutable_files_invalid")
    return mutable


def _fixture_inventory(case: Json, payload: Mapping[str, bytes]) -> dict[str, bytes]:
    fixture = _relative(case["fixture"]) + "/"
    initial = {
        name.removeprefix(fixture): data
        for name, data in payload.items()
        if name.startswith(fixture)
    }
    if not initial:
        raise ValueError("gemma_benchmark_fixture_missing")
    return initial


def _case(value: Any, payload: Mapping[str, bytes]) -> Json:
    _case_header(value)
    initial = _fixture_inventory(value, payload)
    mutable = _mutable_files(value["mutable_files"])
    expected = _hashes(value["expected_files"])
    for name, data in initial.items():
        if (
            name not in mutable
            and expected.get(name) != hashlib.sha256(data).hexdigest()
        ):
            raise ValueError("gemma_benchmark_expected_protected_mutation")
    steps = value["reference_actions"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError("gemma_benchmark_steps_invalid")
    for step in steps:
        _action(step, mutable)
    return value


def _case_groups_and_inventory(
    rows: list[Json], payload: Mapping[str, bytes], cases_name: str
) -> None:
    groups: dict[str, str] = {}
    used = {cases_name}
    for row in rows:
        group, split = row["problem_group"], row["split"]
        if group in groups and groups[group] != split:
            raise ValueError("gemma_benchmark_group_leakage")
        groups[group] = split
        used.update(name for name in payload if name.startswith(row["fixture"] + "/"))
    if used != set(payload):
        raise ValueError("gemma_benchmark_unused_inventory")


def load_cases(manifest_path: Path) -> tuple[Json, list[Json], dict[str, bytes]]:
    """Verify a strict immutable bundle before any executor is invoked."""
    manifest, payload, checksum = _read_bundle(manifest_path)
    cases_name = _relative(manifest["cases"])
    if cases_name not in payload:
        raise ValueError("gemma_benchmark_cases_not_in_manifest")
    rows = [
        _case(json.loads(line), payload)
        for line in payload[cases_name].decode().splitlines()
        if line.strip()
    ]
    if len(rows) != manifest["case_count"] or len({row["id"] for row in rows}) != len(
        rows
    ):
        raise ValueError("gemma_benchmark_case_count_or_ids_invalid")
    _case_groups_and_inventory(rows, payload, cases_name)
    return manifest | {"manifest_sha256": checksum}, rows, payload


def _file(workspace: Path, relative: str) -> Path:
    path = workspace / _relative(relative)
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("gemma_benchmark_workspace_symlink")
    if not path.resolve().is_relative_to(workspace.resolve()):
        raise ValueError("gemma_benchmark_workspace_escape")
    if path.exists() and not path.is_file():
        raise ValueError("gemma_benchmark_workspace_file_required")
    return path


def _read(workspace: Path, relative: str) -> str:
    path = _file(workspace, relative)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("gemma_benchmark_file_limit")
    return path.read_text(encoding="utf-8")


def _reference_step(step: Json, workspace: Path, mutable: set[str]) -> str:
    _action(step, mutable)
    arguments, name = step["arguments"], step["name"]
    if name == "ListFiles":
        return "\n".join(sorted(_inventory(workspace)))
    if name == "ReadFile":
        return _read(workspace, arguments["path"])
    if name == "FilterLog":
        return "\n".join(
            line
            for line in _read(workspace, arguments["path"]).splitlines()
            if arguments["contains"] in line
        )
    path = _file(workspace, arguments["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(arguments["content"], encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_executor(case: Json, workspace: Path) -> Json:
    """Execute only declared fixture operations, with a per-write scope check."""
    mutable = set(case["mutable_files"])
    observations = []
    for step in case["reference_actions"]:
        result = _reference_step(step, workspace, mutable)
        observations.append(
            {
                "name": step["name"],
                "result_sha256": hashlib.sha256(result.encode()).hexdigest(),
            }
        )
    return {"status": "success", "observations": observations}


def _snapshot(workspace: Path) -> dict[str, str]:
    inventory = _inventory(workspace)
    if sum(path.stat().st_size for path in inventory.values()) > MAX_TOTAL_BYTES:
        raise ValueError("gemma_benchmark_workspace_limit")
    return {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in inventory.items()
    }


def _verify(
    case: Json, before: Mapping[str, str], workspace: Path, outcome: Json
) -> Json:
    try:
        after = _snapshot(workspace)
    except ValueError:
        return {
            "success": False,
            "errors": ["unsafe_workspace"],
            "scope_violations": ["unsafe_workspace"],
            "success_without_oracle_confirmation": outcome.get("status") == "success",
            "incorrect_success_status": outcome.get("status") == "success",
        }
    changed = {
        name
        for name in before.keys() | after.keys()
        if before.get(name) != after.get(name)
    }
    violations = sorted(changed - set(case["mutable_files"]))
    matches = after == case["expected_files"]
    claimed = outcome.get("status") == "success"
    success = (
        matches and claimed and not violations and not outcome.get("timed_out", False)
    )
    return {
        "success": success,
        "errors": ([] if matches else ["final_state_mismatch"])
        + ([] if claimed else ["no_success_claim"])
        + (["timed_out"] if outcome.get("timed_out", False) else []),
        "scope_violations": violations,
        "success_without_oracle_confirmation": claimed and not matches,
        "incorrect_success_status": claimed and not success,
    }


def _materialize(case: Json, payload: Mapping[str, bytes], workspace: Path) -> None:
    for name, data in _fixture_inventory(case, payload).items():
        path = _file(workspace, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _execute(
    case: Json, workspace: Path, executor: Executor, *, builtin: bool
) -> tuple[Json, str | None]:
    exposed = copy.deepcopy(case)
    if not builtin:
        exposed.pop("expected_files")
        exposed.pop("reference_actions")
    try:
        outcome = executor(exposed, workspace)
        if not isinstance(outcome, dict) or not isinstance(outcome.get("status"), str):
            raise ValueError("gemma_benchmark_executor_result_invalid")
        if type(outcome.get("timed_out", False)) is not bool:
            raise ValueError("gemma_benchmark_executor_timeout_invalid")
        failure_kind = outcome.get("failure_kind")
        if failure_kind not in {None, "model", "infrastructure"}:
            raise ValueError("gemma_benchmark_executor_failure_kind_invalid")
        return outcome, failure_kind
    except Exception as exc:
        return {
            "status": "infrastructure_error",
            "error_type": type(exc).__name__,
        }, "infrastructure"


def _run_case(
    case: Json, payload: Mapping[str, bytes], executor: Executor, *, builtin: bool
) -> Json:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="gemma-case-") as directory:
        # Temporary roots can have OS-managed symlink parents (for example /var
        # on macOS). Canonicalize our newly owned root before checking paths
        # inside it; symlinks created within the workspace remain forbidden.
        workspace = Path(directory).resolve(strict=True)
        _materialize(case, payload, workspace)
        before = _snapshot(workspace)
        outcome, failure_kind = _execute(case, workspace, executor, builtin=builtin)
        try:
            oracle = _verify(case, before, workspace, outcome)
        except OSError as exc:
            claimed = outcome.get("status") == "success"
            oracle = {
                "success": False,
                "errors": ["workspace_io_error"],
                "scope_violations": [],
                "success_without_oracle_confirmation": claimed,
                "incorrect_success_status": claimed,
            }
            failure_kind = "infrastructure"
            outcome["error_type"] = type(exc).__name__
        if failure_kind is not None:
            oracle["success"] = False
            claimed = outcome.get("status") == "success"
            oracle["success_without_oracle_confirmation"] = claimed
            oracle["incorrect_success_status"] = claimed
            oracle["errors"].append("executor_" + failure_kind + "_error")
        if not oracle["success"] and failure_kind is None:
            failure_kind = "model"
    elapsed = time.monotonic() - started
    return {
        "case_id": case["id"],
        "problem_group": case["problem_group"],
        "family": case["family"],
        "language": case["language"],
        "split": case["split"],
        "arm": "reference",
        "oracle": oracle,
        "failure_kind": failure_kind,
        "timed_out": outcome.get("timed_out", False),
        "task_seconds": elapsed,
        "active_task_seconds": elapsed,
        "executor_error_type": outcome.get("error_type"),
        "reference_observations": outcome.get("observations", []) if builtin else [],
    }


def qualify_cases(manifest_path: Path, *, executor: Executor | None = None) -> Json:
    """Qualify reference scenarios in isolated temporary workspaces, never a model."""
    manifest, cases, payload = load_cases(manifest_path)
    selected = reference_executor if executor is None else executor
    trials = [
        _run_case(case, payload, selected, builtin=executor is None) for case in cases
    ]
    passed = all(row["oracle"]["success"] for row in trials)
    return {
        "schema_version": 1,
        "status": "REFERENCE_PASS" if passed else "REFERENCE_FAIL",
        "benchmark_sha256": manifest["manifest_sha256"],
        "qualification": SOURCE_QUALIFICATION,
        "evidence_scope": "reference_fixture_qualification_only",
        "executor_kind": "builtin_inprocess"
        if executor is None
        else "trusted_injected_adapter",
        "case_count": len(cases),
        "trials": trials,
        "model_evaluated": False,
        "training_ready": False,
        "promotion_authorized": False,
        "activation_authorized": False,
    }
