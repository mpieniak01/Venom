"""Moduł: foreman - agent majster, zarządca zasobów klastra (Load Balancer & Watchdog)."""

import asyncio
from contextlib import suppress
from datetime import datetime
from typing import Any, Dict, Optional

from venom_core.agents.base import BaseAgent
from venom_core.config import SETTINGS
from venom_core.execution.maf_runtime import AgentRuntime as Kernel
from venom_core.infrastructure.message_broker import MessageBroker
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class NodeMetrics:
    """Metryki węzła (Spore)."""

    def __init__(
        self,
        node_id: str,
        node_name: str,
        cpu_usage: float = 0.0,
        memory_usage: float = 0.0,
        active_tasks: int = 0,
        gpu_available: bool = False,
        capabilities: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicjalizacja metryk węzła.

        Args:
            node_id: ID węzła
            node_name: Nazwa węzła
            cpu_usage: Użycie CPU (0-100%)
            memory_usage: Użycie pamięci (0-100%)
            active_tasks: Liczba aktywnych zadań
            gpu_available: Czy węzeł ma dostęp do GPU
            capabilities: Możliwości węzła
        """
        self.node_id = node_id
        self.node_name = node_name
        self.cpu_usage = cpu_usage
        self.memory_usage = memory_usage
        self.active_tasks = active_tasks
        self.gpu_available = gpu_available
        self.capabilities = capabilities or {}
        self.last_update = datetime.now()
        self.is_online = True

    def get_load_score(self) -> float:
        """
        Oblicza wynik obciążenia węzła (niższy = lepszy).

        Wagi można dostosować w config.py dla różnych scenariuszy:
        - CPU-intensive workloads: zwiększ FOREMAN_CPU_WEIGHT
        - Memory-intensive workloads: zwiększ FOREMAN_MEMORY_WEIGHT

        Returns:
            Wynik obciążenia (0-100, gdzie 0 = wolny, 100 = zajęty)
        """
        # Wagi priorytetów z konfiguracji (TD-010 - przeniesione do config.py)
        cpu_weight = SETTINGS.FOREMAN_CPU_WEIGHT
        memory_weight = SETTINGS.FOREMAN_MEMORY_WEIGHT
        tasks_weight = SETTINGS.FOREMAN_TASKS_WEIGHT

        # Normalizuj active_tasks (max z konfiguracji)
        normalized_tasks = (
            min(self.active_tasks / SETTINGS.FOREMAN_MAX_TASKS_NORMALIZATION, 1.0) * 100
        )

        load_score = (
            self.cpu_usage * cpu_weight
            + self.memory_usage * memory_weight
            + normalized_tasks * tasks_weight
        )

        return load_score

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje metryki do słownika."""
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "active_tasks": self.active_tasks,
            "gpu_available": self.gpu_available,
            "capabilities": self.capabilities,
            "load_score": self.get_load_score(),
            "last_update": self.last_update.isoformat(),
            "is_online": self.is_online,
        }


class ForemanAgent(BaseAgent):
    """
    Agent Majster (Foreman) - zarządza zasobami klastra.

    Rola: Load Balancer & Watchdog
    - Monitoruje obciążenie węzłów (CPU/RAM)
    - Decyduje gdzie wysłać zadanie (routing)
    - Wykrywa zombie tasks i zleca je ponownie
    - Zarządza priorytetami i harmonogramem
    """

    def __init__(
        self,
        kernel: Kernel,
        message_broker: MessageBroker,
        node_manager: Optional[Any] = None,
    ):
        """
        Inicjalizacja ForemanAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            message_broker: Broker wiadomości Redis
            node_manager: NodeManager dla dostępu do metryk węzłów (opcjonalny)
        """
        super().__init__(kernel)
        self.message_broker = message_broker
        self.node_manager = node_manager
        self.nodes_metrics: Dict[str, NodeMetrics] = {}
        self._watchdog_task: Optional[asyncio.Task] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        self._is_running = False

        logger.info("ForemanAgent zainicjalizowany")

    async def start(self):
        """Uruchamia Foreman (watchdog i monitoring)."""
        if self._is_running:
            logger.warning("ForemanAgent już działa")
            return

        self._is_running = True

        # Uruchom watchdog (wykrywanie zombie tasks)
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())

        # Uruchom monitoring węzłów
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        await asyncio.sleep(0)

        logger.info("ForemanAgent uruchomiony")

    async def stop(self):
        """Zatrzymuje Foreman."""
        self._is_running = False

        if self._watchdog_task:
            self._watchdog_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._watchdog_task

        if self._monitoring_task:
            self._monitoring_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitoring_task

        logger.info("ForemanAgent zatrzymany")

    async def _watchdog_loop(self):
        """Pętla watchdog - wykrywa i naprawia zombie tasks."""
        while self._is_running:
            try:
                # Wykryj zombie tasks
                zombies = await self.message_broker.detect_zombie_tasks()

                if zombies:
                    logger.warning(f"Wykryto {len(zombies)} zombie tasks")

                    for zombie in zombies:
                        # Oznacz jako failed
                        await self.message_broker.update_task_status(
                            zombie.task_id, status="failed", error="Zombie task timeout"
                        )

                        # Spróbuj retry
                        retry_success = await self.message_broker.retry_task(
                            zombie.task_id
                        )
                        if retry_success:
                            logger.info(
                                f"Zombie task {zombie.task_id} zlecony ponownie"
                            )
                        else:
                            logger.error(
                                f"Nie można ponownie zlecić zombie task {zombie.task_id}"
                            )

                # Czekaj 60 sekund przed następnym sprawdzeniem
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Błąd w watchdog loop: {e}")
                await asyncio.sleep(60)

    async def _monitoring_loop(self):
        """Pętla monitoringu - aktualizuje metryki węzłów."""
        while self._is_running:
            try:
                self._collect_node_metrics()

                # Czekaj 30 sekund przed następną aktualizacją
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Błąd w monitoring loop: {e}")
                await asyncio.sleep(30)

    def _collect_node_metrics(self) -> None:
        if not self.node_manager:
            return
        for node_id, node_info in self.node_manager.nodes.items():
            self._update_single_node_metrics(node_id, node_info)

    def _safe_node_metrics_from_info(self, node_id: str, node_info) -> NodeMetrics:
        capabilities_obj = getattr(node_info, "capabilities", None)
        gpu_available = bool(getattr(capabilities_obj, "has_gpu", False))
        if capabilities_obj and hasattr(capabilities_obj, "model_dump"):
            capabilities = capabilities_obj.model_dump()
        else:
            capabilities = {}
        return NodeMetrics(
            node_id=node_id,
            node_name=getattr(node_info, "node_name", node_id),
            cpu_usage=getattr(node_info, "cpu_usage", 0.0),
            memory_usage=getattr(node_info, "memory_usage", 0.0),
            active_tasks=getattr(node_info, "active_tasks", 0),
            gpu_available=gpu_available,
            capabilities=capabilities,
        )

    def _update_single_node_metrics(self, node_id: str, node_info) -> None:
        try:
            metrics = self._safe_node_metrics_from_info(node_id, node_info)
            self.nodes_metrics[node_id] = metrics
        except Exception as exc:
            logger.warning(f"Nie można pobrać metryk węzła {node_id}: {exc}")

    def select_best_node(
        self, task_requirements: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Wybiera najlepszy węzeł do wykonania zadania.

        Args:
            task_requirements: Wymagania zadania (np. {'gpu': True})

        Returns:
            ID najlepszego węzła lub None jeśli brak dostępnych węzłów
        """
        if not self.nodes_metrics:
            logger.warning("Brak dostępnych węzłów")
            return None

        task_requirements = task_requirements or {}

        # Filtruj węzły spełniające wymagania
        eligible_nodes = []
        for node_id, metrics in self.nodes_metrics.items():
            if not metrics.is_online:
                continue

            # Sprawdź wymagania GPU
            if task_requirements.get("gpu", False) and not metrics.gpu_available:
                continue

            # Sprawdź dostępność capabilities
            required_caps = task_requirements.get("capabilities", [])
            if required_caps:
                node_caps = metrics.capabilities.get("skills", [])
                if not all(cap in node_caps for cap in required_caps):
                    continue

            eligible_nodes.append((node_id, metrics))

        if not eligible_nodes:
            logger.warning("Brak węzłów spełniających wymagania")
            return None

        # Sortuj według load score (najniższy = najlepszy)
        eligible_nodes.sort(key=lambda x: x[1].get_load_score())

        best_node_id = eligible_nodes[0][0]
        best_metrics = eligible_nodes[0][1]

        logger.info(
            f"Wybrany węzeł: {best_node_id} (load: {best_metrics.get_load_score():.1f}%)"
        )

        return best_node_id

    async def assign_task(
        self, task_id: str, task_requirements: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Przypisuje zadanie do najlepszego węzła.

        Args:
            task_id: ID zadania
            task_requirements: Wymagania zadania

        Returns:
            ID węzła lub None jeśli nie udało się przypisać
        """
        # Wybierz najlepszy węzeł
        node_id = self.select_best_node(task_requirements)

        if not node_id:
            logger.error(
                f"Nie można przypisać zadania {task_id} - brak dostępnych węzłów"
            )
            return None

        # Aktualizuj status zadania
        await self.message_broker.update_task_status(
            task_id, status="running", assigned_node=node_id
        )

        # Inkrementuj licznik active_tasks na węźle
        if node_id in self.nodes_metrics:
            self.nodes_metrics[node_id].active_tasks += 1

        logger.info(f"Zadanie {task_id} przypisane do węzła {node_id}")

        return node_id

    async def complete_task(self, task_id: str, node_id: str, result: Any):
        """
        Oznacza zadanie jako ukończone.

        Args:
            task_id: ID zadania
            node_id: ID węzła który wykonał zadanie
            result: Wynik zadania
        """
        # Aktualizuj status zadania
        await self.message_broker.update_task_status(
            task_id, status="completed", result=result
        )

        # Dekrementuj licznik active_tasks na węźle
        if node_id in self.nodes_metrics:
            self.nodes_metrics[node_id].active_tasks = max(
                0, self.nodes_metrics[node_id].active_tasks - 1
            )

        logger.info(f"Zadanie {task_id} ukończone przez węzeł {node_id}")

    async def fail_task(self, task_id: str, node_id: str, error: str):
        """
        Oznacza zadanie jako nieudane.

        Args:
            task_id: ID zadania
            node_id: ID węzła który próbował wykonać zadanie
            error: Opis błędu
        """
        # Aktualizuj status zadania
        await self.message_broker.update_task_status(
            task_id, status="failed", error=error
        )

        # Dekrementuj licznik active_tasks na węźle
        if node_id in self.nodes_metrics:
            self.nodes_metrics[node_id].active_tasks = max(
                0, self.nodes_metrics[node_id].active_tasks - 1
            )

        # Spróbuj retry
        retry_success = await self.message_broker.retry_task(task_id)
        if retry_success:
            logger.info(f"Zadanie {task_id} zlecone ponownie po błędzie")
        else:
            logger.error(f"Zadanie {task_id} nieudane: {error}")

    def get_cluster_status(self) -> Dict[str, Any]:
        """
        Pobiera status klastra.

        Returns:
            Słownik ze statusem klastra
        """
        online_nodes = sum(1 for m in self.nodes_metrics.values() if m.is_online)
        total_nodes = len(self.nodes_metrics)
        avg_cpu = (
            sum(m.cpu_usage for m in self.nodes_metrics.values()) / total_nodes
            if total_nodes > 0
            else 0
        )
        avg_memory = (
            sum(m.memory_usage for m in self.nodes_metrics.values()) / total_nodes
            if total_nodes > 0
            else 0
        )
        total_tasks = sum(m.active_tasks for m in self.nodes_metrics.values())

        return {
            "total_nodes": total_nodes,
            "online_nodes": online_nodes,
            "offline_nodes": total_nodes - online_nodes,
            "avg_cpu_usage": round(avg_cpu, 1),
            "avg_memory_usage": round(avg_memory, 1),
            "total_active_tasks": total_tasks,
            "nodes": [m.to_dict() for m in self.nodes_metrics.values()],
        }

    async def process(self, input_text: str) -> str:
        """
        Przetwarza zapytanie (głównie do monitoringu/statusu).

        Args:
            input_text: Treść zapytania

        Returns:
            Wynik przetwarzania
        """
        # Foreman nie przetwarza zadań bezpośrednio, zwraca status
        status = self.get_cluster_status()
        queue_stats = await self.message_broker.get_queue_stats()

        return (
            f"🔧 Foreman Status:\n\n"
            f"Węzły: {status['online_nodes']}/{status['total_nodes']} online\n"
            f"Średnie obciążenie: CPU {status['avg_cpu_usage']}%, RAM {status['avg_memory_usage']}%\n"
            f"Aktywne zadania: {status['total_active_tasks']}\n\n"
            f"Kolejki:\n"
            f"  High Priority: {queue_stats['high_priority_queue']}\n"
            f"  Background: {queue_stats['background_queue']}\n"
            f"  Pending: {queue_stats['tasks_pending']}\n"
            f"  Running: {queue_stats['tasks_running']}\n"
            f"  Completed: {queue_stats['tasks_completed']}\n"
            f"  Failed: {queue_stats['tasks_failed']}\n"
        )
