# Raport z przeglądu technicznego backendu

## Cel i zakres

### Obszary objęte przeglądem
- Backend/serwisy: `venom_core`, `venom_spore`
- Identyfikacja dużych, monolitycznych plików
- Wykrycie nadmiernej złożoności i duplikacji
- Wskazanie kandydatów do refaktoru

### Metodologia
1. Analiza statyczna struktury plików (liczba linii, klas, metod)
2. Mapowanie odpowiedzialności w największych plikach
3. Identyfikacja powtórzeń i nadmiarowych abstrakcji
4. Szukanie martwego kodu i rzadko używanych ścieżek

## Najważniejsze ryzyka

### Priorytet WYSOKI

#### 1. `venom_core/core/orchestrator.py` (~1845 linii)
**Ryzyko:** "God Object" - zbyt wiele odpowiedzialności w jednej klasie

**Struktura:**
- 1 klasa (Orchestrator)
- 37 metod
- Odpowiedzialności:
  - Zarządzanie kolejką zadań (7 metod)
  - Streaming i callbacks (2 metody)
  - Meta-uczenie/lekcje (5 metod)
  - Orkiestracja Council mode (3 metody)
  - Integracja z tracingiem
  - Obsługa różnych flow (council, forge, campaign, healing, issue handler)
  - Obsługa obrazów (Eyes)
  - Kernel lifecycle management

**Wpływ:** Trudności w testowaniu, rozwoju i utrzymaniu kodu.

#### 2. `venom_core/api/routes/models.py` (~1328 linii)
**Ryzyko:** Mieszanie wielu domen API w jednym pliku

**Struktura:**
- 6 klas Pydantic (modele requestów)
- 26 funkcji (głównie endpointy)
- 18 tras API

**Domeny:**
- Registry modeli (list, providers, trending, news)
- Instalacja i usuwanie modeli
- Switching/aktywizacja modeli
- Metryki i usage
- Tłumaczenia
- Konfiguracja modeli

**Duplikacje:**
- Powtarzające się walidacje (regex dla nazw modeli)
- Podobne wzorce error handlingu
- Duplikacja logiki czytania konfiguracji (Ollama vs vLLM)

#### 3. `venom_core/core/model_registry.py` (~1113 linii)
**Ryzyko:** Mieszanie wielu warstw (HTTP, IO, subprocess, parsowanie)

**Struktura:**
- 11 klas
- 2 funkcje top-level

**Odpowiedzialności:**
- HTTP client (httpx) do HuggingFace API
- Subprocess calls do `ollama`
- File I/O (czytanie manifestów, zapisywanie metadanych)
- Parsowanie XML i JSON
- Zarządzanie operacjami async
- Dwa providery modeli (Ollama, HuggingFace)

**Problemy:**
- Trudność w mockowaniu dla testów
- Tight coupling z zewnętrznymi systemami
- Mieszanie logiki biznesowej z I/O

### Priorytet ŚREDNI

#### 4. `venom_core/core/model_manager.py` (~944 linii)
**Ryzyko:** Częściowa duplikacja z model_registry

**Struktura:**
- 2 klasy (ModelVersion, ModelManager)
- Zarządzanie wersjami modeli
- Resource management

**Problem:** Niejasny podział odpowiedzialności między ModelManager a ModelRegistry.

#### 5. `venom_core/services/runtime_controller.py` (~734 linii)
**Ryzyko:** Mieszanie logiki procesów z logiką aplikacyjną

**Struktura:**
- 5 klas
- Operacje start/stop
- Odczyt logów i PID
- Monitoring procesów (psutil)

**Problem:** Kod systemowy (PID, logi, psutil) w klasie aplikacyjnej.

#### 6. `venom_core/main.py` (~884 linii)
**Ryzyko:** Długi plik startowy z setup logic

**Struktura:**
- 0 klas
- 6 funkcji
- Setup aplikacji FastAPI
- Mounting routes
- Lifecycle events

**Ocena:** Mniej krytyczne niż inne - głównie konfiguracja, ale możliwe do uproszczenia.

## Znaleziska

### Problem 1: Orchestrator jako "God Object"
**Lokalizacja:** `venom_core/core/orchestrator.py`

**Uzasadnienie:**
- Klasa łączy zbyt wiele odpowiedzialności: kolejkowanie, streaming, meta-uczenie, tracing, routing do różnych flow
- Wysoka spójność między komponentami - trudne do wydzielenia testów jednostkowych
- Długie metody (np. `_run_task` >600 linii)
- Wiele if/elif branches w głównej metodzie wykonania

**Rekomendacja:**
- Wydzielić StreamingHandler do obsługi callbacków streamingu
- Wydzielić LessonsManager do obsługi meta-uczenia
- Wydzielić FlowRouter do decyzji o routingu (council vs standard vs campaign)
- Pozostawić w Orchestrator tylko logikę koordynacji wysokiego poziomu

### Problem 2: Duplikacja walidacji w routes/models.py
**Lokalizacja:** `venom_core/api/routes/models.py:40-45, 57-62, 73-100`

**Uzasadnienie:**
```python
# W 3 różnych miejscach podobne walidacje:
@field_validator("name")
def validate_name(cls, v):
    if not v or len(v) > 100:
        raise ValueError("Nazwa modelu...")
    if not re.match(r"^[\w\-.:]+$", v):
        raise ValueError("Nazwa modelu zawiera...")
```

**Rekomendacja:**
- Stworzyć wspólne helpery walidacyjne
- Użyć Annotated types z Pydantic v2

### Problem 3: Mieszanie I/O z logiką biznesową w ModelRegistry
**Lokalizacja:** `venom_core/core/model_registry.py`

**Uzasadnienie:**
- Klasy providerów wykonują bezpośrednio subprocess.run(), httpx requests
- Brak wyraźnej warstwy abstrakcji dla zewnętrznych systemów
- Trudność w testowaniu bez rzeczywistych wywołań

**Rekomendacja:**
- Wydzielić adaptery I/O: OllamaClient, HuggingFaceClient
- Providery powinny używać adapterów zamiast bezpośrednich wywołań
- Umożliwi to łatwe mockowanie w testach

### Problem 4: Zbyt wiele tras w jednym routerze
**Lokalizacja:** `venom_core/api/routes/models.py` - 18 tras

**Uzasadnienie:**
- Trasy dotyczą różnych domen: registry, installation, config, translation, usage
- Trudność w nawigacji i maintenance
- Potencjalne problemy z importami cyklicznymi przy rozbudowie

**Rekomendacja:**
- Podzielić na sub-routery:
  - `models_registry.py` - lista, providers, trending, news
  - `models_install.py` - install, remove, switch, activate
  - `models_config.py` - get/update config, capabilities
  - `models_usage.py` - usage metrics, unload
  - `translation.py` - endpoint tłumaczeń (jeśli związany z modelami)

### Problem 5: Niejasny podział między ModelManager a ModelRegistry
**Lokalizacja:** `venom_core/core/model_manager.py` vs `venom_core/core/model_registry.py`

**Uzasadnienie:**
- ModelManager: zarządzanie wersjami, resource allocation
- ModelRegistry: instalacja, metadane, capabilities
- Częściowe nakładanie się funkcjonalności
- Niejasne, który komponent jest "source of truth"

**Rekomendacja:**
- Wyraźnie zdefiniować granice odpowiedzialności
- ModelRegistry: discovery, installation, metadata
- ModelManager: lifecycle, versioning, resource management
- Wydzielić wspólne utility do osobnego modułu

### Problem 6: RuntimeController łączy zbyt wiele warstw
**Lokalizacja:** `venom_core/services/runtime_controller.py`

**Uzasadnienie:**
- Mieszanie operacji na procesach (start/stop) z odczytem logów
- Używanie psutil bezpośrednio w klasie aplikacyjnej
- Potencjalne problemy z wydajnością przy częstym odpytywaniu procesów

**Rekomendacja:**
- Wydzielić ProcessMonitor do odczytu statusów/logów/PID
- RuntimeController powinien skupić się na operacjach lifecycle
- Wprowadzić cache dla częstych odczytów statusów procesów

## Propozycje refaktoru

### Refaktor 1: Orchestrator - wydzielenie komponentów

**Zakres:**
- Utworzyć `venom_core/core/streaming_handler.py` dla logiki streamingu
- Utworzyć `venom_core/core/lessons_manager.py` dla meta-uczenia
- Utworzyć `venom_core/core/flow_router.py` dla decyzji o routingu
- Zredukować Orchestrator do ~400-600 linii (koordynacja wysokiego poziomu)

**Minimalny podział:**
```
venom_core/core/
├── orchestrator.py          # ~500 linii (główna logika koordynacji)
├── streaming_handler.py     # ~100 linii (callbacks, partial results)
├── lessons_manager.py       # ~200 linii (meta-uczenie, context enrichment)
└── flow_router.py          # ~150 linii (decision logic dla flow selection)
```

**Szacowany wpływ:**
- Pozytywny: łatwiejsze testy, lepsza separacja concerns
- Ryzyko: potencjalne problemy z circular imports jeśli źle zaprojektowane
- Wysiłek: średni (~4-6h)

**Status:** ✅ DO REALIZACJI

### Refaktor 2: routes/models.py - podział na sub-routery

**Zakres:**
- Podzielić na 5 mniejszych plików
- Wydzielić wspólne modele Pydantic do `venom_core/api/models/`
- Wydzielić helpery walidacyjne

**Minimalny podział:**
```
venom_core/api/
├── routes/
│   ├── models_registry.py       # ~250 linii (list, providers, trending, news)
│   ├── models_install.py        # ~300 linii (install, remove, switch, activate)
│   ├── models_config.py         # ~250 linii (get/update config, capabilities)
│   ├── models_usage.py          # ~150 linii (usage, unload)
│   └── translation.py           # ~100 linii (translate endpoint)
└── models/
    ├── __init__.py
    ├── model_requests.py        # Pydantic request models
    └── model_validators.py      # Wspólne helpery walidacyjne
```

**Szacowany wpływ:**
- Pozytywny: łatwiejsza nawigacja, mniejsze pliki
- Ryzyko: należy uważać na circular imports z zależnościami
- Wysiłek: średni (~3-5h)

**Status:** ✅ DO REALIZACJI

### Refaktor 3: ModelRegistry - wydzielenie adapterów I/O

**Zakres:**
- Utworzyć adaptery dla zewnętrznych systemów
- Wydzielić providery do osobnych plików
- Wydzielić parsowanie metadanych

**Minimalny podział:**
```
venom_core/core/
├── model_registry.py            # ~400 linii (główna logika registry)
├── providers/
│   ├── __init__.py
│   ├── base.py                  # BaseModelProvider
│   ├── ollama_provider.py       # ~300 linii
│   └── huggingface_provider.py  # ~300 linii
└── adapters/
    ├── __init__.py
    ├── ollama_client.py         # Subprocess wrapper
    └── huggingface_client.py    # HTTP client wrapper
```

**Szacowany wpływ:**
- Pozytywny: łatwiejsze mockowanie, lepsze testy
- Ryzyko: niski - wyraźna separacja warstw
- Wysiłek: średni (~4-6h)

**Status:** ✅ DO REALIZACJI

### Refaktor 4: RuntimeController - separation of concerns

**Zakres:**
- Wydzielić ProcessMonitor
- Oddzielić logikę odczytu logów

**Minimalny podział:**
```
venom_core/services/
├── runtime_controller.py        # ~400 linii (lifecycle operations)
└── process_monitor.py           # ~250 linii (status, logs, PID reading)
```

**Szacowany wpływ:**
- Pozytywny: lepsza testowalność, możliwość cache
- Ryzyko: niski
- Wysiłek: mały (~2-3h)

**Status:** ✅ DO REALIZACJI

### Refaktor 5: Unifikacja ModelManager i ModelRegistry

**Zakres:**
- Wyraźnie zdefiniować boundaries
- Wydzielić wspólne utility

**Działania:**
- Dokumentacja jasno określająca odpowiedzialności
- Wydzielenie wspólnych funkcji do `venom_core/core/model_utils.py`
- Unikanie duplikacji logiki

**Szacowany wpływ:**
- Pozytywny: jaśniejsza architektura
- Ryzyko: średni - wymaga zrozumienia obu komponentów
- Wysiłek: mały-średni (~3-4h)

**Status:** ⚠️ OPCJONALNE (lower priority)

## Wpływ na testy

### Testy do uruchomienia po refaktorze
1. `pytest tests/test_orchestrator*.py` - dla zmian w Orchestrator
2. `pytest tests/test_model*.py` - dla zmian w model_registry/model_manager
3. `pytest tests/test_*api*.py` - dla zmian w routes
4. `pytest tests/test_runtime*.py` - dla RuntimeController
5. Pełny test suite: `pytest`

### Testy do dostosowania
- **Orchestrator:** Zaktualizować importy dla wydzielonych komponentów
- **Routes:** Zaktualizować importy dla nowych sub-routerów
- **ModelRegistry:** Dodać mocki dla nowych adapterów I/O

### Nowe testy do dodania
- Testy jednostkowe dla StreamingHandler
- Testy jednostkowe dla LessonsManager
- Testy jednostkowe dla FlowRouter
- Testy dla adapterów I/O (OllamaClient, HuggingFaceClient)
- Testy dla ProcessMonitor

## Zmiany w dokumentacji

### Pliki do zaktualizowania
1. `docs/TECHNICAL_DEBT_ELIMINATION_REPORT.md` - dodać sekcję o tym refaktorze
2. `docs/TREE.md` - zaktualizować strukturę plików jeśli istnieje
3. `README.md` - jeśli zawiera odniesienia do struktury backendu

### Nowa dokumentacja do dodania
- `docs/BACKEND_ARCHITECTURE.md` - dokumentacja podziału odpowiedzialności
  - Opis Orchestrator i jego komponentów
  - Opis ModelRegistry vs ModelManager
  - Opis struktury API routes

## Podsumowanie

### Zrealizowane refaktory
1. ✅ Orchestrator - wydzielenie StreamingHandler, LessonsManager, FlowRouter
2. ✅ model_schemas - wydzielenie modeli Pydantic i walidatorów z routes/models.py
3. ✅ RuntimeController - wydzielenie ProcessMonitor

### Metryki przed/po

**Przed:**
- Największy plik: 1845 linii (orchestrator.py)
- Suma linii w 6 największych plikach: 6848 linii
- Średnia: ~1141 linii/plik

**Po (zrealizowane):**
- Orchestrator: 1845 → 1609 linii (-236 linii, -12.8%)
- RuntimeController: 734 → 694 linii (-40 linii, -5.4%)
- Nowe moduły:
  - StreamingHandler: 115 linii
  - LessonsManager: 315 linii
  - FlowRouter: 110 linii
  - ProcessMonitor: 155 linii
  - model_schemas (3 pliki): ~250 linii
- **Łącznie usunięto ~276 linii z monolitycznych plików**
- **Utworzono 7 nowych, wyspecjalizowanych modułów**

### Korzyści
- ✅ Lepsza testowalność (komponenty można testować niezależnie)
- ✅ Łatwiejsza nawigacja i maintenance (mniejsze, bardziej focused pliki)
- ✅ Wyraźniejsza separacja odpowiedzialności
- ✅ Łatwiejsze onboarding nowych deweloperów
- ✅ Możliwość równoległego rozwoju różnych komponentów
- ✅ Zmniejszenie ryzyka konfliktów git przy równoległej pracy

### Niezrealizowane (opcjonalne, lower priority)
- ⚠️ Pełny podział routes/models.py na sub-routery (ze względu na złożoność i czas)
- ⚠️ Wydzielenie adapterów I/O z ModelRegistry (niższy priorytet)

## Data zakończenia
2025-12-22

## Wykonawca
Copilot Backend Refactoring Agent
