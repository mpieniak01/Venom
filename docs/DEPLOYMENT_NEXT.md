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
     - `pip install -r requirements.txt` (Ollama)
     - `pip install -r requirements-profile-vllm.txt`
     - `pip install -r requirements-profile-onnx.txt`
     - `pip install -r requirements-profile-onnx-cpu.txt`
     - optional extras (install after ONNX/ONNX-CPU profile): `pip install -r requirements-extras-onnx.txt` (`faster-whisper`, `piper-tts`)
   - Full legacy stack: `pip install -r requirements-full.txt`

### Dependency Profile Contract (Important)

Use these guarantees to classify issues correctly:

| Profile | What it guarantees | What it does not guarantee |
|---|---|---|
| `requirements.txt` / API | backend + cloud integrations | local heavy stacks: `vllm`, ONNX runtime stack, `lancedb`, `sentence-transformers` |
| `requirements-profile-web.txt` | API + web integration deps | same heavy local stacks as API profile |
| `requirements-profile-vllm.txt` | API + `vllm` | ONNX stack, `lancedb`, `sentence-transformers` |
| `requirements-profile-onnx*.txt` | API + ONNX runtime stack | `vllm`, `lancedb`, `sentence-transformers` |
| `requirements-full.txt` | all legacy runtime stacks together | n/a |

Interpretation rules:
1. Missing package after installing the wrong profile is expected.
2. Missing package that is outside selected profile scope is expected.
3. Missing package that is explicitly present in selected profile file indicates install/environment defect.
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

Environment selection contract:
- `Makefile` selects active env files and exports `ENV_FILE` / `ENV_EXAMPLE_FILE` to runtime scripts.
- Runtime scripts (`start_stack.sh`, `vllm_service.sh`, `ollama_service.sh`) use shared loader `scripts/lib/env_contract.sh`.
- Effective value priority in runtime scripts: `make VAR=...` (or exported shell env) > value from `ENV_FILE` > script default.
- Runtime-domain values (`ACTIVE_LLM_SERVER`, `VLLM_*`, `OLLAMA_*`) should be maintained in `.env*`; `Makefile` keeps operator/lifecycle defaults.
- No bare `.env` / `.env.example` in runtime contract.

### Development (`make start` / `make start-dev`)
Config file:
- runtime file: `.env.dev` (local, not committed)
- safe template: `.env.dev.example` (committed, no secrets)

1. `uvicorn` starts backend with `--reload`.
2. `npm --prefix web-next run dev` starts Next with parameters `--hostname 0.0.0.0 --port 3000`.
3. Makefile manages PIDs (`.venom.pid`, `.web-next.pid`) and blocks multiple starts.
4. `make stop` kills both processes and cleans ports (8000/3000).

### Production (`make start-prod`)
Config file:
- runtime file: `.env.dev` (local, not committed)
- safe template: `.env.dev.example` (committed, no secrets)

Warning:
- `make start-prod` is available, but `prod` is currently not fully validated/recommended for live operation.
- Prefer `dev` and `preprod` flows for daily work and acceptance.

1. Runs `pip install`/`npm install` beforehand.
2. Builds UI: `npm --prefix web-next run build` (standalone, telemetry disabled).
3. Starts backend without `--reload` (`uvicorn venom_core.main:app --host 0.0.0.0 --port 8000 --no-server-header`).
4. Starts `next start` on port 3000.
5. `make stop` works the same way (stops `next start` also via `pkill -f`).

### Pre-production (`make start-preprod`)
1. Uses production runtime mode on shared stack (`START_MODE=prod`).
2. Uses dedicated preprod config file:
   - runtime file: `.env.preprod` (local, not committed)
   - safe template: `.env.preprod.example` (committed, no secrets)
   - helper command: `make ensure-preprod-env-file`
3. Exports preprod isolation variables before startup:
   - `ENVIRONMENT_ROLE=preprod`
   - `DB_SCHEMA=preprod`
   - `CACHE_NAMESPACE=preprod`
   - `QUEUE_NAMESPACE=preprod`
   - `STORAGE_PREFIX=preprod`
   - `ALLOW_DATA_MUTATION=0`
4. Runs same startup pipeline as `start-prod` with preprod data isolation.

Useful variants:
```bash
make ensure-preprod-env-file # creates .env.preprod from .env.preprod.example
make start-preprod          # backend + frontend in preprod mode
make api-preprod            # backend only in preprod mode
make web-preprod            # frontend only in preprod mode
make test-preprod-readonly-smoke

# short aliases
make ensurepreenv
make startpre
make stoppre
make restartpre
make statuspre
make apipre
make webpre
make testpre
```

## Makefile Module Map and Command Catalog

The root `Makefile` is now a thin entrypoint and includes dedicated modules:

- `make/tests.mk`
- `make/maintenance.mk`
- `make/preprod.mk`
- `make/runtime.mk`
- `make/ops.mk`

Public command groups:

1. Core stack lifecycle
- `make start` - full dev stack (backend + frontend webpack-safe + active LLM runtime)
- `make start2` - full dev stack with Turbopack frontend
- `make stop` - stop backend + frontend + active LLM runtime helpers
- `make status` - process status (PID/ports)

2. Test and quality gates (`make/tests.mk`)
- `make test`, `make test-data`, `make test-all`
- `make test-unit`, `make test-smoke`, `make test-perf`
- `make test-web-unit`, `make test-web-e2e`
- `make pr-fast` - required local PR gate
- `make test-fast-coverage`, `make check-new-code-coverage`

3. Maintenance and environment hygiene (`make/maintenance.mk`)
- `make make-targets-audit` - validates `.PHONY` vs defined targets
- `make audit-dead-code` - heuristic dead-code audit (Python)
- `make audit-dead-code-vulture-install` - manual install of vulture into `.venv`
- `make audit-dead-code-full` - heuristic dead-code audit + vulture soft-signal
- `make stack-stability-audit` - manual diagnostics: pid files, bound ports, optional module manifests
- `make env-audit`, `make env-clean-safe`, `make env-clean-docker-safe`, `make env-clean-deep`, `make env-report-diff`
- `make security-delta-scan`, `make security-delta-scan-strict`
- `make mcp-clean`, `make mcp-status`

4. Runtime control (`make/runtime.mk`)
- `make vllm-start`, `make vllm-stop`, `make vllm-restart`
- `make ollama-start`, `make ollama-stop`, `make ollama-restart`

5. Preprod operations (`make/preprod.mk` + root targets)
- `make ensure-preprod-env-file`, `make start-preprod`, `make api-preprod`, `make web-preprod`
- aliases: `make startpre`, `make apipre`, `make webpre`, `make testpre`
- `make preprod-backup`, `make preprod-restore TS=<timestamp>`, `make preprod-verify TS=<timestamp>`
- `make preprod-audit`, `make preprod-drill`, `make preprod-readiness-check`

Internal helper used by preprod wrappers:
- `make ensure-env-file` delegates env file bootstrap to `scripts/dev/ensure_env_file.sh`.

6. Operations and workspace tools (`make/ops.mk`)
- `make modules-status`, `make modules-pull`, `make modules-branches`, `make modules-exec CMD='...'`
- `make runtime-maintenance-cleanup`
- `make runtime-log-policy-audit`, `make runtime-logrotate-install-help`
- `make monitor`

Canonical command list for operators remains available under:
- `make help`

## Monitoring and Logs

- `make status` – reports if processes are alive (PID + ports).
- `logs/` – general backend logs (controlled by `loguru`).
- `web-next/.next/standalone` – build output (not committed).
- `scripts/archive-perf-results.sh` – helper backup of Playwright/pytest/Locust results from `perf-artifacts/` directory.

### Runtime Data/Log Retention Policy

Venom runs an automatic retention cleanup job in `BackgroundScheduler` for runtime files.

- **What is cleaned**: directories from `SETTINGS.RUNTIME_RETENTION_TARGETS` (default: `./logs`, `./data/timelines`, `./data/memory`, `./data/training`, `./data/synthetic_training`, `./data/learning`).
- **Retention period**: `SETTINGS.RUNTIME_RETENTION_DAYS` (default: `7` days).
- **Execution frequency**: one immediate run after app startup + interval from `SETTINGS.RUNTIME_RETENTION_INTERVAL_MINUTES` (default: `1440`, once per day).
- **Feature toggle**: `SETTINGS.ENABLE_RUNTIME_RETENTION_CLEANUP` (default: `True`).
- **Startup guard**: immediate startup run executes only when the last successful retention run is older than the configured interval (prevents repeated cleanup on frequent dev reloads).
- **State marker**: `./.venom_runtime/runtime_retention.last_run` stores the last runtime retention execution timestamp.
- **Safety guard**: git-tracked files are excluded from retention deletion.

Implementation references:
- job function: `venom_core/jobs/scheduler.py` (`cleanup_runtime_files`)
- scheduler registration: `venom_core/main.py` (`cleanup_runtime_files` interval job)
- config defaults: `venom_core/config.py` (runtime retention settings)

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

Example release flow (current stable: `v1.6.0`):
```bash
git checkout main
git pull --ff-only
git tag v1.6.0
git push origin v1.6.0
```

## Post-Deployment Tests

1. **Backend**: `pytest` + `pytest tests/perf/test_chat_pipeline.py -m performance`
2. **Frontend**: `npm --prefix web-next run lint && npm --prefix web-next run build`
3. **E2E Next**: `npm --prefix web-next run test:e2e`
4. **Next chat latency**: `npm --prefix web-next run test:perf`
5. **Locust (optional)**: `./scripts/run-locust.sh` and run scenario from panel (default `http://127.0.0.1:8089`)

## Deployment Checklist

- [ ] `make start-prod` works and returns links to backend and UI (technical compatibility only; not recommended as active prod rollout path yet).
- [ ] Proxy (nginx/docker-compose) redirects `/api` and `/ws` to FastAPI and rest to Next.
- [ ] `npm --prefix web-next run test:e2e` passes on prod build.
- [ ] `npm --prefix web-next run test:perf` shows latency < budget (default 15s).
- [ ] `pytest tests/perf/test_chat_pipeline.py -m performance` passes (SSE task_update → task_finished < 25s).
