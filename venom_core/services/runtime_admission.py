"""Public host ownership contract for bounded, optional runtime experiments.

The ledger is shared by every host consumer when enabled before host startup.
Tokens are host capabilities, never browser/model supplied identifiers. A lease
has no TTL: cancellation and caller disconnection cannot prove GPU quiescence.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from fastapi import HTTPException

from venom_core.config import SETTINGS
from venom_core.core.environment_policy import ensure_data_mutation_allowed

RUNTIME_ADMISSION_API_VERSION = 1
_T = TypeVar("_T")
_CURRENT_OPERATION: ContextVar[str | None] = ContextVar(
    "runtime_operation", default=None
)
_CURRENT_LEASE: ContextVar[str | None] = ContextVar("runtime_lease", default=None)


class RuntimeAdmissionError(HTTPException):
    """Stable error code; presentation/translation belongs to the caller."""

    def __init__(self, code: str = "runtime_busy") -> None:
        self.code = code
        super().__init__(status_code=409, detail={"code": code})


class RuntimeAdmission:
    """SQLite-serialized host admission, with durable crash/quarantine evidence.

    One API worker is qualified. A shared file still closes admission races
    between processes, but does not qualify multi-worker module lifecycles.
    Constructor does not create files; disabled hosts keep their old behavior.
    """

    def __init__(self, database: Path, *, enabled: bool = True) -> None:
        self.database = database
        self.enabled = enabled

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        ensure_data_mutation_allowed("runtime_admission")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS lease (id INTEGER PRIMARY KEY CHECK(id=1), "
                "token TEXT UNIQUE, owner TEXT, run_id TEXT, engine TEXT, model TEXT, "
                "pid INTEGER, cancelled INTEGER DEFAULT 0, quarantine INTEGER DEFAULT 0)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS operation (token TEXT PRIMARY KEY, "
                "lease_token TEXT, kind TEXT, pid INTEGER, uncertain INTEGER DEFAULT 0)"
            )
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _require_supported(self) -> None:
        if not self.enabled:
            raise RuntimeAdmissionError("runtime_admission_disabled")
        for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
            if os.environ.get(name, "1") != "1":
                raise RuntimeAdmissionError("runtime_topology_unsupported")

    def acquire(
        self, *, owner: str, run_id: str, engine: str, model: str
    ) -> RuntimeLease:
        """Reserve a host-issued identity before loading any experiment weights."""
        self._require_supported()
        fields = (owner, run_id, engine, model)
        if any(
            not isinstance(value, str) or not value.strip() or len(value) > 512
            for value in fields
        ):
            raise RuntimeAdmissionError("runtime_identity_invalid")
        with self._transaction() as db:
            if (
                db.execute("SELECT 1 FROM lease").fetchone()
                or db.execute("SELECT 1 FROM operation").fetchone()
            ):
                raise RuntimeAdmissionError()
            token = uuid4().hex
            db.execute(
                "INSERT INTO lease (id,token,owner,run_id,engine,model,pid) VALUES (1,?,?,?,?,?,?)",
                (token, owner, run_id, engine, model, os.getpid()),
            )
        return RuntimeLease(self, token)

    def snapshot(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "api_version": RUNTIME_ADMISSION_API_VERSION,
                "status": "disabled",
                "active_operations": 0,
            }
        with self._transaction() as db:
            lease = db.execute("SELECT * FROM lease").fetchone()
            operations = db.execute("SELECT COUNT(*) FROM operation").fetchone()[0]
            uncertain = db.execute(
                "SELECT COUNT(*) FROM operation WHERE uncertain=1"
            ).fetchone()[0]
        status = "busy" if operations else "available"
        result: dict[str, Any] = {
            "api_version": RUNTIME_ADMISSION_API_VERSION,
            "status": status,
            "active_operations": operations,
        }
        if uncertain:
            result["status"] = "quarantined"
        if lease is not None:
            result.update(
                {key: lease[key] for key in ("owner", "run_id", "engine", "model")}
            )
            if lease["quarantine"] or lease["pid"] != os.getpid():
                result["status"] = "quarantined"
            else:
                result["status"] = "cancelling" if lease["cancelled"] else "owned"
        return result

    def _enter(
        self, kind: str, *, mutation: bool = False, token: str | None = None
    ) -> str | None:
        if not self.enabled:
            return None
        # The outer operation's context is a capability, not just a claimed owner.
        inherited = _CURRENT_OPERATION.get()
        with self._transaction() as db:
            if (
                inherited
                and db.execute(
                    "SELECT 1 FROM operation WHERE token=? AND uncertain=0",
                    (inherited,),
                ).fetchone()
            ):
                return None
            lease = db.execute("SELECT * FROM lease").fetchone()
            if lease is not None:
                if token != lease["token"] or lease["quarantine"] or lease["cancelled"]:
                    raise RuntimeAdmissionError()
            elif token is not None:
                raise RuntimeAdmissionError("runtime_lease_invalid")
            if mutation and db.execute("SELECT 1 FROM operation").fetchone():
                raise RuntimeAdmissionError()
            operation = uuid4().hex
            db.execute(
                "INSERT INTO operation (token,lease_token,kind,pid) VALUES (?,?,?,?)",
                (operation, token, kind, os.getpid()),
            )
            return operation

    def _finish(self, operation: str | None, *, uncertain: bool) -> None:
        if operation is None:
            return
        with self._transaction() as db:
            row = db.execute(
                "SELECT * FROM operation WHERE token=?", (operation,)
            ).fetchone()
            if row is None:
                return
            if uncertain and row["lease_token"]:
                db.execute(
                    "UPDATE lease SET quarantine=1 WHERE token=?", (row["lease_token"],)
                )
            if uncertain and not row["lease_token"]:
                # A failed host transport might have left work in its daemon.
                # Keep evidence for experiment admission/recovery; normal host
                # generations keep existing scheduling semantics.
                db.execute(
                    "UPDATE operation SET uncertain=1 WHERE token=?", (operation,)
                )
            else:
                db.execute("DELETE FROM operation WHERE token=?", (operation,))

    @contextmanager
    def operation(
        self,
        *,
        kind: str,
        mutation: bool = False,
        lease_token: str | None = None,
        confirm_quiescent: Callable[[], bool] | None = None,
    ) -> Iterator[None]:
        """Cover real work, not just queueing it or waiting on its HTTP caller."""
        token = lease_token or _CURRENT_LEASE.get()
        operation = self._enter(kind, mutation=mutation, token=token)
        context = _CURRENT_OPERATION.set(operation or _CURRENT_OPERATION.get())
        lease_context = _CURRENT_LEASE.set(token)
        uncertain = False
        try:
            yield
        except BaseException:
            uncertain = confirm_quiescent is None or not confirm_quiescent()
            raise
        finally:
            _CURRENT_LEASE.reset(lease_context)
            _CURRENT_OPERATION.reset(context)
            self._finish(operation, uncertain=uncertain)

    def _cancel(self, token: str) -> None:
        with self._transaction() as db:
            db.execute("UPDATE lease SET cancelled=1 WHERE token=?", (token,))

    def _release(self, token: str) -> bool:
        with self._transaction() as db:
            row = db.execute("SELECT * FROM lease").fetchone()
            if row is None:
                return True
            if row["token"] != token:
                raise RuntimeAdmissionError("runtime_lease_invalid")
            if (
                row["quarantine"]
                or row["pid"] != os.getpid()
                or db.execute("SELECT 1 FROM operation").fetchone()
            ):
                return False
            db.execute("DELETE FROM lease WHERE token=?", (token,))
            return True

    def recover(
        self,
        *,
        confirm_quiescent: Callable[[], bool],
        expected_token: str | None = None,
    ) -> bool:
        """Trusted host-only recovery after verified daemon/worker quiescence.

        A UI flag, closed socket, expired deadline or empty CUDA cache is not a
        verifier. The callback must check the owned worker and GPU completion.
        Current live operations cannot be erased even by a positive verifier.
        """
        self._require_supported()
        with self._transaction() as db:
            current = db.execute("SELECT token FROM lease").fetchone()
            if (
                expected_token is not None
                and current is not None
                and current["token"] != expected_token
            ):
                raise RuntimeAdmissionError("runtime_lease_invalid")
            if db.execute(
                "SELECT 1 FROM operation WHERE uncertain=0 AND pid=?", (os.getpid(),)
            ).fetchone():
                return False
            if not confirm_quiescent():
                return False
            db.execute("DELETE FROM operation")
            db.execute("DELETE FROM lease")
        return True


@dataclass(frozen=True)
class RuntimeLease:
    """Opaque host capability. Persist public identity, never this token."""

    _admission: RuntimeAdmission
    _token: str

    @contextmanager
    def operation(
        self,
        *,
        kind: str = "generation",
        confirm_quiescent: Callable[[], bool] | None = None,
    ) -> Iterator[None]:
        with self._admission.operation(
            kind=kind, lease_token=self._token, confirm_quiescent=confirm_quiescent
        ):
            yield

    async def run(
        self,
        factory: Callable[[], Awaitable[_T]],
        *,
        confirm_quiescent: Callable[[], bool] | None = None,
    ) -> _T:
        """Keep ownership until the actual task finishes, despite waiter cancel.

        Adapters must await their child process/CUDA completion before returning.
        A bounded model request may continue while the run is cancelling.
        """

        async def execute() -> _T:
            with self.operation(confirm_quiescent=confirm_quiescent):
                return await factory()

        task = asyncio.create_task(execute())
        # A cancelled waiter cannot retrieve a late worker exception itself.
        task.add_done_callback(
            lambda done: None if done.cancelled() else done.exception()
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            self.cancel()
            raise

    def cancel(self) -> None:
        self._admission._cancel(self._token)

    def release(self) -> bool:
        return self._admission._release(self._token)

    def recover(self, *, confirm_quiescent: Callable[[], bool]) -> bool:
        return self._admission.recover(
            confirm_quiescent=confirm_quiescent, expected_token=self._token
        )


_ADMISSION: RuntimeAdmission | None = None


def get_runtime_admission() -> RuntimeAdmission:
    """Public capability entrypoint for host and optional modules (API v1)."""
    global _ADMISSION
    if _ADMISSION is None:
        _ADMISSION = RuntimeAdmission(
            (Path(__file__).resolve().parents[2] / SETTINGS.MEMORY_ROOT)
            / "runtime-admission.sqlite3",
            enabled=SETTINGS.RUNTIME_ADMISSION_ENABLED,
        )
    return _ADMISSION


def admitted_operation(kind: str, *, mutation: bool = False) -> Callable[[Any], Any]:
    """Guard sync, async and streaming host entrypoints without changing results."""

    def decorate(function: Any) -> Any:
        import inspect

        if inspect.isasyncgenfunction(function):

            @wraps(function)
            async def stream(*args: Any, **kwargs: Any) -> Any:
                with get_runtime_admission().operation(kind=kind, mutation=mutation):
                    async for item in function(*args, **kwargs):
                        yield item

            return stream
        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def asynchronous(*args: Any, **kwargs: Any) -> Any:
                with get_runtime_admission().operation(kind=kind, mutation=mutation):
                    return await function(*args, **kwargs)

            return asynchronous
        if inspect.isgeneratorfunction(function):

            @wraps(function)
            def generator(*args: Any, **kwargs: Any) -> Any:
                with get_runtime_admission().operation(kind=kind, mutation=mutation):
                    yield from function(*args, **kwargs)

            return generator

        @wraps(function)
        def synchronous(*args: Any, **kwargs: Any) -> Any:
            with get_runtime_admission().operation(kind=kind, mutation=mutation):
                return function(*args, **kwargs)

        return synchronous

    return decorate
