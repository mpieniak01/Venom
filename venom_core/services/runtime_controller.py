"""
Moduł: runtime_controller - Sterowanie procesami Venom (backend, UI, LLM, Hive, Nexus).

Odpowiada za:
- Wykrywanie statusów usług (PID, port, CPU/RAM)
- Start/Stop/Restart procesów lokalnych
- Historia akcji
- Wsparcie dla profili (Full stack, Light, LLM OFF)
"""

import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from venom_core.config import SETTINGS
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

    def _get_process_info(self, pid: int) -> Optional[Dict]:
        """Pobiera informacje o procesie."""
        try:
            process = psutil.Process(pid)
            if not process.is_running():
                return None

            # Pobierz informacje o procesie
            cpu_percent = process.cpu_percent(interval=0.1)
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            create_time = process.create_time()
            uptime_seconds = int(time.time() - create_time)

            return {
                "cpu_percent": cpu_percent,
                "memory_mb": memory_mb,
                "uptime_seconds": uptime_seconds,
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def _read_last_log_line(self, log_file: Path, max_lines: int = 5) -> Optional[str]:
        """Czyta ostatnie linie z logu."""
        try:
            if not log_file.exists():
                return None

            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                if not lines:
                    return None

                # Zwróć ostatnie N niepustych linii
                non_empty = [line.strip() for line in lines if line.strip()]
                if not non_empty:
                    return None

                return " | ".join(non_empty[-max_lines:])
        except Exception as e:
            logger.warning(f"Nie udało się odczytać logu {log_file}: {e}")
            return None

    def _add_to_history(self, service: str, action: str, success: bool, message: str):
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

    def get_service_status(self, service_type: ServiceType) -> ServiceInfo:
        """Pobiera status usługi."""
        info = ServiceInfo(
            name=service_type.value,
            service_type=service_type,
            status=ServiceStatus.UNKNOWN,
        )

        # Backend i UI - sprawdź PID file
        if service_type in [ServiceType.BACKEND, ServiceType.UI]:
            pid_file = self.pid_files.get(service_type)
            log_file = self.log_files.get(service_type)

            if pid_file and pid_file.exists():
                try:
                    with open(pid_file, "r") as f:
                        pid = int(f.read().strip())
                        process_info = self._get_process_info(pid)

                        if process_info:
                            info.pid = pid
                            info.status = ServiceStatus.RUNNING
                            info.cpu_percent = process_info["cpu_percent"]
                            info.memory_mb = process_info["memory_mb"]
                            info.uptime_seconds = process_info["uptime_seconds"]

                            # Ustaw porty
                            if service_type == ServiceType.BACKEND:
                                info.port = 8000
                            elif service_type == ServiceType.UI:
                                info.port = 3000
                        else:
                            info.status = ServiceStatus.STOPPED
                except Exception as e:
                    info.status = ServiceStatus.ERROR
                    info.error_message = str(e)
            else:
                info.status = ServiceStatus.STOPPED

            # Pobierz ostatni log
            if log_file and log_file.exists():
                info.last_log = self._read_last_log_line(log_file)

        # LLM Ollama
        elif service_type == ServiceType.LLM_OLLAMA:
            info.port = 11434
            if self._check_port_listening(11434):
                info.status = ServiceStatus.RUNNING
                # Spróbuj znaleźć PID procesu ollama
                for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                    try:
                        if "ollama" in proc.info["name"].lower():
                            info.pid = proc.info["pid"]
                            process_info = self._get_process_info(proc.info["pid"])
                            if process_info:
                                info.cpu_percent = process_info["cpu_percent"]
                                info.memory_mb = process_info["memory_mb"]
                                info.uptime_seconds = process_info["uptime_seconds"]
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            else:
                info.status = ServiceStatus.STOPPED

        # LLM vLLM
        elif service_type == ServiceType.LLM_VLLM:
            info.port = 8001
            if self._check_port_listening(8001):
                info.status = ServiceStatus.RUNNING
                # Spróbuj znaleźć PID procesu vllm
                for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                    try:
                        cmdline = " ".join(proc.info["cmdline"] or [])
                        if "vllm" in cmdline.lower():
                            info.pid = proc.info["pid"]
                            process_info = self._get_process_info(proc.info["pid"])
                            if process_info:
                                info.cpu_percent = process_info["cpu_percent"]
                                info.memory_mb = process_info["memory_mb"]
                                info.uptime_seconds = process_info["uptime_seconds"]
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            else:
                info.status = ServiceStatus.STOPPED

        # Hive
        elif service_type == ServiceType.HIVE:
            info.status = (
                ServiceStatus.RUNNING if SETTINGS.ENABLE_HIVE else ServiceStatus.STOPPED
            )

        # Nexus
        elif service_type == ServiceType.NEXUS:
            info.status = (
                ServiceStatus.RUNNING
                if SETTINGS.ENABLE_NEXUS
                else ServiceStatus.STOPPED
            )
            if SETTINGS.ENABLE_NEXUS:
                info.port = SETTINGS.NEXUS_PORT

        # Background Tasks
        elif service_type == ServiceType.BACKGROUND_TASKS:
            info.status = (
                ServiceStatus.STOPPED
                if SETTINGS.VENOM_PAUSE_BACKGROUND_TASKS
                else ServiceStatus.RUNNING
            )

        return info

    def _check_port_listening(self, port: int) -> bool:
        """Sprawdza czy port jest nasłuchiwany."""
        try:
            # Optymalizacja: sprawdź tylko połączenia TCP nasłuchujące
            for conn in psutil.net_connections(kind='tcp'):
                if conn.status == "LISTEN" and conn.laddr.port == port:
                    return True
            return False
        except (psutil.AccessDenied, AttributeError):
            # Fallback: spróbuj otworzyć socket na porcie
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("localhost", port))
                    return False  # Port jest wolny
                except OSError:
                    return True  # Port jest zajęty

    def get_all_services_status(self) -> List[ServiceInfo]:
        """Pobiera status wszystkich usług."""
        return [
            self.get_service_status(service_type) for service_type in ServiceType
        ]

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

        try:
            if service_type == ServiceType.BACKEND:
                result = self._start_backend()
            elif service_type == ServiceType.UI:
                result = self._start_ui()
            elif service_type == ServiceType.LLM_OLLAMA:
                result = self._start_ollama()
            elif service_type == ServiceType.LLM_VLLM:
                result = self._start_vllm()
            elif service_type == ServiceType.HIVE:
                result = {"success": False, "message": "Hive kontrolowany przez konfigurację"}
            elif service_type == ServiceType.NEXUS:
                result = {"success": False, "message": "Nexus kontrolowany przez konfigurację"}
            elif service_type == ServiceType.BACKGROUND_TASKS:
                result = {
                    "success": False,
                    "message": "Background tasks kontrolowane przez konfigurację",
                }
            else:
                result = {"success": False, "message": "Nieznany typ usługi"}

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
            if service_type == ServiceType.BACKEND:
                result = self._stop_backend()
            elif service_type == ServiceType.UI:
                result = self._stop_ui()
            elif service_type == ServiceType.LLM_OLLAMA:
                result = self._stop_ollama()
            elif service_type == ServiceType.LLM_VLLM:
                result = self._stop_vllm()
            elif service_type == ServiceType.HIVE:
                result = {"success": False, "message": "Hive kontrolowany przez konfigurację"}
            elif service_type == ServiceType.NEXUS:
                result = {"success": False, "message": "Nexus kontrolowany przez konfigurację"}
            elif service_type == ServiceType.BACKGROUND_TASKS:
                result = {
                    "success": False,
                    "message": "Background tasks kontrolowane przez konfigurację",
                }
            else:
                result = {"success": False, "message": "Nieznany typ usługi"}

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
            return {"success": False, "message": f"Błąd zatrzymywania backend: {str(e)}"}

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
                    return {"success": True, "message": "Ollama uruchomiony"}
                else:
                    return {
                        "success": False,
                        "message": "Ollama nie uruchomił się w oczekiwanym czasie",
                    }
            except Exception as e:
                return {"success": False, "message": f"Błąd uruchamiania Ollama: {str(e)}"}
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
                return {"success": False, "message": f"Błąd zatrzymywania Ollama: {str(e)}"}
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
                return {"success": False, "message": f"Błąd uruchamiania vLLM: {str(e)}"}
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
                return {"success": False, "message": f"Błąd zatrzymywania vLLM: {str(e)}"}
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
        """Aplikuje profil konfiguracji."""
        logger.info(f"Aplikowanie profilu: {profile_name}")

        if profile_name == "full":
            # Uruchom wszystko
            services = [
                ServiceType.BACKEND,
                ServiceType.UI,
                ServiceType.LLM_OLLAMA,
            ]
            action = "start"
        elif profile_name == "light":
            # Tylko backend i UI
            services = [ServiceType.BACKEND, ServiceType.UI]
            action = "start"
            # Zatrzymaj LLM
            self.stop_service(ServiceType.LLM_OLLAMA)
            self.stop_service(ServiceType.LLM_VLLM)
        elif profile_name == "llm_off":
            # Wszystko oprócz LLM
            services = [ServiceType.BACKEND, ServiceType.UI]
            action = "start"
            self.stop_service(ServiceType.LLM_OLLAMA)
            self.stop_service(ServiceType.LLM_VLLM)
        else:
            return {"success": False, "message": f"Nieznany profil: {profile_name}"}

        results = []
        for service_type in services:
            if action == "start":
                result = self.start_service(service_type)
            else:
                result = self.stop_service(service_type)
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
        }


# Singleton
runtime_controller = RuntimeController()
