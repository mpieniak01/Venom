"""Moduł: hardware_pi - most do komunikacji z Raspberry Pi (Rider-Pi)."""

import asyncio
from typing import Any, Dict, Optional

from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)


class HardwareBridge:
    """
    Most sprzętowy do komunikacji z fizycznym Raspberry Pi (Rider-Pi).
    Obsługuje komunikację poprzez SSH (paramiko) lub HTTP (pigpio daemon).
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 22,
        username: str = "pi",
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        protocol: str = "ssh",
    ):
        """
        Inicjalizacja mostu sprzętowego.

        Args:
            host: Adres IP Raspberry Pi
            port: Port SSH (domyślnie 22) lub HTTP (8888 dla pigpio)
            username: Nazwa użytkownika SSH
            password: Hasło SSH (opcjonalne jeśli używamy klucza)
            key_file: Ścieżka do klucza SSH
            protocol: Protokół komunikacji ('ssh' lub 'http')
        """
        self.host = host
        self.port = port
        self.username = username
        self.password: Optional[Any] = password
        self.key_file = key_file
        self.protocol = protocol
        self.ssh_client: Optional[Any] = None
        self.connected = False
        logger.info(f"Inicjalizacja HardwareBridge: host={host}, protocol={protocol}")

    async def connect(self) -> bool:
        """
        Nawiązuje połączenie z Raspberry Pi.

        Returns:
            True jeśli połączenie udane, False w przeciwnym wypadku
        """
        try:
            if self.protocol == "ssh":
                return await self._connect_ssh()
            elif self.protocol == "http":
                return await self._connect_http()
            else:
                logger.error(f"Nieznany protokół: {self.protocol}")
                return False
        except Exception as e:
            logger.error(f"Błąd podczas łączenia z Raspberry Pi: {e}")
            return False

    async def _connect_ssh(self) -> bool:
        """Łączy przez SSH."""
        try:
            import paramiko

            client = paramiko.SSHClient()

            # SECURITY: Use WarningPolicy instead of AutoAddPolicy for better security.
            # In production, consider using RejectPolicy and managing known_hosts explicitly.
            # For trusted local networks (like Rider-Pi), WarningPolicy provides a balance.
            client.set_missing_host_key_policy(paramiko.WarningPolicy())

            # Alternatively, load known hosts from file for stricter security:
            # self.ssh_client.load_system_host_keys()
            # self.ssh_client.set_missing_host_key_policy(paramiko.RejectPolicy())

            # Połącz w osobnym wątku (paramiko jest blokujący)
            loop = asyncio.get_event_loop()
            password_value = None
            if self.password is not None:
                if hasattr(self.password, "get_secret_value"):
                    password_value = self.password.get_secret_value()
                else:
                    password_value = self.password

            await loop.run_in_executor(
                None,
                lambda: client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=password_value,
                    key_filename=self.key_file,
                    timeout=10,
                ),
            )

            self.ssh_client = client

            self.connected = True
            logger.info(f"Połączono z Raspberry Pi przez SSH: {self.host}")
            return True

        except ImportError:
            logger.error("paramiko nie jest zainstalowany. Użyj: pip install paramiko")
            return False
        except Exception as e:
            logger.error(f"Błąd podczas łączenia SSH: {e}")
            return False

    async def _connect_http(self) -> bool:
        """Łączy przez HTTP (pigpio daemon)."""
        try:
            import httpx

            # Test połączenia
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(build_http_url(self.host, self.port, "/"))
                if response.status_code == 200:
                    self.connected = True
                    logger.info(f"Połączono z Raspberry Pi przez HTTP: {self.host}")
                    return True
                else:
                    logger.error(f"Błąd HTTP: {response.status_code}")
                    return False

        except ImportError:
            logger.error("httpx nie jest zainstalowany. Użyj: pip install httpx")
            return False
        except Exception as e:
            logger.error(f"Błąd podczas łączenia HTTP: {e}")
            return False

    async def disconnect(self):
        """Rozłącza połączenie."""
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None
        self.connected = False
        logger.info("Rozłączono z Raspberry Pi")

    async def execute_command(self, command: str) -> Dict[str, Any]:
        """
        Wykonuje komendę SSH na Raspberry Pi.

        Args:
            command: Komenda do wykonania

        Returns:
            Dict z stdout, stderr i return_code
        """
        if not self.connected or not self.ssh_client:
            logger.error("Brak połączenia z Raspberry Pi")
            return {"stdout": "", "stderr": "Not connected", "return_code": -1}

        try:
            loop = asyncio.get_event_loop()
            stdin, stdout, stderr = await loop.run_in_executor(
                None, self.ssh_client.exec_command, command
            )

            stdout_text = await loop.run_in_executor(None, stdout.read)
            stderr_text = await loop.run_in_executor(None, stderr.read)
            return_code = stdout.channel.recv_exit_status()

            result = {
                "stdout": stdout_text.decode("utf-8"),
                "stderr": stderr_text.decode("utf-8"),
                "return_code": return_code,
            }

            logger.debug(f"Wykonano komendę: {command} -> {result}")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas wykonywania komendy: {e}")
            return {"stdout": "", "stderr": str(e), "return_code": -1}

    async def read_sensor(self, sensor_id: str) -> Optional[float]:
        """
        Pobiera dane z czujnika.

        Args:
            sensor_id: ID czujnika (np. 'cpu_temp', 'gpio_4')

        Returns:
            Wartość czujnika lub None w przypadku błędu
        """
        try:
            if sensor_id == "cpu_temp":
                # Odczytaj temperaturę CPU
                result = await self.execute_command(
                    "cat /sys/class/thermal/thermal_zone0/temp"
                )
                if result["return_code"] == 0:
                    # Temperatura w milidegrees Celcius
                    temp = float(result["stdout"].strip()) / 1000.0
                    logger.info(f"Temperatura CPU: {temp}°C")
                    return temp

            elif sensor_id.startswith("gpio_"):
                # Odczytaj stan GPIO
                pin = sensor_id.split("_")[1]
                result = await self.execute_command(
                    f"raspi-gpio get {pin} | grep 'level'"
                )
                if result["return_code"] == 0:
                    # Parse output (przykład: "level=1 fsel=0")
                    if "level=1" in result["stdout"]:
                        return 1.0
                    else:
                        return 0.0

            logger.warning(f"Nieznany sensor_id: {sensor_id}")
            return None

        except Exception as e:
            logger.error(f"Błąd podczas odczytu czujnika {sensor_id}: {e}")
            return None

    async def set_gpio(self, pin: int, state: bool) -> bool:
        """
        Ustawia stan pinu GPIO.

        Args:
            pin: Numer pinu GPIO (BCM numbering)
            state: True (HIGH) lub False (LOW)

        Returns:
            True jeśli sukces, False w przeciwnym wypadku
        """
        try:
            state_value = 1 if state else 0

            if self.protocol == "ssh":
                # Użyj raspi-gpio (preinstalowane na Raspberry Pi OS)
                result = await self.execute_command(
                    f"raspi-gpio set {pin} op dh && raspi-gpio set {pin} {state_value}"
                )
                success = result["return_code"] == 0

            elif self.protocol == "http":
                # Użyj pigpio HTTP API
                import httpx

                async with httpx.AsyncClient(timeout=5.0) as client:
                    # Set pin mode to output
                    await client.get(
                        build_http_url(self.host, self.port, f"/mode/{pin}/w")
                    )
                    # Set pin state
                    response = await client.get(
                        build_http_url(self.host, self.port, f"/w/{pin}/{state_value}")
                    )
                    success = response.status_code == 200
            else:
                success = False

            if success:
                logger.info(f"GPIO {pin} ustawiony na {'HIGH' if state else 'LOW'}")
            else:
                logger.error(f"Błąd podczas ustawiania GPIO {pin}")

            return success

        except Exception as e:
            logger.error(f"Błąd podczas ustawiania GPIO {pin}: {e}")
            return False

    async def get_system_info(self) -> Dict[str, Any]:
        """
        Pobiera informacje o systemie Raspberry Pi.

        Returns:
            Dict z informacjami systemowymi
        """
        info = {}

        try:
            # Temperatura CPU
            cpu_temp = await self.read_sensor("cpu_temp")
            if cpu_temp:
                info["cpu_temp"] = cpu_temp

            # Uptime
            result = await self.execute_command("uptime -p")
            if result["return_code"] == 0:
                info["uptime"] = result["stdout"].strip()

            # Memory usage
            result = await self.execute_command(
                "free -m | awk 'NR==2{printf \"%.2f\", $3*100/$2 }'"
            )
            if result["return_code"] == 0:
                info["memory_usage_percent"] = float(result["stdout"].strip())

            # Disk usage
            result = await self.execute_command(
                "df -h / | awk 'NR==2{print $5}' | sed 's/%//'"
            )
            if result["return_code"] == 0:
                info["disk_usage_percent"] = float(result["stdout"].strip())

            logger.info(f"Informacje systemowe: {info}")
        except Exception as e:
            logger.error(f"Błąd podczas pobierania informacji systemowych: {e}")

        return info

    async def emergency_procedure(self, procedure_name: str) -> bool:
        """
        Wykonuje procedurę awaryjną.

        Args:
            procedure_name: Nazwa procedury ('reboot', 'shutdown', 'reset_gpio')

        Returns:
            True jeśli sukces, False w przeciwnym wypadku
        """
        logger.warning(f"Uruchomiono procedurę awaryjną: {procedure_name}")

        try:
            if procedure_name == "reboot":
                result = await self.execute_command("sudo reboot")
                return result["return_code"] == 0

            elif procedure_name == "shutdown":
                result = await self.execute_command("sudo shutdown -h now")
                return result["return_code"] == 0

            elif procedure_name == "reset_gpio":
                # Reset wszystkich GPIO do stanu wejściowego
                result = await self.execute_command(
                    "for i in {0..27}; do raspi-gpio set $i ip; done"
                )
                return result["return_code"] == 0

            else:
                logger.error(f"Nieznana procedura awaryjna: {procedure_name}")
                return False

        except Exception as e:
            logger.error(f"Błąd podczas wykonywania procedury awaryjnej: {e}")
            return False
