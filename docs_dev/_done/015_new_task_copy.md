# ZADANIE: 015_THE_OVERMIND (Proactive Maintenance & Background Lifecycle)

**Priorytet:** Strategiczny (Autonomia 3.0)
**Kontekst:** Warstwa Meta i Zarządzania Czasem
**Cel:** Wdrożenie asynchronicznego "bicia serca" systemu. Venom ma działać w tle (jako daemon), monitorować zmiany w plikach, automatycznie aktualizować dokumentację i przeprowadzać "nocną" konsolidację wiedzy oraz refaktoryzację długu technicznego.

---

## 1. Kontekst Biznesowy
Obecnie Venom to "Request-Response". Jeśli zmienisz ręcznie kod w VS Code, Venom o tym nie wie, dopóki mu nie powiesz. Dokumentacja `docs/` szybko staje się przestarzała.
Celem PR jest uruchomienie **Pętli Tła (Background Loop)**, która:
1.  Obserwuje system plików (Watchdog).
2.  Aktualizuje dokumentację w czasie rzeczywistym.
3.  Gdy system jest bezczynny (Idle), uruchamia `GardenerAgent` do sprzątania kodu.

---

## 2. Zakres Prac (Scope)

### A. System Harmonogramowania (`venom_core/core/scheduler.py`)
*Utwórz nowy moduł.* Użyj biblioteki `APScheduler` (Advanced Python Scheduler).
* **Funkcjonalność:**
    - Pozwala rejestrować zadania cykliczne (`interval`, `cron`) oraz zdarzeniowe.
    - Zintegrowany z `FastAPI` (start/stop w `lifespan`).
    - **Zadania domyślne:**
        - `consolidate_memory()` (co 1h): Analiza logów i zapis wniosków do GraphRAG.
        - `check_health()` (co 5min): Pingowanie DockerHabitat.

### B. Moduł Obserwatora (`venom_core/perception/watcher.py`)
*Utwórz moduł z użyciem biblioteki `watchdog`.*
* **Działanie:** Nasłuchuje zdarzeń `FileModified` w katalogu `./workspace` (z wykluczeniem `.git`, `__pycache__`).
* **Reakcja:**
    - Gdy plik `.py` się zmieni -> Triggeruje zdarzenie `CODE_CHANGED`.
    - Przekazuje to zdarzenie do `EventBroadcaster` (WebSocket), aby Dashboard odświeżył widok plików.

### C. Agent Dokumentalista (`venom_core/agents/documenter.py`)
*Wyspecjalizuj `WriterAgent` lub stwórz nowego.*
* **Trigger:** Zdarzenie `CODE_CHANGED` z Watchera.
* **Logika:**
    1. Pobiera diff zmienionego pliku.
    2. Analizuje wpływ zmiany na istniejącą dokumentację (np. `README.md` lub docstringi).
    3. **Autokorekta:** Jeśli zmieniła się sygnatura funkcji, automatycznie aktualizuje docstring i plik `.md` opisujący API.
    4. Używa `GitSkill`, aby stworzyć commit: `docs: auto-update documentation for [file]`.

### D. Tryb "Idle" i Ogrodnik (`venom_core/agents/gardener.py`)
Rozwiń istniejącego (prawdopodobnie pustego) Agenta.
* **Strategia:** Jeśli przez 15 minut nie było requestu od użytkownika (`orchestrator.last_activity`):
    1. Pobiera listę plików o wysokiej złożoności cyklomatycznej (użyj `radon` lub prostej heurystyki w `CodeSkill`).
    2. Planuje refaktoryzację jednego pliku.
    3. Tworzy branch `refactor/auto-gardening`.
    4. Wprowadza zmiany, testuje (PR 012 Guardian) i zostawia branch do akceptacji (nie merge'uje sam do main).

### E. Dashboard: Centrum Operacyjne 24/7 (`web/`)
* Dodaj sekcję **"Background Jobs"**.
* Lista aktywnych zadań w tle (np. "Indexing Memory...", "Watching Files").
* Przełącznik "Auto-Gardening Mode" (ON/OFF) – żeby Venom nie zmieniał kodu, gdy Ty pracujesz.

---

## 3. Kryteria Akceptacji (DoD)

1.  ✅ **Live Documentation:**
    * Zmieniasz ręcznie nazwę funkcji w `main.py` i zapisujesz plik.
    * W ciągu minuty Venom wykrywa zmianę i automatycznie aktualizuje `docs/` oraz tworzy commit `docs: update`.
2.  ✅ **Refaktoryzacja w tle:**
    * Zostawiasz włączonego Venoma na noc.
    * Rano widzisz nowy branch `refactor/...` z poprawionym kodem i zielonymi testami.
3.  ✅ **Konsolidacja Pamięci:**
    * Po intensywnej sesji, Venom automatycznie "trawi" rozmowę i zapisuje kluczowe ustalenia do `VectorStore`, co widać w logach schedulera.
4.  ✅ **Stabilność:**
    * Watchdog nie wpada w pętlę nieskończoną (Venom zmienia plik -> Watchdog wykrywa zmianę -> Venom reaguje -> Venom zmienia plik...). *Hint: Ignoruj zmiany dokonywane przez użytkownika "venom-bot".*

---

## 4. Wskazówki Techniczne
* **Debouncing:** Zdarzenia z `watchdog` przychodzą seriami. Zaimplementuj mechanizm *debounce* (czekaj np. 5 sekund ciszy przed reakcją), aby nie triggerować AI po każdym naciśnięciu Ctrl+S.
* **APScheduler:** Użyj `AsyncIOScheduler`, aby nie blokować głównego wątku FastAPI.
* **Safety Switch:** Dodaj globalną flagę `VENOM_PAUSE_BACKGROUND_TASKS` w configu, łatwo dostępną z Dashboardu.
