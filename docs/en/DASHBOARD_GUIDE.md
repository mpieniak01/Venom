# Venom Dashboard – Launch Instructions

This document describes two frontends:
- **New Next.js (`web-next`)** – default interface with App Router and Playwright smoke.
- **Legacy (`web/` + FastAPI templates)** – preserved for compatibility (last deployments before migration).

Detailed data sources, tests and SCC rules will be documented in the dedicated Frontend Next.js guide (translation in progress).

---

## 1. web-next (Next.js 15)

### 1.1 Requirements
- Node.js 20+
- Running FastAPI backend (`uvicorn main:app …`) – standard on port 8000
- `.env` environment in root directory (backend) + optional frontend variables (`NEXT_PUBLIC_*`)

### 1.2 Installation and Launch

```bash
npm --prefix web-next install          # one-time
npm --prefix web-next run dev          # http://localhost:3000 (proxy to API)
```

Most important frontend environment variables:

```
NEXT_PUBLIC_API_BASE=http://localhost:8000          # when not using built-in proxy
NEXT_PUBLIC_WS_BASE=ws://localhost:8000/ws/events   # telemetry channel
API_PROXY_TARGET=http://localhost:8000              # Next rewriter target (dev)
```

### 1.3 Scripts

| Goal                                 | Command                                              |
|--------------------------------------|------------------------------------------------------|
| Production build                     | `npm --prefix web-next run build`                    |
| Serve build (`next start`)           | `npm --prefix web-next run start`                    |
| Playwright smoke (15 tests)          | `npm --prefix web-next run test:e2e`                 |
| Lint + types                         | `npm --prefix web-next run lint`                     |
| Translation validation               | `npm --prefix web-next run lint:locales`             |

### 1.4 Structure
```
web-next/
├── app/ (Cockpit, Brain, Inspector, Strategy – server components)
├── components/ (layout, UI, overlays)
├── hooks/ (use-api.ts, use-telemetry.ts)
├── lib/ (i18n, formatters, api-client, app-meta)
├── scripts/ (generate-meta.mjs, prepare-standalone.mjs)
└── tests/ (Playwright smoke)
```

### 1.5 Differences from Legacy
- Interface uses `useTranslation` (PL/EN/DE) and SCC – client components have `"use client"`.
- Real-time updates implemented by `usePolling` (fetch + refresh) and WebSocket (`useTelemetryFeed`).
- Bottom status bar and TopBar overlays have `data-testid`, enabling stable E2E tests.
- Build generates `public/meta.json` (version + commit) – used for environment verification in UI.
- Inspector available in `web-next` (`/inspector`) and renders Mermaid flows with zoom/pan.

### 1.6 Cockpit – Operational Panel
Most important blocks in Cockpit (web-next):
- **LLM Servers** – runtime selection (Ollama/vLLM), model list for selected runtime, model activation.
- **Slash commands** – `/gpt`, `/gem`, `/<tool>` with autocomplete, forced routing and "Forced" badge.
- **Response language** – PL/EN/DE UI setting is passed to backend and used for result translation.
- **User feedback** – thumbs up/down on response, feedback logs and quality metrics (👍/👎).
- **Hidden prompts** – aggregation, filtering and activation of approved responses.
- **Learning logs** – preview of LLM-only records from `data/learning/requests.jsonl`.

---

## 2. Legacy Dashboard (`web/`)

Venom Cockpit is a dashboard for real-time monitoring and controlling Venom system.
Dashboard offers:
- **Live Feed**: Real-time system event stream via WebSocket
- **Chat Console**: Interface for sending tasks directly from browser
- **Task Monitor**: List of active tasks with their status
- **Metrics**: System performance metrics (task count, success rate, uptime)

## Requirements

- Python 3.10+
- Dependencies installed from `requirements.txt`
- Port 8000 available for server

## Launch

### 2.1 Dependency Installation

```bash
pip install -r requirements.txt
```

### 2.2 Configuration (optional)

Create `.env` file in project root directory:

```env
LLM_SERVICE_TYPE=local
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1
LLM_MODEL_NAME=phi3:latest
```

### 2.3 Server Launch

```bash
cd venom_core
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2.4 Opening Dashboard

Open browser and go to:
```
http://localhost:8000
```

## Appendix – Structure (legacy)

```
venom_core/
├── api/
│   ├── __init__.py
│   └── stream.py              # WebSocket server and EventBroadcaster
├── core/
│   ├── metrics.py             # Metrics system
│   ├── orchestrator.py        # Modified orchestrator with broadcasting
│   └── dispatcher.py          # Dispatcher with event broadcasting
├── agents/
│   └── architect.py           # Architect agent with event broadcasting
└── main.py                    # FastAPI app with WebSocket and static files

web/
├── templates/
│   └── index.html             # Main dashboard template
└── static/
    ├── css/
    │   └── app.css            # Dashboard styles
    └── js/
        └── app.js             # JavaScript: WebSocket client, UI logic
```

## API Endpoints

### REST API

- `GET /` - Dashboard UI
- `GET /healthz` - Health check
- `POST /api/v1/tasks` - Create new task
- `GET /api/v1/tasks` - List all tasks
- `GET /api/v1/tasks/{task_id}` - Task details
- `GET /api/v1/metrics` - System metrics

### WebSocket

- `WS /ws/events` - WebSocket endpoint for event streaming

## WebSocket Event Types

Dashboard receives following event types:

- `TASK_CREATED` - New task created
- `TASK_STARTED` - Task processing started
- `TASK_COMPLETED` - Task completed successfully
- `TASK_FAILED` - Task failed
- `PLAN_CREATED` - Architect created plan
- `PLAN_STEP_STARTED` - Plan step started
- `PLAN_STEP_COMPLETED` - Plan step completed
- `AGENT_ACTION` - Agent executing action
- `AGENT_THOUGHT` - Agent "thought"
- `SYSTEM_LOG` - System log

## Testing (legacy)

### Manual Test

1. Run server according to instructions above
2. Open dashboard in browser
3. Check connection status (green dot in top right corner)
4. Enter sample task, e.g.:
   ```
   Do research about Python 3.12
   ```
5. Observe:
   - Live Feed: Logs appearing in real-time
   - Task Monitor: New task with its status
   - Chat Console: Response from agent
   - Metrics: Counter updates

### Automated Test

```bash
pytest tests/test_dashboard_api.py -v
```

## Troubleshooting (legacy)

### WebSocket Won't Connect

- Check if server is running
- Check if port 8000 isn't blocked by firewall
- Check browser console (F12) for errors

### Dashboard Won't Load

- Check if `web/` directory exists and contains files
- Check server logs for StaticFiles mounting errors

### Metrics Don't Update

- Check `/api/v1/metrics` endpoint manually in browser
- Check if tasks are created correctly

## Development

### Adding New Event Types

1. Add event type to `EventType` in `venom_core/api/stream.py`
2. Call `event_broadcaster.broadcast_event()` in appropriate place
3. Handle event in `web/static/js/app.js` in `handleWebSocketMessage()` method

### Modifying UI

- Edit `web/templates/index.html` for HTML structure
- Edit `web/static/css/app.css` for styles
- Edit `web/static/js/app.js` for JavaScript logic

## License

Part of Venom Meta-Intelligence project
