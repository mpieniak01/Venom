# Deployment – FastAPI + Next.js

Ten dokument opisuje nową architekturę uruchomieniową Venoma: **FastAPI** działa jako samodzielne API/SSE/WS, a **Next.js (`web-next`)** serwuje interfejs użytkownika. Obie części są uruchamiane i monitorowane niezależnie.

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

## Tryby uruchomień

### Development (`make start` / `make start-dev`)
1. `uvicorn` startuje backend z `--reload`.
2. `npm --prefix web-next run dev` rusza Next-a z parametrami `--hostname 0.0.0.0 --port 3000`.
3. Makefile pilnuje PID-ów (`.venom.pid`, `.web-next.pid`) i blokuje wielokrotne starty.
4. `make stop` zabija oba procesy i czyści porty (8000/3000).

### Production (`make start-prod`)
1. Uruchamia `pip install`/`npm install` wcześniej.
2. Buduje UI: `npm --prefix web-next run build` (standalone, telemetry wyłączone).
3. Startuje backend bez `--reload` (`uvicorn venom_core.main:app --host 0.0.0.0 --port 8000 --no-server-header`).
4. Startuje `next start` na porcie 3000.
5. `make stop` działa tak samo (zatrzymuje `next start` też przez `pkill -f`).

## Monitorowanie i logi

- `make status` – informuje czy procesy żyją (PID + porty).
- `logs/` – ogólne logi backendowe (kontrolowane przez `loguru`).
- `web-next/.next/standalone` – output buildu (nie commitujemy).
- `scripts/archive-perf-results.sh` – pomocniczy backup wyników Playwright/pytest/Locust z katalogu `perf-artifacts/`.

## Testy po wdrożeniu

1. **Backend**: `pytest` + `pytest tests/perf/test_chat_pipeline.py -m performance`
2. **Frontend**: `npm --prefix web-next run lint && npm --prefix web-next run build`
3. **E2E Next**: `npm --prefix web-next run test:e2e`
4. **Latencja czatu Next**: `npm --prefix web-next run test:perf`
5. **Locust (opcjonalnie)**: `./scripts/run-locust.sh` i odpalenie scenariusza z panelu (domyślnie `http://127.0.0.1:8089`)

## Checklist wdrożeniowy

- [ ] `make start-prod` działa i zwraca linki do backendu i UI.
- [ ] Proxy (nginx/docker-compose) przekierowuje `/api` i `/ws` na FastAPI oraz resztę na Next.
- [ ] `npm --prefix web-next run test:e2e` przechodzi na buildzie prod.
- [ ] `npm --prefix web-next run test:perf` wykazuje latency < budżet (domyślnie 15s).
- [ ] `pytest tests/perf/test_chat_pipeline.py -m performance` przechodzi (SSE task_update → task_finished < 25s).
