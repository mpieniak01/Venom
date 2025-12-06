# Venom Core Nervous System V1 - Dokumentacja

## Przegląd

Core Nervous System V1 to MVP systemu zarządzania zadaniami asynchronicznymi dla projektu Venom. System umożliwia przyjmowanie zadań przez API, przetwarzanie ich w tle oraz zarządzanie ich stanem z persystencją do pliku.

## Architektura

### Komponenty

1. **Models** (`venom_core/core/models.py`)
   - `TaskStatus`: Enum statusów zadania (PENDING, PROCESSING, COMPLETED, FAILED)
   - `VenomTask`: Model zadania z pełnymi metadanymi
   - `TaskRequest`: DTO dla tworzenia zadania
   - `TaskResponse`: DTO odpowiedzi po utworzeniu zadania

2. **StateManager** (`venom_core/core/state_manager.py`)
   - Zarządzanie stanem zadań w pamięci
   - Automatyczna persystencja do pliku JSON
   - Ładowanie stanu przy starcie
   - Obsługa błędów I/O

3. **Orchestrator** (`venom_core/core/orchestrator.py`)
   - Przyjmowanie zadań do przetwarzania
   - Asynchroniczne wykonywanie zadań w tle
   - Logowanie wszystkich etapów
   - Obsługa błędów z automatycznym ustawianiem statusu FAILED

4. **API** (`venom_core/main.py`)
   - REST API oparte na FastAPI
   - Trzy główne endpointy do zarządzania zadaniami

## API Endpoints

### 1. Utworzenie zadania
```bash
POST /api/v1/tasks
Content-Type: application/json

{
  "content": "Treść zadania"
}
```

**Odpowiedź:**
```json
{
  "task_id": "uuid",
  "status": "PENDING"
}
```

### 2. Pobranie szczegółów zadania
```bash
GET /api/v1/tasks/{task_id}
```

**Odpowiedź:**
```json
{
  "id": "uuid",
  "content": "Treść zadania",
  "created_at": "2025-12-06T14:22:52.927944",
  "status": "COMPLETED",
  "result": "Przetworzono: Treść zadania",
  "logs": [
    "Zadanie uruchomione: 2025-12-06T14:22:52.928194",
    "Rozpoczęto przetwarzanie: 2025-12-06T14:22:52.929935",
    "Zakończono przetwarzanie: 2025-12-06T14:22:54.931036"
  ]
}
```

### 3. Lista wszystkich zadań
```bash
GET /api/v1/tasks
```

**Odpowiedź:**
```json
[
  {
    "id": "uuid",
    "content": "Treść zadania",
    ...
  },
  ...
]
```

## Uruchomienie

### Instalacja zależności
```bash
pip install fastapi uvicorn pydantic pydantic-settings loguru
```

### Uruchomienie serwera
```bash
uvicorn venom_core.main:app --host 0.0.0.0 --port 8000
```

### Przykładowe użycie

```bash
# Utworzenie zadania
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"content": "Moje zadanie"}'

# Pobranie statusu
curl http://localhost:8000/api/v1/tasks/{task_id}

# Lista wszystkich zadań
curl http://localhost:8000/api/v1/tasks
```

## Persystencja

System automatycznie zapisuje stan wszystkich zadań do pliku `data/memory/state_dump.json`. 
Po restarcie serwera, stan jest automatycznie przywracany z pliku.

### Konfiguracja

Ścieżkę do pliku stanu można skonfigurować w pliku `.env`:
```
STATE_FILE_PATH=./data/memory/state_dump.json
```

## Testowanie

### Uruchomienie testów
```bash
# Wszystkie testy
pytest tests/

# Tylko testy integracyjne
pytest tests/test_core_nervous_system.py

# Tylko testy jednostkowe
pytest tests/test_state_and_orchestrator.py
```

### Pokrycie testami

- ✅ 9 testów integracyjnych (API, async execution)
- ✅ 13 testów jednostkowych (StateManager, Orchestrator)
- ✅ Przypadki brzegowe i obsługa błędów
- ✅ Persystencja i odtwarzanie stanu

## Obsługa błędów

System obsługuje następujące przypadki:

1. **Nieistniejące zadanie**: HTTP 404
2. **Niepoprawny request**: HTTP 422
3. **Błąd wewnętrzny**: HTTP 500 (bez ujawniania szczegółów)
4. **Uszkodzony plik stanu**: Start z pustym stanem + log błędu
5. **Błąd podczas przetwarzania**: Status FAILED + log błędu
6. **Błąd zapisu stanu**: Log błędu, próba kontynuacji

## Ograniczenia MVP

- Mono-procesowy / mono-instancyjny
- Zadania wykonywane lokalnie (symulacja z delay 2s)
- Brak kolejki produkcyjnej
- Brak bazy danych
- Brak mechanizmów retry
- Brak priorytetów zadań

## Przyszłe rozszerzenia

- Migracja do bazy danych (PostgreSQL/MongoDB)
- Implementacja kolejki zadań (Redis/RabbitMQ)
- Rozproszone workery
- Mechanizmy retry i priorytety
- Monitoring i metryki
- Autentykacja i autoryzacja
- WebSocket dla real-time updates
