"""Moduł: node_manager - Zarządza rojem węzłów zdalnych (Swarm Manager)."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import WebSocket

from venom_core.nodes.protocol import (
    Capabilities,
    HeartbeatMessage,
    NodeHandshake,
    NodeMessage,
    NodeResponse,
    SkillExecutionRequest,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class NodeInfo:
    """Informacje o zarejestrowanym węźle."""

    def __init__(
        self,
        node_id: str,
        node_name: str,
        capabilities: Capabilities,
        websocket: WebSocket,
    ):
        """
        Inicjalizacja informacji o węźle.

        Args:
            node_id: Unikalny ID węzła
            node_name: Nazwa węzła
            capabilities: Możliwości węzła
            websocket: Połączenie WebSocket
        """
        self.node_id = node_id
        self.node_name = node_name
        self.capabilities = capabilities
        self.websocket = websocket
        self.last_heartbeat = datetime.now()
        self.cpu_usage = 0.0
        self.memory_usage = 0.0
        self.active_tasks = 0
        self.is_online = True
        self.registered_at = datetime.now()

    def update_heartbeat(self, heartbeat: HeartbeatMessage):
        """Aktualizuje status węzła z heartbeat."""
        self.last_heartbeat = datetime.now()
        self.cpu_usage = heartbeat.cpu_usage
        self.memory_usage = heartbeat.memory_usage
        self.active_tasks = heartbeat.active_tasks
        self.is_online = True

    def to_dict(self) -> dict:
        """Konwertuje informacje o węźle na słownik."""
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "capabilities": self.capabilities.model_dump(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "active_tasks": self.active_tasks,
            "is_online": self.is_online,
            "registered_at": self.registered_at.isoformat(),
        }


class NodeManager:
    """Zarządza rojem węzłów zdalnych."""

    def __init__(self, shared_token: str, heartbeat_timeout: int = 60):
        """
        Inicjalizacja NodeManager.

        Args:
            shared_token: Token uwierzytelniający dla węzłów
            heartbeat_timeout: Timeout w sekundach dla heartbeat (domyślnie 60s)
        """
        self.shared_token = shared_token
        self.heartbeat_timeout = heartbeat_timeout
        self.nodes: Dict[str, NodeInfo] = {}
        self._lock = asyncio.Lock()
        self._pending_requests: Dict[str, asyncio.Future] = {}

        # Uruchom zadanie w tle sprawdzające healthcheck
        self._healthcheck_task = None

    async def start(self):
        """Uruchamia NodeManager i zadania w tle."""
        logger.info("NodeManager uruchomiony")
        self._healthcheck_task = asyncio.create_task(self._healthcheck_loop())

    async def stop(self):
        """Zatrzymuje NodeManager i zadania w tle."""
        if self._healthcheck_task:
            self._healthcheck_task.cancel()
            try:
                await self._healthcheck_task
            except asyncio.CancelledError:
                # Oczekiwane anulowanie zadania podczas zatrzymywania NodeManagera
                pass
        logger.info("NodeManager zatrzymany")

    async def register_node(
        self, handshake: NodeHandshake, websocket: WebSocket
    ) -> bool:
        """
        Rejestruje nowy węzeł w rejestrze.

        Args:
            handshake: Wiadomość handshake od węzła
            websocket: Połączenie WebSocket

        Returns:
            True jeśli rejestracja się powiodła, False w przeciwnym razie
        """
        # Sprawdź token
        if handshake.token != self.shared_token:
            logger.warning(
                f"Odrzucono węzeł {handshake.node_name}: nieprawidłowy token"
            )
            return False

        async with self._lock:
            # Sprawdź czy węzeł już jest zarejestrowany
            if handshake.node_id in self.nodes:
                logger.warning(
                    f"Węzeł {handshake.node_name} ({handshake.node_id}) jest już zarejestrowany"
                )
                # Aktualizuj połączenie WebSocket
                self.nodes[handshake.node_id].websocket = websocket
                self.nodes[handshake.node_id].is_online = True
                self.nodes[handshake.node_id].last_heartbeat = datetime.now()
                return True

            # Zarejestruj nowy węzeł
            node_info = NodeInfo(
                node_id=handshake.node_id,
                node_name=handshake.node_name,
                capabilities=handshake.capabilities,
                websocket=websocket,
            )
            self.nodes[handshake.node_id] = node_info

            logger.info(
                f"Zarejestrowano węzeł: {handshake.node_name} ({handshake.node_id})"
            )
            logger.info(
                f"  Skills: {', '.join(handshake.capabilities.skills) or 'brak'}"
            )
            logger.info(f"  Tags: {', '.join(handshake.capabilities.tags) or 'brak'}")
            logger.info(f"  Platform: {handshake.capabilities.platform}")

            return True

    async def unregister_node(self, node_id: str):
        """
        Wyrejestrowuje węzeł z rejestru.

        Args:
            node_id: ID węzła do wyrejestrowania
        """
        async with self._lock:
            if node_id in self.nodes:
                node = self.nodes[node_id]
                logger.info(f"Wyrejestrowano węzeł: {node.node_name} ({node_id})")
                del self.nodes[node_id]

    async def update_heartbeat(self, heartbeat: HeartbeatMessage):
        """
        Aktualizuje heartbeat węzła.

        Args:
            heartbeat: Wiadomość heartbeat
        """
        async with self._lock:
            if heartbeat.node_id in self.nodes:
                self.nodes[heartbeat.node_id].update_heartbeat(heartbeat)
                logger.debug(
                    f"Heartbeat od węzła {heartbeat.node_id}: "
                    f"CPU={heartbeat.cpu_usage:.2f}, "
                    f"MEM={heartbeat.memory_usage:.2f}, "
                    f"Tasks={heartbeat.active_tasks}"
                )

    async def execute_skill_on_node(
        self,
        node_id: str,
        skill_name: str,
        method_name: str,
        parameters: dict,
        timeout: int = 30,
    ) -> NodeResponse:
        """
        Wykonuje skill na zdalnym węźle.

        Args:
            node_id: ID węzła docelowego
            skill_name: Nazwa skilla
            method_name: Nazwa metody
            parameters: Parametry wywołania
            timeout: Timeout w sekundach

        Returns:
            Odpowiedź od węzła

        Raises:
            ValueError: Jeśli węzeł nie istnieje lub jest offline
            TimeoutError: Jeśli węzeł nie odpowiedział w czasie
        """
        # Pobierz węzeł z lockiem i skopiuj potrzebne dane
        async with self._lock:
            if node_id not in self.nodes:
                raise ValueError(f"Węzeł {node_id} nie istnieje")

            node = self.nodes[node_id]
            if not node.is_online:
                raise ValueError(f"Węzeł {node_id} jest offline")

            # Skopiuj referencję do websocket w zakresie locka
            websocket = node.websocket

        # Utwórz żądanie
        request = SkillExecutionRequest(
            node_id=node_id,
            skill_name=skill_name,
            method_name=method_name,
            parameters=parameters,
            timeout=timeout,
        )

        # Utwórz Future dla odpowiedzi (z lockiem dla _pending_requests)
        future: asyncio.Future[NodeResponse] = asyncio.Future()
        async with self._lock:
            self._pending_requests[request.request_id] = future

        try:
            # Wyślij żądanie do węzła (już poza lockiem, używając skopiowanej referencji)
            message = NodeMessage.from_execution_request(request)
            await websocket.send_json(message.model_dump())

            logger.info(
                f"Wysłano żądanie {request.request_id} do węzła {node_id}: "
                f"{skill_name}.{method_name}"
            )

            # Czekaj na odpowiedź z timeout
            response = await asyncio.wait_for(future, timeout=timeout)
            return response

        except asyncio.TimeoutError:
            logger.error(
                f"Timeout podczas wykonywania {skill_name}.{method_name} na węźle {node_id}"
            )
            raise TimeoutError(f"Węzeł {node_id} nie odpowiedział w czasie {timeout}s")
        except Exception as e:
            logger.error(f"Nie udało się wysłać wiadomości do węzła {node_id}: {e}")
            # Oznacz węzeł jako offline
            async with self._lock:
                if node_id in self.nodes:
                    self.nodes[node_id].is_online = False
            raise ValueError(f"Węzeł {node_id} jest niedostępny")
        finally:
            # Usuń Future z pending (z lockiem)
            async with self._lock:
                if request.request_id in self._pending_requests:
                    del self._pending_requests[request.request_id]

    async def handle_response(self, response: NodeResponse):
        """
        Obsługuje odpowiedź od węzła.

        Args:
            response: Odpowiedź od węzła
        """
        async with self._lock:
            if response.request_id in self._pending_requests:
                future = self._pending_requests[response.request_id]
                if not future.done():
                    future.set_result(response)
                    logger.debug(
                        f"Otrzymano odpowiedź na żądanie {response.request_id} od węzła {response.node_id}"
                    )

    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        """Pobiera informacje o węźle."""
        return self.nodes.get(node_id)

    def list_nodes(self, online_only: bool = False) -> List[NodeInfo]:
        """
        Pobiera listę węzłów.

        Args:
            online_only: Czy zwrócić tylko węzły online

        Returns:
            Lista węzłów
        """
        nodes = list(self.nodes.values())
        if online_only:
            nodes = [n for n in nodes if n.is_online]
        return nodes

    def find_nodes_by_skill(self, skill_name: str) -> List[NodeInfo]:
        """
        Znajduje węzły obsługujące dany skill.

        Args:
            skill_name: Nazwa skilla

        Returns:
            Lista węzłów obsługujących skill
        """
        return [
            node
            for node in self.nodes.values()
            if skill_name in node.capabilities.skills and node.is_online
        ]

    def find_nodes_by_tag(self, tag: str) -> List[NodeInfo]:
        """
        Znajduje węzły z danym tagiem.

        Args:
            tag: Tag do wyszukania (np. "location:server_room")

        Returns:
            Lista węzłów z tagiem
        """
        return [
            node
            for node in self.nodes.values()
            if tag in node.capabilities.tags and node.is_online
        ]

    def select_best_node(self, skill_name: str) -> Optional[NodeInfo]:
        """
        Wybiera najlepszy węzeł do wykonania skilla (load balancing).

        Strategia: wybiera węzeł z najmniejszym obciążeniem CPU i pamięci.

        Args:
            skill_name: Nazwa skilla

        Returns:
            Wybrany węzeł lub None jeśli brak dostępnych
        """
        candidates = self.find_nodes_by_skill(skill_name)
        if not candidates:
            return None

        # Sortuj po obciążeniu (CPU + pamięć + liczba aktywnych zadań)
        def load_score(node: NodeInfo) -> float:
            # Normalizuj active_tasks do zakresu 0-1 (przyjmując max 10 zadań)
            task_load = min(node.active_tasks / 10.0, 1.0)
            return node.cpu_usage + node.memory_usage + task_load

        return min(candidates, key=load_score)

    async def _healthcheck_loop(self):
        """Pętla sprawdzająca healthcheck węzłów."""
        while True:
            try:
                await asyncio.sleep(30)  # Sprawdzaj co 30 sekund

                timeout_threshold = datetime.now() - timedelta(
                    seconds=self.heartbeat_timeout
                )

                async with self._lock:
                    for node_id, node in list(self.nodes.items()):
                        if node.last_heartbeat < timeout_threshold and node.is_online:
                            logger.warning(
                                f"Węzeł {node.node_name} ({node_id}) nie odpowiada - oznaczam jako offline"
                            )
                            node.is_online = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Błąd w healthcheck loop: {e}")
