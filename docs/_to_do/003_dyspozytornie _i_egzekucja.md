# ZADANIE: 003_MOTOR_CORTEX (Dyspozytornia i Egzekucja)

## 1. Kontekst
Venom potrafi już klasyfikować intencje (`CODE_GENERATION`, `GENERAL_CHAT`, `KNOWLEDGE_SEARCH`).
Teraz musimy zaimplementować logikę, która faktycznie wykonuje te zadania.
W tym PR stworzymy mechanizm **Dyspozytora (Dispatcher)**, który na podstawie intencji wybierze odpowiednią umiejętność lub agenta i zwróci rzeczywisty wynik pracy (kod lub odpowiedź).

## 2. Zakres prac

### A. Interfejs Agenta (`venom_core/agents/base.py`)
*Utwórz nowy plik.* Zdefiniuj abstrakcyjną klasę bazową dla agentów Venoma, aby zachować spójność:
- Klasa `BaseAgent`:
  - Metoda abstrakcyjna `async def process(self, input_text: str) -> str`.
  - Inicjalizacja przyjmująca `Kernel` (z Semantic Kernel).

### B. Implementacja Specjalistów (`venom_core/agents/`)
Zaimplementuj logikę w istniejących (pustych) plikach:

1.  **`venom_core/agents/coder.py`**:
    - Klasa `CoderAgent(BaseAgent)`.
    - Logika: Używa Semantic Kernel z promptem systemowym: *"Jesteś ekspertem programowania (Senior Developer). Generuj czysty, udokumentowany kod w odpowiedzi na żądanie..."*.
    - Zwraca wygenerowany kod w bloku markdown.

2.  **`venom_core/agents/chat.py`** (Utwórz nowy lub użyj `writer.py` jako bazę):
    - Klasa `ChatAgent(BaseAgent)`.
    - Logika: Odpowiada na pytania ogólne w sposób pomocny i zwięzły.

### C. Dyspozytor Zadań (`venom_core/core/dispatcher.py`)
Zaimplementuj klasę `TaskDispatcher`:
- Inicjalizuje mapę agentów (Code -> CoderAgent, Chat -> ChatAgent).
- Metoda `async def dispatch(self, intent: str, content: str) -> str`:
  - Jeśli `CODE_GENERATION` -> woła `CoderAgent`.
  - Jeśli `GENERAL_CHAT` -> woła `ChatAgent`.
  - Jeśli `KNOWLEDGE_SEARCH` -> na razie woła `ChatAgent` (z adnotacją TODO: podpiąć GraphRAG w przyszłości).
  - Obsługuje błędy (np. nieznana intencja).

### D. Integracja z Orchestratorem (`venom_core/core/orchestrator.py`)
Zaktualizuj metodę `_run_task`:
1. Po wykryciu intencji przez `IntentManager`, przekaż ją do `TaskDispatcher`.
2. Wynik z dispatchera zapisz w `task.result`.
3. Zaktualizuj logi o informację, który agent przejął zadanie.

---

## 3. Kryteria Akceptacji (DoD)
1.  **Rzeczywista Praca:**
    - Zadanie *"Napisz funkcję Hello World w Python"* zwraca w wyniku: `def hello_world(): print("Hello World")`.
    - Zadanie *"Opowiedz kawał"* zwraca treść żartu.
2.  **Modularność:** Agenci są osobnymi klasami, a Orchestrator tylko nimi zarządza (nie zawiera logiki promptów).
3.  **Local-First:** Wszystko nadal działa na lokalnym modelu (Ollama/Phi-3) skonfigurowanym w `KernelBuilder`.
4.  **Testy:**
    - Unit testy dla `CoderAgent` i `TaskDispatcher` (z mockami Kernela).
    - Test integracyjny, który sprawdza, czy `Orchestrator` zwraca kod, a nie tylko nazwę intencji.

## 4. Wskazówki Techniczne
- Wykorzystaj `KernelBuilder` z poprzedniego zadania do wstrzykiwania `Kernel` do agentów.
- Pamiętaj, że lokalne modele (szczególnie mniejsze jak Phi-3) wymagają bardzo precyzyjnych promptów systemowych, aby nie "gadały za dużo", tylko generowały kod.
