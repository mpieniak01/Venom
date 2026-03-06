"""Moduł: docker_habitat - Zarządca bezpiecznego środowiska wykonawczego (Docker Sandbox)."""

import hashlib
import importlib
import time
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
CONTAINER_WORKDIR = "/workspace"
DEFAULT_WORKSPACE_ROOT = Path(SETTINGS.WORKSPACE_ROOT).resolve()


class DockerHabitat:
    """
    Zarządca siedliska Docker - bezpieczne środowisko uruchomieniowe dla Venoma.

    Zarządza długożyjącym kontenerem Docker (`venom-sandbox`),
    w którym Venom uruchamia i testuje kod. Kontener montuje workspace
    jako volume, umożliwiając dostęp do plików między hostem a kontenerem.
    """

    CONTAINER_NAME = "venom-sandbox"
    CONTAINER_REMOVE_WAIT_SECONDS = 30.0
    CONTAINER_REMOVE_POLL_SECONDS = 0.5
    CONTAINER_CONFLICT_RETRIES = 3

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

        self.workspace_path = self._resolve_workspace_path()
        self.container_name = self._resolve_container_name(self.workspace_path)
        self.container = self._get_or_create_container()
        logger.info(
            f"DockerHabitat zainicjalizowany z kontenerem: {self._active_container_name()}"
        )

    def _active_container_name(self) -> str:
        return getattr(self, "container_name", self.CONTAINER_NAME)

    def _resolve_container_name(self, workspace_path: Path) -> str:
        """
        Zwraca nazwę kontenera.
        Dla domyślnego workspace zachowujemy historyczną nazwę `venom-sandbox`,
        a dla innych workspace dodajemy stabilny suffix, aby uniknąć konfliktów
        między równoległymi testami/workerami.
        """
        if workspace_path.resolve() == DEFAULT_WORKSPACE_ROOT:
            return self.CONTAINER_NAME
        workspace_hash = hashlib.sha256(
            str(workspace_path.resolve()).encode("utf-8")
        ).hexdigest()[:12]
        return f"{self.CONTAINER_NAME}-{workspace_hash}"

    def _get_or_create_container(self):
        """
        Pobiera istniejący kontener lub tworzy nowy.

        Returns:
            docker.models.containers.Container: Kontener Docker

        Raises:
            RuntimeError: Jeśli nie można utworzyć/uruchomić kontenera
        """
        container_name = self._active_container_name()
        try:
            # Sprawdź czy kontener już istnieje
            container = self.client.containers.get(container_name)
            logger.info(f"Znaleziono istniejący kontener: {container_name}")

            expected_workspace = getattr(
                self, "workspace_path", self._resolve_workspace_path()
            )
            if not self._has_expected_workspace_mount(container, expected_workspace):
                logger.warning(
                    "Istniejący kontener ma niezgodny mount workspace "
                    f"(oczekiwano: {expected_workspace}). Rekreacja kontenera."
                )
                self._recreate_container(container)
                return self._create_container(expected_workspace)

            # Jeśli kontener istnieje ale nie działa, uruchom go
            if container.status != "running":
                logger.info(f"Uruchamianie zatrzymanego kontenera: {container_name}")
                try:
                    container.start()
                    container.reload()
                except APIError as exc:
                    if self._is_name_conflict_error(exc):
                        logger.warning(
                            "Nie można uruchomić kontenera %s (%s). Rekreacja.",
                            container_name,
                            exc,
                        )
                        self._recreate_container(container)
                        return self._create_container(expected_workspace)
                    raise

            return container

        except NotFound:
            # Kontener nie istnieje - utwórz nowy
            logger.info(f"Tworzenie nowego kontenera: {container_name}")
            return self._create_container()

    def _resolve_workspace_path(self) -> Path:
        """Zwraca bezwzględną ścieżkę workspace i upewnia się, że katalog istnieje."""
        workspace_path = Path(SETTINGS.WORKSPACE_ROOT).resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)
        return workspace_path

    def _resolve_effective_workspace_path(
        self, workspace_path: Path | None = None
    ) -> Path:
        """Zwraca obowiązującą ścieżkę workspace jako `Path`."""
        if workspace_path is not None:
            return workspace_path
        current_workspace = getattr(self, "workspace_path", None)
        if isinstance(current_workspace, Path):
            return current_workspace
        resolved_workspace = self._resolve_workspace_path()
        self.workspace_path = resolved_workspace
        return resolved_workspace

    def _container_workspace_mount(self, container) -> Path | None:
        """Zwraca hostową ścieżkę bind mounta dla `/workspace` (jeśli istnieje)."""
        container.reload()
        for mount in container.attrs.get("Mounts", []):
            if mount.get("Destination") == CONTAINER_WORKDIR and mount.get("Source"):
                return Path(mount["Source"]).resolve()
        return None

    def _has_expected_workspace_mount(
        self, container, expected_workspace: Path
    ) -> bool:
        """Sprawdza, czy kontener używa oczekiwanego bind mounta workspace."""
        actual_mount = self._container_workspace_mount(container)
        if actual_mount is None:
            return False
        return actual_mount == expected_workspace.resolve()

    def _recreate_container(self, container) -> None:
        """Usuwa istniejący kontener, aby utworzyć go ponownie z poprawnym mountem."""
        try:
            container.reload()
            if container.status == "running":
                container.stop()
        except Exception as exc:
            logger.warning(f"Nie udało się zatrzymać kontenera przed rekreacją: {exc}")
        try:
            container.remove(force=True)
        except Exception as exc:
            logger.warning(f"Nie udało się usunąć kontenera przed rekreacją: {exc}")
        # Domknij ewentualny race-condition na nazwie kontenera.
        self._remove_container_by_name_if_exists()

    def _remove_container_by_name_if_exists(self) -> None:
        """Usuwa kontenery konfliktujące po nazwie i czeka na zwolnienie nazwy."""
        container_name = self._active_container_name()
        try:
            existing = self.client.containers.get(container_name)
        except NotFound:
            existing = None
        if existing is not None:
            try:
                existing.remove(force=True)
            except Exception as exc:
                logger.warning(
                    f"Nie udało się usunąć kontenera {container_name}: {exc}"
                )

        # Domknij przypadki, gdzie API get() zwraca chwilowo NotFound,
        # ale nazwa pozostaje zablokowana przez osierocony/dead kontener.
        self._remove_conflicting_named_containers()
        self._wait_until_container_absent()

    def _remove_conflicting_named_containers(self) -> None:
        """Usuwa wszystkie kontenery dokładnie pasujące do CONTAINER_NAME."""
        container_name = self._active_container_name()
        list_fn = getattr(self.client.containers, "list", None)
        if list_fn is None:
            return

        try:
            candidates = list_fn(all=True, filters={"name": container_name})
        except Exception as exc:
            logger.warning(
                f"Nie udało się pobrać listy kontenerów konfliktowych: {exc}"
            )
            return

        for candidate in candidates:
            if not self._is_exact_container_name_match(candidate):
                continue
            try:
                candidate.remove(force=True)
            except Exception as exc:
                logger.warning(
                    f"Nie udało się usunąć konfliktowego kontenera {container_name}: {exc}"
                )

    def _is_exact_container_name_match(self, container: Any) -> bool:
        """Sprawdza, czy kontener ma dokładnie nazwę CONTAINER_NAME."""
        container_name = self._active_container_name()
        name = str(getattr(container, "name", "") or "").strip()
        if name == container_name:
            return True
        try:
            attrs_name = str(container.attrs.get("Name", "") or "").strip()
        except Exception:
            attrs_name = ""
        return attrs_name in {container_name, f"/{container_name}"}

    def _wait_until_container_absent(self) -> None:
        """Czeka aż nazwa kontenera będzie ponownie dostępna."""
        container_name = self._active_container_name()
        deadline = time.time() + self.CONTAINER_REMOVE_WAIT_SECONDS
        while time.time() < deadline:
            try:
                self.client.containers.get(container_name)
                self._remove_conflicting_named_containers()
            except NotFound:
                if not self._has_named_container_candidates():
                    return
            except Exception as exc:
                logger.warning(
                    f"Błąd podczas sprawdzania dostępności nazwy kontenera: {exc}"
                )
            time.sleep(self.CONTAINER_REMOVE_POLL_SECONDS)
        logger.warning(
            "Timeout oczekiwania na zwolnienie nazwy kontenera %s. "
            "Sprawdź `docker ps -a` i usuń konflikt ręcznie, jeśli problem się powtarza.",
            container_name,
        )

    def _has_named_container_candidates(self) -> bool:
        """Zwraca True gdy istnieją kontenery pasujące dokładnie do CONTAINER_NAME."""
        container_name = self._active_container_name()
        list_fn = getattr(self.client.containers, "list", None)
        if list_fn is None:
            return False
        try:
            candidates = list_fn(all=True, filters={"name": container_name})
        except Exception as exc:
            logger.warning(
                f"Nie udało się sprawdzić listy kontenerów podczas oczekiwania: {exc}"
            )
            # Zachowawczo zakładamy, że nazwa może nadal być zajęta.
            return True
        return any(self._is_exact_container_name_match(c) for c in candidates)

    def _create_container(
        self,
        workspace_path: Path | None = None,
        *,
        retry_on_conflict: bool = True,
        conflict_retries_remaining: int | None = None,
    ):
        """
        Tworzy nowy kontener Docker.

        Returns:
            docker.models.containers.Container: Nowy kontener Docker

        Raises:
            RuntimeError: Jeśli nie można utworzyć kontenera
        """
        retries_left = self._resolve_conflict_retries(conflict_retries_remaining)

        try:
            image_name = SETTINGS.DOCKER_IMAGE_NAME
            self._ensure_image_present(image_name)
            workspace_path = self._resolve_effective_workspace_path(workspace_path)
            container = self._run_container(image_name, workspace_path)
            container.reload()
            logger.info(
                f"Utworzono kontener {self._active_container_name()} z volume: {workspace_path} -> {CONTAINER_WORKDIR}"
            )
            return container

        except APIError as e:
            if retry_on_conflict and self._is_name_conflict_error(e):
                return self._recover_from_name_conflict(
                    error=e,
                    workspace_path=workspace_path,
                    retries_left=retries_left,
                )
            error_msg = f"Błąd API Docker podczas tworzenia kontenera: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"Nieoczekiwany błąd podczas tworzenia kontenera: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _resolve_conflict_retries(self, retries: int | None) -> int:
        if retries is None:
            return self.CONTAINER_CONFLICT_RETRIES
        return max(0, int(retries))

    def _ensure_image_present(self, image_name: str) -> None:
        try:
            self.client.images.get(image_name)
            logger.info(f"Obraz {image_name} już istnieje")
        except ImageNotFound:
            logger.info(f"Pobieranie obrazu {image_name}...")
            self.client.images.pull(image_name)

    def _run_container(self, image_name: str, workspace_path: Path):
        return self.client.containers.run(
            image=image_name,
            name=self._active_container_name(),
            command="tail -f /dev/null",
            volumes={str(workspace_path): {"bind": CONTAINER_WORKDIR, "mode": "rw"}},
            working_dir=CONTAINER_WORKDIR,
            detach=True,
            remove=False,
        )

    @staticmethod
    def _is_name_conflict_error(error: Exception) -> bool:
        error_text = str(error).lower()
        status_code = getattr(error, "status_code", None)
        return bool(
            status_code == 409
            or "409 client error" in error_text
            or "already in use" in error_text
            or "conflict" in error_text
        )

    def _recover_from_name_conflict(
        self,
        *,
        error: Exception,
        workspace_path: Path | None,
        retries_left: int,
    ):
        if retries_left <= 0:
            error_msg = (
                f"Błąd API Docker podczas tworzenia kontenera: {error}. "
                "Wyczerpano limit retry dla konfliktu nazwy kontenera."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg) from error

        logger.warning(
            "Konflikt nazwy kontenera %s; próba ponownego użycia "
            "(pozostałe retry: %s).",
            self._active_container_name(),
            retries_left,
        )
        expected_workspace = self._resolve_effective_workspace_path(workspace_path)
        try:
            existing = self.client.containers.get(self._active_container_name())
            if self._has_expected_workspace_mount(existing, expected_workspace):
                if existing.status != "running":
                    existing.start()
                    existing.reload()
                logger.info(
                    "Ponownie użyto istniejącego kontenera po konflikcie nazwy."
                )
                return existing
            logger.warning(
                "Istniejący kontener po konflikcie ma niezgodny mount; rekreacja."
            )
            self._recreate_container(existing)
            return self._create_container(
                expected_workspace,
                retry_on_conflict=True,
                conflict_retries_remaining=retries_left - 1,
            )
        except NotFound:
            logger.warning("Retry po usunięciu kontenera konfliktowego.")
            self._remove_container_by_name_if_exists()
            return self._create_container(
                expected_workspace,
                retry_on_conflict=True,
                conflict_retries_remaining=retries_left - 1,
            )
        except Exception as reuse_exc:
            logger.warning(
                "Nie udało się ponownie użyć kontenera po konflikcie: %s",
                reuse_exc,
            )
            logger.warning("Retry po usunięciu kontenera konfliktowego.")
            self._remove_container_by_name_if_exists()
            return self._create_container(
                expected_workspace,
                retry_on_conflict=True,
                conflict_retries_remaining=retries_left - 1,
            )

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
                error_msg = f"Kontener {self._active_container_name()} nie działa (status: {self.container.status})"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            logger.info(f"Wykonywanie komendy w kontenerze: {command[:100]}")

            # Wykonaj komendę
            exec_result = self.container.exec_run(
                cmd=command,
                workdir=CONTAINER_WORKDIR,
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
                logger.info(f"Zatrzymywanie kontenera: {self._active_container_name()}")
                self.container.stop()
                logger.info(f"Usuwanie kontenera: {self._active_container_name()}")
                self.container.remove()
                logger.info("Kontener został usunięty")
        except Exception as e:
            logger.warning(f"Błąd podczas czyszczenia kontenera: {e}")

    def __del__(self):
        """Destruktor - nie usuwa kontenera automatycznie (długożyjący kontener)."""
        # Nie wywołujemy cleanup() tutaj - kontener powinien zostać
