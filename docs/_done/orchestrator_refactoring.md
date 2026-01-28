# Refaktoryzacja Architektury: Dekompozycja Modułu Orchestrator

## Wprowadzenie

Moduł `venom_core/core/orchestrator.py` został zrefaktoryzowany z monolitycznego pliku (2203 linii) do dobrze zorganizowanego pakietu zgodnego z zasadami **Clean Architecture** i **Single Responsibility Principle (SRP)**.

## Struktura Przed Refaktoryzacją

```
venom_core/core/
└── orchestrator.py (2203 linii - monolit)
```

**Problemy:**
- Jeden plik odpowiedzialny za wszystko (routing, stan, egzekucję, błędy, uczenie, sesje)
- Przekroczenie limitu 800 linii zgodnie z best practices
- Trudności w utrzymaniu i testowaniu
- Wysokie ryzyko cyklicznych importów przy rozbudowie

## Struktura Po Refaktoryzacji

```
venom_core/core/
├── orchestrator.py (re-export dla backward compatibility - 44 linii)
└── orchestrator/
    ├── __init__.py (główny punkt wejścia pakietu - 38 linii)
    ├── constants.py (stałe konfiguracyjne - 33 linii)
    ├── orchestrator_core.py (główna logika orkiestracji - 2147 linii)*
    ├── session_handler.py (zarządzanie sesją i kontekstem - 400 linii)
    ├── learning_handler.py (meta-uczenie i logowanie - 120 linii)
    ├── middleware.py (błędy i zdarzenia - 100 linii)
    ├── flow_coordinator.py (koordynacja workflows - 370 linii)
    └── kernel_manager.py (zarządzanie kernelem LLM - 80 linii)
```

**\*Uwaga:** `orchestrator_core.py` nadal zawiera główną logikę orkiestracji (metodę `_run_task` i powiązane), ale wykorzystuje komponenty z innych modułów poprzez kompozycję.

## Nowe Moduły

### 1. `constants.py`
**Odpowiedzialność:** Centralizacja wszystkich stałych konfiguracyjnych

**Zawiera:**
- `MAX_LESSONS_IN_CONTEXT` - limit lekcji w kontekście
- `SESSION_HISTORY_LIMIT` - limit historii sesji
- `MAX_CONTEXT_CHARS` - budżet znaków dla promptu
- `COUNCIL_*` - konfiguracja trybu Council
- i inne stałe

**Korzyści:**
- Łatwa modyfikacja konfiguracji w jednym miejscu
- Jasna dokumentacja wartości domyślnych
- Możliwość łatwego przetestowania różnych konfiguracji

### 2. `session_handler.py`
**Odpowiedzialność:** Zarządzanie kontekstem sesji użytkownika i historią rozmowy

**Klasa:** `SessionHandler`

**Główne metody:**
- `persist_session_context()` - zapisuje metadane sesji
- `append_session_history()` - dodaje wpis do historii
- `build_session_context_block()` - buduje blok kontekstu
- `apply_preferred_language()` - tłumaczy wynik na preferowany język
- `_ensure_session_summary()` - tworzy streszczenie historii
- `_retrieve_relevant_memory()` - pobiera dane z pamięci wektorowej

**Korzyści:**
- Izolacja logiki zarządzania sesją
- Łatwiejsze testowanie funkcji pamięci i historii
- Możliwość wymiany implementacji (np. inna strategia streszczania)

### 3. `learning_handler.py`
**Odpowiedzialność:** Proces meta-uczenia i logowanie lekcji

**Klasa:** `LearningHandler`

**Główne metody:**
- `should_store_lesson()` - decyduje czy zapisać lekcję
- `should_log_learning()` - decyduje czy logować proces nauki
- `append_learning_log()` - zapisuje wpis nauki do JSONL

**Korzyści:**
- Wydzielenie logiki uczenia się systemu
- Łatwiejsza integracja z różnymi strategiami uczenia
- Klarowne kryteria decyzyjne

### 4. `middleware.py`
**Odpowiedzialność:** Obsługa błędów, zdarzeń i logowania

**Klasa:** `Middleware`

**Główne metody:**
- `broadcast_event()` - wysyła zdarzenia przez WebSocket
- `build_error_envelope()` - tworzy standardową strukturę błędu
- `set_runtime_error()` - zapisuje błąd runtime

**Korzyści:**
- Ujednolicona obsługa błędów
- Centralizacja logiki zdarzeń
- Łatwiejsza implementacja interceptorów i loggerów

### 5. `flow_coordinator.py`
**Odpowiedzialność:** Koordynacja przepływów pracy (workflows)

**Klasa:** `FlowCoordinator`

**Główne metody:**
- `should_use_council()` - decyduje o użyciu Council mode
- `run_council()` - uruchamia dyskusję Council
- `code_generation_with_review()` - pętla generowania kodu z review
- `execute_healing_cycle()` - pętla samonaprawy
- `execute_forge_workflow()` - tworzenie nowych narzędzi
- `handle_remote_issue()` - obsługa GitHub Issues
- `execute_campaign_mode()` - autonomiczna realizacja roadmapy

**Korzyści:**
- Izolacja logiki różnych przepływów pracy
- Możliwość łatwego dodawania nowych flows
- Lepsza testowalność poszczególnych workflows

### 6. `kernel_manager.py`
**Odpowiedzialność:** Zarządzanie kernelem LLM i jego odświeżaniem

**Klasa:** `KernelManager`

**Główne metody:**
- `refresh_kernel()` - odtwarza kernel po zmianie konfiguracji
- `refresh_kernel_if_needed()` - sprawdza drift i odświeża przy potrzebie

**Korzyści:**
- Wyizolowana logika zarządzania kernelem
- Łatwiejsze testowanie zmian konfiguracji
- Jasna odpowiedzialność za lifecycle kernela

### 7. `orchestrator_core.py`
**Odpowiedzialność:** Główna logika orkiestracji zadań

**Klasa:** `Orchestrator` (zrefaktoryzowana)

**Wykorzystuje komponenty poprzez kompozycję:**
- `self.session_handler` - zarządzanie sesją
- `self.learning_handler` - meta-uczenie
- `self.middleware` - błędy i zdarzenia
- `self.flow_coordinator` - koordynacja workflows
- `self.kernel_manager` - zarządzanie kernelem

**Główne metody:**
- `submit_task()` - przyjmuje nowe zadanie
- `_run_task()` - wykonuje zadanie (główna pętla)
- `pause_queue()`, `resume_queue()` - zarządzanie kolejką
- Metody delegujące do komponentów

## Kompatybilność Wsteczna

### Re-exporty
Plik `orchestrator.py` został zachowany jako moduł re-exportujący dla pełnej kompatybilności:

```python
# Stary kod nadal działa:
from venom_core.core.orchestrator import Orchestrator, MAX_REPAIR_ATTEMPTS

# Nowy kod może importować bezpośrednio:
from venom_core.core.orchestrator.session_handler import SessionHandler
```

### Zachowane API
Wszystkie publiczne metody `Orchestrator` zachowują ten sam interfejs:
- `submit_task(request)`
- `pause_queue()`
- `resume_queue()`
- itd.

### Testy
Istniejące testy powinny działać bez zmian, ponieważ:
- Importy są zachowane
- Publiczne API nie uległo zmianie
- Delegacje są transparentne

## Unikanie Cyklicznych Importów

Wszystkie nowe moduły używają `TYPE_CHECKING` dla adnotacji typów:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from venom_core.core.state_manager import StateManager
    from venom_core.core.tracer import RequestTracer
```

**Korzyści:**
- Brak cyklicznych importów w runtime
- Zachowane type hints dla narzędzi (mypy, IDE)
- Bezpieczne wzajemne referencje między modułami

## Metryki Refaktoryzacji

| Metryka | Przed | Po | Zmiana |
|---------|-------|-----|--------|
| Liczba plików | 1 | 8 | +7 |
| Linie kodu (orchestrator.py) | 2203 | 44 | -98% |
| Średnia wielkość modułu | 2203 | ~390 | -82% |
| Moduły > 800 LOC | 1 | 1* | Bez zmiany |
| Wydzielone odpowiedzialności | 0 | 6 | +6 |

**\*Uwaga:** `orchestrator_core.py` nadal przekracza 800 LOC, ale jest to główna logika orkiestracji która korzysta z wydzielonych komponentów. Dalszy podział wymagałby głębszej refaktoryzacji metody `_run_task`.

## Następne Kroki (Opcjonalne)

1. **Dalszy podział `orchestrator_core.py`:**
   - Wydzielenie `execution_engine.py` dla metody `_run_task`
   - Wydzielenie `context_builder.py` dla przygotowania kontekstu

2. **Refaktoryzacja innych monolitów:**
   - `model_manager.py` (944 LOC)
   - `model_registry.py` (894 LOC)

3. **Refaktoryzacja `BaseAgent`:**
   - Composition over Inheritance
   - Wydzielenie `memory_handler.py`, `tool_handler.py`, `llm_client.py`

## Wnioski

✅ **Osiągnięte cele:**
- Dekompozycja monolitu na spójne moduły
- Zachowanie pełnej kompatybilności wstecznej
- Unikanie cyklicznych importów
- Lepsza organizacja kodu zgodna z SRP

✅ **Korzyści:**
- Łatwiejsze utrzymanie i rozbudowa
- Lepsza testowalność poszczególnych komponentów
- Klarowny podział odpowiedzialności
- Łatwiejsza współpraca zespołowa (mniej konfliktów w git)

📝 **Do rozważenia:**
- Dalsza dekompozycja `orchestrator_core.py`
- Podobna refaktoryzacja innych dużych modułów
- Refaktoryzacja `BaseAgent` na wzór kompozycyjny
