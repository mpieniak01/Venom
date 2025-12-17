"""
Moduł: service_monitor - Monitor zdrowia usług zewnętrznych i wewnętrznych.

Odpowiada za:
- Rejestr usług (ServiceRegistry)
- Sprawdzanie dostępności usług (health checks)
- Zbieranie metryk: status, latency
"""

import asyncio
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp
import psutil

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

try:  # pragma: no cover - zależne od środowiska testowego
    import chromadb  # type: ignore
except ImportError:  # pragma: no cover
    chromadb = None  # type: ignore

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

        # Local LLM (Ollama/vLLM)
        if SETTINGS.LLM_SERVICE_TYPE == "local":
            self.register_service(
                ServiceInfo(
                    name="Local LLM",
                    service_type="api",
                    endpoint=f"{SETTINGS.LLM_LOCAL_ENDPOINT}/models",
                    description=f"Lokalny serwer LLM ({SETTINGS.LLM_MODEL_NAME})",
                    is_critical=True,
                )
            )
            self.register_service(
                ServiceInfo(
                    name="vLLM",
                    service_type="api",
                    endpoint=SETTINGS.LLM_LOCAL_ENDPOINT,
                    description="Serwer vLLM (OpenAI-compatible)",
                    is_critical=True,
                )
            )
            self.register_service(
                ServiceInfo(
                    name="Ollama",
                    service_type="api",
                    endpoint="http://localhost:11434/api/tags",
                    description="Daemon Ollama dla modeli GGUF",
                    is_critical=False,
                )
            )

        # GitHub API (jeśli skonfigurowane)
        github_token = SETTINGS.GITHUB_TOKEN.get_secret_value()
        if github_token and github_token.strip():
            self.register_service(
                ServiceInfo(
                    name="GitHub API",
                    service_type="api",
                    endpoint="https://api.github.com/rate_limit",
                    description="GitHub API do integracji z repozytorium",
                    is_critical=False,
                )
            )

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
                name="Local Memory",
                service_type="database",
                endpoint=None,  # Lokalne, brak endpointu HTTP
                description="Pamięć wektorowa (ChromaDB)",
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

    def __init__(self, registry: ServiceRegistry):
        """
        Inicjalizacja monitora.

        Args:
            registry: Rejestr usług
        """
        self.registry = registry
        self.check_timeout = 5.0  # Timeout dla health checków (sekundy)

        # Cache ChromaDB availability
        self._chromadb_available = None
        self._chromadb_module = None
        self._chromadb_client = None

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
        updated_services = []
        for service, result in zip(services, results):
            if isinstance(result, Exception):
                logger.error(f"Błąd sprawdzania usługi {service.name}: {result}")
                service.status = ServiceStatus.OFFLINE
                service.error_message = str(result)
            else:
                updated_services.append(result)
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
            stdout, stderr = await asyncio.wait_for(
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
        Sprawdza lokalną bazę danych (VectorDB).

        Args:
            service: Usługa do sprawdzenia
        """
        # Check cache for ChromaDB availability (initialize once)
        if self._chromadb_available is None:
            if chromadb is None:
                self._chromadb_available = False
                self._chromadb_module = None
                self._chromadb_client = None
            else:
                self._chromadb_available = True
                self._chromadb_module = chromadb
                # Initialize client once and reuse
                try:
                    self._chromadb_client = chromadb.Client()
                except Exception:
                    # Jeśli inicjalizacja klienta się nie uda, oznacz jako niedostępne
                    self._chromadb_available = False
                    self._chromadb_module = None
                    self._chromadb_client = None

        if not self._chromadb_available:
            service.status = ServiceStatus.OFFLINE
            service.error_message = "ChromaDB nie zainstalowane"
            return

        try:
            # Reuse the cached client
            if self._chromadb_client is None:
                self._chromadb_client = self._chromadb_module.Client()

            # Simple check - list collections (don't store unused result)
            self._chromadb_client.list_collections()

            service.status = ServiceStatus.ONLINE
            service.error_message = None
        except Exception as e:
            service.status = ServiceStatus.OFFLINE
            service.error_message = str(e)[:100]

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
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,memory.total",
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

                vram_used_values = []
                vram_total_values = []

                for line in lines:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) < 2:
                        continue
                    try:
                        vram_used_values.append(float(parts[0]))
                        vram_total_values.append(float(parts[1]))
                    except ValueError:
                        continue

                if vram_used_values:
                    max_index = vram_used_values.index(max(vram_used_values))
                    metrics["vram_usage_mb"] = round(vram_used_values[max_index], 2)
                    if max_index < len(vram_total_values):
                        total_mb = vram_total_values[max_index]
                        metrics["vram_total_mb"] = round(total_mb, 2)
                        if total_mb > 0:
                            metrics["vram_usage_percent"] = round(
                                (metrics["vram_usage_mb"] / total_mb) * 100, 2
                            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # nvidia-smi nie jest dostępne lub wystąpił błąd - ignorujemy
            pass

        return metrics
