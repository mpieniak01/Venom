"""Public host ownership contract for bounded, optional runtime experiments.

The ledger is shared by every host consumer when enabled before host startup.
Tokens are host capabilities, never browser/model supplied identifiers. A lease
has no TTL: cancellation and caller disconnection cannot prove GPU quiescence.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import stat
import sys
import threading
from collections.abc import Awaitable, Callable, Iterator
from contextlib import aclosing, closing, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from venom_core.config import SETTINGS
from venom_core.core.environment_policy import ensure_data_mutation_allowed

RUNTIME_ADMISSION_API_VERSION = 1
# Only these HTTP rejections establish that generation never started.
REJECTED_BEFORE_WORK_HTTP_STATUSES = frozenset({400, 401, 403, 404, 405, 413, 415, 422})
_MAX_OPERATIONS = 128
_SELECT_LEASE = "SELECT * FROM lease"
_CURRENT_OPERATION: ContextVar[str | None] = ContextVar(
    "runtime_operation", default=None
)
_CURRENT_LEASE: ContextVar[str | None] = ContextVar("runtime_lease", default=None)
_CURRENT_EXECUTION: ContextVar[tuple[int, int] | None] = ContextVar(
    "runtime_execution", default=None
)


@dataclass
class _OperationEvidence:
    revision: object


_CURRENT_EVIDENCE: ContextVar[_OperationEvidence | None] = ContextVar(
    "runtime_operation_evidence", default=None
)

_HOST_LOCKS: dict[Path, tuple[int, int]] = {}
_HOST_LOCKS_MUTEX = threading.Lock()


def _own_host_namespace(database: Path) -> None:
    """Fail closed when a second API process shares this runtime namespace."""
    if not sys.platform.startswith("linux"):
        raise RuntimeAdmissionError("runtime_topology_unsupported")
    import fcntl  # Only the Linux application process uses this, never Codex tools.

    path = database.resolve().with_suffix(".host.lock")
    pid = os.getpid()
    with _HOST_LOCKS_MUTEX:
        previous = _HOST_LOCKS.get(path)
        if previous is not None and previous[0] == pid:
            return
        if previous is not None:  # A fork inherited the parent's open descriptor.
            os.close(previous[1])
            del _HOST_LOCKS[path]
        descriptor = _open_private_file(path)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(descriptor)
            raise RuntimeAdmissionError("runtime_topology_unsupported") from exc
        _HOST_LOCKS[path] = (pid, descriptor)


def process_instance_identity(pid: int) -> str | None:
    """Identify one Linux process lifetime across PID reuse and host reboot.

    Missing/denied proc metadata is unknown, never proof of process death.
    The digest contains no command line, environment or lease capability.
    """
    if type(pid) is not int or pid <= 0 or not sys.platform.startswith("linux"):
        return None
    try:
        process = Path("/proc") / str(pid)
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        before = (process / "stat").read_text().rsplit(")", 1)[1].split()[19]
        namespace = os.readlink(process / "ns/pid")
        after = (process / "stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return None
    if not boot or not before.isdecimal() or before != after or not namespace:
        return None
    return hashlib.sha256(f"{boot}\0{namespace}\0{before}".encode()).hexdigest()


def _execution_identity() -> tuple[int, int]:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return threading.get_ident(), id(task)


class RuntimeOperationRejection:
    """Typed host-transport proof bound to the operation that was rejected.

    Only a transport that observes rejection before accepting a response creates
    this marker. A status number/message supplied by a caller is never proof.
    """

    def __init__(self) -> None:
        self._rejected_operation = _CURRENT_OPERATION.get()
        evidence = _CURRENT_EVIDENCE.get()
        self._revision = evidence.revision if evidence is not None else None

    def confirms_rejection(self, operation: str | None) -> bool:
        evidence = _CURRENT_EVIDENCE.get()
        return (
            operation is not None
            and self._rejected_operation == operation
            and evidence is not None
            and self._revision is evidence.revision
        )


class RuntimeAdmissionError(HTTPException):
    """Stable error code; presentation/translation belongs to the caller."""

    def __init__(self, code: str = "runtime_busy") -> None:
        self.code = code
        super().__init__(status_code=409, detail={"code": code})


def _assert_safe_ledger_path(database: Path) -> None:
    """Reject symlinks and special files before SQLite can follow/open them."""
    for index, path in enumerate((database, *database.parents)):
        try:
            entry = path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RuntimeAdmissionError("runtime_storage_unsafe") from exc
        expected_type = stat.S_ISREG if index == 0 else stat.S_ISDIR
        if not expected_type(entry.st_mode) or (index == 0 and entry.st_nlink != 1):
            raise RuntimeAdmissionError("runtime_storage_unsafe")


def _open_private_file(path: Path) -> int:
    """Create/repair only an owned regular file, without following its symlink."""
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            entry = os.fstat(descriptor)
            if (
                not stat.S_ISREG(entry.st_mode)
                or entry.st_nlink != 1
                or entry.st_uid != os.geteuid()
            ):
                raise RuntimeAdmissionError("runtime_storage_unsafe")
            os.fchmod(descriptor, 0o600)
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor
    except OSError as exc:
        raise RuntimeAdmissionError("runtime_storage_unsafe") from exc


class RuntimeAdmission:
    """SQLite-serialized host admission, with durable crash/quarantine evidence.

    One API worker is qualified. A shared file still closes admission races
    between processes, but does not qualify multi-worker module lifecycles.
    Constructor does not create files; disabled hosts keep their old behavior.
    """

    def __init__(self, database: Path, *, enabled: bool = True) -> None:
        self.database = database
        self.enabled = enabled
        self._tasks: set[asyncio.Task[Any]] = set()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        ensure_data_mutation_allowed("runtime_admission")
        _assert_safe_ledger_path(self.database)
        self.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _assert_safe_ledger_path(self.database)
        _own_host_namespace(self.database)
        os.close(_open_private_file(self.database))
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS lease (id INTEGER PRIMARY KEY CHECK(id=1), "
                "token TEXT UNIQUE, owner TEXT, run_id TEXT, engine TEXT, model TEXT, "
                "pid INTEGER, cancelled INTEGER DEFAULT 0, quarantine INTEGER DEFAULT 0, "
                "process_identity TEXT)"
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(lease)")
            }
            if "process_identity" not in columns:
                connection.execute("ALTER TABLE lease ADD COLUMN process_identity TEXT")
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
                "INSERT INTO lease (id,token,owner,run_id,engine,model,pid,process_identity) "
                "VALUES (1,?,?,?,?,?,?,?)",
                (
                    token,
                    owner,
                    run_id,
                    engine,
                    model,
                    os.getpid(),
                    process_instance_identity(os.getpid()),
                ),
            )
        return RuntimeLease(self, token)

    def snapshot(self) -> dict[str, Any]:
        """Observe without creating storage or requiring mutation permission."""
        result: dict[str, Any] = {
            "api_version": RUNTIME_ADMISSION_API_VERSION,
            "status": "available" if self.enabled else "disabled",
            "active_operations": 0,
        }
        if not self.enabled:
            return result
        try:
            _assert_safe_ledger_path(self.database)
        except RuntimeAdmissionError as exc:
            result.update(status="quarantined", code=exc.code)
            return result
        if not self.database.exists():
            return result
        try:
            uri = self.database.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=2.0)) as db:
                db.row_factory = sqlite3.Row
                db.execute("BEGIN")  # A consistent read-only snapshot, never DDL.
                lease = db.execute(_SELECT_LEASE).fetchone()
                operations = db.execute("SELECT * FROM operation").fetchall()
        except sqlite3.Error:
            result.update(status="quarantined", code="runtime_ledger_unavailable")
            return result
        result.update(self._snapshot_rows(lease, operations))
        return result

    @contextmanager
    def recovery_startup(
        self, *, permitted: Callable[[dict[str, Any]], bool]
    ) -> Iterator[None]:
        """Open module state under exclusive host/ledger ownership in quarantine.

        This admits no generation and clears no lease. The trusted predicate
        receives a fresh snapshot inside the writer transaction and must not
        re-enter the ledger. The process-wide namespace lock remains owned.
        """
        self._require_supported()
        with self._transaction() as db:
            runtime = self._snapshot_rows(
                db.execute(_SELECT_LEASE).fetchone(),
                db.execute("SELECT * FROM operation").fetchall(),
            )
            if (
                runtime["status"] != "quarantined"
                or runtime["active_operations"] != 0
                or not permitted(runtime)
            ):
                raise RuntimeAdmissionError()
            yield

    def assert_host_available(self) -> None:
        """Read-only preflight before constructing HTTP/SSE responses.

        Actual worker admission still rechecks atomically; this is not a lease.
        """
        if not self.enabled:
            return
        self._require_supported()
        snapshot = self.snapshot()
        if "owner" in snapshot or snapshot["status"] == "quarantined":
            raise RuntimeAdmissionError()

    @staticmethod
    def _snapshot_rows(
        lease: sqlite3.Row | None, operations: list[sqlite3.Row]
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "busy" if operations else "available",
            "active_operations": len(operations),
        }
        if any(row["uncertain"] or row["pid"] != os.getpid() for row in operations):
            result["status"] = "quarantined"
        if lease is not None:
            result.update(
                {key: lease[key] for key in ("owner", "run_id", "engine", "model")}
            )
            # Process metadata lets optional modules distinguish a crash
            # quarantine from a still-live worker. Never expose the lease token.
            result["owner_pid"] = lease["pid"]
            recorded_identity = (
                lease["process_identity"]
                if "process_identity" in lease.keys()
                else None
            )
            result["owner_process_identity"] = recorded_identity
            same_instance = lease["pid"] == os.getpid() and (
                recorded_identity is None
                or recorded_identity == process_instance_identity(os.getpid())
            )
            if lease["quarantine"] or not same_instance:
                result["status"] = "quarantined"
            else:
                result["status"] = "cancelling" if lease["cancelled"] else "owned"
        return result

    @staticmethod
    def _ancestor(db: sqlite3.Connection) -> sqlite3.Row | None:
        return db.execute(
            "SELECT * FROM operation WHERE token=?",
            (_CURRENT_OPERATION.get(),),
        ).fetchone()

    @staticmethod
    def _validate_lease(
        db: sqlite3.Connection,
        *,
        token: str | None,
        kind: str,
        cleanup: bool,
        ancestor: sqlite3.Row | None,
        nested: bool = False,
    ) -> None:
        lease = db.execute(_SELECT_LEASE).fetchone()
        if lease is None:
            if token is not None:
                raise RuntimeAdmissionError("runtime_lease_invalid")
            return
        if token != lease["token"] or (
            not cleanup and (lease["quarantine"] or lease["cancelled"])
        ):
            raise RuntimeAdmissionError()
        # A lifecycle task can delegate one real operation to its owned thread.
        # Context copying never admits two generations in parallel.
        if nested:
            return
        active = db.execute(
            "SELECT kind FROM operation WHERE lease_token=?", (token,)
        ).fetchall()
        delegated = (
            ancestor is not None
            and ancestor["kind"] == "lifecycle"
            and ancestor["lease_token"] == token
        )
        if active and (
            not delegated
            or kind == "lifecycle"
            or any(row["kind"] != "lifecycle" for row in active)
        ):
            raise RuntimeAdmissionError()

    def _enter(
        self,
        kind: str,
        *,
        mutation: bool = False,
        token: str | None = None,
        detached: bool = False,
        cleanup: bool = False,
    ) -> str | None:
        if not self.enabled:
            return None
        with self._transaction() as db:
            ancestor = self._ancestor(db)
            if ancestor is not None and ancestor["kind"] == "cleanup" and not cleanup:
                raise RuntimeAdmissionError()  # Cleanup cannot start new generation.
            nested = (
                ancestor is not None
                and ancestor["kind"] != "lifecycle"
                and _CURRENT_EXECUTION.get() == _execution_identity()
                and not detached
            )
            self._validate_lease(
                db,
                token=token,
                kind=kind,
                cleanup=cleanup,
                ancestor=ancestor,
                nested=nested,
            )
            if mutation:
                own_token = ancestor["token"] if nested and ancestor is not None else ""
                if db.execute(
                    "SELECT 1 FROM operation WHERE token<>?", (own_token,)
                ).fetchone():
                    raise RuntimeAdmissionError()
            if (
                nested
                and ancestor is not None
                and (kind != "cleanup" or ancestor["kind"] == "cleanup")
            ):
                return None
            if (
                db.execute("SELECT COUNT(*) FROM operation").fetchone()[0]
                >= _MAX_OPERATIONS
            ):
                raise RuntimeAdmissionError("runtime_recovery_required")
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
            uncertain = uncertain or bool(row["uncertain"])
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
        _cleanup: bool = False,
    ) -> Iterator[None]:
        """Cover real work, not just queueing it or waiting on its HTTP caller."""
        token = lease_token or _CURRENT_LEASE.get()
        operation = self._enter(kind, mutation=mutation, token=token, cleanup=_cleanup)
        evidence = _CURRENT_EVIDENCE.get()
        if operation is not None or evidence is None:
            evidence = _OperationEvidence(object())
        else:
            # Nested work shares the operation ID, but never an earlier rejection
            # proof. Mutating its shared revision survives ContextVar restoration.
            evidence.revision = object()
        evidence_context = _CURRENT_EVIDENCE.set(evidence)
        context = _CURRENT_OPERATION.set(operation or _CURRENT_OPERATION.get())
        lease_context = _CURRENT_LEASE.set(token)
        execution_context = _CURRENT_EXECUTION.set(_execution_identity())
        uncertain = False
        try:
            yield
        except BaseException as exc:
            rejected = isinstance(
                exc, RuntimeOperationRejection
            ) and exc.confirms_rejection(_CURRENT_OPERATION.get())
            uncertain = not rejected and (
                confirm_quiescent is None or not confirm_quiescent()
            )
            raise
        finally:
            if uncertain and operation is None:
                self.mark_current_uncertain()
            _CURRENT_EXECUTION.reset(execution_context)
            _CURRENT_LEASE.reset(lease_context)
            _CURRENT_OPERATION.reset(context)
            _CURRENT_EVIDENCE.reset(evidence_context)
            self._finish(operation, uncertain=uncertain)

    def mark_current_uncertain(self) -> None:
        """Keep failure evidence even if a legacy caller catches an exception."""
        if not self.enabled or _CURRENT_OPERATION.get() is None:
            return
        operation = _CURRENT_OPERATION.get()
        with self._transaction() as db:
            db.execute("UPDATE operation SET uncertain=1 WHERE token=?", (operation,))
            db.execute(
                "UPDATE lease SET quarantine=1 WHERE token IN (SELECT lease_token FROM operation WHERE token=?)",
                (operation,),
            )

    def reserve_background(self, *, kind: str) -> Callable[[Callable[[], Any]], Any]:
        """Reserve before spawning a thread; invoke returned function exactly once.

        Only host scheduling code uses this. The reservation survives the
        caller returning and is removed when the real worker terminates.
        """
        operation = self._enter(kind, detached=True)

        def execute(function: Callable[[], Any]) -> Any:
            context = _CURRENT_OPERATION.set(operation)
            execution = _CURRENT_EXECUTION.set(_execution_identity())
            uncertain = False
            try:
                return function()
            except BaseException:
                uncertain = True
                raise
            finally:
                _CURRENT_EXECUTION.reset(execution)
                _CURRENT_OPERATION.reset(context)
                self._finish(operation, uncertain=uncertain)

        return execute

    def _cancel(self, token: str) -> None:
        with self._transaction() as db:
            db.execute("UPDATE lease SET cancelled=1 WHERE token=?", (token,))

    def _release(self, token: str) -> bool:
        with self._transaction() as db:
            row = db.execute(_SELECT_LEASE).fetchone()
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

    @contextmanager
    def cleanup(self, *, confirm_quiescent: Callable[[], bool]) -> Iterator[None]:
        """Only release this adapter's resources; generation is forbidden here."""
        verified = False
        try:
            with self._admission.operation(
                kind="cleanup",
                lease_token=self._token,
                confirm_quiescent=confirm_quiescent,
                _cleanup=True,
            ):
                try:
                    yield
                finally:
                    verified = confirm_quiescent()
                    if not verified:
                        raise RuntimeAdmissionError("runtime_quiescence_unconfirmed")
        finally:
            if verified:
                with self._admission._transaction() as db:
                    db.execute(
                        "UPDATE lease SET quarantine=0 WHERE token=?", (self._token,)
                    )
                    db.execute(
                        "UPDATE operation SET uncertain=0 WHERE lease_token=?",
                        (self._token,),
                    )

    async def run[T](
        self,
        factory: Callable[[], Awaitable[T]],
        *,
        confirm_quiescent: Callable[[], bool] | None = None,
    ) -> T:
        """Keep ownership until the actual task finishes, despite waiter cancel.

        Adapters must await their child process/CUDA completion before returning.
        A bounded model request may continue while the run is cancelling.
        """

        async def execute() -> T:
            with self.operation(kind="lifecycle", confirm_quiescent=confirm_quiescent):
                return await factory()

        task = asyncio.create_task(execute())
        # Keep a strong reference even if the HTTP waiter disappears.
        self._admission._tasks.add(task)

        def finished(done: asyncio.Task[Any]) -> None:
            self._admission._tasks.discard(done)
            if not done.cancelled():
                done.exception()

        task.add_done_callback(finished)
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


def admitted_operation(
    kind: str, *, mutation: bool = False, when: Callable[..., bool] | None = None
) -> Callable[[Any], Any]:
    """Guard sync, async and streaming host entrypoints without changing results."""

    def scope(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        if when is not None and not when(*args, **kwargs):
            return nullcontext()
        return get_runtime_admission().operation(kind=kind, mutation=mutation)

    def decorate(function: Any) -> Any:
        import inspect

        if inspect.isasyncgenfunction(function):

            @wraps(function)
            async def stream(*args: Any, **kwargs: Any) -> Any:
                with scope(args, kwargs):
                    async with aclosing(function(*args, **kwargs)) as iterator:
                        async for item in iterator:
                            yield item

            return stream
        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def asynchronous(*args: Any, **kwargs: Any) -> Any:
                with scope(args, kwargs):
                    return await function(*args, **kwargs)

            return asynchronous
        if inspect.isgeneratorfunction(function):

            @wraps(function)
            def generator(*args: Any, **kwargs: Any) -> Any:
                with scope(args, kwargs):
                    yield from function(*args, **kwargs)

            return generator

        @wraps(function)
        def synchronous(*args: Any, **kwargs: Any) -> Any:
            with scope(args, kwargs):
                return function(*args, **kwargs)

        return synchronous

    return decorate
