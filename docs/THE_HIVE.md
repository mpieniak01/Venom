# THE HIVE - Architektura Rozproszonego Przetwarzania

## Przegląd

THE HIVE to architektura rozproszonego przetwarzania, która przekształca luźno połączone węzły Spore w jeden zsynchronizowany klaster obliczeniowy. System umożliwia równoległe wykonywanie zadań, dynamiczną dystrybucję obciążenia oraz synchronizację kodu między węzłami.

## Architektura

```
┌─────────────┐
│   NEXUS     │ ◄─── Master Node
│  (Master)   │
└──────┬──────┘
       │
       │ Redis Pub/Sub + Task Queue
       │
       ├────────────┬────────────┬────────────┐
       ▼            ▼            ▼            ▼
   ┌──────┐    ┌──────┐    ┌──────┐    ┌──────┐
   │Spore1│    │Spore2│    │Spore3│    │SporeN│
   │Worker│    │Worker│    │Worker│    │Worker│
   └──────┘    └──────┘    └──────┘    └──────┘
```

## Komponenty Główne

### 1. Message Broker (`venom_core/infrastructure/message_broker.py`)

**Rola:** Infrastruktura kolejkowania zadań oparty na Redis + ARQ.

**Funkcjonalność:**
- Zarządzanie kolejkami zadań (high_priority, background)
- Redis Pub/Sub dla broadcast control
- Monitoring statusu zadań
- Detekcja zombie tasks
- Retry mechanism dla nieudanych zadań

**Kolejki:**
- `venom:tasks:high` - Zadania wysokiego priorytetu (interakcje użytkownika)
- `venom:tasks:background` - Zadania w tle (scraping, training)
- `venom:broadcast` - Kanał broadcast (komendy systemowe)

**Przykład użycia:**
```python
from venom_core.infrastructure.message_broker import MessageBroker

# Inicjalizacja
broker = MessageBroker()
await broker.connect()

# Dodanie zadania do kolejki
task_id = await broker.enqueue_task(
    task_type="web_scraping",
    payload={"url": "https://example.com"},
    priority="background"
)

# Sprawdzenie statusu
status = await broker.get_task_status(task_id)
print(f"Status: {status.status}")

# Broadcast do wszystkich węzłów
await broker.broadcast_control("UPDATE_SYSTEM", {"version": "1.2.0"})
```

### 2. Foreman Agent (`venom_core/agents/foreman.py`)

**Rola:** Load Balancer & Watchdog dla klastra.

**Funkcjonalność:**
- Monitoring obciążenia węzłów (CPU, RAM, liczba zadań)
- Inteligentny routing zadań do najlepszych węzłów
- Watchdog - wykrywanie zombie tasks
- Automatyczny retry dla nieudanych zadań
- Zarządzanie statusem klastra

**Algorytm Load Balancing:**
```python
load_score = cpu_usage * 0.4 + memory_usage * 0.3 + (active_tasks/10) * 0.3
```
Węzeł z najniższym `load_score` jest wybierany dla nowego zadania.

**Przykład użycia:**
```python
from venom_core.agents.foreman import ForemanAgent

# Inicjalizacja
foreman = ForemanAgent(kernel, message_broker, node_manager)
await foreman.start()

# Wybór najlepszego węzła
node_id = foreman.select_best_node(task_requirements={"gpu": True})

# Przypisanie zadania
await foreman.assign_task("task_123", task_requirements={"gpu": True})

# Status klastra
status = foreman.get_cluster_status()
print(f"Węzły online: {status['online_nodes']}/{status['total_nodes']}")
print(f"Średnie obciążenie CPU: {status['avg_cpu_usage']}%")
```

### 3. Parallel Skill (`venom_core/execution/skills/parallel_skill.py`)

**Rola:** Umiejętność równoległego przetwarzania dla Architekta (Map-Reduce).

**Funkcjonalność:**
- `map_reduce()` - Przetwarzanie list elementów równolegle
- `parallel_execute()` - Równoległe wykonywanie pod-zadań
- `get_task_status()` - Sprawdzanie postępu zadań

**Map-Reduce Flow:**
1. **MAP** - Rozdzielenie zadania na N pod-zadań
2. **DISTRIBUTE** - Dodanie do kolejki Redis
3. **WAIT** - Asynchroniczne oczekiwanie na wyniki
4. **REDUCE** - Agregacja wyników

**Przykład użycia:**
```python
from venom_core.execution.skills.parallel_skill import ParallelSkill

skill = ParallelSkill(message_broker)

# Map-Reduce na liście URLi
urls = ["https://site1.com", "https://site2.com", "https://site3.com"]
result = await skill.map_reduce(
    task_description="Pobierz treść artykułu i stresuść do 3 zdań",
    items=json.dumps(urls),
    priority="high_priority",
    wait_timeout=300
)

# Wynik zawiera summary + results
data = json.loads(result)
print(f"Ukończone: {data['summary']['completed']}/{data['summary']['total_tasks']}")
```

### 4. OTA Manager (`venom_core/core/ota_manager.py`)

**Rola:** Over-The-Air Updates dla węzłów Spore.

**Funkcjonalność:**
- Tworzenie paczek aktualizacji (ZIP)
- Weryfikacja checksum (SHA256)
- Broadcast UPDATE_SYSTEM do węzłów
- Bezpieczna instalacja na węzłach
- Automatyczna instalacja zależności
- Backup plików przed nadpisaniem

**Proces aktualizacji:**
1. Nexus tworzy paczkę z nowym kodem
2. Nexus wysyła broadcast UPDATE_SYSTEM
3. Spores pobierają paczkę
4. Weryfikacja checksum
5. Rozpakowanie i kopiowanie plików
6. Instalacja zależności (`pip install`)
7. Restart procesu

**Przykład użycia (Nexus):**
```python
from venom_core.core.ota_manager import OTAManager

ota = OTAManager(message_broker)

# Tworzenie paczki
package = await ota.create_package(
    version="1.2.0",
    description="Nowe funkcje Hive",
    source_paths=[Path("venom_core"), Path("venom_spore")],
    include_dependencies=True
)

# Broadcast do węzłów
await ota.broadcast_update(package, target_nodes=["spore-1", "spore-2"])
```

**Przykład użycia (Spore):**
```python
# Nasłuchiwanie broadcast
pubsub = await message_broker.subscribe_broadcast()

async for message in pubsub.listen():
    if message["type"] == "message":
        data = json.loads(message["data"])
        if data["command"] == "UPDATE_SYSTEM":
            # Aplikuj aktualizację
            await ota.apply_update(
                package_url=data["data"]["package_url"],
                expected_checksum=data["data"]["checksum"],
                restart_after=True
            )
```

## Konfiguracja

### Docker Compose - Redis Stack

Domyślny stack Hive z Redis jest automatycznie dostępny w `StackManager`:

```yaml
version: '3.8'

services:
  redis:
    image: redis:alpine
    container_name: venom-hive-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    restart: unless-stopped
```

Wdrażanie stacka:
```python
from venom_core.infrastructure.stack_manager import StackManager

manager = StackManager()
success, msg = manager.deploy_default_hive_stack()
```

### Zmienne Środowiskowe (.env)

```bash
# THE_HIVE Configuration
ENABLE_HIVE=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Kolejki
HIVE_HIGH_PRIORITY_QUEUE=venom:tasks:high
HIVE_BACKGROUND_QUEUE=venom:tasks:background
HIVE_BROADCAST_CHANNEL=venom:broadcast

# Timeouty
HIVE_TASK_TIMEOUT=300
HIVE_MAX_RETRIES=3
HIVE_ZOMBIE_TASK_TIMEOUT=600
```

## Scenariusze Użycia

### 1. Masowe Przetwarzanie (Bulk Processing)

**Problem:** Pobierz i stresuść 20 artykułów z różnych stron.

**Rozwiązanie:**
```python
# Architect rozbija zadanie
urls = ["url1", "url2", ..., "url20"]

# Używa Parallel Skill
result = await parallel_skill.map_reduce(
    task_description="Pobierz artykuł i stresuść do 3 zdań",
    items=json.dumps(urls),
    priority="high_priority"
)

# 5 Spores pracuje jednocześnie (każdy po 4 artykuły)
# Czas: ~5x szybciej niż sekwencyjnie
```

### 2. Równoległe Skanowanie Repozytorium

**Problem:** Przeskanuj całe repozytorium pod kątem security issues.

**Rozwiązanie:**
```python
subtasks = [
    "Skanuj katalog /src",
    "Skanuj katalog /tests",
    "Skanuj katalog /config",
    "Skanuj zależności requirements.txt"
]

result = await parallel_skill.parallel_execute(
    task_description="Security audit repozytorium",
    subtasks=json.dumps(subtasks),
    priority="high_priority"
)
```

### 3. Automatyczna Aktualizacja Węzłów

**Problem:** Nexus otrzymał nową wersję kodu (PR merge).

**Rozwiązanie:**
```python
# 1. Tworzenie paczki
package = await ota.create_package(
    version="1.3.0",
    description="PR #45: Nowa funkcja X",
    source_paths=[Path("venom_core")],
    include_dependencies=True
)

# 2. Broadcast
await ota.broadcast_update(package)

# 3. Wszystkie Spores automatycznie:
#    - Pobiorą nowy kod
#    - Zweryfikują checksum
#    - Zainstalują zależności
#    - Zrestartują się
```

## Monitoring & Debugging

### Status Klastra

```python
# Foreman Status
status = foreman.get_cluster_status()
print(f"""
Węzły: {status['online_nodes']}/{status['total_nodes']} online
Średnie CPU: {status['avg_cpu_usage']}%
Średnia RAM: {status['avg_memory_usage']}%
Aktywne zadania: {status['total_active_tasks']}
""")
```

### Statystyki Kolejek

```python
stats = await message_broker.get_queue_stats()
print(f"""
High Priority Queue: {stats['high_priority_queue']}
Background Queue: {stats['background_queue']}
Pending: {stats['tasks_pending']}
Running: {stats['tasks_running']}
Completed: {stats['tasks_completed']}
Failed: {stats['tasks_failed']}
""")
```

### Zombie Tasks

```python
# Foreman automatycznie wykrywa i retry
zombies = await message_broker.detect_zombie_tasks()
for zombie in zombies:
    print(f"Zombie task: {zombie.task_id}, elapsed: {datetime.now() - zombie.started_at}")
```

## Best Practices

### 1. Idempotentność

Zadania powinny być idempotentne (bezpieczne do wielokrotnego wykonania):

```python
# ✅ DOBRZE - Idempotentne
async def process_url(url: str):
    # Sprawdź czy już przetworzone
    if await cache.exists(url):
        return await cache.get(url)
    
    # Przetwórz
    result = await scrape(url)
    await cache.set(url, result)
    return result

# ❌ ŹLE - Nie-idempotentne
async def increment_counter():
    counter = await db.get_counter()
    await db.set_counter(counter + 1)  # Przy retry zwiększy 2x!
```

### 2. Error Handling

Zawsze obsługuj błędy i zwracaj sensowne komunikaty:

```python
try:
    result = await process_task(task_data)
    await message_broker.update_task_status(task_id, "completed", result=result)
except Exception as e:
    logger.error(f"Task failed: {e}")
    await message_broker.update_task_status(task_id, "failed", error=str(e))
```

### 3. Timeouty

Ustaw rozsądne timeouty dla zadań długotrwałych:

```python
# Zadanie scraping (max 5 min)
await skill.map_reduce(
    task_description="Scrape articles",
    items=json.dumps(urls),
    wait_timeout=300  # 5 minut
)

# Zadanie ML inference (max 10 min)
await skill.parallel_execute(
    task_description="Run model inference",
    subtasks=json.dumps(batches),
    wait_timeout=600  # 10 minut
)
```

### 4. Priorytetyzacja

Używaj priorytetów świadomie:

```python
# High priority - interakcje użytkownika
await broker.enqueue_task("user_query", data, priority="high_priority")

# Background - zadania wsadowe
await broker.enqueue_task("bulk_scraping", data, priority="background")
```

## Rozwiązywanie Problemów

### Problem: Redis connection failed

**Rozwiązanie:**
```bash
# Sprawdź czy Redis działa
docker ps | grep redis

# Uruchom Redis stack
cd venom_core/infrastructure
docker compose up -d

# Lub użyj StackManager
python -c "from venom_core.infrastructure.stack_manager import StackManager; StackManager().deploy_default_hive_stack()"
```

### Problem: Zombie tasks

**Rozwiązanie:**
- Foreman automatycznie wykrywa i retry
- Sprawdź logi węzłów: `docker logs venom-spore-1`
- Zmień timeout jeśli zadania są intensywne:
  ```bash
  HIVE_ZOMBIE_TASK_TIMEOUT=1200  # 20 minut
  ```

### Problem: Węzeł offline

**Rozwiązanie:**
```python
# Sprawdź status węzłów
status = foreman.get_cluster_status()
for node in status['nodes']:
    if not node['is_online']:
        print(f"Node {node['node_name']} offline!")
        # Restart węzła
```

## Przykłady Integracji

### Integracja z Architect Agent

```python
# W promptcie Architekta można używać:
"""
Jeśli zadanie wymaga przetworzenia wielu elementów równolegle,
użyj ParallelSkill.map_reduce():

PRZYKŁAD:
Zadanie: "Pobierz 50 artykułów i wyciągnij kluczowe informacje"
Plan:
1. RESEARCHER - Znajdź 50 URLi artykułów
2. CODER - Użyj ParallelSkill.map_reduce() do równoległego przetworzenia
"""
```

### Integracja z Spore Nodes

```python
# W venom_spore/main.py
from venom_core.infrastructure.message_broker import MessageBroker

broker = MessageBroker()
await broker.connect()

# Nasłuchuj zadań
while True:
    task = await get_next_task_from_queue()
    result = await execute_skill(task)
    await broker.update_task_status(task.id, "completed", result=result)
```

## Metryki & Wydajność

### Throughput
- **Pojedynczy Spore:** ~10-20 zadań/minutę (zależnie od typu)
- **Klaster 5 Spores:** ~50-100 zadań/minutę
- **Speedup:** ~5x dla zadań równoległych

### Latencja
- **Task enqueue:** <10ms
- **Task routing (Foreman):** <50ms
- **Broadcast:** <100ms

### Skalowanie
- Linearne dla większości zadań
- Overhead Redis: marginalny (<5%)
- Bottleneck: Zazwyczaj I/O, nie CPU

## Roadmap

### Planowane Funkcje
- [ ] Dashboard Hive Monitor (wizualizacja klastra)
- [ ] Auto-scaling węzłów (Kubernetes)
- [ ] Priorytety wielopoziomowe (0-10)
- [ ] Task dependencies (DAG)
- [ ] Streaming results (partial results)

## Referencje

- [Redis Documentation](https://redis.io/docs/)
- [ARQ Documentation](https://arq-docs.helpmanual.io/)
- [MapReduce Paper](https://research.google/pubs/pub62/)
