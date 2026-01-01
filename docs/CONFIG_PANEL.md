# Panel Konfiguracji i Sterowania Stosem (ZADANIE 060 + 084)

## Przegląd

Panel konfiguracji dostępny pod `/config` w interfejsie web-next pozwala na:
- Zarządzanie usługami Venom (uruchamianie, zatrzymywanie, restart)
- Edycję parametrów konfiguracji z poziomu UI
- Monitorowanie statusu usług (CPU, RAM, uptime)
- Stosowanie profili szybkich (Full Stack, Light, LLM OFF)
- **Rozróżnienie usług sterowalnych od konfiguracyjnych** (ZADANIE 084)

## Architektura

### Backend

#### Runtime Controller (`venom_core/services/runtime_controller.py`)
Zarządza cyklem życia procesów Venom:
- **Wykrywanie statusów**: Skanuje PID files (`.venom.pid`, `.web-next.pid`) i procesy systemowe
- **Metryki**: Pobiera CPU/RAM za pomocą `psutil`
- **Akcje**: Start/stop/restart dla każdej usługi
- **Historia**: Przechowuje ostatnie 100 akcji
- **Pole `actionable`**: Rozróżnia usługi z realnymi akcjami od kontrolowanych przez konfigurację

**Obsługiwane usługi:**

**Usługi sterowalne (actionable=true):**
- `backend` (Backend API – FastAPI/uvicorn) – sterowanie przez `make start-dev` / `make stop`
- `ui` (Next.js UI – dev/prod) – sterowanie przez make, razem z backendem
- `llm_ollama` (Ollama) – sterowanie przez komendy z env (`OLLAMA_START_COMMAND`, `OLLAMA_STOP_COMMAND`)
- `llm_vllm` (vLLM) – sterowanie przez komendy z env (`VLLM_START_COMMAND`, `VLLM_STOP_COMMAND`)

**Usługi konfigurowalne (actionable=false):**
- `hive` (przetwarzanie rozproszone) – kontrolowane przez flagę `ENABLE_HIVE` w konfiguracji
- `nexus` (mesh/kooperacja) – kontrolowane przez flagę `ENABLE_NEXUS` w konfiguracji
- `background_tasks` (workery w tle) – kontrolowane przez flagę `VENOM_PAUSE_BACKGROUND_TASKS`

**Usługi monitorowane (actionable=false, z ServiceMonitor):**
- LanceDB (pamięć wektorowa embedded) – tylko health check, brak start/stop
- Redis (broker/locki) – serwis zewnętrzny, tylko health check
- Docker Daemon (sandbox) – serwis systemowy, tylko health check

**Profile:**
- `full` - Uruchamia backend, UI i Ollama
- `light` - Tylko backend i UI
- `llm_off` - Backend i UI, wyłącza LLM

#### Config Manager (`venom_core/services/config_manager.py`)
Zarządza plikiem `.env`:
- **Whitelist**: 55 parametrów dostępnych do edycji przez UI
- **Walidacja**: Pydantic models sprawdzają poprawność danych
- **Backup**: Każda zmiana tworzy backup w `config/env-history/.env-YYYYMMDD-HHMMSS`
- **Restart tracking**: Określa które usługi wymagają restartu po zmianie

**Whitelista parametrów:**
- AI Configuration: `AI_MODE`, `LLM_SERVICE_TYPE`, `LLM_LOCAL_ENDPOINT`, klucze API
- LLM Commands: `VLLM_START_COMMAND`, `OLLAMA_START_COMMAND`
- Parametry generacji (per runtime/model): `MODEL_GENERATION_OVERRIDES` (JSON)
- Hive: `ENABLE_HIVE`, `REDIS_HOST`, `REDIS_PORT`
- Nexus: `ENABLE_NEXUS`, `NEXUS_PORT`, `NEXUS_SHARED_TOKEN`
- Background Tasks: `ENABLE_AUTO_DOCUMENTATION`, `ENABLE_AUTO_GARDENING`
- Agents: `ENABLE_GHOST_AGENT`, `ENABLE_DESKTOP_SENSOR`, `ENABLE_AUDIO_INTERFACE`

**Maskowanie sekretów:**
Parametry zawierające "KEY", "TOKEN", "PASSWORD" są maskowane w formacie: `sk-****1234` (pierwsze 4 i ostatnie 4 znaki)

#### API Endpoints (`venom_core/api/routes/system.py`)

**Runtime:**
```
GET  /api/v1/runtime/status
     → {services: [{name, status, pid, port, cpu_percent, memory_mb, uptime_seconds, last_log, actionable, endpoint?, latency_ms?}]}
     
     Pole 'actionable' określa czy usługa ma realne akcje start/stop/restart:
     - true: usługi sterowalne (backend, ui, llm_ollama, llm_vllm)
     - false: usługi kontrolowane przez konfigurację lub tylko monitorowane (hive, nexus, background_tasks, Redis, Docker, LanceDB)

POST /api/v1/runtime/{service}/{action}
     service: backend|ui|llm_ollama|llm_vllm|hive|nexus|background_tasks
     action: start|stop|restart
     → {success: bool, message: str}
     
     Uwaga: Dla usług z actionable=false (hive, nexus, background_tasks) akcje zwracają komunikat 
     "kontrolowane przez konfigurację" bez wykonywania realnej operacji.

GET  /api/v1/runtime/history?limit=50
     → {history: [{timestamp, service, action, success, message}]}

POST /api/v1/runtime/profile/{profile_name}
     profile_name: full|light|llm_off
     → {success: bool, message: str, results: [...]}
```

**Configuration:**
```
GET  /api/v1/config/runtime?mask_secrets=true
     → {config: {KEY: "value", ...}}

POST /api/v1/config/runtime
     body: {updates: {KEY: "new_value", ...}}
     → {success: bool, message: str, restart_required: [services], changed_keys: [...], backup_path: str}

GET  /api/v1/config/backups?limit=20
     → {backups: [{filename, path, size_bytes, created_at}]}

POST /api/v1/config/restore
     body: {backup_filename: ".env-20240101-120000"}
     → {success: bool, message: str, restart_required: [...]}
```

### Frontend

#### Struktura komponentów
```
web-next/
├── app/config/page.tsx              # Strona główna konfiguracji
├── components/config/
│   ├── config-home.tsx              # Główny komponent z zakładkami
│   ├── services-panel.tsx           # Panel usług (kafelki, akcje, profile)
│   └── parameters-panel.tsx         # Panel parametrów (formularze, sekcje)
└── lib/i18n/locales/
    ├── pl.ts                        # Tłumaczenia PL
    ├── en.ts                        # Tłumaczenia EN
    └── de.ts                        # Tłumaczenia DE
```

#### ServicesPanel (`components/config/services-panel.tsx`)
- **Auto-refresh**: Pobiera status co 5 sekund
- **Kafelki usług**: Wyświetla live status, PID, port, CPU, RAM, uptime, ostatni log
- **Akcje warunkowe**: Przyciski start/stop/restart tylko dla usług z `actionable=true`
- **Usługi non-actionable**: Zamiast przycisków wyświetlany jest info badge "Kontrolowane przez konfigurację"
- **Profile szybkie**: 3 przyciski (Full Stack, Light, LLM OFF)
- **Historia akcji**: Ostatnie 10 akcji z timestampem
- **Feedback**: Komunikaty sukcesu/błędu w formie bannerów

**Rozróżnienie typów usług w UI:**
- **Sterowalne (actionable=true)**: Pełny zestaw przycisków Start/Stop/Restart
- **Konfigurowalne (actionable=false)**: Info badge "Kontrolowane przez konfigurację" - zmiana statusu wymaga edycji parametrów w zakładce "Parametry"
- **Monitorowane (actionable=false, z ServiceMonitor)**: Info badge + ewentualna latencja/endpoint - tylko odczyt statusu

#### ParametersPanel (`components/config/parameters-panel.tsx`)
- **Sekcje**: 8 sekcji konfiguracji (AI, Commands, Hive, Nexus, Tasks, Shadow, Ghost, Avatar)
- **Maskowanie**: Automatyczne maskowanie pól sekretów z przyciskiem "pokaż"
- **Walidacja**: Sprawdzanie wypełnionych pól przed zapisem
- **Sticky footer**: Panel akcji zawsze widoczny na dole ekranu
- **Restart warnings**: Banner z listą usług wymagających restartu po zapisie
- **Info box**: Sekcja informacyjna o Ollama vs vLLM z linkiem do benchmarków

#### Nawigacja
Sidebar zawiera nową pozycję "Konfiguracja" z ikoną Settings:
- Polska: "Konfiguracja"
- Angielska: "Configuration"
- Niemiecka: "Konfiguration"

## Bezpieczeństwo

### Whitelist parametrów
Tylko 55 parametrów jest dostępnych do edycji. Lista jest zdefiniowana w `CONFIG_WHITELIST` w `config_manager.py`. Próba edycji innych parametrów zwraca błąd walidacji.

### Maskowanie sekretów
Parametry zawierające wrażliwe dane są maskowane:
- `OPENAI_API_KEY` → `sk-****1234`
- `GOOGLE_API_KEY` → `AI****5678`
- `NEXUS_SHARED_TOKEN` → `tok_****abcd`
- `REDIS_PASSWORD` → `****`

### Backup automatyczny
Każda zmiana `.env` tworzy backup w `config/env-history/`:
```
config/env-history/
├── .env-20241218-094500
├── .env-20241218-101230
└── .env-20241218-143045
```

System przechowuje ostatnie 50 backupów. Starsze są automatycznie usuwane.

### Kontrola restartów
Po zapisie konfiguracji backend zwraca listę usług wymagających restartu:
- Zmiany w `AI_MODE`, `LLM_SERVICE_TYPE` → restart `backend`
- Zmiany w `ENABLE_HIVE` → restart `backend`
- Zmiany w komendach LLM → brak restartu (komendy używane przy next start/stop)

UI wyświetla ostrzeżenie z listą usług i CTA do zakładki "Usługi".

## Użycie

### Uruchamianie usług
1. Przejdź do `/config`
2. Kliknij zakładkę "Usługi"
3. Wybierz usługę (np. backend)
4. Kliknij "Start"
5. Status zmienia się na "running", wyświetlane są metryki CPU/RAM

### Stosowanie profilu
1. W zakładce "Usługi" kliknij jeden z profili:
   - **Full Stack**: Uruchamia backend, UI, Ollama
   - **Light**: Uruchamia backend, UI (bez LLM)
   - **LLM OFF**: Uruchamia backend, UI, zatrzymuje LLM
2. System wykonuje akcje dla wszystkich usług w profilu
3. Banner pokazuje rezultat operacji

### Edycja parametrów
1. Przejdź do zakładki "Parametry"
2. Znajdź sekcję (np. "Tryb AI")
3. Zmień wartości pól (np. `AI_MODE` na "HYBRID")
4. Kliknij "Zapisz konfigurację" w dolnym panelu
5. System:
   - Tworzy backup `.env`
   - Zapisuje zmiany
   - Wyświetla banner z informacją o sukcesie
   - Pokazuje ostrzeżenie o wymaganych restartach

### Przywracanie backupu
1. API endpoint `/api/v1/config/backups` zwraca listę backupów
2. POST do `/api/v1/config/restore` przywraca wybrany backup
3. Aktualny `.env` jest zapisywany jako nowy backup przed przywróceniem

## Tryby LLM: Ollama vs vLLM

Panel zawiera sekcję informacyjną wyjaśniającą różnice:

**Ollama (Light):**
- Priorytet: najkrótszy czas pytanie→odpowiedź
- Niski footprint pamięci
- Single user, ideal do codziennej pracy
- Szybki start (~3 sekundy)

**vLLM (Full):**
- Pipeline benchmarkowy
- Dłuższy start (~5-10 sekund)
- Rezerwuje cały VRAM
- Wyższa przepustowość dla wielu requestów
- Lepsze do testów wydajności

**Rekomendacja:**
Domyślnie uruchamiamy tylko jeden runtime naraz. Drugi runtime ma sens gdy rozdzielamy role (np. UI na Ollama, agent kodujący na vLLM). Pełna strategia wyboru powinna być oparta na wynikach benchmarków → link do `/benchmark`.

## Testy

### Backend (pytest)
```bash
pytest tests/test_runtime_controller_api.py -v
pytest tests/test_config_manager_api.py -v
```

**Pokrycie:**
- Runtime status (GET /api/v1/runtime/status)
- Service actions (POST /api/v1/runtime/{service}/{action})
- Runtime history (GET /api/v1/runtime/history)
- Runtime profiles (POST /api/v1/runtime/profile/{profile})
- Config get/update (GET/POST /api/v1/config/runtime)
- Config backups (GET /api/v1/config/backups)
- Config restore (POST /api/v1/config/restore)
- Edge cases (invalid service, invalid action, validation errors)

### Frontend (Playwright)
TODO: Dodać scenariusze E2E:
- Nawigacja do `/config`
- Zmiana statusu usługi (start/stop)
- Aplikacja profilu
- Edycja parametru i zapis
- Maskowanie/odmaskowanie sekretu
- Wyświetlanie warningów o restartach

## Troubleshooting

### Usługa nie uruchamia się
**Problem**: Kliknięcie "Start" nie zmienia statusu na "running"

**Rozwiązanie:**
1. Sprawdź logi w kafelku usługi (pole "Ostatni log")
2. Sprawdź PID file:
   - Backend: `.venom.pid`
   - UI: `.web-next.pid`
3. Sprawdź port (czy nie jest zajęty):
   ```bash
   lsof -ti tcp:8000  # Backend
   lsof -ti tcp:3000  # UI
   ```
4. Sprawdź komendy LLM w `.env`:
   - `OLLAMA_START_COMMAND`
   - `VLLM_START_COMMAND`

### Zmiany konfiguracji nie są widoczne
**Problem**: Po zapisie parametrów backend nie widzi nowych wartości

**Rozwiązanie:**
1. Sprawdź czy `.env` został zaktualizowany:
   ```bash
   grep AI_MODE .env
   ```
2. Sprawdź backup w `config/env-history/`
3. Zrestartuj backend (zakładka "Usługi" → backend → Restart)
4. Backend wczytuje `.env` tylko przy starcie

### Błąd "Nieprawidłowy poziom: X"
**Problem**: Próba zapisu nieznanego parametru

**Rozwiązanie:**
1. Sprawdź czy klucz jest na whiteliście (`CONFIG_WHITELIST` w `config_manager.py`)
2. Jeśli parametr jest potrzebny, dodaj go do whitelisty i `RESTART_REQUIREMENTS`

### Port zajęty
**Problem**: Usługa nie może się uruchomić bo port jest zajęty

**Rozwiązanie:**
```bash
# Znajdź proces zajmujący port
lsof -ti tcp:8000

# Zakończ proces
kill <PID>

# Lub użyj make clean-ports
make clean-ports
```

## Roadmap

### Zrealizowane (v1.0)
- [x] Backend runtime controller z obsługą 7 typów usług
- [x] Backend config manager z whitelistą 55 parametrów
- [x] API endpoints dla runtime i config
- [x] Frontend panels: Services i Parameters
- [x] Profile szybkie (Full/Light/LLM OFF)
- [x] Maskowanie sekretów
- [x] Backup .env z historią
- [x] Restart warnings
- [x] Testy jednostkowe backend

### TODO (v1.1)
- [ ] Testy E2E Playwright
- [ ] Docker compose integration (opcjonalnie)
- [ ] Remote nodes control (Hive/Nexus)
- [ ] Logs viewer (tail -f w panelu UI)
- [ ] CPU/RAM alerts (threshold warnings)
- [ ] Service dependencies graph
- [ ] Export/import konfiguracji

### TODO (v1.0)
- [ ] Multi-user access control (role-based)
- [ ] Audit log (kto, kiedy, co zmienił)
- [ ] Config templates (dev/prod/test)
- [ ] One-click deployment profiles
- [ ] Health checks i auto-restart
- [ ] Integracja z systemd/supervisord

## Dokumentacja API

Pełna dokumentacja API dostępna w Swagger UI po uruchomieniu backend:
```
http://localhost:8000/docs
```

Sekcje:
- **Runtime** → `/api/v1/runtime/*`
- **Config** → `/api/v1/config/*`

## Licencja

Zgodnie z licencją projektu Venom.
