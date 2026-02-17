# Configuration and Stack Control Panel (TASK 060 + 084)

## Overview

Configuration panel available at `/config` in web-next interface allows:
- Managing Venom services (start, stop, restart)
- Editing configuration parameters from UI
- Monitoring service status (CPU, RAM, uptime)
- Applying quick profiles (Full Stack, Light, LLM OFF)
- **Distinguishing controllable services from configurable ones** (TASK 084)

## Architecture

### Backend

#### Runtime Controller (`venom_core/services/runtime_controller.py`)
Manages Venom process lifecycle:
- **Status detection**: Scans PID files (`.venom.pid`, `.web-next.pid`) and system processes
- **Metrics**: Retrieves CPU/RAM using `psutil`
- **Actions**: Start/stop/restart for each service
- **History**: Stores last 100 actions
- **`actionable` field**: Distinguishes services with real actions from those controlled by configuration

**Supported services:**

**Controllable services (actionable=true):**
- `backend` (Backend API – FastAPI/uvicorn) – controlled via `make start-dev` / `make stop`
- `ui` (Next.js UI – dev/prod) – controlled via make, together with backend
- `llm_ollama` (Ollama) – controlled via env commands (`OLLAMA_START_COMMAND`, `OLLAMA_STOP_COMMAND`)
- `llm_vllm` (vLLM) – controlled via env commands (`VLLM_START_COMMAND`, `VLLM_STOP_COMMAND`)

**Configurable services (actionable=false):**
- `hive` (distributed processing) – controlled by `ENABLE_HIVE` flag in configuration
- `nexus` (mesh/cooperation) – controlled by `ENABLE_NEXUS` flag in configuration
- `background_tasks` (background workers) – controlled by `VENOM_PAUSE_BACKGROUND_TASKS` flag

**Monitored services (actionable=false, with ServiceMonitor):**
- LanceDB (embedded vector memory) – health check only, no start/stop
- Redis (broker/locks) – external service, health check only
- Docker Daemon (sandbox) – system service, health check only

**Profiles:**
- `full` - Starts backend, UI and Ollama
- `light` - Starts backend, UI and Ollama (Gemma), without vLLM
- `llm_off` - Backend and UI without local LLM runtime; external API providers (for example OpenAI/Gemini) remain available after key configuration

#### Config Manager (`venom_core/services/config_manager.py`)
Manages `.env` file:
- **Whitelist**: 55 parameters available for UI editing
- **Validation**: Pydantic models verify data correctness
- **Backup**: Each change creates backup in `config/env-history/.env-YYYYMMDD-HHMMSS`
- **Restart tracking**: Determines which services require restart after change

**Parameter whitelist:**
- AI Configuration: `AI_MODE`, `LLM_SERVICE_TYPE`, `LLM_LOCAL_ENDPOINT`, API keys
- Generation parameters (per runtime/model): `MODEL_GENERATION_OVERRIDES` (JSON)
- Hive: `ENABLE_HIVE`, `REDIS_HOST`, `REDIS_PORT`
- Nexus: `ENABLE_NEXUS`, `NEXUS_PORT`, `NEXUS_SHARED_TOKEN`
- Background Tasks: `ENABLE_AUTO_DOCUMENTATION`, `ENABLE_AUTO_GARDENING`
- Agents: `ENABLE_GHOST_AGENT`, `ENABLE_DESKTOP_SENSOR`, `ENABLE_AUDIO_INTERFACE`

> **Security Note:** LLM runtime start/stop commands (e.g., `VLLM_START_COMMAND`, `OLLAMA_START_COMMAND`) are **not** editable from the configuration panel for security reasons. These commands are configured outside the UI to prevent potential command injection vulnerabilities.

**Secret masking:**
Parameters containing "KEY", "TOKEN", "PASSWORD" are masked in format: `sk-****1234` (first 4 and last 4 characters)

#### API Endpoints (`venom_core/api/routes/system.py`)

**Runtime:**
```
GET  /api/v1/runtime/status
     → {services: [{name, status, pid, port, cpu_percent, memory_mb, uptime_seconds, last_log, actionable, endpoint?, latency_ms?}]}

     'actionable' field determines if service has real start/stop/restart actions:
     - true: controllable services (backend, ui, llm_ollama, llm_vllm)
     - false: services controlled by configuration or only monitored (hive, nexus, background_tasks, Redis, Docker, LanceDB)

POST /api/v1/runtime/{service}/{action}
     service: backend|ui|llm_ollama|llm_vllm|hive|nexus|background_tasks
     action: start|stop|restart
     → {success: bool, message: str}

     Note: For services with actionable=false (hive, nexus, background_tasks) actions return
     "controlled by configuration" message without executing real operation.

GET  /api/v1/runtime/history?limit=50
     → {history: [{timestamp, service, action, success, message}]}

POST /api/v1/runtime/profile/{profile_name}
     profile_name: full|light|llm_off
     → {success: bool, message: str, results: [...]}
```

**Configuration:**
```
GET  /api/v1/config/runtime?mask_secrets=true
     → {config: {KEY: "value", ...}}

     Note: Secret masking is enforced server-side. In production deployments,
     this endpoint should be protected with authentication to prevent
     unauthorized access to configuration data.

POST /api/v1/config/runtime
     body: {updates: {KEY: "new_value", ...}}
     → {success: bool, message: str, restart_required: [services], changed_keys: [...], backup_path: str}

     Note: In production deployments, this endpoint should require authentication
     and authorization to prevent unauthorized configuration changes.

GET  /api/v1/config/backups?limit=20
     → {backups: [{filename, path, size_bytes, created_at}]}

POST /api/v1/config/restore
     body: {backup_filename: ".env-20240101-120000"}
     → {success: bool, message: str, restart_required: [...]}
```

### Frontend

#### Component Structure
```
web-next/
├── app/config/page.tsx              # Main configuration page
├── components/config/
│   ├── config-home.tsx              # Main component with tabs
│   ├── services-panel.tsx           # Services panel (tiles, actions, profiles)
│   └── parameters-panel.tsx         # Parameters panel (forms, sections)
└── lib/i18n/locales/
    ├── pl.ts                        # Polish translations
    ├── en.ts                        # English translations
    └── de.ts                        # German translations
```

#### ServicesPanel (`components/config/services-panel.tsx`)
- **Auto-refresh**: Fetches status every 5 seconds
- **Service tiles**: Displays live status, PID, port, CPU, RAM, uptime, last log
- **Conditional actions**: Start/stop/restart buttons only for services with `actionable=true`
- **Non-actionable services**: Info badge "Controlled by configuration" instead of buttons
- **Quick profiles**: 3 buttons (Full Stack, Light, LLM OFF)
- **Action history**: Last 10 actions with timestamp
- **Feedback**: Success/error messages in banner form

**Service type distinction in UI:**
- **Controllable (actionable=true)**: Full set of Start/Stop/Restart buttons
- **Configurable (actionable=false)**: Info badge "Controlled by configuration" - status change requires parameter editing in "Parameters" tab
- **Monitored (actionable=false, with ServiceMonitor)**: Info badge + possible latency/endpoint - status read-only

#### ParametersPanel (`components/config/parameters-panel.tsx`)
- **Sections**: 8 configuration sections (AI, Commands, Hive, Nexus, Tasks, Shadow, Ghost, Avatar)
- **Masking**: Automatic masking of secret fields with "show" button
- **Validation**: Checking filled fields before save
- **Sticky footer**: Action panel always visible at bottom of screen
- **Restart warnings**: Banner with list of services requiring restart after save
- **Info box**: Informational section about Ollama vs vLLM with link to benchmarks

#### Navigation
Sidebar contains new "Configuration" item with Settings icon:
- Polish: "Konfiguracja"
- English: "Configuration"
- German: "Konfiguration"

## Security

### Parameter Whitelist
Only 55 parameters are available for editing. List is defined in `CONFIG_WHITELIST` in `config_manager.py`. Attempt to edit other parameters returns validation error.

### Secret Masking
Parameters containing sensitive data are masked:
- `OPENAI_API_KEY` → `sk-****1234`
- `GOOGLE_API_KEY` → `AI****5678`
- `NEXUS_SHARED_TOKEN` → `tok_****abcd`
- `REDIS_PASSWORD` → `****`

### Automatic Backup
Each `.env` change creates backup in `config/env-history/`:
```
config/env-history/
├── .env-20241218-094500
├── .env-20241218-101230
└── .env-20241218-143045
```

System keeps last 50 backups. Older ones are automatically removed.

### Restart Control
After saving configuration, backend returns list of services requiring restart:
- Changes in `AI_MODE`, `LLM_SERVICE_TYPE` → restart `backend`
- Changes in `ENABLE_HIVE` → restart `backend`
- Changes in LLM commands → no restart (commands used at next start/stop)

UI displays warning with service list and CTA to "Services" tab.

## Usage

### Starting Services
1. Go to `/config`
2. Click "Services" tab
3. Select service (e.g., backend)
4. Click "Start"
5. Status changes to "running", CPU/RAM metrics displayed

### Applying Profile
1. In "Services" tab click one of profiles:
   - **Full Stack**: Starts backend, UI, Ollama
   - **Light**: Starts backend, UI, Ollama (Gemma), without vLLM
   - **LLM OFF**: Starts backend, UI, stops local LLM runtime (external API providers can still be used if configured)
2. System executes actions for all services in profile
3. Banner shows operation result

### Editing Parameters
1. Go to "Parameters" tab
2. Find section (e.g., "AI Mode")
3. Change field values (e.g., `AI_MODE` to "HYBRID")
4. Click "Save configuration" in bottom panel
5. System:
   - Creates `.env` backup
   - Saves changes
   - Displays success banner
   - Shows restart requirements warning

### Restoring Backup
1. API endpoint `/api/v1/config/backups` returns backup list
2. POST to `/api/v1/config/restore` restores selected backup
3. Current `.env` is saved as new backup before restoration

## LLM Modes: Ollama vs vLLM

Panel contains informational section explaining differences:

**Ollama (Light):**
- Priority: shortest question→answer time
- Low memory footprint
- Single user, ideal for daily work
- Quick start (~3 seconds)

**vLLM (Full):**
- Benchmark pipeline
- Longer start (~5-10 seconds)
- Reserves full VRAM
- Higher throughput for multiple requests
- Better for performance tests

**Recommendation:**
By default we run only one runtime at a time. Second runtime makes sense when separating roles (e.g., UI on Ollama, coding agent on vLLM). Full selection strategy should be based on benchmark results → link to `/benchmark`.

## Tests

### Backend (pytest)
```bash
pytest tests/test_runtime_controller_api.py -v
pytest tests/test_config_manager_api.py -v
```

**Coverage:**
- Runtime status (GET /api/v1/runtime/status)
- Service actions (POST /api/v1/runtime/{service}/{action})
- Runtime history (GET /api/v1/runtime/history)
- Runtime profiles (POST /api/v1/runtime/profile/{profile})
- Config get/update (GET/POST /api/v1/config/runtime)
- Config backups (GET /api/v1/config/backups)
- Config restore (POST /api/v1/config/restore)
- Edge cases (invalid service, invalid action, validation errors)

### Frontend (Playwright)
TODO: Add E2E scenarios:
- Navigation to `/config`
- Service status change (start/stop)
- Profile application
- Parameter edit and save
- Secret mask/unmask
- Restart warnings display

## Troubleshooting

### Service Won't Start
**Problem**: Clicking "Start" doesn't change status to "running"

**Solution:**
1. Check logs in service tile ("Last log" field)
2. Check PID file:
   - Backend: `.venom.pid`
   - UI: `.web-next.pid`
3. Check port (if not occupied):
   ```bash
   lsof -ti tcp:8000  # Backend
   lsof -ti tcp:3000  # UI
   ```
4. Check LLM commands in `.env`:
   - `OLLAMA_START_COMMAND`
   - `VLLM_START_COMMAND`

### Configuration Changes Not Visible
**Problem**: After saving parameters backend doesn't see new values

**Solution:**
1. Check if `.env` was updated:
   ```bash
   grep AI_MODE .env
   ```
2. Check backup in `config/env-history/`
3. Restart backend ("Services" tab → backend → Restart)
4. Backend loads `.env` only at startup

### Error "Invalid level: X"
**Problem**: Attempt to save unknown parameter

**Solution:**
1. Check if key is on whitelist (`CONFIG_WHITELIST` in `config_manager.py`)
2. If parameter is needed, add it to whitelist and `RESTART_REQUIREMENTS`

### Port Occupied
**Problem**: Service can't start because port is occupied

**Solution:**
```bash
# Find process occupying port
lsof -ti tcp:8000

# Kill process
kill <PID>

# Or use make clean-ports
make clean-ports
```

## Roadmap

### Completed (v1.0)
- [x] Backend runtime controller with support for 7 service types
- [x] Backend config manager with 55 parameter whitelist
- [x] API endpoints for runtime and config
- [x] Frontend panels: Services and Parameters
- [x] Quick profiles (Full/Light/LLM OFF)
- [x] Secret masking
- [x] .env backup with history
- [x] Restart warnings
- [x] Backend unit tests

### TODO (v1.1)
- [ ] Playwright E2E tests
- [ ] Docker compose integration (optional)
- [ ] Remote nodes control (Hive/Nexus)
- [ ] Logs viewer (tail -f in UI panel)
- [ ] CPU/RAM alerts (threshold warnings)
- [ ] Service dependencies graph
- [ ] Configuration export/import

### TODO (v2.0)
- [ ] Multi-user access control (role-based)
- [ ] Audit log (who, when, what changed)
- [ ] Config templates (dev/prod/test)
- [ ] One-click deployment profiles
- [ ] Health checks and auto-restart
- [ ] Integration with systemd/supervisord

## API Documentation

Full API documentation available in Swagger UI after running backend:
```
http://localhost:8000/docs
```

Sections:
- **Runtime** → `/api/v1/runtime/*`
- **Config** → `/api/v1/config/*`

## License

According to Venom project license.
