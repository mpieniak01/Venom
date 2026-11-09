"""Bounded local RPC transport using the same host lifecycle as SSH execution."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .paths import operator_path, python_path
from .transport import ACTIONS, MAX_RPC_BYTES, TransportError, execute_ssh

# The caller chooses locators, never an executable module or arbitrary command.
_BOOTSTRAP = (
    "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); "
    "runpy.run_module('venom_core.services.remote_training.remote',run_name='__main__')"
)


@dataclass(frozen=True)
class LocalConfig:
    """Operator-selected local host root and explicit control interpreter."""

    root: Path
    python: Path
    timeout: int = 60

    def validate(self) -> None:
        operator_path(self.root)
        interpreter = python_path(self.python)
        if not os.access(interpreter, os.X_OK):
            raise ValueError("local_training_interpreter_not_executable")
        if type(self.timeout) is not int or not 1 <= self.timeout <= 600:
            raise ValueError("local_training_timeout_invalid")


class LocalTransport:
    """Keep local and remote RPC semantics identical without invoking SSH."""

    def __init__(
        self,
        config: LocalConfig,
        *,
        executor: Callable[..., tuple[int, bytes]] = execute_ssh,
    ):
        config.validate()
        self.config = config
        self.executor = executor

    def request(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action not in ACTIONS or not isinstance(payload, dict):
            raise ValueError("remote_action_invalid")
        try:
            raw = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
        except (TypeError, ValueError):
            raise ValueError("remote_request_invalid") from None
        if len(raw) > MAX_RPC_BYTES:
            raise ValueError("remote_request_too_large")
        argv = [
            str(python_path(self.config.python)),
            "-c",
            _BOOTSTRAP,
            str(Path(__file__).resolve().parents[3]),
            "--root",
            str(operator_path(self.config.root)),
            action,
        ]
        try:
            code, reply = self.executor(argv, raw, self.config.timeout, MAX_RPC_BYTES)
        except TransportError as error:
            raise TransportError(
                "local_training_rpc_failed", retryable=error.retryable
            ) from None
        if code != 0:
            raise TransportError("local_training_rpc_failed", retryable=True)
        if len(reply) > MAX_RPC_BYTES:
            raise TransportError("local_training_reply_too_large")
        try:
            document = json.loads(reply)
        except ValueError:
            raise TransportError("local_training_reply_invalid") from None
        if not isinstance(document, dict) or type(document.get("ok")) is not bool:
            raise TransportError("local_training_reply_invalid")
        if not document["ok"]:
            remote_error = document.get("error", "")
            if not isinstance(remote_error, str) or not re.fullmatch(
                r"[a-z][a-z0-9_]{0,95}", remote_error
            ):
                remote_error = "local_training_operation_failed"
            raise TransportError(remote_error)
        if not isinstance(document.get("result"), dict):
            raise TransportError("local_training_reply_invalid")
        return document["result"]
