"""Moduł: mirror_world - zarządzanie lustrzanymi instancjami Venom do testowania."""

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger
from venom_core.utils.port_authority import find_free_port

logger = get_logger(__name__)


@dataclass
class InstanceInfo:
    """Informacje o instancji lustrzanej."""

    instance_id: str
    port: int
    branch_name: str
    workspace_path: Path
    container_name: Optional[str] = None
    status: str = "initializing"  # initializing, running, failed, stopped


class MirrorWorld:
    """
    Zarządca lustrzanych instancji Venom (Shadow Instances).

    Umożliwia uruchamianie klonów Venom w izolowanych środowiskach Docker
    w celu bezpiecznego testowania zmian w kodzie źródłowym przed ich
    zastosowaniem do głównej instancji.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Inicjalizacja MirrorWorld.

        Args:
            workspace_root: Katalog workspace (domyślnie z SETTINGS)
        """
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.mirror_dir = self.workspace_root / "mirrors"
        self.mirror_dir.mkdir(parents=True, exist_ok=True)

        # Rejestr aktywnych instancji
        self.instances: dict[str, InstanceInfo] = {}

        logger.info(f"MirrorWorld zainicjalizowany z workspace: {self.workspace_root}")

    def spawn_shadow_instance(
        self, branch_name: str, project_root: Path, instance_id: Optional[str] = None
    ) -> InstanceInfo:
        """
        Tworzy lustrzaną instancję Venom z podanego brancha.

        Proces:
        1. Klonuje kod Venoma do tymczasowego katalogu
        2. Przełącza na podany branch
        3. Przygotowuje środowisko Docker
        4. Uruchamia instancję Shadow Venom na wolnym porcie

        Args:
            branch_name: Nazwa brancha Git do testowania
            project_root: Katalog główny projektu Venom
            instance_id: Opcjonalny ID instancji (domyślnie: branch_name-timestamp)

        Returns:
            InstanceInfo z informacjami o instancji

        Raises:
            RuntimeError: Jeśli nie udało się utworzyć instancji
        """
        # Wygeneruj ID instancji
        if not instance_id:
            timestamp = int(time.time())
            clean_branch = branch_name.replace("/", "_").replace("\\", "_")
            instance_id = f"{clean_branch}_{timestamp}"

        logger.info(
            f"Tworzenie lustrzanej instancji: {instance_id} z brancha {branch_name}"
        )

        try:
            # 1. Przygotuj katalog dla instancji lustrzanej
            instance_dir = self.mirror_dir / instance_id
            if instance_dir.exists():
                logger.warning(f"Katalog {instance_dir} już istnieje, usuwam...")
                shutil.rmtree(instance_dir)
            instance_dir.mkdir(parents=True)

            # 2. Sklonuj kod do katalogu instancji
            logger.info(f"Klonowanie kodu z {project_root} do {instance_dir}")
            shutil.copytree(
                project_root,
                instance_dir / "venom",
                ignore=shutil.ignore_patterns(
                    ".git",
                    "__pycache__",
                    "*.pyc",
                    ".pytest_cache",
                    "*.egg-info",
                    "workspace",
                    "data",
                    ".venv",
                    "venv",
                ),
            )

            # 3. Znajdź wolny port
            port = find_free_port(start=8001, end=9000)
            if not port:
                raise RuntimeError("Brak dostępnych portów dla instancji lustrzanej")

            logger.info(f"Przydzielony port {port} dla instancji {instance_id}")

            # 4. Utwórz informacje o instancji
            info = InstanceInfo(
                instance_id=instance_id,
                port=port,
                branch_name=branch_name,
                workspace_path=instance_dir / "venom",
                status="initialized",
            )

            # 5. Zarejestruj instancję
            self.instances[instance_id] = info

            logger.info(
                f"✅ Instancja lustrzana {instance_id} utworzona (port: {port})"
            )
            return info

        except Exception as e:
            error_msg = f"Błąd podczas tworzenia instancji lustrzanej: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    async def start_shadow_instance(
        self, instance_id: str, use_docker: bool = True
    ) -> bool:
        """
        Uruchamia instancję lustrzaną Venom.

        Args:
            instance_id: ID instancji do uruchomienia
            use_docker: Czy używać Docker (domyślnie True)

        Returns:
            True jeśli uruchomiono pomyślnie, False w przeciwnym razie
        """
        if instance_id not in self.instances:
            logger.error(f"Instancja {instance_id} nie istnieje")
            return False

        info = self.instances[instance_id]
        logger.info(f"Uruchamianie instancji lustrzanej: {instance_id}")

        try:
            if use_docker:
                # Uruchom w Dockerze
                success = await self._start_in_docker(info)
            else:
                # Uruchom jako lokalny proces (dla testów)
                success = await self._start_local_process(info)

            if success:
                info.status = "running"
                logger.info(
                    f"✅ Instancja {instance_id} uruchomiona na porcie {info.port}"
                )
            else:
                info.status = "failed"
                logger.error(f"❌ Nie udało się uruchomić instancji {instance_id}")

            return success

        except Exception as e:
            logger.error(f"Błąd podczas uruchamiania instancji: {e}", exc_info=True)
            info.status = "failed"
            return False

    async def _start_in_docker(self, info: InstanceInfo) -> bool:
        """
        Uruchamia instancję w kontenerze Docker.

        Args:
            info: Informacje o instancji

        Returns:
            True jeśli pomyślnie uruchomiono

        Note:
            TODO (Task 021 - Phase 2): Pełna implementacja uruchamiania w Docker wymaga:
            - Docker-in-Docker lub montowanie docker.sock
            - Przygotowanie Dockerfile dla Shadow Venom
            - Zarządzanie cyklem życia kontenera
            - Networking configuration dla nowego portu
            Na razie zwraca False - funkcjonalność planowana do Phase 2.
        """
        # Placeholder: Pełna implementacja w Phase 2
        logger.warning(
            "Uruchamianie w Docker nie jest jeszcze w pełni zaimplementowane (Phase 2)"
        )
        return False

    async def _start_local_process(self, info: InstanceInfo) -> bool:
        """
        Uruchamia instancję jako lokalny proces (dla testów).

        Args:
            info: Informacje o instancji

        Returns:
            True jeśli pomyślnie uruchomiono

        Note:
            TODO (Task 021 - Phase 2): Pełna implementacja uruchamiania lokalnego procesu wymaga:
            - Subprocess management z asyncio
            - Port configuration przez env vars
            - Health monitoring i restart logic
            - Process cleanup przy shutdown
            Na razie zwraca False - funkcjonalność planowana do Phase 2.
        """
        logger.info(f"Uruchamianie instancji {info.instance_id} jako lokalny proces")

        # Placeholder: Pełna implementacja w Phase 2
        logger.warning(
            "Uruchamianie lokalnego procesu nie jest jeszcze zaimplementowane (Phase 2)"
        )
        return False

    async def verify_instance(
        self, instance_id: str, timeout: int = 30
    ) -> tuple[bool, str]:
        """
        Weryfikuje czy instancja lustrzana działa poprawnie.

        Sprawdza:
        1. Health endpoint (/healthz)
        2. Podstawowe API
        3. Czy instancja odpowiada

        Args:
            instance_id: ID instancji do weryfikacji
            timeout: Maksymalny czas oczekiwania w sekundach

        Returns:
            Krotka (sukces, komunikat)
        """
        if instance_id not in self.instances:
            return False, f"Instancja {instance_id} nie istnieje"

        info = self.instances[instance_id]
        logger.info(f"Weryfikacja instancji {instance_id} na porcie {info.port}")

        # URL do instancji
        base_url = f"http://localhost:{info.port}"

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                # 1. Sprawdź health endpoint
                try:
                    response = await client.get(f"{base_url}/healthz")
                    if response.status_code != 200:
                        return (
                            False,
                            f"Health check failed: status {response.status_code}",
                        )

                    health_data = response.json()
                    logger.info(f"Health check OK: {health_data}")

                except httpx.ConnectError:
                    return False, "Nie można połączyć się z instancją (connect error)"
                except httpx.TimeoutException:
                    return False, "Timeout podczas łączenia z instancją"

                # 2. Sprawdź czy instancja odpowiada jako Shadow
                # (możemy dodać specjalny header lub endpoint dla Shadow)
                try:
                    response = await client.get(f"{base_url}/api/v1/metrics")
                    if response.status_code == 200:
                        logger.info("Metrics endpoint OK")
                except Exception as e:
                    logger.warning(f"Metrics endpoint niedostępny: {e}")

                return True, "Instancja działa poprawnie"

        except Exception as e:
            error_msg = f"Błąd podczas weryfikacji instancji: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    async def destroy_instance(self, instance_id: str, cleanup: bool = True) -> bool:
        """
        Zatrzymuje i usuwa instancję lustrzaną.

        Args:
            instance_id: ID instancji do usunięcia
            cleanup: Czy usunąć pliki (domyślnie True)

        Returns:
            True jeśli usunięto pomyślnie
        """
        if instance_id not in self.instances:
            logger.warning(f"Instancja {instance_id} nie istnieje")
            return False

        info = self.instances[instance_id]
        logger.info(f"Usuwanie instancji lustrzanej: {instance_id}")

        try:
            # 1. Zatrzymaj kontener jeśli istnieje
            if info.container_name:
                # TODO: Zatrzymanie kontenera Docker
                logger.info(f"Zatrzymywanie kontenera {info.container_name}")

            # 2. Usuń pliki jeśli cleanup=True
            if cleanup:
                instance_dir = info.workspace_path.parent
                if instance_dir.exists():
                    logger.info(f"Usuwanie katalogu {instance_dir}")
                    shutil.rmtree(instance_dir)

            # 3. Usuń z rejestru
            del self.instances[instance_id]

            logger.info(f"✅ Instancja {instance_id} usunięta")
            return True

        except Exception as e:
            logger.error(f"Błąd podczas usuwania instancji: {e}", exc_info=True)
            return False

    def get_instance_info(self, instance_id: str) -> Optional[InstanceInfo]:
        """
        Pobiera informacje o instancji.

        Args:
            instance_id: ID instancji

        Returns:
            InstanceInfo lub None jeśli instancja nie istnieje
        """
        return self.instances.get(instance_id)

    def list_instances(self) -> list[InstanceInfo]:
        """
        Zwraca listę wszystkich instancji lustrzanych.

        Returns:
            Lista instancji
        """
        return list(self.instances.values())

    async def cleanup_all(self) -> int:
        """
        Usuwa wszystkie instancje lustrzane.

        Returns:
            Liczba usuniętych instancji
        """
        logger.info("Czyszczenie wszystkich instancji lustrzanych")
        count = 0

        # Kopiuj listę kluczy, bo będziemy modyfikować dict
        instance_ids = list(self.instances.keys())

        for instance_id in instance_ids:
            if await self.destroy_instance(instance_id, cleanup=True):
                count += 1

        logger.info(f"Usunięto {count} instancji lustrzanych")
        return count
