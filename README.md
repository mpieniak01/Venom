# Venom v1.0 🐍

[![Quick Validate](https://img.shields.io/github/actions/workflow/status/mpieniak01/Venom/quick-validate.yml?branch=main&logo=github-actions&logoColor=white&label=Quick%20Validate)](https://github.com/mpieniak01/Venom/actions/workflows/quick-validate.yml)
[![GitGuardian](https://img.shields.io/badge/security-GitGuardian-blue)](https://www.gitguardian.com/)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=mpieniak01_Venom&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=mpieniak01_Venom)

**Quality Signals**
- *Quick Validate:* GitHub fast checks (Python compile smoke, CI-lite dependency audit, frontend script sanity).
- *GitGuardian:* secret detection and leak prevention for repository history and pull requests.
- *Quality Gate Status:* SonarCloud gate from backend (`python-coverage.xml`, `python-junit.xml`) and frontend (`lcov.info`) reports.

> **| [Dokumentacja w języku polskim](README_PL.md)**

**Venom** is an autonomous multi-agent engineering system with planning, tool execution, and persistent memory.

### Key Features
- 🧠 **Strategic Planning** — Breaks complex goals into executable steps.
- 🤖 **Agent Orchestration** — Routes tasks to specialized agents.
- 🔌 **Tooling + MCP Import** — Uses local tools and imports MCP tools from Git.
- 🧭 **Runtime LLM Selection** — Switches Ollama / vLLM from the UI.
- 💾 **Long-term Memory** — Stores and reuses lessons and context.
- 🎓 **Learning by Observation** — Records demonstrations and builds workflows.
- 👍👎 **Quality Loop** — User feedback, logs, and response quality metrics.
- 🧠 **Hidden Prompts** — Approved responses stored as contextual shortcuts.
- 💬 **Chat Continuity** — Session history per `session_id` across restarts.
- 🛠️ **Services Panel** — `/config` shows runtime status of local stack.

See `docs/` for architecture, frontend guide, and testing policy.

## 🖼️ UI Preview (snapshots)

### 🧠 Knowledge Grid — memory & knowledge visualization
<p align="center">
  <img src="./docs/assets/wiedza.jpeg" width="900" />
</p>

### 🧪 Trace Analysis — request flow & orchestration diagnostics
<p align="center">
  <img src="./docs/assets/diagram.jpeg" width="900" />
</p>

### ⚙️ Configuration — runtime services & launch profiles
<p align="center">
  <img src="./docs/assets/konfiguracja.jpg" width="900" />
</p>

### 🎛️ AI Command Center — operational cockpit & session history
<p align="center">
  <img src="./docs/assets/chat.jpeg" width="900" />
</p>

### 🎯 Usage Examples

```python
# 1. Searching for current information
"What is the current Bitcoin price?"
→ System automatically searches the Internet and returns fresh data

# 2. Complex projects with planning
"Create a Snake game using PyGame"
→ System:
  1. Finds PyGame documentation (ResearcherAgent)
  2. Creates game structure (CoderAgent)
  3. Adds snake logic (CoderAgent)
  4. Implements scoring (CoderAgent)

# 3. Multi-file webpage
"Create an HTML page with a digital clock and CSS styling"
→ System creates separately: index.html, style.css, script.js

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
- **ResearcherAgent** - Gathers and synthesizes knowledge from the Internet
- **WebSearchSkill** - Search (DuckDuckGo) and scraping (trafilatura)
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
- **Operating Modes**: LOCAL (local only), HYBRID (mix), CLOUD (mainly cloud)
- **Local First**: Privacy and $0 operational costs
- **Providers**: Ollama/vLLM (local), Google Gemini, OpenAI
- Sensitive data **NEVER** goes to the cloud
- **Runtime as API**: model engine is treated as a replaceable HTTP server - we can run it or not, without impacting base logic. This allows using different model standards.
- **LLM-first Direction (Ollama)**: in single-user mode and low query intensity, Ollama's performance is practically comparable to vLLM, and model switching is simpler. vLLM gains an advantage mainly with high parallelism and heavy load.

#### 5. **Learning by Demonstration** 🎓
- **DemonstrationRecorder** - Recording user actions (mouse, keyboard, screenshots)
- **DemonstrationAnalyzer** - Behavioral analysis and transformation pixels → semantics
- **WorkflowStore** - Procedure repository with editing capability
- **GhostAgent Integration** - Executing generated workflows

#### 6. **Orchestration**
- **Orchestrator** - Main system coordinator
- **IntentManager** - Intent classification (5 types: CODE_GENERATION, RESEARCH, COMPLEX_PLANNING, KNOWLEDGE_SEARCH, GENERAL_CHAT)
- **TaskDispatcher** - Task routing to appropriate agents

#### 7. **Runtime Services (operational)**
- **Backend API** (FastAPI/uvicorn) and **Next.js UI** – basic processes.
- **LLM Servers**: Ollama, vLLM – start/stop from services panel.
- **LanceDB** – local vector memory (embedded); **Redis** – optional broker/locks (can be disabled).
- **Nexus**, **Background Tasks** – optional spots for future processes (disabled by default, no start/stop actions; can be hidden/ignored if unused).

**Note about vision/image:** perception currently uses local ONNX models (OCR/object recognition) and selected audio pipelines. Multimodal LLMs (Ollama/vLLM) are supported in theory, but are not wired as the vision runtime yet.

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
> Detailed description of data sources for Brain/Strategy views and test checklist can be found in `docs/FRONTEND_NEXT_GUIDE.md`. The document also defines entry criteria for the next stage of UI work.
> Chat session documentation, Direct/Normal/Complex modes and memory behavior: `docs/CHAT_SESSION.md`.
> Skills standards and MCP import: `docs/DEV_GUIDE_SKILLS.md`.

## 🖥️ Frontend (Next.js – `web-next`)

The new presentation layer runs on Next.js 15 (App Router, React 19). The interface consists of two types of components:
- **SCC (Server/Client Components)** – by default we create server components (without `"use client"` directive), and mark interactive fragments as client. Thanks to this, Brain/Strategy and Cockpit views can stream data without additional queries.
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

# validate translation consistency
npm --prefix web-next run lint:locales
```

The `predev/prebuild` script runs `scripts/generate-meta.mjs`, which saves `public/meta.json` (version + commit hash). All HTTP hooks use `lib/api-client.ts`; in local mode you can point to backend via variables:

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_WS_BASE=ws://localhost:8000/ws/events
API_PROXY_TARGET=http://localhost:8000
```

> Details (directory architecture, SCC guidelines, view data sources) are described in `docs/FRONTEND_NEXT_GUIDE.md`.

Note: Cockpit now has two views — `/` (production layout with selected boxes) and `/chat` (reference, full copy of previous layout).

#### Slash Commands in Cockpit
- Force tool: `/<tool>` (e.g. `/git`, `/web`).
- Force providers: `/gpt` (OpenAI) and `/gem` (Gemini).
- After detecting prefix, query content is cleaned of directive, and UI shows "Forced" label.
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

Full list in [requirements.txt](requirements.txt)

### Configuration

Create `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

## ⚙️ Running (FastAPI + Next.js)

Full list of steps and deployment checklist can be found in [`docs/DEPLOYMENT_NEXT.md`](docs/DEPLOYMENT_NEXT.md). Quick summary below:

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
- Next.js serves UI on `http://localhost:3000`.

### 🔧 Launch Profiles (light mode)

Venom offers flexible modes for running components separately - ideal for development environments with limited resources (PC, laptop).

#### Running Components Separately

| Command | Description | Resource Usage | When to Use |
|---------|-------------|----------------|-------------|
| `make api` | Backend (production, **without** auto-reload) | ~50 MB RAM, ~5% CPU | Working on frontend or not editing backend code |
| `make api-dev` | Backend (development, **with** auto-reload) | ~110 MB RAM, ~70% CPU (spikes) | Active work on backend code |
| `make api-stop` | Stop backend only | - | Frees port 8000 and backend memory |
| `make web` | Frontend (production build + start) | ~500 MB RAM, ~3% CPU | Demo or not editing UI |
| `make web-dev` | Frontend (dev server with auto-reload) | ~1.3 GB RAM, ~7% CPU | Active UI work |
| `make web-stop` | Stop frontend only | - | Frees port 3000 and frontend memory |
| `make vllm-start` | Start vLLM (local LLM model) | ~1.4 GB RAM, 13% RAM | Only when working with local models |
| `make vllm-stop` | Stop vLLM | - | Frees ~1.4 GB RAM |
| `make ollama-start` | Start Ollama | ~400 MB RAM | Alternative to vLLM |
| `make ollama-stop` | Stop Ollama | - | Frees Ollama memory |

#### Example Usage Scenarios

**Scenario 1: Working only on API (Light)**
```bash
make api          # Backend without auto-reload (~50 MB)
# Don't run web or LLM - save ~2.7 GB RAM
```

**Scenario 2: Working on frontend**
```bash
make api          # Backend in background (stable, no reload)
make web-dev      # Frontend with auto-reload for UI work
# Don't run LLM if not needed
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

- **Next.js dev**: `next dev` uses ~1.3 GB RAM due to auto-reload. Use `make web` (production) when only testing, not editing UI.

- **LLM Environment**: vLLM/Ollama use 1-2 GB RAM. Run them **only** when working with local models. In `AI_MODE=CLOUD` mode they are not needed.

> All data and tests are treated as local experiments – Venom runs on user's private machine and **we don't encrypt artifacts**. Instead, directories with results (`**/test-results/`, `perf-artifacts/`, Playwright/Locust reports) go to `.gitignore` to avoid accidentally committing sensitive data. Transparency takes priority over formal "shadow data".

#### Key Environment Variables:

**AI Configuration (hybrid engine):**
```bash
# AI Mode: LOCAL (local only), HYBRID (mix), CLOUD (mainly cloud)
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
SENSITIVE_DATA_LOCAL_ONLY=true     # Sensitive data ALWAYS local
```

**Network and Discovery (local first):**
```bash
# mDNS (Zeroconf) for local network - venom.local
# NOTE: Cloudflare has been removed, we use local discovery
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
ENABLE_ISSUE_POLLING=false          # Enable automatic issue polling
```

📖 **Full variable list:** [.env.example](.env.example)
📖 **External integrations documentation:** [docs/EXTERNAL_INTEGRATIONS.md](docs/EXTERNAL_INTEGRATIONS.md)
📖 **Hybrid AI engine documentation:** [docs/HYBRID_AI_ENGINE.md](docs/HYBRID_AI_ENGINE.md)

### Configuration Panel (UI)

Venom 2.0 introduces a **graphical configuration panel** available in the web interface at `http://localhost:3000/config`. The panel allows:

#### Service Management
- **Status monitoring** - Backend, UI, LLM (Ollama/vLLM), Hive, Nexus, background tasks
- **Process control** - Start/stop/restart from UI without using terminal
- **Real-time metrics** - PID, port, CPU%, RAM, uptime, recent logs
- **Quick profiles**:
  - `Full Stack` - All services active
  - `Light` - Only Backend and UI (resource saving)
  - `LLM OFF` - Everything except language models

#### Parameter Editing
The panel allows editing key runtime parameters from UI, with automatic:
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
- **Parameter whitelist** - Only defined parameters can be edited via UI
- **Type and range validation** - Checking value correctness before saving
- **Dependency checking** - System won't allow starting a service without meeting requirements (e.g. Nexus requires running backend)
- **Change history** - Each `.env` modification is saved with timestamp (last 50 backups kept)

#### Configuration Restore
Panel offers function to restore `.env` from earlier backups:
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

The report will be saved to `logs/diag-YYYYMMDD-HHMMSS.txt` and contains:
- Uptime and load average
- Memory usage (free -h, /proc/meminfo)
- Top 15 processes (CPU and RAM)
- Venom process status (uvicorn, Next.js, vLLM, Ollama)
- PID files status and open ports (8000, 3000, 8001, 11434)

**Example usage:**
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

If you run Venom in WSL (Windows Subsystem for Linux), you may encounter issues with `vmmem` - a Windows process that reserves a lot of RAM despite small Linux-side usage.

#### Checking Memory Usage
```bash
# Show detailed WSL memory statistics
bash scripts/wsl/memory_check.sh
```

The script will display:
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
   # From WSL (stops all Venom processes and executes shutdown)
   bash scripts/wsl/reset_memory.sh

   # OR from Windows (PowerShell/CMD)
   wsl --shutdown
   ```

2. **Permanent:** Limit usage via `.wslconfig`

   Create file `%USERPROFILE%\.wslconfig` (e.g. `C:\Users\YourName\.wslconfig`):
   ```ini
   [wsl2]
   # Memory limit for WSL
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
- Running `wsl --shutdown` to free cache
- Setting limits in `.wslconfig`
- Using Light profiles (`make api` instead of `make start-dev`)

### Running

```bash
# Start server
uvicorn venom_core.main:app --reload

# Or use make
make run
```

## 📖 Documentation

### Architecture and Vision
- [System Architecture](docs/VENOM_MASTER_VISION_V1.md)
- [Backend Architecture](docs/BACKEND_ARCHITECTURE.md)
- [Distributed Architecture (The Hive / Nexus)](docs/THE_HIVE.md)
- [Intent Recognition System](docs/INTENT_RECOGNITION.md)
- [Hybrid AI Engine](docs/HYBRID_AI_ENGINE.md)

### Agents
- [**System Agents Catalog** (34 agents)](docs/SYSTEM_AGENTS_CATALOG.md) 📋
- [**Coding Agents Guidelines**](docs/AGENTS.md) 🧭
- [The Architect - Planning](docs/THE_ARCHITECT.md)
- [The Coder - Code Generation](docs/THE_CODER.md)
- [The Researcher - Knowledge Search](docs/THE_RESEARCHER.md)
- [The Chat - Conversational Assistant](docs/THE_CHAT.md)
- [The Strategist - Complexity Analysis](docs/THE_STRATEGIST.md)
- [The Critic - Code Verification](docs/THE_CRITIC.md)
- [The Librarian - File Management](docs/THE_LIBRARIAN.md)
- [The Integrator - Git & DevOps](docs/THE_INTEGRATOR.md)
- [The Forge (Toolmaker) - Tool Creation](docs/THE_FORGE.md)

### Frontend and UI
- [Frontend Next.js](docs/FRONTEND_NEXT_GUIDE.md)
- [Configuration Panel](docs/CONFIG_PANEL.md)
- [Dashboard](docs/DASHBOARD_GUIDE.md)

### Tools and Features
- [Model Management](docs/MODEL_MANAGEMENT.md)
- [LLM Model Tuning](docs/MODEL_TUNING_GUIDE.md)
- [Flow Inspector](docs/FLOW_INSPECTOR_GUIDE.md)
- [Dream Engine](docs/DREAM_ENGINE_GUIDE.md)
- [Memory Layer](docs/MEMORY_LAYER_GUIDE.md)
- [Google Search Grounding](docs/GOOGLE_SEARCH_GROUNDING_INTEGRATION.md)

### DevOps and Deployment
- [Deployment (Next.js)](docs/DEPLOYMENT_NEXT.md)
- [External Integrations](docs/EXTERNAL_INTEGRATIONS.md)
- [Guardian - Security](docs/GUARDIAN_GUIDE.md)
- [QA Delivery](docs/QA_DELIVERY_GUIDE.md)
- [Docker Minimal Packaging (sanity + publish)](docs/DEPLOYMENT_NEXT.md)
- [Docker Package Release Guide](docs/DOCKER_RELEASE_GUIDE.md)
- [Windows WSL Install on D: (Docker Release)](docs/WINDOWS_WSL_D_DRIVE_INSTALL.md)

### Collaboration
- [Contribution Guide](docs/CONTRIBUTING.md)
- [Testing Policy](docs/TESTING_POLICY.md)
- [Testing and Performance](docs/TESTING_CHAT_LATENCY.md)

## 🧪 Tests

Testing policy and commands are centralized in:

- [`docs/TESTING_POLICY.md`](docs/TESTING_POLICY.md)
- [`docs/TESTING_CHAT_LATENCY.md`](docs/TESTING_CHAT_LATENCY.md) (performance/latency details)

Quick local pre-PR path:

```bash
make pr-fast
```

Manual equivalent (if needed):

```bash
source .venv/bin/activate || true
pre-commit run --all-files
mypy venom_core
make check-new-code-coverage
```

## 📦 Docker Package (End User)

If you want to run Venom from published images (without local build), use release compose:

```bash
git clone https://github.com/mpieniak01/Venom.git
cd Venom

# optional overrides:
# export BACKEND_IMAGE=ghcr.io/<owner>/venom-backend:v1.2.0
# export FRONTEND_IMAGE=ghcr.io/<owner>/venom-frontend:v1.2.0
# export OLLAMA_MODEL=gemma3:1b

scripts/docker/run-release.sh start
```

Compose profiles in this repository:
- `compose/compose.release.yml` - end-user profile (pulls prebuilt backend/frontend from GHCR).
- `compose/compose.minimal.yml` - developer profile (local build of backend/frontend).
- `compose/compose.spores.yml.tmp` - temporary Spore nodes draft; currently unused and intentionally not an active compose profile.

Useful commands:

```bash
scripts/docker/run-release.sh status
scripts/docker/run-release.sh restart
scripts/docker/run-release.sh stop
scripts/docker/logs.sh
```

Optional GPU mode:

```bash
export VENOM_ENABLE_GPU=auto   # default; falls back to CPU if runtime is missing
scripts/docker/run-release.sh restart
```

## 🛠️ Development Tools

### Quality and Security Gates

- **SonarCloud (PR gate):** every pull request is analyzed for bugs, vulnerabilities, code smells, duplications and maintainability issues.
- **Snyk (periodic scan):** dependency and container security scanning is executed periodically to catch newly disclosed CVEs.
- **CI Lite:** fast checks on every PR (lint + selected unit tests) to keep feedback loop short.
- **Docker package flow:** `docker-sanity` validates builds on PR; package publishing (`docker-publish`) runs only on `v*` tags or manual trigger.
- **Docker Minimal network policy:** LAN testing from another machine is supported by default; run only in trusted/private networks.

What this means for contributors and agents:
- Keep functions small and readable (avoid high cognitive complexity).
- Prefer explicit typing and pass `mypy venom_core`.
- Avoid unused blocks/imports and dead code.
- Treat warnings from `ruff`, `mypy`, and Sonar as release blockers for new code.

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
isort .

# mypy (type checking)
mypy venom_core
```

Tools use the repo configuration (`pyproject.toml`) and skip data directories
such as `models/` and `models_cache/`.

## 📊 Project Statistics

- **Lines of code:** 118,555 (non-empty lines; excluding `docs/`, `node_modules/`, `logs/`, `data/`)
- **Number of agents:** 33 (modules `venom_core/agents/*`)
- **Number of skills:** 19 executable (`venom_core/execution/skills/*`) + 4 helper (Memory/Voice/Whisper/Core)
- **Number of tests:** 518 (pytest `def test_`) + 18 (Playwright `test(`)
- **Test coverage:** 65%

## 🎯 Roadmap

### ✅ v1.0 (current)
- [x] Planning Layer (ArchitectAgent)
- [x] Knowledge Expansion (ResearcherAgent + WebSearchSkill)
- [x] Internet Integration
- [x] Long-term memory
- [x] Comprehensive tests
- [x] **NEW: External integrations (PlatformSkill)** 🤖
  - [x] GitHub integration (Issues, pull requests)
  - [x] Discord/Slack notifications
  - [x] Issue → PR process

### 🚧 v1.2 (planned)
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
- [ ] Parallel plan step execution
- [ ] Plan cache for similar tasks
- [ ] GraphRAG integration

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](docs/CONTRIBUTING.md) to learn how to get started.

### Collaboration Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'feat: add new feature'`)
4. Push branch (`git push origin feature/amazing-feature`)
5. Open a PR

### Conventions

- **Code and comments:** English or Polish
- **Commit messages:** Conventional Commits (feat, fix, docs, test, refactor)
- **Style:** Black + Ruff + isort (automatic via pre-commit)
- **Tests:** Required for new features
- **Quality gates:** SonarCloud must pass on PR; security baseline is continuously monitored with periodic Snyk scans

## 👥 Team

- **Development Lead:** mpieniak01
- **Architecture:** Venom Core Team
- **Contributors:** [Contributors list](https://github.com/mpieniak01/Venom/graphs/contributors)

## 🙏 Acknowledgments

- Microsoft Semantic Kernel
- Microsoft AutoGen
- OpenAI / Anthropic / Google AI
- pytest
- Open Source Community

---

**Venom** - *Autonomous AI agent system for next generation automation*

🌟 If you like the project, leave a star on GitHub!

## 📝 License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for more information.

Copyright (c) 2025-2026 Maciej Pieniak

---
