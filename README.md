# Venom v1.8 🐍
[![GitGuardian](https://img.shields.io/badge/security-GitGuardian-blue)](https://www.gitguardian.com/)
[![OpenAPI Contract](https://img.shields.io/github/actions/workflow/status/mpieniak01/Venom/ci.yml?branch=main&logo=swagger&logoColor=white&label=OpenAPI%20Contract)](https://github.com/mpieniak01/Venom/actions/workflows/ci.yml)
[![SonarCloud Quality](https://sonarcloud.io/api/project_badges/measure?project=mpieniak01_Venom&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=mpieniak01_Venom)
[![Known Vulnerabilities](https://snyk.io/test/github/mpieniak01/Venom/badge.svg)](https://snyk.io/test/github/mpieniak01/Venom)

**Quality Signals**
- *GitGuardian:* secret detection and leak prevention in repository history and pull requests.
- *OpenAPI Contract:* validates OpenAPI export and TypeScript codegen synchronization.
- *SonarCloud Quality:* live status of code-quality gate on SonarCloud.
- *Snyk Vulnerabilities:* live status of dependency vulnerabilities for this GitHub repository.

> **| [Dokumentacja w języku polskim](README_PL.md)**

**Venom** is an open-source, local-first AI stack for practical engineering automation. It combines agent orchestration, tool execution, and long-term memory in one environment you can run and evolve locally.

Current environment recommendation: use `dev` and `preprod`. `prod` is still planned and not yet validated/recommended for live operation.

It is not a black box. You get explicit process control (Workflow Control Plane), transparent runtime decisions, and full request-level audit trails. You can also choose between three model stacks: `ONNX`, `vLLM`, `Ollama`, depending on hardware, cost, and latency goals.

## Why Venom
- Local-first by default, cloud when needed: keep data and inference local instead of pushing everything to SaaS.
- Three runtime stacks (`ONNX` / `vLLM` / `Ollama`): pick the best fit for your hardware and latency/cost target.
- Process control instead of hidden behavior: Workflow Control Plane shows what runs, what is active, and what changes.
- Transparency and auditability: request tracing exposes decisions, steps, and outcomes end-to-end.
- Memory and lessons learned: knowledge persists beyond a single chat session.
- Open code and docs: easier to debug, extend, and maintain your own fork.
- Explicit quality gates in CI: SonarCloud, Snyk, and OpenAPI Contract remain visible and measurable.

## Key capabilities
- 🤖 **Agent orchestration** - planning and execution through specialized roles.
- 🧭 **Hybrid model runtime (3-stack)** - Ollama / vLLM / ONNX + cloud switching with local-first behavior.
- 💾 **Memory and knowledge** - persistent context, lessons learned, and knowledge reuse.
- 🎓 **Workflow learning** - automation built from user demonstrations.
- 🛠️ **Operations and governance** - service panel, policy gate, and provider cost control.
- 🔍 **Transparency and full auditability** - end-to-end trace of decisions, actions, and outcomes for operational trust, compliance, and faster incident review.
- 🔌 **Extensibility** - local tools and MCP import from Git repositories.

## Recent updates (2026-03, v1.8)
- Global Policy Gate is active as one central runtime checkpoint in orchestrator flow (`global_pre_execution`).
- Deny contract was unified across policy/autonomy (`reason_code`, `user_message`, `technical_context`, `remediation_hint`) with consistent audit eventing.
- Operational endpoints for policy rollout and KPI were added:
  - `GET /api/v1/system/autonomy/rollout-status`
  - `GET /api/v1/system/autonomy/observability`
- Rollout verification script was delivered: `scripts/ops/verify_policy_rollout.py`.
- Runtime path was simplified to runtime-only governance (legacy submit-level policy block path removed from execution flow).
- Permissions UI in `/config` was expanded with the `Permissions` tab and autonomy/audit controls aligned with the same audit stream.
- Academy ONNX direct deploy path was closed end-to-end for Gemma-3 LoRA (`merge_export -> activate -> inference -> deactivate`) with live artifacted validation.
- Recommended WSL2 profile for ONNX Academy E2E on 32 GB / 12 GB hosts was raised to `memory=30GB`, `swap=16GB` (see `docs/RUNTIME_PROFILES.md`).

## Documentation
### Start and operations
- [Deployment + startup](docs/DEPLOYMENT_NEXT.md) - Development/production startup flow and runtime requirements.
- [Environment support matrix](docs/ENVIRONMENTS_SUPPORT.md) - Current support status for `dev`/`preprod`/`prod` and required configuration model.
- [Dashboard Guide](docs/DASHBOARD_GUIDE.md) - Web dashboard startup, scripts, and operational cockpit overview.
- [Tools Usage Guide](docs/TOOLS_USAGE_GUIDE.md) - Slash-tool routing, tool behavior, and web-search runtime requirements.
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
- [LLM 3-stack benchmark baseline](docs/LLM_RUNTIME_3STACK_BENCHMARK_BASELINE.md) - Frozen reference metrics for `ollama`/`vllm`/`onnx` and E2E comparison.

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
cp .env.dev.example .env.dev
make start
```

Default `requirements.txt` installs **minimal API/cloud profile**.
If you want local runtime engines, install one of:
- `pip install -r requirements.txt` (Ollama: no extra Python deps)
- `pip install -r requirements-profile-vllm.txt`
- `pip install -r requirements-profile-onnx.txt`
- `pip install -r requirements-profile-onnx-cpu.txt`
- `pip install -r requirements-extras-onnx.txt` (optional extras: `faster-whisper` + `piper-tts`; install after ONNX/ONNX-CPU profile)
- `pip install -r requirements-full.txt` (legacy full stack)

### Dependency Profile Guarantees
Use this matrix as the source of truth for "is this missing package expected or a profile bug?".

| Profile | Guaranteed scope | Explicitly not included |
|---|---|---|
| `requirements.txt` (`requirements-profile-api.txt`) | API/cloud baseline (`fastapi`, `uvicorn`, cloud providers) | Local heavy runtime packages (`vllm`, `onnxruntime*`, `lancedb`, `sentence-transformers`) |
| `requirements-profile-web.txt` | API baseline + web integration runtime deps | Same heavy local runtime packages as API profile |
| `requirements-profile-vllm.txt` | API baseline + `vllm` | ONNX stack, RAG/vector stack (`lancedb`, `sentence-transformers`) |
| `requirements-profile-onnx.txt` | API baseline + ONNX runtime stack | vLLM, RAG/vector stack (`lancedb`, `sentence-transformers`) |
| `requirements-profile-onnx-cpu.txt` | API baseline + ONNX CPU runtime stack | vLLM, ONNX CUDA packages, RAG/vector stack (`lancedb`, `sentence-transformers`) |
| `requirements-full.txt` | Legacy all-in profile (includes `vllm`, ONNX, `lancedb`, `sentence-transformers`) | n/a |

Rules for incident triage:
1. If a package is missing because the corresponding profile was not installed, this is expected behavior.
2. If a package is missing and it is not guaranteed by the active profile, this is expected behavior.
3. If a package is listed in the selected profile but still missing after install, this is an environment/install issue and should be treated as a defect.

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
make start       # backend + frontend (webpack-safe dev)
make start2      # backend + frontend (turbopack dev)
make stop        # stop services
make status      # process status
make start-prod  # production mode
```

Warning:
- `make start-prod` exists for technical compatibility, but `prod` is not yet validated/recommended for live operation.
- Recommended environments: `dev` and `preprod`.

## Frontend (Next.js - `web-next`)
The presentation layer runs on Next.js 16 (App Router, React 19).
- Required runtime: Node.js `>=20.9.0` and npm `>=10.0.0` (see `web-next/.nvmrc`).
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
Python 3.12+ (recommended 3.12)
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
- [requirements-profile-web.txt](requirements-profile-web.txt) - API + web-next integration profile
- [requirements-profile-vllm.txt](requirements-profile-vllm.txt) - API + vLLM profile
- [requirements-profile-onnx.txt](requirements-profile-onnx.txt) - API + ONNX LLM profile (third engine)
- [requirements-profile-onnx-cpu.txt](requirements-profile-onnx-cpu.txt) - API + ONNX CPU-only profile
- [requirements-extras-onnx.txt](requirements-extras-onnx.txt) - optional extras (`faster-whisper`, `piper-tts`), installed after ONNX LLM or ONNX CPU profile
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

Warning:
- Treat this mode as non-recommended at current stage (no full production validation yet).

### Lowest-memory configurations
| Configuration | Commands | Estimated RAM | Use case |
|--------------|----------|---------------|----------|
| Minimal | `make api` | ~50 MB | API tests / backend-only |
| Light with local LLM | `make api` + `make ollama-start` | ~450 MB | API + local model, no UI |
| Light with UI | `make api` + `make web` | ~550 MB | Demo and quick UI validation |
| Balanced | `make api` + `make web` + `make ollama-start` | ~950 MB | Day-to-day work without dev autoreload |
| Heaviest (dev) | `make api-dev` + `make web-dev` + `make vllm-start` | ~2.8 GB | Full development and local model testing |

## Key environment variables
Dev template: [.env.dev.example](.env.dev.example)
Preprod template: [.env.preprod.example](.env.preprod.example)

## Configuration panel (UI)
The panel at `http://localhost:3000/config` supports:
- service status monitoring (backend, UI, LLM, Hive, Nexus),
- start/stop/restart from UI,
- realtime metrics (PID, port, CPU, RAM, uptime),
- quick profiles: `Full Stack`, `Light`, `LLM OFF`.

### Parameter editing
- type/range validation,
- secret masking,
- active env file backup (`.env.dev` or `.env.preprod`) to `config/env-history/`,
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
- Security: GitGuardian + Snyk dependency scans.
- SonarCloud = code quality and coverage on new code (maintainability, reliability, test coverage).
- Snyk = package/dependency vulnerability posture (third-party risk in Python and npm ecosystems).
- `pre-commit run --all-files` runs: `block-docs-dev-staged`, `end-of-file-fixer`, `trailing-whitespace`, `check-added-large-files`, `check-yaml`, `debug-statements`, `ruff-check --fix`, `ruff-format`, `isort`.
- Extra hooks outside this command: `block-docs-dev-tracked` (stage `pre-push`) and `update-sonar-new-code-group` (stage `manual`).
- `pre-commit` can auto-fix files; rerun it until all hooks are `Passed`.
- Treat `mypy venom_core` as a full typing audit; the repository may include historical typing backlog not related to your change.
- Local PR sequence:

```bash
test -f .venv/bin/activate || { echo "Missing .venv/bin/activate. Create .venv first."; exit 1; }
source .venv/bin/activate
pre-commit run --all-files
make pr-fast
make check-new-code-coverage
```

## Roadmap
### ✅ v1.5
- [x] v1.4 features (planning, knowledge, memory, integrations).
- [x] The Academy (LoRA/QLoRA).
- [x] Workflow Control Plane.
- [x] Provider Governance.
- [x] Academy Hardening.

### ✅ v1.6
- [x] API contract hardening (Wave-1 + Wave-2 MVP) with OpenAPI/FE synchronization.
- [x] ONNX Runtime integrated as the third local LLM engine (3-stack: Ollama + vLLM + ONNX).
- [x] Runtime profiles and installation strategy update (minimal/API-first + optional local stacks).
- [x] Runtime control-plane improvements and provider/runtime governance stabilization.

### ✅ v1.7
- [x] Remote models capabilities delivered (`/models` remote tab + provider status/catalog/connectivity/validation for GPT/Gemini paths).
- [x] Global traffic-control hardening for inbound/outbound requests (limits, retry/circuit-breaker policies, safer runtime behavior under load).
- [x] Configuration/audit observability expanded (canonical audit stream and stronger operational visibility for config/runtime changes).
- [x] Academy/API hardening wave completed (module decomposition, contract consistency, safer upload/training/history paths).
- [x] Pre-prod operating model finalized on shared stack (data isolation, env split `.env.dev`/`.env.preprod`, Makefile control, guard rails, backup/restore/smoke).

### ✅ v1.8 (current)
- [x] Reduced operational and compliance risk by enforcing one consistent decision model for runtime execution.
- [x] Shortened incident triage time with clearer decision feedback, stronger audit visibility, and more actionable blocking context.
- [x] Improved execution safety for file and desktop automation, reducing failure rate and manual operator intervention.
- [x] Increased response quality and repeatability by stabilizing the learning path and unifying knowledge behavior.
- [x] Improved release predictability through stronger quality gates and explicit operational rollout-readiness validation.
- [x] Increased team delivery throughput with fewer ad-hoc exceptions, more consistent flows, and cleaner ownership handovers.

### 🚧 v1.9 (planned details)
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
