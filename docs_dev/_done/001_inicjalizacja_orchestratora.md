## 1. Kontekst i cel projektu
Venom ma być lekkim, asynchronicznym systemem obsługi zadań („task queue / orchestrator / state manager”). Wersja MVP działa w pamięci + zapisuje stan do pliku, bez skomplikowanej infrastruktury.
Celem jest umożliwienie przyjmowania zadań, zarządzania ich stanami, uruchamiania ich w tle i zwracania wyników — prostym API — stanowiąc fundament pod przyszłe rozszerzenia.

### 1.1 Zakres projektu
- Core logic: modele danych, zarządzanie stanem, orchestrator, API.
- Persistence: zapis stanu do pliku (memory + dump).
- Background execution: asynchroniczne wykonywanie zadań.
- Testowanie: asynchroniczny test integracyjny.
- MVP / prototyp — bez zaawansowanej skalowalności, bez zewnętrznej bazy, bez kolejek produkcyjnych.

## 2. User Story / Wymagania od użytkownika

**Jako** użytkownik backendu / systemu,
**Chcę** mieć możliwość wysyłania zadań do systemu przez API,
**Aby** asynchronicznie wykonywać te zadania w tle, sprawdzać ich status i pobierać wynik, bez manualnej obsługi kolejki czy workerów.

**Akceptacja (Acceptance Criteria):**
- Możliwość wysłania zadania (POST) → otrzymanie unikalnego `task_id` i statusu `PENDING`.
- Możliwość zapytania statusu zadania przed wykonaniem (GET).
- Po wykonaniu zadania status zmienia się na `COMPLETED`, wynik jest dostępny.
- Zadania wykonywane asynchronicznie — nie blokują głównego wątku.
- Stan systemu — pamięć + dump do pliku — umożliwia restart bez utraty stanu.

## 3. Wymagania funkcjonalne

### 3.1 Modele danych
- `TaskStatus` (Enum): `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`
- `VenomTask`:
  - `id`: UUID (domyślnie generowany)
  - `content`: str
  - `created_at`: datetime
  - `status`: TaskStatus
  - `result`: Optional[str]
  - `logs`: List[str]
- `TaskRequest`: DTO — zawiera `content: str`
- `TaskResponse`: DTO — zawiera `task_id: UUID`, `status: TaskStatus`

### 3.2 Zarządzanie stanem (StateManager)
- Przechowywanie zadań w pamięci: `Dict[UUID, VenomTask]`
- Metoda do tworzenia zadania: `create_task(content: str) -> VenomTask`
- Metoda do pobierania zadania: `get_task(task_id: UUID) -> Optional[VenomTask]`
- Metoda do aktualizacji statusu (+ opcjonalnie result): `update_status(task_id: UUID, status: TaskStatus, result: Optional[str] = None)`
- Persistencja: asynchroniczna metoda `_save()` zapisująca stan do pliku np. `data/memory/state_dump.json` przy każdej zmianie

### 3.3 Orkiestrator (Orchestrator)
- Inicjalizacja / injekcja `StateManager`
- Metoda `submit_task(request: TaskRequest)`
  - Tworzy zadanie przez `StateManager`
  - Loguje event (np. start zadania)
  - Tworzy tło zadania: `asyncio.create_task(self._run_task(task_id))`
- Metoda `_run_task(task_id: UUID)`
  - Pobiera zadanie
  - Ustawia status `PROCESSING` i zapisuje stan
  - Symuluje wykonanie (np. `await asyncio.sleep(2)`)
  - Po zakończeniu: ustawia status `COMPLETED`, wypełnia `result`, zapisuje stan + log

## 4. API – interfejs HTTP (np. przy użyciu FastAPI)

| Endpoint | Metoda | Wejście (request) | Wyjście (response) | Uwagi / błędy |
|---------|--------|------------------|-------------------|---------------|
| `/api/v1/tasks` | POST | JSON — `TaskRequest` | JSON — `TaskResponse` (task_id + status) | 400 przy błędnym body, 500 przy błędzie wewnętrznym |
| `/api/v1/tasks/{task_id}` | GET | — | JSON — `VenomTask` | 404 jeśli task_id nie istnieje |
| `/api/v1/tasks` | GET | — | JSON — lista `List[VenomTask]` | — |

## 5. Wymagania niefunkcjonalne / jakościowe

- **Trwałość stanu:** stan zapisywany do pliku przy każdej zmianie lub co określoną częstotliwość — by po restarcie nie utracić danych.
- **Odporność na błędy I/O:** w przypadku błędów zapisu/odczytu — logowanie błędu, ewentualny retry lub czysta inicjalizacja z pustym stanem.
- **Czytelność i spójność kodu:** pełne typowanie (type hints), formatowanie zgodne ze stylem (np. `ruff`), dobra struktura kodu.
- **Rozszerzalność:** chociaż MVP jest prosty — architektura ma umożliwiać łatwą migrację do rozwiązań produkcyjnych (baza danych, kolejka, workerzy).
- **Testowalność i weryfikowalność:** każda funkcjonalność i wymaganie powinno być możliwe do przetestowania (testy integracyjne, jednostkowe, przypadki błędów, edge-cases).

## 6. Obsługa błędów i przypadków brzegowych

- Żądanie GET z nieistniejącym `task_id` → HTTP 404 + czytelny komunikat.
- Plik stanu nie istnieje / jest uszkodzony przy starcie — decyzja: ładowanie stanu jako pusty lub podniesienie błędu.
- Błąd w trakcie zapisu / odczytu stanu → log + próba ponownego zapisu / fallback.
- Background task wyrzuci wyjątek → status `FAILED`, zapis loga, możliwa retry lub informacja użytkownikowi.
- Restart aplikacji przy zadaniach w stanie `PROCESSING`: decyzja co dalej — oznaczyć jako `FAILED`, `PENDING`, albo spróbować „resume”.
- Możliwa kolizja przy równoczesnych zapisach stanu — jeśli system wielowątkowy: synchronizacja / blokady.

## 7. Testowanie / Weryfikacja

- Test integracyjny (asynchroniczny): scenariusz — POST → GET (status PENDING/PROCESSING) → oczekiwanie → GET (status COMPLETED + wynik).
- Testy błędów: nieistniejące `task_id`, niepoprawne requesty, uszkodzony dump stanu, restart podczas tasków.
- (Opcjonalnie) Testy obciążeniowe — np. wysłanie wielu zadań na raz, sprawdzenie stabilności i wydajności.

## 8. Założenia, ograniczenia i przyszłe rozszerzenia

- MVP: memory + dump do pliku — bez bazy danych, bez kolejki produkcyjnej.
- Zadania są lekkie / krótkotrwałe (symulacja, demo).
- System mono-procesowy / mono-instancyjny.
- W przyszłości możliwa migracja do DB / kolejki / workerów / skalowania.
- Możliwość rozszerzenia o mechanizmy retry, kolejkowanie, priorytety zadań, rozproszenie.

## 9. Słownik i definicje / Uwagi

- **Task** — jednostka pracy wysyłana do systemu.
- **VenomTask** — wewnętrzne przedstawienie zadania w systemie, z metadanymi, statusem, logami.
- **State dump** — plik JSON z serializacją stanu wszystkich zadań, używany do przywrócenia stanu po restarcie.
- **MVP** — minimalnie wartościowy produkt / prototyp, bez produkcyjnych wymagań skalowalności.
