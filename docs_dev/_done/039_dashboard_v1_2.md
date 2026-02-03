# Zadanie: Dashboard v1.2 - Historia Żądań i Śledzenie Przepływu (Request Tracing)

**Priorytet:** Wysoki
**Cel:** Umożliwienie użytkownikowi śledzenia drogi jego polecenia przez system. Od momentu wysłania, przez decyzje Orchestratora, działania Agentów, aż po odpowiedź finalną.

## 1. Backend: Moduł RequestTracer
**Plik:** `venom_core/core/tracer.py` (nowy plik)
**Opis:** Centralny rejestr zdarzeń powiązanych z konkretnym ID zadania (`trace_id`).
**Wymagania:**
- Klasa `RequestTracer` powinna przechowywać mapę śladów (traces).
- **Struktura śladu:**
  - `request_id` (UUID)
  - `status` (PENDING, PROCESSING, COMPLETED, FAILED, LOST)
  - `created_at`, `finished_at`
  - `steps`: Lista kroków (np. `[{component: "Router", action: "dispatch", timestamp: "...", status: "ok"}]`).
- Metoda `add_step(request_id, component, details)` - wywoływana przez Agenty i Skille.
- Mechanizm "Watchdog": Jeśli status jest PROCESSING dłużej niż 5 minut i nie ma nowych kroków -> zmień na LOST (status błędu).

## 2. Backend: API Historii
**Plik:** `venom_core/api/history_routes.py` (nowy plik) lub rozszerzenie `main.py`
**Opis:** Endpoints do pobierania historii.
**Wymagania:**
- `GET /api/v1/history/requests` - zwraca listę (paginowaną) requestów z polami: ID, Prompt skrócony, Data, Status, Czas trwania.
- `GET /api/v1/history/requests/{request_id}` - zwraca pełny obiekt ze wszystkimi krokami (`steps`) do wizualizacji szczegółów.

## 3. Frontend: Zakładka "History" (Tabela Requestów)
**Plik:** `web/templates/index.html`, `web/static/css/app.css`
**Opis:** Nowa zakładka w prawym panelu lub osobny widok centralny.
**Wymagania:**
- Dodać zakładkę "📜 History".
- Wyświetlić tabelę z wierszami reprezentującymi requesty.
- **Kolorowanie wierszy (CSS Classes):**
  - ⚪ **Biały** (`status-pending`): Nowy request, jeszcze nie podjęty przez Orchestrator.
  - 🟡 **Żółty** (`status-processing`): W trakcie obróbki (są aktywne kroki).
  - 🟢 **Zielony** (`status-completed`): Zakończony sukcesem (Response wysłany).
  - 🔴 **Czerwony** (`status-failed`): Błąd krytyczny LUB timeout (request "zagubiony").

## 4. Frontend: Widok Szczegółów (Request Journey)
**Plik:** `web/static/js/app.js`
**Opis:** Modal lub rozwijany panel pokazujący, co działo się z requestem.
**Wymagania:**
- Po kliknięciu w wiersz tabeli, pobrać szczegóły z API.
- Wyrenderować "Oś Czasu" (Timeline) lub listę kroków:
  1. `[User]` Wysłanie: "Zrób research"
  2. `[Orchestrator]` Analiza intencji -> Wynik: RESEARCH
  3. `[Researcher]` Uruchomienie WebSkill
  4. `[WebSkill]` Pobieranie strony X
  5. `[Researcher]` Generowanie raportu
  6. `[System]` Zwrócenie odpowiedzi
- Jeśli status to 🔴 (Błąd/Zagubiony), ostatni krok powinien zawierać stack trace lub komunikat "Connection Lost / Timeout".

## 5. Integracja: Podpięcie Tracera do Core
**Pliki:** `venom_core/core/orchestrator.py`, `venom_core/agents/base.py`
**Opis:** Automatyczne raportowanie kroków.
**Wymagania:**
- W `Orchestrator.submit_task`: Utwórz nowy Trace (Status: PENDING -> PROCESSING).
- W `BaseAgent.process`: Dodaj krok "Agent {name} started processing".
- W przypadku wyjątku (`try/except`): Ustaw Status: FAILED i dodaj krok z błędem.

## Kryteria Akceptacji (DoD)
1. Tabela historii odświeża się automatycznie (lub przez WebSocket).
2. Request, który "wisi" w systemie powyżej określonego czasu (np. restart serwera w trakcie pracy), jest oznaczany na czerwono jako "LOST".
3. Kliknięcie w historyczny request pozwala zobaczyć, który dokładnie komponent (Agent/Skill) był ostatni aktywny.
