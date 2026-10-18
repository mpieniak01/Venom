"""Prosty kontroler procesów LLM (start/stop/restart przez komendy powłoki)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from venom_core.config import Settings
from venom_core.utils.llm_runtime import (
    build_onnx_worker_health_url,
    resolve_local_worker_endpoint,
)
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)


@dataclass
class RuntimeCapabilities:
    """Formalny kontrakt lifecycle dla jednego runtime stack.

    Opisuje które operacje lifecycle są dostępne i jak runtime zachowuje się
    podczas switch flow: stop → release → flush_cache → start → await_ready.
    """

    supports_stop: bool
    supports_start: bool
    supports_restart: bool
    supports_health_wait: bool
    supports_cache_flush: bool
    supports_model_unload: bool
    is_in_process: bool
    release_wait_seconds: int = 0

    def as_dict(self) -> dict:
        return {
            "supports_stop": self.supports_stop,
            "supports_start": self.supports_start,
            "supports_restart": self.supports_restart,
            "supports_health_wait": self.supports_health_wait,
            "supports_cache_flush": self.supports_cache_flush,
            "supports_model_unload": self.supports_model_unload,
            "is_in_process": self.is_in_process,
            "release_wait_seconds": self.release_wait_seconds,
        }


@dataclass
class LlmServerConfig:
    """Konfiguracja pojedynczego serwera LLM."""

    name: str
    display_name: str
    description: str
    endpoint: Optional[str]
    provider: str
    commands: Dict[str, str]
    health_url: Optional[str] = None
    capabilities: RuntimeCapabilities = field(
        default_factory=lambda: RuntimeCapabilities(
            supports_stop=False,
            supports_start=False,
            supports_restart=False,
            supports_health_wait=False,
            supports_cache_flush=False,
            supports_model_unload=False,
            is_in_process=False,
        )
    )


@dataclass
class LlmCommandResult:
    """Wynik wykonania komendy."""

    ok: bool
    action: str
    stdout: str
    stderr: str
    exit_code: Optional[int]


class LlmServerController:
    """
    Umożliwia wykonywanie operacji start/stop/restart na lokalnych serwerach LLM
    za pomocą zdefiniowanych komend powłoki.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._servers: Dict[str, LlmServerConfig] = self._build_servers()

    def _build_servers(self) -> Dict[str, LlmServerConfig]:
        servers: Dict[str, LlmServerConfig] = {}

        cfg = self.settings

        repo_root = Path(__file__).resolve().parents[2]

        def _normalize(command: Optional[str], fallback: str) -> str:
            normalized = (command or "").strip()
            if normalized:
                return normalized
            return fallback

        def _normalize_multi_runtime_command(
            command: Optional[str], fallback: str
        ) -> str:
            normalized = _normalize(command, fallback)
            legacy = "gemma4_audio_service.sh"
            if legacy in normalized:
                migrated = normalized.replace(legacy, "multi_runtime_service.sh")
                logger.warning(
                    "Wykryto legacy komendę runtime '{}'; używam '{}'",
                    normalized,
                    migrated,
                )
                return migrated
            return normalized

        # Komendy dla vLLM (puste = akcja niedostępna)
        vllm_start_cmd = _normalize(
            cfg.VLLM_START_COMMAND,
            f"bash {repo_root / 'scripts/llm/vllm_service.sh'} start",
        )
        vllm_stop_cmd = _normalize(
            cfg.VLLM_STOP_COMMAND,
            f"bash {repo_root / 'scripts/llm/vllm_service.sh'} stop",
        )
        vllm_restart_cmd = _normalize(
            cfg.VLLM_RESTART_COMMAND,
            f"bash {repo_root / 'scripts/llm/vllm_service.sh'} restart",
        )

        vllm_endpoint = resolve_local_worker_endpoint(cfg.VLLM_ENDPOINT)
        servers["vllm"] = LlmServerConfig(
            name="vllm",
            display_name="vLLM",
            provider="vllm",
            description="Runtime OpenAI-compatible (port 8001).",
            endpoint=vllm_endpoint,
            health_url=f"{vllm_endpoint}/models" if vllm_endpoint else None,
            commands={
                "start": vllm_start_cmd,
                "stop": vllm_stop_cmd,
                "restart": vllm_restart_cmd,
            },
            capabilities=RuntimeCapabilities(
                supports_stop=True,
                supports_start=True,
                supports_restart=True,
                supports_health_wait=True,
                supports_cache_flush=False,
                supports_model_unload=False,
                is_in_process=False,
                release_wait_seconds=10,
            ),
        )

        # Komendy dla Ollama (puste = brak akcji)
        ollama_start_cmd = _normalize(
            cfg.OLLAMA_START_COMMAND,
            f"bash {repo_root / 'scripts/llm/ollama_service.sh'} start",
        )
        ollama_stop_cmd = _normalize(
            cfg.OLLAMA_STOP_COMMAND,
            f"bash {repo_root / 'scripts/llm/ollama_service.sh'} stop",
        )
        ollama_restart_cmd = _normalize(
            cfg.OLLAMA_RESTART_COMMAND,
            f"bash {repo_root / 'scripts/llm/ollama_service.sh'} restart",
        )

        servers["ollama"] = LlmServerConfig(
            name="ollama",
            display_name="Ollama",
            provider="ollama",
            description="Daemon Ollama (port 11434) dla modeli typu GGUF.",
            endpoint=build_http_url("localhost", 11434),
            health_url=build_http_url("localhost", 11434, "/api/tags"),
            commands={
                "start": ollama_start_cmd,
                "stop": ollama_stop_cmd,
                "restart": ollama_restart_cmd,
            },
            capabilities=RuntimeCapabilities(
                supports_stop=True,
                supports_start=True,
                supports_restart=True,
                supports_health_wait=True,
                supports_cache_flush=False,
                supports_model_unload=True,
                is_in_process=False,
                release_wait_seconds=5,
            ),
        )

        # Multi-runtime (Gemma 4 multimodal — audio, image, text)
        multi_runtime_start_cmd = _normalize_multi_runtime_command(
            cfg.GEMMA4_AUDIO_START_COMMAND,
            f"bash {repo_root / 'scripts/llm/multi_runtime_service.sh'} start",
        )
        multi_runtime_stop_cmd = _normalize_multi_runtime_command(
            cfg.GEMMA4_AUDIO_STOP_COMMAND,
            f"bash {repo_root / 'scripts/llm/multi_runtime_service.sh'} stop",
        )
        multi_runtime_restart_cmd = _normalize_multi_runtime_command(
            cfg.GEMMA4_AUDIO_RESTART_COMMAND,
            f"bash {repo_root / 'scripts/llm/multi_runtime_service.sh'} restart",
        )

        servers["multi_runtime"] = LlmServerConfig(
            name="multi_runtime",
            display_name="Multi-Runtime",
            provider="multi_runtime",
            description="Native multimodal inference daemon for Gemma 4 models (port 8014).",
            endpoint=cfg.GEMMA4_AUDIO_ENDPOINT,
            health_url=build_http_url(
                cfg.GEMMA4_AUDIO_HOST, cfg.GEMMA4_AUDIO_PORT, "/health"
            ),
            commands={
                "start": multi_runtime_start_cmd,
                "stop": multi_runtime_stop_cmd,
                "restart": multi_runtime_restart_cmd,
            },
            capabilities=RuntimeCapabilities(
                supports_stop=True,
                supports_start=True,
                supports_restart=True,
                supports_health_wait=True,
                supports_cache_flush=False,
                supports_model_unload=True,
                is_in_process=False,
                release_wait_seconds=10,
            ),
        )

        onnx_endpoint = resolve_local_worker_endpoint(
            getattr(cfg, "ONNX_LLM_ENDPOINT", None)
        )
        onnx_commands = {
            action: str(
                getattr(cfg, f"ONNX_{action.upper()}_COMMAND", "") or ""
            ).strip()
            for action in ("start", "stop", "restart")
        }
        servers["onnx"] = LlmServerConfig(
            name="onnx",
            display_name="ONNX Runtime",
            provider="onnx",
            description="Isolated ONNX GenAI CUDA worker over HTTP.",
            endpoint=onnx_endpoint,
            health_url=build_onnx_worker_health_url(onnx_endpoint),
            commands=onnx_commands,
            capabilities=RuntimeCapabilities(
                supports_stop=bool(onnx_commands["stop"]),
                supports_start=bool(onnx_commands["start"]),
                supports_restart=bool(onnx_commands["restart"]),
                supports_health_wait=True,
                supports_cache_flush=False,
                supports_model_unload=False,
                is_in_process=False,
                release_wait_seconds=0,
            ),
        )

        return servers

    def list_servers(self) -> List[dict]:
        """
        Zwraca listę serwerów z informacją o dostępnych akcjach.
        """
        servers: List[dict] = []
        for server in self._servers.values():
            servers.append(
                {
                    "name": server.name,
                    "display_name": server.display_name,
                    "description": server.description,
                    "endpoint": server.endpoint,
                    "provider": server.provider,
                    "health_url": server.health_url,
                    "supports": {
                        action: bool(command)
                        for action, command in server.commands.items()
                    },
                    "capabilities": server.capabilities.as_dict(),
                }
            )
        return servers

    def has_server(self, server_name: str) -> bool:
        """Sprawdza czy mamy konfigurację serwera."""
        return server_name in self._servers

    def get_capabilities(self, server_name: str) -> RuntimeCapabilities:
        """Zwraca kontrakt lifecycle dla danego runtime."""
        if server_name not in self._servers:
            raise ValueError(f"Nieznany serwer LLM: {server_name}")
        return self._servers[server_name].capabilities

    async def check_systemd_available(
        self, service_name: str = "ollama.service"
    ) -> bool:
        """
        Sprawdza czy systemd jest dostępny i czy dana usługa istnieje.

        Args:
            service_name: Nazwa usługi systemd

        Returns:
            True jeśli systemd jest dostępny i usługa istnieje
        """
        try:
            # Use list instead of shell=True for security
            process = await asyncio.create_subprocess_exec(
                "systemctl",
                "list-unit-files",
                service_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            return process.returncode == 0 and service_name in stdout.decode()
        except Exception as e:
            logger.debug(f"Systemd nie jest dostępny: {e}")
            return False

    async def run_action(self, server_name: str, action: str) -> LlmCommandResult:
        """
        Uruchamia zdefiniowaną komendę.

        Args:
            server_name: Identyfikator serwera (np. 'vllm')
            action: Nazwa akcji (start/stop/restart)
        """
        action = action.lower()
        if server_name not in self._servers:
            raise ValueError(f"Nieznany serwer LLM: {server_name}")

        server = self._servers[server_name]
        command = server.commands.get(action, "").strip()
        if not command:
            raise ValueError(
                f"Dla serwera {server.display_name} nie skonfigurowano akcji '{action}'."
            )

        logger.info("Uruchamiam komendę {} dla {}: {}", action, server.name, command)

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=300.0
            )
        except asyncio.TimeoutError:
            process.kill()
            logger.error(
                "Komenda {} dla {} przekroczyła timeout (300s). Zabijanie procesu.",
                action,
                server.name,
            )
            raise

        stdout = stdout_bytes.decode().strip()
        stderr = stderr_bytes.decode().strip()
        ok = process.returncode == 0

        if ok:
            logger.info(
                "Akcja {} dla {} zakończona sukcesem (exit={})",
                action,
                server.name,
                process.returncode,
            )
        else:
            logger.error(
                "Akcja {} dla {} zakończona błędem (exit={}): {}",
                action,
                server.name,
                process.returncode,
                stderr or stdout,
            )

        return LlmCommandResult(
            ok=ok,
            action=action,
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode,
        )
