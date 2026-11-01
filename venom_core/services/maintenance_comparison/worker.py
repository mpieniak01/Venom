"""Host-owned experiment worker. Never start a second Venom or a remote API."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import signal
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from .catalog import load_all_models
from .grading import grade
from .inference import LocalModel
from .metrics import MemorySampler
from .report import render
from .runner import drive
from .sandbox import PYTEST_PROFILE, TrialHabitat, TrialTools
from .scenarios import Scenario, build_scenarios
from .workspace import changed_files, patch, prepare, snapshot

JSON_SUFFIX = ".json"
PROGRESS_FILE = "progress.json"

SANDBOX_IMAGE = (
    "sha256:7b287d691d67f06c5e4e13ef0e9c939139466e5fb23e48ee70ae44866b37f278"
)
CACHE_ROOT = Path.home() / ".local/share/venom/maintenance-comparison"


def _write(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def require_host_owner() -> None:
    database = os.environ.get("VENOM_MAINTENANCE_ADMISSION_DB")
    if not database:
        raise RuntimeError("host_runtime_admission_required")
    with sqlite3.connect("file:" + database + "?mode=ro", uri=True) as db:
        row = db.execute(
            "SELECT 1 FROM lease WHERE pid=? AND owner='coding-maintenance' AND engine='maintenance' AND run_id=? AND quarantine=0 AND cancelled=0",
            (os.getppid(), os.environ.get("VENOM_MAINTENANCE_RUN_ID")),
        ).fetchone()
    if not row:
        raise RuntimeError("host_runtime_reservation_missing")


def _blocked(profile: dict, case, reason: str, repetition: int = 0) -> dict:
    return {
        "id": str(uuid4()),
        "model": profile["id"],
        "hf_id": profile["hf_id"],
        "revision": profile["revision"],
        "role": case.role,
        "scenario": case.id,
        "repetition": repetition,
        "status": "blocked",
        "blocked_reason": reason,
        "passed": None,
        "model_finished": False,
        "seconds": None,
        "peak_vram_bytes": None,
        "peak_ram_bytes": None,
    }


def _state(
    rows: list[dict], output: Path, state: Path, planned: list[dict] | None = None
) -> None:
    _write(output / "attempts.json", rows)
    _write(
        state,
        {
            "jobs": [
                {
                    "id": row["id"],
                    "model": row["model"],
                    "mode": "single",
                    "task": row["scenario"],
                    "role": row["role"],
                    "status": "skipped"
                    if row["status"] == "blocked"
                    else "completed"
                    if row["passed"]
                    else "failed",
                    "artifact": str(output / (row["id"] + JSON_SUFFIX)),
                    "rc": None
                    if row["status"] == "blocked"
                    else 0
                    if row["passed"]
                    else 1,
                }
                for row in rows
            ]
            + [
                {
                    "id": item["id"],
                    "model": item["model"],
                    "mode": "single",
                    "task": item["scenario"],
                    "status": "pending",
                    "role": item["role"],
                    "rc": None,
                }
                for item in (planned or [])
                if not any(
                    all(row[k] == item[k] for k in ("model", "scenario", "repetition"))
                    for row in rows
                )
            ]
        },
    )


async def trial(
    model,
    profile,
    case,
    repo: Path,
    sha: str,
    output: Path,
    repetition: int,
    seconds: int,
    *,
    identifier: str | None = None,
) -> dict:
    require_host_owner()
    trial_started = time.monotonic()
    identifier = identifier or str(uuid4())
    workspace = output / "workspaces" / identifier
    habitat = None
    token_start = model.input_tokens, model.output_tokens
    try:
        before = prepare(repo, sha, workspace, case)
        habitat = TrialHabitat(workspace, SANDBOX_IMAGE)
        model.torch.cuda.reset_peak_memory_stats()
        tools = TrialTools(habitat, case.role)
        setup_seconds = time.monotonic() - trial_started
        with MemorySampler() as memory:
            run = await drive(model, case, tools, seconds)
        _write(
            output / (identifier + JSON_SUFFIX),
            {"id": identifier, "phase": "partial_trace_unverified", "run": run},
        )
        verification_started = time.monotonic()
        if case.id == "repair-08":
            resource = habitat.structured(
                "test ! -e /tmp/unavailable-resource.fixture && test ! -L /tmp/unavailable-resource.fixture",
                3,
            )
            run["environment_checks"] = {
                "external_asset_absent": resource["exit_code"] == 0,
                "resource_probe": resource,
            }
        habitat.freeze()
        changed = changed_files(before, snapshot(workspace))
        if run["status"].startswith("infrastructure_"):
            check = {"passed": None, "reason": run["status"], "executed": False}
        elif changed - set(case.allowed_changes):
            check = {
                "passed": False,
                "reason": "out_of_scope_changes",
                "files": sorted(changed),
            }
        else:
            check = grade(case, run, workspace, workspace, SANDBOX_IMAGE)
        row = {
            "id": identifier,
            "model": profile["id"],
            "hf_id": profile["hf_id"],
            "revision": profile["revision"],
            "role": case.role,
            "scenario": case.id,
            "repetition": repetition,
            "repo_sha": sha,
            "configuration": model.configuration,
            "load_seconds": model.load_seconds,
            "status": run["status"],
            "passed": check["passed"],
            "verification": check,
            "patch": patch(case, workspace),
            "changed_files": sorted(changed),
            **run,
            "seconds": time.monotonic() - trial_started,
            "model_tool_seconds": run["seconds"],
            "setup_seconds": setup_seconds,
            "verification_seconds": time.monotonic() - verification_started,
            "timing": {
                "coding_seconds": run["seconds"],
                "request_wall_seconds": run["seconds"],
                "total_seconds": time.monotonic() - trial_started,
            },
            "input_tokens": model.input_tokens - token_start[0],
            "output_tokens": model.output_tokens - token_start[1],
            "peak_vram_bytes": model.memory()["cuda_peak_reserved_bytes"],
            "vram_measurement": "torch.cuda.max_memory_reserved_not_physical_vram",
            "cuda_peak_allocated_bytes": model.memory().get(
                "cuda_peak_allocated_bytes"
            ),
            "cuda_peak_reserved_bytes": model.memory()["cuda_peak_reserved_bytes"],
            "peak_ram_bytes": memory.peak,
            "ram_measurement": "model_worker_RSS_sampled_50ms",
            "split": "test",
            "training_allowed": False,
            "problem_group": "venom-maintenance-v1:" + case.id,
        }
        if run["status"].startswith("infrastructure_"):
            row["status"], row["blocked_reason"] = "blocked", run["status"]
            row["termination_status"] = run["status"]
            if run.get("infrastructure_error", {}).get("phase") == "generation":
                row["output_tokens"] = None
        _write(output / (identifier + JSON_SUFFIX), row)
        return row
    finally:
        if habitat is not None:
            habitat.close()
        # Only this newly generated, UUID-named copy is removed.
        if (
            workspace.exists()
            and workspace.parent == output / "workspaces"
            and workspace.name == identifier
        ):
            shutil.rmtree(workspace)


def _finalist_score(group: list[dict]):
    if len(group) != 10 or any(r["status"] == "blocked" for r in group):
        return None
    primary = [r for r in group if r["scenario"] not in {"repair-08", "repair-10"}]
    correct = sum(bool(r["passed"]) for r in primary)
    return (-correct, sum(r["seconds"] for r in group)) if correct else None


def choose_finalists(rows: list[dict]) -> dict[str, list[str]]:
    finalists = {}
    for role in ["operator", "repair", "localization"]:
        baseline = [r for r in rows if r["role"] == role and r["repetition"] == 0]
        scores = []
        for model in sorted({r["model"] for r in baseline}):
            score = _finalist_score([r for r in baseline if r["model"] == model])
            if score is not None:
                scores.append((*score, model))
        finalists[role] = [item[2] for item in sorted(scores)[:2]]
    return finalists


def _configure_worker(repo: Path) -> None:
    import yaml

    from venom_core.core.permission_guard import permission_guard

    required = yaml.safe_load((repo / "config/skill_permissions.yaml").read_text())[
        "ShellSkill"
    ]
    if not permission_guard.set_level(required):
        raise RuntimeError("experiment_permission_profile_unavailable")


def _release_failed_load() -> None:
    import gc

    gc.collect()
    try:
        import torch

        torch.cuda.empty_cache()
    except ImportError:
        return


def _runtime_environment() -> dict:
    packages: dict[str, str | None] = {}
    for name in ["torch", "transformers", "bitsandbytes", "kernels", "einops"]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    gpu = None
    try:
        import torch

        if torch.cuda.is_available():
            gpu = {
                "name": torch.cuda.get_device_name(0),
                "total_memory_bytes": torch.cuda.get_device_properties(0).total_memory,
            }
    except (ImportError, RuntimeError):
        gpu = None
    return {
        "host_python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "gpu": gpu,
    }


class Experiment:
    """Own one immutable configuration and its role-specific attempt ledger."""

    def __init__(self, arguments):
        self.arguments = arguments
        self.started = time.monotonic()
        self.load_events: list[dict] = []
        self.repo, self.output = (
            Path(arguments.repo).resolve(),
            Path(arguments.out).resolve(),
        )
        self.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.output.chmod(0o700)
        self.phase = arguments.phase
        models, _ = load_all_models(self.repo / "config/maintenance_comparison")
        requested = arguments.models.split(",")
        self.models = [
            m for m in models if m["id"] in requested or m["hf_id"] in requested
        ]
        if len(self.models) != len(set(requested)):
            raise ValueError("unknown_maintenance_model")
        roles = {
            task.removeprefix("maintenance_") for task in arguments.tasks.split(",")
        }
        self.cases = [c for c in build_scenarios(self.repo) if c.role in roles]
        if self.phase == "flaky_diagnostic":
            from dataclasses import replace

            selected_case = next(
                c for c in build_scenarios(self.repo) if c.id == "operator-01"
            )
            self.cases = [
                replace(
                    selected_case,
                    prompt="Run python -m pytest -q test_visible.py exactly three times without edits. Compare actual exit codes. End with success for consistent results or escalated for inconsistent results; report all outcomes.",
                    flaky_probe=True,
                )
            ]
        self.sha = json.loads(
            (self.repo / "config/maintenance_comparison/models.json").read_text()
        )["repo_sha"]
        self.rows: list[dict] = []
        self.planned: list[dict] = []
        self.configuration_id = self._manifest()
        self._extend_plan(0, None)

    def _manifest(self) -> str:
        tracked = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, text=True
        ).strip()
        roots = [
            self.repo / "venom_core/services/maintenance_comparison",
            self.repo / "config/maintenance_comparison",
        ]
        files = [
            f
            for root in roots
            for f in root.rglob("*")
            if f.is_file() and f.suffix in {".py", JSON_SUFFIX}
        ]
        fingerprints = {
            str(f.relative_to(self.repo)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in files
        }
        environment = _runtime_environment()
        selection = {
            "models": [m["id"] for m in self.models],
            "roles": sorted({c.role for c in self.cases}),
        }
        identity = hashlib.sha256(
            json.dumps(
                {
                    "files": fingerprints,
                    "seconds": self.arguments.timeout,
                    "phase": self.phase,
                    "environment": environment,
                    "selection": selection,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        _write(
            self.output / "configuration.json",
            {
                "id": identity,
                "harness_commit": tracked,
                "file_sha256": fingerprints,
                "phase": self.phase,
                "seconds": self.arguments.timeout,
                "selection": selection,
            },
        )
        _write(
            self.output / "environment.json",
            {
                **environment,
                "repo_sha": self.sha,
                "sandbox_image": SANDBOX_IMAGE,
                "sandbox_environment": {"PYTEST_ADDOPTS": PYTEST_PROFILE},
                "target_hardware_profile": "rtx3060-12gb",
                "created_at": datetime.now(timezone.utc),
            },
        )
        return identity

    def _save(self) -> None:
        _state(self.rows, self.output, Path(self.arguments.state_file), self.planned)

    def _extend_plan(self, repetition: int, finalists) -> None:
        if self.phase not in {"comparison", "baseline"}:
            return
        for model in self.models:
            for case in self._model_cases(model, finalists):
                self.planned.append(
                    {
                        "id": str(uuid4()),
                        "model": model["id"],
                        "scenario": case.id,
                        "role": case.role,
                        "repetition": repetition,
                    }
                )
        _write(self.output / "plan.json", self.planned)
        self._save()

    def _model_cases(self, profile, finalists):
        eligible = [c for c in self.cases if c.role in profile["roles"]]
        if finalists is None:
            return eligible
        return [c for c in eligible if profile["id"] in finalists.get(c.role, [])]

    def _append(self, row) -> None:
        row.update(configuration_id=self.configuration_id, repo_sha=self.sha)
        self.rows.append(row)
        _write(self.output / (row["id"] + JSON_SUFFIX), row)
        self._save()
        print(
            json.dumps(
                {
                    "event": "attempt_finished",
                    "model": row["model"],
                    "scenario": row["scenario"],
                    "status": row["status"],
                    "passed": row["passed"],
                }
            ),
            flush=True,
        )

    async def _attempt(self, model, profile, case, repetition):
        _write(
            self.output / PROGRESS_FILE,
            {
                "stage": "attempt_running",
                "model": profile["id"],
                "scenario": case.id,
                "repetition": repetition,
            },
        )
        identifier = str(uuid4())
        try:
            return await trial(
                model,
                profile,
                case,
                self.repo,
                self.sha,
                self.output,
                repetition,
                self.arguments.timeout,
                identifier=identifier,
            )
        except Exception as exc:
            row = _blocked(
                profile, case, "trial_infrastructure:" + type(exc).__name__, repetition
            )
            row["infrastructure_detail"] = str(exc)[:2000]
            artifact = self.output / f"{identifier}{JSON_SUFFIX}"
            if artifact.exists():
                row["partial_artifact"] = str(artifact)
            return row

    async def _qualify(self, model, profile, repetition) -> bool:
        role = "localization" if profile["roles"] == ["localization"] else "operator"
        finish = (
            "localization_finish with locations []"
            if role == "localization"
            else "Finish with status success and a summary of the actual result"
        )
        terminal = "terminal" if role == "localization" else "Terminal"
        prompt = (
            "First call "
            + terminal
            + " with command printf MAINTENANCE_PROTOCOL_OK. Observe the tool result. Then call "
            + finish
            + "."
        )
        case = Scenario(role + "-00", role, prompt, protocol_probe=True)
        probe = await trial(
            model, profile, case, self.repo, self.sha, self.output, repetition, 60
        )
        probe["phase"] = "technical_qualification_not_comparison"
        terminal_observed = any(
            c["name"] == "Terminal"
            and c["result"].get("stdout") == "MAINTENANCE_PROTOCOL_OK"
            for c in probe["calls"]
        )
        passed = bool(
            probe["model_finished"]
            and terminal_observed
            and sum(m["role"] == "assistant" for m in probe["messages"]) >= 2
        )
        probe["passed"] = passed
        probe["verification"] = {"passed": passed, "reason": "technical_round_trip"}
        _write(self.output / (probe["id"] + JSON_SUFFIX), probe)
        _write(
            self.output / (profile["id"] + "-protocol-qualification.json"),
            {"phase": probe["phase"], "passed": passed, "artifact": probe["id"]},
        )
        return passed

    async def _loaded(self, model, profile, cases, repetition) -> None:
        sera_operator = profile["id"] == "sera-8b" and any(
            c.role == "operator" for c in cases
        )
        qualified = True
        if self.phase == "qualification" or sera_operator:
            try:
                qualified = await self._qualify(model, profile, repetition)
            except Exception as exc:
                qualified = False
                _write(
                    self.output / f"{profile['id']}-qualification-error.json",
                    {"error_class": type(exc).__name__, "detail": str(exc)[:2000]},
                )
        if self.phase == "qualification":
            return
        for case in cases:
            if sera_operator and case.role == "operator" and not qualified:
                row = _blocked(
                    profile, case, "sera_operator_protocol_not_qualified", repetition
                )
            else:
                row = await self._attempt(model, profile, case, repetition)
            self._append(row)

    def _load_failure(self, profile, cases, repetition, error) -> None:
        _write(
            self.output / (profile["id"] + "-load-error.json"),
            {
                "phase": self.phase,
                "error_class": type(error).__name__,
                "detail": str(error)[:2000],
            },
        )
        if self.phase == "qualification":
            return
        for case in cases:
            row = _blocked(
                profile, case, "model_load:" + type(error).__name__, repetition
            )
            row["infrastructure_detail"] = str(error)[:2000]
            self._append(row)

    async def _model(self, profile, cases, repetition) -> None:
        require_host_owner()
        _write(
            self.output / PROGRESS_FILE,
            {
                "stage": "model_loading",
                "model": profile["id"],
                "repetition": repetition,
            },
        )
        model = None
        try:
            try:
                model = LocalModel(profile, CACHE_ROOT / "hub")
                self.load_events.append(
                    {
                        "model": profile["id"],
                        "repetition": repetition,
                        "seconds": getattr(model, "load_seconds", None),
                    }
                )
                _write(self.output / "model-loads.json", self.load_events)
            except Exception as exc:
                self._load_failure(profile, cases, repetition, exc)
                return
            await self._loaded(model, profile, cases, repetition)
        finally:
            if model is not None:
                model.close()
            else:
                _release_failed_load()

    async def run(self) -> None:
        for repetition in range(3 if self.phase == "comparison" else 1):
            finalists = choose_finalists(self.rows) if repetition else None
            if finalists is not None:
                _write(self.output / "finalists.json", finalists)
                self._extend_plan(repetition, finalists)
            for profile in self.models:
                cases = self._model_cases(profile, finalists)
                if cases:
                    await self._model(profile, cases, repetition)
            if repetition == 0 and not any(choose_finalists(self.rows).values()):
                return

    def finish(self, interrupted: str | None) -> None:
        _write(
            self.output / "summary.json",
            {
                "wall_seconds": time.monotonic() - self.started,
                "model_load_events": self.load_events,
                "interrupted": interrupted,
                "configuration_id": self.configuration_id,
            },
        )
        if interrupted is not None:
            done = {(r["model"], r["scenario"], r["repetition"]) for r in self.rows}
            models, cases = (
                {m["id"]: m for m in self.models},
                {c.id: c for c in self.cases},
            )
            for item in self.planned:
                if (item["model"], item["scenario"], item["repetition"]) not in done:
                    self._append(
                        _blocked(
                            models[item["model"]],
                            cases[item["scenario"]],
                            "experiment_interrupted:" + interrupted,
                            item["repetition"],
                        )
                    )
        _write(
            self.output / "training-records.json",
            [
                {
                    "problem_group": r.get(
                        "problem_group", "venom-maintenance-v1:" + r["scenario"]
                    ),
                    "split": "test",
                    "training_allowed": False,
                    "verified": r["passed"],
                    "attempt": r["id"],
                    "configuration_id": r.get("configuration_id"),
                    "partial_artifact": r.get("partial_artifact"),
                    "model": r["hf_id"],
                    "revision": r["revision"],
                    "purpose": "held_out_evaluation"
                    if self.phase in {"comparison", "baseline"}
                    else self.phase,
                    "status": r["status"],
                    "repo_sha": r["repo_sha"],
                    "messages": r.get("messages"),
                    "tool_results": r.get("calls"),
                }
                for r in self.rows
            ],
        )
        _write(
            self.output / PROGRESS_FILE,
            {
                "stage": "interrupted" if interrupted else "finished",
                "attempts": len(self.rows),
                "phase": self.phase,
            },
        )
        if self.phase in {"comparison", "baseline"}:
            render(
                self.models,
                self.rows,
                self.output,
                sorted({c.role for c in self.cases}),
                phase=self.phase,
            )
        elif self.phase == "flaky_diagnostic":
            (self.output / "FLAKY_DIAGNOSTIC.md").write_text(
                "# Jawne badanie powtarzalności testu\n\nKontrolowany przypadek operator-01 wykonano z jawnym zezwoleniem na trzy identyczne wywołania. Nie jest to część baseline ani dowód braku niestabilności dla innych testów.\n"
                + "\n".join(
                    f"- {r['model']}: {r['status']}; weryfikacja={r['passed']}"
                    for r in self.rows
                )
            )
        else:
            (self.output / "QUALIFICATION.md").write_text(
                "# Techniczna kwalifikacja adapterów\n\nPróby techniczne i blokady zapisano w *-protocol-qualification.json i *-load-error.json. Nie wchodzą do baseline 180 prób ani powtórzeń finalistów.\n"
            )


def validate_worker_paths(arguments) -> tuple[Path, Path, Path]:
    """CLI paths must match the host-issued run under this installed repository."""
    repo = Path(__file__).resolve().parents[3]
    run_id = str(UUID(os.environ["VENOM_MAINTENANCE_RUN_ID"]))
    root = Path(
        os.environ.get(
            "VENOM_MAINTENANCE_OUTPUT_ROOT", str(repo / "data/benchmarks/coding")
        )
    )
    if not root.is_absolute():
        raise ValueError("maintenance_output_root_invalid")
    output = root / run_id
    if output.is_symlink() or not output.resolve().is_relative_to(root.resolve()):
        raise ValueError("maintenance_output_path_invalid")
    expected = {
        "repo": repo,
        "out": output,
        "state_file": output / "scheduler_state.json",
    }
    for key, path in expected.items():
        if Path(getattr(arguments, key)).resolve() != path.resolve():
            raise ValueError("maintenance_worker_path_mismatch")
    return repo, output, output / "scheduler_state.json"


async def execute(arguments) -> None:
    require_host_owner()
    repo, output, state = validate_worker_paths(arguments)
    trusted = argparse.Namespace(
        repo=str(repo),
        out=str(output),
        state_file=str(state),
        models=arguments.models,
        tasks=arguments.tasks,
        timeout=arguments.timeout,
        phase=arguments.phase,
    )
    _configure_worker(repo)
    experiment = Experiment(trusted)
    interrupted = None
    try:
        await experiment.run()
    except BaseException as exc:
        interrupted = type(exc).__name__
        raise
    finally:
        experiment.finish(interrupted)


def main() -> None:
    def terminate(_signal, _frame):
        raise KeyboardInterrupt("maintenance_worker_stopped")

    signal.signal(signal.SIGTERM, terminate)
    parser = argparse.ArgumentParser()
    for name in ["repo", "out", "models", "tasks", "state-file"]:
        parser.add_argument("--" + name, required=True)
    parser.add_argument(
        "--phase",
        choices=["comparison", "baseline", "qualification", "flaky_diagnostic"],
        default="comparison",
    )
    parser.add_argument("--timeout", type=int, default=120)
    arguments = parser.parse_args()
    asyncio.run(execute(arguments))


if __name__ == "__main__":
    main()
