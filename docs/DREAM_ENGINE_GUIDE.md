# THE DREAMER - Dream Engine Guide (v2.0)

> [!IMPORTANT]
> **Implementation Status:** The development of the "Dream Engine" concept has been officially postponed to **Venom 2.0**.
> In the current version (v1.0), this system is disabled by default (`ENABLE_DREAMING=False`), and this documentation serves as a reference for future work.

## Introduction

**THE DREAMER** (Synthetic Experience Replay & Imagination Engine) is a revolutionary "active dreaming" system in Venom. During idle time or night hours, Venom uses the knowledge acquired by the Oracle to generate hypothetical programming scenarios, solves them in an isolated environment, and, upon success, automatically adds these experiences to its training set.

## Architecture

### Components

1. **DreamEngine** (`venom_core/core/dream_engine.py`)
   - Main engine orchestrating the dreaming process.
   - Manages REM (Rapid Eye Movement) phases.
   - Integrates all components into a coherent workflow.

2. **ScenarioWeaver** (`venom_core/simulation/scenario_weaver.py`)
   - Creative agent generating programming tasks.
   - Uses Few-Shot Chain of Thought for quality.
   - Creates realistic test cases.

3. **EnergyManager** (`venom_core/core/energy_manager.py`)
   - Monitors system resources (CPU, RAM, temperature).
   - Detects user activity.
   - Immediately terminates dreaming when the user returns.

4. **Guardian** (Extended)
   - Ultra-strict validation of synthetic code.
   - 100% quality threshold for saved dreams.
   - Integration with LessonsStore.

## Dreaming Workflow

### Phase 1: Trigger
Dreaming can be triggered by:
- **Nightly Dreams**: Cron schedule (e.g., 2:00-6:00).
- **Idle Dreams**: After 30 minutes of inactivity.
- **Manual**: API call to `enter_rem_phase()`.

### Phase 2: Knowledge Retrieval
```python
# DreamEngine retrieves knowledge clusters from GraphRAG
knowledge_fragments = await dream_engine._get_knowledge_clusters(count=10)
# Fragments are sorted by importance (number of connections in the graph)
```

### Phase 3: Scenario Generation
```python
# ScenarioWeaver creates programming tasks
scenarios = await scenario_weaver.weave_multiple_scenarios(
    knowledge_fragments,
    count=10,
    difficulty="medium"
)
```

**Example generated scenario:**
```json
{
  "title": "Concurrent Web Scraper with Rate Limiting",
  "description": "Scraper downloading 50 pages simultaneously with a limit of 5 requests/second",
  "task_prompt": "Write an async scraper using aiohttp...",
  "test_cases": [
    "All 50 URLs downloaded in <15 seconds",
    "Rate limiting: max 5 requests at the same time",
    "Timeout after 5 seconds for a single URL"
  ],
  "difficulty": "complex",
  "libraries": ["aiohttp", "asyncio"]
}
```

### Phase 4: Dream Realization
```python
# For each scenario:
# 1. CoderAgent generates code
code = await coder_agent.process(scenario.task_prompt)

# 2. Guardian validates (ultra-strict mode)
validation = await guardian_agent.process(validation_prompt)

# 3. If PASS -> save to LessonsStore + synthetic_training/
if is_valid:
    lessons_store.add_lesson(
        situation=scenario.description,
        action=code,
        result="✅ Success",
        tags=["synthetic", "dream", *scenario.libraries],
        metadata={"synthetic": True}
    )
```

### Phase 5: Interruption (Wake Up)
```python
# EnergyManager monitors resources in the background
if cpu_usage > 70% or user_active:
    await energy_manager.wake_up()
    # → dream_engine.state = INTERRUPTED
    # → all dreaming processes stopped in <2s
```

## Configuration

### `.env` File
```bash
# THE DREAMER Configuration
ENABLE_DREAMING=true
DREAMING_IDLE_THRESHOLD_MINUTES=30
DREAMING_NIGHT_HOURS=2-6
DREAMING_MAX_SCENARIOS=10
DREAMING_CPU_THRESHOLD=0.7
DREAMING_MEMORY_THRESHOLD=0.8
DREAMING_SCENARIO_COMPLEXITY=medium
DREAMING_VALIDATION_STRICT=true
DREAMING_OUTPUT_DIR=./data/synthetic_training
DREAMING_DOCKER_NAMESPACE=venom-dream-worker
DREAMING_PROCESS_PRIORITY=19
```

### Parameters

| Parameter | Description | Default Value |
|----------|-------------|---------------|
| `ENABLE_DREAMING` | Enable/disable the dreaming system | `false` |
| `DREAMING_IDLE_THRESHOLD_MINUTES` | Inactivity time before dreaming starts | `30` |
| `DREAMING_NIGHT_HOURS` | Night dreaming hours | `"2-6"` |
| `DREAMING_MAX_SCENARIOS` | Max scenarios per session | `10` |
| `DREAMING_CPU_THRESHOLD` | CPU threshold for interruption (0-1) | `0.7` |
| `DREAMING_MEMORY_THRESHOLD` | RAM threshold for interruption (0-1) | `0.8` |
| `DREAMING_SCENARIO_COMPLEXITY` | Complexity: simple/medium/complex | `"medium"` |
| `DREAMING_VALIDATION_STRICT` | Ultra-strict validation | `true` |
| `DREAMING_OUTPUT_DIR` | Output directory | `./data/synthetic_training` |
| `DREAMING_DOCKER_NAMESPACE` | Namespace for containers | `"venom-dream-worker"` |
| `DREAMING_PROCESS_PRIORITY` | Process priority (0-19) | `19` |

## Usage

### 1. Scheduling Nightly Dreaming

```python
from venom_core.core.scheduler import BackgroundScheduler
from venom_core.core.dream_engine import DreamEngine

# Initialization
scheduler = BackgroundScheduler()
dream_engine = DreamEngine(kernel, graph_rag, lessons_store, energy_manager)

# Schedule nightly dreaming (2:00-6:00)
await scheduler.start()
scheduler.schedule_nightly_dreaming(
    dream_engine,
    start_hour=2,
    end_hour=6
)
```

### 2. Scheduling Idle Dreaming

```python
# Check inactivity every 5 minutes
scheduler.schedule_idle_dreaming(
    dream_engine,
    check_interval_minutes=5
)
```

### 3. Manual Execution

```python
# Start a dreaming session manually
report = await dream_engine.enter_rem_phase(
    max_scenarios=5,
    difficulty="medium"
)

print(report)
# {
#   "session_id": "abc123...",
#   "status": "completed",
#   "duration_seconds": 180,
#   "dreams_attempted": 5,
#   "dreams_successful": 4,
#   "success_rate": 0.8
# }
```

### 4. Status Monitoring

```python
# EnergyManager Status
energy_status = energy_manager.get_status()
print(f"CPU: {energy_status['cpu_percent']}%")
print(f"Is Idle: {energy_status['is_idle']}")

# DreamEngine Statistics
dream_stats = dream_engine.get_statistics()
print(f"Total Dreams: {dream_stats['total_dreams']}")
print(f"Success Rate: {dream_stats['success_rate']:.2%}")
print(f"Saved Dreams: {dream_stats['saved_dreams_count']}")
```

## Output Data Structure

### `data/synthetic_training/` Directory
```
data/synthetic_training/
├── dream_abc123.py          # Generated code
├── dream_abc123.json        # Metadata
├── dream_def456.py
├── dream_def456.json
└── ...
```

### Example `dream_abc123.json`
```json
{
  "dream_id": "abc123",
  "session_id": "xyz789",
  "scenario": {
    "title": "Concurrent Web Scraper with Rate Limiting",
    "description": "Scraper downloading 50 pages...",
    "difficulty": "complex",
    "libraries": ["aiohttp", "asyncio"],
    "test_cases": [...]
  },
  "code_file": "dream_abc123.py",
  "timestamp": "2024-01-15T02:15:30.123Z",
  "synthetic": true
}
```

### Integration with LessonsStore

Dreams are automatically added to `LessonsStore` with the flag `synthetic: true`:

```python
lesson = lessons_store.get_lesson(lesson_id)
print(lesson.tags)  # ["synthetic", "dream", "aiohttp", "asyncio"]
print(lesson.metadata["synthetic"])  # True
```

### Integration with DatasetCurator

Synthetic examples are marked in the training set:

```python
curator = DatasetCurator(lessons_store=lessons_store)
curator.collect_from_lessons()

for example in curator.examples:
    if example.metadata.get("synthetic"):
        print(f"Synthetic example: {example.instruction}")
```

## Best Practices

### 1. Resource Management
- **Set realistic thresholds**: CPU/RAM thresholds should leave a margin for the user.
- **Use low priority**: `DREAMING_PROCESS_PRIORITY=19` (Linux nice value).
- **Monitor temperature**: EnergyManager automatically checks CPU temp.

### 2. Scenario Quality
- **Use GraphRAG**: Ensure the knowledge graph is rich.
- **Adjust complexity**: `simple` for fast learning, `complex` for advanced cases.
- **Verify Few-Shot examples**: ScenarioWeaver uses examples in prompts.

### 3. Validation
- **ALWAYS enable strict validation**: `DREAMING_VALIDATION_STRICT=true`.
- **Do not disable Guardian**: It is the only quality filter.
- **Monitor success rate**: A low value may indicate configuration issues.

### 4. Inactivity
- **Appropriate thresholds**: 30 min is a good balance.
- **Avoid conflicts**: Do not schedule dreams during work hours.
- **Test wake_up**: Check if interruption works in <2s.

## Troubleshooting

### Problem: No dreams in `data/synthetic_training/`
**Cause**: Knowledge graph is empty or validation always fails.
**Solution**:
```python
# Check knowledge graph
stats = graph_rag.get_stats()
print(stats["total_nodes"])  # Should be >0

# Check Guardian logs
tail -f logs/venom.log | grep Guardian
```

### Problem: Dreaming does not stop when the user returns
**Cause**: EnergyManager is not monitoring or thresholds are too high.
**Solution**:
```python
# Check if monitoring is active
await energy_manager.start_monitoring()

# Lower thresholds
energy_manager.cpu_threshold = 0.5  # 50%
```

### Problem: Scenarios are trivial ("Hello World")
**Cause**: Low level of complexity or poor documentation.
**Solution**:
```bash
# Increase complexity
DREAMING_SCENARIO_COMPLEXITY=complex

# Add more knowledge to GraphRAG
oracle_agent.ingest_file("path/to/advanced_docs.pdf")
```

## API Reference

### DreamEngine

#### `enter_rem_phase(max_scenarios, difficulty) -> Dict`
Starts the REM phase - the main dreaming function.

**Args:**
- `max_scenarios` (int): Maximum number of scenarios (default: SETTINGS).
- `difficulty` (str): 'simple', 'medium', 'complex' (default: SETTINGS).

**Returns:**
```python
{
    "session_id": str,
    "status": "completed" | "interrupted" | "error" | "no_knowledge",
    "duration_seconds": float,
    "dreams_attempted": int,
    "dreams_successful": int,
    "success_rate": float
}
```

#### `get_statistics() -> Dict`
Returns DreamEngine statistics.

### ScenarioWeaver

#### `weave_scenario(knowledge_fragment, difficulty, libraries) -> ScenarioSpec`
Generates a single scenario.

**Args:**
- `knowledge_fragment` (str): Documentation/knowledge fragment.
- `difficulty` (str, optional): Difficulty level.
- `libraries` (List[str], optional): List of libraries to use.

**Returns:** `ScenarioSpec` object.

#### `weave_multiple_scenarios(knowledge_fragments, count, difficulty) -> List[ScenarioSpec]`
Generates multiple scenarios.

### EnergyManager

#### `get_metrics() -> SystemMetrics`
Retrieves current system metrics (CPU, RAM, temperature).

#### `is_system_busy() -> bool`
Checks if the system has exceeded resource thresholds.

#### `is_idle(threshold_minutes) -> bool`
Checks if the system is idle.

#### `wake_up() -> None`
Immediately terminates dreaming (callback for high load).

#### `start_monitoring() / stop_monitoring() -> None`
Starts/stops resource monitoring in the background.

## Roadmap

### Planned Functions

1. **Docker Isolation** (v1.1)
   - Separate namespaces for dreams (`venom-dream-worker-X`).
   - Automatic container cleanup after the session.

2. **Dashboard "Dream Journal"** (v1.1)
   - Section in The Academy.
   - Night statistics: "I dreamed 42 solutions".
   - Ability to manually approve dreams.

3. **Multi-Library Scenarios** (v1.1)
   - Combining 2+ libraries in one scenario.
   - Realistic integrations (e.g., FastAPI + SQLAlchemy + Redis).

4. **Adaptive Difficulty** (v1.2)
   - Automatic complexity adjustment based on success rate.
   - Progressive learning (start: simple → medium → complex).

5. **Dream Replay** (v1.2)
   - Re-execution of saved dreams for regression.
   - Scenario benchmarks on new library versions.

## Usage Examples

### Example 1: Nightly Dreaming Session

```python
# main.py - system initialization
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.memory.graph_rag_service import GraphRAGService
from venom_core.memory.lessons_store import LessonsStore
from venom_core.core.energy_manager import EnergyManager
from venom_core.core.dream_engine import DreamEngine
from venom_core.core.scheduler import BackgroundScheduler

# Build kernel
kernel = KernelBuilder().build()

# Initialize components
graph_rag = GraphRAGService()
lessons_store = LessonsStore()
energy_manager = EnergyManager()

# Dream Engine
dream_engine = DreamEngine(
    kernel=kernel,
    graph_rag=graph_rag,
    lessons_store=lessons_store,
    energy_manager=energy_manager
)

# Scheduler
scheduler = BackgroundScheduler()
await scheduler.start()

# Schedule nightly dreaming (2:00)
scheduler.schedule_nightly_dreaming(dream_engine, start_hour=2)

# Run app
await run_app()
```

### Example 2: Results Analysis

```python
# analyze_dreams.py
from pathlib import Path
import json

output_dir = Path("./data/synthetic_training")

# Statistics
dream_files = list(output_dir.glob("dream_*.json"))
print(f"Total dreams: {len(dream_files)}")

# Analysis by libraries
libraries_count = {}
for dream_file in dream_files:
    with open(dream_file) as f:
        data = json.load(f)
        for lib in data["scenario"]["libraries"]:
            libraries_count[lib] = libraries_count.get(lib, 0) + 1

print("\nMost practiced libraries:")
for lib, count in sorted(libraries_count.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {lib}: {count}")
```

## Conclusions

THE DREAMER is a powerful tool for Venom’s self-improvement. Key benefits:

✅ **Automatic learning** - no need for manual creation of examples.
✅ **High quality data** - Guardian ensures 100% quality.
✅ **Resource-light** - works in the background, low priority.
✅ **Intelligent interruption** - immediate reaction to user activity.
✅ **Scalability** - from simple to complex scenarios.

Remember: The richer the Knowledge Graph (GraphRAG), the better the dreams! 🌙
