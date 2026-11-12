"""Optional Optuna planner with a durable, replayable trial journal.

The campaign owns training processes and the per-campaign lock. This helper
commits one assignment or outcome per transaction. It reconstructs the TPE
study from terminal rows using public Optuna APIs and a seed derived per slot.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import subprocess
import sys
from collections.abc import Iterator
from contextlib import closing, contextmanager
from functools import lru_cache
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

OPTUNA_VERSION = "4.9.0"
NUMPY_VERSION = "2.3.5"
OPTUNA_PYTHON = "VENOM_OPTUNA_PYTHON"
_PLANNER_VERSION = 1
_MAX_TRIALS = 32
_INT_RANGES = {"rank": (1, 64), "alpha": (1, 256)}
_FLOAT_RANGES = {"learning_rate": (1e-7, 0.01), "dropout": (0.0, 0.5)}


def validate_search_space(value: object) -> dict:
    if not isinstance(value, dict) or not value:
        raise ValueError("campaign_optuna_space_required")
    if value.keys() - (_INT_RANGES.keys() | _FLOAT_RANGES.keys()):
        raise ValueError("campaign_optuna_parameter_unsupported")
    return {name: _normalize_range(name, value[name]) for name in sorted(value)}


def _normalize_range(name: str, bounds: object) -> dict:
    if (
        not isinstance(bounds, dict)
        or bounds.keys() - {"low", "high", "log"}
        or not {"low", "high"} <= bounds.keys()
    ):
        raise ValueError("campaign_search_range_invalid")
    lower, upper = (_INT_RANGES | _FLOAT_RANGES)[name]
    low, high = bounds["low"], bounds["high"]
    allowed = (int,) if name in _INT_RANGES else (int, float)
    log = bounds.get("log")
    if log is None:
        log = name == "learning_rate"
    if (
        type(low) not in allowed
        or type(high) not in allowed
        or not lower <= low < high <= upper
        or type(log) is not bool
        or (log and low <= 0)
    ):
        raise ValueError("campaign_search_range_invalid")
    numeric = int if name in _INT_RANGES else float
    return {"low": numeric(low), "high": numeric(high), "log": log}


def _contract(plan: dict) -> dict:
    digest = plan.get("plan_sha256")
    seed = plan.get("sampler_seed")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("campaign_optuna_plan_invalid")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("campaign_optuna_seed_invalid")
    return {
        "plan_sha256": digest,
        "sampler_seed": seed,
        "search_space": validate_search_space(plan.get("search_space")),
        "planner_version": _PLANNER_VERSION,
        "optuna_version": OPTUNA_VERSION,
        "numpy_version": NUMPY_VERSION,
    }


def _slot(value: int) -> int:
    if type(value) is not int or not 0 <= value < _MAX_TRIALS:
        raise ValueError("campaign_optuna_trial_number_invalid")
    return value


def _number(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("campaign_optuna_result_invalid")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("campaign_optuna_result_invalid") from exc
    if not math.isfinite(number):
        raise ValueError("campaign_optuna_result_invalid")
    return number


def _outcome(
    status: str,
    value: float | None,
    constraints: list[float] | tuple[float, ...] | None,
) -> tuple[float | None, list[float] | None]:
    if status == "FAIL" and value is None and constraints is None:
        return None, None
    if status != "COMPLETE":
        raise ValueError("campaign_optuna_result_invalid")
    score = _number(value)
    if not -1.0 <= score <= 1.0:
        raise ValueError("campaign_optuna_result_invalid")
    if constraints is None:
        return score, [0.0, 0.0]
    if not isinstance(constraints, (list, tuple)) or len(constraints) != 2:
        raise ValueError("campaign_optuna_result_invalid")
    return score, [_number(item) for item in constraints]


def _tool_python() -> str:
    path = Path(os.getenv(OPTUNA_PYTHON, ""))
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("campaign_optuna_unavailable")
    return str(path)


def _invoke(python: str, payload: dict) -> dict:
    try:
        child = subprocess.run(
            [python, "-I", str(Path(__file__).resolve())],
            input=json.dumps(payload, allow_nan=False),
            encoding="utf-8",
            capture_output=True,
            timeout=30,
            check=False,
        )
        result = json.loads(child.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ValueError("campaign_optuna_unavailable") from exc
    if not isinstance(result, dict):
        raise ValueError("campaign_optuna_response_invalid")
    if child.returncode != 0:
        error = result.get("error")
        code = (
            error
            if isinstance(error, str)
            and error.startswith("campaign_")
            and error.isidentifier()
            else "campaign_optuna_failed"
        )
        raise ValueError(code)
    return result


@lru_cache(maxsize=8)
def _probe(python: str) -> str:
    response = _invoke(python, {"operation": "probe"})
    if response.get("version") != OPTUNA_VERSION:
        raise ValueError("campaign_optuna_version_mismatch")
    return OPTUNA_VERSION


def require_optuna() -> str:
    """Return the supported version when the optional interpreter is ready."""
    return _probe(_tool_python())


def ask(directory: Path, plan: dict, index: int) -> dict:
    return _invoke(
        _tool_python(),
        {
            "operation": "ask",
            "directory": str(directory.absolute()),
            "contract": _contract(plan),
            "trial_number": _slot(index),
        },
    )


def assigned(directory: Path, plan: dict, index: int) -> dict | None:
    """Find a durable assignment without sampling or creating a journal."""
    index = _slot(index)
    database = _database_path(directory.absolute())
    if not database.exists():
        return None
    expected = _json(_contract(plan))
    try:
        # Open the existing file so SQLite can recover a hot rollback journal.
        with closing(
            sqlite3.connect(database.as_uri() + "?mode=rw", uri=True, timeout=5)
        ) as db:
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if not tables:
                return None
            pinned = db.execute("SELECT contract FROM study WHERE id = 1").fetchone()
            if pinned != (expected,):
                raise ValueError("campaign_optuna_plan_changed")
            row = db.execute(
                "SELECT params FROM trial WHERE number = ?", (index,)
            ).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("campaign_optuna_database_invalid") from exc
    return {"trial_number": index, "params": json.loads(row[0])} if row else None


def tell(
    directory: Path,
    plan: dict,
    trial_number: int,
    outcome: str,
    value: float | None = None,
    constraints: list[float] | tuple[float, ...] | None = None,
) -> None:
    score, violation = _outcome(outcome, value, constraints)
    _invoke(
        _tool_python(),
        {
            "operation": "tell",
            "directory": str(directory.absolute()),
            "contract": _contract(plan),
            "trial_number": _slot(trial_number),
            "outcome": outcome,
            "value": score,
            "constraints": violation,
        },
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _database_path(directory: Path) -> Path:
    if directory.resolve() != directory or (
        directory.exists() and not directory.is_dir()
    ):
        raise ValueError("campaign_optuna_directory_invalid")
    database = directory / "optuna.sqlite3"
    if database.is_symlink() or (database.exists() and not database.is_file()):
        raise ValueError("campaign_optuna_database_invalid")
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = database.with_name(database.name + suffix)
        if sidecar.is_symlink() or (sidecar.exists() and not sidecar.is_file()):
            raise ValueError("campaign_optuna_database_invalid")
    return database


def _open_private_database(directory: Path) -> Path:
    database = _database_path(directory)
    fd = os.open(
        database, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
    )
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("campaign_optuna_database_invalid")
    finally:
        os.close(fd)
    return database


@contextmanager
def _transaction(directory: Path, contract: dict) -> Iterator[sqlite3.Connection]:
    database = _open_private_database(directory)
    with closing(sqlite3.connect(database, timeout=5)) as db, db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "CREATE TABLE IF NOT EXISTS study "
            "(id INTEGER PRIMARY KEY CHECK (id = 1), contract TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS trial "
            "(number INTEGER PRIMARY KEY, params TEXT NOT NULL, "
            "outcome TEXT, value REAL, constraints_json TEXT)"
        )
        pinned = _json(contract)
        row = db.execute("SELECT contract FROM study WHERE id = 1").fetchone()
        if row is None:
            db.execute("INSERT INTO study VALUES (1, ?)", (pinned,))
        elif row[0] != pinned:
            raise ValueError("campaign_optuna_plan_changed")
        yield db


def _sampler_seed(seed: int, slot: int) -> int:
    data = hashlib.sha256(f"{_PLANNER_VERSION}:{seed}:{slot}".encode()).digest()
    return int.from_bytes(data[:4], "big")


def _sample(optuna: Any, contract: dict, history: list[tuple], index: int) -> dict:
    distributions = {
        name: (
            optuna.distributions.IntDistribution
            if name in _INT_RANGES
            else optuna.distributions.FloatDistribution
        )(**bounds)
        for name, bounds in contract["search_space"].items()
    }
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(
            seed=_sampler_seed(contract["sampler_seed"], index),
            n_startup_trials=2,
            constraints_func=lambda trial: trial.user_attrs["constraints"],
        ),
        pruner=optuna.pruners.NopPruner(),
    )
    for _, params, status, value, constraints in history:
        study.enqueue_trial(
            json.loads(params),
            user_attrs={"constraints": json.loads(constraints) or [0.0, 0.0]},
        )
        replay = study.ask(fixed_distributions=distributions)
        if replay.params != json.loads(params):
            raise ValueError("campaign_optuna_history_invalid")
        study.tell(replay, values=value, state=optuna.trial.TrialState[status])
    return study.ask(fixed_distributions=distributions).params


def _ask(db: sqlite3.Connection, optuna: Any, contract: dict, index: int) -> dict:
    history = db.execute(
        "SELECT number, params, outcome, value, constraints_json FROM trial ORDER BY number"
    ).fetchall()
    if any(row[0] != number for number, row in enumerate(history)):
        raise ValueError("campaign_optuna_history_invalid")
    if index < len(history):
        return {"trial_number": index, "params": json.loads(history[index][1])}
    if index != len(history) or any(row[2] is None for row in history):
        raise ValueError("campaign_optuna_trial_pending")
    params = _sample(optuna, contract, history, index)
    db.execute(
        "INSERT INTO trial (number, params) VALUES (?, ?)", (index, _json(params))
    )
    return {"trial_number": index, "params": params}


def _tell(db: sqlite3.Connection, request: dict) -> None:
    index = request["trial_number"]
    status = request["outcome"]
    value, constraints = _outcome(
        status, request.get("value"), request.get("constraints")
    )
    row = db.execute(
        "SELECT outcome, value, constraints_json FROM trial WHERE number = ?", (index,)
    ).fetchone()
    if row is None:
        raise ValueError("campaign_optuna_trial_missing")
    evidence = (status, value, _json(constraints))
    if row[0] is None:
        db.execute(
            "UPDATE trial SET outcome = ?, value = ?, constraints_json = ? WHERE number = ?",
            (*evidence, index),
        )
    elif row != evidence:
        raise ValueError("campaign_optuna_result_conflict")


def _check_versions() -> None:
    try:
        installed = (version("optuna"), version("numpy"))
    except PackageNotFoundError as exc:
        raise ValueError("campaign_optuna_unavailable") from exc
    if installed != (OPTUNA_VERSION, NUMPY_VERSION):
        raise ValueError("campaign_optuna_version_mismatch")


def _tool_request(request: dict) -> dict:
    _check_versions()
    operation = request["operation"]
    if operation == "probe":
        return {"version": OPTUNA_VERSION}
    contract = _contract(request["contract"])
    index = _slot(request["trial_number"])
    with _transaction(Path(request["directory"]), contract) as db:
        if operation == "ask":
            optuna = import_module("optuna")
            optuna.logging.set_verbosity(optuna.logging.WARNING)
            return _ask(db, optuna, contract, index)
        if operation == "tell":
            _tell(db, request)
            return {}
    raise ValueError("campaign_optuna_operation_invalid")


def _main() -> int:
    try:
        result = _tool_request(json.load(sys.stdin))
    except (
        KeyError,
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        sqlite3.Error,
    ) as exc:
        code = str(exc)
        if not code.startswith("campaign_") or not code.isidentifier():
            code = "campaign_optuna_failed"
        print(_json({"error": code}))
        return 1
    print(_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
