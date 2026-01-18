# THE_CHRONOMANCER - State Management System Guide

## 📖 Introduction

**The Chronomancer** (Time Manager) is an advanced state and timeline management system in the Venom project. It enables creating snapshots of the entire system state (code + memory + configuration), experimenting on separate timelines, and safely restoring to earlier points in case of errors.

## 🎯 Main Features

### 1. Checkpoints (Restore Points)
- **Creating snapshots** of entire system state
- **Restoring** to any point in history
- **Managing** multiple restore points
- **Automatic backups** before risky operations

### 2. Timelines (Timeline Branching)
- **Creating** separate timelines for experimentation
- **Isolating** experiments from main project
- **Safe testing** of risky changes
- **History** of all changes and decisions

### 3. Risk Management
- **Automatic assessment** of operation risk
- **Recommendations** for checkpoint creation
- **Error analysis** and learning from failures
- **LessonsStore integration** for saving experiences

## 🏗️ Architecture

The system consists of three main components:

```
┌─────────────────────────────────────────────────────────┐
│                    THE_CHRONOMANCER                      │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Chronos    │  │  Historian   │  │  ChronoSkill │  │
│  │   Engine     │◄─┤    Agent     │◄─┤              │  │
│  │              │  │              │  │              │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘  │
│         │                 │                              │
│         │                 │                              │
│         ▼                 ▼                              │
│  ┌──────────────┐  ┌──────────────┐                    │
│  │  Snapshots   │  │    Lessons   │                    │
│  │  (Git+DB)    │  │     Store    │                    │
│  └──────────────┘  └──────────────┘                    │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### ChronosEngine
System core - manages snapshot creation and restoration.

**Key methods:**
- `create_checkpoint(name, description, timeline)` - creates snapshot
- `restore_checkpoint(id, timeline)` - restores state
- `list_checkpoints(timeline)` - snapshot list
- `create_timeline(name)` - new timeline
- `delete_checkpoint(id)` - removes snapshot

**Snapshot Structure:**
```
data/timelines/{timeline}/{checkpoint_id}/
├── checkpoint.json        # Metadata
├── fs_diff.patch         # Code differences (Git)
├── git_status.txt        # Git status
├── memory_dump/          # Database backup
│   ├── test.db
│   └── vector_store/
└── env_config.json       # Environment configuration
```

### HistorianAgent
Agent responsible for risk management and causal analysis.

**Main functions:**
- Operation risk assessment (low/medium/high)
- Checkpoint recommendation before risky actions
- Error analysis and lesson saving
- Change history management

**Risk levels:**
- 🟢 **Low**: Read-only operations
- 🟡 **Medium**: Modifications, updates
- 🔴 **High**: hot_patch, delete, refactor, migration

### ChronoSkill
Semantic Kernel interface for agents to interact with the system.

**Available kernel functions:**
- `create_checkpoint(name, description, timeline)`
- `restore_checkpoint(checkpoint_id, timeline)`
- `list_checkpoints(timeline)`
- `delete_checkpoint(checkpoint_id, timeline)`
- `branch_timeline(name)`
- `list_timelines()`
- `merge_timeline(source, target)` - placeholder

## 🚀 Usage

### Example 1: Basic Usage

```python
from venom_core.core.chronos import ChronosEngine

# Initialize
chronos = ChronosEngine()

# Create checkpoint before risky operation
checkpoint_id = chronos.create_checkpoint(
    name="before_refactoring",
    description="Before major core module refactoring"
)

# ... perform operations ...

# If something went wrong, restore
if error_occurred:
    chronos.restore_checkpoint(checkpoint_id)
```

### Example 2: Using HistorianAgent

```python
from semantic_kernel import Kernel
from venom_core.agents.historian import HistorianAgent

kernel = Kernel()
historian = HistorianAgent(kernel)

# Assess operation risk
result = await historian.process("Execute hot_patch on core module")
# If high risk, recommends checkpoint

# Create safety checkpoint
checkpoint_id = historian.create_safety_checkpoint(
    name="pre_hotpatch",
    description="Before applying hot_patch"
)

# After error, analyze and learn
await historian.analyze_failure(
    operation="hot_patch on core.py",
    error="SyntaxError: invalid syntax",
    checkpoint_before=checkpoint_id
)
```

### Example 3: Timelines for Experiments

```python
# Create checkpoint on main timeline
main_checkpoint = chronos.create_checkpoint(
    name="stable_state",
    timeline="main"
)

# Create experimental timeline
chronos.create_timeline("experimental")

# Experiment on separate timeline
exp_checkpoint = chronos.create_checkpoint(
    name="experiment_start",
    timeline="experimental"
)

# ... conduct experiments ...

# If success, knowledge is already in LessonsStore
# If failure, restore main timeline
chronos.restore_checkpoint(main_checkpoint, timeline="main")
```

### Example 4: Usage via Semantic Kernel

```python
from venom_core.execution.skills.chrono_skill import ChronoSkill

# Add skill to kernel
chrono_skill = ChronoSkill()
kernel.add_plugin(chrono_skill, plugin_name="chronos")

# Agents can now use time functions:
# - "Create checkpoint before starting"
# - "Restore checkpoint abc123"
# - "Show checkpoint list"
# - "Create new experimental timeline"
```

## 🔧 Configuration

New settings added in `config.py`:

```python
# THE_CHRONOMANCER configuration
ENABLE_CHRONOS: bool = True
CHRONOS_TIMELINES_DIR: str = "./data/timelines"
CHRONOS_AUTO_CHECKPOINT: bool = True
CHRONOS_MAX_CHECKPOINTS_PER_TIMELINE: int = 50
CHRONOS_CHECKPOINT_RETENTION_DAYS: int = 30
CHRONOS_COMPRESS_SNAPSHOTS: bool = True
```

## 🔗 DreamEngine Integration [v2.0]

DreamEngine integrated with Chronos for safe experimentation:

```python
class DreamEngine:
    def __init__(self, ..., chronos_engine=None):
        self.chronos = chronos_engine or ChronosEngine()

    async def enter_rem_phase(self, ...):
        # Create temporary timeline for dreams
        timeline_name = f"dream_{session_id}"
        self.chronos.create_timeline(timeline_name)

        # Create safety checkpoint
        checkpoint_id = self.chronos.create_checkpoint(
            name=f"dream_start_{session_id}",
            timeline=timeline_name
        )

        # ... dream ...

        # If success (>50% successes), keep knowledge
        # If failure, timeline remains as history
```

**Advantages:**
- Dreams don't clutter main memory
- Each dream has its own timeline
- Easy rollback of failed experiments
- History of all attempts available for analysis

## 📊 Monitoring and Diagnostics

### System State Check

```python
# List all timelines
timelines = chronos.list_timelines()
print(f"Available timelines: {timelines}")

# List checkpoints on timeline
checkpoints = chronos.list_checkpoints(timeline="main")
for cp in checkpoints:
    print(f"{cp.name} ({cp.checkpoint_id}) - {cp.timestamp}")

# Checkpoint history (HistorianAgent)
history = historian.get_checkpoint_history(limit=10)
```

### Snapshot Statistics

```bash
# Snapshot directory sizes
du -sh data/timelines/*

# Number of checkpoints
find data/timelines -name "checkpoint.json" | wc -l
```

## 🛡️ Security

### What Is Saved in Snapshots
- ✅ Git diff (file changes)
- ✅ Git status (uncommitted files)
- ✅ Database backups (LanceDB, GraphStore)
- ✅ Environment configuration (without secrets)

### What We DON'T Save
- ❌ Secrets and passwords (.env)
- ❌ Large binary files (ML models)
- ❌ .git directory (we use diff)
- ❌ Node_modules, venv, etc.

### Recommendations
1. **Regular cleanup** of old checkpoints
2. **Limits** on checkpoint count per timeline
3. **Compression** of snapshots (if enabled)
4. **Backup** important checkpoints outside project

## 🧪 Testing

Comprehensive tests created:

```bash
# Unit tests
pytest tests/test_chronos.py -v
pytest tests/test_historian_agent.py -v
pytest tests/test_chrono_skill.py -v

# All Chronos tests
pytest tests/test_chrono*.py tests/test_historian*.py -v
```

**Test coverage:**
- ✅ Creating and restoring checkpoints
- ✅ Timeline management
- ✅ Operation risk assessment
- ✅ Error analysis and lesson saving
- ✅ LessonsStore integration
- ✅ Complete checkpoint lifecycles

## 🔮 Future Extensions

### Planned
1. **Intelligent Merge** of timelines with conflicts (via LLM)
2. **Automatic compression** of old snapshots
3. **Garbage Collection** of unused checkpoints
4. **Dashboard** timeline visualization (Web UI)
5. **Git Worktree** for physical branch isolation
6. **Docker Volume Snapshots** for complete container isolation

### Advanced Scenarios
- **A/B Testing**: Two timelines, result comparison
- **Chaos Engineering**: Resilience testing with automatic rollback
- **Training Pipelines**: Timeline per training experiment
- **Production Rollback**: Fast deployment rollback

## 📝 Best Practices

1. **Name checkpoints descriptively**: Instead of "cp1" use "before_migration_v1"
2. **Add descriptions**: Helps with later analysis
3. **Create checkpoints before risky operations**: hot_patch, migrations, refactoring
4. **Use separate timelines for experiments**: Don't clutter main
5. **Regularly clean old checkpoints**: Save space
6. **Document decisions**: Why you created checkpoint, what changed

## 🆘 Troubleshooting

### Problem: Checkpoint doesn't restore files
**Solution**: Check if you're in a Git repository. ChronosEngine uses `git diff` and `git apply`.

### Problem: Out of disk space
**Solution**:
1. Delete old checkpoints: `chronos.delete_checkpoint(id)`
2. Enable compression: `CHRONOS_COMPRESS_SNAPSHOTS = True`
3. Decrease limit: `CHRONOS_MAX_CHECKPOINTS_PER_TIMELINE = 10`

### Problem: Checkpoint restore fails with error
**Solution**: Check logs. Possible causes:
- Git conflicts (resolve manually)
- No file permissions
- Deleted memory directory

### Problem: Historian doesn't recommend checkpoints
**Solution**: Check if operation contains high-risk keywords (hot_patch, delete, migration). You can extend the list in `historian.py`.

## 📚 Related Documents

- [THE_DREAMER](../DREAM_ENGINE_GUIDE.md) - Background processing
- [THE_ACADEMY](./THE_ACADEMY.md) - Training pipelines
- [MEMORY_LAYER_GUIDE](../MEMORY_LAYER_GUIDE.md) - Knowledge consolidation
- [GUARDIAN_GUIDE](../GUARDIAN_GUIDE.md) - Safety checksange validation

## 🎓 End-to-End Example

```python
# Scenario: Safe database migration

# 1. Assess risk
historian = HistorianAgent(kernel)
risk_assessment = await historian.process(
    "Perform database schema migration"
)
# → Recommends checkpoint (high risk)

# 2. Create safety checkpoint
checkpoint_id = historian.create_safety_checkpoint(
    name="pre_migration_v1",
    description="Before migration to schema version 2.0"
)

# 3. Perform migration
try:
    run_database_migration()
except Exception as e:
    # 4. Error - analyze and rollback
    await historian.analyze_failure(
        operation="database_migration_v1",
        error=str(e),
        checkpoint_before=checkpoint_id
    )

    # Restore checkpoint
    chronos.restore_checkpoint(checkpoint_id)
    logger.error("Migration failed, system restored")
else:
    # 5. Success - save new lesson
    lessons_store.add_lesson(
        situation="Database migration to v1.0",
        action="Performed migration with safety checkpoint",
        result="SUCCESS",
        feedback="Checkpoint enabled safe testing",
        tags=["migration", "database", "checkpoint"]
    )
```

---

**Authors**: Venom Core Team
**Version**: 1.0
**Date**: 2024-12-08
**Status**: Implemented ✅
