# Deployment – FastAPI + Next.js

This document describes Venom's new runtime architecture: **FastAPI** runs as standalone API/SSE/WS, and **Next.js (`web-next`)** serves the user interface. Both parts are run and monitored independently.

## Components

| Component | Role | Default port | Start/stop |
|-----------|------|---------------|------------|
| FastAPI (`venom_core.main:app`) | REST API, SSE (`/api/v1/tasks/{id}/stream`), WebSocket `/ws/events` | `8000` | `make start-dev` / `make start-prod` (uvicorn) |
| Next.js (`web-next`) | UI Cockpit/Brain/Strategy (React 19, App Router) | `3000` | `make start-dev` (Next dev) / `make start-prod` (Next build + start) |

## Dependencies and Configuration

1. **Python** – backend installation:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Node.js 18.19+** – frontend:
   ```bash
   npm --prefix web-next install
   ```
3. **Environment variables**:
   | Name | Purpose | Default value |
   |-------|---------|---------------|
   | `SERVE_LEGACY_UI` | Whether FastAPI serves old Jinja UI (`web/`). Set `False` during migration. | `True` |
   | `NEXT_PUBLIC_API_BASE` | Base API URL used by Next (CSR). | `http://localhost:8000` |
   | `NEXT_PUBLIC_WS_BASE` | WebSocket endpoint for `/ws/events`. | `ws://localhost:8000/ws/events` |
   | `API_PROXY_TARGET` | Proxy target in `next.config.ts` (SSR). | `http://localhost:8000` |
   | `NEXT_DISABLE_TURBOPACK` | Set automatically by Makefile in dev mode. | `1` |

## Launch Modes

### Development (`make start` / `make start-dev`)
1. `uvicorn` starts backend with `--reload`.
2. `npm --prefix web-next run dev` starts Next with parameters `--hostname 0.0.0.0 --port 3000`.
3. Makefile manages PIDs (`.venom.pid`, `.web-next.pid`) and blocks multiple starts.
4. `make stop` kills both processes and cleans ports (8000/3000).

### Production (`make start-prod`)
1. Runs `pip install`/`npm install` beforehand.
2. Builds UI: `npm --prefix web-next run build` (standalone, telemetry disabled).
3. Starts backend without `--reload` (`uvicorn venom_core.main:app --host 0.0.0.0 --port 8000 --no-server-header`).
4. Starts `next start` on port 3000.
5. `make stop` works the same way (stops `next start` also via `pkill -f`).

## Legacy Fallback

- For regression purposes, old FastAPI panel can be left:
  - `SERVE_LEGACY_UI=True` – FastAPI still mounts Jinja templates (`/`, `/cockpit`, etc.) on port 8000.
  - Setting `False` makes backend expose only `/api`, `/ws`, `/docs`.
  - In README we described that old panel is treated as "reference solution" and shouldn't be run with Next on same port.

## Monitoring and Logs

- `make status` – reports if processes are alive (PID + ports).
- `logs/` – general backend logs (controlled by `loguru`).
- `web-next/.next/standalone` – build output (not committed).
- `scripts/archive-perf-results.sh` – helper backup of Playwright/pytest/Locust results from `perf-artifacts/` directory.

## Post-Deployment Tests

1. **Backend**: `pytest` + `pytest tests/perf/test_chat_pipeline.py -m performance`
2. **Frontend**: `npm --prefix web-next run lint && npm --prefix web-next run build`
3. **E2E Next**: `npm --prefix web-next run test:e2e`
4. **Next vs legacy chat comparison**: `npm --prefix web-next run test:perf`
5. **Locust (optional)**: `./scripts/run-locust.sh` and run scenario from panel (default `http://127.0.0.1:8089`)

## Deployment Checklist

- [ ] Variable `SERVE_LEGACY_UI` set according to mode (prod → `False`).
- [ ] `make start-prod` works and returns links to backend and UI.
- [ ] Proxy (nginx/docker-compose) redirects `/api` and `/ws` to FastAPI and rest to Next.
- [ ] `npm --prefix web-next run test:e2e` passes on prod build.
- [ ] `npm --prefix web-next run test:perf` shows latency < budget (default 4s for legacy, 5s for Next).
- [ ] `pytest tests/perf/test_chat_pipeline.py -m performance` passes (SSE task_update → task_finished < 25s).
