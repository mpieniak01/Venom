"""Główny moduł Venom Spore - klient węzła rozproszonego."""

import asyncio
import json
import signal
import sys
import time
from datetime import datetime

import psutil
import websockets
from websockets.exceptions import ConnectionClosed

from venom_spore.config import SPORE_SETTINGS
from venom_spore.skill_executor import SkillExecutor

# Import protokołu z venom_core
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
from venom_core.nodes.protocol import (
    Capabilities,
    HeartbeatMessage,
    MessageType,
    NodeHandshake,
    NodeMessage,
    NodeResponse,
    SkillExecutionRequest,
)


class VenomSpore:
    """Klient Venom Spore - lekki węzeł wykonawczy."""

    def __init__(self):
        """Inicjalizacja Venom Spore."""
        self.settings = SPORE_SETTINGS
        self.executor = SkillExecutor()
        self.node_id = None
        self.websocket = None
        self.running = False
        self.active_tasks = 0

    async def connect(self):
        """Łączy się z Nexusem (master node)."""
        nexus_uri = (
            f"ws://{self.settings.NEXUS_HOST}:{self.settings.NEXUS_PORT}/ws/nodes"
        )
        print(f"🔌 Łączenie z Nexusem: {nexus_uri}")

        try:
            self.websocket = await websockets.connect(nexus_uri)
            print("✅ Połączono z Nexusem")

            # Wyślij handshake
            await self._send_handshake()

            # Uruchom heartbeat
            asyncio.create_task(self._heartbeat_loop())

            # Pętla odbierania wiadomości
            await self._message_loop()

        except ConnectionRefusedError:
            print(f"❌ Nie można połączyć się z Nexusem na {nexus_uri}")
            print("   Sprawdź czy Venom działa w trybie Nexus (ENABLE_NEXUS=true)")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Błąd połączenia: {e}")
            sys.exit(1)

    async def _send_handshake(self):
        """Wysyła handshake do Nexusa."""
        # Pobierz możliwości węzła
        caps_dict = self.executor.get_capabilities()

        # Parsuj tagi
        tags = []
        if self.settings.NODE_TAGS:
            tags = [tag.strip() for tag in self.settings.NODE_TAGS.split(",")]

        capabilities = Capabilities(
            skills=caps_dict["skills"],
            tags=tags,
            cpu_cores=caps_dict["cpu_cores"],
            memory_mb=caps_dict["memory_mb"],
            has_gpu=caps_dict["has_gpu"],
            has_docker=caps_dict["has_docker"],
            platform=caps_dict["platform"],
        )

        handshake = NodeHandshake(
            node_name=self.settings.NODE_NAME,
            capabilities=capabilities,
            token=self.settings.SHARED_TOKEN.get_secret_value(),
        )

        self.node_id = handshake.node_id

        message = NodeMessage.from_handshake(handshake)
        await self.websocket.send(json.dumps(message.model_dump()))

        print(f"📡 Wysłano handshake jako: {self.settings.NODE_NAME}")
        print(f"   Node ID: {self.node_id}")
        print(f"   Skills: {', '.join(capabilities.skills)}")
        if tags:
            print(f"   Tags: {', '.join(tags)}")

    async def _heartbeat_loop(self):
        """Pętla wysyłająca heartbeat."""
        while self.running:
            try:
                await asyncio.sleep(self.settings.HEARTBEAT_INTERVAL)

                # Pobierz statystyki
                cpu_usage = psutil.cpu_percent(interval=1) / 100.0
                memory = psutil.virtual_memory()
                memory_usage = memory.percent / 100.0

                heartbeat = HeartbeatMessage(
                    node_id=self.node_id,
                    cpu_usage=cpu_usage,
                    memory_usage=memory_usage,
                    active_tasks=self.active_tasks,
                )

                message = NodeMessage.from_heartbeat(heartbeat)
                await self.websocket.send(json.dumps(message.model_dump()))

                print(
                    f"💓 Heartbeat: CPU={cpu_usage:.2f}, MEM={memory_usage:.2f}, Tasks={self.active_tasks}"
                )

            except ConnectionClosed:
                print("❌ Połączenie z Nexusem zostało zamknięte")
                break
            except Exception as e:
                print(f"⚠️ Błąd w heartbeat: {e}")

    async def _message_loop(self):
        """Pętla odbierająca wiadomości od Nexusa."""
        self.running = True
        print("👂 Nasłuchuję poleceń od Nexusa...")

        try:
            async for message_str in self.websocket:
                try:
                    message_dict = json.loads(message_str)
                    message = NodeMessage(**message_dict)

                    if message.message_type == MessageType.EXECUTE_SKILL:
                        await self._handle_skill_execution(message.payload)
                    else:
                        print(f"⚠️ Nieznany typ wiadomości: {message.message_type}")

                except Exception as e:
                    print(f"❌ Błąd parsowania wiadomości: {e}")

        except ConnectionClosed:
            print("❌ Połączenie z Nexusem zostało zamknięte")
        finally:
            self.running = False

    async def _handle_skill_execution(self, payload: dict):
        """
        Obsługuje żądanie wykonania skilla.

        Args:
            payload: Dane żądania
        """
        request = SkillExecutionRequest(**payload)

        print(f"\n🎯 Otrzymano polecenie: {request.skill_name}.{request.method_name}")
        print(f"   Request ID: {request.request_id}")

        self.active_tasks += 1
        start_time = time.time()

        try:
            # Wykonaj skill
            result = await self.executor.execute(
                skill_name=request.skill_name,
                method_name=request.method_name,
                parameters=request.parameters,
            )

            execution_time = time.time() - start_time

            # Wyślij odpowiedź
            response = NodeResponse(
                request_id=request.request_id,
                node_id=self.node_id,
                success=True,
                result=result,
                execution_time=execution_time,
            )

            print(f"✅ Wykonano w {execution_time:.2f}s")

        except Exception as e:
            execution_time = time.time() - start_time

            response = NodeResponse(
                request_id=request.request_id,
                node_id=self.node_id,
                success=False,
                error=str(e),
                execution_time=execution_time,
            )

            print(f"❌ Błąd: {e}")

        finally:
            self.active_tasks -= 1

        # Wyślij odpowiedź
        message = NodeMessage.from_response(response)
        await self.websocket.send(json.dumps(message.model_dump()))

    async def disconnect(self):
        """Rozłącza się z Nexusem."""
        if self.websocket:
            await self.websocket.close()
            print("👋 Rozłączono z Nexusem")


async def main():
    """Główna funkcja."""
    print("=" * 60)
    print("🦠 VENOM SPORE - Distributed Node Client")
    print("=" * 60)

    spore = VenomSpore()

    # Obsługa sygnałów
    def signal_handler(sig, frame):
        print("\n⚠️ Otrzymano sygnał przerwania")
        asyncio.create_task(spore.disconnect())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Połącz się z Nexusem
    await spore.connect()


if __name__ == "__main__":
    asyncio.run(main())
