"""
Moduł: service_monitor - Monitor zdrowia usług zewnętrznych i wewnętrznych.

Odpowiada za:
- Rejestr usług (ServiceRegistry)
- Sprawdzanie dostępności usług (health checks)
- Zbieranie metryk: status, latency
"""

import asyncio
import shutil
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp
import psutil

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

try:  # pragma: no cover - optional dependency
    import chromadb  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    chromadb = None

logger = get_logger(__name__)


class ServiceStatus(str, Enum):
    """Status usługi."""

    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class ServiceInfo:
    """Informacje o usłudze."""

    name: str
    service_type: str  # 'api', 'database', 'docker', 'local'
    endpoint: Optional[str] = None
    description: str = ""
    is_critical: bool = False  # Czy usługa jest krytyczna dla działania systemu
    status: ServiceStatus = ServiceStatus.UNKNOWN
    latency_ms: float = 0.0
    last_check: Optional[str] = None
    error_message: Optional[str] = None


class ServiceRegistry:
    """Rejestr usług do monitorowania."""

    def __init__(self):
        """Inicjalizacja rejestru usług."""
        self.services: Dict[str, ServiceInfo] = {}
        self._register_default_services()

    def _register_default_services(self):
        """Rejestruje domyślne usługi systemowe."""

        # OpenAI API (jeśli skonfigurowane)
        if SETTINGS.OPENAI_API_KEY and SETTINGS.LLM_SERVICE_TYPE == "openai":
            self.register_service(
                ServiceInfo(
                    name="OpenAI API",
                    service_type="api",
                    endpoint="https://api.openai.com/v1/models",
                    description="OpenAI GPT API dla LLM",
                    is_critical=True,
                )
            )

        # LLM health check przeniesiony do runtime status (dedykowane karty) – nie dodajemy tutaj.

        # Docker Daemon (jeśli sandbox włączony)
        if SETTINGS.ENABLE_SANDBOX:
            self.register_service(
                ServiceInfo(
                    name="Docker Daemon",
                    service_type="docker",
                    endpoint="unix:///var/run/docker.sock",
                    description="Docker do sandbox wykonawczego",
                    is_critical=False,
                )
            )

        # Local Memory (VectorDB)
        self.register_service(
            ServiceInfo(
                name="LanceDB",
                service_type="database",
                endpoint=None,  # Lokalne, brak endpointu HTTP
                description="LanceDB – lokalna pamięć wektorowa (embedded)",
                is_critical=False,
            )
        )

        # Redis (broker/locki)
        self.register_service(
            ServiceInfo(
                name="Redis",
                service_type="database",
                endpoint=f"redis://{SETTINGS.REDIS_HOST}:{SETTINGS.REDIS_PORT}/{SETTINGS.REDIS_DB}",
                description="Broker/locki Redis (jeśli skonfigurowany)",
                is_critical=False,
            )
        )

        # Semantic Kernel (Orchestrator)
        self.register_service(
            ServiceInfo(
                name="Semantic Kernel",
                service_type="orchestrator",
                endpoint=None,
                description="Jądro orkiestracji i zarządzania umiejętnościami",
                is_critical=True,
            )
        )

        # MCP Engine (Model Context Protocol)
        self.register_service(
            ServiceInfo(
                name="MCP Engine",
                service_type="mcp",
                endpoint=None,
                description="Obsługa narzędzi standardu Model Context Protocol",
                is_critical=False,
            )
        )

        logger.info(f"Zarejestrowano {len(self.services)} usług do monitorowania")

    def register_service(self, service: ServiceInfo):
        """
        Rejestruje nową usługę.

        Args:
            service: Informacje o usłudze
        """
        self.services[service.name] = service
        logger.debug(f"Zarejestrowano usługę: {service.name}")

    def get_service(self, name: str) -> Optional[ServiceInfo]:
        """
        Pobiera informacje o usłudze.

        Args:
            name: Nazwa usługi

        Returns:
            Informacje o usłudze lub None
        """
        return self.services.get(name)

    def get_all_services(self) -> List[ServiceInfo]:
        """
        Pobiera listę wszystkich usług.

        Returns:
            Lista usług
        """
        return list(self.services.values())

    def get_critical_services(self) -> List[ServiceInfo]:
        """
        Pobiera listę krytycznych usług.

        Returns:
            Lista krytycznych usług
        """
        return [s for s in self.services.values() if s.is_critical]


class ServiceHealthMonitor:
    """Monitor zdrowia usług."""

    def __init__(self, registry: ServiceRegistry, event_broadcaster=None):
        """
        Inicjalizacja monitora.

        Args:
            registry: Rejestr usług
            event_broadcaster: Transmiter zdarzeń WebSocket
        """
        self.registry = registry
        self.check_timeout = 5.0  # Timeout dla health checków (sekundy)
        self.orchestrator = None  # Referencja do Orchestrator (ustawiana przez main.py)
        self.event_broadcaster = event_broadcaster
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def _spawn_background_task(self, coro: Any) -> None:
        """Uruchamia fire-and-forget task i zachowuje referencję do zakończenia."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def set_orchestrator(self, orchestrator):
        """Ustawia referencję do orkiestratora."""
        self.orchestrator = orchestrator

    def get_all_services(self) -> List[ServiceInfo]:
        """
        Zwraca wszystkie zarejestrowane usługi wraz z ostatnim znanym statusem.

        Returns:
            Lista obiektów ServiceInfo
        """
        return self.registry.get_all_services()

    async def check_health(
        self, service_name: Optional[str] = None
    ) -> List[ServiceInfo]:
        """
        Sprawdza zdrowie usług.

        Args:
            service_name: Opcjonalnie nazwa konkretnej usługi (None = wszystkie)

        Returns:
            Lista usług z zaktualizowanym statusem
        """
        if service_name:
            service = self.registry.get_service(service_name)
            if not service:
                logger.warning(f"Usługa '{service_name}' nie znaleziona w rejestrze")
                return []
            services = [service]
        else:
            services = self.registry.get_all_services()

        # Sprawdź wszystkie usługi równolegle
        tasks = [self._check_service_health(service) for service in services]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Zaktualizuj statusy w rejestrze
        updated_services: List[ServiceInfo] = []
        for service, result in zip(services, results):
            if isinstance(result, Exception):
                logger.error(f"Błąd sprawdzania usługi {service.name}: {result}")
                service.status = ServiceStatus.OFFLINE
                service.error_message = str(result)
                updated_services.append(service)
            elif isinstance(result, ServiceInfo):
                updated_services.append(result)
            else:
                updated_services.append(service)
            self.registry.services[service.name] = service

        return updated_services

    async def _check_service_health(self, service: ServiceInfo) -> ServiceInfo:
        """
        Sprawdza zdrowie pojedynczej usługi.

        Args:
            service: Usługa do sprawdzenia

        Returns:
            Usługa z zaktualizowanym statusem
        """
        start_time = time.time()

        try:
            if service.service_type == "api":
                await self._check_http_service(service)
            elif service.service_type == "docker":
                await self._check_docker_service(service)
            elif service.service_type == "database":
                await self._check_local_database_service(service)
            elif service.service_type == "mcp":
                await self._check_mcp_service(service)
            elif service.service_type == "orchestrator":
                await self._check_semantic_kernel_service(service)
            else:
                logger.warning(f"Nieobsługiwany typ usługi: {service.service_type}")
                service.status = ServiceStatus.UNKNOWN

            latency = (time.time() - start_time) * 1000  # ms
            service.latency_ms = round(latency, 2)
            service.last_check = time.strftime("%Y-%m-%d %H:%M:%S")

        except Exception as e:
            logger.error(f"Błąd sprawdzania usługi {service.name}: {e}")
            service.status = ServiceStatus.OFFLINE
            service.error_message = str(e)
            service.latency_ms = 0.0
            service.last_check = time.strftime("%Y-%m-%d %H:%M:%S")
        finally:
            # Powiadomienie przez WebSocket o zmianie statusu (independently for each service)
            if self.event_broadcaster:
                try:
                    from venom_core.api.stream import EventType

                    self._spawn_background_task(
                        self.event_broadcaster.broadcast_event(
                            event_type=EventType.SERVICE_STATUS_UPDATE,
                            message=f"Status update for {service.name}: {service.status.value}",
                            data={
                                "name": service.name,
                                "type": service.service_type,
                                "service_type": service.service_type,  # Zachowujemy dla wstecznej kompatybilności
                                "status": service.status.value,
                                "error_message": service.error_message,
                                "latency_ms": service.latency_ms,
                            },
                        )
                    )
                except Exception as e:
                    logger.debug(
                        f"Nie udało się wysłać powiadomienia WS dla {service.name}: {e}"
                    )

        return service

    async def _check_http_service(self, service: ServiceInfo):
        """
        Sprawdza usługę HTTP/HTTPS.

        Args:
            service: Usługa do sprawdzenia
        """
        if not service.endpoint:
            service.status = ServiceStatus.UNKNOWN
            service.error_message = "Brak endpointu"
            return

        headers = {}

        # Dodaj autoryzację dla różnych API
        if "github" in service.name.lower():
            token = SETTINGS.GITHUB_TOKEN.get_secret_value()
            if token and token.strip():
                headers["Authorization"] = f"Bearer {token}"

        if "openai" in service.name.lower():
            token = SETTINGS.OPENAI_API_KEY
            if token and token.strip():
                headers["Authorization"] = f"Bearer {token}"

        # Ollama/vLLM nie wymagają autoryzacji domyślnie

        timeout = aiohttp.ClientTimeout(total=self.check_timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(service.endpoint, headers=headers) as response:
                if response.status < 400:
                    service.status = ServiceStatus.ONLINE
                    service.error_message = None
                elif response.status < 500:
                    service.status = ServiceStatus.DEGRADED
                    service.error_message = f"HTTP {response.status}"
                else:
                    service.status = ServiceStatus.OFFLINE
                    service.error_message = f"HTTP {response.status}"

    async def _check_docker_service(self, service: ServiceInfo):
        """
        Sprawdza Docker daemon.

        Args:
            service: Usługa do sprawdzenia
        """
        try:
            # Sprawdź czy Docker jest dostępny używając subprocess
            process = await asyncio.create_subprocess_exec(
                "docker",
                "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.check_timeout
            )

            if process.returncode == 0:
                service.status = ServiceStatus.ONLINE
                service.error_message = None
            else:
                service.status = ServiceStatus.OFFLINE
                service.error_message = stderr.decode().strip()[:100]

        except asyncio.TimeoutError:
            service.status = ServiceStatus.OFFLINE
            service.error_message = "Timeout"
        except FileNotFoundError:
            service.status = ServiceStatus.OFFLINE
            service.error_message = "Docker nie zainstalowany"
        except Exception as e:
            service.status = ServiceStatus.OFFLINE
            service.error_message = str(e)[:100]

    async def _check_local_database_service(self, service: ServiceInfo):
        """
        Sprawdza lokalną bazę danych (LanceDB/Redis).

        Args:
            service: Usługa do sprawdzenia
        """
        name = service.name.lower()
        description = service.description.lower()

        if "redis" in name:
            try:
                import redis.asyncio as redis

                client = redis.from_url(
                    service.endpoint or "", socket_connect_timeout=1
                )
                await asyncio.wait_for(client.ping(), timeout=self.check_timeout)
                service.status = ServiceStatus.ONLINE
                service.error_message = None
            except ModuleNotFoundError:
                service.status = ServiceStatus.OFFLINE
                service.error_message = "redis nie jest zainstalowany"
            except Exception as e:
                service.status = ServiceStatus.OFFLINE
                service.error_message = str(e)[:100]
            return

        if "chroma" in name or "chroma" in description:
            if chromadb is None:
                service.status = ServiceStatus.OFFLINE
                service.error_message = "chromadb nie jest zainstalowane"
                return
            try:
                client = chromadb.Client()
                _ = client.list_collections()
                service.status = ServiceStatus.ONLINE
                service.error_message = None
            except Exception as e:
                service.status = ServiceStatus.OFFLINE
                service.error_message = str(e)[:100]
            return

        # LanceDB (lokalna pamięć embed)
        try:
            import lancedb  # type: ignore[import-untyped]

            db_path = getattr(SETTINGS, "VECTOR_DB_PATH", "data/vector_store")
            conn = lancedb.connect(db_path)
            # Prosty check: pobierz listę tabel (nie przechowujemy wyniku)
            _ = conn.table_names()
            service.status = ServiceStatus.ONLINE
            service.error_message = None
        except ModuleNotFoundError:
            service.status = ServiceStatus.OFFLINE
            service.error_message = "lancedb nie jest zainstalowane"
        except Exception as e:
            service.status = ServiceStatus.OFFLINE
            service.error_message = str(e)[:100]

    async def _check_mcp_service(self, service: ServiceInfo):
        """
        Sprawdza dostępność silnika MCP i liczy zaimportowane narzędzia.

        Args:
            service: Usługa do sprawdzenia
        """
        await asyncio.sleep(0)
        try:
            from pathlib import Path

            from venom_core.skills.mcp_manager_skill import McpManagerSkill

            # Manager tworzy katalogi przy inicjalizacji
            manager = McpManagerSkill()

            # Policz zaimportowane narzędzia w katalogu _repos
            repos_path = Path(manager.repos_root)
            tool_count = 0
            if repos_path.exists():
                tool_count = len([d for d in repos_path.iterdir() if d.is_dir()])

            service.status = ServiceStatus.ONLINE
            service.error_message = f"Zaimportowano {tool_count} narzędzi"
            service.latency_ms = 0.0  # Błyskawiczne sprawdzanie lokalne

        except ImportError:
            service.status = ServiceStatus.OFFLINE
            service.error_message = "Brak biblioteki 'mcp' (SDK)"
        except Exception as e:
            service.status = ServiceStatus.OFFLINE
            service.error_message = f"Błąd MCP: {str(e)[:50]}"

    async def _check_semantic_kernel_service(self, service: ServiceInfo):
        """
        Sprawdza stan Semantic Kernel.
        """
        await asyncio.sleep(0)
        try:
            orchestrator = self.orchestrator

            if not orchestrator:
                service.status = ServiceStatus.UNKNOWN
                service.error_message = "Orchestrator nie zainicjalizowany"
                return

            # Zliczanie pluginów i funkcji
            kernel = orchestrator.task_dispatcher.kernel

            # Pobierz pluginy (W SK v1.0+ to słownik)
            plugins = getattr(kernel, "plugins", {})
            plugin_count = len(plugins)

            # Zlicz funkcje we wszystkich pluginach
            function_count = 0
            for plugin in plugins.values():
                function_count += len(plugin.functions)

            service.status = ServiceStatus.ONLINE
            service.error_message = f"{plugin_count} skille, {function_count} funkcji"
            service.latency_ms = 0.0

        except Exception as e:
            service.status = ServiceStatus.OFFLINE
            service.error_message = f"Błąd SK: {str(e)[:50]}"

    def get_summary(self) -> Dict[str, Any]:
        """
        Zwraca podsumowanie zdrowia systemu.

        Returns:
            Słownik z podsumowaniem
        """
        services = self.registry.get_all_services()
        critical_services = self.registry.get_critical_services()

        online_count = sum(1 for s in services if s.status == ServiceStatus.ONLINE)
        offline_count = sum(1 for s in services if s.status == ServiceStatus.OFFLINE)
        degraded_count = sum(1 for s in services if s.status == ServiceStatus.DEGRADED)

        critical_offline = [
            s.name for s in critical_services if s.status == ServiceStatus.OFFLINE
        ]

        return {
            "total_services": len(services),
            "online": online_count,
            "offline": offline_count,
            "degraded": degraded_count,
            "critical_offline": critical_offline,
            "system_healthy": len(critical_offline) == 0,
        }

    def get_memory_metrics(self) -> Dict[str, Any]:
        """
        Zwraca metryki użycia pamięci RAM i VRAM.

        Returns:
            Słownik z metrykami pamięci:
            - memory_usage_mb: Użycie pamięci RAM w MB
            - memory_total_mb: Całkowita pamięć RAM w MB
            - memory_usage_percent: Procent użycia RAM
            - vram_usage_mb: Użycie pamięci VRAM w MB (jeśli dostępne GPU)
            - vram_total_mb: Całkowita pamięć VRAM w MB (jeśli dostępne)
            - vram_usage_percent: Procent użycia VRAM (jeśli dostępne)
        """
        memory = psutil.virtual_memory()

        metrics = {
            "memory_usage_mb": round(memory.used / (1024**2), 2),
            "memory_total_mb": round(memory.total / (1024**2), 2),
            "memory_usage_percent": round(memory.percent, 2),
            "vram_usage_mb": None,
            "vram_total_mb": None,
            "vram_usage_percent": None,
        }

        # Próba pobrania informacji o GPU/VRAM z nvidia-smi (jeśli dostępne)
        try:
            # Sprawdź czy nvidia-smi jest dostępne
            nvidia_smi_path = shutil.which("nvidia-smi")
            if not nvidia_smi_path:
                return metrics

            result = subprocess.run(
                [
                    nvidia_smi_path,
                    "--query-gpu=memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                gpu_data = self._parse_nvidia_smi_output(result.stdout)
                if gpu_data:
                    # Znajdź GPU z największym użyciem pamięci
                    vram_used_mb, vram_total_mb = max(gpu_data, key=lambda x: x[0])
                    metrics["vram_usage_mb"] = round(vram_used_mb, 2)
                    metrics["vram_total_mb"] = round(vram_total_mb, 2)
                    if vram_total_mb > 0:
                        metrics["vram_usage_percent"] = round(
                            (vram_used_mb / vram_total_mb) * 100, 2
                        )
        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
        ):
            # nvidia-smi nie jest dostępne lub wystąpił błąd - ignorujemy
            pass

        return metrics

    @staticmethod
    def _parse_nvidia_smi_output(stdout: str) -> List[tuple[float, float]]:
        """Parsuje wyjście nvidia-smi do listy (used_mb, total_mb)."""
        parsed: List[tuple[float, float]] = []
        lines = [line.strip() for line in stdout.strip().split("\n") if line.strip()]
        for line in lines:
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 2:
                continue
            try:
                parsed.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
        return parsed

    def get_gpu_memory_usage(self) -> Optional[float]:
        """
        Zwraca bieżące zużycie pamięci GPU (VRAM) w MB.

        Używa nvidia-smi do pobrania informacji o zużyciu VRAM.
        Jeśli dostępnych jest wiele GPU, zwraca wartość dla GPU z największym użyciem.

        Returns:
            Zużycie VRAM w MB lub None jeśli GPU nie jest dostępne
        """
        try:
            # Sprawdź czy nvidia-smi jest dostępne
            nvidia_smi_path = shutil.which("nvidia-smi")
            if not nvidia_smi_path:
                return None

            result = subprocess.run(
                [
                    nvidia_smi_path,
                    "--query-gpu=memory.used",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                lines = [
                    line.strip()
                    for line in result.stdout.strip().split("\n")
                    if line.strip()
                ]

                # Znajdź GPU z największym użyciem pamięci
                max_usage = 0.0
                for line in lines:
                    try:
                        usage = float(line)
                        if usage > max_usage:
                            max_usage = usage
                    except ValueError:
                        continue

                return round(max_usage, 2) if max_usage > 0 else None

        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
        ):
            # nvidia-smi nie jest dostępne lub wystąpił błąd
            pass
        except Exception as exc:  # pragma: no cover - defensywne logowanie
            logger.warning(f"Błąd get_gpu_memory_usage: {exc}")

        return None
