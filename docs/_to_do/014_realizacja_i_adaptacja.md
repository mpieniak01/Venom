# ZADANIE: 014_THE_FORGE (Dynamic Tool Generation & Runtime Expansion)

**Priorytet:** Strategiczny (Autonomia 2.0)
**Kontekst:** Warstwa Wykonawcza (Execution) i Adaptacyjna
**Cel:** Umożliwienie Venomowi samodzielnego tworzenia, testowania i ładowania nowych Umiejętności (Skills/Plugins) w czasie rzeczywistym. System ma wykrywać brak narzędzia, napisać je, zweryfikować bezpieczeństwo i natychmiast rozszerzyć swoje możliwości.

---

## 1. Analiza Luki (Gap Analysis)
* **Problem:** Venom posiada statyczny zestaw umiejętności (`FileSkill`, `GitSkill`). W przypadku nietypowych zadań (np. "Pobierz dane z API NBP", "Zresize'uj obrazek", "Wyślij maila"), musi on "improwizować" używając Shella, co jest nietrwałe i podatne na błędy.
* **Rozwiązanie:** Wdrożenie **Kuźni (The Forge)** – mechanizmu, w którym wyspecjalizowany agent (`Toolmaker`) pisze profesjonalne pluginy Semantic Kernel, które są trwale dołączane do arsenału Venoma.

---

## 2. Zakres Prac (Scope)

### A. Menedżer Umiejętności (`venom_core/execution/skill_manager.py`)
*Utwórz nowy moduł.* Odpowiada za zarządzanie cyklem życia wtyczek.
* **Funkcjonalność:**
    - `load_skills_from_dir(path: str)`: Dynamicznie importuje pliki `.py` z katalogu `venom_core/execution/skills/custom/` i rejestruje je w Kernelu.
    - `reload_skill(skill_name: str)`: Przeładowuje moduł (hot-reload) bez restartu aplikacji (użyj `importlib.reload`).
    - `validate_skill(file_path: str)`: Sprawdza statycznie (AST), czy kod jest bezpieczny (np. czy dziedziczy po `BaseSkill`, czy ma dekoratory `@kernel_function`).

### B. Agent Narzędziowiec (`venom_core/agents/toolmaker.py`)
*Utwórz nowego agenta.* To inżynier narzędziowy.
* **Rola:** Pisanie kodu wtyczek (Plugins) zgodnie ze standardem Semantic Kernel.
* **Prompt Systemowy:** *"Jesteś ekspertem tworzenia narzędzi dla AI. Twoim zadaniem jest napisać klasę w Pythonie, która realizuje zadaną funkcję. Kod musi być bezpieczny, otypowany i posiadać docstringi, które zrozumie inne LLM."*
* **Workflow:**
    1. Otrzymuje specyfikację (np. "Potrzebuję narzędzia do pobierania kursów walut").
    2. Generuje plik `currency_skill.py`.
    3. Generuje test jednostkowy `test_currency_skill.py`.

### C. Pipeline Kuźni (Orchestrator Extension)
Rozbuduj logikę `Orchestrator` i `Council`:
1.  **Detekcja:** Jeśli w trakcie planowania `Architect` stwierdzi: *"Brakuje nam narzędzia X"*, kieruje zgłoszenie do `Toolmakera`.
2.  **Produkcja:**
    - `Toolmaker` pisze kod narzędzia i testy.
    - `Guardian` uruchamia testy w `DockerHabitat` (bezpieczna weryfikacja).
    - Jeśli testy przejdą -> `SkillManager` ładuje nowe narzędzie do głównego Kernela.
3.  **Użycie:** `CoderAgent` lub `Researcher` dostają informację: *"Nowe narzędzie X jest dostępne"* i mogą go użyć w tym samym zadaniu.

### D. Katalog Custom Skills (`venom_core/execution/skills/custom/`)
* Utwórz ten katalog i dodaj go do `.gitignore` (chyba że chcemy wersjonować własne narzędzia Venoma – wtedy dodaj `.keep`).
* To tutaj będą lądować "wynalazki" Venoma.

### E. Dashboard Update (`web/`)
* Nowa sekcja: **"Active Skills"**.
* Lista załadowanych pluginów z opisami funkcji (wyciągniętymi z docstringów przez Semantic Kernel).
* Przycisk "Reload All Skills".

---

## 3. Kryteria Akceptacji (DoD)

1.  ✅ **Scenariusz "Weather Tool":**
    * Użytkownik: *"Jaka jest pogoda w Warszawie? Jeśli nie masz narzędzia, stwórz je."*
    * Venom (Toolmaker): Pisze `WeatherSkill` używając np. `open-meteo.com` (nie wymaga klucza).
    * Venom (Guardian): Testuje skill w Dockerze.
    * Venom (Core): Ładuje skill.
    * Venom (Chat): Używa `WeatherSkill.get_current_weather("Warsaw")` i odpowiada: *"Jest 15 stopni"*.
2.  ✅ **Hot-Swapping:**
    * Nowe umiejętności są dostępne natychmiast, bez konieczności restartowania procesu `uvicorn`.
3.  ✅ **Bezpieczeństwo:**
    * Kod nowego narzędzia jest weryfikowany w izolacji (Docker) przed załadowaniem do procesu hosta (Venom Core).
4.  ✅ **Trwałość:**
    * Wygenerowane narzędzie zostaje na dysku i jest dostępne przy kolejnym uruchomieniu Venoma.

---

## 4. Wskazówki Techniczne
* **Python Dynamic Import:** Użyj `importlib.util.spec_from_file_location` do ładowania modułów ze ścieżki.
* **Semantic Kernel Plugin Structure:**
  ```python
  from semantic_kernel.functions import kernel_function

  class WeatherSkill:
      @kernel_function(description="Pobiera pogodę dla miasta")
      def get_weather(self, city: str) -> str:
          # ... implementation


* **Kernel Registry:** Pamiętaj, że po załadowaniu pluginu musisz zaktualizować definicje narzędzi przekazywane do agentów w AutoGen (register_function / update_tool_definitions), , aby "Rada" wiedziała o nowym narzędziu.
