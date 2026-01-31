# THE STRATEGIST - Task Planning & Complexity Management (v2.0)

> [!NOTE]
> **Implementation Status:** The Strategy Screen has been postponed to **Venom 2.0**. In the current version (v1.0), it is hidden from the UI, while the agent operates in the background as a system component.

## Role

Strategist Agent is a planner and complexity analyst in the Venom system, responsible for assessing task difficulty, managing progress, detecting scope creep, and optimizing resource usage (API calls, tokens).

## Responsibilities

- **Complexity assessment** - Classifying tasks as TRIVIAL, SIMPLE, MODERATE, COMPLEX, VERY_COMPLEX
- **Task splitting** - Breaking down large tasks into smaller, executable parts
- **Progress monitoring** - Tracking execution vs. estimates (overrun detection)
- **Budget management** - Controlling API call and token limits
- **Warning** - Alerts about scope creep, budget overrun

## Key Components

### 1. Work Ledger (`venom_core/ops/work_ledger.py`)

**Role:** Task and project progress ledger.

**Functionality:**
- Task registration with complexity estimates
- Status tracking (PLANNED, IN_PROGRESS, COMPLETED, FAILED)
- Actual time vs. estimate comparison
- Overrun detection (budget exceeded)
- Report export (JSON)

**Usage example:**
```python
from venom_core.ops.work_ledger import WorkLedger, TaskComplexity

ledger = WorkLedger()

# Task registration
task_id = ledger.register_task(
    description="REST API implementation",
    estimated_complexity=TaskComplexity.MODERATE,
    estimated_time_minutes=120
)

# Status update
ledger.start_task(task_id)
# ... work ...
ledger.complete_task(task_id, success=True)

# Report
report = ledger.generate_report()
print(f"Completed tasks: {report['completed_tasks']}")
print(f"Total time: {report['total_time_minutes']} min")
```

### 2. Complexity Skill (`venom_core/execution/skills/complexity_skill.py`)

**Role:** Tool for assessing task complexity.

**Functionality:**
- `estimate_complexity(task_description)` - Complexity assessment (1-5)
- `split_task(task_description)` - Split into subtasks
- `detect_scope_creep(original_task, current_task)` - Detecting scope expansion

**Complexity scale:**
```python
class TaskComplexity(Enum):
    TRIVIAL = 1       # <15 min  - "Display Hello World"
    SIMPLE = 2        # 15-30 min - "Create file with function"
    MODERATE = 3      # 30-90 min - "REST API with 3 endpoints"
    COMPLEX = 4       # 1.5-3h - "TODO app with DB"
    VERY_COMPLEX = 5  # >3h - "E-commerce with payments"
```

### 3. API Budget Management

**Default limits (daily):**
```python
DEFAULT_API_LIMITS = {
    "openai": {
        "calls": 1000,
        "tokens": 1_000_000
    },
    "anthropic": {
        "calls": 500,
        "tokens": 500_000
    },
    "google": {
        "calls": 1000,
        "tokens": 1_000_000
    }
}
```

**Monitoring:**
- Tracking API calls per provider
- Tracking tokens (input + output)
- Alerts when approaching limit (>80%)
- Block on excess (requires approval)

## System Integration

### Execution Flow

```
User: "Create e-commerce shop"
        ↓
StrategistAgent.estimate_complexity()
        → VERY_COMPLEX (5/5)
        ↓
StrategistAgent.split_task()
        → [
            "Backend API (COMPLEX)",
            "Frontend (COMPLEX)",
            "Payment system (MODERATE)",
            "Product database (MODERATE)"
          ]
        ↓
WorkLedger.register_task(parent_task)
WorkLedger.register_task(subtask_1)
...
        ↓
ArchitectAgent plans each subtask separately
        ↓
Execution monitoring through Work Ledger
        ↓
Final report (time, costs, success)
```

### Collaboration with Other Agents

- **ArchitectAgent** - Receives task estimates and splits
- **Orchestrator** - Reports budget overruns and scope creep
- **AnalystAgent** - Provides cost and performance metrics
- **IntentManager** - Classifies intents as SIMPLE vs COMPLEX

## Usage Examples

### Example 1: Complexity Assessment
```python
strategist = StrategistAgent(kernel=kernel)

complexity = await strategist.estimate_complexity(
    "Create HTML page with digital clock"
)
# → TaskComplexity.SIMPLE (2/5)

complexity = await strategist.estimate_complexity(
    "Build e-learning platform with videos and quizzes"
)
# → TaskComplexity.VERY_COMPLEX (5/5)
```

### Example 2: Task Split
```python
subtasks = await strategist.split_task(
    "Create TODO app with FastAPI and PostgreSQL"
)
# → [
#     "Setup FastAPI + PostgreSQL (Docker Compose)",
#     "SQLAlchemy models for TODO",
#     "CRUD endpoints (GET, POST, PUT, DELETE)",
#     "Unit tests",
# ]
```

### Example 3: Scope Creep Detection
```python
original = "Create simple HTML page"
current = "Create responsive page with animations, forms and API integration"

scope_creep = await strategist.detect_scope_creep(original, current)
if scope_creep:
    # Alert: "Task has grown beyond original scope!"
```

## Configuration

```bash
# In .env (no dedicated flags for Strategist)
# API Limits configured in code or through environment variables

# Example custom limits:
OPENAI_DAILY_CALLS_LIMIT=500
OPENAI_DAILY_TOKENS_LIMIT=500000
```

## Metrics and Monitoring

**Key indicators:**
- Average estimate accuracy (actual_time / estimated_time)
- Overrun rate (% tasks exceeding estimate)
- API usage (calls/day, tokens/day per provider)
- Number of tasks with scope creep (% tasks)

**Work Ledger reports:**
```json
{
  "total_tasks": 15,
  "completed_tasks": 12,
  "failed_tasks": 1,
  "in_progress": 2,
  "total_time_minutes": 340,
  "average_complexity": 2.8,
  "overrun_tasks": 3
}
```

## Best Practices

1. **Estimate before planning** - Always call `estimate_complexity()` before ArchitectAgent
2. **Split large tasks** - VERY_COMPLEX (5/5) → split_task() → smaller parts
3. **Monitor budget** - Check API usage every 100 requests
4. **Document overrun** - Record reason for time overrun
5. **Scope freeze** - After plan approval don't expand scope without approval

## Known Limitations

- Estimates based on LLM heuristics (not always precise)
- No integration with actual API costs (only tracking calls/tokens)
- Work Ledger kept in memory (resets after restart)
- No automatic re-estimation after overrun detection

## See also

- [THE_ARCHITECT.md](THE_ARCHITECT.md) - Task planning
- [THE_HIVE.md](THE_HIVE.md) - Distributed task execution
- [COST_GUARD.md](COST_GUARD.md) - API budget protection
- [AGENTS_INDEX.md](AGENTS_INDEX.md) - Complete agent index
