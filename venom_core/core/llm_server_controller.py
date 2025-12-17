"""Prosty kontroler procesów LLM (start/stop/restart przez komendy powłoki)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional

from venom_core.config import Settings
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


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

        # Wykryj czy używamy systemd dla vLLM
        vllm_start_cmd = cfg.VLLM_START_COMMAND.strip()
        if not vllm_start_cmd:
            # Fallback do skryptu
            vllm_start_cmd = "bash scripts/llm/vllm_service.sh start"

        servers["vllm"] = LlmServerConfig(
            name="vllm",
            display_name="vLLM",
            provider="vllm",
            description="Runtime OpenAI-compatible (port 8001).",
            endpoint=cfg.LLM_LOCAL_ENDPOINT,
            health_url=f"{cfg.LLM_LOCAL_ENDPOINT.rstrip('/')}/models",
            commands={
                "start": vllm_start_cmd,
                "stop": cfg.VLLM_STOP_COMMAND.strip() or "bash scripts/llm/vllm_service.sh stop",
                "restart": cfg.VLLM_RESTART_COMMAND.strip() or "bash scripts/llm/vllm_service.sh restart",
            },
        )

        # Wykryj czy używamy systemd dla Ollama
        ollama_start_cmd = cfg.OLLAMA_START_COMMAND.strip()
        if not ollama_start_cmd:
            # Fallback do skryptu
            ollama_start_cmd = "bash scripts/llm/ollama_service.sh start"

        servers["ollama"] = LlmServerConfig(
            name="ollama",
            display_name="Ollama",
            provider="ollama",
            description="Daemon Ollama (port 11434) dla modeli typu GGUF.",
            endpoint="http://localhost:11434",
            health_url="http://localhost:11434/api/tags",
            commands={
                "start": ollama_start_cmd,
                "stop": cfg.OLLAMA_STOP_COMMAND.strip() or "bash scripts/llm/ollama_service.sh stop",
                "restart": cfg.OLLAMA_RESTART_COMMAND.strip() or "bash scripts/llm/ollama_service.sh restart",
            },
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
                }
            )
        return servers

    def has_server(self, server_name: str) -> bool:
        """Sprawdza czy mamy konfigurację serwera."""
        return server_name in self._servers

    async def check_systemd_available(self, service_name: str = "ollama.service") -> bool:
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

        logger.info("Uruchamiam komendę %s dla %s: %s", action, server.name, command)

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await process.communicate()

        stdout = stdout_bytes.decode().strip()
        stderr = stderr_bytes.decode().strip()
        ok = process.returncode == 0

        if ok:
            logger.info(
                "Akcja %s dla %s zakończona sukcesem (exit=%s)",
                action,
                server.name,
                process.returncode,
            )
        else:
            logger.error(
                "Akcja %s dla %s zakończona błędem (exit=%s): %s",
                action,
                server.name,
                process.returncode,
                stderr,
            )

        return LlmCommandResult(
            ok=ok,
            action=action,
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode,
        )
