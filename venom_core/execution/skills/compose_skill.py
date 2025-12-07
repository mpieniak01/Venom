"""Moduł: compose_skill - umiejętność orkiestracji środowisk Docker Compose."""

import re
from typing import Annotated, Optional

from semantic_kernel.functions import kernel_function

from venom_core.infrastructure.stack_manager import StackManager
from venom_core.utils.logger import get_logger
from venom_core.utils.port_authority import find_free_port, is_port_in_use

logger = get_logger(__name__)

# Konfiguracja zakresu portów dla automatycznej alokacji
PORT_RANGE_START = 8000
PORT_RANGE_END = 9000


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
        self.stack_manager = StackManager(workspace_root=workspace_root)
        logger.info("ComposeSkill zainicjalizowany")

    @kernel_function(
        name="create_environment",
        description="Tworzy i uruchamia środowisko wielokontenerowe (stack) na podstawie docker-compose.yml. "
        "Automatycznie znajduje wolne porty jeśli są konflikty. "
        "Użyj gdy zadanie wymaga bazy danych, cache'a, kolejki lub innych serwisów.",
    )
    async def create_environment(
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
            # Walidacja nazwy stacka
            if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9]|)$", stack_name):
                return (
                    f"Błąd: Nieprawidłowa nazwa stacka '{stack_name}'. "
                    "Nazwa musi zaczynać się i kończyć małą literą lub cyfrą, może zawierać myślniki w środku."
                )

            logger.info(f"Tworzenie środowiska: {stack_name}")

            # Znajdź i zastąp placeholdery portów
            processed_content = await self._process_port_placeholders(compose_content)

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

                return result
            else:
                return f"❌ Błąd podczas tworzenia środowiska '{stack_name}':\n{message}"

        except Exception as e:
            logger.error(f"Błąd w create_environment: {e}")
            return f"❌ Nieoczekiwany błąd: {str(e)}"

    @kernel_function(
        name="destroy_environment",
        description="Zatrzymuje i usuwa środowisko Docker Compose wraz z wolumenami. "
        "Użyj do czyszczenia zasobów po zakończeniu pracy.",
    )
    async def destroy_environment(
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
    async def check_service_health(
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
                return (
                    f"❌ Nie można pobrać logów serwisu '{service_name}':\n{logs}"
                )

        except Exception as e:
            logger.error(f"Błąd w check_service_health: {e}")
            return f"❌ Nieoczekiwany błąd: {str(e)}"

    @kernel_function(
        name="list_environments",
        description="Listuje wszystkie aktywne środowiska Docker Compose. "
        "Użyj aby zobaczyć jakie stacki są obecnie uruchomione.",
    )
    async def list_environments(self) -> str:
        """
        Listuje aktywne środowiska.

        Returns:
            Lista aktywnych stacków
        """
        try:
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
    async def get_environment_status(
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

    async def _process_port_placeholders(self, compose_content: str) -> str:
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
        assigned_ports = set()
        
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
                free_port = self._find_unique_free_port(PORT_RANGE_START, assigned_ports)
                logger.info(f"Znaleziono wolny port: {free_port}")

            # Dodaj do przypisanych portów
            assigned_ports.add(free_port)
            
            # Zastąp pierwsze wystąpienie placeholdera
            processed = processed.replace(placeholder, str(free_port), 1)

        return processed

    def _find_unique_free_port(self, start: int, assigned_ports: set) -> int:
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
        # Proste wyciąganie portów z linii typu "8080:80"
        port_pattern = r"(\d+):(\d+)"
        ports = re.findall(port_pattern, compose_content)

        if not ports:
            return ""

        result = ""
        for host_port, container_port in ports:
            result += f"  • localhost:{host_port} -> kontener:{container_port}\n"

        return result
