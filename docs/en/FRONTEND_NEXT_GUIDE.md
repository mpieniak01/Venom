# FRONTEND NEXT – ARCHITECTURE AND CHECKLIST

This document extends `docs/DASHBOARD_GUIDE.md` with information specific to the `web-next` version. Contains:
1. Architecture and Next.js directories (App Router, SCC – Server/Client Components) and environment configuration.
2. Description of data sources used by key views (Brain, Strategy, Cockpit) – including fallbacks.
3. Manual and Playwright test checklist confirming functional readiness.
4. Entry criteria for **Stage 29** and list of elements still considered "legacy".

---

## 0. Stack and `web-next` structure

### 0.1 Directories
```
web-next/
├── app/                    # App Router, server components (`page.tsx`, layouts, route handlers)
│   ├── page.tsx            # Cockpit
│   ├── chat/page.tsx       # Cockpit reference (full layout)
│   ├── brain/page.tsx      # Brain view
│   ├── inspector/page.tsx  # Flow Inspector
│   ├── strategy/page.tsx   # Strategy / KPI (v2.0 - Hidden)
│   └── config/page.tsx     # Configuration Panel (Task 060)
├── components/             # Shared components (layout, UI, overlays)
├── hooks/                  # Data hooks (`use-api.ts`, `use-telemetry.ts`)
├── lib/                    # Utilities (i18n, formatters, API client)
├── public/                 # Static assets (`meta.json`)
├── scripts/                # Build tools (`generate-meta.mjs`, `prepare-standalone.mjs`)
└── tests/                  # Playwright (smoke suite)
```

### 0.2 SCC – principles (Server / Client Components)
- By default, components in `app/*` are server-side – we don't add `"use client"` if we don't need to.
- Interactive components (chat, bars, overlays) declare `"use client"` and use React hooks.
- `components/layout/*` is mixed: e.g. `SystemStatusBar` is client-side (real-time updates), while Brain/Strategy sections remain server-side with lazy-hydration only where necessary.
- We reuse styles through tokens (`surface-card`, `glass-panel` etc.) in `globals.css`.
- **Naming conventions:** all interfaces/types in `web-next/lib/types.ts` use English names (`Lesson`, `LessonsStats`, `ServiceStatus`, `Task`, `Metrics`, `ModelsUsageResponse`). We don't add parallel PL aliases or import shortcuts – instead of `Lekcja` we use `Lesson`, instead of `StatusSłużba` → `ServiceStatus`. UI translations live in `lib/i18n`, but code/types maintain a uniform English prefix to avoid convention drift when adding new modules.

### 0.3 NPM scripts / workflow
| Command                               | Purpose                                                                               |
|---------------------------------------|---------------------------------------------------------------------------------------|
| `npm --prefix web-next install`       | Install dependencies                                                                 |
| `npm --prefix web-next run dev`       | Dev server (Next 15) with automatic meta generation (`predev → generate-meta.mjs`)   |
| `npm --prefix web-next run build`     | Prod build, generates `public/meta.json` and standalone `.next/standalone`           |
| `npm --prefix web-next run test:e2e`  | Playwright smoke in prod mode (15 Cockpit + bars scenarios)                          |
| `npm --prefix web-next run lint`      | Next lint (ESLint 9)                                                                 |
| `npm --prefix web-next run lint:locales` | Validate i18n dictionary consistency (`scripts/check-locales.ts`)                  |

### 0.4 Configuration and proxy
- Backend FastAPI listens on port 8000 by default – frontend connects via Next *rewrites* (see `next.config.mjs`) or via variables:
  - `NEXT_PUBLIC_API_BASE` – base `/api/v1/*` (when running dashboard in standalone mode)
  - `NEXT_PUBLIC_WS_BASE` – WebSocket telemetry (`ws://localhost:8000/ws/events`)
  - `API_PROXY_TARGET` – direct backend URL; Next builds rewriter, so no code modification needed in dev mode.
- `scripts/generate-meta.mjs` saves `public/meta.json` with `version`, `commit`, `timestamp`. Data consumed by bottom status bar.

### 0.5 Loading optimizations (task 054)
- `lib/server-data.ts` performs SSR-prefetch of critical endpoints (`/api/v1/metrics`, `/queue/status`, `/tasks`, `/models/usage`, `/metrics/tokens`, `/git/status`). Layout passes them to `TopBar` (`StatusPills`) and `SystemStatusBar` as `initialData`, so on first render no empty dashes are visible.
- `StatusPills` and bottom bar work in "stale-while-revalidate" mode: show SSR data, and `usePolling` hook fetches update after mounting (spinners appear only if we have no snapshot).
- `/strategy` has local `sessionStorage` cache (`strategy-roadmap-cache`, `strategy-status-report`). Roadmap is presented immediately on entry, and status report fetches automatically in background if previous snapshot is older than 60 seconds. Cache doesn't block manual "Status report" – click forces new request.
- `next.config.ts` has enabled `experimental.optimizePackageImports` for `lucide-react`, `framer-motion`, `chart.js`, `mermaid`, which trims JS "first load" and accelerates dynamic icon/animation imports.
- Cockpit and Brain use server wrappers (`app/page.tsx`, `app/brain/page.tsx`) that fetch data snapshot via `fetchCockpitInitialData` / `fetchBrainInitialData`. Client components (`components/cockpit/cockpit-home.tsx`, `components/brain/brain-home.tsx`) combine these snapshots with `usePolling` hooks, so KPIs, model list, lessons and graph show last state already after SSR and only fetch updates after hydration.
- Command Console (chat) has optimistic UI: `optimisticRequests` render user bubbles + response placeholder before API return, block opening details until synchronized with `useHistory`, and `ConversationBubble` shows spinner and reports last response time in header.
- Command Console handles slash commands (`/gpt`, `/gem`, `/<tool>`) with autocomplete (max 3 suggestions) and "Forced" badge in response.
- UI language (PL/EN/DE) is sent as `preferred_language` in `/api/v1/tasks` and backend translates response if different language detected.
- Calculation results (e.g. JSON/arrays) are formatted in chat to tables/lists; when formulas detected we render KaTeX.

## 1. Brain / Strategy – Data sources and hooks

| View / module                     | Endpoints / hooks                                                                                              | Fallback / notes                                                                                           |
|----------------------------------|----------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| **Brain** – Mind Mesh            | `useKnowledgeGraph` → `/api/v1/graph/summary`, `/api/v1/graph/scan`, `/api/v1/graph/file`, `/api/v1/graph/impact` | On HTTP error renders `OverlayFallback` and blocks actions (scan/upload).                                  |
| **Brain** – Lessons & stats      | `useLessons`, `useLessonsStats`, `LessonActions` (tags), `FileAnalysisForm`                                     | No data displays `EmptyState` with CTA "Refresh lessons".                                                  |
| **Brain** – Graph controls       | `GraphFilterButtons`, `GraphActionButtons` + `useGraphSummary`                                                 | Offline versions (e.g. no `/api/v1/graph/summary`) show `offline` badge in BrainMetricCard cards.         |
### Strategy (Postponed to v2.0)

> [!NOTE]
> **Postponed to v2.0:** The Strategy screen and its associated features (Vision, KPI, Roadmap) have been postponed to Venom v2.0. The code remains in `app/strategy` but is hidden from navigation in v1.0.

| **Strategy** – KPI / Vision      | `useRoadmap` (`/api/v1/roadmap`), `requestRoadmapStatus`, `createRoadmap`, `startCampaign`                      | All actions wrapped in `useToast`; on 4xx/5xx panel displays `OverlayFallback`.                            |
| **Strategy** – Milestones/Tasks  | `RoadmapKpiCard`, `TaskStatusBreakdown` (uses `/api/v1/roadmap` and `/api/v1/tasks` for statuses)              | No tasks → message "No defined milestones" (EmptyState).                                                    |
| **Strategy** – Campaigns         | `handleStartCampaign` asks `window.confirm` (like legacy), then sends `/api/campaign/start`.                   | On missing API informs user via toast and doesn't change local state.                                       |
| **Config** – Services            | `/api/v1/runtime/status`, `/api/v1/runtime/{service}/{action}`, `/api/v1/runtime/profile/{profile}`            | Displays live service status (backend, UI, LLM, Hive, Nexus) with CPU/RAM metrics. Start/stop/restart actions. |
| **Config** – Parameters          | `/api/v1/config/runtime` (GET/POST), `/api/v1/config/backups`, `/api/v1/config/restore`                        | Edit whitelisted parameters from `.env`, mask secrets, backup to `config/env-history/`, restart warnings.    |

> **Note:** all hooks use `lib/api-client.ts`, which automatically retrieves base URL from `NEXT_PUBLIC_API_BASE` or Next rewrites. This allows UI to work on both HTTP and HTTPS without manual configuration.

---

## 1.1 Configuration Panel – Stack management (Task 060)

### Goal
Configuration panel (`/config`) allows managing Venom services (backend, UI, LLM, distributed modules) and editing key parameters from UI, without manual `.env` editing.

### Functionality

#### "Services" Panel
- **Status tiles**: Each service (backend, ui, llm_ollama, llm_vllm, hive, nexus, background_tasks) shows:
  - Status (running/stopped/error)
  - PID and port
  - CPU and RAM
  - Uptime
  - Last log
- **Actions**: Start/stop/restart buttons for each service
- **Quick profiles**:
  - **Full Stack**: Starts all services
  - **Light**: Only backend and UI (no LLM)
  - **LLM OFF**: Backend and UI, disables language models
- **Action history**: List of last 10 actions with timestamp

#### "Parameters" Panel
- **Configuration sections**:
  - AI mode (AI_MODE, LLM_SERVICE_TYPE, model endpoints, API keys)
  - LLM server commands (VLLM_START_COMMAND, OLLAMA_START_COMMAND)
  - Hive – distributed processing (ENABLE_HIVE, Redis config)
  - Nexus – distributed mesh (ENABLE_NEXUS, port, token)
  - Background tasks (auto-documentation, gardening, memory consolidation)
  - Shadow Agent (desktop awareness)
  - Ghost Agent (GUI automation)
  - Avatar (audio interface)
- **Secret masking**: API keys and tokens are masked by default, "show" button reveals value
- **Validation**: Frontend checks value presence, backend validates whitelist
- **Backup**: Each save creates `.env` backup in `config/env-history/.env-YYYYMMDD-HHMMSS`
- **Restart warnings**: After save UI informs which components require restart

#### Info Box: Ollama vs vLLM
Panel contains informational section explaining differences between LLM runtimes:
- **Ollama (Light)**: Quick start, low footprint, single user
- **vLLM (Full)**: Longer start, higher VRAM, benchmarks and performance tests
- Link to `/benchmark` with suggestion to compare models

### Backend API

#### Runtime Controller
```
GET  /api/v1/runtime/status            # Service list with status, PID, CPU/RAM
POST /api/v1/runtime/{service}/{action} # start/stop/restart (service: backend, ui, llm_ollama, etc.)
GET  /api/v1/runtime/history           # Action history (limit 50)
POST /api/v1/runtime/profile/{name}    # Apply profile (full, light, llm_off)
```

#### Config Manager
```
GET  /api/v1/config/runtime            # Fetch whitelisted parameters (mask_secrets=true)
POST /api/v1/config/runtime            # Save changes (updates: {key: value})
GET  /api/v1/config/backups            # List .env backups
POST /api/v1/config/restore            # Restore backup (backup_filename)
```

### Security
- **Parameter whitelist**: Only selected parameters (55 keys) are editable via UI
- **Secret masking**: Fields containing "KEY", "TOKEN", "PASSWORD" are masked
- **Automatic backup**: Every `.env` change creates backup copy
- **Restart notification**: UI informs which services require restart after configuration change

### Tests
- Backend: `tests/test_runtime_controller_api.py`, `tests/test_config_manager_api.py`
- Frontend: TODO – Playwright scenarios for navigation, start/stop, parameter editing

---

## 2. Tests – Brain / Strategy (manual + Playwright)

### 2.1 Manual smoke (after each release)
1. **Brain**
   - `Scan graph` returns spinner and new log in "Recent graph operations".
   - Click on node opens panel with relations, tags and actions (file impact, lessons).
2. **Strategy**
   - Refresh roadmap (`refreshRoadmap`) and check that KPI/Milestones show API data.
   - `Start campaign` → confirm prompt → success/error message + log in toasts.

### 2.2 Playwright (to be added / extended)
| Scenario name                       | Input / expectations                                                                  |
|-------------------------------------|----------------------------------------------------------------------------------------|
| `brain-can-open-node-details`       | `page.goto("/brain")`, click first node (seed data) → details panel visible          |
| `strategy-campaign-confirmation`    | Open `/strategy`, click "Start campaign", check confirm + offline message             |
| `strategy-kpi-offline-fallback`     | With backend disabled visible `OverlayFallback` + text "No data".                     |

> TODO: add above scenarios to `web-next/tests/smoke.spec.ts` after stabilizing CI. Document will be updated with PR adding tests.

---

## 3. Block map → stage 29

### 3.1 Checklist "legacy vs. next"
- [x] Sidebar / TopBar – use glass tokens and shared components.
- [x] Cockpit – hero, command console, macros, models, repo → all in `_szablon.html` style.
- [x] Brain / Strategy – described above.
- [ ] Inspector – missing manual "Refresh" + JSON panel (task 051, section 6).
- [ ] Strategy KPI timeline – requires real data from `/api/v1/tasks` (task 051, section 6.3).

### 3.2 Entry criteria for **Stage 29**
1. **Functional parity** – each legacy view has counterpart in `web-next`; no duplicate panels.
2. **Shared components** – all lists/histories use `HistoryList`/`TaskStatusBreakdown`.
3. **Tests** – Playwright covers Cockpit, Brain, Inspector, Strategy + critical overlays.
4. **Documentation** – this file + README have data sources and tests section.
5. **QA** – note list from task 051 (sections 4–7) marked as ✅.

After meeting above points, can officially close stage 28 and move to 29 (e.g. performance optimizations, UI A/B tests).
