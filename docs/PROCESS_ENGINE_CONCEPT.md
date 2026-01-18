# System Procesowy Venom (Process Engine) [v2.0]

> [!NOTE]
> **Status:** Koncepcja planowana dla wersji **Venom 2.0**.
> Dokument ten opisuje wizję "Podejścia Procesowego", w którym użytkownik może samodzielnie budować, układać i zarządzać złożonymi procesami biznesowymi/logicznymi.

## Wizja: Venom jako Silnik Procesów

W wersji 1.0 Venom posiada **wbudowane procesy** (np. cykl Chat => Planner => Coder => Critic), które są sztywne i zarządzane przez system ("Internal/Fixed Processes"). Użytkownik zleca zadania, a Venom dobiera odpowiedni wbudowany proces.

W wersji 2.0 wprowadzamy **Podejście Procesowe (User-Configurable Processes)**, gdzie użytkownik zyskuje kontrolę nad definicją tych przepływów. Przestaje być tylko zlecającym, a staje się architektem logiki, układając klocki w graficznym edytorze.

### Kluczowe Założenia

1.  **Visual Process Builder** - Graficzny interfejs (drag & drop) do układania klocków (Agents, Skills, Logic).
2.  **Determinizm vs AI** - Możliwość łączenia sztywnych reguł (If/Else, Pętle) z elastycznymi węzłami AI (np. "Zdecyduj czy mail jest ważny").
3.  **Wielokrotne Użycie** - Zdefiniowany proces staje się nowym "Skillem" dostępnym dla innych agentów.
4.  **Human-in-the-Loop** - Węzły wymagające zatwierdzenia lub decyzji człowieka przed przejściem dalej.

## Architektura (Planowana)

```mermaid
graph TD
    User[Użytkownik] -->|Buduje| ProcessBuilder[Visual Process Builder]
    ProcessBuilder -->|Generuje| WorkflowDef[Workflow Definition (JSON/YAML)]

    WorkflowDef -->|Wczytuje| ProcessEngine[Process Engine Core]

    ProcessEngine -->|Orkiestruje| Flow[Przepływ]

    subgraph Flow Execution
        Node1[Węzeł: Pobierz Dane] -->|Wynik| Node2{Decyzja AI}
        Node2 -->|Ważne| Node3[Agent: Wyślij Alert]
        Node2 -->|Spam| Node4[Ignoruj]
    end
```

### Komponenty

-   **Process Designer**: UI w Next.js oparty na bibliotece grafowej (np. React Flow).
-   **Execution Engine**: Rozszerzenie obecnego `Orchestrator` o obsługę długotrwałych, stanowych procesów (State Machines).
-   **Standard**: Rozważenie adaptacji BPMN 2.0 lub uproszczonego standardu JSON.

## Przykładowe Procesy Użytkownika

1.  **Onboarding Pracownika**
    *   Krok 1: Wygeneruj umowę (Coder/Writer)
    *   Krok 2: Wyślij email (Tool: SMTP)
    *   Krok 3: Czekaj na podpis (Human Trigger)
    *   Krok 4: Utwórz konta w systemach (Ghost Agent)

2.  **Monitoring Mediów**
    *   Krok 1: Co 1h sprawdź RSS (Researcher)
    *   Krok 2: Jeśli temat = "Venom AI" -> Analizuj sentyment (Analyst)
    *   Krok 3: Jeśli negatywny -> Wyślij SMS do Admina

## Relacja z The Apprentice

Podczas gdy **The Apprentice** uczy się przez *obserwację* (nagrywanie), **Process Engine** pozwala na *świadome projektowanie* i *edycję* logiki. Te systemy będą współpracować: Apprentice może wygenerować surowy proces, który użytkownik następnie dopracuje w Process Builderze.
