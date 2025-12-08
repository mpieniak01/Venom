# Venom Spore - Klient Węzła Rozproszonego

Venom Spore to lekki klient, który pozwala na rozszerzenie możliwości Venoma poprzez wykonywanie zadań na zdalnych maszynach.

## 🎯 Czym jest Venom Spore?

Venom Spore ("Zarodnik") to mniejsza, uproszczona wersja Venoma, która:
- **Nie wymaga** bazy danych ani modeli LLM
- Łączy się z głównym Venomem (Nexus) przez WebSocket
- Udostępnia swoje zasoby lokalne (Shell, File, Camera, etc.)
- Wykonuje polecenia otrzymane od Nexusa i zwraca wyniki

## 📦 Instalacja

### Wymagania
- Python 3.10+
- `websockets` i `psutil` (instalowane automatycznie)

### Szybki start

```bash
# Z głównego katalogu Venom
cd venom_spore

# Uruchom klienta
python main.py
```

## ⚙️ Konfiguracja

Konfiguracja odbywa się przez zmienne środowiskowe lub plik `.env`:

```bash
# Podstawowa konfiguracja
SPORE_NODE_NAME=venom-spore-1        # Nazwa węzła
SPORE_NEXUS_HOST=localhost           # Adres IP Nexusa
SPORE_NEXUS_PORT=8765                # Port WebSocket Nexusa
SPORE_SHARED_TOKEN=your-secret-token # Token uwierzytelniający

# Możliwości węzła
SPORE_ENABLE_SHELL=true              # Włącz ShellSkill
SPORE_ENABLE_FILE=true               # Włącz FileSkill
SPORE_ENABLE_DOCKER=false            # Włącz Docker (jeśli dostępny)
SPORE_ENABLE_CAMERA=false            # Włącz Camera (jeśli dostępna)

# Tagi opisujące węzeł (opcjonalne)
SPORE_NODE_TAGS=location:server_room,gpu

# Heartbeat
SPORE_HEARTBEAT_INTERVAL=30          # Interwał heartbeat w sekundach
```

## 🚀 Przykłady użycia

### 1. Lokalne uruchomienie (testowe)

```bash
# Terminal 1: Uruchom Venom w trybie Nexus
cd venom_core
export ENABLE_NEXUS=true
export NEXUS_SHARED_TOKEN=test-token-123
python main.py

# Terminal 2: Uruchom Venom Spore
cd venom_spore
export SPORE_SHARED_TOKEN=test-token-123
python main.py
```

### 2. Raspberry Pi jako węzeł z kamerą

```bash
# Na Raspberry Pi
cd venom_spore
export SPORE_NODE_NAME=rider-pi
export SPORE_NEXUS_HOST=192.168.1.10  # IP komputera z Nexusem
export SPORE_SHARED_TOKEN=your-token
export SPORE_NODE_TAGS=location:office,camera,sensor
export SPORE_ENABLE_CAMERA=true
python main.py
```

### 3. VPS jako węzeł do web scrapingu

```bash
# Na serwerze VPS
cd venom_spore
export SPORE_NODE_NAME=scraper-vps
export SPORE_NEXUS_HOST=your-nexus-ip
export SPORE_SHARED_TOKEN=your-token
export SPORE_NODE_TAGS=location:cloud,scraper
python main.py
```

## 🐳 Docker (rekomendowane)

### Uruchomienie w kontenerze

```dockerfile
# Dockerfile dla Venom Spore
FROM python:3.11-slim

WORKDIR /app
COPY venom_spore/ /app/
COPY venom_core/nodes/ /app/venom_core/nodes/

RUN pip install websockets psutil pydantic pydantic-settings

CMD ["python", "main.py"]
```

```bash
# Build
docker build -t venom-spore .

# Uruchom
docker run -e SPORE_NEXUS_HOST=host.docker.internal \
           -e SPORE_SHARED_TOKEN=your-token \
           -e SPORE_NODE_NAME=spore-docker-1 \
           venom-spore
```

### Docker Compose (symulacja roju)

```yaml
version: '3.8'

services:
  spore-1:
    build: .
    environment:
      - SPORE_NODE_NAME=spore-1
      - SPORE_NEXUS_HOST=host.docker.internal
      - SPORE_SHARED_TOKEN=test-token-123
      - SPORE_NODE_TAGS=worker,docker

  spore-2:
    build: .
    environment:
      - SPORE_NODE_NAME=spore-2
      - SPORE_NEXUS_HOST=host.docker.internal
      - SPORE_SHARED_TOKEN=test-token-123
      - SPORE_NODE_TAGS=worker,docker
```

## 🔧 Obsługiwane Skills

### ShellSkill
Wykonywanie komend shell na węźle.

```python
# Z poziomu Nexusa (przez API)
POST /api/v1/nodes/{node_id}/execute
{
    "skill_name": "ShellSkill",
    "method_name": "run",
    "parameters": {
        "command": "ls -la"
    }
}
```

### FileSkill
Operacje na plikach w workspace węzła.

```python
# Odczyt pliku
{
    "skill_name": "FileSkill",
    "method_name": "read_file",
    "parameters": {
        "path": "data/config.txt"
    }
}

# Zapis pliku
{
    "skill_name": "FileSkill",
    "method_name": "write_file",
    "parameters": {
        "path": "output.txt",
        "content": "Hello from remote node"
    }
}

# Listowanie plików
{
    "skill_name": "FileSkill",
    "method_name": "list_files",
    "parameters": {
        "path": "."
    }
}
```

## 📊 Monitoring

Sprawdź status węzłów przez API Nexusa:

```bash
# Lista wszystkich węzłów
GET http://localhost:8000/api/v1/nodes

# Informacje o konkretnym węźle
GET http://localhost:8000/api/v1/nodes/{node_id}
```

## 🔒 Bezpieczeństwo

⚠️ **WAŻNE:** Venom Spore wykonuje komendy shell przekazane przez Nexus.
Upewnij się, że:

1. **Token jest tajny** - nie commituj go do repo
2. **Sieć jest zaufana** - używaj VPN lub firewall
3. **Workspace jest izolowany** - ograniczony dostęp do systemu
4. **Komendy są walidowane** - (TODO: implementacja whitelisty)

## 🛠️ Rozwój i dodawanie nowych Skills

Aby dodać nowy skill do Spore:

1. Edytuj `skill_executor.py`
2. Dodaj handler w `SkillExecutor.execute()`
3. Zaktualizuj `get_capabilities()` aby zawierał nowy skill

Przykład:

```python
async def _handle_my_skill(self, method_name: str, parameters: dict) -> str:
    if method_name == "do_something":
        # Twoja logika
        return "Result"
```

## 🐛 Troubleshooting

### Węzeł nie może się połączyć

```
❌ Nie można połączyć się z Nexusem
```

**Rozwiązania:**
- Sprawdź czy Nexus działa: `curl http://localhost:8000/healthz`
- Sprawdź czy `ENABLE_NEXUS=true` w konfiguracji Nexusa
- Sprawdź firewall i czy port 8765 jest otwarty

### Błąd autoryzacji

```
❌ Authentication failed
```

**Rozwiązanie:**
- Upewnij się, że `SPORE_SHARED_TOKEN` = `NEXUS_SHARED_TOKEN`

### Węzeł oznaczony jako offline

**Możliwe przyczyny:**
- Brak heartbeat przez > 60s (domyślny timeout)
- Problemy sieciowe
- Węzeł został zamknięty

## 📚 Więcej informacji

- [Główny README Venoma](../README.md)
- [Dokumentacja API](../docs/api.md)
- [Przykłady użycia](../examples/)

## 🤝 Wkład

Venom Spore jest częścią projektu Venom. Pull requesty mile widziane!

## 📄 Licencja

Ten kod jest częścią projektu Venom i podlega tej samej licencji.
