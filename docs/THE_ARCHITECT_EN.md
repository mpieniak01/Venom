# THE ARCHITECT - Strategic Planning & Task Decomposition

## Role

The Architect Agent is the main strategic planner and project manager in the Venom system. It takes complex user goals and breaks them down into concrete, executable steps, managing the orchestration of multiple specialized agents.

## Responsibilities

- **Strategic Planning** - Decomposing complex tasks into executable steps
- **Workflow Management** - Determining order and dependencies between steps
- **Executor Selection** - Assigning appropriate agents to specific tasks
- **Plan Optimization** - Minimizing number of steps while maintaining completeness
- **Infrastructure Management** - Planning multi-container environments (Docker Compose)

## Key Components

### 1. Planning Logic (`venom_core/agents/architect.py`)

**Available Executors:**
- `RESEARCHER` - Gathering knowledge from Internet, documentation, examples
- `CODER` - Code implementation, file creation, Docker Compose environments
- `LIBRARIAN` - File management, reading existing code
- `TOOLMAKER` - Creating new tools/skills for the system

**Planning Principles:**
1. Break goal into small, concrete steps (3-7 steps optimally)
2. Each step has one executor
3. Steps in logical order with defined dependencies
4. Tasks requiring technological knowledge start with RESEARCHER
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

**Example 1: Web Application with Database**
```
Task: "Create REST API with Redis cache"
Plan:
1. RESEARCHER - Find FastAPI and Redis client documentation
2. CODER - Create docker-compose.yml (api + redis) and start stack
3. CODER - Implement API endpoints with Redis integration
```

**Example 2: PyGame Game**
```
Task: "Create Snake game in PyGame"
Plan:
1. RESEARCHER - Find PyGame documentation (collisions, rendering)
2. CODER - Create game structure (main loop, classes)
3. CODER - Implement snake and food logic
4. CODER - Add scoring system and game over
```

**Example 3: New Tool**
```
Task: "Add email sending capability"
Plan:
1. TOOLMAKER - Create EmailSkill with send_email, validate_email methods
2. CODER - Integrate EmailSkill with system
```

## Usage Examples

### Example 1: Complex Project Planning

```python
from venom_core.agents.architect import ArchitectAgent

architect = ArchitectAgent()

# Create plan for complex task
plan = await architect.create_plan(
    task="Build e-commerce website with payment integration"
)

print(f"Plan has {len(plan.steps)} steps:")
for step in plan.steps:
    print(f"{step.step_number}. {step.agent_type}: {step.instruction}")

# Output:
# Plan has 5 steps:
# 1. RESEARCHER: Find documentation for FastAPI and Stripe integration
# 2. CODER: Create docker-compose.yml with database and cache
# 3. CODER: Implement user authentication and product catalog
# 4. CODER: Integrate Stripe payment processing
# 5. CODER: Add shopping cart and order management
```

### Example 2: Plan Execution

```python
from venom_core.core.flows.orchestrator import Orchestrator

orchestrator = Orchestrator()

# Execute plan step by step
result = await orchestrator.execute_plan(plan)

print(f"Execution status: {result.status}")
print(f"Completed steps: {result.completed_steps}/{result.total_steps}")
```

### Example 3: Plan Validation

```python
# Validate plan before execution
validation = architect.validate_plan(plan)

if validation.is_valid:
    await orchestrator.execute_plan(plan)
else:
    print(f"Plan issues: {validation.issues}")
```

## Integration with Other Agents

### With Strategist
```python
# Strategist assesses complexity, Architect plans
complexity = await strategist.assess_complexity(task)

if complexity >= TaskComplexity.COMPLEX:
    plan = await architect.create_plan(task)
    result = await orchestrator.execute_plan(plan)
```

### With Researcher
```python
# Architect can request research for planning
knowledge = await researcher.research(
    "Best practices for microservices architecture"
)
plan = architect.create_plan_with_knowledge(task, knowledge)
```

## Advanced Features

### 1. Adaptive Planning

The Architect can modify plans during execution:

```python
# Start execution
execution = orchestrator.start_execution(plan)

# Monitor progress
while execution.is_running:
    status = await execution.get_status()
    
    if status.needs_replanning:
        # Adapt plan based on results
        new_plan = await architect.replan(
            original_plan=plan,
            completed_steps=status.completed_steps,
            new_requirements=status.new_requirements
        )
        await execution.update_plan(new_plan)
```

### 2. Parallel Execution

For independent steps:

```python
plan = await architect.create_plan(
    task="Build microservices system",
    allow_parallel=True
)

# Steps without dependencies can run in parallel
# Step 2 and 3 might run simultaneously if independent
```

### 3. Plan Optimization

```python
# Optimize plan for minimal steps
optimized_plan = architect.optimize_plan(
    plan=original_plan,
    objective="minimize_steps"
)

# Or optimize for cost
cost_optimized = architect.optimize_plan(
    plan=original_plan,
    objective="minimize_cost"
)
```

## Configuration

**Environment Variables** (`.env`):
```bash
# Planning settings
MAX_PLAN_STEPS=20
ENABLE_PARALLEL_EXECUTION=true
AUTO_OPTIMIZE_PLANS=true

# Agent timeouts
RESEARCHER_TIMEOUT=300
CODER_TIMEOUT=600
```

## Best Practices

### 1. Clear Task Description
❌ Bad: "Build an app"
✅ Good: "Build REST API for todo list with PostgreSQL database and user authentication"

### 2. Appropriate Complexity
- Use Architect for tasks with 3+ logical steps
- Simple tasks (<3 steps) can skip planning

### 3. Review Plans
```python
# Always review plan before execution
plan = await architect.create_plan(task)
print(plan.summary())  # Human-readable overview
if user_approves(plan):
    await orchestrator.execute_plan(plan)
```

### 4. Handle Failures
```python
try:
    result = await orchestrator.execute_plan(plan)
except PlanExecutionError as e:
    # Log failed step
    print(f"Failed at step {e.step_number}: {e.message}")
    
    # Attempt recovery
    remaining_steps = plan.steps[e.step_number:]
    recovery_plan = await architect.create_recovery_plan(remaining_steps)
```

## Metrics

```python
{
  "total_plans_created": 50,
  "average_steps_per_plan": 4.2,
  "successful_executions": 45,
  "failed_executions": 5,
  "average_planning_time_ms": 1200,
  "average_execution_time_ms": 15000
}
```

## API Reference

### ArchitectAgent Methods

```python
class ArchitectAgent:
    async def create_plan(
        self,
        task: str,
        allow_parallel: bool = False
    ) -> ExecutionPlan:
        """Create execution plan for task"""
        pass
    
    def validate_plan(
        self,
        plan: ExecutionPlan
    ) -> ValidationResult:
        """Validate plan structure and logic"""
        pass
    
    def optimize_plan(
        self,
        plan: ExecutionPlan,
        objective: str = "minimize_steps"
    ) -> ExecutionPlan:
        """Optimize plan for given objective"""
        pass
```

### ExecutionPlan Model

```python
@dataclass
class ExecutionPlan:
    steps: List[PlanStep]
    total_steps: int
    estimated_time_minutes: int
    requires_infrastructure: bool
    parallel_groups: Optional[List[List[int]]]
```

## Related Documentation

- [Strategist](THE_STRATEGIST.md)
- [Orchestrator](../core/flows/orchestrator.py)
- [ResearcherAgent](THE_RESEARCHER.md)
- [CoderAgent](THE_CODER.md)

---

**Version:** 1.0
**Last Updated:** 2024-12-30
