"""Moduł: chronos - Silnik Zarządzania Stanem i Linii Czasowych (The Chronomancer)."""

import json
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from venom_core.config import SETTINGS
from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class Checkpoint:
    """
    Reprezentacja punktu przywracania (snapshot) stanu systemu.
    """

    def __init__(
        self,
        checkpoint_id: str,
        name: str,
        timestamp: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicjalizacja checkpointu.

        Args:
            checkpoint_id: Unikalny identyfikator checkpointu
            name: Nazwa checkpointu (user-friendly)
            timestamp: Timestamp utworzenia
            description: Opcjonalny opis
            metadata: Dodatkowe metadane
        """
        self.checkpoint_id = checkpoint_id
        self.name = name
        self.timestamp = timestamp
        self.description = description
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje checkpoint do słownika."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "name": self.name,
            "timestamp": self.timestamp,
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        """Tworzy checkpoint ze słownika."""
        return cls(
            checkpoint_id=data["checkpoint_id"],
            name=data["name"],
            timestamp=data["timestamp"],
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
        )


class ChronosEngine:
    """
    Silnik Zarządzania Czasem - zarządza migawkami stanu całego systemu.

    Odpowiada za:
    - Tworzenie snapshotów (kod + pamięć + konfiguracja)
    - Przywracanie stanu do poprzedniego punktu
    - Zarządzanie liniami czasu (branches)
    """

    def __init__(
        self,
        timelines_dir: Optional[str] = None,
        workspace_root: Optional[str] = None,
        memory_root: Optional[str] = None,
    ):
        """
        Inicjalizacja ChronosEngine.

        Args:
            timelines_dir: Katalog główny dla snapshotów (domyślnie ./data/timelines)
            workspace_root: Katalog workspace projektu
            memory_root: Katalog pamięci (bazy danych)
        """
        self.timelines_dir = Path(timelines_dir or "./data/timelines").resolve()
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.memory_root = Path(memory_root or SETTINGS.MEMORY_ROOT).resolve()

        # Utwórz katalog główny dla snapshotów
        self.timelines_dir.mkdir(parents=True, exist_ok=True)

        # Katalog dla głównej linii czasu
        self.main_timeline = self.timelines_dir / "main"
        self.main_timeline.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"ChronosEngine zainicjalizowany: timelines={self.timelines_dir}, "
            f"workspace={self.workspace_root}, memory={self.memory_root}"
        )

    def create_checkpoint(
        self, name: str, description: str = "", timeline: str = "main"
    ) -> str:
        """
        Tworzy snapshot całego stanu systemu.

        Args:
            name: Nazwa checkpointu (user-friendly)
            description: Opcjonalny opis checkpointu
            timeline: Nazwa linii czasowej (domyślnie "main")

        Returns:
            ID utworzonego checkpointu
        """
        checkpoint_id = str(uuid.uuid4())[:8]
        timestamp = get_utc_now_iso()

        logger.info(
            f"Tworzenie checkpointu '{name}' (ID: {checkpoint_id}) na timeline: {timeline}"
        )

        # Ścieżka do katalogu checkpointu
        timeline_path = self.timelines_dir / timeline
        timeline_path.mkdir(parents=True, exist_ok=True)
        checkpoint_dir = timeline_path / checkpoint_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Zapisz różnice w systemie plików (Git diff/patch)
            self._save_fs_diff(checkpoint_dir)

            # 2. Backup pamięci (bazy danych)
            self._backup_memory(checkpoint_dir)

            # 3. Zapisz konfigurację środowiska
            self._save_env_config(checkpoint_dir)

            # 4. Zapisz metadane checkpointu
            checkpoint = Checkpoint(
                checkpoint_id=checkpoint_id,
                name=name,
                timestamp=timestamp,
                description=description,
                metadata={
                    "timeline": timeline,
                    "workspace_root": str(self.workspace_root),
                    "memory_root": str(self.memory_root),
                },
            )
            self._save_checkpoint_metadata(checkpoint_dir, checkpoint)

            logger.info(f"Checkpoint '{name}' utworzony pomyślnie: {checkpoint_id}")
            return checkpoint_id

        except Exception as e:
            logger.error(f"Błąd podczas tworzenia checkpointu: {e}")
            # Cleanup w przypadku błędu
            if checkpoint_dir.exists():
                shutil.rmtree(checkpoint_dir)
            raise

    def restore_checkpoint(self, checkpoint_id: str, timeline: str = "main") -> bool:
        """
        Przywraca system do stanu z checkpointu.

        Args:
            checkpoint_id: ID checkpointu do przywrócenia
            timeline: Nazwa linii czasowej

        Returns:
            True jeśli przywracanie się powiodło, False w przeciwnym razie
        """
        logger.info(f"Przywracanie checkpointu {checkpoint_id} z timeline: {timeline}")

        checkpoint_dir = self.timelines_dir / timeline / checkpoint_id
        if not checkpoint_dir.exists():
            logger.error(f"Checkpoint {checkpoint_id} nie istnieje")
            return False

        try:
            # 1. Przywróć różnice w systemie plików
            self._restore_fs_diff(checkpoint_dir)

            # 2. Przywróć pamięć
            self._restore_memory(checkpoint_dir)

            # 3. Przywróć konfigurację środowiska
            self._restore_env_config(checkpoint_dir)

            logger.info(f"Checkpoint {checkpoint_id} przywrócony pomyślnie")
            return True

        except Exception as e:
            logger.error(f"Błąd podczas przywracania checkpointu: {e}")
            return False

    def list_checkpoints(self, timeline: str = "main") -> List[Checkpoint]:
        """
        Zwraca listę wszystkich checkpointów dla danej linii czasowej.

        Args:
            timeline: Nazwa linii czasowej

        Returns:
            Lista obiektów Checkpoint
        """
        timeline_path = self.timelines_dir / timeline
        if not timeline_path.exists():
            return []

        checkpoints: List[Tuple[Checkpoint, int]] = []
        for checkpoint_dir in timeline_path.iterdir():
            if not checkpoint_dir.is_dir():
                continue
            checkpoint_entry = self._load_checkpoint_entry(checkpoint_dir)
            if checkpoint_entry is not None:
                checkpoints.append(checkpoint_entry)

        # Sortuj po timestamp (od najnowszych), z fallbackiem na mtime
        checkpoints.sort(
            key=lambda item: self._safe_checkpoint_sort_key(item[0].timestamp, item[1]),
            reverse=True,
        )
        return [checkpoint for checkpoint, _ in checkpoints]

    def _load_checkpoint_entry(
        self, checkpoint_dir: Path
    ) -> Optional[Tuple[Checkpoint, int]]:
        """Ładuje pojedynczy wpis checkpointu i mtime katalogu."""
        metadata_file = checkpoint_dir / "checkpoint.json"
        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file, "r", encoding="utf-8") as handle:
                checkpoint = Checkpoint.from_dict(json.load(handle))
        except Exception as error:
            logger.warning(
                f"Błąd odczytu metadanych checkpointu {checkpoint_dir.name}: {error}"
            )
            return None

        try:
            mtime_ns = checkpoint_dir.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0
        return checkpoint, mtime_ns

    @staticmethod
    def _safe_checkpoint_sort_key(
        timestamp: str, mtime_ns: int
    ) -> Tuple[datetime, int]:
        """Buduje stabilny klucz sortowania checkpointu."""
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            parsed = datetime.min
        return parsed, mtime_ns

    def delete_checkpoint(self, checkpoint_id: str, timeline: str = "main") -> bool:
        """
        Usuwa checkpoint.

        Args:
            checkpoint_id: ID checkpointu do usunięcia
            timeline: Nazwa linii czasowej

        Returns:
            True jeśli usunięcie się powiodło
        """
        checkpoint_dir = self.timelines_dir / timeline / checkpoint_id
        if not checkpoint_dir.exists():
            logger.error(f"Checkpoint {checkpoint_id} nie istnieje")
            return False

        try:
            shutil.rmtree(checkpoint_dir)
            logger.info(f"Checkpoint {checkpoint_id} usunięty")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania checkpointu: {e}")
            return False

    def list_timelines(self) -> List[str]:
        """
        Zwraca listę wszystkich dostępnych linii czasowych.

        Returns:
            Lista nazw linii czasowych
        """
        timelines = []
        for item in self.timelines_dir.iterdir():
            if item.is_dir():
                timelines.append(item.name)
        return sorted(timelines)

    def create_timeline(self, name: str) -> bool:
        """
        Tworzy nową linię czasową (branch).

        Args:
            name: Nazwa nowej linii czasowej

        Returns:
            True jeśli utworzono pomyślnie
        """
        timeline_path = self.timelines_dir / name
        if timeline_path.exists():
            logger.warning(f"Timeline '{name}' już istnieje")
            return False

        try:
            timeline_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Timeline '{name}' utworzona")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia timeline: {e}")
            return False

    # --- Metody pomocnicze ---

    def _save_fs_diff(self, checkpoint_dir: Path) -> None:
        """Zapisuje różnice w systemie plików (Git diff)."""
        try:
            # Sprawdź status Git
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=30,
            )

            diff_file = checkpoint_dir / "fs_diff.patch"
            with open(diff_file, "w", encoding="utf-8") as f:
                f.write(result.stdout)

            # Zapisz też info o uncommitted files
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=30,
            )

            status_file = checkpoint_dir / "git_status.txt"
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(status_result.stdout)

            logger.debug(f"Diff zapisany: {diff_file}")

        except Exception as e:
            logger.warning(f"Nie można zapisać Git diff: {e}")
            # Nie przerywamy procesu - to nie jest krytyczne

    def _restore_fs_diff(self, checkpoint_dir: Path) -> None:
        """Przywraca różnice w systemie plików."""
        diff_file = checkpoint_dir / "fs_diff.patch"
        if not diff_file.exists() or diff_file.stat().st_size == 0:
            logger.debug("Brak zmian do przywrócenia (pusty diff)")
            return

        try:
            # Sprawdź czy mamy nieucommitowane zmiany
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if status_result.stdout.strip():
                logger.warning(
                    "UWAGA: Wykryto nieucommitowane zmiany. Zostaną one nadpisane podczas przywracania."
                )
                logger.warning(f"Nieucommitowane pliki:\n{status_result.stdout[:500]}")

            # Zresetuj do czystego stanu
            subprocess.run(
                ["git", "reset", "--hard", "HEAD"],
                cwd=self.workspace_root,
                check=True,
                timeout=30,
                capture_output=True,
            )

            # Zastosuj patch
            subprocess.run(
                ["git", "apply", str(diff_file)],
                cwd=self.workspace_root,
                check=True,
                timeout=30,
                capture_output=True,
            )

            logger.debug("Diff przywrócony")

        except subprocess.CalledProcessError as e:
            logger.error(
                f"Błąd Git podczas przywracania diff: {e}\n"
                f"Stdout: {e.stdout}\n"
                f"Stderr: {e.stderr}"
            )
            raise RuntimeError(
                "Nie udało się przywrócić diff. Upewnij się, że katalog workspace jest repozytorium Git."
            ) from e
        except FileNotFoundError:
            logger.error("Git nie jest zainstalowany lub niedostępny w PATH")
            raise RuntimeError(
                "Git jest wymagany do przywracania checkpointów"
            ) from None

    def _backup_memory(self, checkpoint_dir: Path) -> None:
        """Tworzy backup baz danych pamięci."""
        if not self.memory_root.exists():
            logger.debug("Katalog pamięci nie istnieje - pomijam backup")
            return

        try:
            memory_backup = checkpoint_dir / "memory_dump"
            memory_backup.mkdir(exist_ok=True)

            # Kopiuj zawartość katalogu pamięci
            for item in self.memory_root.iterdir():
                if item.is_file():
                    shutil.copy2(item, memory_backup / item.name)
                elif item.is_dir() and not item.name.startswith("."):
                    # Kopiuj katalogi (np. LanceDB)
                    shutil.copytree(item, memory_backup / item.name, dirs_exist_ok=True)

            logger.debug(f"Backup pamięci zapisany: {memory_backup}")

        except Exception as e:
            logger.warning(f"Błąd podczas backupu pamięci: {e}")

    def _copy_memory_items(self, source_dir: Path, target_dir: Path) -> None:
        for item in source_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, target_dir / item.name)
            elif item.is_dir():
                shutil.copytree(item, target_dir / item.name, dirs_exist_ok=True)

    def _restore_memory_from_backup(self, memory_backup: Path) -> None:
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self._copy_memory_items(memory_backup, self.memory_root)

    def _rollback_memory_restore(
        self, temp_backup: Path, restore_error: Exception
    ) -> None:
        logger.error(f"Błąd podczas przywracania pamięci: {restore_error}")
        logger.info("Przywracam z tymczasowego backupu...")
        if self.memory_root.exists():
            shutil.rmtree(self.memory_root)
        shutil.copytree(temp_backup, self.memory_root)
        shutil.rmtree(temp_backup)
        raise RuntimeError(
            "Nie udało się przywrócić pamięci, przywrócono poprzedni stan"
        ) from restore_error

    def _restore_with_temp_backup(self, memory_backup: Path, temp_backup: Path) -> None:
        try:
            shutil.rmtree(self.memory_root)
            self._restore_memory_from_backup(memory_backup)
            shutil.rmtree(temp_backup)
            logger.debug("Pamięć przywrócona pomyślnie")
        except Exception as restore_error:
            self._rollback_memory_restore(temp_backup, restore_error)

    def _restore_memory(self, checkpoint_dir: Path) -> None:
        """Przywraca bazy danych pamięci."""
        memory_backup = checkpoint_dir / "memory_dump"
        if not memory_backup.exists():
            logger.debug("Brak backupu pamięci do przywrócenia")
            return

        try:
            # Utwórz backup obecnego stanu przed nadpisaniem
            if self.memory_root.exists():
                temp_backup = (
                    self.memory_root.parent
                    / f"memory_backup_temp_{uuid.uuid4().hex[:8]}"
                )
                logger.debug(f"Tworzę tymczasowy backup: {temp_backup}")
                shutil.copytree(self.memory_root, temp_backup)
                self._restore_with_temp_backup(memory_backup, temp_backup)
            else:
                # Brak obecnego stanu - po prostu przywróć
                self._restore_memory_from_backup(memory_backup)
                logger.debug("Pamięć przywrócona")

        except Exception as e:
            logger.error(f"Błąd podczas przywracania pamięci: {e}")
            raise

    def _save_env_config(self, checkpoint_dir: Path) -> None:
        """Zapisuje konfigurację środowiska."""
        try:
            # Zapisz istotne zmienne środowiskowe
            env_config = {
                "timestamp": get_utc_now_iso(),
                "settings": {
                    "WORKSPACE_ROOT": str(self.workspace_root),
                    "MEMORY_ROOT": str(self.memory_root),
                    "ENV": SETTINGS.ENV,
                    "LLM_SERVICE_TYPE": SETTINGS.LLM_SERVICE_TYPE,
                    "LLM_MODEL_NAME": SETTINGS.LLM_MODEL_NAME,
                    "ENABLE_SANDBOX": SETTINGS.ENABLE_SANDBOX,
                },
            }

            config_file = checkpoint_dir / "env_config.json"
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(env_config, f, indent=2)

            logger.debug(f"Konfiguracja środowiska zapisana: {config_file}")

        except Exception as e:
            logger.warning(f"Błąd podczas zapisywania konfiguracji: {e}")

    def _restore_env_config(self, checkpoint_dir: Path) -> None:
        """Przywraca konfigurację środowiska (informacyjne)."""
        config_file = checkpoint_dir / "env_config.json"
        if not config_file.exists():
            logger.debug("Brak konfiguracji środowiska do przywrócenia")
            return

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                env_config = json.load(f)

            logger.info("Konfiguracja środowiska z checkpointu:")
            logger.info(json.dumps(env_config.get("settings", {}), indent=2))
            logger.warning(
                "UWAGA: Przywracanie zmiennych środowiskowych wymaga restartu systemu"
            )

        except Exception as e:
            logger.warning(f"Błąd podczas odczytu konfiguracji: {e}")

    def _save_checkpoint_metadata(
        self, checkpoint_dir: Path, checkpoint: Checkpoint
    ) -> None:
        """Zapisuje metadane checkpointu."""
        metadata_file = checkpoint_dir / "checkpoint.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)
