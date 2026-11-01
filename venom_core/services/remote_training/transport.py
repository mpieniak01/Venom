"""Bounded JSON RPC over a strictly verified, operator-configured SSH host."""

from __future__ import annotations

import json
import os
import re
import selectors
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Protocol

ACTIONS = frozenset(
    {
        "prepare",
        "upload",
        "start",
        "status",
        "logs",
        "stop",
        "resume",
        "retry",
        "collect",
    }
)
MAX_RPC_BYTES = 2 * 1024 * 1024


class TransportError(RuntimeError):
    """Stable error code which never includes SSH stderr, credentials or payloads."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class Transport(Protocol):
    """An injectable RPC boundary, also implemented by offline test transports."""

    def request(self, action: str, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class SSHConfig:
    """Locators only; keys and credentials remain in the existing SSH configuration."""

    config_file: Path = field(repr=False)
    alias: str
    remote_root: str
    python: str = "python3"
    timeout: int = 60

    def validate(self) -> None:
        """Reject option injection, implicit host trust and unbounded timeouts."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", self.alias):
            raise ValueError("remote_ssh_alias_invalid")
        path = self.config_file.expanduser()
        if not path.is_file():
            raise ValueError("remote_ssh_config_missing")
        root = PurePosixPath(self.remote_root)
        if not root.is_absolute() or len(root.parts) < 3 or ".." in root.parts:
            raise ValueError("remote_root_invalid")
        if any(char in self.remote_root for char in ("\x00", "\n", "\r")):
            raise ValueError("remote_root_invalid")
        if not re.fullmatch(r"(?:/[A-Za-z0-9_.-]+)+|python3(?:\.[0-9]+)?", self.python):
            raise ValueError("remote_python_invalid")
        if type(self.timeout) is not int or not 1 <= self.timeout <= 600:
            raise ValueError("remote_timeout_invalid")


def _kill_owned(process: subprocess.Popen[bytes]) -> None:
    """Reap our session, including pipe-holding children after its leader exits."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


def execute_ssh(
    argv: list[str], payload: bytes, timeout: int, limit: int
) -> tuple[int, bytes]:
    """Bound all pipe I/O and cleanup without blocking buffered-reader threads."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if name
        in {
            "HOME",
            "PATH",
            "USER",
            "LOGNAME",
            "LANG",
            "LC_ALL",
            "SSH_AUTH_SOCK",
            "XDG_RUNTIME_DIR",
            "TERM",
        }
    }
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=environment,
            bufsize=0,
        )
    except OSError:
        raise TransportError("remote_ssh_unavailable") from None
    output = bytearray()
    deadline = time.monotonic() + timeout
    sent = 0
    assert process.stdin is not None and process.stdout is not None
    try:
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            if payload:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE)
            else:
                process.stdin.close()
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TransportError("remote_ssh_timeout", retryable=True)
                for key, _events in selector.select(remaining):
                    if key.events == selectors.EVENT_READ:
                        try:
                            data = os.read(key.fd, 65536)
                        except BlockingIOError:
                            continue
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        if len(output) + len(data) > limit:
                            raise TransportError("remote_reply_too_large")
                        output.extend(data)
                    else:
                        try:
                            sent += os.write(key.fd, payload[sent : sent + 65536])
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            sent = len(payload)
                        if sent == len(payload):
                            selector.unregister(key.fileobj)
                            process.stdin.close()
            # Do not reap the session leader before group cleanup: its reserved
            # PID prevents signalling a different session after PID reuse.
            while (
                os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                is None
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TransportError("remote_ssh_timeout", retryable=True)
                time.sleep(min(0.01, remaining))
    except OSError:
        raise TransportError("remote_ssh_failed", retryable=True) from None
    finally:
        _kill_owned(process)
        process.stdout.close()
        process.stdin.close()
    if process.returncode is None:
        raise TransportError("remote_ssh_cleanup_failed")
    return process.returncode, bytes(output)


class SSHTransport:
    """Execute only the fixed remote training RPC module, never manifest commands."""

    def __init__(
        self,
        config: SSHConfig,
        *,
        executor: Callable[..., tuple[int, bytes]] = execute_ssh,
    ):
        config.validate()
        self.config = config
        self.executor = executor

    def request(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Encode one request; semantic errors are not retried as transport failures."""
        if action not in ACTIONS or not isinstance(payload, dict):
            raise ValueError("remote_action_invalid")
        try:
            raw = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
        except (TypeError, ValueError):
            raise ValueError("remote_request_invalid") from None
        if len(raw) > MAX_RPC_BYTES:
            raise ValueError("remote_request_too_large")
        remote = [
            self.config.python,
            "-m",
            "venom_core.services.remote_training.remote",
            "--root",
            self.config.remote_root,
            action,
        ]
        argv = [
            "ssh",
            "-F",
            str(self.config.config_file.expanduser().resolve()),
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=2",
            "--",
            self.config.alias,
            shlex.join(remote),
        ]
        code, reply = self.executor(argv, raw, self.config.timeout, MAX_RPC_BYTES)
        if code != 0:
            raise TransportError("remote_ssh_failed", retryable=True)
        if len(reply) > MAX_RPC_BYTES:
            raise TransportError("remote_reply_too_large")
        try:
            document = json.loads(reply)
        except (ValueError, UnicodeError):
            raise TransportError("remote_reply_invalid") from None
        if not isinstance(document, dict) or type(document.get("ok")) is not bool:
            raise TransportError("remote_reply_invalid")
        if not document["ok"]:
            error = document.get("error", "")
            if not isinstance(error, str) or not re.fullmatch(
                r"[a-z][a-z0-9_]{0,95}", error
            ):
                error = "remote_operation_failed"
            raise TransportError(error)
        if not isinstance(document.get("result"), dict):
            raise TransportError("remote_reply_invalid")
        return document["result"]
