# THE ARCHITECT - Strategic Planning & Task Decomposition

## Role

Architect Agent is the main strategic planner and project manager in the Venom system. It takes complex user goals and breaks them down into specific, executable steps, managing the orchestration of multiple specialized agents.

## Responsibilities

- **Strategic planning** - Decomposition of complex tasks into executable steps
- **Workflow management** - Determining sequence and dependencies between steps
- **Executor selection** - Assigning appropriate agents to specific tasks
- **Plan optimization** - Minimizing number of steps while maintaining completeness
- **Infrastructure management** - Planning multi-container environments (Docker Compose)

## Key Components

### 1. Planning Logic (`venom_core/agents/architect.py`)

**Available Executors:**
- `RESEARCHER` - Gathering knowledge from Internet, documentation, examples
- `CODER` - Code implementation, file creation, Docker Compose environments
- `LIBRARIAN` - File management, reading existing code
- `TOOLMAKER` - Creating new tools/skills for the system

**Planning Principles:**
1. Break down goal into small, specific steps (3-7 steps optimally)
2. Each step has one executor
3. Steps in logical sequence with defined dependencies
4. Tasks requiring technical knowledge start with RESEARCHER
5. Infrastructure (databases, cache) managed by CODER + ComposeSkill

**Plan Format (ExecutionPlan):**
```json
{
  "steps": [
    {
      "step_number": 1,
      "agent_type": "RESEARCHER",
      "instruction": "Find PyGame documentation on collisions and rendering",
      "depends_on": null
    },
    {
      "step_number": 2,
      "agent_type": "CODER",
      "instruction": "Create game.py file with basic Snake game structure",
      "depends_on": 1
    }
  ]
}
```

### 2. Plan Examples

**Example 1: Web application with database**
```
Task: "Create REST API with Redis cache"
Plan:
1. RESEARCHER - Find FastAPI and Redis client documentation
2. CODER - Create docker-compose.yml (api + redis) and launch stack
3. CODER - Implement API endpoints with Redis integration
```

**Example 2: PyGame game**
```
Task: "Create Snake game in PyGame"
Plan:
1. RESEARCHER - Find PyGame documentation (collisions, rendering)
2. CODER - Create game structure (main loop, classes)
3. CODER - Implement snake and food logic
4. CODER - Add scoring system and game over
```

**Example 3: New tool**
```
Task: "Add email sending capability"
Plan:
1. TOOLMAKER - Create EmailSkill with send_email, validate_email methods
2. CODER - Integrate EmailSkill with system
```

## System Integration

### Execution Flow

```
User: "Create TODO app with FastAPI + PostgreSQL"
        ↓
IntentManager: COMPLEX_PLANNING
        ↓
ArchitectAgent.plan_execution()
        ↓
ExecutionPlan (4 steps):
  1. RESEARCHER - FastAPI + PostgreSQL documentation
  2. CODER - docker-compose.yml + launch stack
  3. CODER - SQLAlchemy models + DB connection
  4. CODER - CRUD endpoints for TODO
        ↓
TaskDispatcher executes steps sequentially
        ↓
Result: Working application in Docker Compose
```

### Collaboration with Other Agents

- **TaskDispatcher** - Passes plan for execution step by step
- **ResearcherAgent** - Provides technical knowledge at project start
- **CoderAgent** - Implements code according to instructions
- **LibrarianAgent** - Checks existing files before starting work
- **ToolmakerAgent** - Creates missing tools on plan request

## Configuration

```bash
# In .env (no dedicated flags for Architect)
# Architect is always available in COMPLEX_PLANNING mode
```

## Metrics and Monitoring

**Key indicators:**
- Average number of steps in plan (optimally 3-7)
- Plan success rate (% plans completed without errors)
- Planning time (typically <10s)
- Usage of different agent types (RESEARCHER/CODER/LIBRARIAN balance)

## Best Practices

1. **Start with research** - Complex projects should have RESEARCHER step at beginning
2. **Infrastructure first** - Docker Compose stack before application code
3. **Small steps** - Better 5 small steps than 2 large ones
4. **Clear instructions** - Each step should be specific and understandable
5. **Dependencies** - Use `depends_on` to enforce order

## Known Limitations

- Plan is linear (no parallel step execution)
- No automatic plan optimization after step failure
- Maximum planning depth: 1 level (no nested subplans)

## See also

- [THE_CODER.md](THE_CODER.md) - Code implementation
- [THE_RESEARCHER.md](THE_RESEARCHER.md) - Knowledge gathering
- [THE_HIVE.md](THE_HIVE.md) - Distributed plan execution
- [INTENT_RECOGNITION.md](INTENT_RECOGNITION.md) - Intent classification
