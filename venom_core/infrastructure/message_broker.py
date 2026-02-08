"""Modul: message_broker - infrastruktura kolejkowania zadan (Redis + ARQ)."""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
REDIS_NOT_CONNECTED_ERROR = "MessageBroker nie jest połączony z Redis"


class TaskMessage:
    """Reprezentacja zadania w kolejce."""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        priority: str = "background",
        created_at: Optional[datetime] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        """
        Inicjalizacja zadania.

        Args:
            task_id: Unikalny identyfikator zadania
            task_type: Typ zadania (np. 'map_reduce', 'skill_execution')
            payload: Dane zadania
            priority: Priorytet ('high_priority' lub 'background')
            created_at: Czas utworzenia
            timeout: Timeout wykonania w sekundach
            max_retries: Maksymalna liczba prób
        """
        self.task_id = task_id
        self.task_type = task_type
        self.payload = payload
        self.priority = priority
        self.created_at = created_at or datetime.now()
        self.timeout = timeout or SETTINGS.HIVE_TASK_TIMEOUT
        self.max_retries = max_retries or SETTINGS.HIVE_MAX_RETRIES
        self.attempt = 0
        self.assigned_node: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.status = "pending"  # pending, running, completed, failed

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje zadanie do słownika."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "payload": self.payload,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "attempt": self.attempt,
            "assigned_node": self.assigned_node,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "result": self.result,
            "error": self.error,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskMessage":
        """Tworzy zadanie ze słownika."""
        task = cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            payload=data["payload"],
            priority=data.get("priority", "background"),
            created_at=datetime.fromisoformat(data["created_at"]),
            timeout=data.get("timeout"),
            max_retries=data.get("max_retries"),
        )
        task.attempt = data.get("attempt", 0)
        task.assigned_node = data.get("assigned_node")
        task.started_at = (
            datetime.fromisoformat(data["started_at"])
            if data.get("started_at")
            else None
        )
        task.completed_at = (
            datetime.fromisoformat(data["completed_at"])
            if data.get("completed_at")
            else None
        )
        task.result = data.get("result")
        task.error = data.get("error")
        task.status = data.get("status", "pending")
        return task


class MessageBroker:
    """
    Broker wiadomości Redis + ARQ dla architektury Hive.

    Zarządza kolejkami zadań, dystrybuuje prace do węzłów (Spores),
    obsługuje broadcast control commands oraz monitoring stanu zadań.
    """

    def __init__(self):
        """Inicjalizacja Message Broker."""
        self.redis_client: Optional[redis.Redis] = None
        self.arq_pool: Optional[ArqRedis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self._is_connected = False
        self._task_registry: Dict[str, TaskMessage] = {}
        self._lock = asyncio.Lock()

        # Konfiguracja Redis
        self.redis_settings = RedisSettings(
            host=SETTINGS.REDIS_HOST,
            port=SETTINGS.REDIS_PORT,
            database=SETTINGS.REDIS_DB,
            password=(
                SETTINGS.REDIS_PASSWORD.get_secret_value()
                if SETTINGS.REDIS_PASSWORD.get_secret_value()
                else None
            ),
        )

        logger.info("MessageBroker zainicjalizowany")

    async def connect(self) -> bool:
        """
        Nawiązuje połączenie z Redis.

        Returns:
            True jeśli połączenie udane, False w przeciwnym razie
        """
        try:
            # Połączenie z Redis dla pub/sub i cache
            self.redis_client = redis.Redis(
                host=self.redis_settings.host,
                port=self.redis_settings.port,
                db=self.redis_settings.database,
                password=self.redis_settings.password,
                decode_responses=False,  # Przechowujemy binarne payloady JSON
            )

            # Test połączenia
            await self.redis_client.ping()

            # Połączenie z ARQ pool dla kolejki zadań
            self.arq_pool = await create_pool(self.redis_settings)

            self._is_connected = True
            logger.info(
                f"MessageBroker połączony z Redis: {self.redis_settings.host}:{self.redis_settings.port}"
            )
            return True

        except Exception as e:
            logger.error(f"Błąd połączenia z Redis: {e}")
            self._is_connected = False
            return False

    async def disconnect(self):
        """Zamyka połączenie z Redis."""
        try:
            if self.pubsub:
                await self.pubsub.unsubscribe()
                await self.pubsub.close()

            if self.arq_pool:
                await self.arq_pool.close()

            if self.redis_client:
                await self.redis_client.close()

            self._is_connected = False
            logger.info("MessageBroker rozłączony")

        except Exception as e:
            logger.error(f"Błąd podczas rozłączania MessageBroker: {e}")

    async def enqueue_task(
        self,
        task_type: str,
        payload: Dict[str, Any],
        priority: str = "background",
        task_id: Optional[str] = None,
    ) -> str:
        """
        Dodaje zadanie do kolejki.

        Args:
            task_type: Typ zadania
            payload: Dane zadania
            priority: Priorytet ('high_priority' lub 'background')
            task_id: Opcjonalny identyfikator zadania (domyślnie generowany)

        Returns:
            ID zadania

        Raises:
            RuntimeError: Jeśli brak połączenia z Redis
        """
        if not self._is_connected or not self.arq_pool:
            raise RuntimeError(REDIS_NOT_CONNECTED_ERROR)

        # Generuj ID jeśli nie podano
        if not task_id:
            task_id = f"{task_type}_{datetime.now().timestamp()}"

        # Utwórz TaskMessage
        task = TaskMessage(
            task_id=task_id, task_type=task_type, payload=payload, priority=priority
        )

        async with self._lock:
            # Zapisz w rejestrze
            self._task_registry[task_id] = task

            # Dodaj do odpowiedniej kolejki ARQ
            queue_name = (
                SETTINGS.HIVE_HIGH_PRIORITY_QUEUE
                if priority == "high_priority"
                else SETTINGS.HIVE_BACKGROUND_QUEUE
            )

            # Enqueue task do ARQ
            await self.arq_pool.enqueue_job(
                task_type,
                task_id,
                payload,
                _job_id=task_id,
                _queue_name=queue_name,
            )

            # Zapisz informacje o zadaniu w Redis (dla monitoringu)
            await self._store_task_info(task)

            logger.info(f"Zadanie {task_id} dodane do kolejki {queue_name}")

        return task_id

    async def _store_task_info(self, task: TaskMessage):
        """Zapisuje informacje o zadaniu w Redis."""
        if not self.redis_client:
            return

        key = f"venom:task:{task.task_id}"
        payload = task.to_dict()
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        # TTL: 24 godziny
        await self.redis_client.setex(key, 86400, data)

    async def get_task_status(self, task_id: str) -> Optional[TaskMessage]:
        """
        Pobiera status zadania.

        Args:
            task_id: ID zadania

        Returns:
            TaskMessage lub None jeśli nie znaleziono
        """
        if not self.redis_client:
            return None

        # Sprawdź w pamięci
        if task_id in self._task_registry:
            return self._task_registry[task_id]

        # Sprawdź w Redis
        key = f"venom:task:{task_id}"
        data = await self.redis_client.get(key)
        if data:
            try:
                decoded = data.decode("utf-8") if isinstance(data, bytes) else str(data)
                task_payload = json.loads(decoded)
                if not isinstance(task_payload, dict):
                    logger.warning(
                        "Nieprawidlowy format task payload w Redis dla task_id=%s",
                        task_id,
                    )
                    return None
                task = TaskMessage.from_dict(task_payload)
                self._task_registry[task_id] = task
                return task
            except Exception as exc:
                logger.warning(
                    "Nie udalo sie odczytac task payload z Redis dla task_id=%s: %s",
                    task_id,
                    exc,
                )
                return None

        return None

    async def update_task_status(
        self,
        task_id: str,
        status: str,
        assigned_node: Optional[str] = None,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ):
        """
        Aktualizuje status zadania.

        Args:
            task_id: ID zadania
            status: Nowy status ('running', 'completed', 'failed')
            assigned_node: Node który wykonuje/wykonał zadanie
            result: Wynik zadania
            error: Błąd (jeśli wystąpił)
        """
        task = await self.get_task_status(task_id)
        if not task:
            logger.warning(f"Zadanie {task_id} nie znalezione")
            return

        async with self._lock:
            task.status = status
            if assigned_node:
                task.assigned_node = assigned_node
            if status == "running" and not task.started_at:
                task.started_at = datetime.now()
            if status in ("completed", "failed"):
                task.completed_at = datetime.now()
            if result is not None:
                task.result = result
            if error:
                task.error = error

            # Zapisz w Redis
            await self._store_task_info(task)

        logger.info(f"Status zadania {task_id} zaktualizowany: {status}")

    async def broadcast_control(
        self, command: str, data: Optional[Dict[str, Any]] = None
    ):
        """
        Wysyła komendę broadcast do wszystkich węzłów.

        Args:
            command: Komenda (np. 'UPDATE_SYSTEM', 'SHUTDOWN', 'STATUS')
            data: Dodatkowe dane komendy
        """
        if not self.redis_client:
            raise RuntimeError(REDIS_NOT_CONNECTED_ERROR)

        message = {
            "command": command,
            "data": data or {},
            "timestamp": datetime.now().isoformat(),
        }

        # Publikuj na kanale broadcast
        await self.redis_client.publish(
            SETTINGS.HIVE_BROADCAST_CHANNEL, json.dumps(message)
        )

        logger.info(f"Broadcast wysłany: {command}")

    async def subscribe_broadcast(self) -> redis.client.PubSub:
        """
        Subskrybuje kanał broadcast.

        Returns:
            Obiekt PubSub do odbioru wiadomości

        Raises:
            RuntimeError: Jeśli brak połączenia z Redis
        """
        if not self.redis_client:
            raise RuntimeError(REDIS_NOT_CONNECTED_ERROR)

        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe(SETTINGS.HIVE_BROADCAST_CHANNEL)

        logger.info(f"Subskrypcja kanału broadcast: {SETTINGS.HIVE_BROADCAST_CHANNEL}")
        return self.pubsub

    async def get_queue_length(self, queue_name: str) -> int:
        """
        Pobiera długość kolejki.

        Args:
            queue_name: Nazwa kolejki

        Returns:
            Liczba zadań w kolejce
        """
        if not self.redis_client:
            return 0

        # ARQ używa sorted set dla kolejki
        length = await self.redis_client.zcard(queue_name)
        return length

    async def get_queue_stats(self) -> Dict[str, Any]:
        """
        Pobiera statystyki kolejek.

        Returns:
            Słownik ze statystykami
        """
        # Długości kolejek (0 jeśli brak połączenia)
        high_priority_length = 0
        background_length = 0

        if self.redis_client:
            high_priority_length = await self.get_queue_length(
                SETTINGS.HIVE_HIGH_PRIORITY_QUEUE
            )
            background_length = await self.get_queue_length(
                SETTINGS.HIVE_BACKGROUND_QUEUE
            )

        # Zlicz zadania według statusu
        pending = sum(1 for t in self._task_registry.values() if t.status == "pending")
        running = sum(1 for t in self._task_registry.values() if t.status == "running")
        completed = sum(
            1 for t in self._task_registry.values() if t.status == "completed"
        )
        failed = sum(1 for t in self._task_registry.values() if t.status == "failed")

        return {
            "high_priority_queue": high_priority_length,
            "background_queue": background_length,
            "total_queued": high_priority_length + background_length,
            "tasks_pending": pending,
            "tasks_running": running,
            "tasks_completed": completed,
            "tasks_failed": failed,
            "connected": self._is_connected,
        }

    async def detect_zombie_tasks(self) -> List[TaskMessage]:
        """
        Wykrywa zombie tasks (zadania które utknęły).

        Returns:
            Lista zombie tasks
        """
        zombies = []
        now = datetime.now()
        timeout = timedelta(seconds=SETTINGS.HIVE_ZOMBIE_TASK_TIMEOUT)

        async with self._lock:
            for task in self._task_registry.values():
                if task.status == "running" and task.started_at:
                    elapsed = now - task.started_at
                    if elapsed > timeout:
                        zombies.append(task)
                        logger.warning(
                            f"Wykryto zombie task: {task.task_id} (elapsed: {elapsed})"
                        )

        return zombies

    async def retry_task(self, task_id: str) -> bool:
        """
        Ponownie próbuje wykonać zadanie.

        Args:
            task_id: ID zadania

        Returns:
            True jeśli zadanie zostało dodane ponownie, False w przeciwnym razie
        """
        task = await self.get_task_status(task_id)
        if not task:
            logger.warning(f"Zadanie {task_id} nie znalezione")
            return False

        if task.attempt >= task.max_retries:
            logger.warning(
                f"Zadanie {task_id} osiągnęło maksymalną liczbę prób ({task.max_retries})"
            )
            return False

        async with self._lock:
            task.attempt += 1
            task.status = "pending"
            task.assigned_node = None
            task.started_at = None
            task.error = None

            # Enqueue ponownie
            await self.enqueue_task(
                task_type=task.task_type,
                payload=task.payload,
                priority=task.priority,
                task_id=task.task_id,
            )

            logger.info(
                f"Zadanie {task_id} dodane ponownie (próba {task.attempt}/{task.max_retries})"
            )

        return True

    def is_connected(self) -> bool:
        """Sprawdza czy broker jest połączony."""
        return self._is_connected
