# Deployment – FastAPI + Next.js

This document describes Venom's new runtime architecture: **FastAPI** runs as standalone API/SSE/WS, and **Next.js (`web-next`)** serves the user interface. Both parts are run and monitored independently.

For security operating assumptions and localhost admin policy, see `docs/SECURITY_POLICY.md`.

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
   Notes:
   - `requirements.txt` = minimal API/cloud profile (default).
   - For local runtime engines install additional profile:
     - `pip install -r requirements-profile-ollama.txt`
     - `pip install -r requirements-profile-vllm.txt`
     - `pip install -r requirements-profile-onnx.txt`
     - optional extras (not ONNX LLM itself): `pip install -r requirements-extras-onnx.txt` (`faster-whisper`, `piper-tts`)
   - Full legacy stack: `pip install -r requirements-full.txt`
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
   | `OLLAMA_IMAGE` | Ollama container image tag used by compose profiles. | `ollama/ollama:0.16.1` |
   | `VENOM_RUNTIME_PROFILE` | Runtime profile (`light`, `llm_off`, `full`) for single-package deployment flow (`llm_off` = no local LLM runtime, external APIs still possible after key setup). | `light` |
   | `OLLAMA_HOST` | Bind address for Ollama inside container. | `0.0.0.0` |
   | `VENOM_OLLAMA_PROFILE` | Venom single-user tuning profile (`balanced-12-24gb`, `low-vram-8-12gb`, `max-context-24gb-plus`). | `balanced-12-24gb` |
   | `OLLAMA_CONTEXT_LENGTH` | Explicit context override (`0` = profile default). | `0` |
   | `OLLAMA_NUM_PARALLEL` | Explicit parallelism override (`0` = profile default). | `0` |
   | `OLLAMA_MAX_QUEUE` | Explicit queue override (`0` = profile default). | `0` |
   | `OLLAMA_FLASH_ATTENTION` | Enable flash attention. | `1` |
   | `OLLAMA_KV_CACHE_TYPE` | KV cache type override (empty = profile default). | `` |
   | `OLLAMA_LOAD_TIMEOUT` | Model load timeout passed to Ollama runtime. | `10m` |
   | `OLLAMA_NO_CLOUD` | Disable cloud models in Ollama (privacy-oriented local mode). | `1` |
   | `OLLAMA_RETRY_MAX_ATTEMPTS` | Retry attempts for transient Ollama errors (429/5xx). | `2` |
   | `OLLAMA_RETRY_BACKOFF_SECONDS` | Backoff base for Ollama retries. | `0.35` |

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

Detailed step-by-step release procedure:
- `docs/DOCKER_RELEASE_GUIDE.md`

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
- `ghcr.io/mpieniak01/venom-backend`
- `ghcr.io/mpieniak01/venom-frontend`

Security note (MVP default):
- `compose/compose.minimal.yml` publishes ports on host interfaces to allow testing from another computer in LAN.
- `compose/compose.spores.yml.tmp` is a temporary Spore nodes draft, currently unused and not part of the Venom minimal onboarding path.
- Mandatory condition: run this profile only in a trusted/private network.
- Do not expose these ports directly to public Internet. If remote/public access is needed, place a reverse proxy in front and add authentication/authorization.

Default tags:
- always: `sha-<short_sha>`
- on release tag: `<git_tag>` + `latest`
- manual run: optional `custom_tag` (+ optional `latest`)

Example release flow (current stable: `v1.5.0`):
```bash
git checkout main
git pull --ff-only
git tag v1.5.0
git push origin v1.5.0
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
