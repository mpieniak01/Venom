"""Moduł: state_manager - zarządzanie stanem zadań."""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

from venom_core.core.models import TaskStatus, VenomTask
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class StateManager:
    """Zarządzanie stanem zadań w pamięci z persystencją do pliku."""

    def __init__(self, state_file_path: str = "data/memory/state_dump.json"):
        """
        Inicjalizacja StateManager.

        Args:
            state_file_path: Ścieżka do pliku z zapisem stanu
        """
        self._tasks: Dict[UUID, VenomTask] = {}
        self._state_file_path = Path(state_file_path)
        self._save_lock = asyncio.Lock()

        # Upewnij się, że katalog istnieje
        self._state_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Załaduj stan z pliku jeśli istnieje
        self._load_state()

    def _load_state(self) -> None:
        """Ładuje stan z pliku JSON."""
        if not self._state_file_path.exists():
            logger.info(
                f"Plik stanu nie istnieje: {self._state_file_path}. Rozpoczynanie z pustym stanem."
            )
            return

        try:
            with open(self._state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for task_dict in data.get("tasks", []):
                task = VenomTask(**task_dict)
                self._tasks[task.id] = task

            logger.info(
                f"Załadowano {len(self._tasks)} zadań z pliku {self._state_file_path}"
            )
        except json.JSONDecodeError as e:
            logger.error(
                f"Błąd parsowania pliku stanu: {e}. Rozpoczynanie z pustym stanem."
            )
        except Exception as e:
            logger.error(f"Błąd ładowania stanu: {e}. Rozpoczynanie z pustym stanem.")

    async def _save(self) -> None:
        """Zapisuje stan do pliku JSON (asynchronicznie z lockiem)."""
        async with self._save_lock:
            try:
                # Serializuj zadania
                tasks_list = [
                    task.model_dump(mode="json") for task in self._tasks.values()
                ]
                data = {"tasks": tasks_list}

                # Zapisz do pliku
                with open(self._state_file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, default=str)

                logger.debug(f"Stan zapisany do {self._state_file_path}")
            except Exception as e:
                logger.error(f"Błąd zapisu stanu do pliku: {e}")

    def _schedule_save(self) -> None:
        """Planuje zapis stanu, obsługując brak event loop."""
        try:
            # Próbuj uzyskać aktywny event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._save())
            else:
                # Jeśli loop nie działa, uruchom synchronicznie
                loop.run_until_complete(self._save())
        except RuntimeError:
            # Jeśli nie ma event loop (np. w testach sync), pomiń zapis
            logger.debug("Brak event loop - pomijam automatyczny zapis stanu")

    def create_task(self, content: str) -> VenomTask:
        """
        Tworzy nowe zadanie.

        Args:
            content: Treść zadania

        Returns:
            Utworzone zadanie
        """
        task = VenomTask(content=content)
        self._tasks[task.id] = task
        logger.info(f"Utworzono zadanie {task.id} ze statusem {task.status}")

        # Zapisz stan asynchronicznie
        self._schedule_save()

        return task

    def get_task(self, task_id: UUID) -> Optional[VenomTask]:
        """
        Pobiera zadanie po ID.

        Args:
            task_id: ID zadania

        Returns:
            Zadanie lub None jeśli nie istnieje
        """
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[VenomTask]:
        """
        Pobiera wszystkie zadania.

        Returns:
            Lista wszystkich zadań
        """
        return list(self._tasks.values())

    async def update_status(
        self, task_id: UUID, status: TaskStatus, result: Optional[str] = None
    ) -> None:
        """
        Aktualizuje status zadania.

        Args:
            task_id: ID zadania
            status: Nowy status
            result: Opcjonalny wynik zadania
        """
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(f"Próba aktualizacji nieistniejącego zadania: {task_id}")
            return

        task.status = status
        if result is not None:
            task.result = result

        logger.info(f"Zaktualizowano zadanie {task_id} do statusu {status}")

        # Zapisz stan
        await self._save()

    def add_log(self, task_id: UUID, log_message: str) -> None:
        """
        Dodaje wpis do logów zadania.

        Args:
            task_id: ID zadania
            log_message: Wiadomość do dodania
        """
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(f"Próba dodania logu do nieistniejącego zadania: {task_id}")
            return

        task.logs.append(log_message)
        self._schedule_save()
