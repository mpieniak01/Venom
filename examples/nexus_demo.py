"""
Demo: The Nexus - Distributed Mesh Architecture

Ten skrypt demonstruje jak Venom może zarządzać rojem zdalnych węzłów (Venom Spores).

Scenariusz:
1. Uruchom Venom w trybie Nexus (master node)
2. Symuluj połączenie 2 węzłów Spore
3. Wykonaj zdalne zadania na węzłach
4. Pokaż load balancing i failover

WYMAGANIA:
- Venom uruchomiony z ENABLE_NEXUS=true
- Port 8765 wolny dla WebSocket
- Token uwierzytelniający skonfigurowany
"""

import asyncio
import sys
import time

import httpx

from venom_core.utils.url_policy import build_http_url

# Konfiguracja
NEXUS_API_URL = f"{build_http_url('localhost', 8000)}/api/v1"
NEXUS_WS_URL = "ws://localhost:8765/ws/nodes"


async def check_nexus_status():
    """Sprawdza czy Nexus jest dostępny."""
    print("🔍 Sprawdzam status Nexusa...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(build_http_url("localhost", 8000, "/healthz"))
            if response.status_code == 200:
                print("✅ Nexus działa")
                return True
    except Exception as e:
        print(f"❌ Nexus nie jest dostępny: {e}")
        print("\nUruchom Venom w trybie Nexus:")
        print("  export ENABLE_NEXUS=true")
        print("  export NEXUS_SHARED_TOKEN=demo-token-123")
        print("  cd venom_core && python main.py")
        return False


async def list_nodes():
    """Wyświetla listę zarejestrowanych węzłów."""
    print("\n📡 Lista węzłów:")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{NEXUS_API_URL}/nodes")
            if response.status_code == 200:
                data = response.json()
                nodes = data.get("nodes", [])

                if not nodes:
                    print("  Brak zarejestrowanych węzłów")
                    print("\n  Uruchom Venom Spore w osobnym terminalu:")
                    print("    cd venom_spore")
                    print("    export SPORE_SHARED_TOKEN=demo-token-123")
                    print("    python main.py")
                    return []

                for node in nodes:
                    status = "🟢 ONLINE" if node["is_online"] else "🔴 OFFLINE"
                    print(f"\n  {status} {node['node_name']}")
                    print(f"    ID: {node['node_id']}")
                    print(f"    Skills: {', '.join(node['capabilities']['skills'])}")
                    if node["capabilities"]["tags"]:
                        print(f"    Tags: {', '.join(node['capabilities']['tags'])}")
                    print(
                        f"    Resources: CPU={node['cpu_usage']:.0%}, MEM={node['memory_usage']:.0%}"
                    )
                    print(f"    Active tasks: {node['active_tasks']}")

                return nodes
            else:
                print(f"  ❌ Błąd: {response.status_code}")
                return []

    except Exception as e:
        print(f"  ❌ Błąd: {e}")
        return []


async def execute_on_node(
    node_id: str, skill_name: str, method_name: str, params: dict
):
    """Wykonuje skill na zdalnym węźle."""
    print(f"\n🎯 Wykonuję {skill_name}.{method_name} na węźle {node_id[:8]}...")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{NEXUS_API_URL}/nodes/{node_id}/execute",
                json={
                    "skill_name": skill_name,
                    "method_name": method_name,
                    "parameters": params,
                    "timeout": 30,
                },
            )

            if response.status_code == 200:
                data = response.json()
                if data["success"]:
                    print(f"✅ Wykonano w {data['execution_time']:.2f}s")
                    print("\nWynik:")
                    print(data["result"])
                    return data["result"]
                else:
                    print(f"❌ Błąd: {data['error']}")
                    return None
            else:
                print(f"❌ Błąd HTTP: {response.status_code}")
                return None

    except Exception as e:
        print(f"❌ Błąd: {e}")
        return None


async def demo_shell_execution(nodes):
    """Demo: Wykonanie komendy shell na zdalnym węźle."""
    print("\n" + "=" * 60)
    print("DEMO 1: Zdalne wykonanie komendy shell")
    print("=" * 60)

    # Znajdź węzeł z ShellSkill
    shell_nodes = [n for n in nodes if "ShellSkill" in n["capabilities"]["skills"]]

    if not shell_nodes:
        print("❌ Brak węzłów z ShellSkill")
        return

    node = shell_nodes[0]
    print(f"\n📍 Wybrany węzeł: {node['node_name']}")

    # Wykonaj komendę
    await execute_on_node(
        node_id=node["node_id"],
        skill_name="ShellSkill",
        method_name="run",
        params={"command": "echo 'Hello from remote node!' && uname -a"},
    )


async def demo_file_operations(nodes):
    """Demo: Operacje na plikach na zdalnym węźle."""
    print("\n" + "=" * 60)
    print("DEMO 2: Zdalne operacje na plikach")
    print("=" * 60)

    # Znajdź węzeł z FileSkill
    file_nodes = [n for n in nodes if "FileSkill" in n["capabilities"]["skills"]]

    if not file_nodes:
        print("❌ Brak węzłów z FileSkill")
        return

    node = file_nodes[0]
    print(f"\n📍 Wybrany węzeł: {node['node_name']}")

    # 1. Zapisz plik
    print("\n1️⃣ Tworzę plik test.txt...")
    await execute_on_node(
        node_id=node["node_id"],
        skill_name="FileSkill",
        method_name="write_file",
        params={
            "path": "demo_test.txt",
            "content": f"Test file created by Nexus at {time.strftime('%Y-%m-%d %H:%M:%S')}",
        },
    )

    await asyncio.sleep(1)

    # 2. Odczytaj plik
    print("\n2️⃣ Odczytuję plik test.txt...")
    await execute_on_node(
        node_id=node["node_id"],
        skill_name="FileSkill",
        method_name="read_file",
        params={"path": "demo_test.txt"},
    )

    await asyncio.sleep(1)

    # 3. Listuj pliki
    print("\n3️⃣ Listuję pliki w workspace...")
    await execute_on_node(
        node_id=node["node_id"],
        skill_name="FileSkill",
        method_name="list_files",
        params={"path": "."},
    )


async def demo_load_balancing(nodes):
    """Demo: Load balancing między węzłami."""
    print("\n" + "=" * 60)
    print("DEMO 3: Load Balancing")
    print("=" * 60)

    # Znajdź węzły z ShellSkill
    shell_nodes = [n for n in nodes if "ShellSkill" in n["capabilities"]["skills"]]

    if len(shell_nodes) < 2:
        print("⚠️ Potrzebne co najmniej 2 węzły z ShellSkill dla demo load balancingu")
        print(f"   Obecnie dostępne: {len(shell_nodes)} węzłów")
        return

    print(f"\n📍 Dostępne węzły: {len(shell_nodes)}")

    # Wykonaj kilka zadań sekwencyjnie
    for i in range(3):
        # Nexus powinien automatycznie wybrać najmniej obciążony węzeł
        # W tym demo wykonujemy manualnie na różnych węzłach
        node = shell_nodes[i % len(shell_nodes)]
        print(f"\n🎯 Zadanie {i + 1} -> {node['node_name']}")

        await execute_on_node(
            node_id=node["node_id"],
            skill_name="ShellSkill",
            method_name="run",
            params={"command": f"echo 'Task {i + 1} executed on {node['node_name']}'"},
        )

        await asyncio.sleep(0.5)


async def main():
    """Główna funkcja demo."""
    print("=" * 60)
    print("🦠 VENOM NEXUS - Distributed Mesh Demo")
    print("=" * 60)

    # Sprawdź czy Nexus działa
    if not await check_nexus_status():
        sys.exit(1)

    await asyncio.sleep(1)

    # Pobierz listę węzłów
    nodes = await list_nodes()

    if not nodes:
        print("\n⚠️ Brak połączonych węzłów")
        print("\nAby zobaczyć demo w akcji:")
        print("1. Uruchom Venom Spore w osobnym terminalu")
        print("2. Uruchom ten skrypt ponownie")
        sys.exit(0)

    online_nodes = [n for n in nodes if n["is_online"]]
    if not online_nodes:
        print("\n❌ Wszystkie węzły są offline")
        sys.exit(1)

    await asyncio.sleep(2)

    # Uruchom dema
    try:
        await demo_shell_execution(online_nodes)
        await asyncio.sleep(2)

        await demo_file_operations(online_nodes)
        await asyncio.sleep(2)

        await demo_load_balancing(online_nodes)

        print("\n" + "=" * 60)
        print("✅ Demo zakończone")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\n⚠️ Demo przerwane przez użytkownika")


if __name__ == "__main__":
    asyncio.run(main())
