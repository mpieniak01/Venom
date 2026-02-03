# ZADANIE: 012_THE_GUARDIAN (Autonomous Testing & Self-Healing Pipeline)

**Priorytet:** Krytyczny (Reliability & Automation)
**Kontekst:** Integracja Warstwy Infrastruktury, Wykonywania i Agentów
**Cel:** Wdrożenie pętli "Test-Diagnose-Fix". Venom ma samodzielnie uruchamiać testy w izolowanym środowisku (Docker), analizować wyniki i poprawiać kod aż do uzyskania "zielonego paska", a następnie commitować zmiany.

---

## 1. Analiza Stanu i Luki (Deep Dive)
Z analizy repozytorium wynika, że mamy wszystkie klocki:
1.  **Izolacja:** `DockerHabitat` (PR 010) pozwala bezpiecznie uruchamiać kod.
2.  **Wersjonowanie:** `GitSkill` (PR 011) pozwala zarządzać kodem.
3.  **Kompetencje:** `CoderAgent` pisze kod, `CriticAgent` go ocenia.

**Brakuje:** Automatyzacji procesu zapewniania jakości. Obecnie Venom napisze kod i powie "gotowe", nawet jeśli kod nie działa. Brakuje mechanizmu, który mówi: *"Sprawdzam. Testy nie przeszły. Naprawiam."*

---

## 2. Zakres Prac (Scope)

### A. Implementacja `TestSkill` (`venom_core/execution/skills/test_skill.py`)
Utwórz nowy skill, który jest wrapperem na narzędzia testowe wewnątrz `DockerHabitat`.
* **Wymagania:**
    - Skill musi używać `DockerHabitat` do uruchamiania komend (nie lokalnie!).
    - Metoda `run_pytest(test_path: str = ".") -> TestReport`:
        - Uruchamia `pytest` w kontenerze.
        - Parsuje wyjście (stdout/stderr) do struktury: `passed: int`, `failed: int`, `failures: List[str]` (szczegóły błędów).
    - Metoda `run_linter() -> LintReport`: Uruchamia `ruff` lub `flake8`.

### B. Agent Strażnik (`venom_core/agents/guardian.py`)
Nowy agent odpowiedzialny za jakość (QA Engineer).
* **Rola:** Nie pisze nowych funkcji. Jego celem jest sprawienie, by testy przechodziły.
* **Narzędzia:** `TestSkill`, `GitSkill`, `FileSkill`.
* **Prompt Systemowy:** *"Jesteś inżynierem QA/DevOps. Twoim zadaniem jest analiza raportów z testów i precyzyjne wskazywanie Coderowi, co musi naprawić. Nie akceptujesz kodu, który nie przechodzi testów."*

### C. Pipeline Samonaprawy (Orchestrator Update)
To jest serce tego PR. Zmodyfikuj `venom_core/core/orchestrator.py` o nową, złożoną procedurę `execute_healing_cycle`.

**Algorytm Pętli Naprawczej (Max 3 iteracje):**
1.  **Phase 1 (Check):** `Guardian` uruchamia testy w Dockerze.
    - Jeśli `exit_code == 0` -> Sukces, koniec.
    - Jeśli Błąd -> Przejdź do fazy 2.
2.  **Phase 2 (Diagnose):** `Guardian` analizuje traceback błędu i tworzy "Ticket Naprawczy" (opis co nie działa i w którym pliku).
3.  **Phase 3 (Fix):** `CoderAgent` otrzymuje Ticket + treść pliku. Generuje poprawkę.
4.  **Phase 4 (Apply):** Kod jest zapisywany (`FileSkill`).
5.  **Loop:** Wróć do Fazy 1.

### D. Integracja z Dashboardem (`web/`)
Rozbuduj `stream.py` i frontend:
* Nowy typ zdarzenia WebSocket: `TEST_RESULT`.
* Wizualizacja w UI: Pasek postępu testów (🔴/🟢).
* Wyświetlanie sformatowanego Tracebacka w przypadku błędu.

---

## 3. Kryteria Akceptacji (Definition of Done)

1.  ✅ **Scenariusz Błędu:**
    * Użytkownik prosi o funkcję, która zawiera celowy błąd (np. dzielenie przez zero).
    * Venom generuje kod -> Uruchamia test -> Wykrywa błąd -> Coder poprawia kod (dodaje obsługę wyjątków) -> Test przechodzi -> Venom zgłasza sukces.
2.  ✅ **Izolacja Testów:**
    * Testy uruchamiają się *wyłącznie* w kontenerze Docker. Host (komputer użytkownika) nie musi mieć zainstalowanego `pytest` w venvie projektu workspace.
3.  ✅ **Raportowanie:**
    * Logi jasno pokazują: *"Próba naprawy 1/3: Wykryto błąd w linii 45. Zlecam poprawkę."*
4.  ✅ **Interwencja:**
    * Jeśli po 3 próbach testy nadal nie przechodzą, Venom przerywa pętlę i zwraca użytkownikowi raport z prośbą o pomoc ręczną (Fail Fast).

---

## 4. Wskazówki Techniczne
* **Parsowanie pytest:** Nie musisz parsować XML. Wystarczy, że `TestSkill` wyłapie sekcję `FAILED` z outputu tekstowego `pytest`. To wystarczy LLM-owi do diagnozy.
* **Stan Kontenera:** Pamiętaj, że `DockerHabitat` musi mieć zainstalowane zależności (`pip install -r requirements.txt`) przed uruchomieniem testów. Dodaj krok `prepare_environment` w Orchestratorze.
* **Timeout:** Testy mogą się zawiesić. Ustaw `timeout` w `DockerHabitat.execute_command` na np. 60 sekund.
