# Orchestrator Package

Zrefaktoryzowany moduł orkiestracji zadań w systemie Venom.

## Struktura Pakietu

```
orchestrator/
├── __init__.py              # Punkt wejścia pakietu, re-exporty
├── constants.py             # Stałe konfiguracyjne
├── orchestrator_core.py     # Główna logika orkiestracji
├── session_handler.py       # Zarządzanie sesją i kontekstem
├── learning_handler.py      # Meta-uczenie i logowanie lekcji
├── middleware.py            # Obsługa błędów i zdarzeń
├── flow_coordinator.py      # Koordynacja przepływów pracy
└── kernel_manager.py        # Zarządzanie kernelem LLM
```

## Użycie

### Import (backward compatible)

```python
# Stary sposób - nadal działa
from venom_core.core.orchestrator import Orchestrator, MAX_CONTEXT_CHARS

# Nowy sposób - bezpośrednio z pakietu
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.orchestrator.constants import MAX_CONTEXT_CHARS
```

### Inicjalizacja

```python
from venom_core.core.state_manager import StateManager
from venom_core.core.orchestrator import Orchestrator

state_manager = StateManager("state.json")
orchestrator = Orchestrator(state_manager)

# Orchestrator automatycznie inicjalizuje wszystkie komponenty:
# - session_handler
# - learning_handler
# - middleware
# - flow_coordinator
# - kernel_manager
```

## Moduły

### constants.py
Centralne miejsce dla wszystkich stałych konfiguracyjnych:
- Limity kontekstu i historii
- Ustawienia meta-uczenia
- Konfiguracja Council mode
- Parametry streszczania

### session_handler.py
Zarządzanie sesją użytkownika:
- Persystencja kontekstu sesji
- Historia rozmowy
- Streszczanie długich sesji
- Pamięć wektorowa
- Tłumaczenie na preferowany język

### learning_handler.py
Proces meta-uczenia systemu:
- Decyzje o zapisywaniu lekcji
- Logowanie procesów nauki
- Kryteria uczenia się

### middleware.py
Obsługa błędów i zdarzeń:
- Broadcasting zdarzeń przez WebSocket
- Standardowe struktury błędów
- Logowanie runtime errors

### flow_coordinator.py
Koordynacja złożonych przepływów pracy:
- Council mode (group chat)
- Code generation with review
- Healing cycle (auto-repair)
- Forge workflow (tool creation)
- GitHub issue handling
- Campaign mode (autonomous execution)

### kernel_manager.py
Zarządzanie kernelem LLM:
- Odświeżanie kernela przy zmianie konfiguracji
- Detekcja drift konfiguracji
- Lifecycle management

### orchestrator_core.py
Główna logika orkiestracji zadań:
- Submit i execute zadań
- Zarządzanie kolejką
- Integracja wszystkich komponentów

## Zasady Projektowe

1. **Single Responsibility Principle (SRP)**
   - Każdy moduł ma jedną, jasno określoną odpowiedzialność

2. **Composition over Inheritance**
   - Orchestrator składa się z komponentów, nie dziedziczy po nich

3. **TYPE_CHECKING dla importów**
   - Unikanie circular dependencies w runtime
   - Zachowane type hints dla narzędzi

4. **Backward Compatibility**
   - Pełna kompatybilność z istniejącym kodem
   - Re-exporty w `__init__.py`

## Przykłady

### Użycie SessionHandler bezpośrednio

```python
from venom_core.core.orchestrator.session_handler import SessionHandler
from venom_core.memory.memory_skill import MemorySkill

memory_skill = MemorySkill()
session_handler = SessionHandler(
    state_manager=state_manager,
    memory_skill=memory_skill,
    testing_mode=False
)

# Zbuduj kontekst sesji
context = session_handler.build_session_context_block(request, task_id)
```

### Użycie FlowCoordinator

```python
from venom_core.core.orchestrator.flow_coordinator import FlowCoordinator

flow_coordinator = FlowCoordinator(
    state_manager=state_manager,
    task_dispatcher=task_dispatcher,
    event_broadcaster=event_broadcaster
)

# Sprawdź czy użyć Council mode
if flow_coordinator.should_use_council(context, intent):
    result = await flow_coordinator.run_council(task_id, context, middleware)
```

## Testy

Testy powinny działać bez zmian dzięki zachowanej kompatybilności wstecznej:

```python
# Istniejące testy nadal działają
from venom_core.core.orchestrator import Orchestrator, SESSION_HISTORY_LIMIT

def test_orchestrator():
    orchestrator = Orchestrator(state_manager)
    assert orchestrator is not None
```

## Dokumentacja

Szczegółowa dokumentacja refaktoryzacji dostępna w:
`docs/architecture/orchestrator_refactoring.md`

## Kontrybutorzy

Refaktoryzacja przeprowadzona zgodnie z zasadami Venom v2:
- Clean Architecture
- Single Responsibility Principle
- Composition over Inheritance
- Type Safety (TYPE_CHECKING)
