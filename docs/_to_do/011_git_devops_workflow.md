# ZADANIE: 011_THE_CONTRIBUTOR (Git Integration & DevOps Workflow)

**Kontekst:** Warstwa Wykonawcza (Execution) i Agentów
**Cel:** Przekształcenie Venoma w pełnoprawnego kontrybutora, który potrafi zarządzać repozytorium Git, pracować na branchach, tworzyć semantyczne commity i integrować zmiany.

---

## 1. Analiza Luki (Gap Analysis)
Z analizy kodu wynika, że:
1.  Plik `venom_core/execution/skills/git_skill.py` zawiera tylko docstring i jest pusty.
2.  Wenom operuje w `./workspace` w sposób destrukcyjny (nadpisuje pliki bez historii).
3.  Brak agenta odpowiedzialnego za cykl życia kodu (Release/Merge).

Celem tego PR jest wdrożenie roli **Integratora** i umiejętności **Git**, co pozwoli na workflow: *Branch -> Code -> Test -> Commit*.

---

## 2. Zakres Prac (Scope)

### A. Implementacja `GitSkill` (`venom_core/execution/skills/git_skill.py`)
Zaimplementuj klasę `GitSkill` używając biblioteki `GitPython` (dodaj do `requirements.txt`).
* **Lokalizacja:** Skill musi działać na **Hoście** (podobnie jak Orchestrator), aby korzystać z kluczy SSH użytkownika (nie w Dockerze).
* **Metody (@kernel_function):**
    - `init_repo(url: str = None)`: Inicjalizuje lub klonuje repozytorium w `WORKSPACE_ROOT`.
    - `checkout(branch_name: str, create_new: bool = False)`: Przełącza gałąź.
    - `get_status() -> str`: Zwraca wynik `git status` (zmodyfikowane pliki).
    - `get_diff() -> str`: Zwraca `git diff` (niezbędne dla LLM do zrozumienia, co się zmieniło).
    - `add_files(files: List[str] = ["."])`: Stage'uje pliki.
    - `commit(message: str)`: Tworzy commit.
    - `push(remote: str = "origin", branch: str = None)`: Wypycha zmiany.
    - `get_last_commit_log(n: int = 5)`: Czyta historię.

### B. Agent Integrator (`venom_core/agents/integrator.py`)
*Utwórz nowy plik.* To specjalista DevOps.
* **Rola:** Zarządzanie wersjonowaniem i higieną repozytorium.
* **Narzędzia:** Wyłączny dostęp do `GitSkill`.
* **Kluczowa Funkcjonalność - `generate_commit_message`:**
    1. Integrator pobiera `get_diff()`.
    2. Używa LLM do analizy zmian.
    3. Generuje wiadomość zgodną ze standardem **Conventional Commits** (np. `feat(core): add git skill implementation` lub `fix(docker): resolve permission denied in habitat`).

### C. Workflow "Feature Branch" w Orchestratorze
Zaktualizuj `venom_core/core/orchestrator.py` i `dispatcher.py`.
* Dodaj obsługę intencji `VERSION_CONTROL`.
* **Scenariusz Automatyczny (Pipeline):**
    1.  **Start:** Użytkownik zleca: "Dodaj obsługę plików CSV".
    2.  **Plan:** Architekt decyduje o stworzeniu nowego brancha.
    3.  **Action 1 (Integrator):** `git checkout -b feat/csv-support`.
    4.  **Action 2 (Coder):** Pisze kod i testy w Dockerze (Habitat).
    5.  **Action 3 (Critic):** Weryfikuje poprawność (Code Review).
    6.  **Action 4 (Integrator):** Sprawdza `git status`. Jeśli są zmiany -> analizuje diff -> robi commit -> robi push.

### D. UI / Dashboard (`web/`)
* Dodaj sekcję "Repository Status" w nagłówku dashboardu:
    - Aktualny Branch (np. 🌿 `main`).
    - Status (np. 🔴 `2 modified files` / 🟢 `Clean`).
    - Przyciski szybkiej akcji: `Sync`, `Undo Changes`.

---

## 3. Kryteria Akceptacji (Definition of Done)

1.  ✅ **Zarządzanie Branchami:**
    * Polecenie *"Pracuj na nowej gałęzi o nazwie refactor-auth"* powoduje faktyczne przełączenie brancha w systemie plików.
2.  ✅ **Semantyczne Commity:**
    * Po modyfikacji pliku, Venom nie pyta "jak nazwać commit?", tylko sam analizuje zmiany i tworzy opis typu `refactor(auth): simplify login logic`.
3.  ✅ **Integracja z Habitatem:**
    * Pliki stworzone przez `DockerHabitat` (mogą mieć właściciela `root`) są poprawnie commitowane przez `GitSkill` na hoście (może wymagać `chown` lub konfiguracji safe directory).
4.  ✅ **Bezpieczeństwo:**
    * Venom odmawia wykonania `git push --force` chyba że zostanie wyraźnie nadpisany w Policy Engine.

---

## 4. Wskazówki Techniczne
* **GitPython:** Jest potężny, ale do operacji `push`/`pull` korzystających z SSH lepiej czasem użyć wrappera na komendy systemowe, aby uniknąć problemów z konfiguracją kluczy wewnątrz biblioteki Python.
* **Konflikty:** Na tym etapie, w przypadku konfliktu merge'a (`git pull` zwraca błąd), Integrator powinien zgłosić **krytyczny wyjątek** i poprosić człowieka o pomoc, zamiast próbować rozwiązywać to samemu (ryzyko utraty kodu).
* **Docker Permissions:** Pamiętaj, że pliki tworzone w kontenerze Docker (Habitat) mogą należeć do roota. GitSkill działający na hoście (użytkownik) musi mieć do nich prawa. W `DockerHabitat` (PR 010) upewnij się, że użytkownik w kontenerze ma ten sam UID co host, lub wykonuj `chown` po zakończeniu pracy Codera.
