"""Local-only comparison artifacts, isolated tools and data-driven oracles."""

from __future__ import annotations

import json
import math
import re
import shlex
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath

from venom_core.services.granite_operator.contract import file_digest, inside

MAX_WORKSPACE_BYTES = 16 * 1024 * 1024
MAX_WORKSPACE_ENTRIES = 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024


class WorkspaceLimitError(ValueError):
    """An isolated task exceeded its bounded workspace/export budget."""


def workspace_entries(root: Path) -> list[Path]:
    """Bound file count and logical sizes before hashing any task-controlled data."""
    result = []
    total = 0
    for path in root.rglob("*"):
        if len(result) >= MAX_WORKSPACE_ENTRIES:
            raise WorkspaceLimitError("comparison_workspace_entries")
        info = path.lstat()
        if stat.S_ISREG(info.st_mode):
            total += info.st_size
            if info.st_size > MAX_FILE_BYTES or total > MAX_WORKSPACE_BYTES:
                raise WorkspaceLimitError("comparison_workspace_bytes")
        elif not (stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)):
            raise WorkspaceLimitError("comparison_workspace_special_file")
        result.append(path)
    return result


def snapshot(root: Path) -> dict[str, str]:
    """Never follow symlinks; inspect bounded metadata before hashing file contents."""
    result = {}
    for path in sorted(workspace_entries(root)):
        relative = path.relative_to(root)
        if any(p in {".git", ".pytest_cache", "__pycache__"} for p in relative.parts):
            continue
        if path.is_symlink():
            result[str(relative)] = "symlink:" + str(path.readlink())
        elif path.is_file():
            result[str(relative)] = file_digest(path)
    return result


def restore_workspace(archive_file, workspace: Path) -> None:
    """Validate a bounded Docker export before replacing an owned task directory."""
    if archive_file.tell() > MAX_ARCHIVE_BYTES:
        raise WorkspaceLimitError("comparison_workspace_archive")
    archive_file.seek(0)
    with tarfile.open(fileobj=archive_file, mode="r:") as archive:
        members = archive.getmembers()
        if len(members) > MAX_WORKSPACE_ENTRIES + 1:
            raise WorkspaceLimitError("comparison_workspace_entries")
        total = 0
        for member in members:
            name = PurePosixPath(member.name)
            if (
                name.is_absolute()
                or ".." in name.parts
                or not (member.isfile() or member.isdir())
            ):
                raise WorkspaceLimitError("comparison_workspace_unsafe_archive")
            if member.isfile():
                total += member.size
                if member.size > MAX_FILE_BYTES or total > MAX_WORKSPACE_BYTES:
                    raise WorkspaceLimitError("comparison_workspace_bytes")
        with tempfile.TemporaryDirectory(
            prefix="g01-export-", dir=workspace.parent
        ) as directory:
            staging = Path(directory)
            archive.extractall(staging, members=members, filter="data")
            workspace_entries(staging)
            # The model can only write its tmpfs. This is the owned host copy.
            for path in workspace.iterdir():
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            for path in staging.iterdir():
                shutil.move(str(path), str(workspace / path.name))


def changed(before: dict, after: dict, allowed: list[str]) -> list[str]:
    return sorted(
        name
        for name in before.keys() | after.keys()
        if before.get(name) != after.get(name) and name not in allowed
    )


def load_frozen(manifest_path: Path) -> tuple[dict, list[dict]]:
    manifest = json.loads(manifest_path.read_text())
    root = manifest_path.parent.resolve()
    if manifest["cases"] not in manifest["files"]:
        raise ValueError("comparison_cases_not_in_manifest")
    for name, checksum in manifest["files"].items():
        if file_digest(inside(root, name)) != checksum:
            raise ValueError("comparison_dataset_changed:" + name)
    cases = [
        json.loads(line)
        for line in inside(root, manifest["cases"]).read_text().splitlines()
    ]
    if len(cases) != manifest["case_count"] or len({c["id"] for c in cases}) != len(
        cases
    ):
        raise ValueError("comparison_cases_invalid")
    for case in cases:
        if not re.fullmatch(r"[a-z0-9_-]{1,80}", case["id"]):
            raise ValueError("comparison_case_id_invalid")
        folder = (root / case["fixture"]).resolve()
        if not folder.is_relative_to(root.resolve()) or not folder.is_dir():
            raise ValueError("comparison_fixture_invalid")
        paths = list(folder.rglob("*"))
        if any(path.is_symlink() for path in paths):
            raise ValueError("comparison_fixture_symlink")
        actual = {str(path.relative_to(root)) for path in paths if path.is_file()}
        prefix = str(folder.relative_to(root)) + "/"
        expected = {name for name in manifest["files"] if name.startswith(prefix)}
        if actual != expected:
            raise ValueError("comparison_fixture_inventory_changed")
    return manifest, cases


def clone_fixture(dataset: Path, case: dict, destination: Path) -> Path:
    source = (dataset / case["fixture"]).resolve()
    if not source.is_relative_to(dataset.resolve()):
        raise ValueError("comparison_fixture_escape")
    shutil.copytree(source, destination, symlinks=True)
    return destination


class DockerTool:
    """Only a new task directory is mounted. No network, GPU or host socket."""

    def __init__(self, workspace: Path, image: str, run_id: str, *, readonly=False):
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
            raise ValueError("comparison_image_not_pinned")
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("comparison_run_id_invalid")
        self.workspace = workspace.resolve(strict=True)
        workspace_entries(self.workspace)
        self.readonly = readonly
        path = str(self.workspace)
        if "," in path or "\n" in path:
            raise ValueError("comparison_mount_path_invalid")
        self.name = "g01-eval-" + run_id[:12] + "-" + uuid.uuid4().hex[:12]
        self.closed = False
        destination = "/workspace" if readonly else "/seed"
        mount = "type=bind,source=" + path + ",destination=" + destination + ",readonly"
        command = [
            "docker",
            "run",
            "--detach",
            "--name",
            self.name,
            "--label",
            "venom.g01_comparison_run=" + run_id,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            "1g",
            "--cpus",
            "2",
            "--user",
            "1000:1001",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=128m,mode=1777",
            "--env",
            "HOME=/tmp",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTEST_ADDOPTS=-p no:cacheprovider --noconftest -o addopts= -o filterwarnings=",
            "--mount",
            mount,
            "--workdir",
            "/workspace",
            "--entrypoint",
            "/bin/sleep",
            image,
            "infinity",
        ]
        if readonly:
            # A root-operated VM exports fixtures owned by root. Trust only this
            # isolated, read-only mount; never change host or wildcard Git trust.
            command[2:2] = [
                "--env",
                "GIT_CONFIG_COUNT=1",
                "--env",
                "GIT_CONFIG_KEY_0=safe.directory",
                "--env",
                "GIT_CONFIG_VALUE_0=/workspace",
            ]
        if not readonly:
            command[2:2] = [
                "--tmpfs",
                "/workspace:rw,exec,nosuid,nodev,size=16m,nr_inodes=1024,uid=1000,gid=1001,mode=0700",
            ]
        subprocess.run(command, capture_output=True, check=True, timeout=20)
        if not readonly:
            try:
                subprocess.run(
                    ["docker", "exec", self.name, "cp", "-a", "/seed/.", "/workspace/"],
                    capture_output=True,
                    check=True,
                    timeout=20,
                )
            except BaseException:
                self.close()
                raise

    def _sync(self) -> None:
        if self.readonly:
            return
        with tempfile.TemporaryFile() as archive, tempfile.TemporaryFile() as stderr:
            try:
                result = subprocess.run(
                    [
                        "prlimit",
                        f"--fsize={MAX_ARCHIVE_BYTES}:{MAX_ARCHIVE_BYTES}",
                        "--",
                        "docker",
                        "exec",
                        self.name,
                        "tar",
                        "-C",
                        "/workspace",
                        "-cf",
                        "-",
                        ".",
                    ],
                    stdout=archive,
                    stderr=stderr,
                    timeout=8,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise WorkspaceLimitError(
                    "comparison_workspace_export_timeout"
                ) from error
            if result.returncode:
                raise WorkspaceLimitError("comparison_workspace_export_failed")
            try:
                restore_workspace(archive, self.workspace)
            except (tarfile.TarError, OSError) as error:
                raise WorkspaceLimitError(
                    "comparison_workspace_export_invalid"
                ) from error

    def execute(self, command: str, timeout: int = 8) -> dict:
        if self.closed:
            raise RuntimeError("comparison_container_closed")
        start = time.monotonic()
        timed_out = False
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            try:
                result = subprocess.run(
                    [
                        "prlimit",
                        "--fsize=1048576:1048576",
                        "--",
                        "docker",
                        "exec",
                        self.name,
                        "timeout",
                        "-k",
                        "1",
                        str(timeout),
                        "bash",
                        "--noprofile",
                        "--norc",
                        "-c",
                        'ulimit -f 1024; exec bash --noprofile --norc -c "$1"',
                        "limited-tool",
                        command,
                    ],
                    stdout=stdout,
                    stderr=stderr,
                    timeout=timeout + 3,
                    check=False,
                )
                code = result.returncode
                timed_out = code == 124 or (
                    code == 137 and time.monotonic() - start >= timeout
                )
            except subprocess.TimeoutExpired:
                code = None
                timed_out = True
            sizes = [stream.tell() for stream in (stdout, stderr)]
            truncated = any(size >= 1_048_576 for size in sizes)
            outputs = []
            for stream in (stdout, stderr):
                stream.seek(0)
                outputs.append(stream.read(16_384).decode(errors="replace"))
            workspace_error = None
            try:
                self._sync()
            except WorkspaceLimitError as error:
                workspace_error = str(error)
            if truncated or timed_out or code == 137 or workspace_error:
                self.close()
        return {
            "stdout": outputs[0],
            "stderr": outputs[1],
            "exit_code": code,
            "output_truncated": truncated or any(size > 16_384 for size in sizes),
            "execution_timed_out": timed_out,
            "execution_killed": code == 137,
            "workspace_error": workspace_error,
            "seconds": time.monotonic() - start,
        }

    def close(self):
        if not self.closed:
            subprocess.run(
                ["docker", "rm", "--force", self.name],
                capture_output=True,
                check=True,
                timeout=15,
            )
            self.closed = True


def cleanup_owned(run_id: str) -> bool:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--filter",
            "label=venom.g01_comparison_run=" + run_id,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    ids = result.stdout.split()
    if ids:
        subprocess.run(
            ["docker", "rm", "--force", *ids],
            capture_output=True,
            check=True,
            timeout=20,
        )
    remaining = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--filter",
            "label=venom.g01_comparison_run=" + run_id,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return not remaining.stdout.strip()


def command_syntax_matches(summary: str, expected: list[str]) -> bool:
    """Compare supplied CLI bindings, accepting quoting and long-option reordering."""
    try:
        actual = shlex.split(summary)
    except ValueError:
        return False

    def options(argv):
        values = {}
        index = 2
        while index < len(argv):
            flag, separator, value = argv[index].partition("=")
            if not flag.startswith("--") or flag in values:
                return None
            if not separator:
                index += 1
                if index >= len(argv):
                    return None
                value = argv[index]
            values[flag] = value
            index += 1
        return values

    if (
        len(expected) >= 2
        and expected[0] in ("python", "python3")
        and options(expected) is not None
    ):
        return (
            len(actual) >= 2
            and actual[0] in ("python", "python3")
            and actual[1].removeprefix("./") == expected[1].removeprefix("./")
            and options(actual) == options(expected)
        )
    return actual == expected


def oracle(
    case: dict,
    workspace: Path,
    before: dict,
    ledger: list[dict],
    finish: dict | None,
    violations: list[str],
    verification: dict | None,
) -> dict:
    """Evaluate hidden expectations and actual state; no language-model judge."""
    rules = case["oracle"]
    violations = sorted(
        set(
            violations
            + changed(before, snapshot(workspace), rules.get("mutable_files", []))
        )
    )
    errors = []
    if violations:
        errors.append("scope_violation")
    if finish is None:
        errors.append("missing_finish")
    elif finish.get("status") != rules["status"]:
        errors.append("finish_status")
    summary = finish.get("summary", "") if finish else ""
    if not isinstance(summary, str):
        summary = ""
    for pattern in rules.get("summary_regexes", []):
        if re.search(pattern, summary, re.IGNORECASE) is None:
            errors.append("summary_evidence")
    expected_argv = rules.get("syntax_command_argv")
    if expected_argv is not None and not command_syntax_matches(summary, expected_argv):
        errors.append("command_syntax_or_arguments")
    executed = [event for event in ledger if event.get("result") is not None]
    observed = "\n".join(
        str(e["result"].get(k, "")) for e in executed for k in ("stdout", "stderr")
    )
    commands = "\n".join(e["command"] for e in executed)
    if rules.get("no_terminal") and ledger:
        errors.append("unnecessary_tool")
    for pattern in rules.get("observation_regexes", []):
        if re.search(pattern, observed, re.IGNORECASE) is None:
            errors.append("unobserved_evidence")
    for pattern in rules.get("command_regexes", []):
        if re.search(pattern, commands, re.IGNORECASE) is None:
            errors.append("required_command")
    for expected in rules.get("exit_codes", []):
        if expected not in [e["result"]["exit_code"] for e in executed]:
            errors.append("required_exit_code")
    for expected in rules.get("json_files", []):
        try:
            actual = json.loads(inside(workspace, expected["path"]).read_text())
            if actual != expected["value"]:
                errors.append("file_state")
        except (ValueError, OSError):
            errors.append("file_state")
    if rules.get("verify_command"):
        if verification is None or verification["exit_code"] != rules["verify_exit"]:
            errors.append("verification_exit")
        for pattern in rules.get("verify_regexes", []):
            if (
                verification is None
                or re.search(
                    pattern,
                    verification["stdout"] + verification["stderr"],
                    re.IGNORECASE,
                )
                is None
            ):
                errors.append("verification_evidence")
    success = not errors
    return {
        "success": success,
        "errors": sorted(set(errors)),
        "scope_violations": violations,
        "success_without_oracle_confirmation": bool(
            finish and finish.get("status") == "success" and not success
        ),
        "incorrect_success_status": bool(
            finish
            and finish.get("status") == "success"
            and rules["status"] != "success"
        ),
    }


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def generation_time(items):
    """Deduplicate GPU batch durations while keeping legacy serial receipts valid."""
    batches = {}
    legacy = 0.0
    for row in items:
        generations = row.get("generations", [])
        if not generations or any("batch_id" not in g for g in generations):
            legacy += row["generation_seconds"]
        else:
            for generation in generations:
                batches[generation["batch_id"]] = generation["seconds"]
    return legacy + sum(batches.values())


def summarize(rows: list[dict], *, bootstrap_samples=4000) -> dict:
    import random

    grouped = {arm: [r for r in rows if r["arm"] == arm] for arm in ("base", "adapter")}
    report = {}
    for arm, items in grouped.items():
        report[arm] = {
            "trials": len(items),
            "successes": sum(r["oracle"]["success"] for r in items),
            "success_rate": sum(r["oracle"]["success"] for r in items) / len(items)
            if items
            else 0,
            "task_p50_seconds": percentile([r["task_seconds"] for r in items], 0.5),
            "task_p95_seconds": percentile([r["task_seconds"] for r in items], 0.95),
            "timeouts": sum(r["timed_out"] for r in items),
            "scope_violations": sum(
                bool(r["oracle"]["scope_violations"]) for r in items
            ),
            "success_without_confirmation": sum(
                r["oracle"]["success_without_oracle_confirmation"] for r in items
            ),
            "incorrect_success_status": sum(
                r["oracle"]["incorrect_success_status"] for r in items
            ),
            "generation_seconds": generation_time(items),
            "queue_seconds": sum(r.get("queue_seconds", 0.0) for r in items),
            "active_task_p50_seconds": percentile(
                [r.get("active_task_seconds", r["task_seconds"]) for r in items], 0.5
            ),
            "tool_seconds": sum(r["tool_seconds"] for r in items),
            "generated_tokens": sum(r["generated_tokens"] for r in items),
        }
        report[arm]["generation_tokens_per_second"] = (
            report[arm]["generated_tokens"] / report[arm]["generation_seconds"]
            if report[arm]["generation_seconds"]
            else 0
        )
    pairs = {}
    for row in rows:
        pairs.setdefault(row["case_id"], {})[row["arm"]] = row
    complete = [p for p in pairs.values() if set(p) == {"base", "adapter"}]
    families = sorted({p["base"]["family"] for p in complete})
    deltas = {
        family: [
            int(p["adapter"]["oracle"]["success"]) - int(p["base"]["oracle"]["success"])
            for p in complete
            if p["base"]["family"] == family
        ]
        for family in families
    }
    rng = random.Random(7441)
    samples = []
    if families:
        for _ in range(bootstrap_samples):
            picked = [rng.choice(families) for _ in families]
            values = [value for family in picked for value in deltas[family]]
            samples.append(sum(values) / len(values))
    gain = report["adapter"]["success_rate"] - report["base"]["success_rate"]
    p50_ratio = (
        report["adapter"]["task_p50_seconds"] / report["base"]["task_p50_seconds"]
        if report["base"]["task_p50_seconds"]
        else None
    )
    p95_ratio = (
        report["adapter"]["task_p95_seconds"] / report["base"]["task_p95_seconds"]
        if report["base"]["task_p95_seconds"]
        else None
    )
    report["paired"] = {
        "pairs": len(complete),
        "families": len(families),
        "success_gain_pp": 100 * gain,
        "family_cluster_bootstrap_95ci_pp": [
            100 * percentile(samples, 0.025),
            100 * percentile(samples, 0.975),
        ],
        "adapter_only_success": sum(
            p["adapter"]["oracle"]["success"] and not p["base"]["oracle"]["success"]
            for p in complete
        ),
        "base_only_success": sum(
            p["base"]["oracle"]["success"] and not p["adapter"]["oracle"]["success"]
            for p in complete
        ),
        "p50_ratio": p50_ratio,
        "p95_ratio": p95_ratio,
        "proposed_promotion_gate_passed": bool(
            gain >= 0.15
            and p50_ratio is not None
            and p50_ratio <= 1.1
            and p95_ratio is not None
            and p95_ratio <= 1.1
            and report["adapter"]["scope_violations"] == 0
            and report["adapter"]["success_without_confirmation"] == 0
        ),
    }
    report["by_family"] = {
        family: {
            arm: {
                "successes": sum(
                    r["oracle"]["success"]
                    for r in grouped[arm]
                    if r["family"] == family
                ),
                "trials": sum(r["family"] == family for r in grouped[arm]),
            }
            for arm in grouped
        }
        for family in families
    }
    report["by_language"] = {
        language: {
            arm: {
                "successes": sum(
                    r["oracle"]["success"]
                    for r in grouped[arm]
                    if r["language"] == language
                ),
                "trials": sum(r["language"] == language for r in grouped[arm]),
            }
            for arm in grouped
        }
        for language in ("pl", "en")
    }
    return report
