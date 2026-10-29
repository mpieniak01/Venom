"""API-owned, explicitly attached SSH connection to one managed Vast Ollama.

No host lifecycle or model installation happens here. Persisted intent contains
identity only; a restarted API always requires a fresh explicit attach.
"""

from __future__ import annotations

import atexit
import copy
import json
import re
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import httpx

from venom_core.infrastructure.providers.vast.client import VastClient, VastError
from venom_core.services.vast_environments.ssh import ssh_args
from venom_core.services.vast_environments.store import Journal

SERVER_NAME = "vast_ollama"
ROOT = Path(__file__).resolve().parents[2] / ".venom_runtime" / "vast"
_MAX_RESPONSE = 2_000_000
TUNNEL_FAILED = "vast.tunnel_failed"
CHAT_MODELS_INVALID = "vast.chat_models_invalid"
CHAT_UNAVAILABLE = "vast.chat_unavailable"
CHAT_INSTANCE_UNAVAILABLE = "vast.chat_instance_unavailable"
CHAT_PROBE_FAILED = "vast.chat_probe_failed"


class ManagedTunnel:
    """One SSH child, one loopback listener, never a public Ollama port."""

    def __init__(self, plan: Any, instance: dict[str, Any]):
        args = ssh_args(plan, instance)
        target = args.pop()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.endpoint = f"http://127.0.0.1:{port}"
        self.process = subprocess.Popen(
            args
            + [
                "-N",
                "-o",
                "ExitOnForwardFailure=yes",
                "-L",
                f"127.0.0.1:{port}:127.0.0.1:11434",
                target,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 20
            while self.alive():
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                        return
                except OSError:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.1)
            raise VastError(TUNNEL_FAILED)
        except BaseException:
            self.close()
            raise

    def alive(self) -> bool:
        return self.process.poll() is None

    def close(self) -> None:
        if not self.alive():
            self.process.wait()
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def _models(value: Any) -> list[dict[str, Any]]:
    rows = value.get("models") if isinstance(value, dict) else None
    if not isinstance(rows, list) or len(rows) > 256:
        raise VastError(CHAT_MODELS_INVALID)
    models: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise VastError(CHAT_MODELS_INVALID)
        name, digest = row.get("name"), row.get("digest")
        if (
            not isinstance(name, str)
            or not name
            or len(name) > 512
            or name != name.strip()
            or any(c.isspace() for c in name)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or type(row.get("size")) is not int
            or row["size"] < 0
        ):
            raise VastError(CHAT_MODELS_INVALID)
        item = {
            "name": name,
            "digest": digest,
            "size": row["size"],
            "details": row.get("details")
            if isinstance(row.get("details"), dict)
            else {},
        }
        current = models.get(digest)
        if current is None or (len(name), name) < (
            len(current["name"]),
            current["name"],
        ):
            models[digest] = item
    return sorted(models.values(), key=lambda row: row["name"])


class VastChatConnection:
    def __init__(
        self,
        settings: Any,
        *,
        journal: Journal | None = None,
        client_factory: Callable[..., Any] = VastClient,
        tunnel_factory: Callable[..., Any] = ManagedTunnel,
        http_factory: Callable[..., Any] = httpx.Client,
    ):
        self.settings = settings
        self.journal = journal or Journal(ROOT)
        self.client_factory = client_factory
        self.tunnel_factory = tunnel_factory
        self.http_factory = http_factory
        self._lock = threading.RLock()  # Serializes transport operations only.
        self._state_lock = threading.Lock()
        self._cached_status: dict[str, Any] = {}
        self._cached_tunnel: Any = None
        self._probe_failures = 0
        self._tunnel: Any = None
        self._client: Any = None
        self._plan: Any = None
        self._intent: dict[str, Any] | None = None
        self._generation = uuid4().hex
        self._error: str | None = None
        self._available = False
        self._catalog: list[dict[str, Any]] = []
        self._version: str | None = None
        path = self.journal.root / "chat-target.json"
        if path.is_file():
            try:
                value = json.loads(path.read_text()).get("target")
                if value is not None:
                    self.journal.path(value["plan_id"], ".plan.json")
                    if (
                        type(value["instance_id"]) is not int
                        or value["instance_id"] <= 0
                    ):
                        raise ValueError
                    self._intent = {
                        "plan_id": value["plan_id"],
                        "instance_id": value["instance_id"],
                    }
                    self._error = "vast.chat_attach_required"
            except (
                VastError,
                OSError,
                ValueError,
                KeyError,
                TypeError,
                AttributeError,
            ):
                self._error = "vast.chat_intent_invalid"
        self._publish_status()

    def _save_intent(self) -> None:
        self.journal.write(
            self.journal.root / "chat-target.json", {"target": self._intent}
        )

    def _close_transport(self) -> None:
        self._available = False
        self._catalog = []
        tunnel, client = self._tunnel, self._client
        self._tunnel = self._client = None
        self._publish_status()
        try:
            if tunnel is not None:
                tunnel.close()
        finally:
            if client is not None:
                client.close()

    def _invalidate(self, code: str) -> None:
        self._error = code
        self._version = None
        self._close_transport()

    def _json(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        if self._tunnel is None:
            raise VastError(CHAT_UNAVAILABLE)
        with self.http_factory(
            timeout=3.0,
            trust_env=False,
            follow_redirects=False,
            base_url=self._tunnel.endpoint,
        ) as client:
            method = "GET" if payload is None else "POST"
            with client.stream(
                method, path, **({"json": payload} if payload else {})
            ) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > _MAX_RESPONSE:
                        raise VastError("vast.chat_response_limit")
                return json.loads(content)

    def _probe(self) -> None:
        if (
            self._tunnel is None
            or not self._tunnel.alive()
            or self._client is None
            or self._intent is None
        ):
            raise VastError(CHAT_UNAVAILABLE)
        instance = self._client.instance(self._intent["instance_id"])
        if (
            instance.get("id") != self._intent["instance_id"]
            or instance.get("actual_status") != "running"
        ):
            raise VastError(CHAT_INSTANCE_UNAVAILABLE)
        for key in ("host_id", "machine_id"):
            if instance.get(key) != self._plan.assessment.offer.get(key):
                raise VastError("vast.chat_instance_mismatch")
        version = self._json("/api/version")
        if (
            not isinstance(version, dict)
            or not isinstance(version.get("version"), str)
            or not version["version"]
        ):
            raise VastError("vast.chat_version_invalid")
        self._catalog = _models(self._json("/api/tags"))
        self._version = version["version"][:100]
        self._available = True
        self._error = None
        self._probe_failures = 0
        self._publish_status()

    def attach(self, plan_id: str) -> dict[str, Any]:
        with self._lock:
            self.journal.path(plan_id, ".plan.json")
            plan = self.journal.plan(plan_id)
            record = self.journal.record(plan_id)
            if plan.profile.mode != "ollama" or record.instance_id is None:
                raise VastError("vast.chat_ollama_plan_required")
            if record.pending_action or record.state == "destroyed":
                raise VastError(CHAT_INSTANCE_UNAVAILABLE)
            self._close_transport()
            self._plan = plan
            self._intent = {"plan_id": plan_id, "instance_id": record.instance_id}
            self._generation = uuid4().hex
            self._save_intent()
            self._probe_failures = 0
            self._publish_status()
            try:
                self._client = self.client_factory(self.settings.VAST_API_KEY)
                instance = self._client.instance(record.instance_id)
                if (
                    instance.get("id") != record.instance_id
                    or instance.get("actual_status") != "running"
                ):
                    raise VastError(CHAT_INSTANCE_UNAVAILABLE)
                for key in ("host_id", "machine_id"):
                    if instance.get(key) != plan.assessment.offer.get(key):
                        raise VastError("vast.chat_instance_mismatch")
                self._tunnel = self.tunnel_factory(plan, instance)
                self._probe()
            except (VastError, OSError, ValueError, httpx.HTTPError) as exc:
                code = exc.code if isinstance(exc, VastError) else CHAT_PROBE_FAILED
                self._invalidate(code)
                raise VastError(code) from None
            return self.status(refresh=False)

    @staticmethod
    def _transient(error: Exception) -> bool:
        if isinstance(error, VastError):
            return error.code == "vast.transport_error" or (
                error.status is not None
                and (error.status == 429 or error.status >= 500)
            )
        if isinstance(error, httpx.HTTPStatusError):
            return (
                error.response.status_code == 429 or error.response.status_code >= 500
            )
        return isinstance(error, httpx.TransportError)

    def _probe_failed(self, error: Exception) -> None:
        code = error.code if isinstance(error, VastError) else CHAT_PROBE_FAILED
        self._probe_failures += 1
        if self._transient(error) and self._probe_failures < 3:
            self._available = False
            self._catalog = []
            self._error = code
            self._publish_status()
        else:
            self._invalidate(code)

    def _publish_status(self) -> None:
        # The operation lock owns mutable transport fields. Readers only see this
        # coherent snapshot; no network or process shutdown holds the state lock.
        intent = self._intent or {}
        target = (
            f"ollama@vast:{intent['plan_id']}:{intent['instance_id']}"
            if intent
            else None
        )
        value = {
            "server_name": SERVER_NAME,
            "label": "Ollama · Vast",
            "engine": "ollama",
            "placement": "remote",
            "owner": "vast",
            "target_id": target,
            "plan_id": intent.get("plan_id"),
            "instance_id": intent.get("instance_id"),
            "generation": self._generation,
            "available": self._available,
            "endpoint": self._tunnel.endpoint + "/v1" if self._available else None,
            "models": copy.deepcopy(self._catalog),
            "version": self._version,
            "error": self._error,
            "probe_failures": self._probe_failures,
        }
        with self._state_lock:
            self._cached_status = value
            self._cached_tunnel = self._tunnel

    def _read_status(self) -> dict[str, Any]:
        with self._state_lock:
            value = copy.deepcopy(self._cached_status)
            tunnel = self._cached_tunnel
        # Popen.poll is non-blocking. Revocation is immediate even before the
        # next refresh can serialize transport cleanup.
        if tunnel is not None and not tunnel.alive():
            value.update(available=False, endpoint=None, models=[], error=TUNNEL_FAILED)
        return value

    def status(self, refresh: bool = True) -> dict[str, Any]:
        if not refresh:
            return self._read_status()
        with self._lock:
            if self._tunnel is not None:
                try:
                    if not self._tunnel.alive():
                        raise VastError(TUNNEL_FAILED)
                    self._probe()
                except (VastError, OSError, ValueError, httpx.HTTPError) as error:
                    self._probe_failed(error)
            return self._read_status()

    def catalog(self) -> list[dict[str, Any]]:
        return self.status()["models"]

    def model_details(self, name: str) -> dict[str, Any]:
        with self._lock:
            state = self.require_available()
            if name not in {row["name"] for row in state["models"]}:
                raise VastError("vast.chat_model_missing")
            try:
                value = self._json("/api/show", {"model": name})
                if not isinstance(value, dict):
                    raise VastError("vast.chat_model_details_invalid")
                return {
                    key: value[key]
                    for key in ("capabilities", "parameters", "details", "model_info")
                    if key in value
                }
            except (VastError, OSError, ValueError, httpx.HTTPError) as exc:
                self._probe_failed(exc)
                raise VastError(CHAT_UNAVAILABLE) from None

    def require_available(self) -> dict[str, Any]:
        value = self.status(refresh=True)
        if not value["available"]:
            raise VastError(CHAT_UNAVAILABLE)
        return value

    def detach(self, expected_plan_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if (
                expected_plan_id is not None
                and self._intent is not None
                and self._intent.get("plan_id") != expected_plan_id
            ):
                raise VastError("vast.chat_detach_target_changed")
            self._close_transport()
            self._intent = self._plan = None
            self._error = None
            self._version = None
            self._generation = uuid4().hex
            self._save_intent()
            self._publish_status()
            return self.status(refresh=False)

    def close(self) -> None:
        with self._lock:
            self._close_transport()


_connection: VastChatConnection | None = None
_singleton_lock = threading.Lock()


def get_vast_chat_connection(settings: Any = None) -> VastChatConnection:
    global _connection
    with _singleton_lock:
        if _connection is None:
            if settings is None:
                from venom_core.config import SETTINGS

                settings = SETTINGS
            _connection = VastChatConnection(settings)
            atexit.register(_connection.close)
        return _connection
