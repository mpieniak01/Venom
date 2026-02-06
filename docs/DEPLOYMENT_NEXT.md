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

## Monitoring and Logs

- `make status` – reports if processes are alive (PID + ports).
- `logs/` – general backend logs (controlled by `loguru`).
- `web-next/.next/standalone` – build output (not committed).
- `scripts/archive-perf-results.sh` – helper backup of Playwright/pytest/Locust results from `perf-artifacts/` directory.

## Docker Minimal Packages (Build and Publish)

For Docker onboarding MVP we use two workflows:

1. **`docker-sanity`** (`.github/workflows/docker-sanity.yml`)
   - runs on PRs touching Docker files,
   - validates compose + shell scripts + image build,
   - does **not** publish images.

2. **`docker-publish`** (`.github/workflows/docker-publish.yml`)
   - publishes GHCR images only on:
     - git tag push matching `v*` (release mode), or
     - manual run (`workflow_dispatch`).
   - accidental-release guards:
     - manual publish requires `confirm_publish=true`,
     - manual publish is allowed only from `main`,
     - tag publish requires strict semver tag (`vMAJOR.MINOR.PATCH`) and tag commit that belongs to `main` history.
   - avoids package rebuild/publish on every small commit.

Published images:
- `ghcr.io/<owner>/venom-backend`
- `ghcr.io/<owner>/venom-frontend`

Security note (MVP default):
- `compose/compose.minimal.yml` publishes ports on host interfaces to allow testing from another computer in LAN.
- Mandatory condition: run this profile only in a trusted/private network.
- Do not expose these ports directly to public Internet. If remote/public access is needed, place a reverse proxy in front and add authentication/authorization.

Default tags:
- always: `sha-<short_sha>`
- on release tag: `<git_tag>` + `latest`
- manual run: optional `custom_tag` (+ optional `latest`)

Example release flow:
```bash
git checkout main
git pull --ff-only
git tag v1.0.0
git push origin v1.0.0
```

## Post-Deployment Tests

1. **Backend**: `pytest` + `pytest tests/perf/test_chat_pipeline.py -m performance`
2. **Frontend**: `npm --prefix web-next run lint && npm --prefix web-next run build`
3. **E2E Next**: `npm --prefix web-next run test:e2e`
4. **Next chat latency**: `npm --prefix web-next run test:perf`
5. **Locust (optional)**: `./scripts/run-locust.sh` and run scenario from panel (default `http://127.0.0.1:8089`)

## Deployment Checklist

- [ ] `make start-prod` works and returns links to backend and UI.
- [ ] Proxy (nginx/docker-compose) redirects `/api` and `/ws` to FastAPI and rest to Next.
- [ ] `npm --prefix web-next run test:e2e` passes on prod build.
- [ ] `npm --prefix web-next run test:perf` shows latency < budget (default 15s).
- [ ] `pytest tests/perf/test_chat_pipeline.py -m performance` passes (SSE task_update → task_finished < 25s).
