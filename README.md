# Venom v1.6.0 🐍
[![Quick Validate](https://img.shields.io/github/actions/workflow/status/mpieniak01/Venom/quick-validate.yml?branch=main&logo=github-actions&logoColor=white&label=Quick%20Validate)](https://github.com/mpieniak01/Venom/actions/workflows/quick-validate.yml)
[![GitGuardian](https://img.shields.io/badge/security-GitGuardian-blue)](https://www.gitguardian.com/)
[![OpenAPI Contract](https://img.shields.io/github/actions/workflow/status/mpieniak01/Venom/ci.yml?branch=main&logo=swagger&logoColor=white&label=OpenAPI%20Contract)](https://github.com/mpieniak01/Venom/actions/workflows/ci.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=mpieniak01_Venom&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=mpieniak01_Venom)

**Quality Signals**
- *Quick Validate:* fast GitHub checks (Python compile smoke, CI-lite dependency audit, frontend script checks).
- *GitGuardian:* secret detection and leak prevention in repository history and pull requests.
- *OpenAPI Contract:* validates OpenAPI export and TypeScript codegen synchronization.
- *Quality Gate Status:* SonarCloud quality gate for backend and frontend.

> **| [Dokumentacja w języku polskim](README_PL.md)**

**Venom** is a local AI platform for engineering automation that combines agent orchestration, tool execution, and organizational memory in one operational environment. It is designed to shorten delivery time from task analysis and planning to implementation and quality control. With a local-first approach, teams keep stronger control over data, costs, and runtime predictability.

In practice, Venom acts as a decision-and-execution layer for technical teams: it automates repetitive work, structures project knowledge, and provides a consistent control point for runtime, configuration, and model governance. This makes scaling delivery easier without proportional growth in operational overhead.

## Why it matters for business
- Reduces end-to-end delivery time for technical tasks (plan + execute + verify).
- Lowers operating cost with local runtime and provider control.
- Keeps organizational knowledge through long-term memory and lessons learned.
- Improves operational control: service status, configuration, and model governance.
- Standardizes team workflows and QA expectations.

## Key capabilities
- 🤖 **Agent orchestration** - planning and execution through specialized roles.
- 🧭 **Hybrid model runtime (3-stack)** - Ollama / vLLM / ONNX + cloud switching with local-first behavior.
- 💾 **Memory and knowledge** - persistent context, lessons learned, and knowledge reuse.
- 🎓 **Workflow learning** - automation built from user demonstrations.
- 🛠️ **Operations and governance** - service panel, policy gate, and provider cost control.
- 🔍 **Transparency and full auditability** - end-to-end trace of decisions, actions, and outcomes for operational trust, compliance, and faster incident review.
- 🔌 **Extensibility** - local tools and MCP import from Git repositories.

## Recent updates (2026-02)
- Release 1.6.0 milestone: local 3-stack runtime is production-ready, giving teams better continuity and lower provider risk.
- Security/governance baseline was hardened (`Policy Gate`, cost limits, fallback policy) to improve operational safety.
- Workflow Control Plane and runtime governance were unified into one operating model (monitoring + configuration + activation flow).
- API traffic control and anti-ban guardrails were integrated as a shared core layer for inbound/outbound communication.
- Quality and learning track was strengthened (`Academy`, intent routing rollout, test-artifact policy) to improve repeatability of delivery.
- Runtime onboarding profiles (`light/llm_off/full`) were stabilized in `venom.sh` (PL/EN/DE + headless mode).
- API Contract Wave-1 was closed (OpenAPI/codegen sync, explicit response schemas, DI cleanup).
- Optional modules platform was opened: custom modules can be enabled through environment-driven registry.

## Documentation
### Start and operations
- [Deployment + startup](docs/DEPLOYMENT_NEXT.md) - Development/production startup flow and runtime requirements.
- [Configuration panel](docs/CONFIG_PANEL.md) - What can be edited from UI and safe editing rules.
- [Frontend Next.js](docs/FRONTEND_NEXT_GUIDE.md) - `web-next` structure, views, and implementation standards.
- [API traffic control](docs/API_TRAFFIC_CONTROL.md) - Global anti-spam/anti-ban model for inbound and outbound API traffic.

### Architecture
- [System vision](docs/VENOM_MASTER_VISION_V1.md) - Target platform direction and product assumptions.
- [Backend architecture](docs/BACKEND_ARCHITECTURE.md) - Backend modules, responsibilities, and component flows.
- [Hybrid AI engine](docs/HYBRID_AI_ENGINE.md) - LOCAL/HYBRID/CLOUD routing and local-first policy.
- [Workflow Control](docs/THE_WORKFLOW_CONTROL.md) - Workflow control model, operations, and guardrails.

### Agents and capabilities
- [System agents catalog](docs/SYSTEM_AGENTS_CATALOG.md) - Agent roles, inputs/outputs, and runtime cooperation.
- [The Academy](docs/THE_ACADEMY.md) - Learning, tuning, and training data operationalization.
- [Optional Module Guide](docs/MODULES_OPTIONAL_REGISTRY.md) - How to author, register, and enable optional modules for Venom core.
- [Memory layer](docs/MEMORY_LAYER_GUIDE.md) - Vector/graph memory organization and retrieval rules.
- [External integrations](docs/EXTERNAL_INTEGRATIONS.md) - GitHub/Slack and other integration setup.

### Quality and collaboration
- [Coding-agent guidelines](docs/AGENTS.md) - Mandatory agent workflow and quality gates.
- [Contributing](docs/CONTRIBUTING.md) - Contribution process and PR expectations.
- [Testing policy](docs/TESTING_POLICY.md) - Test scope, validation commands, and quality requirements.
- [QA Delivery Guide](docs/QA_DELIVERY_GUIDE.md) - Delivery checklist from validation to release readiness.
- [LLM 3-stack benchmark baseline (2026-02-22)](docs/LLM_RUNTIME_3STACK_BENCHMARK_BASELINE_2026-02-22.md) - Frozen reference metrics for `ollama`/`vllm`/`onnx` and E2E comparison.

## UI preview
<table>
  <tr>
    <td align="center" width="50%">
      <img src="./docs/assets/wiedza.jpeg" width="100%" alt="Knowledge Grid" />
      <br />
      <strong>Knowledge Grid</strong><br />
      Memory and knowledge relation view.
    </td>
    <td align="center" width="50%">
      <img src="./docs/assets/diagram.jpeg" width="100%" alt="Trace Analysis" />
      <br />
      <strong>Trace Analysis</strong><br />
      Request flow and orchestration analysis.
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="./docs/assets/konfiguracja.jpg" width="100%" alt="Configuration" />
      <br />
      <strong>Configuration</strong><br />
      Runtime and service management.
    </td>
    <td align="center" width="50%">
      <img src="./docs/assets/chat.jpeg" width="100%" alt="AI Command Center" />
      <br />
      <strong>AI Command Center</strong><br />
      Operations console and work history.
    </td>
  </tr>
</table>

## Architecture
### Project structure
```text
venom/
├── venom_core/
│   ├── api/routes/          # REST API endpoints (agents, tasks, memory, nodes)
│   ├── core/flows/          # Business flows and orchestration
│   ├── agents/              # Specialized AI agents
│   ├── execution/           # Execution layer and model routing
│   ├── perception/          # Perception (desktop_sensor, audio)
│   ├── memory/              # Long-term memory (vectors, graph, workflows)
│   └── infrastructure/      # Infrastructure (hardware, cloud, message broker)
├── web-next/                # Dashboard frontend (Next.js)
└── modules/                 # Optional modules workspace (separate module repos)
```

### Main components
#### 1) Strategic layer
- **ArchitectAgent** - breaks complex tasks into an execution plan.
- **ExecutionPlan** - plan model with steps and dependencies.

#### 2) Knowledge expansion
- **ResearcherAgent** - gathers and synthesizes web knowledge.
- **WebSearchSkill** - search and content extraction.
- **MemorySkill** - long-term memory (LanceDB).

#### 3) Execution layer
- **CoderAgent** - generates code based on available knowledge.
- **CriticAgent** - verifies code quality.
- **LibrarianAgent** - manages files and project structure.
- **ChatAgent** - conversational assistant.
- **GhostAgent** - GUI automation (RPA).
- **ApprenticeAgent** - learns workflows by observation.

#### 4) Hybrid AI engine
- **HybridModelRouter** (`venom_core/execution/model_router.py`) - local/cloud routing.
- **Modes**: LOCAL, HYBRID, CLOUD.
- **Local-first**: privacy and cost control first.
- **Providers**: Ollama/vLLM/ONNX (local), Gemini, OpenAI.
- Sensitive data can be blocked from leaving local runtime.

#### 5) Learning by demonstration
- **DemonstrationRecorder** - records user actions (mouse, keyboard, screen).
- **DemonstrationAnalyzer** - behavioral analysis and pixel-to-semantic mapping.
- **WorkflowStore** - editable procedure repository.
- **GhostAgent integration** - execution of generated workflows.

#### 6) Orchestration and control
- **Orchestrator** - core coordinator.
- **IntentManager** - intent classification and path selection.
- **TaskDispatcher** - routes tasks to agents.
- **Workflow Control Plane** - visual workflow control.

#### 7) The Academy
- **LessonStore** - repository of experience and corrections.
- **Training Pipeline** - LoRA/QLoRA fine-tuning.
- **Adapter Management** - model adapter hot-swapping.
- **Genealogy** - model evolution and metric tracking.

#### 8) Runtime services
- Backend API (FastAPI/uvicorn) and Next.js UI.
- LLM servers: Ollama, vLLM, ONNX (in-process).
- LanceDB (embedded), Redis (optional).
- Nexus and background tasks as optional processes.

## Quick start
### Path A: manual setup from Git (dev)
```bash
git clone https://github.com/mpieniak01/Venom.git
cd Venom
pip install -r requirements.txt
cp .env.example .env
make start
```

Default `requirements.txt` installs **minimal API/cloud profile**.
If you want local runtime engines, install one of:
- `pip install -r requirements-profile-ollama.txt`
- `pip install -r requirements-profile-vllm.txt`
- `pip install -r requirements-profile-onnx.txt`
- `pip install -r requirements-extras-onnx.txt` (optional extras: `faster-whisper` + `piper-tts`)
- `pip install -r requirements-full.txt` (legacy full stack)

### Path B: Docker script setup (single command)
```bash
git clone https://github.com/mpieniak01/Venom.git
cd Venom
scripts/docker/venom.sh
```

After startup:
- API: `http://localhost:8000`
- UI: `http://localhost:3000`

Protocol policy:
- Dev/local stack uses HTTP by default (`URL_SCHEME_POLICY=force_http` in docker profiles).
- Public production should use HTTPS on reverse proxy/ingress (edge TLS).

### Most common commands
```bash
make start       # backend + frontend (dev)
make stop        # stop services
make status      # process status
make start-prod  # production mode
```

## Frontend (Next.js - `web-next`)
The presentation layer runs on Next.js 15 (App Router, React 19).
- **SCC (server/client components)** - server components by default, interactive parts as client components.
- **Shared layout** (`components/layout/*`) - TopBar, Sidebar, status bar, overlays.

### Frontend commands
```bash
npm --prefix web-next install
npm --prefix web-next run dev
npm --prefix web-next run build
npm --prefix web-next run test:e2e
npm --prefix web-next run lint:locales
```

### Local API variables
```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_WS_BASE=ws://localhost:8000/ws/events
API_PROXY_TARGET=http://localhost:8000
```

### Slash commands in Cockpit
- Force tool: `/<tool>` (e.g. `/git`, `/web`).
- Force provider: `/gpt` (OpenAI) and `/gem` (Gemini).
- UI shows a `Forced` label when a prefix is detected.
- UI language is sent as `preferred_language` in `/api/v1/tasks`.
- Summary strategy (`SUMMARY_STRATEGY`): `llm_with_fallback` or `heuristic_only`.

## Installation and dependencies
### Requirements
```text
Python 3.10+ (recommended 3.11)
```

### Key packages
- `semantic-kernel>=1.9.0` - agent orchestration.
- `ddgs>=1.0` - web search.
- `trafilatura` - web text extraction.
- `beautifulsoup4` - HTML parsing.
- `lancedb` - vector memory database.
- `fastapi` - API server.
- `zeroconf` - mDNS service discovery.
- `pynput` - user action recording.
- `google-genai` - Gemini (optional).
- `openai` / `anthropic` - LLM providers (optional).

Profiles:
- [requirements.txt](requirements.txt) - default minimal API/cloud profile
- [requirements-profile-ollama.txt](requirements-profile-ollama.txt) - API + Ollama profile
- [requirements-profile-vllm.txt](requirements-profile-vllm.txt) - API + vLLM profile
- [requirements-profile-onnx.txt](requirements-profile-onnx.txt) - API + ONNX LLM profile (third engine)
- [requirements-extras-onnx.txt](requirements-extras-onnx.txt) - optional extras (`faster-whisper`, `piper-tts`), separate from ONNX LLM profile
- [requirements-full.txt](requirements-full.txt) - full legacy stack

## Running (FastAPI + Next.js)
Full checklist: [`docs/DEPLOYMENT_NEXT.md`](docs/DEPLOYMENT_NEXT.md).

### Development mode
```bash
make start
make stop
make status
```

### Production mode
```bash
make start-prod
make stop
```

### Lowest-memory configurations
| Configuration | Commands | Estimated RAM | Use case |
|--------------|----------|---------------|----------|
| Minimal | `make api` | ~50 MB | API tests / backend-only |
| Light with local LLM | `make api` + `make ollama-start` | ~450 MB | API + local model, no UI |
| Light with UI | `make api` + `make web` | ~550 MB | Demo and quick UI validation |
| Balanced | `make api` + `make web` + `make ollama-start` | ~950 MB | Day-to-day work without dev autoreload |
| Heaviest (dev) | `make api-dev` + `make web-dev` + `make vllm-start` | ~2.8 GB | Full development and local model testing |

## Key environment variables
Full list: [.env.example](.env.example)

## Configuration panel (UI)
The panel at `http://localhost:3000/config` supports:
- service status monitoring (backend, UI, LLM, Hive, Nexus),
- start/stop/restart from UI,
- realtime metrics (PID, port, CPU, RAM, uptime),
- quick profiles: `Full Stack`, `Light`, `LLM OFF`.

### Parameter editing
- type/range validation,
- secret masking,
- `.env` backup to `config/env-history/`,
- restart hints after changes.

### Panel security
- editable parameter whitelist,
- service dependency validation,
- timestamped change history.

## Monitoring and environment hygiene
### Resource monitoring
```bash
make monitor
bash scripts/diagnostics/system_snapshot.sh
```

Report (`logs/diag-YYYYMMDD-HHMMSS.txt`) includes:
- uptime and load average,
- memory usage,
- top CPU/RAM processes,
- Venom process status,
- open ports (8000, 3000, 8001, 11434).

### Dev environment hygiene (repo + Docker)
```bash
make env-audit
make env-clean-safe
make env-clean-docker-safe
CONFIRM_DEEP_CLEAN=1 make env-clean-deep
make env-report-diff
```

## Docker package (end users)
Run with prebuilt images:
```bash
git clone https://github.com/mpieniak01/Venom.git
cd Venom
scripts/docker/venom.sh
```

Compose profiles:
- `compose/compose.release.yml` - end-user profile (pull prebuilt images).
- `compose/compose.minimal.yml` - developer profile (local build).
- `compose/compose.spores.yml.tmp` - Spore draft, currently inactive.

Useful commands:
```bash
scripts/docker/venom.sh
scripts/docker/run-release.sh status
scripts/docker/run-release.sh restart
scripts/docker/run-release.sh stop
scripts/docker/uninstall.sh --stack both --purge-volumes --purge-images
scripts/docker/logs.sh
```

Runtime profile (single package, selectable mode):
```bash
export VENOM_RUNTIME_PROFILE=light   # light|llm_off|full
scripts/docker/run-release.sh start
```
`llm_off` means no local LLM runtime (Ollama/vLLM/ONNX), but backend and UI can still use external LLM APIs (for example OpenAI/Gemini) after API key configuration.

Optional GPU mode:
```bash
export VENOM_ENABLE_GPU=auto
scripts/docker/run-release.sh restart
```

## Quality and security
- CI: Quick Validate + OpenAPI Contract + SonarCloud.
- Security: GitGuardian + periodic dependency scans.
- `pre-commit run --all-files` runs: `block-docs-dev-staged`, `end-of-file-fixer`, `trailing-whitespace`, `check-added-large-files`, `check-yaml`, `debug-statements`, `ruff-check --fix`, `ruff-format`, `isort`.
- Extra hooks outside this command: `block-docs-dev-tracked` (stage `pre-push`) and `update-sonar-new-code-group` (stage `manual`).
- `pre-commit` can auto-fix files; rerun it until all hooks are `Passed`.
- Treat `mypy venom_core` as a full typing audit; the repository may include historical typing backlog not related to your change.
- Local PR sequence:

```bash
source .venv/bin/activate || true
pre-commit run --all-files
make pr-fast
make check-new-code-coverage
```

## Roadmap
### ✅ v1.6.0 (current)
- [x] v1.4 features (planning, knowledge, memory, integrations).
- [x] The Academy (LoRA/QLoRA).
- [x] Workflow Control Plane.
- [x] Provider Governance.
- [x] Academy Hardening.

### ✅ v1.6 (milestone release)
- [x] API contract hardening (Wave-1 + Wave-2 MVP) with OpenAPI/FE synchronization.
- [x] ONNX Runtime integrated as the third local LLM engine (3-stack: Ollama + vLLM + ONNX).
- [x] Runtime profiles and installation strategy update (minimal/API-first + optional local stacks).
- [x] Runtime control-plane improvements and provider/runtime governance stabilization.

### 🚧 v1.7 (planned details)
- [ ] Background polling for GitHub Issues.
- [ ] Dashboard panel for external integrations.
- [ ] Recursive long-document summarization.
- [ ] Search result caching.
- [ ] Plan validation and optimization UX.
- [ ] Better end-to-end error recovery.

### 🔮 v2.0 (future)
- [ ] GitHub webhook handling.
- [ ] MS Teams integration.
- [ ] Multi-source verification.
- [ ] Google Search API integration.
- [ ] Parallel plan step execution.
- [ ] Plan caching for similar tasks.
- [ ] GraphRAG integration.

### Conventions
- Code and comments: Polish or English.
- Commit messages: Conventional Commits (`feat`, `fix`, `docs`, `test`, `refactor`).
- Style: Black + Ruff + isort (via pre-commit).
- Tests: required for new functionality.
- Quality gates: SonarCloud must pass on PR.

## Team
- **Development lead:** mpieniak01.
- **Architecture:** Venom Core Team.
- **Contributors:** [Contributors list](https://github.com/mpieniak01/Venom/graphs/contributors).

## Thanks
- Microsoft Semantic Kernel, Microsoft AutoGen, OpenAI / Anthropic / Google AI, pytest, open-source community.

---
**Venom** - *Autonomous AI agent system for next-generation automation*

## License
This project is distributed under the MIT license. See [`LICENSE`](LICENSE).
Copyright (c) 2025-2026 Maciej Pieniak
