"""
Moduł: benchmark_coding - Serwis zarządzania coding benchmarkami Ollama.

Odpowiada za:
- Uruchamianie schedulera benchmarków codingowych jako subproces
- Śledzenie stanu uruchomień (pending/running/completed/failed)
- Odczyt wyników z pliku scheduler_state.json
- Trwałe przechowywanie metadanych run w katalogu storage_dir
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

_SCHEDULER_SCRIPT = "scripts/ollama_bench/scheduler.py"
_VALID_TASKS = frozenset(
    {"python_sanity", "python_simple", "python_complex", "python_complex_bugfix"}
)
_VALID_STATUS = frozenset(
    {"pending", "running", "completed", "completed_with_failures", "failed"}
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_valid_run_id(value: str) -> bool:
    """Waliduje run_id jako kanoniczny UUID."""
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return str(parsed) == value


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@dataclass
class CodingRunConfig:
    """Konfiguracja uruchomienia coding benchmarku."""

    models: list[str]
    tasks: list[str]
    loop_task: str
    first_sieve_task: str
    timeout: int
    max_rounds: int
    endpoint: str
    stop_on_failure: bool
    options: dict[str, Any]
    model_timeout_overrides: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodingJobState:
    """Stan pojedynczego joba."""

    id: str
    model: str
    mode: str
    task: str
    role: str = "main"
    status: str = "pending"
    created_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    rc: Optional[int] = None
    artifact: Optional[str] = None
    output: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodingBenchmarkRun:
    """Stan uruchomienia coding benchmarku."""

    run_id: str
    config: CodingRunConfig
    status: str = "pending"
    jobs: list[CodingJobState] = field(default_factory=list)
    created_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "config": self.config.to_dict(),
            "jobs": [j.to_dict() for j in self.jobs],
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_message": self.error_message,
        }

    def to_summary_dict(self) -> dict[str, Any]:
        total = len(self.jobs)
        completed = sum(1 for j in self.jobs if j.status == "completed")
        failed = sum(1 for j in self.jobs if j.status == "failed")
        pending = sum(1 for j in self.jobs if j.status == "pending")
        running = sum(1 for j in self.jobs if j.status == "running")
        skipped = sum(1 for j in self.jobs if j.status == "skipped")
        success_rate = round((completed / total) * 100.0, 2) if total else 0.0
        queue_finished = total > 0 and pending == 0 and running == 0
        return {
            "total_jobs": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "running": running,
            "skipped": skipped,
            "queue_finished": queue_finished,
            "success_rate": success_rate,
        }

    def to_status_dict(self) -> dict[str, Any]:
        d = self.to_dict()
        d["summary"] = self.to_summary_dict()
        # Wzbogać jobs o metryki timing z artefaktów
        d["jobs"] = [_enrich_job_dict(j) for j in self.jobs]
        return d


def _enrich_job_dict(job: CodingJobState) -> dict[str, Any]:
    """Dodaj metryki timing z pliku artefaktu jeśli istnieje."""
    d = job.to_dict()
    d.pop("output", None)
    # artifact field contains the path to the JSON artifact
    artifact_file = d.get("artifact")
    if artifact_file:
        try:
            artifact_data = json.loads(Path(artifact_file).read_text(encoding="utf-8"))
            timing = artifact_data.get("timing") or {}
            d["warmup_seconds"] = _safe_float(timing.get("warmup_seconds"))
            d["coding_seconds"] = _safe_float(timing.get("coding_seconds"))
            d["request_wall_seconds"] = _safe_float(timing.get("request_wall_seconds"))
            d["total_seconds"] = _safe_float(timing.get("total_seconds"))
            d["passed"] = artifact_data.get("passed")
            d["error"] = artifact_data.get("error")
        except Exception as exc:
            logger.warning(
                "Nie można odczytać artefaktu joba %s z %s: %s",
                d.get("id"),
                artifact_file,
                exc,
            )
    return d


def _parse_scheduler_state(state_file: Path) -> list[CodingJobState]:
    """Parsuje scheduler_state.json i zwraca listę jobów."""
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        jobs_raw = data.get("jobs", [])
        jobs = []
        for j in jobs_raw:
            if not isinstance(j, dict):
                continue
            jobs.append(
                CodingJobState(
                    id=str(j.get("id", "")),
                    model=str(j.get("model", "")),
                    mode=str(j.get("mode", "single")),
                    task=str(j.get("task", "")),
                    role=str(j.get("role", "main")),
                    status=str(j.get("status", "pending")),
                    created_at=str(j.get("created_at", "")),
                    started_at=j.get("started_at"),
                    finished_at=j.get("finished_at"),
                    rc=j.get("rc"),
                    artifact=j.get("artifact"),
                    output=j.get("output"),
                )
            )
        return jobs
    except Exception as exc:
        logger.warning(f"Nie można odczytać scheduler_state.json: {exc}")
        return []


class CodingBenchmarkService:
    """
    Serwis zarządzania coding benchmarkami Ollama.

    Uruchamia scheduler jako subproces i śledzi stan run_id.
    """

    def __init__(self, storage_dir: str, repo_root: Optional[str] = None) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.repo_root = (
            Path(repo_root).resolve()
            if repo_root
            else Path(__file__).resolve().parents[2]
        )
        self._runs: dict[str, CodingBenchmarkRun] = {}
        self._active_procs: dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()
        self._load_persisted_runs()

    def _run_dir(self, run_id: str) -> Path:
        """
        Zwraca bezpieczną ścieżkę katalogu run.

        Ścieżka jest zawsze normalizowana i musi pozostać wewnątrz storage_dir.
        """
        if not _is_valid_run_id(run_id):
            raise ValueError("Invalid run_id")
        storage_root = self.storage_dir.resolve()
        run_dir = (storage_root / run_id).resolve()
        try:
            run_dir.relative_to(storage_root)
        except ValueError as exc:
            raise ValueError("Run path escapes storage directory") from exc
        return run_dir

    def _meta_file(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "meta.json"

    def _state_file(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "scheduler_state.json"

    def _persist_meta(self, run: CodingBenchmarkRun) -> None:
        try:
            meta_path = self._meta_file(run.run_id)
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(
                json.dumps(run.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"Nie można zapisać metadanych run {run.run_id}: {exc}")

    def _load_persisted_runs(self) -> None:
        """Odczytuje wszystkie persisted runs z dysku przy starcie serwisu."""
        if not self.storage_dir.exists():
            return
        for meta_file in self.storage_dir.glob("*/meta.json"):
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                run_id = data.get("run_id", "")
                if not _is_valid_run_id(run_id):
                    continue
                cfg_d = data.get("config", {})
                cfg = CodingRunConfig(
                    models=cfg_d.get("models", []),
                    tasks=cfg_d.get("tasks", []),
                    loop_task=cfg_d.get("loop_task", ""),
                    first_sieve_task=cfg_d.get("first_sieve_task", ""),
                    timeout=int(cfg_d.get("timeout", 180)),
                    max_rounds=int(cfg_d.get("max_rounds", 3)),
                    endpoint=cfg_d.get("endpoint", "http://127.0.0.1:11434"),
                    stop_on_failure=bool(cfg_d.get("stop_on_failure", False)),
                    options=cfg_d.get("options", {}),
                    model_timeout_overrides=cfg_d.get("model_timeout_overrides", {}),
                )
                run = CodingBenchmarkRun(
                    run_id=run_id,
                    config=cfg,
                    status=data.get("status", "completed"),
                    created_at=data.get("created_at", ""),
                    started_at=data.get("started_at"),
                    finished_at=data.get("finished_at"),
                    error_message=data.get("error_message"),
                )
                # Odczytaj stan jobów z scheduler_state.json
                state_file = self._state_file(run_id)
                if state_file.exists():
                    run.jobs = _parse_scheduler_state(state_file)
                else:
                    run.jobs = [
                        CodingJobState(**j) if isinstance(j, dict) else j
                        for j in data.get("jobs", [])
                    ]
                self._normalize_loaded_run_status(run)
                with self._lock:
                    self._runs[run_id] = run
            except Exception as exc:
                logger.warning(f"Nie można załadować run {meta_file}: {exc}")

    def _normalize_loaded_run_status(self, run: CodingBenchmarkRun) -> None:
        """Normalizuje status run po restarcie serwisu na podstawie stanu jobów."""
        if run.status not in _VALID_STATUS:
            run.status = "failed"
            if not run.error_message:
                run.error_message = "Nieznany status run po restarcie serwisu."
            return

        summary = run.to_summary_dict()
        queue_finished = bool(summary["queue_finished"])
        has_failures = (summary["failed"] + summary["skipped"]) > 0
        has_jobs = summary["total_jobs"] > 0

        if run.status == "running":
            if queue_finished and has_jobs:
                run.status = "completed_with_failures" if has_failures else "completed"
                return
            run.status = "failed"
            if not run.error_message:
                run.error_message = (
                    "Run oznaczony jako running po restarcie serwisu; "
                    "oznaczono jako failed."
                )
            return

        # Migracja starych danych: queue domknięta i są błędy jobów -> status częściowo udany.
        if run.status == "failed" and queue_finished and has_jobs and has_failures:
            run.status = "completed_with_failures"

    def _validate_start_request(self, models: list[str], tasks: list[str]) -> None:
        if not models:
            raise ValueError("Lista modeli nie może być pusta")
        if not tasks:
            raise ValueError("Lista zadań nie może być pusta")
        invalid_tasks = [t for t in tasks if t not in _VALID_TASKS]
        if invalid_tasks:
            raise ValueError(
                f"Nieznane zadania: {invalid_tasks}. Dozwolone: {sorted(_VALID_TASKS)}"
            )

    def start_run(
        self,
        models: list[str],
        tasks: list[str],
        loop_task: str = "python_complex_bugfix",
        first_sieve_task: str = "",
        timeout: int = 180,
        max_rounds: int = 3,
        options: Optional[dict[str, Any]] = None,
        model_timeout_overrides: Optional[dict[str, int]] = None,
        stop_on_failure: bool = False,
        endpoint: str = "http://127.0.0.1:11434",
    ) -> str:
        """Uruchamia coding benchmark i zwraca run_id."""
        self._validate_start_request(models, tasks)
        run_id = str(uuid.uuid4())
        cfg = CodingRunConfig(
            models=list(models),
            tasks=list(tasks),
            loop_task=loop_task,
            first_sieve_task=first_sieve_task,
            timeout=timeout,
            max_rounds=max_rounds,
            endpoint=endpoint,
            stop_on_failure=stop_on_failure,
            options=options or {"temperature": 0.1, "top_p": 0.9},
            model_timeout_overrides=model_timeout_overrides or {},
        )
        run = CodingBenchmarkRun(
            run_id=run_id,
            config=cfg,
            status="pending",
            created_at=_utc_now_iso(),
        )
        with self._lock:
            self._runs[run_id] = run
        self._persist_meta(run)
        # Uruchom scheduler w tle
        thread = threading.Thread(
            target=self._run_scheduler_thread,
            args=(run_id,),
            daemon=True,
        )
        thread.start()
        return run_id

    def _build_scheduler_command(self, run: CodingBenchmarkRun) -> list[str]:
        cfg = run.config
        python_bin = sys.executable or "python3"
        scheduler = (self.repo_root / _SCHEDULER_SCRIPT).resolve()
        if not scheduler.exists():
            raise FileNotFoundError(f"Nie znaleziono schedulera: {scheduler}")
        out_dir = str(self._run_dir(run.run_id))
        cmd = [
            python_bin,
            str(scheduler),
            "--models",
            ",".join(cfg.models),
            "--tasks",
            ",".join(cfg.tasks),
            "--loop-task",
            cfg.loop_task,
            "--first-sieve-task",
            cfg.first_sieve_task,
            "--timeout",
            str(cfg.timeout),
            "--max-rounds",
            str(cfg.max_rounds),
            "--options",
            json.dumps(cfg.options, ensure_ascii=False),
            "--model-timeout-overrides",
            json.dumps(cfg.model_timeout_overrides, ensure_ascii=False),
            "--endpoint",
            cfg.endpoint,
            "--out",
            out_dir,
            "--state-file",
            str(self._state_file(run.run_id)),
        ]
        if cfg.stop_on_failure:
            cmd.append("--stop-on-failure")
        return cmd

    def _run_scheduler_thread(self, run_id: str) -> None:
        """Uruchamia scheduler w wątku i aktualizuje stan run."""
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            return

        run.status = "running"
        run.started_at = _utc_now_iso()
        self._persist_meta(run)

        cmd = self._build_scheduler_command(run)
        logger.info(f"Uruchamiam coding benchmark {run_id}")
        try:
            proc = subprocess.Popen(
                cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.repo_root),
            )
            with self._lock:
                self._active_procs[run_id] = proc
            _, stderr = proc.communicate()
            # Odczytaj finalny stan jobów
            state_file = self._state_file(run_id)
            if state_file.exists():
                run.jobs = _parse_scheduler_state(state_file)

            run.finished_at = _utc_now_iso()
            self._finalize_run_status(run, proc.returncode, stderr)
        except Exception as exc:
            logger.exception(f"Błąd schedulera dla run {run_id}")
            run.status = "failed"
            run.error_message = str(exc)
            run.finished_at = _utc_now_iso()
        finally:
            with self._lock:
                self._active_procs.pop(run_id, None)

        with self._lock:
            is_still_registered = self._runs.get(run_id) is run
        if is_still_registered:
            self._persist_meta(run)

    def _finalize_run_status(
        self, run: CodingBenchmarkRun, returncode: int, stderr_raw: str | None
    ) -> None:
        """Wyznacza końcowy status runu na podstawie rc schedulera i stanu kolejki."""
        summary = run.to_summary_dict()
        queue_finished = bool(summary["queue_finished"])
        has_failures = (summary["failed"] + summary["skipped"]) > 0
        has_jobs = summary["total_jobs"] > 0
        stderr = (stderr_raw or "").strip()

        if returncode == 0:
            if has_failures:
                run.status = "completed_with_failures"
                run.error_message = f"Run zakończony z błędami: failed={summary['failed']}, skipped={summary['skipped']}."
            else:
                run.status = "completed"
            return

        if queue_finished and has_jobs:
            if has_failures:
                run.status = "completed_with_failures"
                details = f"failed={summary['failed']}, skipped={summary['skipped']}"
                run.error_message = (
                    f"Scheduler rc={returncode} po domknięciu kolejki ({details}): {stderr[:500]}"
                    if stderr
                    else f"Scheduler rc={returncode} po domknięciu kolejki ({details})."
                )
                return
            # Defensive fallback: nie ma błędów jobów, ale scheduler zwrócił rc != 0.
            run.status = "completed"
            run.error_message = (
                f"Scheduler rc={returncode} mimo kompletnej kolejki bez błędów jobów."
            )
            return

        run.status = "failed"
        run.error_message = (
            f"Scheduler rc={returncode}: {stderr[:500]}"
            if stderr
            else f"Scheduler rc={returncode}"
        )

    def _stop_active_process(self, run_id: str) -> None:
        """Kończy aktywny proces schedulera dla run, jeśli istnieje."""
        with self._lock:
            proc = self._active_procs.get(run_id)
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
        except Exception as exc:
            logger.warning("Nie można zatrzymać procesu run %s: %s", run_id, exc)
        finally:
            with self._lock:
                self._active_procs.pop(run_id, None)

    def _refresh_running_jobs(self, run: CodingBenchmarkRun) -> None:
        """Odświeża stan jobów dla running run z scheduler_state.json."""
        if run.status != "running":
            return
        state_file = self._state_file(run.run_id)
        if state_file.exists():
            run.jobs = _parse_scheduler_state(state_file)

    def get_run_status(self, run_id: str) -> Optional[dict[str, Any]]:
        """Zwraca status run lub None jeśli nie znaleziono."""
        if not _is_valid_run_id(run_id):
            return None
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            return None
        self._refresh_running_jobs(run)
        return run.to_status_dict()

    def list_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        """Zwraca listę ostatnich run posortowanych od najnowszych."""
        with self._lock:
            all_runs = list(self._runs.values())
        all_runs.sort(key=lambda r: r.created_at, reverse=True)
        result = []
        for run in all_runs[:limit]:
            d = run.to_dict()
            d["summary"] = run.to_summary_dict()
            d.pop("jobs", None)
            result.append(d)
        return result

    def delete_run(self, run_id: str) -> bool:
        """Usuwa run. Zwraca True jeśli usunięto, False jeśli nie znaleziono."""
        if not _is_valid_run_id(run_id):
            return False
        self._stop_active_process(run_id)
        with self._lock:
            run = self._runs.pop(run_id, None)
        if run is None:
            return False
        # Usuń pliki z dysku
        try:
            import shutil

            # Use persisted run identifier from in-memory state, not raw request value.
            run_dir = self._run_dir(run.run_id)
            if run_dir.exists():
                shutil.rmtree(run_dir)
        except Exception as exc:
            logger.warning(f"Nie można usunąć katalogu run {run_id}: {exc}")
        return True

    def clear_all_runs(self) -> int:
        """Usuwa wszystkie run. Zwraca liczbę usuniętych."""
        with self._lock:
            run_ids = list(self._runs.keys())
            self._runs.clear()
        for run_id in run_ids:
            self._stop_active_process(run_id)
        count = len(run_ids)
        for run_id in run_ids:
            try:
                import shutil

                run_dir = self._run_dir(run_id)
                if run_dir.exists():
                    shutil.rmtree(run_dir)
            except Exception as exc:
                logger.warning(f"Nie można usunąć katalogu run {run_id}: {exc}")
        return count
