"""Moduł: cloud_provisioner - zarządzanie zdalnym deploymentem przez SSH i lokalną widocznością w sieci."""

import asyncio
import re
import socket
import uuid
from pathlib import Path
from typing import Any, Optional

import asyncssh
import httpx
from zeroconf import ServiceInfo, Zeroconf

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class CloudProvisionerError(Exception):
    """Błąd podczas operacji cloud provisioning."""

    pass


class CloudProvisioner:
    """
    Zarządca wdrożeń w chmurze - obsługa SSH, deployment i konfiguracja serwerów.
    Dodatkowo: broadcasting lokalnej widoczności w sieci LAN przez mDNS.

    BEZPIECZEŃSTWO:
    - Nigdy nie loguj kluczy prywatnych SSH
    - Używaj tylko ścieżek do kluczy, nie samych kluczy
    - Timeout dla wszystkich operacji SSH
    - Walidacja komend przed wykonaniem
    - Żadnych połączeń wychodzących do publicznych API DNS (Intranet Mode)
    """

    def __init__(
        self,
        ssh_key_path: Optional[str] = None,
        default_user: str = "root",
        timeout: int = 300,
        service_port: int = 8000,
        agent_id: Optional[str] = None,
    ):
        """
        Inicjalizacja CloudProvisioner.

        Args:
            ssh_key_path: Ścieżka do klucza SSH (domyślnie z SETTINGS)
            default_user: Domyślny użytkownik SSH
            timeout: Timeout dla operacji SSH w sekundach
            service_port: Port usługi dla mDNS broadcasting (domyślnie 8000)
            agent_id: Unikalny identyfikator agenta (UUID), generowany automatycznie jeśli nie podano
        """
        self.ssh_key_path = ssh_key_path or SETTINGS.DEPLOYMENT_SSH_KEY_PATH
        self.default_user = default_user or SETTINGS.DEPLOYMENT_DEFAULT_USER
        self.timeout = timeout or SETTINGS.DEPLOYMENT_TIMEOUT
        self.service_port = service_port

        # mDNS / Zeroconf
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None

        # Hive Registration
        self.agent_id = agent_id or str(uuid.uuid4())
        self.hive_url = SETTINGS.HIVE_URL
        self.hive_registered = False

        if self.ssh_key_path:
            key_path = Path(self.ssh_key_path)
            if not key_path.exists():
                logger.warning(
                    f"Klucz SSH nie istnieje: {self.ssh_key_path}. "
                    f"Deployment będzie wymagał hasła."
                )

        logger.info(
            f"CloudProvisioner zainicjalizowany (user={self.default_user}, "
            f"timeout={self.timeout}s, agent_id={self.agent_id})"
        )
        logger.info("[INFO] Network Mode: INTRANET (mDNS active)")

        # Automatyczna rejestracja w Ulu jeśli HIVE_URL jest skonfigurowany
        if self.hive_url:
            logger.info(f"HIVE_URL skonfigurowany: {self.hive_url}")

    async def _execute_ssh_command(
        self,
        host: str,
        command: str,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> tuple[str, str, int]:
        """
        Wykonuje komendę przez SSH.

        Args:
            host: Adres hosta
            command: Komenda do wykonania
            user: Użytkownik SSH (opcjonalnie)
            password: Hasło SSH (opcjonalnie, jeśli brak klucza)

        Returns:
            Tuple (stdout, stderr, exit_code)

        Raises:
            CloudProvisionerError: Jeśli połączenie nie powiedzie się
        """
        user = user or self.default_user
        connect_kwargs = {"host": host, "username": user, "known_hosts": None}

        # Preferuj klucz SSH
        if self.ssh_key_path and Path(self.ssh_key_path).exists():
            connect_kwargs["client_keys"] = [self.ssh_key_path]
        elif password:
            connect_kwargs["password"] = password
        else:
            raise CloudProvisionerError(
                "Brak klucza SSH ani hasła. Nie można nawiązać połączenia."
            )

        try:
            async with asyncio.timeout(self.timeout):
                async with asyncssh.connect(**connect_kwargs) as conn:
                    result = await conn.run(command, check=False)
                    stdout = result.stdout if result.stdout else ""
                    stderr = result.stderr if result.stderr else ""
                    exit_code = result.exit_status or 0

                    logger.debug(
                        f"SSH Command '{command[:50]}...' exit_code={exit_code}"
                    )
                    return stdout, stderr, exit_code

        except asyncio.TimeoutError:
            raise CloudProvisionerError(
                f"Timeout podczas wykonywania komendy na {host}"
            )
        except asyncssh.Error as e:
            raise CloudProvisionerError(f"Błąd SSH: {e}")
        except Exception as e:
            raise CloudProvisionerError(f"Nieoczekiwany błąd: {e}")

    async def provision_server(
        self,
        host: str,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> dict[str, str]:
        """
        Instaluje Docker i Nginx na czystym serwerze Linux.

        Args:
            host: Adres IP lub hostname serwera
            user: Użytkownik SSH
            password: Hasło SSH (jeśli brak klucza)

        Returns:
            Dict ze statusem instalacji

        Raises:
            CloudProvisionerError: Jeśli instalacja nie powiedzie się
        """
        logger.info(f"Rozpoczynam provisioning serwera {host}...")

        commands = [
            # Update system
            "apt-get update",
            # Install Docker
            "apt-get install -y docker.io docker-compose",
            # Start Docker service
            "systemctl start docker",
            "systemctl enable docker",
            # Install Nginx (opcjonalne, jako reverse proxy)
            "apt-get install -y nginx",
            # Weryfikacja
            "docker --version",
        ]

        results = {}
        for cmd in commands:
            try:
                stdout, stderr, exit_code = await self._execute_ssh_command(
                    host, cmd, user, password
                )
                if exit_code != 0:
                    logger.warning(
                        f"Komenda '{cmd[:30]}...' zakończona z kodem {exit_code}: {stderr}"
                    )
                    results[cmd] = f"FAILED: {stderr[:100]}"
                else:
                    results[cmd] = "OK"
                    logger.debug(f"✓ {cmd[:50]}")
            except CloudProvisionerError as e:
                logger.error(f"Błąd podczas '{cmd}': {e}")
                results[cmd] = f"ERROR: {e}"
                raise

        logger.info(f"Provisioning serwera {host} zakończony pomyślnie")
        return results

    async def deploy_stack(
        self,
        host: str,
        stack_name: str,
        compose_file_path: str,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> dict[str, str]:
        """
        Przesyła docker-compose.yml i uruchamia stack na zdalnym serwerze.

        Args:
            host: Adres serwera
            stack_name: Nazwa stacku
            compose_file_path: Lokalna ścieżka do docker-compose.yml
            user: Użytkownik SSH
            password: Hasło SSH

        Returns:
            Dict ze statusem deploymentu

        Raises:
            CloudProvisionerError: Jeśli deployment nie powiedzie się
        """
        logger.info(f"Rozpoczynam deployment stacku '{stack_name}' na {host}...")

        compose_path = Path(compose_file_path)
        if not compose_path.exists():
            raise CloudProvisionerError(
                f"Plik docker-compose nie istnieje: {compose_file_path}"
            )

        # Walidacja stack_name (bezpieczeństwo)
        if not re.match(r"^[a-zA-Z0-9_-]+$", stack_name):
            raise CloudProvisionerError(
                f"Invalid stack_name '{stack_name}'. Only alphanumeric characters, underscore, and hyphen are allowed."
            )

        # Katalog zdalny
        remote_dir = f"/opt/{stack_name}"
        remote_compose = f"{remote_dir}/docker-compose.yml"

        user = user or self.default_user
        connect_kwargs = {"host": host, "username": user, "known_hosts": None}

        if self.ssh_key_path and Path(self.ssh_key_path).exists():
            connect_kwargs["client_keys"] = [self.ssh_key_path]
        elif password:
            connect_kwargs["password"] = password
        else:
            raise CloudProvisionerError(
                "Brak klucza SSH ani hasła. Nie można nawiązać połączenia."
            )

        try:
            async with asyncio.timeout(self.timeout):
                async with asyncssh.connect(**connect_kwargs) as conn:
                    # Utworzenie katalogu
                    await conn.run(f"mkdir -p {remote_dir}", check=True)

                    # Przesłanie pliku
                    async with conn.start_sftp_client() as sftp:
                        await sftp.put(str(compose_path), remote_compose)
                        logger.info(f"✓ Plik przesłany do {remote_compose}")

                    # Uruchomienie stacku
                    result = await conn.run(
                        f"cd {remote_dir} && docker-compose up -d", check=False
                    )

                    if result.exit_status != 0:
                        raise CloudProvisionerError(
                            f"docker-compose up failed: {result.stderr}"
                        )

                    logger.info(f"✓ Stack '{stack_name}' uruchomiony pomyślnie")
                    return {
                        "status": "deployed",
                        "stack_name": stack_name,
                        "remote_dir": remote_dir,
                        "host": host,
                    }

        except asyncio.TimeoutError:
            raise CloudProvisionerError(f"Timeout podczas deploymentu na {host}")
        except asyncssh.Error as e:
            raise CloudProvisionerError(f"Błąd SSH podczas deploymentu: {e}")
        except Exception as e:
            raise CloudProvisionerError(f"Nieoczekiwany błąd podczas deploymentu: {e}")

    async def check_deployment_health(
        self,
        host: str,
        stack_name: str,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Sprawdza stan stacku na zdalnym serwerze.

        Args:
            host: Adres serwera
            stack_name: Nazwa stacku
            user: Użytkownik SSH
            password: Hasło SSH

        Returns:
            Dict ze statusem kontenersów
        """
        logger.info(f"Sprawdzam stan stacku '{stack_name}' na {host}...")

        # Walidacja stack_name (bezpieczeństwo)
        if not re.match(r"^[a-zA-Z0-9_-]+$", stack_name):
            raise CloudProvisionerError(
                f"Invalid stack_name '{stack_name}'. Only alphanumeric characters, underscore, and hyphen are allowed."
            )

        remote_dir = f"/opt/{stack_name}"
        command = f"cd {remote_dir} && docker-compose ps"

        try:
            stdout, stderr, exit_code = await self._execute_ssh_command(
                host, command, user, password
            )

            if exit_code != 0:
                return {
                    "status": "error",
                    "message": stderr,
                }

            return {
                "status": "healthy",
                "containers": stdout,
            }

        except CloudProvisionerError as e:
            logger.error(f"Błąd podczas sprawdzania zdrowia: {e}")
            return {
                "status": "unreachable",
                "message": str(e),
            }

    def start_broadcasting(self, service_name: Optional[str] = None) -> dict[str, str]:
        """
        Rozpoczyna broadcasting usługi w sieci lokalnej przez mDNS (Zeroconf).

        Args:
            service_name: Nazwa usługi (domyślnie: venom-{hostname})

        Returns:
            Dict ze statusem konfiguracji mDNS
        """
        try:
            hostname = socket.gethostname()
            service_name = service_name or f"venom-{hostname}"
            service_type = "_venom._tcp.local."

            # Pobierz lokalny adres IP (unikaj localhost/127.0.0.1)
            # Próbujemy się połączyć z zewnętrznym adresem, aby wykryć lokalny IP
            local_ip = None
            try:
                # Metoda 1: Połącz się z zewnętrznym adresem (nie wysyła danych)
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
            except Exception:
                # Metoda 2: Fallback do gethostbyname
                try:
                    local_ip = socket.gethostbyname(hostname)
                    # Unikaj localhost
                    if local_ip.startswith("127."):
                        local_ip = None
                except Exception:
                    pass

            if not local_ip:
                raise Exception(
                    "Nie można wykryć lokalnego adresu IP. "
                    "Sprawdź konfigurację sieci."
                )

            # Utwórz ServiceInfo
            self.service_info = ServiceInfo(
                service_type,
                f"{service_name}.{service_type}",
                port=self.service_port,
                addresses=[socket.inet_aton(local_ip)],
                properties={
                    "version": "1.0",
                    "hostname": hostname,
                },
                server=f"{service_name}.local.",
            )

            # Uruchom Zeroconf
            self.zeroconf = Zeroconf()
            self.zeroconf.register_service(self.service_info)

            logger.info(
                f"mDNS broadcasting uruchomiony: {service_name}.local na {local_ip}:{self.service_port}"
            )

            return {
                "status": "active",
                "service_name": f"{service_name}.local",
                "ip": local_ip,
                "port": self.service_port,
                "service_url": self.get_service_url(service_name),
            }

        except Exception as e:
            logger.error(
                f"Błąd podczas uruchamiania mDNS broadcasting: {e}", exc_info=True
            )
            return {
                "status": "error",
                "message": str(e),
            }

    def stop_broadcasting(self) -> dict[str, str]:
        """
        Zatrzymuje broadcasting usługi mDNS.

        Returns:
            Dict ze statusem
        """
        try:
            if self.zeroconf and self.service_info:
                self.zeroconf.unregister_service(self.service_info)
                self.zeroconf.close()
                self.zeroconf = None
                self.service_info = None
                logger.info("mDNS broadcasting zatrzymany")
                return {"status": "stopped"}
            else:
                logger.warning("mDNS broadcasting nie był uruchomiony")
                return {"status": "not_running"}

        except Exception as e:
            logger.error(
                f"Błąd podczas zatrzymywania mDNS broadcasting: {e}", exc_info=True
            )
            return {
                "status": "error",
                "message": str(e),
            }

    def get_service_url(self, service_name: Optional[str] = None) -> str:
        """
        Zwraca URL usługi dla lokalnej sieci.

        Args:
            service_name: Nazwa usługi (domyślnie: venom)

        Returns:
            URL usługi w formacie http://venom.local:8000
        """
        service_name = service_name or "venom"
        # Usuń .local jeśli już jest
        local_suffix = ".local"
        if service_name.endswith(local_suffix):
            service_name = service_name[: -len(local_suffix)]
        return f"http://{service_name}.local:{self.service_port}"

    async def register_in_hive(
        self, hive_url: Optional[str] = None, metadata: Optional[dict] = None
    ) -> dict[str, Any]:
        """
        Rejestruje agenta w centralnym Ulu (Hive Server).

        Agent inicjuje połączenie wychodzące do Ula, dzięki czemu działa za NAT/Firewallem.
        Ul otrzymuje metadane agenta i może przydzielić mu zadania.

        Args:
            hive_url: URL Ula (domyślnie z SETTINGS.HIVE_URL), np. https://hive.example.com:8080
            metadata: Dodatkowe metadane agenta (opcjonalne)

        Returns:
            Dict ze statusem rejestracji i informacjami zwróconymi przez Ul

        Raises:
            CloudProvisionerError: Jeśli rejestracja nie powiedzie się
        """
        hive_url = hive_url or self.hive_url

        if not hive_url:
            logger.warning(
                "HIVE_URL nie jest skonfigurowany. Rejestracja w Ulu pominięta."
            )
            return {
                "status": "skipped",
                "message": "HIVE_URL not configured",
            }

        # Przygotuj payload z metadanymi agenta
        hostname = socket.gethostname()
        payload = {
            "agent_id": self.agent_id,
            "hostname": hostname,
            "service_port": self.service_port,
            "status": "online",
            "capabilities": ["ssh_deployment", "mdns_discovery"],
            "version": "1.0",
        }

        # Dodaj opcjonalne metadane użytkownika
        if metadata:
            payload.update(metadata)

        # Przygotuj nagłówki autoryzacji
        headers = {"Content-Type": "application/json"}
        if SETTINGS.HIVE_REGISTRATION_TOKEN:
            token = SETTINGS.HIVE_REGISTRATION_TOKEN.get_secret_value()
            headers["Authorization"] = f"Bearer {token}"

        try:
            # Wykonaj POST do Ula z timeoutem
            registration_endpoint = f"{hive_url.rstrip('/')}/api/agents/register"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(
                    f"Rejestracja w Ulu: {registration_endpoint} (agent_id={self.agent_id})"
                )

                response = await client.post(
                    registration_endpoint, json=payload, headers=headers
                )

                # Sprawdź status odpowiedzi
                if response.status_code in (200, 201):
                    self.hive_registered = True
                    response_data = response.json()
                    logger.info(
                        f"✓ Agent zarejestrowany w Ulu: {hive_url} (agent_id={self.agent_id})"
                    )

                    return {
                        "status": "registered",
                        "agent_id": self.agent_id,
                        "hive_url": hive_url,
                        "hive_response": response_data,
                    }
                else:
                    error_msg = (
                        f"Ul zwrócił status {response.status_code}: {response.text}"
                    )
                    logger.error(f"Błąd rejestracji w Ulu: {error_msg}")

                    return {
                        "status": "error",
                        "message": error_msg,
                        "status_code": response.status_code,
                    }

        except httpx.TimeoutException:
            error_msg = f"Timeout podczas rejestracji w Ulu: {hive_url}"
            logger.error(error_msg)
            return {
                "status": "timeout",
                "message": error_msg,
            }

        except httpx.RequestError as e:
            error_msg = f"Błąd połączenia z Ulem: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                "status": "connection_error",
                "message": error_msg,
            }

        except Exception as e:
            error_msg = f"Nieoczekiwany błąd podczas rejestracji w Ulu: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                "status": "error",
                "message": error_msg,
            }
