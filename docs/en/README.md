# Venom v1.0 🐍

**Venom desktop version – meta-intelligence system** - Autonomous AI agent system with strategic planning layer and knowledge expansion.

> **[Polska Wersja](../../README.md)**

Venom is being transformed from a simple command executor into an **autonomous engineer** capable of:

### ✨ Key Features
- 🎨 Creating new tools and self-repair
- 🔌 **MCP Tools Import** - Model Context Protocol integration (Git import)
- 🌐 **Internet Access** - Searching for current information (prices, news, documentation)
- 🧠 **Strategic Planning** - Automatic decomposition of complex projects into steps
- 📚 **Knowledge Synthesis** - Collecting and analyzing documentation from multiple sources
- 🤖 **Agent Management** - Coordination of multiple specialized agents
- 💾 **Long-term Memory** - Saving and utilizing acquired knowledge
- 🎓 **Learning by Observation** - Recording demonstrations and automatic workflow generation (NEW!)
- 👍👎 **Quality Loop** - User feedback + logs and response quality metrics
- 🧠 **Hidden Prompts** - Approved responses as context shortcuts
- 🧭 **LLM Runtime Selection** - Ollama/vLLM + active model controlled from panel
- 💬 **Chat Continuity** - Consistent session history per `session_id` (SessionStore) with reset after backend restart
- 🗺️ **Memory Visualization** - Memory layer (LessonsStore + LanceDB) in `/brain` view, with session/pinned filtering and pin/delete actions
- 🛠️ **Services Panel** - `/config` shows real-time statuses of local stack (Backend API, Next.js UI, Ollama, vLLM, LanceDB, Redis, Docker) + Full/Light/LLM OFF profiles

### 🎯 Usage Examples

```python
# 1. Searching for current information
"What is the current price of Bitcoin?"
→ System automatically searches the Internet and returns fresh data

# 2. Complex projects with planning
"Create a Snake game using PyGame"
→ System:
  1. Will find PyGame documentation (ResearcherAgent)
  2. Will create game structure (CoderAgent)
  3. Add snake logic (CoderAgent)
  4. Implement scoring (CoderAgent)

# 3. Web page with multiple files
"Create an HTML page with digital clock and CSS styling"
→ System will create separately: index.html, style.css, script.js

# 4. NEW: Learning by demonstration
"Venom, watch how I send a report to Slack"
→ [User performs actions]
→ System records, analyzes and generates workflow
→ "Saved as skill 'send_slack_report'"
→ Later: "Venom, send report to Slack" - executes automatically!
```

## 🏗️ Architecture

### Project Structure
```
venom_core/
├── api/routes/          # REST API endpoints (agents, tasks, memory, nodes)
├── core/flows/          # Business flows and orchestration
├── agents/              # Specialized AI agents
├── execution/           # Execution layer and model routing
├── perception/          # Perception (desktop_sensor, audio)
├── memory/              # Long-term memory (vectors, graph, workflows)
└── infrastructure/      # Infrastructure (hardware, cloud, message broker)
```

### Main Components

#### 1. **Strategic Layer** (Planning)
- **ArchitectAgent** - Project manager, breaks down complex tasks into steps
- **ExecutionPlan** - Execution plan model with defined steps and dependencies

#### 2. **Knowledge Expansion**
- **ResearcherAgent** - Collects and synthesizes knowledge from the Internet
- **WebSearchSkill** - Searching (DuckDuckGo) and scraping (trafilatura)
- **MemorySkill** - Long-term memory (LanceDB)

#### 3. **Execution Layer**
- **CoderAgent** - Generates code using knowledge
- **CriticAgent** - Verifies code quality
- **LibrarianAgent** - Manages files and project structure
- **ChatAgent** - Conversation and assistant
- **GhostAgent** - GUI automation (RPA - Robotic Process Automation)
- **ApprenticeAgent** - Learning workflows through observation (NEW!)

#### 4. **Hybrid AI Engine** 🧠
- **HybridModelRouter** (`venom_core/execution/model_router.py`) - Intelligent routing between local LLM and cloud
- **Work modes**: LOCAL (local only), HYBRID (mix), CLOUD (mainly cloud)
- **Local first**: Privacy and $0 operational costs
- **Providers**: Ollama/vLLM (local), Google Gemini, OpenAI
- Sensitive data **NEVER** goes to the cloud
- **Runtime as API**: model engine is treated as a replaceable HTTP server — we can run it or not, without affecting the base logic. This allows using different model standards.
- **LLM-first direction (Ollama)**: in single-user mode and low query intensity, Ollama's performance is practically comparable to vLLM, and model switching is simpler. vLLM gains advantage mainly with high parallelism and high load.

#### 5. **Learning by Demonstration** 🎓
- **DemonstrationRecorder** - Recording user actions (mouse, keyboard, screenshots)
- **DemonstrationAnalyzer** - Behavioral analysis and pixel → semantics transformation
- **WorkflowStore** - Procedure storage with editing capability
- **Integration with GhostAgent** - Executing generated workflows

#### 6. **Orchestration**
- **Orchestrator** - Main system coordinator
- **IntentManager** - Intent classification (5 types: CODE_GENERATION, RESEARCH, COMPLEX_PLANNING, KNOWLEDGE_SEARCH, GENERAL_CHAT)
- **TaskDispatcher** - Task routing to appropriate agents

#### 7. **Runtime Services (Operational)**
- **Backend API** (FastAPI/uvicorn) and **Next.js UI** – core processes.
- **LLM Servers**: Ollama, vLLM – start/stop from services panel.
- **LanceDB** – local vector memory (embedded); **Redis** – optional broker/locks (can be disabled).
- **Nexus**, **Background Tasks** – optional places for future processes (disabled by default, no start/stop actions; can be hidden/ignored if unused).

**Note about vision/image:** image perception currently uses local vision models in Ollama or OpenAI GPT-4o; Florence-2 ONNX is planned. Ollama/vLLM can handle multimodal models, but this repo does not yet wire a dedicated ONNX runtime for vision.
**We already use ONNX:** currently mainly in TTS (Piper). LLMs remain on Ollama/vLLM (or cloud), and ONNX for vision is a future direction.

### Data Flow

```
User Query
    ↓
IntentManager (intent classification)
    ↓
Orchestrator (flow decision)
    ↓
┌─────────────────────┬─────────────────────┬──────────────────────┐
│  Simple code        │  Complex project    │  Search              │
│  CODE_GENERATION    │  COMPLEX_PLANNING   │  RESEARCH            │
├─────────────────────┼─────────────────────┼──────────────────────┤
│    CoderAgent       │  ArchitectAgent     │   ResearcherAgent    │
│         ↓           │         ↓           │        ↓             │
│    CriticAgent      │  Plan creation      │   WebSearchSkill     │
│         ↓           │         ↓           │        ↓             │
│       Result        │  Plan execution     │   MemorySkill        │
│                     │   (step by step)    │        ↓             │
│                     │        ↓            │      Result          │
│                     │      Result         │                      │
└─────────────────────┴─────────────────────┴──────────────────────┘
```

## 🚀 Quick Start

> 🔎 **New web-next dashboard**
> Detailed description of data sources for Brain/Strategy views and test checklist can be found in the `FRONTEND_NEXT_GUIDE.md` document (translation in progress).
> Chat session documentation, Direct/Normal/Complex modes and memory behavior: `CHAT_SESSION.md`.
> Skills standards and MCP import documentation: `DEV_GUIDE_SKILLS.md`.

## 🖥️ Frontend (Next.js – `web-next`)

The new presentation layer runs on Next.js 15 (App Router, React 19). The interface consists of two types of components:
- **SCC (server/client components)** – by default we create server components (without `"use client"` directive), and mark interactive fragments as client components. This way Brain/Strategy views and Cockpit can stream data without additional queries.
- **Shared layout** (`components/layout/*`) – TopBar, Sidebar, bottom status bar and overlays share graphic tokens and translations (`useTranslation`).

### Key Commands

```bash
# install dependencies
npm --prefix web-next install

# development environment (http://localhost:3000)
npm --prefix web-next run dev

# production build (generates meta versions + standalone)
npm --prefix web-next run build

# short E2E tests (Playwright, prod mode)
npm --prefix web-next run test:e2e

# translation consistency validation
npm --prefix web-next run lint:locales
```

The `predev/prebuild` script runs `scripts/generate-meta.mjs`, which saves `public/meta.json` (version + commit hash). All HTTP hooks use `lib/api-client.ts`; in local mode you can point to backend via variables:

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_WS_BASE=ws://localhost:8000/ws/events
API_PROXY_TARGET=http://localhost:8000
```

> Details (directory architecture, SCC guidelines, view data sources) will be described in the `FRONTEND_NEXT_GUIDE.md` document (translation in progress).

Note: Cockpit now has two views — `/` (production layout with selected boxes) and `/chat` (reference, full copy of previous layout).

#### Slash commands in Cockpit
- Force tool: `/<tool>` (e.g., `/git`, `/web`).
- Force providers: `/gpt` (OpenAI) and `/gem` (Gemini).
- After detecting the prefix, the query content is cleaned of the directive, and UI shows "Forced" label.
- UI language setting (PL/EN/DE) is passed as `preferred_language` in `/api/v1/tasks`.
- Context summary strategy (`SUMMARY_STRATEGY` in `.env`): `llm_with_fallback` (default, active model) or `heuristic_only`.

### Installation

```bash
# Clone repository
git clone https://github.com/mpieniak01/Venom.git
cd Venom

# Install dependencies
pip install -r requirements.txt

# Configuration (copy .env.example to .env and fill in)
cp .env.example .env
```

### Required Dependencies

```
Python 3.10+ (recommended 3.11)
```

### Key Packages:
- `semantic-kernel>=1.9.0` - Agent orchestration
- `ddgs>=1.0` - Search engine (successor to duckduckgo-search)
- `trafilatura` - Text extraction from web pages
- `beautifulsoup4` - HTML parsing
- `lancedb` - Vector database for memory
- `fastapi` - API server
- `zeroconf` - mDNS service discovery for local network
- `pynput` - User action recording (THE_APPRENTICE)
- `google-generativeai` - Google Gemini (optional)
- `openai` / `anthropic` - LLM models (optional)

Full list in [requirements.txt](../../requirements.txt)

### Configuration

Create `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

## ⚙️ Running (FastAPI + Next.js)

Full list of steps and deployment checklist can be found in [`DEPLOYMENT_NEXT.md`](DEPLOYMENT_NEXT.md). Summary below:

### Development Mode
```bash
# backend (uvicorn --reload) + web-next (next dev, turbopack off)
make start        # alias make start-dev

# stop processes and clean ports 8000/3000
make stop

# PID status
make status
```

### Production Mode
```bash
make start-prod   # build next + uvicorn without reload
make stop
```

- backend runs on `http://localhost:8000` (REST/SSE/WS),
- Next.js serves UI on `http://localhost:3000`,
- `SERVE_LEGACY_UI=True` flag runs old FastAPI panel on port 8000 (emergency / reference solution).

### 🔧 Launch Profiles (Light Mode)

Venom offers flexible component launch modes separately - ideal for development environments with limited resources (PC, laptop).

#### Running Components Separately

| Command | Description | Resource Usage | When to Use |
|---------|-------------|----------------|-------------|
| `make api` | Backend (production, **without** auto-reload) | ~50 MB RAM, ~5% CPU | Frontend work or when not editing backend code |
| `make api-dev` | Backend (development, **with** auto-reload) | ~110 MB RAM, ~70% CPU (spikes) | Active backend code work |
| `make api-stop` | Stop backend only | - | Frees port 8000 and backend memory |
| `make web` | Frontend (production build + start) | ~500 MB RAM, ~3% CPU | Demo or when not editing UI |
| `make web-dev` | Frontend (dev server with auto-reload) | ~1.3 GB RAM, ~7% CPU | Active UI work |
| `make web-stop` | Stop frontend only | - | Frees port 3000 and frontend memory |
| `make vllm-start` | Start vLLM (local LLM model) | ~1.4 GB RAM, 13% RAM | Only when working with local models |
| `make vllm-stop` | Stop vLLM | - | Frees ~1.4 GB RAM |
| `make ollama-start` | Start Ollama | ~400 MB RAM | Alternative to vLLM |
| `make ollama-stop` | Stop Ollama | - | Frees Ollama memory |

#### Example Usage Scenarios

**Scenario 1: API work only (Light)**
```bash
make api          # Backend without auto-reload (~50 MB)
# Don't start web or LLM - saves ~2.7 GB RAM
```

**Scenario 2: Frontend work**
```bash
make api          # Backend in background (stable, without reload)
make web-dev      # Frontend with auto-reload for UI work
# Don't start LLM if not needed
```

**Scenario 3: Full stack development**
```bash
make api-dev      # Backend with auto-reload
make web-dev      # Frontend with auto-reload
make vllm-start   # LLM only if working with local models
```

**Scenario 4: Demo / presentation**
```bash
make start-prod   # Everything in production mode (lower CPU usage)
```

**Scenario 5: API testing only**
```bash
make api          # Backend without UI
curl http://localhost:8000/health
```

#### 💡 Optimization Tips

- **VS Code Server**: If working in CLI, close remote VS Code:
  ```bash
  # From WSL/Linux
  pkill -f vscode-server
  # Or if using code tunnel
  code tunnel exit
  ```

- **Autoreload**: `--reload` in uvicorn spawns an additional watcher process. Use `make api` instead of `make api-dev` when not editing backend code.

- **Next.js dev**: `next dev` consumes ~1.3 GB RAM through auto-reload. Use `make web` (production) when only testing, not editing UI.

- **LLM Environment**: vLLM/Ollama consume 1-2 GB RAM. Run them **only** when working with local models. In `AI_MODE=CLOUD` mode they are not needed.

> All data and tests are treated as local experiment – Venom runs on user's private machine and **we don't encrypt artifacts**. Instead, result directories (`**/test-results/`, `perf-artifacts/`, Playwright/Locust reports) go to `.gitignore` to avoid accidental commit of sensitive data. Transparency has priority over formal "shadow-type data".

#### Key Environment Variables:

**AI Configuration (hybrid engine):**
```bash
# AI mode: LOCAL (local only), HYBRID (mix), CLOUD (mainly cloud)
AI_MODE=LOCAL

# Local LLM (Ollama/vLLM)
LLM_SERVICE_TYPE=local
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1
LLM_MODEL_NAME=llama3

# Cloud providers (optional, required for HYBRID/CLOUD)
GOOGLE_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

# Hybrid settings
HYBRID_CLOUD_PROVIDER=google        # google or openai
HYBRID_LOCAL_MODEL=llama3
HYBRID_CLOUD_MODEL=gemini-1.5-pro
SENSITIVE_DATA_LOCAL_ONLY=true     # Sensitive data ALWAYS locally
```

**Network and discovery (local first):**
```bash
# mDNS (Zeroconf) for local network - venom.local
# NOTE: Cloudflare was removed, we use local discovery
```

**The Hive (distributed processing):**
```bash
ENABLE_HIVE=false
HIVE_URL=https://hive.example.com:8080
HIVE_REGISTRATION_TOKEN=your_token
REDIS_HOST=localhost
```

**The Nexus (distributed mesh):**
```bash
ENABLE_NEXUS=false
NEXUS_SHARED_TOKEN=your_secret_token
NEXUS_PORT=8765
```

**External Integrations:**
```bash
GITHUB_TOKEN=ghp_your_token         # Personal access token
GITHUB_REPO_NAME=username/repo      # Repository name
DISCORD_WEBHOOK_URL=https://...     # Optional
SLACK_WEBHOOK_URL=https://...       # Optional
HF_TOKEN=                           # Optional (Hugging Face)
TAVILY_API_KEY=                     # Optional (Tavily Search)
ENABLE_GOOGLE_CALENDAR=false        # Optional
GOOGLE_CALENDAR_CREDENTIALS_PATH=./data/config/google_calendar_credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=./data/config/google_calendar_token.json
ENABLE_ISSUE_POLLING=false          # Enable automatic Issue polling
```

📖 **Full list of variables:** [.env.example](../../.env.example)
📖 **External integrations documentation:** [EXTERNAL_INTEGRATIONS.md](EXTERNAL_INTEGRATIONS.md)
📖 **Hybrid AI engine documentation:** [HYBRID_AI_ENGINE.md](HYBRID_AI_ENGINE.md)

### Configuration Panel (UI)

Venom 2.0 introduces **graphical configuration panel** available in web interface at `http://localhost:3000/config`. The panel enables:

#### Service Management
- **Status monitoring** - Backend, UI, LLM (Ollama/vLLM), Hive, Nexus, background tasks
- **Process control** - Start/stop/restart from UI without terminal
- **Real-time metrics** - PID, port, CPU%, RAM, uptime, last logs
- **Quick profiles**:
  - `Full Stack` - All services active
  - `Light` - Backend and UI only (resource saving)
  - `LLM OFF` - Everything except language models

#### Parameter Editing
Panel enables editing key runtime parameters from UI, with automatic:
- **Range validation** - Ports (1-65535), confidence thresholds (0.0-1.0), boolean values
- **Secret masking** - API keys, tokens, passwords are hidden by default
- **Configuration backup** - Automatic `.env` backup to `config/env-history/` before each change
- **Restart information** - System indicates which services require restart after change

#### Available Parameter Sections:
1. **AI Mode** - AI mode, LLM endpoint, API keys, model routing
2. **Commands** - Start/stop commands for Ollama and vLLM
3. **Hive** - Redis configuration, queues, timeouts
4. **Nexus** - Distributed mesh, port, tokens, heartbeat
5. **Tasks** - Background tasks (documentation, cleanup, memory consolidation)
6. **Shadow** - Desktop awareness, confidence thresholds, privacy filter
7. **Ghost** - GUI automation, verification, safety delays
8. **Avatar** - Audio interface, Whisper, TTS, VAD

#### Security
- **Parameter whitelist** - Only defined parameters can be edited through UI
- **Type and range validation** - Value correctness checking before save
- **Dependency checking** - System won't allow starting service without meeting requirements (e.g., Nexus requires running backend)
- **Change history** - Each `.env` modification is saved with timestamp (keeps last 50 backups)

#### Configuration Restore
Panel offers `.env` restore function from earlier backups:
```bash
# Backups are located in:
config/env-history/.env-YYYYMMDD-HHMMSS
```

> 💡 **Tip**: Quick profiles are ideal for switching between work modes. Use `Light` during development on laptop, and `Full Stack` on workstation with GPU.

### 📊 Resource Monitoring

Venom offers tools for quick diagnostics of system resource usage.

#### System Snapshot
```bash
# Generate diagnostic report (processes, memory, CPU, service status)
make monitor

# Manual run
bash scripts/diagnostics/system_snapshot.sh
```

Report will be saved in `logs/diag-YYYYMMDD-HHMMSS.txt` and contains:
- Uptime and load average
- Memory usage (free -h, /proc/meminfo)
- Top 15 processes (CPU and RAM)
- Venom process status (uvicorn, Next.js, vLLM, Ollama)
- PID files status and open ports (8000, 3000, 8001, 11434)

**Usage example:**
```bash
# Before starting work - check baseline
make monitor

# After starting services - compare usage
make api-dev
make web-dev
make monitor

# After finishing - make sure everything stopped
make stop
make monitor
```

### 💾 WSL Memory Management (Windows)

If running Venom in WSL (Windows Subsystem for Linux), you may encounter `vmmem` issue - Windows process that reserves a lot of RAM despite low Linux-side usage.

#### Checking Memory Usage
```bash
# Show detailed WSL memory statistics
bash scripts/wsl/memory_check.sh
```

Script will display:
- Memory summary (free -h)
- Detailed info from /proc/meminfo
- Top 10 RAM-consuming processes
- Memory usage by individual Venom components

#### Problem: vmmem occupies 20+ GB on Windows

**Symptom:** Task Manager in Windows shows `vmmem` process occupying 20-30 GB RAM, even though `free -h` in WSL shows only 3-4 GB.

**Cause:** WSL doesn't return memory to Windows immediately. Cache and buffers are kept "just in case".

**Solution:**

1. **Immediate:** WSL memory reset
   ```bash
   # From WSL (will stop all Venom processes and execute shutdown)
   bash scripts/wsl/reset_memory.sh

   # OR from Windows (PowerShell/CMD)
   wsl --shutdown
   ```

2. **Permanent:** Limit usage through `.wslconfig`

   Create file `%USERPROFILE%\.wslconfig` (e.g., `C:\Users\YourName\.wslconfig`):
   ```ini
   [wsl2]
   # WSL memory limit
   memory=12GB

   # Number of processors
   processors=4

   # Swap limit
   swap=8GB
   ```

   Available example with comments:
   ```bash
   # See full configuration with examples
   cat scripts/wsl/wslconfig.example

   # Copy to Windows (from WSL)
   cp scripts/wsl/wslconfig.example /mnt/c/Users/YourName/.wslconfig
   ```

   After saving `.wslconfig` execute:
   ```powershell
   # From Windows (PowerShell/CMD)
   wsl --shutdown
   ```

   Then restart WSL terminal.

#### Example .wslconfig Configurations

**PC with 16 GB RAM (economical):**
```ini
[wsl2]
memory=8GB
processors=4
swap=4GB
```

**PC with 32 GB RAM (balanced):**
```ini
[wsl2]
memory=12GB
processors=6
swap=8GB
```

**Workstation with 64 GB RAM (performance):**
```ini
[wsl2]
memory=32GB
processors=12
swap=16GB
```

#### Monitoring vmmem in Windows

1. Open Task Manager (Ctrl+Shift+Esc)
2. "Details" or "Processes" tab
3. Find "vmmem" process - this is memory used by WSL
4. Compare with `free -h` results in WSL

If difference is significant (>50%), consider:
- Executing `wsl --shutdown` to free cache
- Setting limits in `.wslconfig`
- Using Light profiles (`make api` instead of `make start-dev`)

### Launch

```bash
# Start server
uvicorn venom_core.main:app --reload

# Or use make
make run
```

## 📖 Documentation

### Architecture and Vision
- [System architecture](VENOM_MASTER_VISION_V1.md)
- [Backend architecture](BACKEND_ARCHITECTURE.md)
- [Venom Architecture Overview](README.md)
- [Intent recognition system](INTENT_RECOGNITION.md)
- [Hybrid AI engine](HYBRID_AI_ENGINE.md)

### Agents
- [**Index of all agents** (34 agents)](AGENTS_INDEX.md) 📋
- [The Architect - Planning](THE_ARCHITECT.md) *(translation in progress)*
- [The Coder - Code generation](THE_CODER.md) *(translation in progress)*
- [The Researcher - Knowledge search](THE_RESEARCHER.md) *(translation in progress)*
- [The Chat - Conversational assistant](THE_CHAT.md) *(translation in progress)*
- [The Strategist - Complexity analysis](THE_STRATEGIST.md) *(Postponed to v2.0)*
- [The Critic - Code verification](THE_CRITIC.md) *(translation in progress)*
- [The Librarian - File management](THE_LIBRARIAN.md) *(translation in progress)*
- [The Integrator - Git & DevOps](THE_INTEGRATOR.md) *(translation in progress)*
- [The Forge (Toolmaker) - Tool creation](THE_FORGE.md) *(translation in progress)*

### Frontend and UI
- [Frontend Next.js](FRONTEND_NEXT_GUIDE.md) *(translation in progress)*
- [Configuration panel](CONFIG_PANEL.md)
- [Dashboard](DASHBOARD_GUIDE.md)

### Tools and Features
- [Model management](../MODEL_MANAGEMENT.md) *(translation in progress)*
- [LLM model tuning](../../docs/_done/072_strojenie_modelu_llm_ui.md) *(Polish only)*
- [Flow Inspector](FLOW_INSPECTOR_GUIDE.md)
- [Dream Engine](DREAM_ENGINE_GUIDE.md) *(Postponed to v2.0)*
- [Process Engine](PROCESS_ENGINE_CONCEPT.md) *(Planned for v2.0)*
- [MEMORY_LAYER_GUIDE.md](../MEMORY_LAYER_GUIDE.md) - Context retrieval
- [Google Search Grounding](../GOOGLE_SEARCH_GROUNDING_INTEGRATION.md) *(translation in progress)*

### DevOps and Deployment
- [Deployment (Next.js)](DEPLOYMENT_NEXT.md)
- [External integrations](EXTERNAL_INTEGRATIONS.md)
- [Guardian - Security](../GUARDIAN_GUIDE.md)
- [QA Delivery](../QA_DELIVERY_GUIDE.md) *(translation in progress)*

### Collaboration
- [Contribution guide](CONTRIBUTING.md)
- [Testing and performance](TESTING_CHAT_LATENCY.md)

## 🧪 Tests

```bash
cd /home/ubuntu/venom
source .venv/bin/activate || true

# Run all tests
pytest

## 🔬 Tests and Benchmarks

Full instructions (steps + expected values) are in [`TESTING_CHAT_LATENCY.md`](TESTING_CHAT_LATENCY.md). Most important commands:

### Backend (FastAPI / agents)
- `pytest -q` — quick system-wide test.
- `pytest tests/test_researcher_agent.py` / `tests/test_architect_agent.py` — agent scenarios.
- `pytest tests/perf/test_chat_pipeline.py -m performance` — SSE measurement (task_update → task_finished) + parallel batch.
- `pytest --cov=venom_core --cov-report=html` — coverage report.

### Frontend Next.js
- `npm --prefix web-next run lint`
- `npm --prefix web-next run build`
- `npm --prefix web-next run test:e2e` — Playwright on prod build.

### Response time and chat performance
- `npm --prefix web-next run test:perf` — Playwright comparing Next Cockpit and old panel (`PERF_NEXT_BASE_URL` / `PERF_LEGACY_BASE_URL`, HTML report goes to `test-results/perf-report`).
-  Available envs: `PERF_NEXT_LATENCY_BUDGET`, `PERF_LEGACY_LATENCY_BUDGET` (default 5000ms/6000ms) and `PERF_*_RESPONSE_TIMEOUT` if you need to relax limits on slower machines.
- `pytest tests/perf/test_chat_pipeline.py -m performance` — backend pipeline (time to `task_finished` + batch).
- `./scripts/run-locust.sh` — start Locust panel (`http://127.0.0.1:8089`) and manual API load.
- `./scripts/archive-perf-results.sh` — dump `test-results/`, Playwright/Locust reports to `perf-artifacts/<timestamp>/`.

> Test results DO NOT go to repo (we ignore `**/test-results/`, `perf-artifacts/`, `playwright-report/`, etc.) – this way you keep them locally without risk of data disclosure.

## 🛠️ Development Tools

### Pre-commit Hooks

```bash
# Installation
pip install pre-commit
pre-commit install

# Manual run
pre-commit run --all-files
```

### Linting and Formatting

```bash
cd /home/ubuntu/venom
source .venv/bin/activate || true

# Ruff (linter + formatter)
ruff check . --fix
ruff format .

# isort (import sorting)
isort . --profile black

# mypy (type checking)
mypy venom_core
```

## 📊 Project Statistics

- **Lines of code:** 118,555 (non-empty lines; excluding `docs/`, `node_modules/`, `logs/`, `data/`)
- **Number of agents:** 33 (modules `venom_core/agents/*`)
- **Number of skills:** 19 executive (`venom_core/execution/skills/*`) + 4 helper (Memory/Voice/Whisper/Core)
- **Number of tests:** 518 (pytest `def test_`) + 18 (Playwright `test(`)
- **Test coverage:** 65%

## 🎯 Roadmap

### ✅ v1.0 (current - Q4 2024)
- [x] Planning Layer (ArchitectAgent)
- [x] Knowledge Expansion (ResearcherAgent + WebSearchSkill)
- [x] Internet Integration
- [x] Long-term memory
- [x] Comprehensive tests
- [x] **NEW: External integrations (PlatformSkill)** 🤖
  - [x] GitHub integration (Issues, pull requests)
  - [x] Discord/Slack notifications
  - [x] Issue → PR process

### 🚧 v1.1 (planned)
- [ ] Background polling for GitHub Issues
- [ ] Dashboard panel for external integrations
- [ ] Recursive summarization of long documents
- [ ] Search results cache
- [ ] Plan validation and optimization
- [ ] Better error recovery

### 🔮 v1.2 (future)
- [ ] Webhook support for GitHub
- [ ] MS Teams integration
- [ ] Multi-source verification
- [ ] Google Search API integration
- [ ] Parallel execution of plan steps
- [ ] Plan cache for similar tasks
- [ ] GraphRAG integration

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) to learn how to start.

### Contribution Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'feat: add new feature'`)
4. Push branch (`git push origin feature/amazing-feature`)
5. Open PR

### Conventions

- **Code and comments:** Polish
- **Commit messages:** Conventional Commits (feat, fix, docs, test, refactor)
- **Style:** Black + Ruff + isort (automatic via pre-commit)
- **Tests:** Required for new features


## 🌐 THE NEXUS: Distributed Architecture

**NEW in v1.1!** Venom can now operate as **Central Node (Nexus)** managing a swarm of remote instances ("Spores").

### Distributed mesh features:
- 🔗 **Master-worker architecture** - Nexus (brain) + Spores (executors)
- 📡 **WebSocket communication** - fast, bidirectional
- 🔍 **mDNS service discovery** - automatic node detection on local network (venom.local)
- ⚖️ **Load balancing** - automatic selection of least loaded node
- 🔄 **Hot-plugging** - dynamic adding/removing of nodes
- 💓 **Health check and failover** - automatic offline detection

### Usage Example:

```bash
# 1. Run Venom in Nexus mode
export ENABLE_NEXUS=true
export NEXUS_SHARED_TOKEN=your-secret-token
cd venom_core && python main.py

# 2. Run Venom Spore on remote machine
cd venom_spore
export SPORE_NEXUS_HOST=venom.local  # or 192.168.1.10
export SPORE_SHARED_TOKEN=your-secret-token
python main.py

# 3. Check connected nodes
curl http://localhost:8000/api/v1/nodes

# 4. Execute task on remote node
curl -X POST http://localhost:8000/api/v1/nodes/{node_id}/execute \
  -H "Content-Type: application/json" \
  -d '{"skill_name": "ShellSkill", "method_name": "run", "parameters": {"command": "ls"}}'
```

### Docker Compose Demo:
```bash
# Run swarm simulation (2 Docker nodes)
docker-compose -f docker-compose.spores.yml up

# Run demo
python examples/nexus_demo.py
```

📖 **Full documentation:** [venom_spore/README.md](../../venom_spore/README.md)
📖 **Hive architecture:** [THE_HIVE.md](THE_HIVE.md)

## 👥 Team

- **Development Lead:** mpieniak01
- **Architecture:** Venom Core Team
- **Contributors:** [List of contributors](https://github.com/mpieniak01/Venom/graphs/contributors)

## 🙏 Acknowledgments

- Microsoft Semantic Kernel
- Microsoft AutoGen
- OpenAI / Anthropic / Google AI
- Open Source Community

---

**Venom** - *Autonomous AI agent system for next-generation automation*

🌟 If you like the project, leave a star on GitHub!

## 📝 License

This project is currently in early development stage.
The repository is public solely for viewing and reference purposes.

At this stage no license is granted.
All rights are reserved by the author until further notice.

---
