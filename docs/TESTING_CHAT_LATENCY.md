# Testing Chat Response Time

This document describes how to measure Venom chat pipeline performance in two areas:

1. **Frontend (UI)** – time from sending prompt to response appearing in Cockpit.
2. **Backend (API/SSE)** – task duration (`task_update` → `task_finished`), parallel scaling and load.

## Requirements
- Running backend (`make start-dev` or `make start-prod`).
- Running Next (`make start-dev` / `make start-prod`).
- Node 18.19+ (Playwright) and Python test environment (`pip install -r requirements.txt` + `pip install locust`).

## Playwright: UI Latency

File: `web-next/tests/perf/chat-latency.spec.ts`
Configuration: `web-next/playwright.perf.config.ts`

```bash
npm --prefix web-next run test:perf
```

Test:
1. Opens Next Cockpit.
2. Sends prompt "benchmark latency".
3. Waits for new response bubble and measures time.
4. Checks budget (default ≤ 15s – configurable values).

Artifacts (screenshots/video) are saved to `web-next/test-results/` and ignored by git.

## Pytest: Backend SSE Pipeline

Files:
- `tests/perf/chat_pipeline.py` – helpers (submit_task, stream_task, measurement).
- `tests/perf/test_chat_pipeline.py` – tests:
  - `test_chat_pipeline_smoke_latency`
  - `test_chat_pipeline_parallel_batch`

Execution:

```bash
pytest tests/perf/test_chat_pipeline.py -m performance
```

Parameters (in file):
- `STREAM_TIMEOUT` – maximum wait time for `task_finished`.
- `PIPELINE_CONCURRENCY` – number of parallel tasks.
- `PIPELINE_BATCH_BUDGET_SECONDS` – budget for slowest task.

## Locust: Load Testing (Manual)

File: `tests/perf/locustfile.py`

Helper script execution:

```bash
./scripts/run-locust.sh
```

Script:
- kills previous instances listening on port 8089,
- starts Locust with `LOCUST_WEB_HOST`/`LOCUST_WEB_PORT` (default `127.0.0.1:8089`),
- informs in log where panel is available.

In panel set number of users, spawn rate, and addresses (default `http://localhost:8000`). `ChatUser` scenario simulates request → SSE.

## Archiving Results

```
./scripts/archive-perf-results.sh
```

Creates `perf-artifacts/<timestamp>/` and copies:
- `test-results/`, `web-next/test-results/`,
- `playwright-report/`,
- Locust logs (`locust.stats.csv`, `locust.failure.csv` if exist).

## Notes
- Repository is local experiment – test artifacts are NOT encrypted, but are ignored (`.gitignore`) and stored locally.
- Performance tests are not yet hooked to CI – we run them manually before release.

## Reference Results (Last Run)
| Date (UTC) | Test | Result |
| --- | --- | --- |
| 2026-01-05 | `tests/perf/chat-latency.spec.ts` (Next Cockpit) | PASS, 4.0s |
| 2026-02-05 | `scripts/perf_check_help.py` (Fast Path Warm) | PASS, ~0.09s |
