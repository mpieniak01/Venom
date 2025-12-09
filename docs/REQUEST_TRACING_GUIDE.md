# Dashboard v2.2 - Request Tracing Guide

## Przegląd

System Request Tracing umożliwia śledzenie przepływu każdego zadania przez system Venom - od momentu wysłania przez użytkownika, przez wszystkie etapy przetwarzania, aż do zwrócenia odpowiedzi.

## Architektura

### RequestTracer (`venom_core/core/tracer.py`)

Centralny moduł odpowiedzialny za rejestrowanie i przechowywanie śladów wykonania zadań.

**Kluczowe komponenty:**
- `RequestTrace` - Model pojedynczego śladu (request_id, status, prompt, timestamps, steps)
- `TraceStep` - Model pojedynczego kroku w wykonaniu (component, action, timestamp, status, details)
- `TraceStatus` - Enum statusów: PENDING, PROCESSING, COMPLETED, FAILED, LOST
- `RequestTracer` - Główna klasa zarządzająca śladami

**Mechanizm Watchdog:**
- Automatycznie sprawdza co minutę czy są zadania bez aktywności
- Jeśli zadanie w statusie PROCESSING nie ma aktywności przez 5 minut → zmienia status na LOST
- Przydatne do wykrywania requestów "zagubionych" np. po restarcie serwera

**Thread Safety:**
- Wszystkie operacje na `_traces` są chronione przez Lock
- Bezpieczne użycie w środowisku asynchronicznym

### Integracja z Orchestratorem

Orchestrator automatycznie loguje kluczowe kroki wykonania:

```python
# Przy submit_task
tracer.create_trace(task_id, prompt)
tracer.add_step(task_id, "User", "submit_request")

# Przy rozpoczęciu przetwarzania
tracer.update_status(task_id, TraceStatus.PROCESSING)
tracer.add_step(task_id, "Orchestrator", "start_processing")

# Po klasyfikacji intencji
tracer.add_step(task_id, "Orchestrator", "classify_intent", details=f"Intent: {intent}")

# Po przetworzeniu przez agenta
tracer.add_step(task_id, agent_name, "process_task")

# Po zakończeniu
tracer.update_status(task_id, TraceStatus.COMPLETED)
tracer.add_step(task_id, "System", "complete", details="Response sent")

# W przypadku błędu
tracer.update_status(task_id, TraceStatus.FAILED)
tracer.add_step(task_id, "System", "error", status="error", details=str(e))
```

## API Endpoints

### GET `/api/v1/history/requests`

Zwraca paginowaną listę requestów z historii.

**Parametry:**
- `limit` (int, optional): Maksymalna liczba wyników (domyślnie 50)
- `offset` (int, optional): Offset dla paginacji (domyślnie 0)
- `status` (str, optional): Filtr po statusie (PENDING/PROCESSING/COMPLETED/FAILED/LOST)

**Odpowiedź:**
```json
[
  {
    "request_id": "uuid",
    "prompt": "Treść polecenia...",
    "status": "COMPLETED",
    "created_at": "2024-12-09T08:00:00",
    "finished_at": "2024-12-09T08:00:15",
    "duration_seconds": 15.5
  }
]
```

### GET `/api/v1/history/requests/{request_id}`

Zwraca szczegółowy ślad wykonania zadania z wszystkimi krokami.

**Odpowiedź:**
```json
{
  "request_id": "uuid",
  "prompt": "Treść polecenia...",
  "status": "COMPLETED",
  "created_at": "2024-12-09T08:00:00",
  "finished_at": "2024-12-09T08:00:15",
  "duration_seconds": 15.5,
  "steps": [
    {
      "component": "User",
      "action": "submit_request",
      "timestamp": "2024-12-09T08:00:00",
      "status": "ok",
      "details": "Request received"
    },
    {
      "component": "Orchestrator",
      "action": "classify_intent",
      "timestamp": "2024-12-09T08:00:01",
      "status": "ok",
      "details": "Intent: RESEARCH"
    },
    {
      "component": "ResearcherAgent",
      "action": "process_task",
      "timestamp": "2024-12-09T08:00:10",
      "status": "ok",
      "details": "Task processed successfully"
    },
    {
      "component": "System",
      "action": "complete",
      "timestamp": "2024-12-09T08:00:15",
      "status": "ok",
      "details": "Response sent"
    }
  ]
}
```

## UI - Zakładka History

### Funkcjonalności

1. **Tabela Requestów**
   - Kolumny: Status (badge), Polecenie (skrócone), Czas utworzenia + czas trwania
   - Kolorowanie wierszy według statusu:
     - ⚪ Biały (PENDING) - Nowy request, jeszcze nie podjęty
     - 🟡 Żółty (PROCESSING) - W trakcie obróbki
     - 🟢 Zielony (COMPLETED) - Zakończony sukcesem
     - 🔴 Czerwony (FAILED/LOST) - Błąd lub zagubiony
   - Sortowanie od najnowszych
   - Kliknięcie w wiersz otwiera szczegóły

2. **Modal Szczegółów**
   - Informacje podstawowe: ID, Status, Pełne polecenie, Czasy, Czas trwania
   - Timeline wykonania:
     - Lista kroków w kolejności chronologiczej
     - Dla każdego kroku: komponent, akcja, timestamp, szczegóły
     - Wizualne oznaczenie błędów (czerwona kropka, czerwony border)
     - Szczegóły błędów wyświetlane w osobnym bloku

3. **Auto-refresh**
   - Historia ładowana automatycznie przy przełączeniu na zakładkę
   - Przycisk "🔄" do manualnego odświeżenia

## Rozszerzanie systemu

### Dodawanie kroków w własnym kodzie

```python
# W agencie lub skill
if self.tracer:
    self.tracer.add_step(
        request_id=task_id,
        component="MyAgent",
        action="custom_action",
        status="ok",  # lub "error"
        details="Additional info"
    )
```

### Dodawanie własnych statusów

Aby dodać nowy status, rozszerz enum `TraceStatus` w `tracer.py` i zaktualizuj logikę UI w:
- `app.js` - metoda `getStatusIcon()`
- `app.css` - klasy `.status-{nazwa}`

## Best Practices

1. **Logowanie kroków:**
   - Loguj kluczowe momenty (start, koniec, decyzje)
   - Unikaj zbyt dużej granularności (nie każda linia kodu)
   - Dodawaj szczegóły (`details`) dla błędów i ważnych decyzji

2. **Performance:**
   - RequestTracer używa Lock - operacje są synchroniczne
   - Unikaj wywołań w pętlach o wysokiej częstotliwości
   - Rozważ async logging jeśli wydajność jest krytyczna

3. **Czyszczenie:**
   - Użyj `tracer.clear_old_traces(days=7)` do usuwania starych śladów
   - Można dodać to jako scheduled job w BackgroundScheduler

4. **Debugowanie:**
   - Sprawdź timeline w UI aby zobaczyć dokładnie gdzie zadanie "utknęło"
   - Status LOST oznacza brak aktywności - sprawdź logi serwera

## Przykładowe scenariusze

### Scenariusz 1: Sukces
```
User → submit_request
Orchestrator → start_processing
Orchestrator → classify_intent (RESEARCH)
ResearcherAgent → process_task
WebSkill → fetch_data
ResearcherAgent → generate_report
System → complete
```

### Scenariusz 2: Błąd
```
User → submit_request
Orchestrator → start_processing
Orchestrator → classify_intent (CODE_GENERATION)
CoderAgent → process_task
System → error (Connection timeout)
```

### Scenariusz 3: Zagubiony (LOST)
```
User → submit_request
Orchestrator → start_processing
Orchestrator → classify_intent (RESEARCH)
ResearcherAgent → process_task
[5 minut bez aktywności]
Watchdog → timeout (Status: LOST)
```

## Troubleshooting

**Problem:** Historia nie ładuje się
- Sprawdź czy `request_tracer` jest zainicjalizowany w `main.py`
- Sprawdź logi serwera pod kątem błędów inicjalizacji

**Problem:** Requesty nie pojawiają się w historii
- Upewnij się że Orchestrator ma przekazany `request_tracer` w konstruktorze
- Sprawdź czy watchdog jest uruchomiony: `await tracer.start_watchdog()`

**Problem:** Brakujące kroki w timeline
- Sprawdź czy komponenty wywołują `tracer.add_step()`
- Upewnij się że `request_id` jest poprawnie przekazywany

**Problem:** Za dużo requestów w bazie
- Użyj `tracer.clear_old_traces(days=N)` regularnie
- Rozważ dodanie scheduled job do czyszczenia

## Przyszłe rozszerzenia

- [ ] Export historii do CSV/JSON
- [ ] Filtrowanie po intencji/agencie
- [ ] Statystyki wydajności (średni czas, success rate)
- [ ] Integracja z BaseAgent (automatyczne logowanie)
- [ ] WebSocket real-time updates dla historii
- [ ] Wizualizacja grafu zależności między komponentami
