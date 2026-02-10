"""Moduł: parallel_skill - umiejętność równoległego przetwarzania (Map-Reduce)."""

import asyncio
import json
from typing import Annotated, Any, Dict, List

from anyio import fail_after
from semantic_kernel.functions import kernel_function

from venom_core.infrastructure.message_broker import MessageBroker
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Stałe konfiguracyjne
DEFAULT_SORT_INDEX = 999999  # Używane dla zadań bez item_index przy sortowaniu
POLLING_INTERVAL_SECONDS = 2  # Interwał sprawdzania statusu zadań


class ParallelSkill:
    """
    Skill do równoległego przetwarzania zadań (Map-Reduce).

    Umożliwia Architektowi rozdzielanie dużych zadań na mniejsze części,
    dystrybuowanie ich do węzłów (Spores) i agregowanie wyników.
    """

    def __init__(self, message_broker: MessageBroker):
        """
        Inicjalizacja ParallelSkill.

        Args:
            message_broker: Broker wiadomości Redis
        """
        self.message_broker = message_broker
        logger.info("ParallelSkill zainicjalizowany")

    @kernel_function(
        name="map_reduce",
        description="Wykonuje zadanie równolegle na wielu elementach używając architektury Map-Reduce. "
        "Rozdziela zadanie na N pod-zadań, dystrybuuje je do węzłów Spore, czeka na wyniki i agreguje je. "
        "Idealny do przetwarzania list elementów (URLe, pliki, dane) gdzie każdy element można przetworzyć niezależnie.",
    )
    async def map_reduce(
        self,
        task_description: Annotated[
            str,
            "Opis zadania do wykonania na KAŻDYM elemencie. "
            "Przykład: 'Pobierz treść artykułu i stresuść ją do 3 zdań'",
        ],
        items: Annotated[
            str,
            "Lista elementów do przetworzenia w formacie JSON (np. lista URLi, plików, tekstów). "
            "Każdy element zostanie przekazany jako osobne zadanie. "
            'Przykład: \'["url1", "url2", "url3"]\' lub \'[{"title": "doc1", "path": "/file1"}, ...]\'',
        ],
        priority: Annotated[
            str,
            "Priorytet zadań: 'high_priority' lub 'background'. Domyślnie 'background'.",
        ] = "background",
        wait_timeout: Annotated[
            int,
            "Maksymalny czas oczekiwania na wyniki w sekundach. Domyślnie 300 (5 minut).",
        ] = 300,
    ) -> str:
        """
        Wykonuje Map-Reduce na liście elementów.

        Args:
            task_description: Opis zadania do wykonania na każdym elemencie
            items: Lista elementów do przetworzenia (JSON string)
            priority: Priorytet zadań
            wait_timeout: Timeout oczekiwania na wyniki

        Returns:
            JSON string z wynikami lub informacja o błędzie
        """
        try:
            # Parse items z JSON
            try:
                items_list = json.loads(items)
            except json.JSONDecodeError as e:
                return f"❌ Błąd parsowania listy elementów: {e}"

            if not isinstance(items_list, list):
                return "❌ Parameter 'items' musi być listą JSON"

            if not items_list:
                return "❌ Lista elementów jest pusta"

            logger.info(
                f"Rozpoczynam Map-Reduce: {len(items_list)} elementów, priorytet: {priority}"
            )

            # FAZA MAP: Utwórz zadania dla każdego elementu
            task_ids = []
            for idx, item in enumerate(items_list):
                # Przygotuj payload zadania
                payload = {
                    "task_description": task_description,
                    "item": item,
                    "item_index": idx,
                    "total_items": len(items_list),
                }

                # Dodaj zadanie do kolejki
                task_id = await self.message_broker.enqueue_task(
                    task_type="map_task",
                    payload=payload,
                    priority=priority,
                )
                task_ids.append(task_id)

            logger.info(f"Utworzono {len(task_ids)} zadań Map: {task_ids[:3]}...")

            # FAZA WAIT: Czekaj na ukończenie wszystkich zadań
            results = await self._wait_for_results_with_timeout(task_ids, wait_timeout)

            # FAZA REDUCE: Agreguj wyniki
            completed = sum(1 for r in results if r["status"] == "completed")
            failed = sum(1 for r in results if r["status"] == "failed")
            pending = sum(1 for r in results if r["status"] == "pending")

            response = {
                "summary": {
                    "total_tasks": len(task_ids),
                    "completed": completed,
                    "failed": failed,
                    "pending": pending,
                    "success_rate": f"{(completed / len(task_ids) * 100):.1f}%",
                },
                "results": results,
            }

            logger.info(
                f"Map-Reduce zakończony: {completed} OK, {failed} Failed, {pending} Pending"
            )

            return json.dumps(response, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Błąd w map_reduce: {e}")
            return f"❌ Błąd podczas wykonywania Map-Reduce: {e}"

    async def _wait_for_results(self, task_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Czeka na wyniki zadań z timeoutem.

        Args:
            task_ids: Lista ID zadań
        Returns:
            Lista wyników zadań
        """
        results: List[Dict[str, Any]] = []
        result_ids: set[str] = set()

        while True:
            all_done = await self._collect_terminal_results(
                task_ids=task_ids,
                results=results,
                result_ids=result_ids,
            )

            if all_done:
                break

            await asyncio.sleep(POLLING_INTERVAL_SECONDS)

        results.sort(
            key=lambda r: (
                r["item_index"] if r["item_index"] is not None else DEFAULT_SORT_INDEX
            )
        )

        return results

    async def _wait_for_results_with_timeout(
        self, task_ids: List[str], wait_timeout: int
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        result_ids: set[str] = set()
        try:
            with fail_after(wait_timeout):
                while True:
                    all_done = await self._collect_terminal_results(
                        task_ids=task_ids,
                        results=results,
                        result_ids=result_ids,
                    )
                    if all_done:
                        break
                    await asyncio.sleep(POLLING_INTERVAL_SECONDS)
        except TimeoutError:
            logger.warning(
                f"Timeout waiting for results ({wait_timeout}s), returning partial results"
            )
            await self._collect_terminal_results(
                task_ids=task_ids,
                results=results,
                result_ids=result_ids,
            )
        self._append_pending_results(task_ids, results, result_ids)
        results.sort(
            key=lambda r: (
                r["item_index"] if r["item_index"] is not None else DEFAULT_SORT_INDEX
            )
        )
        return results

    async def _collect_terminal_results(
        self,
        *,
        task_ids: List[str],
        results: List[Dict[str, Any]],
        result_ids: set[str],
    ) -> bool:
        all_done = True
        for task_id in task_ids:
            task = await self.message_broker.get_task_status(task_id)
            if not task:
                all_done = False
                continue
            if task.status in ("completed", "failed"):
                self._append_result(task_id, task, results, result_ids)
                continue
            all_done = False
        return all_done

    def _append_result(
        self,
        task_id: str,
        task: Any,
        results: List[Dict[str, Any]],
        result_ids: set[str],
    ) -> None:
        if task_id in result_ids:
            return
        results.append(
            {
                "task_id": task_id,
                "status": task.status,
                "result": task.result,
                "error": task.error,
                "item_index": task.payload.get("item_index"),
            }
        )
        result_ids.add(task_id)

    def _append_pending_results(
        self,
        task_ids: List[str],
        results: List[Dict[str, Any]],
        result_ids: set[str],
    ) -> None:
        for task_id in task_ids:
            if task_id in result_ids:
                continue
            results.append(
                {
                    "task_id": task_id,
                    "status": "pending",
                    "result": None,
                    "error": "Timeout",
                    "item_index": None,
                }
            )
            result_ids.add(task_id)

    @kernel_function(
        name="parallel_execute",
        description="Wykonuje jedno zadanie równolegle na wielu węzłach (dla zadań intensywnych obliczeniowo). "
        "Używaj gdy jedno zadanie może zostać rozdzielone na niezależne podzadania wykonywane równolegle.",
    )
    async def parallel_execute(
        self,
        task_description: Annotated[
            str, "Opis zadania do wykonania równolegle na wielu węzłach."
        ],
        subtasks: Annotated[
            str,
            "Lista pod-zadań w formacie JSON, gdzie każde pod-zadanie to opis co należy wykonać. "
            'Przykład: \'["Przeskanuj katalog /src", "Przeskanuj katalog /tests"]\'',
        ],
        priority: Annotated[
            str,
            "Priorytet zadań: 'high_priority' lub 'background'. Domyślnie 'high_priority'.",
        ] = "high_priority",
        wait_timeout: Annotated[
            int,
            "Maksymalny czas oczekiwania na wyniki w sekundach. Domyślnie 600 (10 minut).",
        ] = 600,
    ) -> str:
        """
        Wykonuje równolegle listę pod-zadań.

        Args:
            task_description: Ogólny opis zadania
            subtasks: Lista pod-zadań (JSON string)
            priority: Priorytet
            wait_timeout: Timeout

        Returns:
            JSON string z wynikami
        """
        try:
            # Parse subtasks z JSON
            try:
                subtasks_list = json.loads(subtasks)
            except json.JSONDecodeError as e:
                return f"❌ Błąd parsowania listy pod-zadań: {e}"

            if not isinstance(subtasks_list, list):
                return "❌ Parameter 'subtasks' musi być listą JSON"

            if not subtasks_list:
                return "❌ Lista pod-zadań jest pusta"

            logger.info(f"Rozpoczynam parallel_execute: {len(subtasks_list)} pod-zadań")

            # Utwórz zadania
            task_ids = []
            for idx, subtask in enumerate(subtasks_list):
                payload = {
                    "main_task": task_description,
                    "subtask": subtask,
                    "subtask_index": idx,
                    "total_subtasks": len(subtasks_list),
                }

                task_id = await self.message_broker.enqueue_task(
                    task_type="parallel_task", payload=payload, priority=priority
                )
                task_ids.append(task_id)

            logger.info(f"Utworzono {len(task_ids)} zadań równoległych")

            # Czekaj na wyniki
            results = await self._wait_for_results_with_timeout(task_ids, wait_timeout)

            # Agreguj
            completed = sum(1 for r in results if r["status"] == "completed")
            failed = sum(1 for r in results if r["status"] == "failed")

            response = {
                "task_description": task_description,
                "summary": {
                    "total_subtasks": len(task_ids),
                    "completed": completed,
                    "failed": failed,
                    "success_rate": f"{(completed / len(task_ids) * 100):.1f}%",
                },
                "results": results,
            }

            logger.info(f"parallel_execute zakończony: {completed} OK, {failed} Failed")

            return json.dumps(response, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Błąd w parallel_execute: {e}")
            return f"❌ Błąd podczas równoległego wykonywania: {e}"

    @kernel_function(
        name="get_task_status",
        description="Sprawdza status zadania równoległego. Użyj gdy chcesz sprawdzić postęp zadania.",
    )
    async def get_task_status(
        self,
        task_id: Annotated[str, "ID zadania do sprawdzenia"],
    ) -> str:
        """
        Sprawdza status zadania.

        Args:
            task_id: ID zadania

        Returns:
            JSON string ze statusem zadania
        """
        try:
            task = await self.message_broker.get_task_status(task_id)

            if not task:
                return f"❌ Zadanie {task_id} nie znalezione"

            status_info = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": task.status,
                "priority": task.priority,
                "assigned_node": task.assigned_node,
                "attempt": task.attempt,
                "max_retries": task.max_retries,
                "created_at": task.created_at.isoformat(),
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": (
                    task.completed_at.isoformat() if task.completed_at else None
                ),
                "result": task.result,
                "error": task.error,
            }

            return json.dumps(status_info, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania statusu zadania: {e}")
            return f"❌ Błąd: {e}"
