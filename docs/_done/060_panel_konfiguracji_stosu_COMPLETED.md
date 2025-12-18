# ZADANIE 060: Panel konfiguracji i sterowania stosem

## Cel
- Dodać nowy ekran „Konfiguracja” w menu web-next, który pozwala włączać/wyłączać główne usługi (backend, UI, LLM, tryby rozproszone) oraz edytować kluczowe parametry Venom z poziomu UI.
- Ograniczyć zużycie zasobów (RAM/CPU) przez świadome zarządzanie stosem: szybkie OFF dla ciężkich komponentów (vLLM/Ollama, Next dev), podgląd statusów i parametrów bez grzebania w `.env`.

## Problemy do rozwiązania
- Brak centralnego widoku „co działa”: backend, Next.js, LLM (vLLM/Ollama), Hive/Nexus, zadania w tle → dziś tylko logi/htop.
- Sterowanie stosem wymaga CLI (`make start/stop`, ręczne porty), co utrudnia pracę na słabszych maszynach (WSL, laptopy).
- Parametry w `.env` są liczne i rozproszone – brak UI do szybkiej zmiany trybu pracy (LOCAL/HYBRID/CLOUD), endpointów modeli, przełączników modułów (Hive/Nexus/Ghost/Shadow).

## Zakres funkcjonalny (UI)
1. **Nawigacja**
   - Nowa pozycja menu „Konfiguracja” (desktop + mobile) prowadząca na `/config`.
   - Widok w układzie dwóch paneli: „Usługi” (włącz/wyłącz) oraz „Parametry” (formularze).
2. **Sterowanie stosem**
   - Kafelki usług z live statusem i akcjami: Backend (uvicorn), UI (Next dev/prod), LLM runtime (vLLM/Ollama), Hive/Nexus, zadania w tle (Auto doc/gardening), ewentualnie Docker sandbox.
   - Akcje start/stop/restart + informacja o porcie, PID, ostatnim logu, zużyciu RAM/CPU (pobierane z backendu).
   - Szybkie profile: „Full stack”, „Light” (tylko API), „LLM OFF” – ustawiają zestaw przełączników.
3. **Parametry Venom**
   - Sekcje formularza:
     - Tryb AI: `AI_MODE`, `LLM_SERVICE_TYPE`, endpoint/model lokalny (`LLM_LOCAL_ENDPOINT`, `LLM_MODEL_NAME`), klucze cloud (`OPENAI_API_KEY`, `GOOGLE_API_KEY`), routing (`ENABLE_MODEL_ROUTING`, `FORCE_LOCAL_MODEL`).
     - Moduły rozproszone: `ENABLE_HIVE`, `ENABLE_NEXUS`, host/port/queues, tokeny.
     - Agenci i sensory: `ENABLE_GHOST_AGENT`, `ENABLE_DESKTOP_SENSOR`, `ENABLE_AUDIO_INTERFACE`, progi bezpieczeństwa/UX (`SHADOW_PRIVACY_FILTER`, `GHOST_VERIFICATION_ENABLED`).
     - Zadania w tle: `ENABLE_AUTO_DOCUMENTATION`, `ENABLE_AUTO_GARDENING`, `ENABLE_MEMORY_CONSOLIDATION`, `VENOM_PAUSE_BACKGROUND_TASKS`.
   - Walidacja po stronie UI (required/formaty), podpowiedzi/tooltipy, zapisywanie zmian z potwierdzeniem.
4. **Bezpieczeństwo i ergonomia**
   - Maskowanie pól sekretów (API keys) + przycisk „pokaż” lokalnie.
   - Przy zapisie konfiguracji informacja, które usługi wymagają restartu (np. backend/LLM) i przycisk „Zastosuj i zrestartuj”.
   - Ostrzeżenie przed stop LLM/Backend gdy aktywne zadania (info z backendu).

## Backend (API i logika)
- Endpoint `GET /api/v1/runtime/status` → zwraca statusy usług (pid, port, cpu/mem snapshot, uptime).
- Endpointy akcji: `POST /api/v1/runtime/{service}/{action}` (`start|stop|restart`), obsługujące backend, UI, LLM, Hive/Nexus, background workers. Powinny być odporne na brak procesu i zwracać komunikat.
- Konfiguracja:
  - `GET /api/v1/config/runtime` → zwraca whitelistę parametrów z `.env` (bez sekretów lub z maską).
  - `POST /api/v1/config/runtime` → przyjmuje tylko dozwolone klucze; waliduje, zapisuje do `.env` lub dedykowanego pliku konfiguracyjnego i sygnalizuje potrzebę restartu usług.
- Logi/telemetria: krótka historia ostatnich akcji start/stop (do wyświetlenia na froncie).

## Plan PR (zadanie złożone)
1. **API i serwis runtime**
   - Serwis/status dla usług (uvicorn, Next, vLLM/Ollama, Hive/Nexus, background tasks) + endpointy REST start/stop/restart.
   - Adapter do pobierania CPU/RAM (psutil) i logów (tail z `logs/*.log`).
2. **Warstwa konfiguracji**
   - Whitelist parametrów, model walidacji (Pydantic) + zapis do `.env`/config.
   - Endpoint GET/POST `config/runtime` + sygnalizacja, które usługi wymagają restartu po zmianie.
3. **Frontend – ekran Konfiguracja**
   - Nowa trasa `/config`, wpis w sidebar/topbar/mobile nav.
   - Panel „Usługi” z kafelkami statusów i przełącznikami akcji + profile („Full/Light/LLM OFF”).
   - Panel „Parametry” z sekcjami formularzy, walidacją, maskowaniem sekretów, CTA „Zapisz i zrestartuj”.
   - Sekcja „Tryb LLM” z opisem dwóch wspieranych runtime’ów:
     - `Ollama (Light)` – priorytet na najkrótszy czas pytanie→odpowiedź, niski footprint (single user).
     - `vLLM (Full)` – pipeline benchmarkowy, dłuższy start, rezerwuje cały VRAM, ale pozwala na testy wydajności.
     - Wskazówka: domyślnie uruchamiamy tylko jeden runtime naraz; druga opcja ma sens jedynie, gdy rozdzielamy role (np. UI vs. kodowanie).
   - Link i CTA do ekranu benchmarków (`/benchmark`) z presetem „porównaj te same modele i pytania” – pełna strategia wyboru runtime będzie oparta na wynikach testów (zestaw pytań + licznik tokenów).
4. **Testy i UX**
   - Testy API (start/stop, walidacja wejścia), testy UI (Playwright: zmiana profilu, zapis konfiguracji).
   - Dokumentacja w README/FRONTEND_NEXT_GUIDE: opis ekranu, wymagane env, bezpieczeństwo.

## Kryteria akceptacji
- W menu dostępny jest widok „Konfiguracja” z dwoma panelami: usługi + parametry.
- Można wystartować/zatrzymać backend, UI i LLM z UI; statusy odświeżają się live (polling lub SSE).
- Formularz pozwala zmienić kluczowe parametry (`AI_MODE`, endpointy LLM, przełączniki modułów) z walidacją i maskowaniem sekretów.
- Po zapisie UI informuje, które komponenty zostaną zrestartowane i realizuje restart na żądanie.
- Pokrycie testami API/Playwright podstawowych ścieżek (pobranie statusów, zmiana profilu, zapis konfiguracji).
- Profil runtime LLM komunikuje różnice (Ollama vs. vLLM), pozwala wybrać tylko jeden na raz i opisuje scenariusz dualny (np. UI vs. agent kodujący) jako opcję zaawansowaną.
- W dokumencie pojawia się odniesienie do benchmarków – po uruchomieniu testu (ten sam model, ustalone pytania) UI prezentuje rekomendowaną strategię.

## Ustalenia (zamknięcie pytań otwartych)
- Sterujemy wyłącznie procesami lokalnymi (uvicorn, Next dev/prod, vLLM/Ollama, Hive/Nexus, background workers). Nie integrujemy się z docker-compose ani zewnętrznymi klastrami – pojedyncza instancja jest prostsza w diagnostyce.
- Zmiany konfiguracji trafiają do `.env`, ale przed zapisem tworzymy kopię w katalogu `config/env-history/` (`.env-YYYYMMDD-HHMMSS`). Dzięki temu mamy historię wersji bez ryzyka utraty poprzednich ustawień.
- UI może restartować wszystkie obsługiwane usługi, w tym backend i Next. Panel pokaże ostrzeżenie o krótkiej utracie kontroli podczas restartu UI i wykona sekwencję stop→start bez udziału operatora.
