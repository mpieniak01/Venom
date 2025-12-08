# ZADANIE: 030_THE_STRATEGIST

**(Autonomous Time Estimation, Task Complexity & Operational Intelligence)**

**Priorytet:** Strategiczny (Planning & Cognitive Load Management)
**Kontekst:** Warstwa Operacyjna (Operational Layer)

---

## 🎯 Cel

Wyposażyć Venoma w zdolność **realistycznego szacowania czasu, złożoności i kosztów operacyjnych** zadań technicznych.
System ma potrafić:

* ocenić, które zadania są szybkie, które długie,
* wykryć zbyt duże zadania (dzielić je na mniejsze),
* prognozować obciążenie agentów,
* doradzać najlepszą sekwencję prac,
* przerywać lub zmieniać strategię, gdy zadanie "puchnie".

**Bez warstwy finansowej – tylko inteligentne zarządzanie pracą, czasem i złożonością.**

---

## 🧩 1. Kontekst Operacyjny

**Problem:**
Venom jest świetny w kodowaniu, lecz:

* nie przewiduje, ile coś potrwa,
* nie zna złożoności zadania,
* czasem wpada w tunel i robi coś za długo,
* nie dzieli zadań na optymalne moduły,
* nie ocenia, czy jego pomysł jest realistyczny.

**Rozwiązanie:**
Dodanie warstwy **Operational Intelligence**, która:

1. Rozumie rozmiar zadania.
2. Prognozuje czas i złożoność.
3. Sugeruje najlepszą kolejność działań.
4. Ostrzega przed "scope creep".
5. Wprowadza *Safety Cutoff* przy zadaniach rosnących poza kontrolę.

---

## 🧩 2. Zakres Prac (Scope)

### A. Work Ledger (`venom_core/ops/work_ledger.py`)

Zbiór metadanych o zadaniach Venoma.

**Funkcje:**

* `log_task(name, estimated_minutes, complexity)`
* `update_progress(task_id, percent)`
* `predict_overrun(task_id)` – przewidywanie przekroczenia czasu
* `summaries()` – raport: czas vs złożoność vs efekt

**Zastosowanie:**
Nie koszt finansowy, lecz **koszt poznawczy, operacyjny i czasowy**.

---

### B. Skill: ComplexitySkill (`venom_core/execution/skills/complexity_skill.py`)

Agent oceniający zadania.

**Metody (@kernel_function):**

* `estimate_time(description: str)`
* `estimate_complexity(description: str)`
* `suggest_subtasks(description: str)`
* `flag_risks(description: str)`

---

### C. Agent Strategist (`venom_core/agents/strategist.py`)

Zastępuje rolę CFO → pełni rolę planisty i analityka złożoności.

**Zadania:**

* ocena każdego PR / Task przed realizacją,
* sprawdzanie czy zadanie nie jest zbyt duże,
* dzielenie zadań na sprinty,
* proponowanie kolejności działań,
* ostrzeganie gdy zadanie eksploduje złożonością.

**Uprawnienia:**
Może wstrzymać działanie agentów, jeśli:

* czas przekracza estymację,
* złożoność rośnie nieliniowo,
* pojawiają się ryzyka jakości.

---

### D. SaaS Boilerplate (część operacyjna)

Rozbudowa `ComposeSkill` i `CoderAgent`:

* generowanie metadanych czasu i obciążenia obliczeniowego,
* tworzenie *task cards* (karty zadań, jak w Jira),
* automatyczny plan sprintu dla nowego projektu.

---

### E. Dashboard: "The Operations Room"

Wyświetla:

* listę zadań + estymacje,
* poziom złożoności projektów,
* wykres „time spent vs expected”,
* proponowaną kolejność działań,
* alerty Strategista.

---

## 🧩 3. Kryteria Akceptacji (DoD)

1. Strategist dzieli duże zadanie na 3 mniejsze PR-y.
2. Venom przewiduje, że generowanie wielu komponentów zajmie zbyt długo → proponuje iterację.
3. System ostrzega: *"To zadanie ma wysokie ryzyko rozszerzania zakresu – sugeruję prototyp najpierw."*
4. Dashboard pokazuje wykres „Plan vs Rzeczywistość”.
5. Strategist wprowadza cutoff, gdy zadanie rośnie poza kontrolę.

---

## 🧩 4. Wskazówki Techniczne

* używaj tokenów/CPU **wyłącznie** jako miary obciążenia, nie kosztu,
* złożoność licz heurystycznie (ilość plików, modułów, integracji),
* Strategist powinien działać **przed** kodowaniem i **po** każdej iteracji,
* Dashboard może używać Plotly/Chart.js.

---

## F. Kontrola Kosztów Zewnętrznych (API Usage Awareness)

Strategist musi rozumieć, kiedy zadania **angażują zewnętrzne API**, które mogą:

* mieć limit szybkości (rate limits),
* generować opóźnienia,
* zużywać zasoby,
* wymagać świadomego zarządzania.

### Dlaczego?

Nawet jeśli nie liczymy finansów, to **zewnętrzne API są zasobem operacyjnym** i należy nimi zarządzać tak, jak każdą inną częścią systemu.

### Funkcje do dodania:

* `record_api_usage(provider: str, tokens: int, ops: int)` – zapis wykorzystania API.
* `predict_api_pressure()` – czy kolejne zadania spowodują przeciążenie API.
* `suggest_local_fallback()` – np. *"Generowanie obrazu w OpenAI jest intensywne – proponuję użyć lokalnego Stable Diffusion."*
* `enforce_api_limits(max_daily_calls)` – automatyczne odcięcie zadań po przekroczeniu limitu.

### Przykłady decyzji:

* *„Wygenerowaliśmy dziś 40 obrazów w OpenAI – sugeruję przełączenie na lokalny backend.”*
* *„Analiza dużych PDF-ów w LLM jest obciążająca – podziel plik na mniejsze części.”*
