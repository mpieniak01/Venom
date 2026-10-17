"""Moduł: compose_skill - umiejętność orkiestracji środowisk Docker Compose."""

import os
import re
from typing import Annotated, Optional

from venom_core.config import SETTINGS
from venom_core.execution.agent_contracts import tool_function as kernel_function
from venom_core.infrastructure.stack_manager import StackManager
from venom_core.utils.logger import get_logger
from venom_core.utils.port_authority import is_port_in_use

logger = get_logger(__name__)

# Konfiguracja zakresu portów dla automatycznej alokacji
PORT_RANGE_START = 8000
PORT_RANGE_END = 9000

# Konfiguracja generowania sekretów
SECRET_KEY_BYTES = 32  # Liczba bajtów dla SECRET_KEY (64 znaki hex)
STACK_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9]|)$")
SERVICE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


class ComposeSkill:
    """
    Skill do zarządzania środowiskami Docker Compose.

    Umożliwia agentom tworzenie i zarządzanie wielokontenerowymi środowiskami
    (stackami) przy użyciu docker-compose.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Inicjalizacja ComposeSkill.

        Args:
            workspace_root: Katalog roboczy (domyślnie z SETTINGS)
        """
        self.stack_manager: Optional[StackManager]
        self.disabled_reason: Optional[str] = None

        try:
            self.stack_manager = StackManager(workspace_root=workspace_root)
            logger.info("ComposeSkill zainicjalizowany")
        except RuntimeError as exc:
            # Środowisko lokalne często nie ma Dockera – zamiast wywalać cały system
            # traktujemy ComposeSkill jako opcjonalny i zgłaszamy brak w runtime.
            self.stack_manager = None
            self.disabled_reason = str(exc)
            logger.warning(
                "ComposeSkill wyłączony - Docker Compose niedostępny: %s", exc
            )

    def _compose_unavailable_response(self) -> str:
        """Informuje agenta o braku możliwości użycia Docker Compose."""
        reason = (
            self.disabled_reason or "Docker Compose nie jest dostępny w tym środowisku."
        )
        return (
            "❌ ComposeSkill jest niedostępny: "
            f"{reason}\n"
            "Zainstaluj Docker + Docker Compose lub uruchom Venom na maszynie z tym środowiskiem, "
            "aby korzystać z orkiestracji stacków."
        )

    def _validate_stack_name(self, stack_name: str) -> Optional[str]:
        """Waliduje nazwę stacka."""
        if not stack_name or not stack_name.strip():
            return "❌ Błąd: Nazwa stacka nie może być pusta."
        if not STACK_NAME_PATTERN.fullmatch(stack_name):
            return (
                f"Błąd: Nieprawidłowa nazwa stacka '{stack_name}'. "
                "Nazwa musi zaczynać się i kończyć małą literą lub cyfrą, "
                "może zawierać myślniki w środku."
            )
        return None

    def _validate_service_name(self, service_name: str) -> Optional[str]:
        """Waliduje nazwę serwisu w compose."""
        if not service_name or not service_name.strip():
            return "❌ Błąd: Nazwa serwisu nie może być pusta."
        if not SERVICE_NAME_PATTERN.fullmatch(service_name):
            return (
                f"❌ Błąd: Nieprawidłowa nazwa serwisu '{service_name}'. "
                "Dozwolone: litery, cyfry, '_', '-', '.'."
            )
        return None

    def _scan_compose_policy_issues(self, compose_content: str) -> list[str]:
        """Wykrywa potencjalnie niebezpieczne wzorce w compose (policy guard)."""
        issues: list[str] = []
        checks = [
            (r"(?im)^\s*privileged\s*:\s*true\b", "Użycie privileged: true"),
            (
                r"(?im)^\s*network_mode\s*:\s*[\"']?host[\"']?\s*$",
                "Użycie network_mode: host",
            ),
            (r"/var/run/docker\.sock", "Bind mount /var/run/docker.sock"),
            (
                r"(?im)^\s*-\s*[\"']?/\s*:[^\r\n]+$",
                "Bind mount katalogu root '/' z hosta",
            ),
            (
                r"(?im)^\s*-\s*[\"']?[a-zA-Z]:[/\\]\s*:[^\r\n]+$",
                "Bind mount root dysku hosta Windows (np. C:/)",
            ),
        ]
        for pattern, description in checks:
            if re.search(pattern, compose_content):
                issues.append(description)
        return issues

    @kernel_function(
        name="create_environment",
        description="Tworzy i uruchamia środowisko wielokontenerowe (stack) na podstawie docker-compose.yml. "
        "Automatycznie znajduje wolne porty jeśli są konflikty. "
        "Użyj gdy zadanie wymaga bazy danych, cache'a, kolejki lub innych serwisów.",
    )
    def create_environment(
        self,
        compose_content: Annotated[
            str,
            "Zawartość pliku docker-compose.yml definiująca stack. "
            "Może zawierać placeholder {{PORT}} który zostanie zastąpiony wolnym portem.",
        ],
        stack_name: Annotated[
            str,
            "Nazwa środowiska/stacka (np. 'todo-app', 'api-stack'). "
            "Musi być unikalna i składać się z małych liter, cyfr i myślników.",
        ],
    ) -> str:
        """
        Tworzy i uruchamia środowisko Docker Compose.

        Args:
            compose_content: Zawartość docker-compose.yml
            stack_name: Nazwa stacka

        Returns:
            Komunikat o sukcesie lub błędzie
        """
        try:
            if not self.stack_manager:
                return self._compose_unavailable_response()

            stack_name_error = self._validate_stack_name(stack_name)
            if stack_name_error:
                return stack_name_error

            logger.info(f"Tworzenie środowiska: {stack_name}")

            # Znajdź i zastąp placeholdery portów
            processed_content = self._process_port_placeholders(compose_content)

            # Znajdź i zastąp inne placeholdery (SECRET_KEY, HOST_IP, VOLUME_ROOT)
            processed_content = self._process_template_placeholders(processed_content)

            # Walidacja YAML
            if not self._validate_yaml(processed_content):
                return (
                    "❌ Błąd: Wygenerowany docker-compose.yml ma nieprawidłową składnię YAML. "
                    "Sprawdź poprawność szablonu."
                )

            policy_issues = self._scan_compose_policy_issues(processed_content)
            policy_mode = os.getenv("VENOM_COMPOSE_POLICY_MODE", "warn").lower()
            if policy_issues:
                issues = "; ".join(policy_issues)
                if policy_mode == "block":
                    logger.warning("Compose policy BLOCK (%s): %s", stack_name, issues)
                    return (
                        "❌ Compose zablokowany przez politykę bezpieczeństwa: "
                        f"{issues}"
                    )
                logger.warning("Compose policy WARN (%s): %s", stack_name, issues)

            # Wdróż stack
            success, message = self.stack_manager.deploy_stack(
                compose_content=processed_content,
                stack_name=stack_name,
            )

            if success:
                # Pobierz informacje o portach z wdrożonego stacka
                port_info = self._extract_port_info(processed_content)
                result = (
                    f"✅ Środowisko '{stack_name}' utworzone i uruchomione pomyślnie!\n\n"
                    f"{message}\n"
                )
                if port_info:
                    result += f"\n📡 Dostępne porty:\n{port_info}"
                if policy_issues:
                    result += (
                        "\n⚠️ Ostrzeżenia polityki bezpieczeństwa (tryb warn-only):\n"
                        + "\n".join(f"  • {issue}" for issue in policy_issues)
                    )

                return result
            else:
                return (
                    f"❌ Błąd podczas tworzenia środowiska '{stack_name}':\n{message}"
                )

        except Exception as e:
            logger.error(f"Błąd w create_environment: {e}")
            return f"❌ Nieoczekiwany błąd: {str(e)}"

    @kernel_function(
        name="destroy_environment",
        description="Zatrzymuje i usuwa środowisko Docker Compose wraz z wolumenami. "
        "Użyj do czyszczenia zasobów po zakończeniu pracy.",
    )
    def destroy_environment(
        self,
        stack_name: Annotated[str, "Nazwa środowiska/stacka do usunięcia"],
    ) -> str:
        """
        Usuwa środowisko Docker Compose.

        Args:
            stack_name: Nazwa stacka

        Returns:
            Komunikat o sukcesie lub błędzie
        """
        try:
            if not self.stack_manager:
                return self._compose_unavailable_response()
            stack_name_error = self._validate_stack_name(stack_name)
            if stack_name_error:
                return stack_name_error
            logger.info(f"Usuwanie środowiska: {stack_name}")

            success, message = self.stack_manager.destroy_stack(
                stack_name=stack_name,
                remove_volumes=True,
            )

            if success:
                return f"✅ Środowisko '{stack_name}' usunięte pomyślnie\n{message}"
            else:
                return f"❌ Błąd podczas usuwania środowiska '{stack_name}':\n{message}"

        except Exception as e:
            logger.error(f"Błąd w destroy_environment: {e}")
            return f"❌ Nieoczekiwany błąd: {str(e)}"

    @kernel_function(
        name="check_service_health",
        description="Sprawdza czy serwis w środowisku działa poprawnie poprzez "
        "pobranie logów lub sprawdzenie statusu. Użyj do weryfikacji działania aplikacji.",
    )
    def check_service_health(
        self,
        stack_name: Annotated[str, "Nazwa środowiska/stacka"],
        service_name: Annotated[
            str, "Nazwa serwisu w docker-compose.yml (np. 'api', 'db', 'redis')"
        ],
    ) -> str:
        """
        Sprawdza health serwisu w stacku.

        Args:
            stack_name: Nazwa stacka
            service_name: Nazwa serwisu

        Returns:
            Status serwisu i ostatnie logi
        """
        try:
            if not self.stack_manager:
                return self._compose_unavailable_response()
            stack_name_error = self._validate_stack_name(stack_name)
            if stack_name_error:
                return stack_name_error
            service_name_error = self._validate_service_name(service_name)
            if service_name_error:
                return service_name_error
            logger.info(f"Sprawdzanie zdrowia serwisu: {service_name} w {stack_name}")

            # Pobierz logi serwisu
            success, logs = self.stack_manager.get_service_logs(
                stack_name=stack_name,
                service=service_name,
                tail=50,
            )

            if success:
                return (
                    f"✅ Serwis '{service_name}' w środowisku '{stack_name}':\n\n"
                    f"📋 Ostatnie logi:\n{logs}"
                )
            else:
                return f"❌ Nie można pobrać logów serwisu '{service_name}':\n{logs}"

        except Exception as e:
            logger.error(f"Błąd w check_service_health: {e}")
            return f"❌ Nieoczekiwany błąd: {str(e)}"

    @kernel_function(
        name="list_environments",
        description="Listuje wszystkie aktywne środowiska Docker Compose. "
        "Użyj aby zobaczyć jakie stacki są obecnie uruchomione.",
    )
    def list_environments(self) -> str:
        """
        Listuje aktywne środowiska.

        Returns:
            Lista aktywnych stacków
        """
        try:
            if not self.stack_manager:
                return self._compose_unavailable_response()
            running_stacks = self.stack_manager.get_running_stacks()

            if not running_stacks:
                return "📦 Brak aktywnych środowisk"

            result = f"📦 Aktywne środowiska ({len(running_stacks)}):\n\n"
            for stack in running_stacks:
                result += f"• {stack['name']} - {stack['status']}\n"
                result += f"  Ścieżka: {stack['path']}\n\n"

            return result

        except Exception as e:
            logger.error(f"Błąd w list_environments: {e}")
            return f"❌ Błąd podczas listowania środowisk: {str(e)}"

    @kernel_function(
        name="get_environment_status",
        description="Pobiera szczegółowy status środowiska Docker Compose. "
        "Pokazuje które kontenery działają i ich stan.",
    )
    def get_environment_status(
        self,
        stack_name: Annotated[str, "Nazwa środowiska/stacka"],
    ) -> str:
        """
        Pobiera status środowiska.

        Args:
            stack_name: Nazwa stacka

        Returns:
            Status środowiska
        """
        try:
            if not self.stack_manager:
                return self._compose_unavailable_response()
            stack_name_error = self._validate_stack_name(stack_name)
            if stack_name_error:
                return stack_name_error
            success, status = self.stack_manager.get_stack_status(stack_name)

            if success:
                stack_status = status.get("status", "unknown")
                details = status.get("details", "")

                result = f"📊 Status środowiska '{stack_name}': {stack_status}\n"
                if details:
                    result += f"\n{details}"

                return result
            else:
                error = status.get("error", "Nieznany błąd")
                return f"❌ Błąd: {error}"

        except Exception as e:
            logger.error(f"Błąd w get_environment_status: {e}")
            return f"❌ Nieoczekiwany błąd: {str(e)}"

    def _process_port_placeholders(self, compose_content: str) -> str:
        """
        Przetwarza placeholdery portów w docker-compose.yml.

        Znajduje placeholdery {{PORT}} i zastępuje je wolnymi portami.
        Każdy unikalny placeholder otrzymuje unikalny port.

        Args:
            compose_content: Zawartość docker-compose.yml

        Returns:
            Przetworzona zawartość z zastąpionymi portami
        """
        # Znajdź wszystkie placeholdery portów
        port_pattern = r"\{\{PORT(?::(\d+))?\}\}"
        matches = list(re.finditer(port_pattern, compose_content))

        if not matches:
            return compose_content

        # Śledź przypisane porty aby uniknąć duplikatów
        assigned_ports: set[int] = set()

        # Dla każdego placeholdera znajdź wolny port
        processed = compose_content
        for match in matches:
            placeholder = match.group(0)
            preferred_port = match.group(1)

            if preferred_port:
                # Sprawdź czy preferowany port jest wolny
                preferred = int(preferred_port)
                if not is_port_in_use(preferred) and preferred not in assigned_ports:
                    free_port = preferred
                    logger.info(f"Użycie preferowanego portu: {free_port}")
                else:
                    # Znajdź alternatywny port
                    free_port = self._find_unique_free_port(preferred, assigned_ports)
                    logger.info(
                        f"Port {preferred} zajęty lub już przypisany, użycie alternatywnego: {free_port}"
                    )
            else:
                # Znajdź dowolny wolny port
                free_port = self._find_unique_free_port(
                    PORT_RANGE_START, assigned_ports
                )
                logger.info(f"Znaleziono wolny port: {free_port}")

            # Dodaj do przypisanych portów
            assigned_ports.add(free_port)

            # Zastąp pierwsze wystąpienie placeholdera
            processed = processed.replace(placeholder, str(free_port), 1)

        return processed

    def _process_template_placeholders(self, compose_content: str) -> str:
        """
        Przetwarza placeholdery szablonów w docker-compose.yml.

        Obsługuje:
        - {{SECRET_KEY}} - generuje losowy klucz (32 bajty hex)
        - {{HOST_IP}} - wstawia adres IP hosta
        - {{VOLUME_ROOT}} - wstawia absolutną ścieżkę do workspace

        Args:
            compose_content: Zawartość docker-compose.yml

        Returns:
            Przetworzona zawartość z zastąpionymi placeholderami
        """
        import secrets
        import socket

        processed = compose_content

        # {{SECRET_KEY}} - generuj silny losowy ciąg znaków
        if "{{SECRET_KEY}}" in processed:
            secret_key = secrets.token_hex(SECRET_KEY_BYTES)  # 64 znaki hex
            processed = processed.replace("{{SECRET_KEY}}", secret_key)
            logger.info("Wygenerowano SECRET_KEY dla docker-compose")

        # {{HOST_IP}} - wstaw adres IP hosta
        if "{{HOST_IP}}" in processed:
            try:
                # Pobierz lokalny adres IP hosta
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect((SETTINGS.NETWORK_PROBE_HOST, SETTINGS.NETWORK_PROBE_PORT))
                host_ip = s.getsockname()[0]
                s.close()
            except Exception as e:
                logger.warning(f"Nie można pobrać HOST_IP: {e}. Używam 127.0.0.1")
                host_ip = "127.0.0.1"

            processed = processed.replace("{{HOST_IP}}", host_ip)
            logger.info(f"Wstawiono HOST_IP: {host_ip}")

        # {{VOLUME_ROOT}} - wstaw absolutną ścieżkę do workspace
        if "{{VOLUME_ROOT}}" in processed:
            from pathlib import Path

            if self.stack_manager:
                volume_root = str(Path(self.stack_manager.workspace_root).resolve())
            else:
                volume_root = str(Path(SETTINGS.WORKSPACE_ROOT).resolve())
            processed = processed.replace("{{VOLUME_ROOT}}", volume_root)
            logger.info(f"Wstawiono VOLUME_ROOT: {volume_root}")

        return processed

    def _validate_yaml(self, compose_content: str) -> bool:
        """
        Waliduje składnię YAML pliku docker-compose.

        Args:
            compose_content: Zawartość docker-compose.yml do walidacji

        Returns:
            True jeśli YAML jest poprawny, False w przeciwnym razie
        """
        try:
            import yaml

            yaml.safe_load(compose_content)
            return True
        except yaml.YAMLError as e:
            logger.error(f"Błąd walidacji YAML: {e}")
            return False
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas walidacji YAML: {e}")
            return False

    def _find_unique_free_port(self, start: int, assigned_ports: set[int]) -> int:
        """
        Znajduje wolny port który nie jest jeszcze przypisany.

        Args:
            start: Port początkowy do przeszukiwania
            assigned_ports: Zbiór już przypisanych portów

        Returns:
            Wolny port

        Raises:
            RuntimeError: Jeśli nie można znaleźć wolnego portu
        """
        # Przeszukaj od start do PORT_RANGE_END
        for port in range(start, PORT_RANGE_END):
            if port not in assigned_ports and not is_port_in_use(port):
                return port

        # Przeszukaj od PORT_RANGE_START jeśli nie znaleziono
        if start > PORT_RANGE_START:
            for port in range(PORT_RANGE_START, start):
                if port not in assigned_ports and not is_port_in_use(port):
                    return port

        raise RuntimeError(
            f"Nie można znaleźć wolnego portu (start: {start}, assigned: {len(assigned_ports)})"
        )

    def _extract_port_info(self, compose_content: str) -> str:
        """
        Wyciąga informacje o portach z docker-compose.yml.

        Args:
            compose_content: Zawartość docker-compose.yml

        Returns:
            Sformatowane informacje o portach
        """
        # Proste wyciąganie portów z linii typu "8080:80" bez regex.
        ports: list[tuple[str, str]] = []
        for raw_line in compose_content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("-"):
                line = line[1:].strip()
            line = line.strip("\"'")
            if ":" not in line:
                continue
            host_port, container_part = line.split(":", 1)
            host_port = host_port.strip().strip("\"'")
            container_port = (
                container_part.strip().strip("\"'").split("/", 1)[0].strip()
            )
            if host_port.isdigit() and container_port.isdigit():
                ports.append((host_port, container_port))

        if not ports:
            return ""

        result = ""
        for host_port, container_port in ports:
            result += f"  • localhost:{host_port} -> kontener:{container_port}\n"

        return result
