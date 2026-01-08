# Venom Agents Index - Complete List

## Overview

The Venom system consists of 34 specialized agents, each responsible for a specific area of functionality. Below you'll find a complete list with descriptions and links to detailed documentation.

## Agent Categories

### 🏗️ Planning and Architecture

| Agent | File | Documentation | Description |
|-------|------|--------------|-------------|
| **Architect** | `architect.py` | [THE_ARCHITECT.md](THE_ARCHITECT.md) | Strategic planning, complex task decomposition |
| **Strategist** | `strategist.py` | [THE_STRATEGIST.md](THE_STRATEGIST.md) | Complexity assessment, API budget management |
| **Executive** | `executive.py` | [THE_EXECUTIVE.md](THE_EXECUTIVE.md) | High-level orchestration, decision-making |

### 💻 Implementation and Code

| Agent | File | Documentation | Description |
|-------|------|--------------|-------------|
| **Coder** | `coder.py` | [THE_CODER.md](THE_CODER.md) | Code generation, Docker Compose, self-repair |
| **Critic** | `critic.py` | [THE_CRITIC.md](THE_CRITIC.md) | Code quality and security verification |
| **Toolmaker** | `toolmaker.py` | [THE_FORGE.md](THE_FORGE.md) | Creating new Skills/tools |

### 📚 Knowledge and Research

| Agent | File | Documentation | Description |
|-------|------|--------------|-------------|
| **Researcher** | `researcher.py` | [THE_RESEARCHER.md](THE_RESEARCHER.md) | Internet search, knowledge synthesis |
| **Librarian** | `librarian.py` | [THE_LIBRARIAN.md](THE_LIBRARIAN.md) | File management, project navigation |
| **Oracle** | `oracle.py` | [ORACLE_GRAPHRAG_GUIDE.md](ORACLE_GRAPHRAG_GUIDE.md) | GraphRAG, project knowledge analysis |
| **Historian** | `historian.py` | - | Project history, change tracking |

### 🤖 User Interaction

| Agent | File | Documentation | Description |
|-------|------|--------------|-------------|
| **Chat** | `chat.py` | [THE_CHAT.md](THE_CHAT.md) | Conversational assistant, general questions |
| **Apprentice** | `apprentice.py` | [THE_APPRENTICE.md](THE_APPRENTICE.md) | Learning by observation, workflow recording |
| **Professor** | `professor.py` | [THE_ACADEMY.md](THE_ACADEMY.md) | User education, concept explanations |

### 🎨 Creativity and Design

| Agent | File | Documentation | Description |
|-------|------|--------------|-------------|
| **Creative Director** | `creative_director.py` | - | Branding, marketing, AI art prompts |
| **Designer** | `designer.py` | - | UI/UX design, prototypes |
| **Writer** | `writer.py` | - | Copywriting, marketing content |
| **UX Analyst** | `ux_analyst.py` | - | User experience analysis |

### 🔧 DevOps and Infrastructure

| Agent | File | Documentation | Description |
|-------|------|--------------|-------------|
| **Integrator** | `integrator.py` | [THE_INTEGRATOR.md](THE_INTEGRATOR.md) | Git, GitHub Issues, Pull Requests |
| **DevOps** | `devops.py` | - | CI/CD, deployment, monitoring |
| **System Engineer** | `system_engineer.py` | - | System configuration, infrastructure |
| **Operator** | `operator.py` | - | Runtime operations, maintenance |
| **Release Manager** | `release_manager.py` | [THE_LAUNCHPAD.md](THE_LAUNCHPAD.md) | Release management, CHANGELOG |

### 🧪 Testing and Quality

| Agent | File | Documentation | Description |
|-------|------|--------------|-------------|
| **Tester** | `tester.py` | - | Unit and integration test generation |
| **Guardian** | `guardian.py` | [GUARDIAN_GUIDE.md](GUARDIAN_GUIDE.md) | Security, sandbox verification |
| **Analyst** | `analyst.py` | - | Performance analysis, metrics, costs |

### 📝 Documentation and Maintenance

| Agent | File | Documentation | Description |
|-------|------|--------------|-------------|
| **Documenter** | `documenter.py` | - | Documentation generation, docstrings |
| **Gardener** | `gardener.py` | - | Refactoring, code cleanup |
| **Foreman** | `foreman.py` | - | Project build task management |
| **Publisher** | `publisher.py` | - | Artifact publishing, release notes |

### 🤝 External Integrations

| Agent | File | Documentation | Description |
|-------|------|--------------|-------------|
| **Simulated User** | `simulated_user.py` | - | User simulation for E2E tests |
| **Ghost Agent** | `ghost_agent.py` | [GHOST_AGENT.md](GHOST_AGENT.md) | GUI automation (RPA) |
| **Shadow** | `shadow.py` | [THE_SHADOW.md](THE_SHADOW.md) | Desktop awareness, proactive help |

### ⏰ Time and Monitoring

| Agent | File | Documentation | Description |
|-------|------|--------------|-------------|
| **Time Assistant** | `time_assistant.py` | [THE_CHRONOMANCER.md](THE_CHRONOMANCER.md) | Time management, schedules |
| **System Status** | `system_status.py` | [THE_OVERMIND.md](THE_OVERMIND.md) | System state monitoring, health checks |

### 🌐 Distributed Architecture

| Concept | Documentation | Description |
|---------|--------------|-------------|
| **The Hive** | [THE_HIVE.md](THE_HIVE.md) | Distributed architecture with Redis |
| **The Nexus** | - | Master-worker mesh, distributed execution |
| **The Council** | [THE_COUNCIL.md](THE_COUNCIL.md) | Collective management, consensus |

## Agent Interaction Patterns

### Sequential Flow
```
User → Chat Agent → Orchestrator → Specialist Agent → Result
```

### Collaborative Flow
```
User → Architect (planning)
     → Researcher (gather knowledge)
     → Coder (implementation)
     → Critic (verification)
     → Result
```

### Autonomous Flow
```
Shadow (monitors) → detects need
                  → activates appropriate agent
                  → executes proactively
                  → reports to user
```

## Agent Selection Logic

The **Orchestrator** selects agents based on:

1. **Intent Classification**
   - RESEARCH → ResearcherAgent
   - CODE_GENERATION → CoderAgent
   - COMPLEX_PLANNING → ArchitectAgent
   - KNOWLEDGE_SEARCH → LibrarianAgent + MemorySkill
   - GENERAL_CHAT → ChatAgent

2. **Task Complexity**
   - TRIVIAL/SIMPLE → Direct execution (CoderAgent, ChatAgent)
   - MODERATE/COMPLEX → Planning layer (ArchitectAgent → specialists)
   - VERY_COMPLEX → Multi-agent collaboration

3. **Context & History**
   - Previous tasks in session
   - User preferences
   - Success patterns

## Core Agents (Always Active)

These agents are fundamental to the system:

1. **Orchestrator** - Main coordinator
2. **ChatAgent** - User interface
3. **IntentManager** - Intent classification
4. **MemorySkill** - Knowledge retrieval

## Specialized Agents (On-Demand)

Activated when needed:

- **ResearcherAgent** - For web searches and knowledge synthesis
- **CoderAgent** - For code generation
- **ArchitectAgent** - For complex task planning
- **CriticAgent** - For code quality checks
- **GhostAgent** - For GUI automation
- **etc.**

## Agent Communication

### Via Orchestrator (Centralized)
```python
# Orchestrator coordinates
result = await orchestrator.execute(
    task="Build REST API",
    agents=["architect", "researcher", "coder", "critic"]
)
```

### Direct Collaboration (Peer-to-Peer)
```python
# ArchitectAgent calls ResearcherAgent directly
knowledge = await self.researcher.research(
    "FastAPI best practices for async routes"
)
```

### Event-Based (Pub/Sub)
```python
# Agent publishes event
await event_bus.publish("task_completed", data)

# Other agents can subscribe
@event_bus.subscribe("task_completed")
async def on_task_completed(data):
    # React to event
    pass
```

## Agent Development Guidelines

### Creating a New Agent

1. **Choose a clear responsibility**
   - Single, well-defined purpose
   - Unique from existing agents
   - Fits into agent categories

2. **Implement base interface**
   ```python
   from venom_core.agents.base import BaseAgent
   
   class MyNewAgent(BaseAgent):
       def __init__(self):
           super().__init__(name="MyNewAgent")
       
       async def execute(self, task: str) -> Result:
           # Implementation
           pass
   ```

3. **Add required skills**
   - Identify needed skills (WebSearch, Shell, etc.)
   - Register skills in agent constructor
   - Use skills in execute method

4. **Write documentation**
   - Create `docs/THE_MYNEWAGENT.md`
   - Document responsibilities, usage, examples
   - Add to this index

5. **Add tests**
   - Unit tests in `tests/test_agents/`
   - Integration tests if needed
   - Mock external dependencies

### Best Practices

- **Single Responsibility**: One agent, one main purpose
- **Loose Coupling**: Agents should be independent
- **Clear Interface**: Well-defined inputs/outputs
- **Error Handling**: Graceful degradation
- **Logging**: Comprehensive logging for debugging
- **Metrics**: Track success rate, performance

## Agent Metrics

Each agent tracks:
```python
{
  "total_tasks": 150,
  "successful_tasks": 142,
  "failed_tasks": 8,
  "average_duration_ms": 2340,
  "average_tokens_used": 1500,
  "success_rate": 0.947
}
```

## Future Agents (Roadmap)

Planned additions:

- **The Analyst** - Data analysis and visualization
- **The Mediator** - Conflict resolution between agents
- **The Optimizer** - Performance optimization specialist
- **The Debugger** - Advanced debugging and troubleshooting
- **The Translator** - Multi-language content translation
- **The Validator** - Input/output validation specialist

## Related Documentation

- [System Architecture](VENOM_MASTER_VISION_V1.md) *(Polish only)*
- [Orchestrator](../core/flows/orchestrator.py)
- [Intent Recognition](INTENT_RECOGNITION.md) *(Polish only)*
- [Skills System](SKILLS_ENHANCEMENTS_SUMMARY.md) *(Polish only)*

---

**Total Agents:** 34
**Categories:** 10
**Last Updated:** 2024-12-30

For detailed documentation on specific agents, click on the links in the tables above.
