"""Studio-owned local embedding worker. The API owns all persistent memory."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from threading import Lock
from time import monotonic
from typing import Any, BinaryIO

from venom_core.memory.embedding_service import EmbeddingService
from venom_core.services.model_resources import model_operation, register_model_resource
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
_REQUEST_TIMEOUT_SECONDS = 120
_STOP_TIMEOUT_SECONDS = 2
_WORKER_MODULE = "venom_core.memory.embedding_process"


def _send(channel: socket.socket, message: Any) -> None:
    channel.sendall(json.dumps(message).encode("utf-8") + b"\n")


def _serve_embeddings(fd: int) -> None:
    service = EmbeddingService(service_type="local")
    with socket.socket(fileno=fd) as channel, channel.makefile("rb") as incoming:
        for line in incoming:
            operation, payload = json.loads(line)
            try:
                if operation == "single":
                    value = service.get_embedding(payload)
                elif operation == "batch":
                    value = service.get_embeddings_batch(payload)
                elif operation == "dimension":
                    value = service.embedding_dimension
                else:
                    raise ValueError("Unknown embedding operation")
            except Exception:
                logger.exception("Studio embedding request failed in worker")
                _send(channel, (False, None))
            else:
                _send(channel, (True, value))


class ProcessEmbeddingService:
    """Launch one local model on demand and serialize requests and retirement."""

    def __init__(self, idle_seconds: int) -> None:
        self._idle_seconds = idle_seconds
        self._lock = Lock()
        self._worker: tuple[subprocess.Popen[bytes], socket.socket, BinaryIO] | None = (
            None
        )
        self._last_use = 0.0
        self._dimension: int | None = None
        register_model_resource(self, "embeddings", "release_model_resource")

    @model_operation
    def get_embedding(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("Tekst nie może być pusty")
        with self._lock:
            result = self._request("single", text)
            self._dimension = len(result)
            return result

    @model_operation
    def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            raise ValueError("Lista tekstów nie może być pusta")
        with self._lock:
            result = self._request("batch", texts)
            self._dimension = len(result[0])
            return result

    @property
    @model_operation
    def embedding_dimension(self) -> int:
        with self._lock:
            if self._dimension is None:
                self._dimension = self._request("dimension", None)
            return self._dimension

    @staticmethod
    def _start() -> tuple[subprocess.Popen[bytes], socket.socket, BinaryIO]:
        # A fresh interpreter owns CUDA and the model. Only the private socket is inherited.
        channel, child = socket.socketpair()
        with child:
            fd = child.fileno()
            try:
                process = subprocess.Popen(
                    [sys.executable, "-m", _WORKER_MODULE, str(fd)],
                    stdin=subprocess.DEVNULL,
                    pass_fds=(fd,),
                )
            except OSError:
                channel.close()
                raise
        channel.settimeout(_REQUEST_TIMEOUT_SECONDS)
        logger.info("Studio embedding worker started pid={}", process.pid)
        return process, channel, channel.makefile("rb")

    def _request(self, operation: str, payload: str | list[str] | None) -> Any:
        if self._worker is not None and self._worker[0].poll() is not None:
            self._stop()
        if self._worker is None:
            self._worker = self._start()
        _, channel, incoming = self._worker
        try:
            _send(channel, (operation, payload))
            line = incoming.readline()
            if not line:
                raise EOFError("Studio embedding worker disconnected")
            ok, value = json.loads(line)
        except (EOFError, OSError, ValueError) as exc:
            self._stop()
            raise RuntimeError("Studio embedding worker unavailable") from exc
        self._last_use = monotonic()
        if not ok:
            raise RuntimeError("Studio embedding request failed")
        return value

    def _stop(self) -> bool:
        if self._worker is None:
            return True
        process, channel, incoming = self._worker
        incoming.close()
        channel.close()
        try:
            try:
                process.wait(_STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(_STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                logger.error(
                    "Studio embedding worker could not be stopped pid={}", process.pid
                )
                return False
        logger.info("Studio embedding worker stopped pid={}", process.pid)
        self._worker = None
        return True

    def release_if_idle(self) -> bool:
        if not self._lock.acquire(blocking=False):
            return False
        try:
            return (
                self._worker is not None
                and monotonic() - self._last_use >= self._idle_seconds
                and self._stop()
            )
        finally:
            self._lock.release()

    def release_model_resource(self) -> bool:
        with self._lock:
            return self._stop()


if __name__ == "__main__":
    _serve_embeddings(int(sys.argv[1]))
