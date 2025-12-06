# ZADANIE: 004_THE_HANDS (File I/O, Sandbox & Librarian)

## 1. Kontekst Biznesowy
Obecnie Venom potrafi wygenerować kod, ale "ginie" on w logach czatu. System jest teoretykiem.
Celem tego zadania jest przekształcenie go w inżyniera, który potrafi:
1. Zapisać wygenerowany kod w konkretnym pliku w katalogu `./workspace`.
2. Odczytać istniejący kod, aby go zrefaktorować.
3. Zrozumieć strukturę projektu, w którym pracuje.

---

## 2. Zakres Prac (Scope)

### A. Skill Plikowy (`venom_core/execution/skills/file_skill.py`)
Zaimplementuj klasę `FileSkill` jako plugin Semantic Kernel.
* **Metody (udekorowane `@kernel_function`):**
  - `write_file(file_path: str, content: str)`: Tworzy/nadpisuje plik.
  - `read_file(file_path: str)`: Zwraca treść pliku.
  - `list_files(directory: str)`: Zwraca listę plików (rekurencyjnie lub płasko).
  - `file_exists(file_path: str)`: Zwraca `True`/`False`.
* **Bezpieczeństwo (Sandbox):**
  - Wszystkie operacje muszą być ograniczone do `SETTINGS.WORKSPACE_ROOT`.
  - Każda próba wyjścia poza katalog (np. `../`, `/etc/`) musi rzucać `SecurityError` lub `ValueError`.

### B. Agent Bibliotekarz (`venom_core/agents/librarian.py`)
Zaimplementuj klasę `LibrarianAgent(BaseAgent)`.
* **Rola:** Zarządca wiedzy o strukturze projektu.
* **Narzędzia:** Posiada dostęp do `FileSkill`.
* **Prompt:** Skonstruuj prompt systemowy, który instruuje agenta, że jego zadaniem jest nawigacja po plikach, sprawdzanie ich istnienia i opisywanie struktury katalogów.

### C. Aktualizacja CoderAgent (`venom_core/agents/coder.py`)
Zmodernizuj agenta programistę.
* **Rejestracja Narzędzi:** Zarejestruj `FileSkill` w kernelu agenta.
* **Prompt Systemowy:** Dodaj instrukcję: *"Masz dostęp do systemu plików. Gdy użytkownik prosi o napisanie kodu do pliku, UŻYJ funkcji `write_file`. Nie tylko wypisuj kod w markdownie."*
* **Logika (Tool Calling):**
  - Skonfiguruj `OpenAIChatCompletion` (lub odpowiednik) z włączonym `auto_invoke_kernel_functions=True` (jeśli model to wspiera).
  - *Fallback:* Jeśli model nie wspiera native functions, zaimplementuj prostą logikę w `process`, która parsuje odpowiedź i wywołuje `write_file` jeśli wykryje blok kodu i ścieżkę.

### D. Routing w Dispatcherze (`venom_core/core/dispatcher.py`)
* Zaktualizuj mapę intencji.
* **Nowa Intencja:** `FILE_OPERATION` (lub obsługa w ramach `KNOWLEDGE_SEARCH` / `CODE_GENERATION`).
* Skieruj pytania o strukturę ("jakie mam pliki?") do `LibrarianAgent`.

### E. Konfiguracja (`venom_core/config.py`)
* Dodaj `WORKSPACE_ROOT` (domyślnie `./workspace`).
* Upewnij się, że katalog workspace jest tworzony przy starcie aplikacji (`venom_core/main.py` -> `lifespan`).

---

## 3. Kryteria Akceptacji (Definition of Done)

1.  ✅ **Zapis Fizyczny:**
    * Zadanie *"Stwórz plik test.py z funkcją print('Hello')"* powoduje utworzenie pliku na dysku.
2.  ✅ **Odczyt Fizyczny:**
    * Zadanie *"Co jest w pliku test.py?"* zwraca poprawną treść.
3.  ✅ **Bezpieczeństwo:**
    * Próba zapisu do `../../system.ini` jest blokowana i rzuca wyjątek.
4.  ✅ **Świadomość Struktury:**
    * Pytanie *"Pokaż strukturę plików"* zwraca listę wygenerowaną przez `LibrarianAgent`.
5.  ✅ **Testy:**
    * Testy jednostkowe dla `FileSkill` (szczególnie weryfikacja path traversal).
    * Test integracyjny sprawdzający zapis i odczyt pliku przez pełny pipeline Orchestratora.

---

## 4. Wskazówki Techniczne
* Do bezpiecznego zarządzania ścieżkami użyj biblioteki `pathlib`:
  ```python
  # Przykład weryfikacji
  safe_path = (base_path / user_path).resolve()
  if not str(safe_path).startswith(str(base_path.resolve())):
      raise SecurityError("Access denied")
