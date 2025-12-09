"""
Moduł: service_monitor - Monitor zdrowia usług zewnętrznych i wewnętrznych.

Odpowiada za:
- Rejestr usług (ServiceRegistry)
- Sprawdzanie dostępności usług (health checks)
- Zbieranie metryk: status, latency
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import aiohttp

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

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

    async def check_health(self, service_name: Optional[str] = None) -> List[ServiceInfo]:
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
            if token:
                headers["Authorization"] = f"Bearer {token}"

        if "openai" in service.name.lower():
            token = SETTINGS.OPENAI_API_KEY
            if token:
                headers["Authorization"] = f"Bearer {token}"

        if "local llm" in service.name.lower():
            # Ollama/vLLM nie wymagają autoryzacji domyślnie
            pass

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
        try:
            # Sprawdź czy ChromaDB jest dostępne poprzez import
            import chromadb

            # Spróbuj utworzyć klienta
            client = chromadb.Client()
            # Proste sprawdzenie - listuj kolekcje
            collections = client.list_collections()

            service.status = ServiceStatus.ONLINE
            service.error_message = None
        except ImportError:
            service.status = ServiceStatus.OFFLINE
            service.error_message = "ChromaDB nie zainstalowane"
        except Exception as e:
            service.status = ServiceStatus.OFFLINE
            service.error_message = str(e)[:100]

    def get_summary(self) -> Dict[str, any]:
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
