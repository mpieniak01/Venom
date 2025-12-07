# Docker Compose Orchestration - Task 016_THE_CONSTRUCTOR

## Przegląd

Venom posiada teraz możliwość tworzenia i zarządzania środowiskami wielokontenerowymi (stackami) przy użyciu Docker Compose. Ta funkcjonalność przekształca Venoma z "skrypciarza" w "Inżyniera DevOps", który potrafi postawić pełną aplikację lokalnie (np. FastAPI + React + Redis + Postgres).

## Nowe Moduły

### 1. StackManager (`venom_core/infrastructure/stack_manager.py`)

Zarządca stacków Docker Compose. Wrapper na komendy `docker compose`.

**Kluczowe funkcje:**
- `deploy_stack(compose_content, stack_name)` - Wdraża stack z docker-compose.yml
- `destroy_stack(stack_name)` - Usuwa stack i czyści zasoby (`docker compose down -v`)
- `get_service_logs(stack_name, service)` - Pobiera logi konkretnego serwisu
- `get_running_stacks()` - Listuje aktywne stacki
- `get_stack_status(stack_name)` - Zwraca status stacka

**Przykład użycia:**
```python
from venom_core.infrastructure.stack_manager import StackManager

manager = StackManager()

compose_content = """
version: '3.8'
services:
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
"""

# Wdróż stack
success, msg = manager.deploy_stack(compose_content, "my-redis-stack")

# Pobierz logi
success, logs = manager.get_service_logs("my-redis-stack", "redis")

# Usuń stack
manager.destroy_stack("my-redis-stack")
```

### 2. Port Authority (`venom_core/utils/port_authority.py`)

Narzędzie do zarządzania portami i unikania konfliktów.

**Funkcje:**
- `is_port_in_use(port)` - Sprawdza czy port jest zajęty
- `find_free_port(start, end)` - Znajduje wolny port w zakresie
- `get_free_ports(count, start, end)` - Znajduje wiele wolnych portów

**Przykład użycia:**
```python
from venom_core.utils.port_authority import find_free_port, is_port_in_use

# Sprawdź czy port 8000 jest wolny
if is_port_in_use(8000):
    # Znajdź alternatywny port
    free_port = find_free_port(start=8000, end=9000)
    print(f"Użyj portu: {free_port}")
```

### 3. ComposeSkill (`venom_core/execution/skills/compose_skill.py`)

Plugin dla agentów z dekoratorami `@kernel_function`.

**Umiejętności (kernel functions):**
- `create_environment(compose_content, stack_name)` - Tworzy środowisko
- `destroy_environment(stack_name)` - Usuwa środowisko
- `check_service_health(stack_name, service_name)` - Sprawdza health serwisu
- `list_environments()` - Listuje aktywne środowiska
- `get_environment_status(stack_name)` - Pobiera status środowiska

**Zaawansowane funkcje:**
- Automatyczne zastępowanie placeholderów `{{PORT}}` wolnymi portami
- Wykrywanie konfliktów portów i znajdowanie alternatyw
- Izolacja workspace - każdy stack ma swój katalog w `workspace/stacks/`

**Przykład użycia przez agenta:**
```python
# Agent Coder automatycznie ma dostęp do ComposeSkill
# Może wykonywać takie operacje:

# 1. Stwórz środowisko
result = await compose_skill.create_environment("""
version: '3.8'
services:
  redis:
    image: redis:alpine
    ports:
      - "{{PORT}}:6379"
""", "app-cache")

# 2. Sprawdź status
status = await compose_skill.get_environment_status("app-cache")

# 3. Posprzątaj
await compose_skill.destroy_environment("app-cache")
```

## Integracja z Agentami

### CoderAgent

CoderAgent ma teraz dostęp do ComposeSkill. W systemowym prompcie dodano:

```
MASZ DOSTĘP DO ORKIESTRACJI DOCKER COMPOSE:
- create_environment: Stwórz środowisko wielokontenerowe
- destroy_environment: Usuń środowisko i posprzątaj zasoby
- check_service_health: Sprawdź logi i status serwisu
- list_environments: Zobacz aktywne środowiska
```

### ArchitectAgent

Architekt rozpoznaje teraz potrzeby infrastrukturalne i potrafi zaplanować "Infrastructure Setup".

**Nowy przykład w prompcie planowania:**

```json
{
  "steps": [
    {
      "step_number": 1,
      "agent_type": "CODER",
      "instruction": "Stwórz docker-compose.yml z serwisami: python-api (FastAPI) i redis. Użyj ComposeSkill.create_environment() aby wdrożyć stack o nazwie 'todo-stack'",
      "depends_on": null
    },
    {
      "step_number": 2,
      "agent_type": "CODER",
      "instruction": "Stwórz plik main.py z FastAPI, endpointy POST/GET /todos, używaj redis (host='redis') do przechowywania zadań",
      "depends_on": 1
    }
  ]
}
```

## Kryteria Akceptacji (DoD)

### ✅ Scenariusz Full-Stack

**Użytkownik:** "Stwórz prostą aplikację todo z API w Pythonie i bazą Redis do przechowywania zadań"

**Venom:**
1. ✅ Tworzy `docker-compose.yml` z serwisami (Python API, Redis)
2. ✅ Generuje kod API (`main.py`) używający hosta `redis`
3. ✅ Uruchamia stack używając `create_environment()`
4. Testuje endpoint (wymaga GuardianAgent - przyszła integracja)
5. ✅ Zgłasza gotowość

### ✅ Zarządzanie Zasobami

- ✅ Po zakończeniu pracy, Venom może usunąć kontenery i sieci używając `destroy_environment()`
- ✅ Funkcja `destroy_stack()` usuwa wolumeny (`-v` flag)

### ✅ Odporność na Konflikty

- ✅ System automatycznie wykrywa zajęte porty
- ✅ Placeholder `{{PORT}}` jest zastępowany wolnym portem
- ✅ Preferowane porty: `{{PORT:8000}}` - próbuje użyć 8000, jeśli zajęty znajduje alternatywę

## Workspace Isolation

Każdy stack ma swój izolowany katalog:

```
workspace/
└── stacks/
    ├── todo-stack/
    │   └── docker-compose.yml
    ├── api-stack/
    │   └── docker-compose.yml
    └── test-env/
        └── docker-compose.yml
```

## Networking

**Ważne:** Venom (host) widzi serwisy na `localhost:MAPPED_PORT`, ale serwisy widzą siebie nawzajem po nazwach usług:

```yaml
# docker-compose.yml
services:
  api:
    # ...
    environment:
      - REDIS_HOST=redis  # Nie localhost!
      
  redis:
    # ...
```

## Testy

### Unit Tests

- ✅ `tests/test_port_authority.py` - 10 testów (100% pass)
- ✅ `tests/test_stack_manager.py` - 12 testów (100% pass)
- ✅ `tests/test_compose_skill.py` - Testy umiejętności ComposeSkill

### Integration Tests

- ✅ `tests/test_compose_integration.py` - Scenariusze full-stack
  - Redis integration
  - Multi-service stack
  - Port conflict handling
  - Workspace isolation

## Wymagania Techniczne

### Zależności

- Docker Engine (testowane na v28.0.4)
- Docker Compose (CLI v2 - `docker compose`)
- Python 3.10+

### Python Packages

Wszystkie wymagane pakiety są już w `requirements.txt`:
- `docker` - Docker SDK dla Python
- `pydantic-settings` - Walidacja konfiguracji

## Wskazówki Techniczne

### Docker-in-Docker vs Socket

Venom używa standardowego CLI `docker compose` przez `subprocess`. Działa na hoście, nie wymaga Docker-in-Docker.

### Timeouts

- `deploy_stack`: 300 sekund (5 minut)
- `destroy_stack`: 120 sekund (2 minuty)
- `get_service_logs`: 30 sekund
- `check_docker_compose`: 10 sekund

### Error Handling

Wszystkie funkcje zwracają krotkę `(success: bool, message: str)`:

```python
success, message = manager.deploy_stack(content, name)
if success:
    print(f"✅ {message}")
else:
    print(f"❌ {message}")
```

## Przyszłe Rozszerzenia

### Dashboard Integration (Phase 5 - Future)

Planowana nowa zakładka "Environments" w web UI:
- Kafelki z aktywnymi stackami
- Status kontenerów (🟢/🔴)
- Linki do wystawionych portów (np. `http://localhost:8081`)
- Przycisk "Stop" dla każdego stacka

### Health Checks

GuardianAgent mógłby używać `check_service_health()` do:
- Weryfikacji czy API odpowiada
- Sprawdzania logów pod kątem błędów
- Testowania endpointów (curl/httpx)

## Przykłady Użycia

### Przykład 1: Prosta aplikacja z Redis

```python
compose_content = """
version: '3.8'
services:
  app:
    image: python:3.11-slim
    command: python app.py
    volumes:
      - ./:/app
    working_dir: /app
    depends_on:
      - redis
    environment:
      - REDIS_HOST=redis
      
  redis:
    image: redis:alpine
    ports:
      - "{{PORT:6379}}:6379"
"""

await compose_skill.create_environment(compose_content, "my-app")
```

### Przykład 2: Full-stack z PostgreSQL

```python
compose_content = """
version: '3.8'
services:
  api:
    image: python:3.11-slim
    ports:
      - "{{PORT:8000}}:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mydb
    depends_on:
      - db
      
  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=mydb
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
"""

await compose_skill.create_environment(compose_content, "fullstack-app")
```

## Troubleshooting

### Problem: "Docker Compose nie jest dostępny"

**Rozwiązanie:** Upewnij się że masz zainstalowany Docker Compose v2:
```bash
docker compose version
```

### Problem: "Timeout podczas wdrażania stacka"

**Rozwiązanie:** 
- Zwiększ timeout w `deploy_stack(timeout=600)`
- Sprawdź czy obrazy Docker są już pobrane
- Sprawdź logi: `docker compose logs`

### Problem: "Port już zajęty"

**Rozwiązanie:** 
- Użyj placeholdera `{{PORT}}` zamiast hardcoded portu
- System automatycznie znajdzie wolny port

### Problem: "Stack nie startuje"

**Rozwiązanie:**
```python
# Sprawdź logi
success, logs = manager.get_service_logs("my-stack", "my-service")
print(logs)

# Sprawdź status
success, status = manager.get_stack_status("my-stack")
print(status)
```

## Podsumowanie

Venom posiada teraz pełną infrastrukturę do orkiestracji środowisk wielokontenerowych:

1. ✅ **StackManager** - Niskopoziomowe zarządzanie docker-compose
2. ✅ **Port Authority** - Inteligentne zarządzanie portami
3. ✅ **ComposeSkill** - High-level interfejs dla agentów
4. ✅ **Integracja z Agentami** - Coder i Architect rozumieją infrastrukturę
5. ✅ **Testy** - 22+ testy jednostkowe i integracyjne

System jest gotowy do tworzenia złożonych aplikacji wymagających wielu serwisów (bazy danych, cache, kolejki, API).
