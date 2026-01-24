"""Moduł: docker_habitat - Zarządca bezpiecznego środowiska wykonawczego (Docker Sandbox)."""

import importlib
from pathlib import Path
from typing import Any

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

docker: Any = None
try:  # pragma: no cover - zależne od środowiska
    docker = importlib.import_module("docker")
    docker_errors = importlib.import_module("docker.errors")
    APIError = docker_errors.APIError
    ImageNotFound = docker_errors.ImageNotFound
    NotFound = docker_errors.NotFound
except Exception:  # pragma: no cover
    docker = None
    APIError = Exception
    ImageNotFound = Exception
    NotFound = Exception

logger = get_logger(__name__)


class DockerHabitat:
    """
    Zarządca siedliska Docker - bezpieczne środowisko uruchomieniowe dla Venoma.

    Zarządza jednym długożyjącym kontenerem Docker (`venom-sandbox`),
    w którym Venom uruchamia i testuje kod. Kontener montuje workspace
    jako volume, umożliwiając dostęp do plików między hostem a kontenerem.
    """

    CONTAINER_NAME = "venom-sandbox"

    def __init__(self):
        """
        Inicjalizacja DockerHabitat.

        Sprawdza czy kontener już istnieje. Jeśli tak i działa - podłącza się.
        Jeśli nie istnieje - tworzy i uruchamia nowy.

        Raises:
            RuntimeError: Jeśli Docker nie jest dostępny lub nie można uruchomić kontenera
        """
        if docker is None:
            error_msg = "Docker SDK nie jest dostępny"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        try:
            self.client = docker.from_env()
            logger.info("Połączono z Docker daemon")
        except Exception as e:
            error_msg = f"Nie można połączyć się z Docker daemon: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

        self.container = self._get_or_create_container()
        logger.info(
            f"DockerHabitat zainicjalizowany z kontenerem: {self.CONTAINER_NAME}"
        )

    def _get_or_create_container(self):
        """
        Pobiera istniejący kontener lub tworzy nowy.

        Returns:
            docker.models.containers.Container: Kontener Docker

        Raises:
            RuntimeError: Jeśli nie można utworzyć/uruchomić kontenera
        """
        try:
            # Sprawdź czy kontener już istnieje
            container = self.client.containers.get(self.CONTAINER_NAME)
            logger.info(f"Znaleziono istniejący kontener: {self.CONTAINER_NAME}")

            # Jeśli kontener istnieje ale nie działa, uruchom go
            if container.status != "running":
                logger.info(
                    f"Uruchamianie zatrzymanego kontenera: {self.CONTAINER_NAME}"
                )
                container.start()
                container.reload()

            return container

        except NotFound:
            # Kontener nie istnieje - utwórz nowy
            logger.info(f"Tworzenie nowego kontenera: {self.CONTAINER_NAME}")
            return self._create_container()

    def _create_container(self):
        """
        Tworzy nowy kontener Docker.

        Returns:
            docker.models.containers.Container: Nowy kontener Docker

        Raises:
            RuntimeError: Jeśli nie można utworzyć kontenera
        """
        try:
            # Pobierz obraz jeśli nie istnieje
            image_name = SETTINGS.DOCKER_IMAGE_NAME
            try:
                self.client.images.get(image_name)
                logger.info(f"Obraz {image_name} już istnieje")
            except ImageNotFound:
                logger.info(f"Pobieranie obrazu {image_name}...")
                self.client.images.pull(image_name)

            # Przygotuj ścieżkę workspace jako bezwzględną
            workspace_path = Path(SETTINGS.WORKSPACE_ROOT).resolve()
            workspace_path.mkdir(parents=True, exist_ok=True)

            # Utwórz kontener
            container = self.client.containers.run(
                image=image_name,
                name=self.CONTAINER_NAME,
                command="tail -f /dev/null",  # Utrzymuje kontener w działaniu
                volumes={str(workspace_path): {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                detach=True,
                remove=False,  # Nie usuwaj kontenera po zatrzymaniu
            )

            # Odśwież status kontenera
            container.reload()

            logger.info(
                f"Utworzono kontener {self.CONTAINER_NAME} z volume: {workspace_path} -> /workspace"
            )
            return container

        except APIError as e:
            error_msg = f"Błąd API Docker podczas tworzenia kontenera: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"Nieoczekiwany błąd podczas tworzenia kontenera: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def execute(self, command: str, timeout: int = 30) -> tuple[int, str]:
        """
        Wykonuje komendę w kontenerze Docker.

        Args:
            command: Komenda do wykonania (np. "python script.py")
            timeout: Maksymalny czas wykonania w sekundach (domyślnie 30)
                    Uwaga: Obecnie timeout nie jest implementowany - parametr jest
                    zachowany dla kompatybilności z przyszłymi wersjami

        Returns:
            Krotka (exit_code, output) gdzie:
            - exit_code: Kod wyjścia komendy (0 = sukces)
            - output: Połączony stdout i stderr

        Raises:
            RuntimeError: Jeśli kontener nie działa lub komenda się nie powiodła
        """
        try:
            # Sprawdź czy kontener działa
            self.container.reload()
            if self.container.status != "running":
                error_msg = f"Kontener {self.CONTAINER_NAME} nie działa (status: {self.container.status})"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            logger.info(f"Wykonywanie komendy w kontenerze: {command[:100]}")

            # Wykonaj komendę
            exec_result = self.container.exec_run(
                cmd=command,
                workdir="/workspace",
                demux=False,  # Połącz stdout i stderr
            )

            exit_code = exec_result.exit_code
            output = exec_result.output.decode("utf-8") if exec_result.output else ""

            logger.info(f"Komenda zakończona z kodem: {exit_code}")
            if exit_code != 0:
                logger.warning(f"Output błędu: {output[:200]}")

            return exit_code, output

        except Exception as e:
            error_msg = f"Błąd podczas wykonywania komendy: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def cleanup(self):
        """
        Zatrzymuje i usuwa kontener.

        Użyj tej metody, gdy chcesz całkowicie wyczyścić środowisko.
        """
        try:
            if self.container:
                logger.info(f"Zatrzymywanie kontenera: {self.CONTAINER_NAME}")
                self.container.stop()
                logger.info(f"Usuwanie kontenera: {self.CONTAINER_NAME}")
                self.container.remove()
                logger.info("Kontener został usunięty")
        except Exception as e:
            logger.warning(f"Błąd podczas czyszczenia kontenera: {e}")

    def __del__(self):
        """Destruktor - nie usuwa kontenera automatycznie (długożyjący kontener)."""
        # Nie wywołujemy cleanup() tutaj - kontener powinien zostać
