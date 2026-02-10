"""Moduł: state_manager - zarządzanie stanem zadań."""

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from venom_core.config import SETTINGS
from venom_core.core.models import TaskStatus, VenomTask
from venom_core.utils.boot_id import BOOT_ID
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Maksymalny rozmiar pliku stanu w bajtach (10 MB)
MAX_STATE_FILE_SIZE = 10 * 1024 * 1024
MAX_TASKS = 1000
STATE_META_PATH = Path("./data/memory/state_meta.json")


class StateManager:
    """Zarządzanie stanem zadań w pamięci z persystencją do pliku."""

    def __init__(self, state_file_path: Optional[str] = None):
        """
        Inicjalizacja StateManager.

        Args:
            state_file_path: Ścieżka do pliku z zapisem stanu
        """
        self._tasks: Dict[UUID, VenomTask] = {}
        self._uses_custom_state_file = state_file_path is not None
        settings_path = getattr(SETTINGS, "STATE_FILE_PATH", None)
        resolved_path = state_file_path or (
            settings_path
            if isinstance(settings_path, str) and settings_path
            else "data/memory/state_dump.json"
        )
        self._state_file_path = Path(resolved_path)
        self._save_lock = asyncio.Lock()
        self._save_task: Optional[asyncio.Task] = None
        self._save_requested: bool = False

        # AutonomyGate - poziom autonomii (0, 10, 20, 30, 40)
        self.autonomy_level: int = 0  # Domyślnie ISOLATED

        # Global Cost Guard - flaga płatnego trybu (dla compatibility z TokenEconomist)
        self.paid_mode_enabled: bool = False

        # Upewnij się, że katalog istnieje
        self._state_file_path.parent.mkdir(parents=True, exist_ok=True)

        # boot_id reset dotyczy tylko globalnego pliku runtime.
        # Dla jawnie przekazanych ścieżek (np. testowych) nie czyścimy stanu.
        if not self._uses_custom_state_file:
            self._ensure_boot_id()
        # Załaduj stan z pliku jeśli istnieje
        self._load_state()

    def _ensure_boot_id(self) -> None:
        """Czyści stan po restarcie backendu (zmiana boot_id)."""
        try:
            if STATE_META_PATH.exists():
                payload = json.loads(STATE_META_PATH.read_text(encoding="utf-8"))
                stored_boot = payload.get("boot_id")
                if stored_boot and stored_boot != BOOT_ID:
                    if self._state_file_path.exists():
                        self._state_file_path.unlink(missing_ok=True)
            else:
                STATE_META_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_META_PATH.write_text(
                json.dumps({"boot_id": BOOT_ID}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Nie udało się sprawdzić boot_id stanu: %s", exc)

    def _load_state(self) -> None:
        """Ładuje stan z pliku JSON."""
        if not self._state_file_path.exists():
            logger.info(
                f"Plik stanu nie istnieje: {self._state_file_path}. Rozpoczynanie z pustym stanem."
            )
            return

        try:
            # Sprawdź rozmiar pliku przed ładowaniem
            file_size = self._state_file_path.stat().st_size
            if file_size > MAX_STATE_FILE_SIZE:
                logger.error(
                    f"Plik stanu jest zbyt duży ({file_size} bajtów, maksimum {MAX_STATE_FILE_SIZE}). "
                    f"Rozpoczynanie z pustym stanem."
                )
                return
            if file_size == 0:
                logger.info(
                    f"Plik stanu {self._state_file_path} jest pusty. Rozpoczynanie z pustym stanem."
                )
                return

            with open(self._state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for task_dict in data.get("tasks", []):
                task = VenomTask(**task_dict)
                self._tasks[task.id] = task

            # Przywróć paid_mode_enabled (używane przez testy i API)
            self.paid_mode_enabled = data.get("paid_mode_enabled", False)

            # Załaduj autonomy_level jeśli istnieje (nowa funkcjonalność)
            self.autonomy_level = data.get("autonomy_level", 0)

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
                data = {
                    "tasks": tasks_list,
                    "paid_mode_enabled": self.paid_mode_enabled,
                    "autonomy_level": self.autonomy_level,
                }

                def _write_state() -> None:
                    with open(self._state_file_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

                # Zapisz do pliku poza pętlą event loop
                await asyncio.to_thread(_write_state)

                logger.debug(f"Stan zapisany do {self._state_file_path}")
            except Exception as e:
                logger.error(f"Błąd zapisu stanu do pliku: {e}")

    def _schedule_save(self) -> None:
        """Planuje zapis stanu z mechanizmem debouncingu."""
        self._save_requested = True

        try:
            # Sprawdź czy pętla zapisu już działa
            if self._save_task and not self._save_task.done():
                return

            # Spróbuj uzyskać aktywny event loop
            try:
                asyncio.get_running_loop()
                self._save_task = asyncio.create_task(self._process_save_queue())
            except RuntimeError:
                logger.debug("Brak event loop - pomijam automatyczny zapis stanu")
        except Exception as e:
            logger.error(f"Błąd podczas planowania zapisu: {e}")

    async def _process_save_queue(self) -> None:
        """Pętla przetwarzająca żądania zapisu."""
        # Krótkie opóźnienie dla grupowania zmian (burst handling)
        await asyncio.sleep(0.2)

        while True:
            self._save_requested = False
            await self._save()
            if not self._save_requested:
                break

    def _prune_tasks_if_needed(self) -> None:
        """Usuwa najstarsze zadania jeśli przekroczono limity."""

        if len(self._tasks) <= MAX_TASKS:
            return

        # Sortuj po created_at
        sorted_tasks = sorted(
            self._tasks.values(), key=lambda t: t.created_at, reverse=True
        )

        # Zachowaj tylko MAX_TASKS najnowszych
        kept_tasks = sorted_tasks[:MAX_TASKS]
        removed_count = len(self._tasks) - len(kept_tasks)

        if removed_count > 0:
            self._tasks = {t.id: t for t in kept_tasks}
            logger.info(
                f"Pruning StateManager: usunięto {removed_count} najstarszych zadań (limit {MAX_TASKS})"
            )

    async def shutdown(self) -> None:
        """Czeka na zakończenie pętli zapisu."""
        if self._save_task and not self._save_task.done():
            logger.info("Oczekiwanie na zakończenie zapisu stanu...")
            # Wymuś zapis jeśli był requested
            if self._save_requested:
                self._save_requested = False
                await self._save()

            with suppress(asyncio.CancelledError):
                await self._save_task
            self._save_task = None
            logger.info("Zapisy stanu zakończone")

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
        self._prune_tasks_if_needed()
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
            Lista wszystkich zadań posortowana od najnowszych
        """
        tasks = list(self._tasks.values())
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def clear_session_context(self, session_id: str) -> int:
        """
        Czyści historię i streszczenie w zadaniach powiązanych z podaną sesją.

        Args:
            session_id: identyfikator sesji

        Returns:
            Liczba zadań, które zostały zaktualizowane.
        """
        if not session_id:
            return 0

        updated = 0
        for task in self._tasks.values():
            ctx = getattr(task, "context_history", {}) or {}
            session_meta = ctx.get("session") or {}
            if session_meta.get("session_id") != session_id:
                continue

            ctx["session_history"] = []
            ctx["session_history_full"] = []
            ctx["session_summary"] = None
            ctx["session"] = {"session_id": session_id}
            task.context_history = ctx
            updated += 1

        if updated:
            self._schedule_save()
        return updated

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

    def update_partial_result(
        self, task_id: UUID, partial_result: str, persist: bool = False
    ) -> None:
        """
        Aktualizuje częściowy wynik zadania (np. stream chunk).

        Args:
            task_id: ID zadania
            partial_result: Złożony fragment odpowiedzi
            persist: Czy zapisać do pliku stanu (domyślnie False, aby nie spamować dysku)
        """
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(
                f"Próba aktualizacji wyniku dla nieistniejącego zadania: {task_id}"
            )
            return

        task.result = partial_result
        if persist:
            self._schedule_save()

    def update_context(self, task_id: UUID, updates: Dict[str, Any]) -> None:
        """
        Aktualizuje słownik context_history zadania (shallow merge).

        Args:
            task_id: ID zadania
            updates: Klucze i wartości do scalania
        """
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(
                f"Próba aktualizacji kontekstu nieistniejącego zadania: {task_id}"
            )
            return

        for key, value in updates.items():
            self._merge_context_value(task.context_history, key, value)

        self._schedule_save()

    @staticmethod
    def _merge_context_value(
        context_history: Dict[str, Any], key: str, value: Any
    ) -> None:
        """Scala pojedynczy wpis kontekstu (obsługuje usunięcia przez None)."""
        if value is None:
            context_history.pop(key, None)
            return

        existing = context_history.get(key)
        if not (isinstance(existing, dict) and isinstance(value, dict)):
            context_history[key] = value
            return

        for nested_key, nested_value in value.items():
            if nested_value is None:
                existing.pop(nested_key, None)
            else:
                existing[nested_key] = nested_value
        context_history[key] = existing

    def set_paid_mode(self, enabled: bool) -> None:
        """
        Ustawia tryb płatny (Global Cost Guard).

        UWAGA: W środowisku produkcyjnym ta metoda powinna być chroniona
        autoryzacją/uwierzytelnianiem. Obecnie brak weryfikacji uprawnień.

        Args:
            enabled: True włącza płatne funkcje (Google Grounding), False wyłącza
        """
        self.paid_mode_enabled = enabled
        logger.info(f"Paid Mode {'włączony' if enabled else 'wyłączony'}")
        self._schedule_save()

    # ========================================
    # Global Cost Guard Methods
    # ========================================

    def enable_paid_mode(self) -> None:
        """
        Włącza tryb płatny (Pro Mode) - umożliwia dostęp do chmurowych API.

        UWAGA: Ten stan jest tymczasowy i resetuje się przy restarcie aplikacji.
        """
        self.paid_mode_enabled = True
        logger.warning("🔓 Paid Mode ENABLED - Cloud API access unlocked")

    def disable_paid_mode(self) -> None:
        """
        Wyłącza tryb płatny (Eco Mode) - blokuje dostęp do chmurowych API.
        """
        self.paid_mode_enabled = False
        logger.info("🔒 Paid Mode DISABLED - Cloud API access blocked")

    def is_paid_mode_enabled(self) -> bool:
        """
        Sprawdza czy tryb płatny jest włączony.

        Returns:
            True jeśli tryb płatny jest włączony, False w przeciwnym wypadku
        """
        return self.paid_mode_enabled
