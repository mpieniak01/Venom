# Venom Agents Index - Complete List

## Overview

> **[Polska Wersja](../AGENTS_INDEX.md)**

The Venom system consists of 34 specialized agents, each responsible for a specific functionality area. Below you'll find the complete list with descriptions and links to detailed documentation.

> **Note:** This index has been translated to English. Individual agent documentation files (THE_*.md) are currently being translated. Links to untranslated files may not work yet.

## Agent Categories

### 🏗️ Planning and Architecture

| Agent | File | Documentation | Description |
|-------|------|--------------|------|
| **Architect** | `architect.py` | [THE_ARCHITECT.md](THE_ARCHITECT.md) | Strategic planning, complex task decomposition |
| **Strategist** | `strategist.py` | [THE_STRATEGIST.md](THE_STRATEGIST.md) | [v2.0] Complexity assessment, API budget management |
| **Executive** | `executive.py` | [THE_EXECUTIVE.md](THE_EXECUTIVE.md) | High-level orchestration, decision-making |

### 💻 Implementation and Code

| Agent | File | Documentation | Description |
|-------|------|--------------|------|
| **Coder** | `coder.py` | [THE_CODER.md](THE_CODER.md) | Code generation, Docker Compose, self-repair |
| **Critic** | `critic.py` | [THE_CRITIC.md](THE_CRITIC.md) | Code quality and security verification |
| **Toolmaker** | `toolmaker.py` | [THE_FORGE.md](THE_FORGE.md) | Creating new Skills/tools |

### 📚 Knowledge and Research

| Agent | File | Documentation | Description |
|-------|------|--------------|------|
| **Researcher** | `researcher.py` | [THE_RESEARCHER.md](THE_RESEARCHER.md) | Internet search, knowledge synthesis |
| **Librarian** | `librarian.py` | [THE_LIBRARIAN.md](THE_LIBRARIAN.md) | File management, project navigation |
| **Oracle** | `oracle.py` | [ORACLE_GRAPHRAG_GUIDE.md](../ORACLE_GRAPHRAG_GUIDE.md) | GraphRAG, project knowledge analysis |
| **Historian** | `historian.py` | - | Project history, change tracking |

### 🤖 User Interaction

| Agent | File | Documentation | Description |
|-------|------|--------------|------|
| **Chat** | `chat.py` | [THE_CHAT.md](THE_CHAT.md) | Conversational assistant, general questions |
| **Apprentice** | `apprentice.py` | [THE_APPRENTICE.md](THE_APPRENTICE.md) | Learning by observation, workflow recording |
| **Professor** | `professor.py` | [THE_ACADEMY.md](THE_ACADEMY.md) | User education, concept explanations |

### 🎨 Creativity and Design

| Agent | File | Documentation | Description |
|-------|------|--------------|------|
| **Creative Director** | `creative_director.py` | - | Branding, marketing, AI art prompts |
| **Designer** | `designer.py` | - | UI/UX design, prototypes |
| **UX Analyst** | `ux_analyst.py` | - | User experience analysis |

### 🔧 DevOps and Infrastructure

| Agent | File | Documentation | Description |
|-------|------|--------------|------|
| **Integrator** | `integrator.py` | [THE_INTEGRATOR.md](THE_INTEGRATOR.md) | Git, GitHub Issues, Pull Requests |
| **DevOps** | `devops.py` | - | CI/CD, deployment, monitoring |
| **System Engineer** | `system_engineer.py` | - | System configuration, infrastructure |
| **Operator** | `operator.py` | - | Runtime operations, maintenance |
| **Release Manager** | `release_manager.py` | [THE_LAUNCHPAD.md](THE_LAUNCHPAD.md) | Release management, CHANGELOG |

### 🧪 Testing and Quality

| Agent | File | Documentation | Description |
|-------|------|--------------|------|
| **Tester** | `tester.py` | - | Unit and integration test generation |
| **Guardian** | `guardian.py` | [GUARDIAN_GUIDE.md](../GUARDIAN_GUIDE.md) | Security, sandbox verification |
| **Analyst** | `analyst.py` | - | Performance analysis, metrics, costs |

### 📝 Documentation and Cleanup

| Agent | File | Documentation | Description |
|-------|------|--------------|------|
| **Documenter** | `documenter.py` | - | Documentation generation, docstrings |
| **Gardener** | `gardener.py` | - | Refactoring, code cleanup |
| **Foreman** | `foreman.py` | - | Project build task management |
| **Publisher** | `publisher.py` | - | Artifact publication, release notes |

### 🤝 External Integrations

| Agent | File | Documentation | Description |
|-------|------|--------------|------|
| **Simulated User** | `simulated_user.py` | - | User simulation for E2E tests |
| **Ghost Agent** | `ghost_agent.py` | [GHOST_AGENT.md](GHOST_AGENT.md) | GUI automation (RPA) |
| **Shadow** | `shadow.py` | [THE_SHADOW.md](THE_SHADOW.md) | Desktop awareness, proactive help |

### ⏰ Time and Monitoring

| Agent | File | Documentation | Description |
|-------|------|--------------|------|
| **Time Assistant** | `time_assistant.py` | [THE_CHRONOMANCER.md](THE_CHRONOMANCER.md) | Time management, schedules |
| **System Status** | `system_status.py` | [THE_OVERMIND.md](THE_OVERMIND.md) | System status monitoring, health checks |

### 🌐 Distributed Architecture

| Concept | Documentation | Description |
|-----------|--------------|------|
| **The Hive** | [THE_HIVE.md](THE_HIVE.md) | Distributed architecture with Redis |
| **The Nexus** | - | Master-worker mesh, distributed execution |
| **The Council** | [THE_COUNCIL.md](THE_COUNCIL.md) | Collective management, consensus |

## Agents Without Dedicated Documentation

The following agents exist in code but don't yet have dedicated documentation files (13 of 34):

- **Analyst** (`analyst.py`) - Performance and cost analysis
- **Creative Director** (`creative_director.py`) - Branding and marketing
- **Designer** (`designer.py`) - UI/UX design
- **DevOps** (`devops.py`) - CI/CD and deployment
- **Documenter** (`documenter.py`) - Documentation generation
- **Foreman** (`foreman.py`) - Build task management
- **Gardener** (`gardener.py`) - Refactoring and cleanup
- **Historian** (`historian.py`) - Project history
- **Operator** (`operator.py`) - Runtime operations
- **Publisher** (`publisher.py`) - Artifact publication
- **Simulated User** (`simulated_user.py`) - User simulation
- **System Engineer** (`system_engineer.py`) - System configuration
- **Tester** (`tester.py`) - Test generation
- **UX Analyst** (`ux_analyst.py`) - UX analysis

## How to Choose the Right Agent?

### I want to...

**Write code** → **Coder** + **Critic** (review)
**Find information** → **Researcher** (Internet) or **Librarian** (local files)
**Plan project** → **Architect** (plan) + **Strategist** (complexity assessment)
**Create new tool** → **Toolmaker** (THE_FORGE)
**Manage repository** → **Integrator** (Git, PR, Issues)
**Chat** → **Chat** (general questions)
**Automate GUI** → **Ghost Agent** (RPA)
**Test** → **Tester** (generation) + **Guardian** (sandbox)
**Document** → **Documenter** (docstrings) + **Publisher** (release notes)
**Teach system** → **Apprentice** (workflow recording)

## Workflows

### 1. Complex Project (E2E)
```
User Request → IntentManager (COMPLEX_PLANNING)
            → Architect (plan: 5 steps)
            → Strategist (estimate: COMPLEX, 3h)
            → Researcher (find docs)
            → Coder (implement)
            → Critic (review)
            → Tester (generate tests)
            → Guardian (sandbox verify)
            → Integrator (commit, PR)
```

### 2. Simple Question
```
User: "What is the capital of France?"
→ IntentManager (GENERAL_CHAT)
→ Chat Agent
→ Answer: "Paris"
```

### 3. New Tool
```
User: "Add weather checking capability"
→ Architect detects missing tool
→ Toolmaker creates WeatherSkill
→ Critic reviews code
→ SkillManager loads skill
→ System: "Skill loaded. You can use get_weather()"
```

## Agent System Metrics

**General statistics:**
- Number of agents: **34**
- With `THE_*.md` documentation or dedicated files: **21** (62%)
- Without documentation: **13** (38%)
- Categories: **10**

**Most used:**
1. **Coder** - Code generation
2. **Chat** - User conversations
3. **Researcher** - Information search
4. **Architect** - Project planning
5. **Integrator** - Git and GitHub

## See also

- [BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md) - Backend architecture
- [INTENT_RECOGNITION.md](INTENT_RECOGNITION.md) - Intent classification

*Note: Additional documentation files (VENOM_MASTER_VISION_V1.md, THE_HIVE.md) are currently being translated.*
