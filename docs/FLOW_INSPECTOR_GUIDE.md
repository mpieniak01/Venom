# Flow Inspector - Przewodnik Użytkownika

## 🔀 Co to jest Flow Inspector?

Flow Inspector to narzędzie do wizualizacji procesów decyzyjnych systemu Venom w czasie rzeczywistym. Pozwala zrozumieć, dlaczego system podjął daną decyzję (np. wybrał konkretnego agenta, wszedł w tryb The Council).

## ✨ Główne Funkcje

- **Dynamiczna wizualizacja** - diagramy Mermaid.js Sequence Diagram pokazujące przepływ zadania
- **Decision Gates** - wyróżnione bramki decyzyjne pokazujące kluczowe punkty w przepływie
- **Real-time updates** - automatyczne odświeżanie dla zadań w trakcie wykonywania
- **Historia zadań** - przeglądanie wszystkich wykonanych zadań z filtrami

## 🚀 Jak używać?

### 1. Dostęp do Flow Inspector

Przejdź do Flow Inspector klikając na link **🔀 Flow Inspector** w nawigacji lub bezpośrednio pod adresem:

```
http://localhost:8000/flow-inspector
```

### 2. Wybór zadania do analizy

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

Jeśli zadanie jest nadal w trakcie (PROCESSING), Flow Inspector automatycznie odświeża dane co 3 sekundy.

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

1. **Filtrowanie** - użyj przycisku "🔄 Odśwież" aby załadować najnowsze zadania
2. **Live monitoring** - pozostaw otwartą stronę Flow Inspector podczas wykonywania zadania, aby zobaczyć przepływ w czasie rzeczywistym
3. **Debugging** - Decision Gates pomagają zrozumieć, dlaczego system wybrał konkretną ścieżkę wykonania
4. **Historia** - wszystkie zadania są zapisywane, możesz wrócić do analizy starszych zadań

## 🐛 Troubleshooting

### Brak zadań na liście
- Upewnij się, że RequestTracer jest włączony w konfiguracji
- Wykonaj przynajmniej jedno zadanie przez system

### Diagram nie renderuje się
- Sprawdź konsolę JavaScript w przeglądarce
- Upewnij się, że Mermaid.js jest załadowany (powinien być w base.html)

### Brak Decision Gates w diagramie
- Upewnij się, że używasz najnowszej wersji Orchestrator z wzbogaconym logowaniem
- Decision Gates są dodawane tylko dla zadań wykonanych po wdrożeniu tej funkcji

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

**Wersja:** 1.0  
**Data:** 2024-12-10  
**Autor:** Venom Team
