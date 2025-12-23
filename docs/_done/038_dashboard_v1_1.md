# Zadanie: Dashboard v1.1 - Monitoring Systemowy, Status API i Wizualizacja Procesów "Na Żywo"

**Priorytet:** Wysoki
**Cel:** Zapewnienie pełnej obserwowalności (observability) systemu. Użytkownik musi widzieć stan fizyczny maszyny, status połączeń z zewnętrznymi API oraz wizualizację tego, co system robi w danej chwili (np. "Trwa kodowanie").

## 1. Backend: Moduł ServiceHealthMonitor
**Plik:** `venom_core/core/service_monitor.py` (nowy plik)
**Opis:** Serwis monitorujący dostępność usług zewnętrznych i wewnętrznych.
**Wymagania:**
- Zdefiniować rejestr usług (ServiceRegistry) zawierający: `OpenAI`, `GitHub`, `Docker Daemon`, `Local Memory (VectorDB)`.
- Zaimplementować metodę `check_health()` wykonującą lekki ping/request do każdego serwisu.
- Zbierać metryki: `Status` (Online/Offline), `Latency` (ms).
- Wystawić endpoint `GET /api/v1/system/services`.

## 2. Backend: Instrumentacja SkillManager (Real-time Activity)
**Plik:** `venom_core/execution/skill_manager.py`
**Opis:** System musi wiedzieć, kiedy dana umiejętność (Skill) jest aktywnie używana.
**Wymagania:**
- Dodać dekorator lub wrapper na metody wykonywania skilli.
- Przed uruchomieniem skilla wysłać event WebSocket: `SKILL_STARTED` (payload: `{skill: "GitSkill", action: "clone_repo", is_external: true}`).
- Po zakończeniu wysłać: `SKILL_COMPLETED`.
- Dzięki temu frontend będzie wiedział, że "teraz trwa operacja Git".

## 3. Frontend: Widget "Integrations Matrix"
**Plik:** `web/static/js/app.js` (metoda `renderTableWidget`)
**Opis:** Tabela pokazująca stan połączeń z zewnętrznym światem.
**Wymagania:**
- Wyświetlić tabelę z kolumnami: `Usługa`, `Status` (zielona kropka/czerwona), `Opóźnienie`, `Ostatni Test`.
- Dane odświeżane automatycznie co 30-60 sekund.
- Jeśli usługa jest kluczowa (np. LLM) i jest Offline, wyświetlić ostrzeżenie w nagłówku panelu.

## 4. Frontend: Widget "System Pulse" (Rozszerzenie)
**Plik:** `web/static/js/app.js`
**Opis:** Wizualizacja aktualnie wykonywanej pracy (poza wykresem CPU/RAM).
**Wymagania:**
- Dodać sekcję "Active Operations" w Widgecie Systemowym.
- Obsłużyć eventy `SKILL_STARTED` / `SKILL_COMPLETED`.
- Wyświetlać animowane "plakietki" (Badges) w zależności od typu akcji, np.:
  - 🧠 **Thinking** (gdy działa LLM) - pulsujący fioletowy.
  - ⌨️ **Coding** (gdy działa FileSkill/SandBox) - pulsujący zielony.
  - 🌐 **API Call** (gdy działa Browser/Search) - pulsujący niebieski.
  - ⚙️ **System** (Docker/Git) - szary spinner.

## 5. Frontend: Interaktywna Mapa Systemu (Mermaid v1)
**Plik:** `web/static/js/app.js`
**Opis:** Graf architektury reagujący na stan aktywności.
**Wymagania:**
- Wygenerować graf Mermaid z węzłami reprezentującymi: Core, Agenty, Skille, Zewnętrzne API.
- **Dynamiczne stylowanie:** Jeśli przyjdzie event, że `CoderAgent` używa `GitHub API`, frontend powinien (jeśli to możliwe w Mermaid.js API lub poprzez przeładowanie definicji) pogrubić linię łączącą te dwa węzły lub zmienić kolor węzła `GitHub API` na aktywny.
- Jeśli dynamiczna zmiana stylu Mermaid jest zbyt ciężka, wyświetlić "dymek" (tooltip) nad wykresem: "Aktywne połączenie: Coder -> GitHub".

## Kryteria Akceptacji (DoD)
1. Użytkownik widzi listę zintegrowanych API (OpenAI, GitHub, etc.) z ich aktualnym statusem (Online/Offline).
2. Gdy Agent zaczyna pisać kod (używa `write_file`), na dashboardzie pojawia się wyraźna wizualna informacja "Writing Code...".
3. Wykresy zużycia zasobów są uzupełnione o wskaźnik "Network I/O" (aktywność sieciowa).
