# Venom Dashboard – Launch Instructions

This document describes the Next.js dashboard (`web-next`).

Detailed data sources, tests and SCC rules will be documented in the dedicated Frontend Next.js guide (translation in progress).

---

## 1. web-next (Next.js 16)

### 1.1 Requirements
- Node.js 20+
- Running FastAPI backend (`uvicorn main:app …`) – standard on port 8000
- `.env` environment in root directory (backend) + optional frontend variables (`NEXT_PUBLIC_*`)

### 1.2 Installation and Launch

```bash
npm --prefix web-next install          # one-time
npm --prefix web-next run dev          # http://localhost:3000 (proxy to API)
npm --prefix web-next run dev:turbo    # optional Turbopack mode
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
| Turbopack smoke regression           | `npm --prefix web-next run test:dev:turbo:smoke:clean` |
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

### 1.5 Notes
- Interface uses `useTranslation` (PL/EN/DE) and SCC – client components have `"use client"`.
- Real-time updates implemented by `usePolling` (fetch + refresh) and WebSocket (`useTelemetryFeed`).
- Bottom status bar and TopBar overlays have `data-testid`, enabling stable E2E tests.
- Build generates `public/meta.json` (version + commit) – used for environment verification in UI.
- Inspector available in `web-next` (`/inspector`) and renders Mermaid flows with zoom/pan.

### 1.6 Cockpit – Operational Panel
Most important blocks in Cockpit (web-next):
- **LLM Servers** – runtime selection (Ollama/vLLM/ONNX), model list for selected runtime, model activation.
- **Slash commands** – `/gpt`, `/gem`, `/<tool>` with autocomplete, forced routing and "Forced" badge.
- **Response language** – PL/EN/DE UI setting is passed to backend and used for result translation.
- **User feedback** – thumbs up/down on response, feedback logs and quality metrics (👍/👎).
- **Hidden prompts** – aggregation, filtering and activation of approved responses.
- **Learning logs** – preview of LLM-only records from `data/learning/requests.jsonl`.

### 1.7 Tools Quickstart
- See [TOOLS_USAGE_GUIDE.md](TOOLS_USAGE_GUIDE.md) for current slash-tool mapping, `forced_tool` routing behavior, and required web-search dependencies in `.venv`.

---

## License

Part of Venom Meta-Intelligence project
