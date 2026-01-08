# THE STRATEGIST - Task Planning & Complexity Management

## Role

The Strategist Agent is the planner and complexity analyst in the Venom system, responsible for assessing task difficulty, managing progress, detecting scope creep, and optimizing resource usage (API calls, tokens).

## Responsibilities

- **Complexity Assessment** - Classifying tasks as TRIVIAL, SIMPLE, MODERATE, COMPLEX, VERY_COMPLEX
- **Task Division** - Breaking down large tasks into smaller, executable parts
- **Progress Monitoring** - Tracking execution vs. estimates (overrun detection)
- **Budget Management** - Controlling API call and token limits
- **Warnings** - Alerts about scope creep, budget overruns

## Key Components

### 1. Work Ledger (`venom_core/ops/work_ledger.py`)

**Role:** Task and project progress ledger.

**Functionality:**
- Task registration with complexity estimates
- Status tracking (PLANNED, IN_PROGRESS, COMPLETED, FAILED)
- Comparing actual time vs. estimate
- Overrun detection (budget exceeding)
- Report export (JSON)

**Usage Example:**
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

### 2. Cost Guard (`venom_core/ops/cost_guard.py`)

**Role:** API call and token budget control.

**Functionality:**
- Setting limits per provider (OpenAI, Google, Anthropic)
- Real-time usage tracking
- Threshold alerts (50%, 75%, 90%)
- Budget enforcement (hard stop at 100%)
- Cost reports

**Usage Example:**
```python
from venom_core.ops.cost_guard import CostGuard

guard = CostGuard()

# Set budget
guard.set_budget(
    provider="openai",
    max_tokens=100000,
    max_cost_usd=10.0
)

# Track usage
guard.track_usage(
    provider="openai",
    tokens_used=1500,
    cost_usd=0.03
)

# Check status
status = guard.get_status("openai")
print(f"Token usage: {status['tokens_used']}/{status['max_tokens']}")
print(f"Budget: ${status['cost_used']:.2f}/${status['max_cost']:.2f}")
```

📖 **Full documentation:** [COST_GUARD.md](COST_GUARD.md)

### 3. Complexity Classifier

**Role:** Automatic task complexity assessment.

**Classification:**
- **TRIVIAL** (1) - Single operation, <30s
  - Example: "What time is it?"
- **SIMPLE** (2) - Few operations, <2 min
  - Example: "Create hello.txt file"
- **MODERATE** (3) - Multiple steps, 5-15 min
  - Example: "Create REST API with 3 endpoints"
- **COMPLEX** (4) - Many steps, 30-60 min
  - Example: "Build web scraper with database"
- **VERY_COMPLEX** (5) - Project, >60 min
  - Example: "Create microservices application"

**Classifier Logic:**
```python
class ComplexityClassifier:
    def classify(self, task_description: str) -> TaskComplexity:
        # Analyzes:
        # - Number of verbs (actions)
        # - Technical keywords
        # - File/component count
        # - Technology stack
        # - Integration requirements
        pass
```

### 4. Overrun Detector

**Role:** Detecting when task exceeds estimates.

**Functionality:**
- Comparing actual time vs. estimate
- Detecting scope creep (task grows during execution)
- Warnings about potential problems
- Recommendations for task splitting

**Example:**
```python
from venom_core.ops.overrun_detector import OverrunDetector

detector = OverrunDetector(ledger)

# Check during execution
if detector.is_overrun(task_id):
    warning = detector.get_warning(task_id)
    print(f"Warning: {warning.message}")
    print(f"Actual: {warning.actual_time} vs Estimated: {warning.estimated_time}")
    print(f"Recommendation: {warning.recommendation}")
```

## Workflow

```
New Task
    ↓
ComplexityClassifier
    ↓
Complexity Assessment (TRIVIAL to VERY_COMPLEX)
    ↓
WorkLedger - Task Registration
    ↓
Execution Start
    ↓
┌────────────────────┬────────────────────┬────────────────────┐
│  Progress Monitor  │   Cost Guard       │  Overrun Detector  │
├────────────────────┼────────────────────┼────────────────────┤
│  Time tracking     │   API tracking     │  Time comparison   │
│  Status updates    │   Token tracking   │  Scope detection   │
│                    │   Budget alerts    │  Warnings          │
└────────────────────┴────────────────────┴────────────────────┘
    ↓
Task Completion
    ↓
Report Generation
```

## Usage Examples

### Example 1: Simple Task Assessment
```python
from venom_core.agents.strategist import StrategistAgent

strategist = StrategistAgent()

# Assess task
assessment = await strategist.assess_task(
    "Create a Python function to sort a list"
)

print(f"Complexity: {assessment.complexity}")  # SIMPLE
print(f"Estimated time: {assessment.estimated_minutes} min")  # ~5 min
print(f"Recommended approach: {assessment.approach}")
```

### Example 2: Complex Project Planning
```python
# Complex task
assessment = await strategist.assess_task(
    "Build e-commerce platform with user auth, shopping cart, and payment"
)

print(f"Complexity: {assessment.complexity}")  # VERY_COMPLEX
print(f"Should split: {assessment.should_split}")  # True
print(f"Subtasks: {assessment.subtasks}")
# Subtasks:
# 1. User authentication system
# 2. Product catalog
# 3. Shopping cart
# 4. Payment integration
# 5. Order management
```

### Example 3: Budget Management
```python
# Set project budget
strategist.set_project_budget(
    max_tokens=500000,
    max_cost_usd=50.0,
    max_time_minutes=480  # 8 hours
)

# Execute with monitoring
result = await strategist.execute_with_monitoring(
    task="Build REST API",
    check_interval=60  # Check every minute
)

# Warnings if needed
if result.warnings:
    for warning in result.warnings:
        print(f"⚠️ {warning}")
```

### Example 4: Progress Tracking
```python
# Start task
task_id = strategist.start_task("Implement user authentication")

# Update progress
strategist.update_progress(task_id, progress=0.3)  # 30%
strategist.update_progress(task_id, progress=0.6)  # 60%

# Complete
strategist.complete_task(task_id, success=True)

# Report
report = strategist.get_task_report(task_id)
print(f"Duration: {report.duration_minutes} min")
print(f"Complexity was: {report.actual_complexity}")
```

## Configuration

**Environment Variables** (`.env`):
```bash
# Budget defaults
DEFAULT_MAX_TOKENS=100000
DEFAULT_MAX_COST_USD=10.0
DEFAULT_MAX_TIME_MINUTES=60

# Overrun thresholds
OVERRUN_WARNING_THRESHOLD=1.2  # 120% of estimate
OVERRUN_CRITICAL_THRESHOLD=1.5  # 150% of estimate

# Complexity settings
AUTO_SPLIT_THRESHOLD=4  # Auto-split tasks with complexity >= 4
```

## Integration with Other Agents

### With ArchitectAgent
```python
# Strategist assesses, Architect plans
complexity = await strategist.assess_complexity(task)

if complexity >= TaskComplexity.COMPLEX:
    # Let Architect create detailed plan
    plan = await architect.create_plan(task)
else:
    # Direct execution
    result = await coder.execute(task)
```

### With CoderAgent
```python
# Strategist monitors Coder's work
task_id = strategist.start_task("Implement API")

try:
    code = await coder.generate_code(task)
    strategist.complete_task(task_id, success=True)
except Exception as e:
    strategist.complete_task(task_id, success=False, error=str(e))
```

## Quality Metrics

```python
{
  "total_tasks": 150,
  "completed_tasks": 142,
  "failed_tasks": 8,
  "average_accuracy": 0.89,  # Estimate vs actual
  "overrun_rate": 0.12,      # 12% tasks exceeded estimates
  "total_tokens_used": 450000,
  "total_cost_usd": 8.50
}
```

## Best Practices

### 1. Accurate Task Descriptions
❌ Bad: "Fix the app"
✅ Good: "Fix authentication bug in login endpoint - users can't login with Gmail OAuth"

### 2. Regular Budget Reviews
```python
# Check budget daily/weekly
status = strategist.get_budget_status()
if status.usage_percent > 70:
    print("⚠️ Budget 70% used - review remaining tasks")
```

### 3. Split Large Tasks
```python
# For COMPLEX/VERY_COMPLEX tasks
if assessment.complexity >= TaskComplexity.COMPLEX:
    subtasks = strategist.split_task(task)
    for subtask in subtasks:
        execute(subtask)
```

### 4. Track Patterns
```python
# Learn from history
patterns = strategist.analyze_patterns()
# "Authentication tasks usually take 15min, not 5min"
# "API tasks often need 2x estimated tokens"
```

## Error Handling

```python
try:
    assessment = await strategist.assess_task(task)
except InvalidTaskError:
    # Task description too vague
    task = await clarify_task(task)
except BudgetExceededError:
    # Stop execution
    await notify_user("Budget exceeded")
except OverrunError as e:
    # Task taking too long
    decision = await ask_user(f"Task overrun: {e.message}. Continue?")
```

## Troubleshooting

### Problem: Inaccurate complexity estimates
**Solution:**
- Provide more detailed task descriptions
- Review historical data
- Adjust complexity thresholds in config

### Problem: Frequent budget overruns
**Solution:**
- Increase buffers (multiply estimates by 1.5x)
- Use cheaper models for simple tasks
- Implement caching for repeated queries

### Problem: Scope creep detection failing
**Solution:**
- More granular progress updates
- Better task decomposition
- Stricter task boundaries

## Advanced Features

### 1. Predictive Analysis
```python
# Predict task duration based on history
prediction = strategist.predict_duration(
    task="Implement user profile page",
    based_on_similar_tasks=True
)
```

### 2. Resource Optimization
```python
# Choose optimal model for task complexity
model = strategist.recommend_model(complexity)
# TRIVIAL/SIMPLE → local model (Ollama)
# COMPLEX → cloud model (GPT-4)
```

### 3. Multi-project Management
```python
# Manage multiple projects
strategist.create_project("Project A")
strategist.create_project("Project B")

# Allocate budgets
strategist.allocate_budget("Project A", tokens=200000, cost=20)
strategist.allocate_budget("Project B", tokens=300000, cost=30)
```

## API Reference

### StrategistAgent Methods

```python
class StrategistAgent:
    async def assess_task(
        self,
        task_description: str
    ) -> TaskAssessment:
        """Assess task complexity"""
        pass
    
    async def split_task(
        self,
        task_description: str
    ) -> List[str]:
        """Split complex task into subtasks"""
        pass
    
    def set_budget(
        self,
        max_tokens: int,
        max_cost_usd: float,
        max_time_minutes: int
    ) -> None:
        """Set resource budgets"""
        pass
    
    def track_progress(
        self,
        task_id: str,
        progress: float
    ) -> ProgressStatus:
        """Track task progress"""
        pass
```

### TaskAssessment Model

```python
@dataclass
class TaskAssessment:
    complexity: TaskComplexity          # TRIVIAL to VERY_COMPLEX
    estimated_minutes: int              # Time estimate
    estimated_tokens: int               # Token estimate
    should_split: bool                  # Should task be split
    subtasks: Optional[List[str]]       # Suggested subtasks
    approach: str                       # Recommended approach
    risks: List[str]                    # Identified risks
```

## Related Documentation

- [Cost Guard](COST_GUARD.md)
- [ArchitectAgent](THE_ARCHITECT.md)
- [Orchestrator](../core/flows/orchestrator.py)
- [Work Ledger](../ops/work_ledger.py)

---

**Version:** 1.0
**Last Updated:** 2024-12-30
