"""
Moduł: runtime_controller - Sterowanie procesami Venom (backend, UI, LLM, Hive, Nexus).

Odpowiada za:
- Wykrywanie statusów usług (PID, port, CPU/RAM)
- Start/Stop/Restart procesów lokalnych
- Historia akcji
- Wsparcie dla profili (Full stack, Light, LLM OFF)
"""

import json
import subprocess
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx
import psutil

from venom_core.config import SETTINGS
from venom_core.services.process_monitor import ProcessMonitor
from venom_core.services.profile_config import RuntimeProfile, get_profile_capabilities
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ServiceType(str, Enum):
    """Typy usług."""

    BACKEND = "backend"
    UI = "ui"
    LLM_OLLAMA = "llm_ollama"
    LLM_VLLM = "llm_vllm"
    HIVE = "hive"
    NEXUS = "nexus"
    BACKGROUND_TASKS = "background_tasks"
    ACADEMY = "academy"
    INTENT_EMBEDDING_ROUTER = "intent_embedding_router"


class ServiceStatus(str, Enum):
    """Status usługi."""

    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"
    ERROR = "error"


@dataclass
class ServiceInfo:
    """Informacje o usłudze."""

    name: str
    service_type: ServiceType
    status: ServiceStatus
    pid: Optional[int] = None
    port: Optional[int] = None
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    uptime_seconds: Optional[int] = None
    last_log: Optional[str] = None
    error_message: Optional[str] = None
    runtime_version: Optional[str] = None
    actionable: bool = True  # Czy usługa ma realne akcje start/stop/restart


@dataclass
class ActionHistory:
    """Historia akcji."""

    timestamp: str
    service: str
    action: str
    success: bool
    message: str


class RuntimeController:
    """Kontroler procesów Venom."""

    def __init__(self):
        """Inicjalizacja kontrolera."""
        self.project_root = Path(__file__).parent.parent.parent
        self.pid_files = {
            ServiceType.BACKEND: self.project_root / ".venom.pid",
            ServiceType.UI: self.project_root / ".web-next.pid",
        }
        self.log_files = {
            ServiceType.BACKEND: self.project_root / "logs" / "backend.log",
            ServiceType.UI: self.project_root / "logs" / "web-next.log",
        }
        self.history: List[ActionHistory] = []
        self.max_history = 100
        self._runtime_version_cache: Dict[str, str] = {}
        self._runtime_version_last_fetch: Dict[str, float] = {}
        self._runtime_version_ttl_seconds = 3600.0
        self._backend_version: Optional[str] = None
        self._ui_version: Optional[str] = None
        self._aux_runtime_version_resolvers: Dict[str, Callable[[], Optional[str]]] = (
            self._build_aux_runtime_version_resolvers()
        )

        # Inicjalizuj ProcessMonitor
        self.process_monitor = ProcessMonitor(self.project_root)

    @staticmethod
    def _is_actionable(service_type: ServiceType) -> bool:
        return service_type in {
            ServiceType.BACKEND,
            ServiceType.UI,
            ServiceType.LLM_OLLAMA,
            ServiceType.LLM_VLLM,
        }

    def _get_process_info(self, pid: int) -> Optional[Dict[str, float | int]]:
        """Pobiera informacje o procesie. Deleguje do ProcessMonitor."""
        return self.process_monitor.get_process_info(pid)

    def _read_last_log_line(self, log_file: Path, max_lines: int = 5) -> Optional[str]:
        """Czyta ostatnie linie z logu. Deleguje do ProcessMonitor."""
        return self.process_monitor.read_last_log_line(log_file, max_lines)

    def _add_to_history(
        self, service: str, action: str, success: bool, message: str
    ) -> None:
        """Dodaje wpis do historii."""
        entry = ActionHistory(
            timestamp=datetime.now().isoformat(),
            service=service,
            action=action,
            success=success,
            message=message,
        )
        self.history.append(entry)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]

    def _base_service_info(self, service_type: ServiceType) -> ServiceInfo:
        return ServiceInfo(
            name=service_type.value,
            service_type=service_type,
            status=ServiceStatus.UNKNOWN,
            actionable=self._is_actionable(service_type),
        )

    def _apply_process_metrics(self, info: ServiceInfo, pid: int) -> None:
        process_info = self._get_process_info(pid)
        if not process_info:
            return
        info.pid = pid
        info.cpu_percent = process_info["cpu_percent"]
        info.memory_mb = process_info["memory_mb"]
        uptime_seconds = process_info.get("uptime_seconds")
        if uptime_seconds is not None:
            info.uptime_seconds = int(uptime_seconds)

    def _read_pid_file(self, service_type: ServiceType) -> Optional[int]:
        pid_file = self.pid_files.get(service_type)
        if not pid_file or not pid_file.exists():
            return None
        with open(pid_file, "r") as pid_handle:
            return int(pid_handle.read().strip())

    def _update_pid_file_service_status(
        self, info: ServiceInfo, service_type: ServiceType
    ) -> None:
        try:
            pid = self._read_pid_file(service_type)
            if pid is None:
                info.status = ServiceStatus.STOPPED
                return

            process_info = self._get_process_info(pid)
            if not process_info:
                info.status = ServiceStatus.STOPPED
                return

            info.status = ServiceStatus.RUNNING
            self._apply_process_metrics(info, pid)
            if service_type == ServiceType.BACKEND:
                info.port = 8000
            elif service_type == ServiceType.UI:
                info.port = 3000
        except Exception as exc:
            info.status = ServiceStatus.ERROR
            info.error_message = str(exc)

    def _update_llm_status(
        self,
        info: ServiceInfo,
        *,
        port: int,
        process_match: str,
        service_type: ServiceType,
    ) -> None:
        info.port = port
        info.runtime_version = self._get_service_runtime_version(service_type)
        if not self._check_port_listening(port):
            info.status = ServiceStatus.STOPPED
            return

        info.status = ServiceStatus.RUNNING
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                proc_name = (proc.info.get("name") or "").lower()
                cmdline = " ".join(proc.info.get("cmdline") or []).lower()
                if process_match in proc_name or process_match in cmdline:
                    pid = proc.info["pid"]
                    self._apply_process_metrics(info, pid)
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if service_type == ServiceType.LLM_OLLAMA:
            info.runtime_version = self._refresh_ollama_runtime_version(force=False)

    def _cache_key_for_service(self, service_type: ServiceType) -> str:
        return f"service::{service_type.value}"

    def _cache_key_for_aux(self, service_name: str) -> str:
        return f"aux::{service_name.strip().lower()}"

    def _get_cached_runtime_version(self, cache_key: str) -> Optional[str]:
        last_fetch = self._runtime_version_last_fetch.get(cache_key)
        cached = self._runtime_version_cache.get(cache_key)
        if cached is None or last_fetch is None:
            return None
        if (time.time() - last_fetch) >= self._runtime_version_ttl_seconds:
            return None
        return cached

    def _set_cached_runtime_version(
        self, cache_key: str, value: Optional[str]
    ) -> Optional[str]:
        if not value:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        self._runtime_version_cache[cache_key] = normalized
        self._runtime_version_last_fetch[cache_key] = time.time()
        return normalized

    @staticmethod
    def _normalize_version(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        cleaned = raw.strip()
        if not cleaned:
            return None

        # Deterministic scan for semantic-like version fragments (x.y[.z[.w]])
        # without regex backtracking.
        token_chars: list[str] = []
        started = False
        for ch in cleaned:
            if ch.isdigit():
                token_chars.append(ch)
                started = True
                continue
            if ch == "." and started:
                token_chars.append(ch)
                continue
            if started:
                break

        token = "".join(token_chars).strip(".")
        if token:
            parts = [part for part in token.split(".") if part]
            if len(parts) >= 2 and all(part.isdigit() for part in parts):
                return ".".join(parts[:4])

        return cleaned or None

    def _run_version_command(self, cmd: List[str]) -> Optional[str]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None

        output = (result.stdout or result.stderr or "").strip()
        if result.returncode != 0 and not output:
            return None
        return self._normalize_version(output)

    def _read_backend_version(self) -> Optional[str]:
        if self._backend_version is not None:
            return self._backend_version
        pyproject_path = self.project_root / "pyproject.toml"
        try:
            with pyproject_path.open("rb") as handle:
                pyproject_data = tomllib.load(handle)
            self._backend_version = self._normalize_version(
                str(pyproject_data.get("project", {}).get("version", "")).strip()
            )
        except Exception:
            self._backend_version = None
        return self._backend_version

    def _read_ui_version(self) -> Optional[str]:
        if self._ui_version is not None:
            return self._ui_version

        meta_path = self.project_root / "web-next" / "public" / "meta.json"
        package_json_path = self.project_root / "web-next" / "package.json"
        try:
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                self._ui_version = self._normalize_version(str(meta.get("version", "")))
                if self._ui_version:
                    return self._ui_version
        except Exception:
            pass

        try:
            if package_json_path.exists():
                pkg = json.loads(package_json_path.read_text(encoding="utf-8"))
                self._ui_version = self._normalize_version(str(pkg.get("version", "")))
        except Exception:
            self._ui_version = None

        return self._ui_version

    def _read_lancedb_version(self) -> Optional[str]:
        try:
            return self._normalize_version(package_version("lancedb"))
        except PackageNotFoundError:
            return None

    def _build_aux_runtime_version_resolvers(
        self,
    ) -> Dict[str, Callable[[], Optional[str]]]:
        resolvers: Dict[str, Callable[[], Optional[str]]] = {}

        backend_resolver = self._read_backend_version
        for alias in {
            "backend",
            "backend api",
            "hive",
            "nexus",
            "zadania w tle",
            "academy",
            "router embeddingów intencji",
            "semantic kernel",
            "silnik mcp",
        }:
            resolvers[alias] = backend_resolver

        def _ui_resolver() -> Optional[str]:
            return self._read_ui_version() or self._read_backend_version()

        for alias in {"next.js ui", "frontend", "ui"}:
            resolvers[alias] = _ui_resolver

        def _docker_resolver() -> Optional[str]:
            return self._run_version_command(["docker", "--version"])

        for alias in {"docker daemon", "docker"}:
            resolvers[alias] = _docker_resolver

        resolvers["redis"] = lambda: self._run_version_command(
            ["redis-server", "--version"]
        )
        resolvers["lancedb"] = self._read_lancedb_version
        return resolvers

    def _resolve_aux_runtime_version(self, service_name: str) -> Optional[str]:
        normalized_name = service_name.strip().lower()
        resolver = self._aux_runtime_version_resolvers.get(normalized_name)
        if resolver is None:
            return None
        return resolver()

    def get_aux_runtime_version(
        self, service_name: str, *, force: bool = False
    ) -> Optional[str]:
        cache_key = self._cache_key_for_aux(service_name)
        if not force:
            cached = self._get_cached_runtime_version(cache_key)
            if cached is not None:
                return cached
        resolved = self._resolve_aux_runtime_version(service_name)
        return self._set_cached_runtime_version(cache_key, resolved)

    def _get_service_runtime_version(self, service_type: ServiceType) -> Optional[str]:
        cache_key = self._cache_key_for_service(service_type)
        cached = self._get_cached_runtime_version(cache_key)
        if cached is not None:
            return cached

        if service_type == ServiceType.LLM_OLLAMA:
            return self._refresh_ollama_runtime_version(force=False)
        if service_type == ServiceType.LLM_VLLM:
            return self._set_cached_runtime_version(
                cache_key, self._run_version_command(["vllm", "--version"])
            )
        if service_type == ServiceType.UI:
            return self._set_cached_runtime_version(cache_key, self._read_ui_version())

        # Pozostałe komponenty stacka to część backendu Venom (jedna wersja aplikacji)
        return self._set_cached_runtime_version(cache_key, self._read_backend_version())

    def _refresh_ollama_runtime_version(self, *, force: bool) -> Optional[str]:
        cache_key = self._cache_key_for_service(ServiceType.LLM_OLLAMA)
        if not force:
            cached = self._get_cached_runtime_version(cache_key)
            if cached is not None:
                return cached

        version_url = "http://127.0.0.1:11434/api/version"
        try:
            with httpx.Client(timeout=1.5) as client:
                response = client.get(version_url)
                if response.status_code != 200:
                    return self._runtime_version_cache.get(cache_key)
                payload = response.json()
                version = self._normalize_version(
                    payload.get("version") if isinstance(payload, dict) else None
                )
                if not version:
                    return self._runtime_version_cache.get(cache_key)
                return self._set_cached_runtime_version(cache_key, version)
        except (httpx.HTTPError, ValueError):
            return self._runtime_version_cache.get(cache_key)

    def _update_config_managed_status(
        self, info: ServiceInfo, service_type: ServiceType
    ) -> None:
        if service_type == ServiceType.HIVE:
            info.status = (
                ServiceStatus.RUNNING if SETTINGS.ENABLE_HIVE else ServiceStatus.STOPPED
            )
            return
        if service_type == ServiceType.NEXUS:
            info.status = (
                ServiceStatus.RUNNING
                if SETTINGS.ENABLE_NEXUS
                else ServiceStatus.STOPPED
            )
            if SETTINGS.ENABLE_NEXUS:
                info.port = getattr(SETTINGS, "NEXUS_PORT", None)
            return
        if service_type == ServiceType.BACKGROUND_TASKS:
            info.status = (
                ServiceStatus.STOPPED
                if SETTINGS.VENOM_PAUSE_BACKGROUND_TASKS
                else ServiceStatus.RUNNING
            )
            return
        if service_type in {
            ServiceType.ACADEMY,
            ServiceType.INTENT_EMBEDDING_ROUTER,
        }:
            setting_name = f"ENABLE_{service_type.name}"
            info.status = (
                ServiceStatus.RUNNING
                if getattr(SETTINGS, setting_name, False)
                else ServiceStatus.STOPPED
            )

    def _update_last_log(self, info: ServiceInfo, service_type: ServiceType) -> None:
        log_file = self.log_files.get(service_type)
        if log_file and log_file.exists():
            info.last_log = self._read_last_log_line(log_file)

    def get_service_status(self, service_type: ServiceType) -> ServiceInfo:
        """Pobiera status usługi."""
        info = self._base_service_info(service_type)
        info.runtime_version = self._get_service_runtime_version(service_type)
        if service_type in {ServiceType.BACKEND, ServiceType.UI}:
            self._update_pid_file_service_status(info, service_type)
            self._update_last_log(info, service_type)
            return info
        if service_type == ServiceType.LLM_OLLAMA:
            self._update_llm_status(
                info,
                port=11434,
                process_match="ollama",
                service_type=ServiceType.LLM_OLLAMA,
            )
            return info
        if service_type == ServiceType.LLM_VLLM:
            self._update_llm_status(
                info,
                port=8001,
                process_match="vllm",
                service_type=ServiceType.LLM_VLLM,
            )
            return info
        self._update_config_managed_status(info, service_type)
        return info

    def _config_controlled_result(self, service_type: ServiceType) -> Dict[str, Any]:
        messages = {
            ServiceType.HIVE: "Hive kontrolowany przez konfigurację",
            ServiceType.NEXUS: "Nexus kontrolowany przez konfigurację",
            ServiceType.BACKGROUND_TASKS: "Background tasks kontrolowane przez konfigurację",
            ServiceType.ACADEMY: "Academy kontrolowane przez konfigurację",
            ServiceType.INTENT_EMBEDDING_ROUTER: "Intent embedding router kontrolowany przez konfigurację",
        }
        message = messages.get(service_type, "Nieznany typ usługi")
        return {"success": False, "message": message}

    def _start_service_handler(self, service_type: ServiceType):
        handlers = {
            ServiceType.BACKEND: self._start_backend,
            ServiceType.UI: self._start_ui,
            ServiceType.LLM_OLLAMA: self._start_ollama,
            ServiceType.LLM_VLLM: self._start_vllm,
        }
        return handlers.get(service_type)

    def _stop_service_handler(self, service_type: ServiceType):
        handlers = {
            ServiceType.BACKEND: self._stop_backend,
            ServiceType.UI: self._stop_ui,
            ServiceType.LLM_OLLAMA: self._stop_ollama,
            ServiceType.LLM_VLLM: self._stop_vllm,
        }
        return handlers.get(service_type)

    def _perform_action(
        self, service_type: ServiceType, *, action: str
    ) -> Dict[str, Any]:
        handler = (
            self._start_service_handler(service_type)
            if action == "start"
            else self._stop_service_handler(service_type)
        )
        if handler is not None:
            return handler()
        return self._config_controlled_result(service_type)

    def _check_port_listening(self, port: int) -> bool:
        """Sprawdza czy port jest nasłuchiwany. Deleguje do ProcessMonitor."""
        return self.process_monitor.check_port_listening(port)

    def get_all_services_status(self) -> List[ServiceInfo]:
        """Pobiera status wszystkich usług."""
        return [self.get_service_status(service_type) for service_type in ServiceType]

    def _check_service_dependencies(self, service_type: ServiceType) -> Optional[str]:
        """
        Sprawdza czy zależności usługi są spełnione.

        Args:
            service_type: Typ usługi do sprawdzenia

        Returns:
            None jeśli wszystko OK, komunikat błędu jeśli brak zależności
        """
        # Hive wymaga Redis (sprawdzane przez konfigurację)
        if service_type == ServiceType.HIVE:
            if not SETTINGS.ENABLE_HIVE:
                return "Hive jest wyłączone w konfiguracji (ENABLE_HIVE=false)"

        # Nexus wymaga backendu
        if service_type == ServiceType.NEXUS:
            if not SETTINGS.ENABLE_NEXUS:
                return "Nexus jest wyłączone w konfiguracji (ENABLE_NEXUS=false)"
            backend_status = self.get_service_status(ServiceType.BACKEND)
            if backend_status.status != ServiceStatus.RUNNING:
                return "Nexus wymaga działającego backendu. Uruchom najpierw backend."

        # Background tasks wymagają backendu
        if service_type == ServiceType.BACKGROUND_TASKS:
            backend_status = self.get_service_status(ServiceType.BACKEND)
            if backend_status.status != ServiceStatus.RUNNING:
                return "Background tasks wymagają działającego backendu. Uruchom najpierw backend."

        # UI wymaga backendu w większości przypadków
        if service_type == ServiceType.UI:
            backend_status = self.get_service_status(ServiceType.BACKEND)
            if backend_status.status != ServiceStatus.RUNNING:
                logger.warning(
                    "UI uruchamiany bez backendu - ograniczona funkcjonalność"
                )

        return None

    def start_service(self, service_type: ServiceType) -> Dict[str, Any]:
        """Uruchamia usługę."""
        service_name = service_type.value
        logger.info(f"Próba uruchomienia usługi: {service_name}")

        # Sprawdź czy usługa już działa
        current_status = self.get_service_status(service_type)
        if current_status.status == ServiceStatus.RUNNING:
            message = f"Usługa {service_name} już działa (PID {current_status.pid})"
            self._add_to_history(service_name, "start", False, message)
            return {"success": False, "message": message}

        # Sprawdź zależności
        dependency_error = self._check_service_dependencies(service_type)
        if dependency_error:
            logger.warning(
                f"Zależności niespełnione dla {service_name}: {dependency_error}"
            )
            self._add_to_history(service_name, "start", False, dependency_error)
            return {"success": False, "message": dependency_error}

        try:
            result = self._perform_action(service_type, action="start")
            self._add_to_history(
                service_name, "start", result["success"], result["message"]
            )
            return result

        except Exception as e:
            message = f"Błąd podczas uruchamiania {service_name}: {str(e)}"
            logger.exception(message)
            self._add_to_history(service_name, "start", False, message)
            return {"success": False, "message": message}

    def stop_service(self, service_type: ServiceType) -> Dict[str, Any]:
        """Zatrzymuje usługę."""
        service_name = service_type.value
        logger.info(f"Próba zatrzymania usługi: {service_name}")

        # Sprawdź czy usługa działa
        current_status = self.get_service_status(service_type)
        if current_status.status == ServiceStatus.STOPPED:
            message = f"Usługa {service_name} już jest zatrzymana"
            self._add_to_history(service_name, "stop", True, message)
            return {"success": True, "message": message}

        try:
            result = self._perform_action(service_type, action="stop")
            self._add_to_history(
                service_name, "stop", result["success"], result["message"]
            )
            return result

        except Exception as e:
            message = f"Błąd podczas zatrzymywania {service_name}: {str(e)}"
            logger.exception(message)
            self._add_to_history(service_name, "stop", False, message)
            return {"success": False, "message": message}

    def restart_service(self, service_type: ServiceType) -> Dict[str, Any]:
        """Restartuje usługę."""
        service_name = service_type.value
        logger.info(f"Próba restartu usługi: {service_name}")

        # Zatrzymaj
        stop_result = self.stop_service(service_type)
        if not stop_result["success"]:
            # Jeśli stop nie powiódł się, ale usługa była już stopped, kontynuuj
            current_status = self.get_service_status(service_type)
            if current_status.status != ServiceStatus.STOPPED:
                return stop_result

        # Poczekaj chwilę
        time.sleep(2)

        # Uruchom
        start_result = self.start_service(service_type)

        message = f"Restart {service_name}: stop={stop_result['success']}, start={start_result['success']}"
        self._add_to_history(service_name, "restart", start_result["success"], message)

        return start_result

    def _start_backend(self) -> Dict[str, Any]:
        """Uruchamia backend (uvicorn)."""
        try:
            # Uruchom przez Makefile
            subprocess.Popen(
                ["make", "start-dev"],
                cwd=str(self.project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            # Poczekaj chwilę na start
            time.sleep(3)

            # Sprawdź czy się uruchomił
            status = self.get_service_status(ServiceType.BACKEND)
            if status.status == ServiceStatus.RUNNING:
                return {
                    "success": True,
                    "message": f"Backend uruchomiony (PID {status.pid})",
                }
            else:
                return {
                    "success": False,
                    "message": "Backend nie uruchomił się w oczekiwanym czasie",
                }

        except Exception as e:
            return {"success": False, "message": f"Błąd uruchamiania backend: {str(e)}"}

    def _stop_backend(self) -> Dict[str, Any]:
        """Zatrzymuje backend."""
        try:
            # Użyj make stop
            result = subprocess.run(
                ["make", "stop"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return {"success": True, "message": "Backend zatrzymany"}
            else:
                return {
                    "success": False,
                    "message": f"Błąd zatrzymywania backend: {result.stderr}",
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"Błąd zatrzymywania backend: {str(e)}",
            }

    def _start_ui(self) -> Dict[str, Any]:
        """Uruchamia UI (Next.js) - już uruchomiony przez make start-dev."""
        # UI jest uruchamiany razem z backendem przez make start-dev
        status = self.get_service_status(ServiceType.UI)
        if status.status == ServiceStatus.RUNNING:
            return {
                "success": True,
                "message": f"UI uruchomiony (PID {status.pid})",
            }
        else:
            return {
                "success": False,
                "message": "UI nie jest uruchomiony. Użyj 'make start-dev' aby uruchomić cały stos.",
            }

    def _stop_ui(self) -> Dict[str, Any]:
        """Zatrzymuje UI - zatrzymane przez make stop."""
        return {
            "success": True,
            "message": "UI zatrzymywany przez 'make stop'",
        }

    def _start_ollama(self) -> Dict[str, Any]:
        """Uruchamia Ollama."""
        if SETTINGS.OLLAMA_START_COMMAND:
            try:
                # SECURITY NOTE: shell=True używany z environment variables z .env
                # Tylko administrator może edytować .env bezpośrednio (nie przez UI)
                # UI używa whitelisty i nie pozwala edytować *_COMMAND parametrów
                subprocess.Popen(
                    SETTINGS.OLLAMA_START_COMMAND,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                time.sleep(3)
                status = self.get_service_status(ServiceType.LLM_OLLAMA)
                if status.status == ServiceStatus.RUNNING:
                    self._refresh_ollama_runtime_version(force=True)
                    return {"success": True, "message": "Ollama uruchomiony"}
                else:
                    return {
                        "success": False,
                        "message": "Ollama nie uruchomił się w oczekiwanym czasie",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Błąd uruchamiania Ollama: {str(e)}",
                }
        else:
            return {
                "success": False,
                "message": "Brak skonfigurowanego OLLAMA_START_COMMAND w .env",
            }

    def _stop_ollama(self) -> Dict[str, Any]:
        """Zatrzymuje Ollama."""
        if SETTINGS.OLLAMA_STOP_COMMAND:
            try:
                # SECURITY NOTE: shell=True używany z environment variables z .env
                # Tylko administrator może edytować .env bezpośrednio (nie przez UI)
                # UI używa whitelisty i nie pozwala edytować *_COMMAND parametrów
                result = subprocess.run(
                    SETTINGS.OLLAMA_STOP_COMMAND,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    return {"success": True, "message": "Ollama zatrzymany"}
                else:
                    return {
                        "success": False,
                        "message": f"Błąd zatrzymywania Ollama: {result.stderr}",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Błąd zatrzymywania Ollama: {str(e)}",
                }
        else:
            return {
                "success": False,
                "message": "Brak skonfigurowanego OLLAMA_STOP_COMMAND w .env",
            }

    def _start_vllm(self) -> Dict[str, Any]:
        """Uruchamia vLLM."""
        if SETTINGS.VLLM_START_COMMAND:
            try:
                # SECURITY NOTE: shell=True używany z environment variables z .env
                # Tylko administrator może edytować .env bezpośrednio (nie przez UI)
                # UI używa whitelisty i nie pozwala edytować *_COMMAND parametrów
                subprocess.Popen(
                    SETTINGS.VLLM_START_COMMAND,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                time.sleep(5)
                status = self.get_service_status(ServiceType.LLM_VLLM)
                if status.status == ServiceStatus.RUNNING:
                    return {"success": True, "message": "vLLM uruchomiony"}
                else:
                    return {
                        "success": False,
                        "message": "vLLM nie uruchomił się w oczekiwanym czasie",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Błąd uruchamiania vLLM: {str(e)}",
                }
        else:
            return {
                "success": False,
                "message": "Brak skonfigurowanego VLLM_START_COMMAND w .env",
            }

    def _stop_vllm(self) -> Dict[str, Any]:
        """Zatrzymuje vLLM."""
        if SETTINGS.VLLM_STOP_COMMAND:
            try:
                # SECURITY NOTE: shell=True używany z environment variables z .env
                # Tylko administrator może edytować .env bezpośrednio (nie przez UI)
                # UI używa whitelisty i nie pozwala edytować *_COMMAND parametrów
                result = subprocess.run(
                    SETTINGS.VLLM_STOP_COMMAND,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    return {"success": True, "message": "vLLM zatrzymany"}
                else:
                    return {
                        "success": False,
                        "message": f"Błąd zatrzymywania vLLM: {result.stderr}",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Błąd zatrzymywania vLLM: {str(e)}",
                }
        else:
            return {
                "success": False,
                "message": "Brak skonfigurowanego VLLM_STOP_COMMAND w .env",
            }

    def get_history(self, limit: int = 50) -> List[Dict]:
        """Pobiera historię akcji."""
        return [
            {
                "timestamp": h.timestamp,
                "service": h.service,
                "action": h.action,
                "success": h.success,
                "message": h.message,
            }
            for h in self.history[-limit:]
        ]

    def apply_profile(self, profile_name: str) -> Dict[str, Any]:
        """Aplikuje profil konfiguracji z wykorzystaniem kontraktu ProfileCapabilities."""
        logger.info(f"Aplikowanie profilu: {profile_name}")

        try:
            profile = RuntimeProfile.from_string(profile_name)
        except ValueError as e:
            return {"success": False, "message": str(e)}

        capabilities = get_profile_capabilities(profile)
        results = []

        def _stop_and_record(service_type: ServiceType) -> None:
            stop_result = self.stop_service(service_type)
            results.append(
                {
                    "service": service_type.value,
                    "success": stop_result["success"],
                    "message": stop_result["message"],
                }
            )

        # Stop disabled services based on profile
        service_map = {
            "ollama": ServiceType.LLM_OLLAMA,
            "vllm": ServiceType.LLM_VLLM,
        }

        for disabled_svc in capabilities.disabled_services:
            if disabled_svc in service_map:
                _stop_and_record(service_map[disabled_svc])

        # Determine which services to start
        services_to_start = []
        if "backend" in capabilities.required_services:
            services_to_start.append(ServiceType.BACKEND)
        if "frontend" in capabilities.required_services:
            services_to_start.append(ServiceType.UI)

        # Handle LLM services
        if capabilities.uses_local_llm:
            active_llm = str(getattr(SETTINGS, "ACTIVE_LLM_SERVER", "")).strip().lower()
            if profile == RuntimeProfile.FULL and active_llm in {"vllm", "llm_vllm"}:
                preferred_llm = ServiceType.LLM_VLLM
                opposite_llm = ServiceType.LLM_OLLAMA
            else:
                preferred_llm = ServiceType.LLM_OLLAMA
                opposite_llm = ServiceType.LLM_VLLM
            services_to_start.append(preferred_llm)
            _stop_and_record(opposite_llm)

        # Start required services
        for service_type in services_to_start:
            result = self.start_service(service_type)
            results.append(
                {
                    "service": service_type.value,
                    "success": result["success"],
                    "message": result["message"],
                }
            )

        all_success = all(r["success"] for r in results)
        message = f"Profil {profile_name} zastosowany: {len([r for r in results if r['success']])}/{len(results)} usług"

        self._add_to_history("profile", profile_name, all_success, message)

        return {
            "success": all_success,
            "message": message,
            "results": results,
            "profile_capabilities": {
                "uses_local_llm": capabilities.uses_local_llm,
                "gpu_support": capabilities.gpu_support,
                "requires_onnx": capabilities.requires_onnx,
            },
        }


# Singleton
runtime_controller = RuntimeController()
