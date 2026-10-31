"""Trial-scoped DockerHabitat adapter for the shared SkillManager tool path."""

import asyncio
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from venom_core.infrastructure.docker_habitat import DockerHabitat

CONTAINER_WORKSPACE = "/workspace"

PYTEST_PROFILE = "-o addopts= -o filterwarnings= --noconftest"


class TrialHabitat(DockerHabitat):
    """No network, host socket, GPU, privileged mode or writable container root."""

    def __init__(
        self, workspace: Path, image: str, *, read_only_workspace: bool = False
    ):
        self.trial_readonly_workspace = read_only_workspace
        self.trial_workspace = workspace.resolve(strict=True)
        self.trial_image = image
        if not image.startswith("sha256:") or len(image) != 71:
            raise ValueError("immutable_sandbox_image_required")
        super().__init__()

    def _resolve_workspace_path(self) -> Path:
        return self.trial_workspace

    def _ensure_image_present(self, image_name: str) -> None:
        self.client.images.get(self.trial_image)

    def _run_container(self, image_name: str, workspace_path: Path):
        return self.client.containers.run(
            image=self.trial_image,
            name=self._active_container_name(),
            command=["sleep", "infinity"],
            volumes={
                str(workspace_path): {
                    "bind": CONTAINER_WORKSPACE,
                    "mode": "ro" if self.trial_readonly_workspace else "rw",
                }
            },
            working_dir=CONTAINER_WORKSPACE,
            environment={"PYTEST_ADDOPTS": PYTEST_PROFILE},
            detach=True,
            remove=False,
            network_disabled=True,
            network_mode="none",
            read_only=True,
            user="1000:1000",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            pids_limit=64,
            mem_limit="1g",
            nano_cpus=2_000_000_000,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=128m,uid=0,gid=1000,mode=1770"},
            labels={
                "venom.experiment": "maintenance-comparison",
                "venom.run_id": os.environ.get(
                    "VENOM_MAINTENANCE_RUN_ID", "manual-probe"
                ),
            },
        )

    @staticmethod
    def _close_exec_stream(stream) -> None:
        close = getattr(stream, "close", None)
        if close is not None:
            close()

    def _stopped_after_output_cap(self, truncated: bool) -> bool:
        if not truncated:
            return False
        self.container.reload()
        return self.container.status in {"paused", "exited", "dead"}

    def structured(self, command: str, timeout: int) -> dict[str, Any]:
        started = time.monotonic()
        execution = self.client.api.exec_create(
            self.container.id,
            ["timeout", "-k", "1", str(timeout), "bash", "-lc", command],
            user="1000:1000",
            workdir=CONTAINER_WORKSPACE,
        )
        chunks: list[list[bytes]] = [[], []]
        total, truncated = 0, False
        deadline_hit = threading.Event()
        watchdog = threading.Timer(
            timeout + 2, self._stop_overdue, args=(deadline_hit,)
        )
        watchdog.daemon = True
        watchdog.start()
        transport_error = None
        try:
            stream = self.client.api.exec_start(
                execution["Id"], stream=True, demux=True
            )
            try:
                for pair in stream:
                    for index, chunk in enumerate(pair):
                        if chunk:
                            remaining = max(0, 1_048_576 - total)
                            chunks[index].append(chunk[:remaining])
                            total += len(chunk)
                    if total > 1_048_576:
                        truncated = True
                        # Release the hijacked output socket before asking Docker to kill.
                        self._close_exec_stream(stream)
                        stream = None
                        self.container.kill()
                        break
            finally:
                self._close_exec_stream(stream)
            exit_code = self.client.api.exec_inspect(execution["Id"])["ExitCode"]
        except Exception as exc:
            if not self._stopped_after_output_cap(truncated):
                raise
            # A known output violation is still a failure; an unavailable exit is never invented.
            exit_code = None
            transport_error = type(exc).__name__
        finally:
            watchdog.cancel()
        result = {
            "stdout": b"".join(chunks[0]).decode("utf-8", errors="replace"),
            "stderr": b"".join(chunks[1]).decode("utf-8", errors="replace"),
            "exit_code": exit_code,
            "output_truncated": truncated,
            "execution_timed_out": deadline_hit.is_set() or exit_code == 124,
            "seconds": time.monotonic() - started,
        }
        if transport_error is not None:
            result["transport_error"] = transport_error
        return result

    def _stop_overdue(self, deadline_hit: threading.Event) -> None:
        deadline_hit.set()
        try:
            self.container.kill()
        except Exception:
            pass  # Cleanup still requires confirmed process/container termination.

    def freeze(self) -> None:
        self.container.reload()
        quiescent = {"paused", "exited", "dead"}
        if self.container.status == "running":
            try:
                self.container.pause()
            except Exception:
                # A watchdog may stop the container between reload and pause.
                self.container.reload()
                if self.container.status not in quiescent:
                    raise
        elif self.container.status not in quiescent:
            raise RuntimeError("sandbox_state_not_quiescent")

    def close(self) -> None:
        try:
            self.container.remove(force=True)
        finally:
            self.client.close()


class TrialTools:
    """The model supplies arguments; only SkillManager invokes this adapter."""

    def __init__(self, habitat: TrialHabitat, role: str):
        self.habitat, self.role = habitat, role
        self.finished: dict | None = None
        self.calls: list[dict] = []
        self.command_seconds = 15
        self.no_progress_limit = 3
        self.available_tools: set[str] | None = None
        self.protocol: str | None = None

    def list_tools(self) -> list[str]:
        tools = [
            "Terminal",
            "LocalizationFinish" if self.role == "localization" else "Finish",
        ]
        if self.protocol == "localization":
            tools = ["terminal", "localization_finish"]
        return [
            tool
            for tool in tools
            if self.available_tools is None or tool in self.available_tools
        ]

    async def invoke_tool(self, name: str, arguments: dict) -> dict:
        if name not in self.list_tools():
            raise ValueError("tool_not_available")
        if name in {"Terminal", "terminal"}:
            if set(arguments) != {"command"} or not isinstance(
                arguments["command"], str
            ):
                raise ValueError("terminal_command_required")
            if (
                not arguments["command"]
                or len(arguments["command"]) > 16000
                or chr(0) in arguments["command"]
            ):
                raise ValueError("terminal_command_invalid")
            before = self.fingerprint()
            result = await asyncio.to_thread(
                self.habitat.structured, arguments["command"], self.command_seconds
            )
            self.calls.append(
                {
                    "name": "Terminal",
                    "wire_name": name,
                    "arguments": arguments,
                    "before": before,
                    "after": self.fingerprint(),
                    "result": result,
                }
            )
            return result
        if self.protocol == "localization":
            from .codescout import validate_submission

            validate_submission(arguments)
            self.finished = {
                "kind": "codescout_native",
                "locations": arguments["locations"],
            }
        else:
            self.validate_completion(arguments)
            self.finished = arguments
        self.calls.append(
            {"name": name, "arguments": arguments, "result": {"accepted": True}}
        )
        return {"accepted": True}

    def validate_completion(self, arguments: dict) -> None:
        allowed = (
            {"status", "summary", "locations"}
            if self.role == "localization"
            else {"status", "summary"}
        )
        if set(arguments) - allowed:
            raise ValueError("unknown_finish_argument")
        if arguments.get("status") not in {
            "success",
            "tool_error",
            "needs_input",
            "unsupported",
            "escalated",
            "not_found",
        }:
            raise ValueError("finish_status_required")
        if not isinstance(arguments.get("summary"), str) or not arguments["summary"]:
            raise ValueError("finish_summary_required")
        if self.role == "localization" and not isinstance(
            arguments.get("locations"), list
        ):
            raise ValueError("localization_evidence_required")
        if self.role == "localization":
            self._validate_locations(arguments["locations"])

    @staticmethod
    def _validate_locations(locations: list) -> None:
        for location in locations:
            if not isinstance(location, dict) or set(location) != {
                "path",
                "symbol",
                "evidence",
            }:
                raise ValueError("localization_location_invalid")
            if not all(isinstance(value, str) and value for value in location.values()):
                raise ValueError("localization_location_invalid")

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self.habitat.workspace_path.rglob("*")):
            relative = path.relative_to(self.habitat.workspace_path)
            if any(part in {"__pycache__", ".pytest_cache"} for part in relative.parts):
                continue
            if path.is_symlink():
                digest.update(str(relative).encode())
                digest.update(str(path.readlink()).encode())
            elif path.is_file():
                digest.update(str(relative).encode())
                with path.open("rb") as source:
                    while chunk := source.read(65536):
                        digest.update(chunk)
        return digest.hexdigest()

    def repeated_without_progress(self) -> bool:
        if not self.no_progress_limit or len(self.calls) < self.no_progress_limit:
            return False
        signatures = [
            action_signature(c) for c in self.calls[-self.no_progress_limit :]
        ]
        return len(set(signatures)) == 1


def action_signature(call: dict) -> str:
    data = {key: call.get(key) for key in ("name", "arguments", "before", "after")}
    result = call.get("result", {})
    data["observation"] = {
        key: result.get(key) for key in ("stdout", "stderr", "exit_code")
    }
    return json.dumps(data, sort_keys=True)


def cleanup_run_containers(run_id: str) -> bool:
    """Delete only trial containers carrying this host-issued run identifier."""
    from venom_core.infrastructure.docker_habitat import docker

    if docker is None:
        return False
    try:
        client = docker.from_env()
        for container in client.containers.list(
            all=True,
            filters={
                "label": [
                    "venom.experiment=maintenance-comparison",
                    "venom.run_id=" + run_id,
                ]
            },
        ):
            labels = container.attrs.get("Config", {}).get("Labels", {})
            if (
                labels.get("venom.experiment") != "maintenance-comparison"
                or labels.get("venom.run_id") != run_id
            ):
                return False
            container.remove(force=True)
        return True
    except Exception:
        return False
