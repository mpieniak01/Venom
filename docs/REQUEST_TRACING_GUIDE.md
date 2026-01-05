# Dashboard v1.2 - Request Tracing Guide

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
  "llm_provider": "ollama",
  "llm_model": "gemma3:latest",
  "llm_endpoint": "http://localhost:11434/v1",
  "first_token": { "elapsed_ms": 740, "preview": "O" },
  "streaming": { "chunk_count": 120, "first_chunk_ms": 740, "last_emit_ms": 5200 },
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
      "component": "LLM",
      "action": "start",
      "timestamp": "2024-12-09T08:00:02",
      "status": "ok",
      "details": "intent=GENERAL_CHAT"
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

2. **Spójność runtime:**
   - W trace pojawia się krok `Orchestrator.routing_resolved` z `provider/model/endpoint/hash`.
   - Gdy wykryty jest drift konfiguracji, pojawia się `Orchestrator.routing_mismatch` i zadanie kończy się błędem `routing_mismatch`.
   - Wstępne wymagania środowiska są logowane jako `DecisionGate.requirements_resolved`, a brakujące zależności jako `DecisionGate.requirements_missing`.
   - `kernel_required` oznacza intencje wymagające function calling (np. CODE_GENERATION, RESEARCH, KNOWLEDGE_SEARCH).
   - Brak kernela logowany jest jako `DecisionGate.capability_required` → `DecisionGate.requirements_missing` → `Execution.execution_contract_violation`.

3. **Standard błędu (ErrorEnvelope):**
   - `error_code` to stabilna klasa błędu (np. `routing_mismatch`, `execution_contract_violation`).
   - `error_details` zawiera szczegóły (np. `missing`, `expected_hash`, `actual_hash`, `stage`).
   - UI renderuje badge na podstawie `error_code` i detale z `error_details` – bez parsowania treści wyjątku.

## Scenariusz: intencja rozpoznana, brak narzędzi

Jeśli intencja została rozpoznana, ale nie ma pasujących narzędzi/akcji, system **nie uruchamia LLM**.
Taki request trafia do `UnsupportedAgent` i to on zwraca odpowiedź szablonową.

**Konsekwencje w logach i dalszym procesie:**
- W trace pojawia się `DecisionGate.route_to_agent` → `UnsupportedAgent.process_task`.
- Brak realnego wywołania LLM (meta może zostać wyczyszczona do `None/None`).
- To jest właściwy sygnał do analizy braków w narzędziach i planowania nowych umiejętności.

**Cel:** zapewnić, że system nie "udaje" odpowiedzi modelem, gdy brakuje narzędzi, tylko jasno raportuje brak obsługi i kieruje na ścieżkę rozbudowy toolingu.

## Definicja: narzędzia jako wiedza specjalistyczna

W tej strategii **toolsy** są traktowane jako wiedza specjalistyczna, do której LLM **nie ma dostępu**:
- **Toolsy** dostarczają aktualnej, zewnętrznej lub systemowej wiedzy (np. internet, aktualny czas, stan systemu).
- **LLM** odpowiada tylko z własnej wiedzy; jeśli nie ma pewności, powinien przyznać brak wiedzy.
- Gdy zadanie wymaga narzędzia, a brak dopasowania — request trafia do `UnsupportedAgent`.

**Skutek dla logowania:** logi o `UnsupportedAgent` są sygnałem brakującej wiedzy specjalistycznej (narzędzi), nie braku „inteligencji” modelu.

### Rozpiska decyzji: LLM vs tool

**Prosta reguła:** wszystko, co nie wymaga toola, trafia do LLM.

**LLM (bez tooli):**
- Pytania o wiedzę ogólną, statyczną lub definicje.
- Wyjaśnienia, streszczenia, wnioski, parafrazy.
- Tworzenie treści, kodu, opisów, planów.
- Gdy brak danych zewnętrznych i użytkownik akceptuje odpowiedź z wiedzy modelu.

**Tool wymagany:**
- Dane „tu i teraz” (aktualny czas, pogoda, newsy, wyniki w sieci).
- Stan systemu (pliki, procesy, zasoby, logi, konfiguracja).
- Interakcja ze światem zewnętrznym (API, web, integracje).
- Każde zadanie, gdzie wynik zależy od świeżych lub lokalnych danych.

**Reguła spójności:**
- Jeśli zadanie wymaga toola, a tool nie istnieje lub nie pasuje do intencji,
  request kończy jako `UnsupportedAgent` i jest kandydatem do rozbudowy toolingu.

**Reguła rozwoju:** jeśli zadanie nie wymaga toola i trafia do LLM, uruchamiany jest proces uczenia:
- zapisujemy potrzebę użytkownika (co chciał uzyskać),
- identyfikujemy skróty ścieżki (jak dojść do tego szybciej następnym razem),
- sygnały z tych requestów budują backlog usprawnień lub przyszłych tooli.

W trace pojawia się krok `DecisionGate.tool_requirement`, a wpisy uczenia są zapisywane lokalnie
w `data/learning/requests.jsonl`. Do podglądu logów służy `GET /api/v1/learning/logs`
z opcjonalnym filtrowaniem (`intent`, `success`, `tag`).

Feedback użytkownika jest zapisywany do `data/feedback/feedback.jsonl` i udostępniany
przez `GET /api/v1/feedback/logs`. Metryki jakości są dostępne w `/api/v1/metrics`
(pola `feedback.up` i `feedback.down`).

Hidden prompts (zatwierdzone pary prompt → odpowiedź) są agregowane z
`data/learning/hidden_prompts.jsonl` i udostępniane przez
`GET /api/v1/learning/hidden-prompts`.

### Checklista: kiedy dodać narzędzie

- Czy odpowiedź wymaga aktualnych danych (czas/stan/system/internet)?
- Czy wynik musi być weryfikowalny na podstawie zewnętrznego źródła?
- Czy bez toola LLM musiałby zgadywać lub halucynować?
- Czy pojawiają się powtarzalne requesty kończące w `UnsupportedAgent`?

### Przykłady

- „Podaj aktualny czas” → tool (czas systemowy).
- „Sprawdź stan kolejki zadań” → tool (status systemu).
- „Wyjaśnij czym jest OAuth” → LLM (wiedza statyczna).
- „Zrób streszczenie tego opisu” → LLM (analiza tekstu użytkownika).

### Tabela: mapowanie intencji na narzędzia

| Intencja / potrzeba | Dane potrzebne | Tool wymagany | Jeśli brak toola | Przykład |
| --- | --- | --- | --- | --- |
| Aktualny czas | Systemowe „tu i teraz” | `time.now` | `UnsupportedAgent` | „Podaj aktualny czas” |
| Stan systemu | Lokalne zasoby, procesy, logi | `system.status` | `UnsupportedAgent` | „Sprawdź stan kolejki” |
| Dane z internetu | Źródła zewnętrzne, aktualności | `web.search` | `UnsupportedAgent` | „Jakie są najnowsze newsy?” |
| Operacje na plikach | Pliki w workspace | `fs.read` / `fs.list` | `UnsupportedAgent` | „Pokaż plik config” |
| Wyjaśnienie pojęcia | Wiedza ogólna LLM | brak | LLM odpowiada lub przyznaje brak wiedzy | „Co to jest OAuth?” |
| Streszczenie tekstu | Tekst użytkownika | brak | LLM odpowiada | „Streszcz ten opis” |

### Aktualne narzędzia (skills)

| Skill (moduł) | Zakres | Funkcje (przykłady) |
| --- | --- | --- |
| `AssistantSkill` (`assistant_skill.py`) | Czas, pogoda, status usług | `get_current_time`, `get_weather`, `check_services` |
| `BrowserSkill` (`browser_skill.py`) | Playwright E2E / przeglądarka | `visit_page`, `take_screenshot`, `get_html_content`, `click_element`, `fill_form`, `wait_for_element`, `close_browser` |
| `ChronoSkill` (`chrono_skill.py`) | Checkpointy i linie czasu | `create_checkpoint`, `restore_checkpoint`, `list_checkpoints`, `branch_timeline`, `merge_timeline` |
| `ComplexitySkill` (`complexity_skill.py`) | Szacowanie złożoności zadań | `estimate_time`, `estimate_complexity`, `suggest_subtasks`, `flag_risks` |
| `ComposeSkill` (`compose_skill.py`) | Docker Compose / stacki | `create_environment`, `destroy_environment`, `check_service_health`, `list_environments` |
| `CoreSkill` (`core_skill.py`) | Operacje na kodzie Venom | `hot_patch`, `rollback`, `list_backups`, `restart_service`, `verify_syntax` |
| `DocsSkill` (`docs_skill.py`) | Budowa dokumentacji | `generate_mkdocs_config`, `build_docs_site`, `serve_docs`, `check_docs_structure` |
| `FileSkill` (`file_skill.py`) | Pliki workspace | `write_file`, `read_file`, `list_files`, `file_exists` |
| `GitSkill` (`git_skill.py`) | Git / repozytorium | `init_repo`, `checkout`, `get_status`, `get_diff`, `add_files`, `commit`, `push`, `pull`, `merge`, `reset` |
| `GithubSkill` (`github_skill.py`) | GitHub (public API) | `search_repos`, `get_readme`, `get_trending` |
| `GoogleCalendarSkill` (`google_calendar_skill.py`) | Kalendarz | `read_agenda`, `schedule_task` |
| `HuggingfaceSkill` (`huggingface_skill.py`) | Hugging Face | `search_models`, `get_model_card`, `search_datasets` |
| `InputSkill` (`input_skill.py`) | Wejście systemowe (mysz/klawiatura) | `mouse_click`, `keyboard_type`, `keyboard_hotkey`, `get_mouse_position`, `take_screenshot` |
| `MediaSkill` (`media_skill.py`) | Grafika / assety | `generate_image`, `resize_image`, `list_assets` |
| `ParallelSkill` (`parallel_skill.py`) | Map-Reduce / równoległość | `map_reduce`, `parallel_execute`, `get_task_status` |
| `PlatformSkill` (`platform_skill.py`) | GitHub/Slack/Discord | `get_assigned_issues`, `create_pull_request`, `comment_on_issue`, `send_notification`, `get_configuration_status` |
| `RenderSkill` (`render_skill.py`) | UI / widgety / wykresy | `render_chart`, `render_table`, `render_dashboard_widget`, `render_markdown`, `render_mermaid_diagram`, `update_widget` |
| `ResearchSkill` (`research_skill.py`) | Ingestia do grafu wiedzy | `digest_url`, `digest_file`, `digest_directory`, `get_knowledge_stats` |
| `ShellSkill` (`shell_skill.py`) | Komendy shell | `run_shell` |
| `TestSkill` (`test_skill.py`) | Testy i linter | `run_pytest`, `run_linter` |
| `WebSearchSkill` (`web_skill.py`) | Search i scraping WWW | `search`, `scrape_text`, `search_and_scrape` |

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
