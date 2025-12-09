# TECH_DEBT_AUDIT_V1 - Audyt Długu Technicznego Venom

**Data audytu:** 2025-12-09
**Zakres:** Całe repozytorium Venom (255 plików Python)
**Metodologia:** Automatyczne skanowanie + manualna analiza krytycznych komponentów

---

## 1. PRZEGLĄD (Overview)

Repozytorium Venom zawiera **255 plików Python** zorganizowanych w spójną architekturę modułową. Audyt zidentyfikował **główne obszary długu technicznego** skoncentrowane w następujących kategoriach:

### Kluczowe obserwacje:

1. **Koncentracja problemów:** Dług techniczny koncentruje się w:
   - **venom_core/main.py** (2073 linii) - monolityczna implementacja API z licznymi placeholderami
   - **venom_core/core/orchestrator.py** (1872 linii) - złożona logika orkiestracji wymagająca refaktoryzacji
   - **venom_core/perception/** - niekompletna implementacja nagrywania akcji użytkownika
   - **venom_core/agents/professor.py** - zaślepki dla Arena i inteligentnego doboru parametrów treningowych

2. **Dominujące typy problemów:**
   - **28 jawnych TODO** (faktyczne komentarze oznaczone jako TODO w kodzie)
   - **64 wystąpienia placeholderów i "nie jest jeszcze zaimplementowane"**
   - **1 NotImplementedError** (Azure OpenAI w KernelBuilder)
   - **Placeholder endpointy API** (konsolidacja pamięci, git pull/reset)
   - **Niekompletne integracje** (Shadow Agent actions, Evolution Coordinator merges)

3. **Najbardziej krytyczne dla stabilności:**
   - **Brak obsługi błędów w Shadow Agent callbacks** (main.py:343-375) - akcje nie wykonują rzeczywistych zmian
   - **Niekompletne nagrywanie akcji** (desktop_sensor.py:357) - fundamentalny feature dla Apprentice
   - **Placeholder funkcje scheduled jobs** (main.py:498, 529) - nie wykonują faktycznej pracy
   - **Duże pliki wymagające dekompozycji** (main.py, orchestrator.py) - utrudniają utrzymanie

4. **Architektoniczne niespójności:**
   - Różne wzorce nazewnictwa metod agentów (process/execute/run/perform)
   - Brak spójnego interfejsu dla Agentów poza abstrakcyjnym BaseAgent
   - Duplikacja logiki dla różnych typów tasków w orchestrator.py
   - Mieszanie logiki biznesowej z endpoint definitions w main.py (>2000 linii)

---

## 2. ZNALEZISKA WEDŁUG KATEGORII

### 2.1 TODO_MARKERS

| ID | Plik:Linia | Kategoria | Opis | Sugerowane działanie | Priorytet | Szac. Nakład |
|----|-----------|-----------|------|----------------------|-----------|--------------|
| TD-001 | venom_core/perception/desktop_sensor.py:357 | TODO_MARKERS | Brak implementacji faktycznego nagrywania akcji (mouse, keyboard) - metoda tylko inicjalizuje stan | Implementować przechwytywanie zdarzeń z pynput, zapisywanie timestampów i typu akcji | H | L |
| TD-002 | venom_core/perception/vision_grounding.py:84 | TODO_MARKERS | Parametr confidence_threshold jest nieużywany w metodzie | Zaimplementować filtrowanie wyników na podstawie confidence lub usunąć parametr | L | S |
| TD-003 | venom_core/main.py:348-371 | TODO_MARKERS | Shadow Agent action handlers nie są zintegrowane z Orchestrator, Coder, GoalStore | Podłączyć handle_shadow_action do rzeczywistych metod orchestrator.submit_task, goal_store.update_goal_status | H | M |
| TD-004 | venom_core/core/evolution_coordinator.py:251 | TODO_MARKERS | Uruchamianie testów w Shadow Instance nie jest zaimplementowane | Dodać integrację z TesterAgent dla weryfikacji eksperymentów | M | M |
| TD-005 | venom_core/core/evolution_coordinator.py:275 | TODO_MARKERS | Automatyczny merge brancha nie jest zaimplementowany | Dodać metody merge() i create_pull_request() do GitSkill | M | M |
| TD-006 | venom_core/core/dispatcher.py:228 | TODO_MARKERS | Brak parsowania content dla operacji na plikach | Dodać ekstrakcję ścieżek plików i parametrów z content używając regex lub LLM | M | S |
| TD-007 | venom_core/agents/professor.py:303 | TODO_MARKERS | Arena (ewaluacja modeli) jest placeholder z mock results | Stworzyć zestaw benchmark testów, mechanizm porównywania modeli, automated metrics | M | L |
| TD-008 | venom_core/agents/professor.py:350 | TODO_MARKERS | Brak sprawdzania interwału od ostatniego treningu | Dodać zapisywanie timestampów w training_history, sprawdzanie minimum elapsed time | L | S |
| TD-009 | venom_core/agents/professor.py:365 | TODO_MARKERS | Inteligentny dobór parametrów treningowych nie jest zaimplementowany | Dodać heurystyki: dataset size → batch size, VRAM → model size, previous results → learning rate | M | M |
| TD-010 | venom_core/agents/foreman.py:62 | TODO_MARKERS | Wagi priorytetów są hardcodowane, rozważyć przeniesienie do SETTINGS | Przenieść wagi do config.py jako konfigurowalne parametry | L | S |

### 2.2 MISSING_IMPLEMENTATION

| ID | Plik:Linia | Kategoria | Opis | Sugerowane działanie | Priorytet | Szac. Nakład |
|----|-----------|-----------|------|----------------------|-----------|--------------|
| TD-011 | venom_core/execution/kernel_builder.py:193 | MISSING_IMPLEMENTATION | Azure OpenAI nie jest zaimplementowany - rzuca NotImplementedError | Dodać implementację Azure OpenAI service używając semantic_kernel.connectors.ai.azure | M | S |
| TD-012 | venom_core/main.py:1405-1407 | MISSING_IMPLEMENTATION | Endpoint /api/v1/git/sync (git pull) nie jest zaimplementowany | Dodać metodę pull() do GitSkill z obsługą conflicts | M | M |
| TD-013 | venom_core/main.py:1428-1430 | MISSING_IMPLEMENTATION | Endpoint /api/v1/git/undo (git reset) nie jest zaimplementowany | Dodać metodę reset() do GitSkill z confirmation guards | M | M |
| TD-014 | venom_core/main.py:498-526 | MISSING_IMPLEMENTATION | Funkcja _consolidate_memory() jest placeholder - nie wykonuje konsolidacji | Zaimplementować analizę logów, ekstrakcję wniosków, zapis do GraphRAG/LessonsStore | M | L |
| TD-015 | venom_core/main.py:529-550 | MISSING_IMPLEMENTATION | Funkcja _check_health() jest placeholder - nie wykonuje health check | Dodać sprawdzanie CPU/memory/disk, status agentów, connectivity do LLM | M | M |
| TD-016 | venom_core/execution/skills/chrono_skill.py:284 | MISSING_IMPLEMENTATION | Merge timeline jest placeholder wymagający pełnej implementacji | Dodać: porównanie zmian, detekcję konfliktów, inteligentne mergowanie przez LLM | L | L |
| TD-017 | venom_core/infrastructure/cloud_provisioner.py:322 | MISSING_IMPLEMENTATION | configure_domain() jest placeholder - brak integracji z DNS API | Zintegrować z Cloudflare API lub innym DNS provider do automatycznej konfiguracji | L | M |
| TD-018 | venom_core/agents/apprentice.py:434-436 | MISSING_IMPLEMENTATION | Generowanie odpowiedzi bez LLM - prosty placeholder return | Zintegrować z LLM kernel dla generowania inteligentnych odpowiedzi | M | S |
| TD-019 | venom_core/learning/demonstration_analyzer.py:315 | MISSING_IMPLEMENTATION | Detekcja elementu UI jest prosty placeholder | Rozważyć integrację Florence-2 lub LLaVA dla vision-based UI detection | L | L |
| TD-020 | venom_core/agents/devops.py:45 | MISSING_IMPLEMENTATION | configure_domain w DevOpsAgent jest placeholder (dokumentacja) | Zaimplementować rzeczywistą metodę configure_domain lub usunąć z dokumentacji | L | M |

### 2.3 OUT_OF_SCOPE_NOW

| ID | Plik:Linia | Kategoria | Opis | Sugerowane działanie | Priorytet | Szac. Nakład |
|----|-----------|-----------|------|----------------------|-----------|--------------|
| TD-021 | venom_core/perception/audio_engine.py:135 | OUT_OF_SCOPE_NOW | TTS działa w trybie mock gdy brak ścieżki do modelu | Dodać walidację konfiguracji przy starcie, jasny komunikat o wymaganiach TTS | L | S |
| TD-022 | venom_core/execution/skills/media_skill.py:22-169 | OUT_OF_SCOPE_NOW | Generowanie obrazów używa fallback placeholders (Pillow) zamiast DALL-E/Stable Diffusion | Rozważyć dodanie integracji z generatywnym AI gdy potrzebne | L | M |
| TD-023 | venom_core/execution/skills/compose_skill.py:76-77 | OUT_OF_SCOPE_NOW | Przetwarzanie placeholderów portów {{PORT}} - obecna implementacja działa ale może być ulepszona | Dodać wsparcie dla innych placeholders ({{HOST}}, {{SECRET}}), lepszą walidację | L | S |
| TD-024 | venom_core/main.py:225 | OUT_OF_SCOPE_NOW | Scheduled job "konsolidacja pamięci" opisany jako placeholder | Usunąć placeholder albo zaimplementować zgodnie z TD-014 | M | S |
| TD-025 | venom_core/main.py:236 | OUT_OF_SCOPE_NOW | Scheduled job "health check" opisany jako placeholder | Usunąć placeholder albo zaimplementować zgodnie z TD-015 | M | S |

### 2.4 DUPLICATION_OR_INCONSISTENCY

| ID | Plik:Linia | Kategoria | Opis | Sugerowane działanie | Priorytet | Szac. Nakład |
|----|-----------|-----------|------|----------------------|-----------|--------------|
| TD-026 | venom_core/agents/*.py | DUPLICATION_OR_INCONSISTENCY | Różne wzorce nazewnictwa metod: process(), execute(), run(), perform() | Ustandaryzować na process() (zgodnie z BaseAgent) dla wszystkich agentów | M | M |
| TD-027 | venom_core/main.py:1-2073 | DUPLICATION_OR_INCONSISTENCY | main.py jest monolityczny (2073 linii) - miesza logikę API, scheduled jobs, WebSocket | Wydzielić do osobnych modułów: api/routes/, api/websocket.py, jobs/scheduler.py | H | L |
| TD-028 | venom_core/core/orchestrator.py:1-1872 | DUPLICATION_OR_INCONSISTENCY | orchestrator.py jest bardzo długi (1872 linii) - złożona logika różnych flow | Wydzielić metody do osobnych klas: CouncilOrchestrator, StandardOrchestrator, ForgeOrchestrator | H | L |
| TD-029 | venom_core/execution/skills/ | DUPLICATION_OR_INCONSISTENCY | Skills nie mają wspólnego interfejsu bazowego poza konwencją nazw | Stworzyć BaseSkill abstract class z metodami execute(), validate_params() | M | M |
| TD-030 | venom_core/core/*.py | DUPLICATION_OR_INCONSISTENCY | Wiele klas *Manager, *Store, *Service bez spójnego wzorca | Zdefiniować wspólne interfejsy: IManager, IStore, IService z core methods | L | L |
| TD-031 | venom_core/core/orchestrator.py:450-550 | DUPLICATION_OR_INCONSISTENCY | Logika Coder-Critic loop jest zagnieżdżona w orchestrator, powinna być wydzielona | Stworzyć CodeReviewLoop class jako separate concern | M | M |
| TD-032 | venom_core/agents/ | DUPLICATION_OR_INCONSISTENCY | Niektóre agenty dziedziczą z BaseAgent, inne nie (np. Professor, Executive) | Upewnić się że wszystkie agenty dziedziczą z BaseAgent lub uzasadnić wyjątki | M | S |
| TD-033 | venom_core/ | DUPLICATION_OR_INCONSISTENCY | Logowanie używa get_logger(__name__) konsystentnie - DOBRA PRAKTYKA | Kontynuować spójne używanie get_logger we wszystkich nowych modułach | - | - |

### 2.5 OTHER_TECH_DEBT

| ID | Plik:Linia | Kategoria | Opis | Sugerowane działanie | Priorytet | Szac. Nakład |
|----|-----------|-----------|------|----------------------|-----------|--------------|
| TD-034 | venom_core/agents/base.py:31 | OTHER_TECH_DEBT | Abstrakcyjna metoda process() w BaseAgent używa `pass` zamiast raise NotImplementedError | Zmienić na explicit raise NotImplementedError dla jasności | L | S |
| TD-035 | venom_core/infrastructure/cloud_provisioner.py:19 | OTHER_TECH_DEBT | CloudProvisionerError używa pustego `pass` w ciele | Dodać docstring lub usunąć niepotrzebny pass | L | S |
| TD-036 | venom_core/agents/gardener.py:94, 144 | OTHER_TECH_DEBT | Exception handling z pustym pass - może maskować problemy | Dodać logger.debug() przynajmniej dla widoczności co się dzieje | L | S |
| TD-037 | venom_core/core/tracer.py:86 | OTHER_TECH_DEBT | Try-except z pustym pass może ukrywać błędy | Dodać logowanie błędów nawet jeśli są one expected | L | S |
| TD-038 | venom_core/execution/skills/test_skill.py:195, 200 | OTHER_TECH_DEBT | Puste pass statements w exception handling | Dodać odpowiednie logowanie lub komentarze wyjaśniające dlaczego ignorowane | L | S |
| TD-039 | venom_core/core/energy_manager.py:84-94 | OTHER_TECH_DEBT | Temperatura CPU może nie być dostępna na niektórych platformach - try-except z pass | Działający kod, ale można poprawić przez dodanie logger.debug o braku wsparcia | L | S |
| TD-040 | venom_core/core/model_manager.py:262 | OTHER_TECH_DEBT | TODO dla implementacji ładowania PEFT adaptera | Zaimplementować ładowanie adapters dla fine-tuned models (LoRA, QLoRA) | M | M |
| TD-041 | docs/ | OTHER_TECH_DEBT | 26 plików dokumentacji - niektóre mogą być nieaktualne względem kodu | Przeprowadzić audit dokumentacji: sprawdzić czy odpowiada implementacji | M | L |
| TD-042 | venom_core/perception/watcher.py | OTHER_TECH_DEBT | Watcher może duplikować funkcjonalność desktop_sensor | Wyjaśnić różnicę między Watcher a DesktopSensor, rozważyć konsolidację | L | M |
| TD-043 | venom_core/utils/helpers.py | OTHER_TECH_DEBT | Plik helpers.py może zawierać mixed utilities bez spójnego tematu | Przejrzeć helpers i rozdzielić na tematyczne moduły (file_utils, string_utils) | L | M |
| TD-044 | tests/ | OTHER_TECH_DEBT | 92 pliki testowe - nie sprawdzono coverage ani quality | Uruchomić pytest --cov, zidentyfikować obszary z niskim coverage | M | L |
| TD-045 | venom_core/main.py | OTHER_TECH_DEBT | 52 funkcje/endpointy w jednym pliku - trudne w nawigacji | Związane z TD-027 - refaktoryzacja poprawi organizację | H | L |

---

## 3. ZIARNA ZADAŃ DO KOLEJNEGO ETAPU

Poniżej przedstawiono pogrupowane zadania gotowe do realizacji. Każde ziarno zawiera powiązane ID oraz gotowy prompt dla agenta kodującego.

---

### TS-001 – Uzupełnienie nagrywania akcji użytkownika (Apprentice/DesktopSensor)

**Powiązane:** TD-001, TD-002
**Priorytet:** WYSOKI
**Nakład:** DUŻY

**Prompt:**
```
Uzupełnij implementację nagrywania akcji użytkownika w venom_core/perception/desktop_sensor.py:

1. W metodzie start_recording() dodaj faktyczne przechwytywanie zdarzeń myszy i klawiatury używając biblioteki pynput
2. Zapisuj każdą akcję z timestampem, typem (click/key_press/mouse_move), pozycją i danymi
3. Implementuj stop_recording() aby zwracał pełną listę nagranych akcji
4. W venom_core/perception/vision_grounding.py:84 zaimplementuj użycie parametru confidence_threshold lub usuń go jeśli niepotrzebny
5. Dodaj testy jednostkowe weryfikujące nagrywanie (mock pynput events)
6. Zaktualizuj dokumentację w docs/THE_APPRENTICE.md jeśli potrzebne

Kod powinien być zgodny z istniejącym stylem, używać get_logger(__name__) i być bezpieczny (nie nagrywać haseł).
```

---

### TS-002 – Integracja Shadow Agent Actions z systemem

**Powiązane:** TD-003
**Priorytet:** WYSOKI
**Nakład:** ŚREDNI

**Prompt:**
```
Zintegruj handle_shadow_action callback w venom_core/main.py:343-375 z rzeczywistymi komponentami systemu:

1. Dla action_type="error_fix": wywołaj orchestrator.submit_task() z TaskRequest zawierającym opis błędu
2. Dla action_type="code_improvement": wywołaj coder_agent.process() lub podobną metodę
3. Dla action_type="task_update": wywołaj goal_store.update_goal_status() z odpowiednim status
4. Usuń komentarze TODO i "not implemented" po dodaniu faktycznych implementacji
5. Dodaj obsługę błędów (try-except) i logowanie wyników
6. Dodaj testy integracyjne weryfikujące każdy typ akcji

Upewnij się że callback jest async i obsługuje wszystkie edge cases.
```

---

### TS-003 – Implementacja Evolution Coordinator test running i merge

**Powiązane:** TD-004, TD-005
**Priorytet:** ŚREDNI
**Nakład:** ŚREDNI

**Prompt:**
```
Uzupełnij brakujące funkcjonalności w venom_core/core/evolution_coordinator.py:

1. W metodzie _verify_changes (linia ~251):
   - Dodaj integrację z TesterAgent dla uruchamiania testów w Shadow Instance
   - Zamiast placeholder zwróć faktyczne wyniki testów
   - Obsłuż przypadki gdy tester_agent jest None

2. W metodzie _merge_changes (linia ~275):
   - Dodaj nowe metody do venom_core/execution/skills/git_skill.py: merge(), create_pull_request()
   - Zaimplementuj faktyczne mergowanie brancha lub tworzenie PR
   - Obsłuż konflikty mergowania i błędy git

3. Usuń placeholder komunikaty i TODO comments
4. Dodaj testy jednostkowe dla obu metod

Kod powinien być defensywny i logować wszystkie kroki operacji.
```

---

### TS-004 – Dodanie Azure OpenAI i brakujących integracji LLM

**Powiązane:** TD-011, TD-018
**Priorytet:** ŚREDNI
**Nakład:** MAŁY

**Prompt:**
```
Dodaj wsparcie dla Azure OpenAI oraz popraw inne integracje LLM:

1. W venom_core/execution/kernel_builder.py:193:
   - Zamień NotImplementedError na faktyczną implementację Azure OpenAI
   - Użyj semantic_kernel.connectors.ai.azure.AzureChatCompletion
   - Pobierz credentials z SETTINGS (AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_DEPLOYMENT_NAME)

2. W venom_core/agents/apprentice.py:434-436:
   - Zamiast prostego return dodaj wywołanie LLM przez kernel
   - Użyj full_prompt do generowania inteligentnej odpowiedzi

3. Dodaj testy jednostkowe (z mockami) dla Azure OpenAI service
4. Zaktualizuj config.py jeśli potrzebne nowe zmienne środowiskowe

Upewnij się że kod działa zarówno z OpenAI jak i Azure OpenAI.
```

---

### TS-005 – Implementacja placeholder API endpoints (git sync/undo)

**Powiązane:** TD-012, TD-013
**Priorytet:** ŚREDNI
**Nakład:** ŚREDNI

**Prompt:**
```
Zaimplementuj brakujące endpointy Git API w venom_core/main.py:

1. Endpoint /api/v1/git/sync (linia 1405-1407):
   - Dodaj metodę pull() do GitSkill z obsługą konfliktów
   - Zaimplementuj endpoint aby wykonywał git pull
   - Zwróć status: success/conflicts wraz z listą zmienionych plików

2. Endpoint /api/v1/git/undo (linia 1428-1430):
   - Dodaj metodę reset(mode='hard') do GitSkill
   - Dodaj confirmation guard (require confirmation=true query param)
   - Zaimplementuj endpoint aby wykonywał git reset --hard
   - Zwróć informację o cofniętych zmianach

3. Usuń HTTPException(501) i "nie jest jeszcze zaimplementowane"
4. Dodaj testy API (pytest + httpx) dla obu endpointów
5. Zaktualizuj dokumentację API jeśli istnieje

Kod powinien być bezpieczny - reset wymaga explicit confirmation.
```

---

### TS-006 – Implementacja scheduled jobs (memory consolidation, health check)

**Powiązane:** TD-014, TD-015, TD-024, TD-025
**Priorytet:** ŚREDNI
**Nakład:** DUŻY

**Prompt:**
```
Zaimplementuj placeholder scheduled jobs w venom_core/main.py:

1. Funkcja _consolidate_memory() (linia 498-526):
   - Dodaj analizę ostatnich logów (ostatnie N godzin)
   - Ekstrakcję wniosków/wzorców używając LLM
   - Zapis do GraphRAG service lub LessonsStore
   - Usunięcie placeholder comments i logów

2. Funkcja _check_health() (linia 529-550):
   - Sprawdzanie CPU, memory, disk używając psutil
   - Status agentów (które są aktywne, ostatnia aktywność)
   - Connectivity do LLM endpoint (ping test)
   - Zwrócenie health report z metrykami

3. Zaktualizuj description scheduled jobs (usuń "(placeholder)")
4. Dodaj configuration w SETTINGS dla interwałów i thresholds
5. Dodaj testy jednostkowe dla obu funkcji

Jobs powinny być odporne na błędy i logować problemy zamiast crashować.
```

---

### TS-007 – Refaktoryzacja main.py - wydzielenie modułów

**Powiązane:** TD-027, TD-045
**Priorytet:** WYSOKI
**Nakład:** DUŻY

**Prompt:**
```
Zrefaktoryzuj monolityczny venom_core/main.py (2073 linii) przez wydzielenie do osobnych modułów:

1. Utwórz strukturę:
   - venom_core/api/routes/tasks.py - endpointy /api/v1/task/*
   - venom_core/api/routes/git.py - endpointy /api/v1/git/*
   - venom_core/api/routes/memory.py - endpointy /api/v1/memory/*
   - venom_core/api/routes/agents.py - endpointy /api/v1/agents/*
   - venom_core/api/websocket.py - WebSocket logic
   - venom_core/jobs/scheduler.py - scheduled jobs (_consolidate_memory, _check_health)

2. W main.py zostaw tylko:
   - Inicjalizację FastAPI app
   - Lifecycle events (startup/shutdown)
   - Inclusion of routers: app.include_router(tasks_router)

3. Zachowaj dependency injection (orchestrator, event_broadcaster) przez FastAPI Depends
4. Wszystkie testy powinny dalej działać bez zmian
5. Zaktualizuj imports w innych plikach jeśli potrzebne

Refaktoryzacja powinna być bezpieczna - nie zmieniać logiki, tylko organizację.
```

---

### TS-008 – Refaktoryzacja orchestrator.py - wydzielenie concerns

**Powiązane:** TD-028, TD-031
**Priorytet:** WYSOKI
**Nakład:** DUŻY

**Prompt:**
```
Zrefaktoryzuj venom_core/core/orchestrator.py (1872 linii) przez wydzielenie logicznych komponentów:

1. Wydziel Coder-Critic Loop (linia 450-550):
   - Utwórz venom_core/core/code_review_loop.py
   - Przenieś logikę pętli naprawy kodu do CodeReviewLoop class
   - Metody: execute_with_review(task_id, code_request) -> CodeResult

2. Wydziel Council flow:
   - Rozważ venom_core/core/council_orchestrator.py
   - Metody specyficzne dla AutoGen Group Chat

3. Wydziel Forge flow:
   - Rozważ venom_core/core/forge_orchestrator.py
   - Workflow tworzenia narzędzi

4. Orchestrator główny powinien delegować do tych komponentów
5. Zachowaj istniejące testy - upewnij się że wszystko działa po refaktoryzacji
6. Dodaj testy jednostkowe dla nowych klas

Zachowaj backward compatibility - public API orchestratora nie może się zmienić.
```

---

### TS-009 – Ustandaryzowanie interfejsów Agents i Skills

**Powiązane:** TD-026, TD-029, TD-032
**Priorytet:** ŚREDNI
**Nakład:** ŚREDNI

**Prompt:**
```
Ustandaryzuj interfejsy dla Agentów i Skills w całym projekcie:

1. Agents (venom_core/agents/):
   - Upewnij się że wszystkie agenty dziedziczą z BaseAgent
   - Zmień różne nazwy metod (execute/run/perform) na process() zgodnie z BaseAgent
   - Dodaj type hints dla process() signature
   - Jeśli agent nie dziedziczy z BaseAgent, dodaj komentarz uzasadniający

2. Skills (venom_core/execution/skills/):
   - Utwórz BaseSkill abstract class w venom_core/execution/skills/base_skill.py
   - Metody: execute(**kwargs), validate_params(params: dict) -> bool
   - Zaktualizuj wszystkie istniejące Skills żeby dziedziczyły z BaseSkill
   - Dodaj @abstractmethod dla execute()

3. Dodaj type hints i docstrings gdzie brakuje
4. Uruchom testy - upewnij się że nic się nie zepsuło
5. Zaktualizuj dokumentację guidelines o standardowych interfejsach

Zachowaj backward compatibility - używaj @deprecated dla starych metod jeśli potrzebne.
```

---

### TS-010 – Implementacja Professor Agent features (Arena, params selection)

**Powiązane:** TD-007, TD-008, TD-009, TD-040
**Priorytet:** ŚREDNI
**Nakład:** DUŻY

**Prompt:**
```
Uzupełnij brakujące features w venom_core/agents/professor.py:

1. Metoda _evaluate_model (linia ~303):
   - Zamień mock na faktyczny benchmark system (Arena)
   - Stwórz zestaw 10-20 testowych pytań/zadań
   - Uruchom oba modele (stary, nowy) na tym samym zestawie
   - Porównaj wyniki używając metrics (accuracy, quality score)
   - Zwróć faktyczny raport z porównaniem

2. Metoda should_start_training (linia ~350):
   - Dodaj zapisywanie timestampów w training_history
   - Sprawdzaj minimum elapsed time od ostatniego treningu (np. 24h)
   - Uwzględnij to w decyzji czy rozpocząć trening

3. Metoda _select_training_parameters (linia ~365):
   - Dodaj heurystyki doboru parametrów:
     - Dataset size → batch size (więcej danych = większe batche)
     - Dostępna VRAM → model size, batch size
     - Previous results → adjust learning rate
   - Zwróć inteligentnie dobrane parametry zamiast defaults

4. Dla TD-040 w venom_core/core/model_manager.py:262:
   - Dodaj ładowanie PEFT adapters (LoRA, QLoRA) dla fine-tuned models

5. Dodaj testy jednostkowe dla wszystkich metod

Kod powinien być konfigurowalny przez SETTINGS i dobrze udokumentowany.
```

---

### TS-011 – Cleanup pustych pass statements i error handling

**Powiązane:** TD-034, TD-035, TD-036, TD-037, TD-038, TD-039
**Priorytet:** NISKI
**Nakład:** MAŁY

**Prompt:**
```
Popraw empty pass statements i error handling w całym projekcie:

1. venom_core/agents/base.py:31:
   - Zmień `pass` na `raise NotImplementedError("Subclasses must implement process()")`

2. venom_core/infrastructure/cloud_provisioner.py:19:
   - Dodaj docstring do CloudProvisionerError lub usuń niepotrzebny pass

3. venom_core/agents/gardener.py:94, 144:
   - Dodaj logger.debug() w exception handlers wyjaśniające dlaczego ignorujemy

4. venom_core/core/tracer.py:86:
   - Dodaj logowanie błędu nawet jeśli exception jest expected

5. venom_core/execution/skills/test_skill.py:195, 200:
   - Dodaj komentarze lub logowanie wyjaśniające puste pass

6. venom_core/core/energy_manager.py:93:
   - Dodaj logger.debug("Temperature sensors not available on this platform")

Ogólnie: każdy empty pass w exception handler powinien mieć przynajmniej logger.debug() dla traceability.
Uruchom testy aby upewnić się że nic się nie zepsuło.
```

---

### TS-012 – Audit i aktualizacja dokumentacji

**Powiązane:** TD-041
**Priorytet:** ŚREDNI
**Nakład:** DUŻY

**Prompt:**
```
Przeprowadź audit dokumentacji w katalogu docs/ (26 plików markdown):

1. Dla każdego pliku w docs/*.md:
   - Przeczytaj dokumentację i porównaj z faktyczną implementacją w kodzie
   - Sprawdź czy opisane features są zaimplementowane
   - Oznacz features które są:
     - ✅ Zaimplementowane i działające
     - ⚠️ Częściowo zaimplementowane (placeholder)
     - ❌ Nie zaimplementowane

2. Utwórz raport: docs/DOCUMENTATION_AUDIT_REPORT.md z:
   - Lista plików dokumentacji
   - Status każdego opisanego feature
   - Recommended actions (zaktualizować, usunąć, dodać disclaimer)

3. Dla kluczowych dokumentów (THE_APPRENTICE.md, THE_FORGE.md, etc):
   - Zaktualizuj aby odzwierciedlały obecny stan kodu
   - Dodaj sekcję "Known Limitations" jeśli feature nie jest w pełni działający

4. Sprawdź spójność między README.md a implementacją

Nie zmieniaj kodu - tylko dokumentacja. Raport powinien być gotowy do wykorzystania w kolejnych zadaniach.
```

---

### TS-013 – Code quality improvements (helpers, watcher, tests coverage)

**Powiązane:** TD-042, TD-043, TD-044
**Priorytet:** NISKI
**Nakład:** DUŻY

**Prompt:**
```
Popraw quality i organizację kodu w obszarach pomocniczych:

1. venom_core/utils/helpers.py (TD-043):
   - Przejrzyj wszystkie funkcje w helpers.py
   - Rozdziel na tematyczne moduły: file_utils.py, string_utils.py, validation_utils.py
   - Każda funkcja powinna mieć docstring i type hints
   - Zaktualizuj imports w innych plikach

2. venom_core/perception/watcher.py vs desktop_sensor.py (TD-042):
   - Przeanalizuj funkcjonalność obu modułów
   - Dodaj komentarze wyjaśniające różnicę w przeznaczeniu
   - Jeśli są duplikaty - rozważ konsolidację lub wyjaśnij separation of concerns

3. Tests coverage (TD-044):
   - Uruchom: pytest --cov=venom_core --cov-report=html
   - Zidentyfikuj moduły z coverage < 50%
   - Utwórz raport: docs/TEST_COVERAGE_REPORT.md z:
     - Lista modułów i ich coverage %
     - Recommended priority areas dla dodania testów
   - Nie dodawaj testów teraz - tylko raport

Cel: lepsza organizacja i visibility do quality metrics.
```

---

## 4. PODSUMOWANIE I ZALECENIA

### Statystyki długu technicznego:
- **45 zidentyfikowanych issues** (TD-001 do TD-045)
- **Priorytety:** 9 HIGH, 26 MEDIUM, 10 LOW
- **Szacowany nakład:** 12 DUŻY, 20 ŚREDNI, 13 MAŁY
- **13 ziaren zadań** gotowych do realizacji

### Zalecana kolejność realizacji:

**FAZA 1 - Krytyczne (1-2 tygodnie):**
1. TS-007 - Refaktoryzacja main.py ⚠️
2. TS-008 - Refaktoryzacja orchestrator.py ⚠️
3. TS-001 - Nagrywanie akcji (Apprentice)
4. TS-002 - Shadow Agent integration

**FAZA 2 - Ważne (2-3 tygodnie):**
5. TS-006 - Scheduled jobs implementation
6. TS-005 - Git API endpoints
7. TS-009 - Standardization of interfaces
8. TS-003 - Evolution Coordinator features

**FAZA 3 - Ulepszenia (1-2 tygodnie):**
9. TS-004 - Azure OpenAI i LLM integrations
10. TS-010 - Professor Agent features
11. TS-012 - Documentation audit

**FAZA 4 - Cleanup (< 1 tydzień):**
12. TS-011 - Pass statements cleanup
13. TS-013 - Code quality improvements

### Długoterminowe rekomendacje:

1. **Monitoring długu technicznego:** Dodać pre-commit hook sprawdzający TODO/FIXME
2. **Code review guidelines:** Wymagać explanation dla każdego placeholder
3. **Architecture Decision Records:** Dokumentować kluczowe decyzje projektowe
4. **Refactoring sprints:** Co 2-3 miesiące dedykowany sprint na cleanup
5. **Coverage targets:** Minimum 70% test coverage dla core modules

---

**KONIEC RAPORTU**

Ten raport jest gotowy do użycia jako wsad dla kolejnych zadań refaktoryzacji i uzupełniania implementacji.
