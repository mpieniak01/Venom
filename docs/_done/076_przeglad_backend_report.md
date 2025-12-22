# 076: Przegląd techniczny backendu - Raport refaktoryzacji

## Data wykonania
2024-12-22

## Cel i zakres

### Cel
Znaleźć nieoptymalny, nadmiernie skomplikowany lub niewydajny kod w backendzie Venom, wykryć zbyt duże pliki monolityczne oraz martwy kod, wskazać kandydatów do refaktoru i zrealizować kluczowe uproszczenia.

### Zakres
- Backend/serwisy: `venom_core`, `venom_spore`
- Fokus na plikach >700 linii
- Analiza odpowiedzialności i spójności modułów

## Najważniejsze ryzyka (priorytet malejący)

### 1. ⚠️ WYSOKIE: orchestrator.py (1845 linii, 47 metod)
**Problem:** "God Object" łączący wiele niezwiązanych odpowiedzialności
- Orkiestracja zadań i kolejkowanie
- Streaming callbacks i TTFT metrics
- Meta-learning (lessons store)
- Flow routing (council/forge/healing/campaign)
- Intent classification i decision gates
- Request tracing

**Ryzyko:** Trudności w testowaniu, wysokie ryzyko regresji przy zmianach, słaba możliwość ponownego użycia komponentów.

### 2. ⚠️ WYSOKIE: api/routes/models.py (1328 linii, 21 endpointów)
**Problem:** Różne domeny w jednym pliku
- Model listing/installation (Ollama)
- Model registry operations (HuggingFace)
- Model configuration/capabilities
- Translation service endpoint
- Generation parameters management
- Duplikacja walidacji (regex patterns powtarzane 4x)

**Ryzyko:** Trudności w nawigacji, duplikacja logiki walidacji, niespójna odpowiedzialność routera.

### 3. ⚠️ ŚREDNIE: model_registry.py (1113 linii)
**Problem:** Mieszanie warstw
- HTTP client (httpx) bezpośrednio w klasie
- Subprocess operations (`ollama pull`, `huggingface_hub`)
- File I/O (cache, manifests)
- Business logic (metadata, capabilities)

**Ryzyko:** Trudności w testowaniu (mockowanie subprocess/HTTP), ścisłe powiązanie z infrastrukturą.

### 4. ⚠️ ŚREDNIE: model_manager.py (944 linii) - duplikacja z registry
**Problem:** Częściowo pokrywająca się odpowiedzialność
- Model manager: versioning, hot-swap, genealogia
- Model registry: installation, providers, metadata
- Oba zarządzają cache'em i plikami modeli

**Ryzyko:** Niejednoznaczne "źródło prawdy", potencjalna duplikacja danych.

### 5. ⚠️ NISKIE: runtime_controller.py (734 linii)
**Problem:** Łączenie systemowych operacji
- Process management (PID, start/stop)
- Log reading
- Resource monitoring (CPU/RAM via psutil)

**Ryzyko:** Umiarkowane - można dalej refaktoryzować, ale funkcjonalność jest spójna.

## Znaleziska i rekomendacje

### orchestrator.py

#### Problem 1: Inline streaming callback (linie 768-817)
**Lokalizacja:** `async def _run_task()` - nested function `_handle_stream_chunk`

**Uzasadnienie:** Logika streamingu (50+ linii) zagnieżdżona w metodzie wykonania zadania. Trudna do testowania, niemożliwa do ponownego użycia.

**Rekomendacja:** ✅ **ZREALIZOWANE**
- Wydzielono `venom_core.core.streaming.StreamingHandler`
- Klasa hermetyzuje stan streamingu (buffer, timers, metrics)
- Metoda `get_callback()` zwraca callable dla `set_llm_stream_callback`
- Usunięto ~50 linii z orchestratora

**Wpływ:** Orchestrator zmniejszony o ~50 linii, lepsza testowalność.

#### Problem 2: Meta-learning rozproszony (4 metody)
**Lokalizacja:**
- `_should_store_lesson()` (linia 465)
- `_add_lessons_to_context()` (linia 1252)
- `_save_task_lesson()` (linia 1303)
- `_should_log_learning()` (linia 1395)
- `_append_learning_log()` (linia 1413)

**Uzasadnienie:** 5 metod obsługujących lessons store, łącznie ~200 linii. Logika ściśle związana z `lessons_store`, ale rozrzucona po orchestratorze.

**Rekomendacja:** ⚠️ **DO ROZWAŻENIA**
- Opcja A (preferowana): Delegować całą logikę do `LessonsStore` - dodać metody `should_store()`, `enrich_context()`, `save_lesson()`
- Opcja B: Utworzyć `MetaLearningCoordinator` jako facade dla lessons operations

**Wpływ szacowany:** -150 linii z orchestratora, wyższa spójność.

#### Problem 3: Flow routing (council/forge/healing/campaign)
**Lokalizacja:** Inicjalizacja lazy (linie 101-107), decyzje routingu (linie 820-915)

**Uzasadnienie:** Flows są już wydzielone do `core/flows/`, ale orchestrator zawiera decision gates.

**Rekomendacja:** ✅ **STRUKTURA OK**
- Flows są poprawnie wydzielone
- Decision gates są uzasadnione w orchestratorze (central routing)
- **Nie wymagapoprawy** - obecna struktura jest adekwatna

### api/routes/models.py

#### Problem 1: Duplikacja walidacji
**Lokalizacja:** Klasy Pydantic (linie 34-131)
- `ModelInstallRequest.validate_name` - regex `^[\w\-.:]+$`
- `ModelSwitchRequest.validate_name` - **identyczny regex**
- `ModelRegistryInstallRequest.validate_name` - regex `^[\w\-.:\/]+$`
- `ModelActivateRequest.validate_name` - **identyczny regex** z registry
- `validate_provider` - powtarzane 2x
- `validate_runtime` - powtarzane 3x

**Uzasadnienie:** ~60 linii duplikacji. Każda zmiana wymagałaby aktualizacji w 4 miejscach.

**Rekomendacja:** ✅ **ZREALIZOWANE**
- Utworzono `venom_core.api.validators` z funkcjami:
  - `validate_model_name(name, max_length, allow_slash)`
  - `validate_provider(provider)`
  - `validate_runtime(runtime)`
  - `validate_huggingface_model_name(name)`
  - `validate_ollama_model_name(name)`
- Pydantic validators delegują do wspólnych funkcji
- Usunięto ~60 linii duplikacji

**Wpływ:** -60 linii z routes/models.py, single source of truth dla walidacji.

#### Problem 2: Różne domeny w jednym routerze
**Lokalizacja:** 21 endpointów w jednym pliku
- Core operations: `/models` (list), `/models/install`, `/models/switch`, `/models/{model_name}` (delete)
- Registry operations: `/models/registry/install`, `/models/registry/{model_name}`, `/models/activate`
- Configuration: `/models/{model_name}/capabilities`, `/models/{model_name}/config`
- Utilities: `/models/usage`, `/models/unload-all`, `/models/providers`, `/models/trending`, `/models/news`
- Translation: `/translate` (nie związany z modelami!)

**Uzasadnienie:** Różne domeny biznesowe w jednym module. Narusza Single Responsibility Principle.

**Rekomendacja:** ⚠️ **DO ROZWAŻENIA** (opcjonalne)
- Podział na mniejsze routery:
  - `models_core.py` - list, install, switch, delete, usage
  - `models_registry.py` - registry operations, activate, operations
  - `models_config.py` - capabilities, config, generation params
  - `models_discovery.py` - providers, trending, news
  - `translation.py` - translate endpoint (przenieść do osobnego routera)

**Uwaga:** Wymaga refaktoru w `main.py` (router mounting). Średni effort, średni benefit.

**Wpływ szacowany:** Lepsza organizacja, ale wymagałoby ~5 nowych plików i aktualizacji `main.py`.

### model_registry.py

#### Problem: HTTP i subprocess bezpośrednio w klasach
**Lokalizacja:**
- `OllamaModelProvider.list_available_models()` - httpx (linia 227)
- `OllamaModelProvider.install_model()` - subprocess (linia 280)
- `HuggingFaceModelProvider.install_model()` - huggingface_hub (linia 460)

**Uzasadnienie:** Ścisłe powiązanie z infrastrukturą. Trudne mockowanie w testach.

**Rekomendacja:** ⚠️ **DO ROZWAŻENIA W PRZYSZŁOŚCI**
- Utworzenie adapterów:
  - `OllamaHTTPClient` - wrapper dla httpx calls
  - `OllamaCLIClient` - wrapper dla subprocess
  - `HuggingFaceClient` - wrapper dla HF Hub
- Dependency injection do providerów

**Uwaga:** Wymagałoby znacznego refaktoru testów i ~3-4 nowych plików. **Odroczono** ze względu na constraint "nie mnożyć bytów".

**Wpływ szacowany:** Lepsza testowalność, ale wysokie koszty refaktoru.

### model_manager.py vs model_registry.py

#### Problem: Nakładające się odpowiedzialności
**Lokalizacja:**
- `ModelManager` - versioning (linia 24), hot-swap (linia 68), Ollama cache (linia 89)
- `ModelRegistry` - installation (linia 510), metadata (linia 116), providers (linia 217)
- Oba zarządzają plikami w `data/models/`

**Uzasadnienie:** Niejednoznaczne rozgraniczenie. Developer nie wie, którego użyć.

**Rekomendacja:** ⚠️ **WYMAGA DECYZJI ARCHITEKTONICZNEJ**
- Opcja A: `ModelRegistry` jako "source of truth" - installation, metadata. `ModelManager` deprecated/usunięty.
- Opcja B: `ModelManager` fokus na versioning/hot-swap. `ModelRegistry` fokus na installation/discovery. Jasny podział odpowiedzialności w dokumentacji.

**Preferowana:** Opcja B z dokumentacją użycia w `docs/MODEL_MANAGEMENT.md`.

**Wpływ:** Wymaga decyzji biznesowej, potencjalnie usunięcie lub refaktor jednej klasy.

### runtime_controller.py

#### Problem: Process operations + log reading
**Lokalizacja:**
- `_get_process_info()` - psutil (linia 92)
- `_read_latest_log()` - file I/O (linia ~400)
- `start_service()`, `stop_service()` - subprocess (linia ~500)

**Uzasadnienie:** Spójna funkcjonalność (runtime control), ale można wydzielić log reader.

**Rekomendacja:** ⚠️ **NISKI PRIORYTET**
- Opcjonalnie: wydzielić `LogReader` helper
- Obecna struktura jest akceptowalna

**Wpływ:** Minimalny - obecna struktura jest zadowalająca.

## Propozycje refaktoru

### Zrealizowane refaktory (✅)

#### 1. Wydzielenie StreamingHandler z orchestrator.py
**Zakres:**
- Utworzono `venom_core/core/streaming.py`
- Klasa `StreamingHandler` (~115 linii)
- Metody: `handle_chunk()`, `get_result()`, `get_callback()`, `_record_first_token()`

**Minimalny podział:**
```
venom_core/core/
├── orchestrator.py (-50 linii)
└── streaming.py (nowy, 115 linii)
```

**Wpływ:**
- ✅ Orchestrator bardziej czytelny
- ✅ Streaming handler testowalny w izolacji
- ✅ Możliwość ponownego użycia w innych miejscach

#### 2. Wydzielenie wspólnych walidatorów do api/validators.py
**Zakres:**
- Utworzono `venom_core/api/validators.py`
- Funkcje: `validate_model_name`, `validate_provider`, `validate_runtime`, `validate_huggingface_model_name`, `validate_ollama_model_name`, `validate_generation_params`

**Minimalny podział:**
```
venom_core/api/
├── routes/models.py (-60 linii duplikacji)
└── validators.py (nowy, 205 linii)
```

**Wpływ:**
- ✅ Usunięto duplikację walidacji
- ✅ Single source of truth dla validation rules
- ✅ Łatwiejsze utrzymanie i testowanie

### Proponowane refaktory do rozważenia (⚠️)

#### 1. Meta-learning coordinator z orchestrator.py
**Zakres:** ~150 linii
**Effort:** Średni (1-2h)
**Benefit:** Wysoki - lepsza spójność, łatwiejsze testowanie lessons

#### 2. Podział routes/models.py na mniejsze routery
**Zakres:** ~1200 linii → 4-5 plików po 200-300 linii
**Effort:** Wysoki (4-6h + testy)
**Benefit:** Średni - lepsza organizacja, ale wymaga zmian w wielu miejscach

#### 3. Unifikacja model_manager.py i model_registry.py
**Zakres:** Decyzja architektoniczna + refaktor
**Effort:** Bardzo wysoki (8-12h)
**Benefit:** Wysoki - ale wymaga jasnej decyzji biznesowej

### Odroczone refaktory (❌)

#### 1. Wydzielenie IO adapters z model_registry.py
**Powód:** Constraint "nie mnożyć bytów", wysokie koszty refaktoru, niski immediate benefit

#### 2. Kompletny refaktor orchestrator.py na mikroserwisy
**Powód:** Constraint "nie przebudowywać backendu w mikroserwisy"

## Wpływ na testy

### Testy do dostosowania (✅ priorytet)
- `tests/test_orchestrator*.py` - aktualizacja importów dla `StreamingHandler`
- `tests/test_model_registry.py` - potencjalnie dodać testy dla nowych walidatorów
- Nowe testy jednostkowe:
  - `tests/test_streaming.py` - testy dla `StreamingHandler`
  - `tests/test_validators.py` - testy dla `api.validators`

### Testy do uruchomienia (weryfikacja braku regresji)
```bash
# Testy core orchestrator
pytest tests/test_orchestrator*.py -v

# Testy API models
pytest tests/test_model_registry.py tests/test_model_manager.py -v

# Testy integracyjne
pytest tests/test_api_dependencies.py -v
```

### Nowe testy utworzone
- ⚠️ **TODO:** `tests/test_streaming.py` - unit testy dla StreamingHandler
- ⚠️ **TODO:** `tests/test_validators.py` - unit testy dla validators

## Zmiany w dokumentacji

### Pliki do aktualizacji
1. **docs/MODEL_MANAGEMENT.md** (jeśli istnieje)
   - Dokumentacja kiedy używać `ModelManager` vs `ModelRegistry`
   - Klaryfikacja odpowiedzialności każdej klasy

2. **docs/TECHNICAL_DEBT_ELIMINATION_REPORT.md**
   - Dodać sekcję o refaktoryzacji 076
   - Referencja do tego raportu

3. **README.md** (opcjonalnie)
   - Aktualizacja struktury projektu jeśli dodano nowe moduły

### Nowa dokumentacja
- ✅ **Ten raport:** `docs/_done/076_przeglad_backend_report.md`

## Martwy kod

### Znalezione przypadki

#### 1. venom_core/core/orchestrator.py
- Linia 405-407: `get_token_economist()` - raises `NotImplementedError`
  - **Rekomendacja:** Usunąć lub zaimplementować
  - **Status:** 🔴 Martwy kod

#### 2. venom_core/api/routes/models.py
- Funkcja `_read_ollama_manifest_params()` (linia 233) - używana tylko w jednym miejscu
  - **Rekomendacja:** OK - helper function, nie jest martwy

#### 3. venom_core/core/model_manager.py
- Metoda `_last_ollama_warning` (linia 90) - throttling flag, ale rzadko używany
  - **Rekomendacja:** OK - mechanizm throttlingu, nie jest martwy

### Potencjalny martwy kod do weryfikacji
- `venom_core/main.py` - globalne zmienne (linie 52-100) - niektóre mogą być `None` i nigdy nie inicjalizowane
  - **Wymaga:** Analiza przepływu inicjalizacji w `lifespan()`

## Metryki refaktoryzacji

### Przed refaktorem
| Plik | Linie | Metody/Funkcje | Odpowiedzialności |
|------|-------|----------------|-------------------|
| `orchestrator.py` | 1845 | 47 | 7 (zbyt wiele) |
| `api/routes/models.py` | 1328 | 21 endpoints | 5 (zbyt wiele) |
| `model_registry.py` | 1113 | ~25 | 3 (OK) |
| `model_manager.py` | 944 | ~20 | 3 (duplikacja z registry) |
| `runtime_controller.py` | 734 | ~15 | 2 (OK) |

### Po refaktorze (zrealizowane)
| Plik | Linie | Metody/Funkcje | Odpowiedzialności | Δ |
|------|-------|----------------|-------------------|---|
| `orchestrator.py` | ~1795 | 45 | 6 | -50 linii |
| `api/routes/models.py` | ~1268 | 21 endpoints | 5 | -60 linii |
| **`core/streaming.py`** | 115 | 4 | 1 | **+115 (nowy)** |
| **`api/validators.py`** | 205 | 7 | 1 | **+205 (nowy)** |

**Netto:** -110 linii duplikacji, +2 moduły (lepsza organizacja)

### Po refaktorze (proponowane)
Jeśli zrealizować wszystkie proponowane refaktory:
- `orchestrator.py`: ~1550 linii (-295)
- `api/routes/models.py`: split na 4-5 plików po ~250 linii
- Nowe moduły: +7 plików

**Ocena:** Proponowane refaktory dałyby lepszą organizację, ale wymagają więcej czasu i testów.

## Wnioski

### Co udało się osiągnąć (✅)
1. **Wydzielono StreamingHandler** - orchestrator.py bardziej czytelny (-50 linii)
2. **Wydzielono validators** - usunięto duplikację z routes/models.py (-60 linii)
3. **Zidentyfikowano kluczowe problemy** - god object, mixed concerns, duplikacje
4. **Udokumentowano decyzje** - jasne rekomendacje do przyszłych refaktorów

### Co wymaga dalszej pracy (⚠️)
1. **Meta-learning coordinator** - wydzielić z orchestratora (średni effort)
2. **Podział routes/models.py** - opcjonalny, wysoki effort
3. **Unifikacja model_manager/model_registry** - wymaga decyzji architektonicznej

### Co zostało odroczone (❌)
1. **IO adapters dla model_registry** - wysokie koszty, constraint "nie mnożyć bytów"
2. **Mikroserwisy** - poza zakresem zadania

### Rekomendacje na przyszłość
1. **Monitoruj rozmiar plików** - automatyczny lint rule: max 800 linii na plik
2. **Egzekwuj SRP** - jeden router = jedna domena biznesowa
3. **Testy jednostkowe** - dla nowych modułów (streaming, validators)
4. **Dokumentacja architektoniczna** - jasny podział odpowiedzialności między model_manager i model_registry

## Podsumowanie

Refaktoryzacja skupiła się na **małych, bezpiecznych zmianach** zgodnie z constraint "nie mnożyć bytów". Usunięto ~110 linii duplikacji, poprawiono organizację kodu i zidentyfikowano dalsze możliwości optymalizacji.

**Status:** ✅ **Zrealizowano kluczowe refaktory**, udokumentowano dalsze kroki.

---

**Autor:** Copilot Agent  
**Data:** 2024-12-22  
**Zadanie:** #076 Przegląd techniczny backendu
