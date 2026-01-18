# Flow Inspector - Przewodnik Użytkownika

## 🔀 Co to jest Flow Inspector?

Flow Inspector to narzędzie do wizualizacji procesów decyzyjnych systemu Venom w czasie rzeczywistym. Pozwala zrozumieć, dlaczego system podjął daną decyzję (np. wybrał konkretnego agenta, wszedł w tryb The Council).

### Dostępne wersje:

1. **Flow Inspector (legacy)** (`/flow-inspector`) - podstawowa wersja w legacy UI (FastAPI).
2. **Inspector (web-next)** (`/inspector`) - docelowa wersja w Next.js:
   - React + Mermaid
   - zoom/pan na diagramie (`react-zoom-pan-pinch`)
   - panel telemetryczny i filtr kroków
   - pełne dane błędu (`error_code`, `error_details`)

## ✨ Główne Funkcje

- **Dynamiczna wizualizacja** - diagramy Mermaid.js Sequence Diagram pokazujące przepływ zadania
- **Decision Gates** - wyróżnione bramki decyzyjne pokazujące kluczowe punkty w przepływie
- **Real-time updates** - automatyczne odświeżanie dla zadań w trakcie wykonywania
- **Historia zadań** - przeglądanie wszystkich wykonanych zadań z filtrami

## 🚀 Jak używać?

### 1. Dostęp do Flow Inspector

Przejdź do Flow Inspector klikając na link w nawigacji:

- **🔀 Flow Inspector (legacy)**: `http://localhost:8000/flow-inspector`
- **🔍 Inspector (web-next)**: `http://localhost:3000/inspector`

### 2. Interactive Inspector - Zaawansowane funkcje

#### Układ interfejsu:

1. **Sidebar (lewy panel)** - Lista śladów (ostatnie 50 requestów)
   - Filtry statusów przez badge i listę historii
   - Przyciski odświeżania

2. **Diagram Panel (górny panel główny)** - Mermaid + zoom/pan
   - Kontrolki: zoom in/out, reset
   - Sanitizacja treści przed renderem

3. **Telemetry Panel (dolny panel główny)** - Kontekst i błędy
   - `error_code`, `error_details`, etap i retryable
   - Lista kroków z filtrem tekstowym
   - Checkbox „Tylko kontrakty” (execution_contract_violation)

#### Interaktywność:

✅ **Zoom & Pan:**
- Kółko myszy - zoom in/out
- Przeciąganie myszą - przesuwanie diagramu
- Przyciski 🔍+/🔍-/↺ - kontrolki zoom

✅ **Lista kroków + panel telemetryczny:**
- Kliknij krok w liście, by zobaczyć szczegóły i JSON
- Filtruj kroki po treści lub tylko kontrakty wykonania

✅ **Decision Gates:**
- Wyróżnione żółtym tłem na diagramie
- Emoji 🔀 w opisie
- Dodatkowe informacje w panelu szczegółów

### 3. Wybór zadania do analizy (obie wersje)

W sekcji "📋 Wybierz zadanie do analizy" zobaczysz listę ostatnich zadań:

- **Zielona ramka** - zadanie ukończone (COMPLETED)
- **Czerwona ramka** - zadanie zakończone błędem (FAILED)
- **Pomarańczowa ramka** - zadanie w trakcie (PROCESSING)
- **Niebieska ramka** - zadanie oczekujące (PENDING)

Kliknij na zadanie, które chcesz przeanalizować.

### 3. Analiza diagramu przepływu

Po wybraniu zadania zobaczysz:

#### 📊 Diagram Mermaid

Interaktywny diagram sekwencji pokazujący:
- **Uczestników** - komponenty systemu (User, Orchestrator, Agenci)
- **Strzałki** - przepływ komunikacji między komponentami
- **Notatki żółte (Decision Gates)** - kluczowe punkty decyzyjne oznaczone emoji:
  - 🔀 Routing decision
  - 🏛️ Council Mode
  - 💻 Code Review Loop
  - 🚀 Campaign Mode
  - itp.

#### 🔍 Szczegóły kroków

Lista wszystkich kroków z:
- **Component** - nazwa komponentu
- **Action** - wykonana akcja
- **Timestamp** - czas wykonania
- **Details** - dodatkowe szczegóły

Decision Gates są wyróżnione **pomarańczowym tłem** i mają badge **🔀 Decision Gate**.

### 4. Auto-refresh

**Flow Inspector (podstawowy):** Jeśli zadanie jest nadal w trakcie (PROCESSING), automatycznie odświeża dane co 3 sekundy.

**Interactive Inspector:** Wymaga ręcznego odświeżenia przyciskiem.

## 🔒 Bezpieczeństwo

Inspector w web-next:
- Sanityzuje treści (komponenty, akcje, szczegóły) przed renderem Mermaid.
- Renderuje diagramy w kontrolowanym komponencie (bez zewnętrznych CDN).
- Obsługuje fallback diagramu przy błędach renderu.

## 🎯 Przykłady użycia

### Analiza wyboru agenta

```
User -> Orchestrator: "Napisz funkcję sortującą"
Orchestrator -> IntentManager: classify_intent
Note over DecisionGate: 🔀 Route to Code Generation
Orchestrator -> CoderAgent: process_task
CoderAgent -> User: ✅ Task completed
```

**Decision Gate** pokazuje, że system rozpoznał intencję CODE_GENERATION i zdecydował się na użycie CoderAgent.

### Analiza trybu Council

```
User -> Orchestrator: "Stwórz złożoną aplikację webową"
Orchestrator -> IntentManager: classify_intent
Note over DecisionGate: 🏛️ Complex task -> Council Mode
Orchestrator -> CouncilFlow: run_discussion
CouncilFlow -> User: ✅ Task completed
```

**Decision Gate** pokazuje, że zadanie było wystarczająco złożone, aby system aktywował tryb Council.

### Analiza błędu

```
User -> Orchestrator: "Zadanie z błędem"
Orchestrator -> Agent: process_task
Agent --x User: ❌ Task failed (Connection timeout)
```

Przerywana linia `--x` wskazuje na błąd w przepływie.

## 🔧 API Endpoint

Flow Inspector wykorzystuje endpoint REST API:

```
GET /api/v1/flow/{task_id}
```

**Response:**
```json
{
  "request_id": "uuid",
  "prompt": "Treść zadania",
  "status": "COMPLETED",
  "created_at": "2024-12-10T13:00:00",
  "finished_at": "2024-12-10T13:00:05",
  "duration_seconds": 5.0,
  "steps": [
    {
      "component": "Orchestrator",
      "action": "classify_intent",
      "timestamp": "2024-12-10T13:00:01",
      "status": "ok",
      "details": "Intent: CODE_GENERATION",
      "is_decision_gate": false
    },
    {
      "component": "DecisionGate",
      "action": "select_code_review_loop",
      "timestamp": "2024-12-10T13:00:02",
      "status": "ok",
      "details": "💻 Routing to Coder-Critic Review Loop",
      "is_decision_gate": true
    }
  ],
  "mermaid_diagram": "sequenceDiagram\n..."
}
```

## 📝 Decision Gates - Typy

System rozpoznaje następujące typy Decision Gates:

1. **route_help** - routing do systemu pomocy (HELP_REQUEST)
2. **route_campaign** - routing do trybu kampanii (START_CAMPAIGN)
3. **select_council_mode** - wybór trybu Council dla złożonych zadań
4. **select_code_review_loop** - wybór pętli Coder-Critic dla generowania kodu
5. **route_to_architect** - routing do Architekta dla złożonego planowania
6. **route_to_agent** - standardowy routing do konkretnego agenta

## 💡 Tips & Tricks

### Flow Inspector (podstawowy):
1. **Filtrowanie** - użyj przycisku "🔄 Odśwież" aby załadować najnowsze zadania
2. **Live monitoring** - pozostaw otwartą stronę podczas wykonywania zadania

### Interactive Inspector:
1. **Nawigacja** - użyj kółka myszy i przeciągania dla dużych diagramów
2. **Eksploracja** - klikaj elementy aby zobaczyć szczegóły JSON
3. **Reset widoku** - przycisk ↺ przywraca początkowe ustawienie zoom
4. **Debugging** - panel szczegółów pokazuje pełne dane każdego kroku

### Obie wersje:
1. **Debugging** - Decision Gates pomagają zrozumieć, dlaczego system wybrał konkretną ścieżkę wykonania
2. **Historia** - wszystkie zadania są zapisywane, możesz wrócić do analizy starszych zadań

## 🐛 Troubleshooting

### Brak zadań na liście
- Upewnij się, że RequestTracer jest włączony w konfiguracji
- Wykonaj przynajmniej jedno zadanie przez system

### Diagram nie renderuje się
- Sprawdź konsolę JavaScript w przeglądarce (F12)
- Upewnij się, że Mermaid.js jest załadowany (powinien być w base.html)
- **Interactive Inspector:** Sprawdź czy biblioteki CDN są dostępne (Alpine.js, svg-pan-zoom)

### Brak Decision Gates w diagramie
- Upewnij się, że używasz najnowszej wersji Orchestrator z wzbogaconym logowaniem
- Decision Gates są dodawane tylko dla zadań wykonanych po wdrożeniu tej funkcji

### Interactive Inspector - brak interaktywności
- Sprawdź konsolę JavaScript - powinny być komunikaty o inicjalizacji
- Sprawdź połączenie internetowe (CDN libraries)
- Odśwież stronę (Ctrl+F5)

### Błędy bezpieczeństwa CSP (Content Security Policy)
- Interactive Inspector używa CDN - upewnij się, że CSP pozwala na `cdn.jsdelivr.net`

## 🔗 Powiązane dokumenty

- [REQUEST_TRACING_GUIDE.md](REQUEST_TRACING_GUIDE.md) - szczegóły o systemie śledzenia requestów
- [THE_COUNCIL.md](THE_COUNCIL.md) - dokumentacja trybu Council
- [INTENT_RECOGNITION.md](INTENT_RECOGNITION.md) - klasyfikacja intencji

## 📊 Przykładowe scenariusze

### Scenariusz 1: Prosty request

```
Użytkownik: "Hello!"
Intent: GENERAL_CHAT
Decision: Route to AssistantAgent
Rezultat: Odpowiedź od AssistantAgent
```

### Scenariusz 2: Złożony projekt

```
Użytkownik: "Stwórz aplikację TODO z React i FastAPI"
Intent: COMPLEX_PLANNING
Decision: Check complexity -> Council Mode activated
Rezultat: Dyskusja w Council -> Architect planuje -> Coder implementuje
```

### Scenariusz 3: Generowanie kodu z review

```
Użytkownik: "Napisz funkcję fibonacci"
Intent: CODE_GENERATION
Decision: Code Review Loop
Rezultat: Coder generuje -> Critic sprawdza -> iteracje -> akceptacja
```

---

## 📚 Technologie

### Flow Inspector (podstawowy):
- Vanilla JavaScript
- Mermaid.js (sequence diagrams)
- Fetch API

### Interactive Inspector:
- **Alpine.js 3.13.3** - reactive state management
- **svg-pan-zoom 3.6.1** - interactive diagram navigation
- **Mermaid.js 10.6.1** - sequence diagram rendering
- **Pure CSS3** - flexbox layout, no build tools required

---

**Wersja:** 1.0
**Data:** 2024-12-10
**Autor:** Venom Team
