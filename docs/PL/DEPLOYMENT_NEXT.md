# Deployment – FastAPI + Next.js

Ten dokument opisuje nową architekturę uruchomieniową Venoma: **FastAPI** działa jako samodzielne API/SSE/WS, a **Next.js (`web-next`)** serwuje interfejs użytkownika. Obie części są uruchamiane i monitorowane niezależnie.

Założenia bezpieczeństwa operacyjnego oraz politykę localhost-admin opisuje `docs/PL/SECURITY_POLICY.md`.

## Składniki

| Komponent | Rola | Domyślny port | Start/stop |
|-----------|------|---------------|------------|
| FastAPI (`venom_core.main:app`) | REST API, SSE (`/api/v1/tasks/{id}/stream`), WebSocket `/ws/events` | `8000` | `make start-dev` / `make start-prod` (uvicorn) |
| Next.js (`web-next`) | UI Cockpit/Brain/Strategy (React 19, App Router) | `3000` | `make start-dev` (Next dev) / `make start-prod` (Next build + start) |

## Zależności i konfiguracja

1. **Python** – instalacja backendu:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   Uwagi:
   - `requirements.txt` = minimalny profil API/cloud (domyślny).
   - Dla lokalnych silników runtime doinstaluj profil:
     - `pip install -r requirements.txt` (Ollama)
     - `pip install -r requirements-profile-vllm.txt`
     - `pip install -r requirements-profile-onnx.txt`
     - `pip install -r requirements-profile-onnx-cpu.txt`
   - opcjonalne extras (instaluj po profilu ONNX/ONNX-CPU): `pip install -r requirements-extras-onnx.txt` (`faster-whisper`, `piper-tts`)
   - Pełny legacy stack: `pip install -r requirements-full.txt`

### Kontrakt profili zależności (ważne)

Tych gwarancji używamy do rozróżnienia "to normalne" vs "to błąd":

| Profil | Co gwarantuje | Czego nie gwarantuje |
|---|---|---|
| `requirements.txt` / API | backend + integracje cloud | lokalne ciężkie stosy: `vllm`, stos ONNX, `lancedb`, `sentence-transformers` |
| `requirements-profile-web.txt` | API + zależności integracji web | te same ciężkie stosy lokalne co profil API |
| `requirements-profile-vllm.txt` | API + `vllm` | stos ONNX, `lancedb`, `sentence-transformers` |
| `requirements-profile-onnx*.txt` | API + stos runtime ONNX | `vllm`, `lancedb`, `sentence-transformers` |
| `requirements-full.txt` | pełny legacy stack (wszystkie główne stosy razem) | n/a |

Zasady interpretacji:
1. Brak pakietu po instalacji niewłaściwego profilu jest zachowaniem oczekiwanym.
2. Brak pakietu, który nie należy do zakresu wybranego profilu, jest zachowaniem oczekiwanym.
3. Brak pakietu, który jest jawnie wpisany w pliku wybranego profilu, oznacza problem instalacji/środowiska i traktujemy to jako defekt.
2. **Node.js 18.19+** – frontend:
   ```bash
   npm --prefix web-next install
   ```
3. **Zmienne środowiskowe**:
   | Nazwa | Przeznaczenie | Wartość domyślna |
   |-------|---------------|------------------|
   | `NEXT_PUBLIC_API_BASE` | Bazowy URL API używany przez Next (CSR). | `http://localhost:8000` |
   | `NEXT_PUBLIC_WS_BASE` | Endpoint WebSocket dla `/ws/events`. | `ws://localhost:8000/ws/events` |
   | `API_PROXY_TARGET` | Cel proxy w `next.config.ts` (SSR). | `http://localhost:8000` |
   | `NEXT_DISABLE_TURBOPACK` | W trybie dev ustawiane automatycznie przez Makefile. | `1` |
   | `OLLAMA_IMAGE` | Tag obrazu Ollama używany w profilach compose. | `ollama/ollama:0.16.1` |
   | `VENOM_RUNTIME_PROFILE` | Profil runtime (`light`, `llm_off`, `full`) dla modelu jednej paczki (`llm_off` = bez lokalnego runtime LLM, ale możliwe API zewnętrzne po konfiguracji kluczy). | `light` |
   | `OLLAMA_HOST` | Adres nasłuchu Ollama wewnątrz kontenera. | `0.0.0.0` |
   | `VENOM_OLLAMA_PROFILE` | Profil strojenia single-user (`balanced-12-24gb`, `low-vram-8-12gb`, `max-context-24gb-plus`). | `balanced-12-24gb` |
   | `OLLAMA_CONTEXT_LENGTH` | Jawne nadpisanie kontekstu (`0` = domyślne z profilu). | `0` |
   | `OLLAMA_NUM_PARALLEL` | Jawne nadpisanie równoległości (`0` = domyślne z profilu). | `0` |
   | `OLLAMA_MAX_QUEUE` | Jawne nadpisanie kolejki (`0` = domyślne z profilu). | `0` |
   | `OLLAMA_FLASH_ATTENTION` | Włącza flash attention. | `1` |
   | `OLLAMA_KV_CACHE_TYPE` | Nadpisanie typu KV cache (puste = domyślne z profilu). | `` |
   | `OLLAMA_LOAD_TIMEOUT` | Timeout ładowania modelu przekazywany do runtime Ollama. | `10m` |
   | `OLLAMA_NO_CLOUD` | Wyłącza modele cloud w Ollama (tryb privacy/local-first). | `1` |
   | `OLLAMA_RETRY_MAX_ATTEMPTS` | Liczba prób retry dla błędów przejściowych Ollama (429/5xx). | `2` |
   | `OLLAMA_RETRY_BACKOFF_SECONDS` | Bazowy backoff retry dla Ollama. | `0.35` |

## Tryby uruchomień

Kontrakt wyboru środowiska:
- `Makefile` wybiera aktywne pliki env i eksportuje `ENV_FILE` / `ENV_EXAMPLE_FILE` do skryptów runtime.
- Skrypty runtime (`start_stack.sh`, `vllm_service.sh`, `ollama_service.sh`) używają wspólnego loadera `scripts/lib/env_contract.sh`.
- Priorytet wartości efektywnej w skryptach runtime: `make VAR=...` (lub eksport środowiska shella) > wartość z `ENV_FILE` > domyślny fallback skryptu.
- Wartości runtime-domain (`ACTIVE_LLM_SERVER`, `VLLM_*`, `OLLAMA_*`) utrzymujemy w `.env*`; `Makefile` trzyma głównie domyślne parametry operatorskie/lifecycle.
- W kontrakcie runtime nie używamy już gołego `.env` / `.env.example`.

### Development (`make start` / `make start-dev`)
Plik konfiguracji:
- plik runtime: `.env.dev` (lokalny, niecommitowany)
- bezpieczny szablon: `.env.dev.example` (commitowany, bez sekretów)

1. `uvicorn` startuje backend z `--reload`.
2. `npm --prefix web-next run dev` rusza Next-a z parametrami `--hostname 0.0.0.0 --port 3000`.
3. Makefile pilnuje PID-ów (`.venom.pid`, `.web-next.pid`) i blokuje wielokrotne starty.
4. `make stop` zabija oba procesy i czyści porty (8000/3000).

### Production (`make start-prod`)
Plik konfiguracji:
- plik runtime: `.env.dev` (lokalny, niecommitowany)
- bezpieczny szablon: `.env.dev.example` (commitowany, bez sekretów)

Ostrzeżenie:
- `make start-prod` jest dostępne, ale `prod` nie jest obecnie w pełni zwalidowane/rekomendowane do działania live.
- Do codziennej pracy i akceptacji używaj przepływów `dev` oraz `preprod`.

1. Uruchamia `pip install`/`npm install` wcześniej.
2. Buduje UI: `npm --prefix web-next run build` (standalone, telemetry wyłączone).
3. Startuje backend bez `--reload` (`uvicorn venom_core.main:app --host 0.0.0.0 --port 8000 --no-server-header`).
4. Startuje `next start` na porcie 3000.
5. `make stop` działa tak samo (zatrzymuje `next start` też przez `pkill -f`).

### Pre-production (`make start-preprod`)
1. Używa trybu produkcyjnego na wspólnym stacku (`START_MODE=prod`).
2. Używa dedykowanego pliku konfiguracji preprod:
   - plik runtime: `.env.preprod` (lokalny, niecommitowany)
   - bezpieczny szablon: `.env.preprod.example` (commitowany, bez sekretów)
   - komenda pomocnicza: `make ensure-preprod-env-file`
3. Ustawia przed startem zmienne izolacji preprod:
   - `ENVIRONMENT_ROLE=preprod`
   - `DB_SCHEMA=preprod`
   - `CACHE_NAMESPACE=preprod`
   - `QUEUE_NAMESPACE=preprod`
   - `STORAGE_PREFIX=preprod`
   - `ALLOW_DATA_MUTATION=0`
4. Uruchamia ten sam pipeline co `start-prod`, ale z izolacją danych preprod.

Przydatne warianty:
```bash
make ensure-preprod-env-file # tworzy .env.preprod na podstawie .env.preprod.example
make start-preprod          # backend + frontend w trybie preprod
make api-preprod            # tylko backend w trybie preprod
make web-preprod            # tylko frontend w trybie preprod
make test-preprod-readonly-smoke

# krótkie aliasy
make ensurepreenv
make startpre
make stoppre
make restartpre
make statuspre
make apipre
make webpre
make testpre
```

## Mapa modułów Makefile i katalog komend

Główny `Makefile` działa teraz jako cienki entrypoint i dołącza moduły:

- `make/tests.mk`
- `make/maintenance.mk`
- `make/preprod.mk`
- `make/runtime.mk`
- `make/ops.mk`

Publiczne grupy komend:

1. Lifecycle głównego stacka
- `make start` - pełny stack dev (backend + frontend webpack-safe + aktywny runtime LLM)
- `make start2` - pełny stack dev z frontendem Turbopack
- `make stop` - zatrzymanie backendu + frontendu + helperów runtime
- `make status` - status procesów (PID/porty)

2. Testy i bramki jakości (`make/tests.mk`)
- `make test`, `make test-data`, `make test-all`
- `make test-unit`, `make test-smoke`, `make test-perf`
- `make test-web-unit`, `make test-web-e2e`
- `make pr-fast` - wymagany lokalny gate PR
- `make test-fast-coverage`, `make check-new-code-coverage`

3. Maintenance i higiena środowiska (`make/maintenance.mk`)
- `make make-targets-audit` - walidacja spójności `.PHONY` vs zdefiniowane targety
- `make audit-dead-code` - heurystyczny audyt ślepego kodu (Python)
- `make audit-dead-code-vulture-install` - ręczna instalacja vulture do `.venv`
- `make audit-dead-code-full` - heurystyczny audyt ślepego kodu + sygnał vulture
- `make stack-stability-audit` - ręczna diagnostyka: pid, porty, manifesty modułów optional
- `make llm-runtime-stability-audit` - ręczny audyt lifecycle LLM na działającym stacku (aktywacja/switch/unload dla ollama/vllm/onnx)
- `make llm-runtime-stability-cycle-start` - cykl: `make start` -> audyt lifecycle runtime LLM -> `make stop`
- `make llm-runtime-stability-cycle-start2` - cykl: `make start2` -> audyt lifecycle runtime LLM -> `make stop`
- `make env-audit`, `make env-clean-safe`, `make env-clean-docker-safe`, `make env-clean-deep`, `make env-report-diff`
- `make security-delta-scan`, `make security-delta-scan-strict`
- `make mcp-clean`, `make mcp-status`

4. Kontrola runtime (`make/runtime.mk`)
- `make vllm-start`, `make vllm-stop`, `make vllm-restart`
- `make ollama-start`, `make ollama-stop`, `make ollama-restart`

5. Operacje preprod (`make/preprod.mk` + targety root)
- `make ensure-preprod-env-file`, `make start-preprod`, `make api-preprod`, `make web-preprod`
- aliasy: `make startpre`, `make apipre`, `make webpre`, `make testpre`
- `make preprod-backup`, `make preprod-restore TS=<timestamp>`, `make preprod-verify TS=<timestamp>`
- `make preprod-audit`, `make preprod-drill`, `make preprod-readiness-check`

Wewnętrzny helper używany przez wrappery preprod:
- `make ensure-env-file` deleguje bootstrap pliku env do `scripts/dev/ensure_env_file.sh`.

6. Narzędzia operacyjne i workspace (`make/ops.mk`)
- `make modules-status`, `make modules-pull`, `make modules-branches`, `make modules-exec CMD='...'`
- `make runtime-maintenance-cleanup`
- `make runtime-log-policy-audit`, `make runtime-logrotate-install-help`
- `make monitor`

Kanoniczna lista komend operatorskich pozostaje dostępna przez:
- `make help`

## Monitorowanie i logi

- `make status` – informuje czy procesy żyją (PID + porty).
- `logs/` – ogólne logi backendowe (kontrolowane przez `loguru`).
- `web-next/.next/standalone` – output buildu (nie commitujemy).
- `scripts/archive-perf-results.sh` – pomocniczy backup wyników Playwright/pytest/Locust z katalogu `perf-artifacts/`.

### Polityka retencji danych runtime i logów

Venom uruchamia automatyczne zadanie retencji w `BackgroundScheduler` dla plików runtime.

- **Co jest czyszczone**: katalogi z `SETTINGS.RUNTIME_RETENTION_TARGETS` (domyślnie: `./logs`, `./data/timelines`, `./data/memory`, `./data/training`, `./data/synthetic_training`, `./data/learning`).
- **Okres retencji**: `SETTINGS.RUNTIME_RETENTION_DAYS` (domyślnie: `7` dni).
- **Częstotliwość uruchamiania**: jedno natychmiastowe uruchomienie po starcie aplikacji + interwał z `SETTINGS.RUNTIME_RETENTION_INTERVAL_MINUTES` (domyślnie: `1440`, raz na dobę).
- **Przełącznik funkcji**: `SETTINGS.ENABLE_RUNTIME_RETENTION_CLEANUP` (domyślnie: `True`).
- **Guard startowy**: jednorazowe uruchomienie po starcie wykona się tylko wtedy, gdy ostatnia udana retencja jest starsza niż ustawiony interwał (brak „mielenia” przy częstym reloadzie w dev).
- **Marker stanu**: `./.venom_runtime/runtime_retention.last_run` zapisuje timestamp ostatniego wykonania retencji runtime.
- **Bezpiecznik**: pliki śledzone przez Git są wykluczone z usuwania przez retencję.

Referencje implementacji:
- funkcja joba: `venom_core/jobs/scheduler.py` (`cleanup_runtime_files`)
- rejestracja w schedulerze: `venom_core/main.py` (job interwałowy `cleanup_runtime_files`)
- wartości domyślne konfiguracji: `venom_core/config.py` (ustawienia retencji runtime)

## Paczki Docker Minimal (build i publikacja)

Szczegółowa procedura wydania krok po kroku:
- `docs/PL/DOCKER_RELEASE_GUIDE.md`

Dla dockerowego onboardingu MVP używamy dwóch workflow:

1. **`docker-sanity`** (`.github/workflows/docker-sanity.yml`)
   - uruchamia się na PR-ach dotykających plików Docker,
   - waliduje compose + skrypty shell + build obrazów,
   - **nie** publikuje obrazów.

2. **`docker-publish`** (`.github/workflows/docker-publish.yml`)
   - publikuje obrazy do GHCR tylko gdy:
     - wypchniesz tag `v*` (tryb release), albo
     - uruchomisz workflow ręcznie (`workflow_dispatch`).
   - zabezpieczenia przed przypadkowym wydaniem:
     - manualny publish wymaga `confirm_publish=true`,
     - manualny publish działa tylko z gałęzi `main`,
     - publish po tagu wymaga ścisłego semver (`vMAJOR.MINOR.PATCH`) i commita należącego do historii `main`.
   - dzięki temu nie publikujemy paczek po każdym drobnym commicie.

Publikowane obrazy:
- `ghcr.io/mpieniak01/venom-backend`
- `ghcr.io/mpieniak01/venom-frontend`

Uwaga bezpieczeństwa (domyślnie dla MVP):
- `compose/compose.minimal.yml` publikuje porty na interfejsach hosta, aby umożliwić testy z innego komputera w LAN.
- `compose/compose.spores.yml.tmp` to tymczasowy draft topologii Spore, obecnie nieużywany i poza ścieżką onboardingu Venom minimal.
- Warunek konieczny: uruchamiaj ten profil wyłącznie w zaufanej/prywatnej sieci.
- Nie wystawiaj tych portów bezpośrednio do Internetu. Dla dostępu publicznego użyj reverse proxy i dodaj uwierzytelnienie/autoryzację.

Domyślne tagi:
- zawsze: `sha-<short_sha>`
- na tagu release: `<git_tag>` + `latest`
- przy uruchomieniu ręcznym: opcjonalny `custom_tag` (+ opcjonalny `latest`)

Przykładowy flow release (aktualny stable: `v1.8.0`):
```bash
git checkout main
git pull --ff-only
git tag v1.8.0
git push origin v1.8.0
```

## Testy po wdrożeniu

1. **Backend**: `pytest` + `pytest tests/perf/test_chat_pipeline.py -m performance`
2. **Frontend**: `npm --prefix web-next run lint && npm --prefix web-next run build`
3. **E2E Next**: `npm --prefix web-next run test:e2e`
4. **Latencja czatu Next**: `npm --prefix web-next run test:perf`
5. **Locust (opcjonalnie)**: `./scripts/run-locust.sh` i odpalenie scenariusza z panelu (domyślnie `http://127.0.0.1:8089`)

## Checklist wdrożeniowy

- [ ] `make start-prod` działa i zwraca linki do backendu i UI (zgodność techniczna; to nie jest jeszcze rekomendowana ścieżka aktywnego rolloutu prod).
- [ ] Proxy (nginx/docker-compose) przekierowuje `/api` i `/ws` na FastAPI oraz resztę na Next.
- [ ] `npm --prefix web-next run test:e2e` przechodzi na buildzie prod.
- [ ] `npm --prefix web-next run test:perf` wykazuje latency < budżet (domyślnie 15s).
- [ ] `pytest tests/perf/test_chat_pipeline.py -m performance` przechodzi (SSE task_update → task_finished < 25s).
