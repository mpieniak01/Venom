# THE_OVERMIND - Background Lifecycle Management

## Overview

THE_OVERMIND is a background task management system that transforms Venom from a "Request-Response" model into an autonomous 24/7 operating system. The system monitors file changes, automatically updates documentation, and performs refactoring during idle time.

## Architecture

### 1. BackgroundScheduler (`venom_core/core/scheduler.py`)

Scheduling system based on APScheduler (AsyncIOScheduler).

**Functionality:**
- Registration of periodic tasks (interval, cron)
- FastAPI lifespan integration (start/stop)
- Pause/Resume all tasks
- Task metadata tracking

**Default tasks:**
- `consolidate_memory`: Memory consolidation every 60 minutes
- `check_health`: System health check every 5 minutes

**Usage Example:**
```python
scheduler = BackgroundScheduler(event_broadcaster=event_broadcaster)
await scheduler.start()

# Add interval job
scheduler.add_interval_job(
    func=my_async_function,
    minutes=30,
    job_id="my_job",
    description="Custom job"
)

# Pause all tasks
await scheduler.pause_all_jobs()

# Resume tasks
await scheduler.resume_all_jobs()
```

### 2. FileWatcher (`venom_core/perception/watcher.py`)

File system observer based on Watchdog.

**Functionality:**
- Recursive workspace monitoring
- Debouncing (default 5 seconds)
- Ignore patterns (.git, __pycache__, etc.)
- Broadcasting CODE_CHANGED events

**Ignored patterns:**
- `.git`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`
- `node_modules`, `.venv`, `venom`, `.idea`, `.vscode`
- `*.pyc`, `*.pyo`, `*.swp`, `*.tmp`

**Monitored extensions:**
- `.py` (Python)
- `.md` (Markdown)

**Usage Example:**
```python
async def on_file_change(file_path: str):
    print(f"File changed: {file_path}")

watcher = FileWatcher(
    workspace_root="./workspace",
    on_change_callback=on_file_change,
    event_broadcaster=event_broadcaster
)
await watcher.start()
```

### 3. DocumenterAgent (`venom_core/agents/documenter.py`)

Agent automatically updating documentation on code changes.

**Functionality:**
- Detecting changes in Python files
- Diff analysis with GitSkill
- Creating/updating CHANGELOG_AUTO.md
- Automatic commit of documentation changes
- Loop prevention (ignores venom-bot changes)

**Algorithm:**
1. .py file changes → FileWatcher detects
2. DocumenterAgent checks diff
3. Analyzes if change requires documentation update
4. Updates docs/CHANGELOG_AUTO.md
5. Commits: `docs: auto-update documentation for [file]`

**Usage Example:**
```python
documenter = DocumenterAgent(
    workspace_root="./workspace",
    git_skill=git_skill,
    event_broadcaster=event_broadcaster
)

# Call on file change
await documenter.handle_code_change("/path/to/changed_file.py")
```

### 4. Enhanced GardenerAgent (Idle Mode)

Extended GardenerAgent with automatic refactoring functionality.

**Functionality:**
- Monitoring last activity (orchestrator.last_activity)
- Idle threshold: 15 minutes (configurable)
- Cyclomatic complexity analysis (radon)
- Creating branch `refactor/auto-gardening`
- Selecting file with highest complexity

**Idle mode algorithm:**
1. System idle for 15+ minutes
2. GardenerAgent scans Python files
3. Radon analyzes cyclomatic complexity
4. Selects file with complexity > 10
5. Creates branch `refactor/auto-gardening`
6. (Future: refactoring + tests + commit)

**Usage Example:**
```python
gardener = GardenerAgent(
    graph_store=graph_store,
    orchestrator=orchestrator,
    event_broadcaster=event_broadcaster
)
await gardener.start()
```

## Configuration

All settings in `venom_core/config.py`:

```python
# Global background tasks switch
VENOM_PAUSE_BACKGROUND_TASKS: bool = False

# Automatic documentation update
ENABLE_AUTO_DOCUMENTATION: bool = True

# Automatic refactoring in Idle mode
ENABLE_AUTO_GARDENING: bool = True

# Debounce time for watchdog (seconds)
WATCHER_DEBOUNCE_SECONDS: int = 5

# Idle threshold before auto-gardening (minutes)
IDLE_THRESHOLD_MINUTES: int = 15

# Memory consolidation interval (minutes)
MEMORY_CONSOLIDATION_INTERVAL_MINUTES: int = 60

# Health check interval (minutes)
HEALTH_CHECK_INTERVAL_MINUTES: int = 5
```

Environment variables in `.env` file:

```bash
VENOM_PAUSE_BACKGROUND_TASKS=true
ENABLE_AUTO_DOCUMENTATION=false
ENABLE_AUTO_GARDENING=true
WATCHER_DEBOUNCE_SECONDS=10
IDLE_THRESHOLD_MINUTES=30
```

## REST API

### Scheduler

**GET /api/v1/scheduler/status**
```json
{
  "status": "success",
  "scheduler": {
    "is_running": true,
    "paused": false,
    "jobs_count": 2,
    "state": "STATE_RUNNING"
  }
}
```

**GET /api/v1/scheduler/jobs**
```json
{
  "status": "success",
  "jobs": [
    {
      "id": "consolidate_memory",
      "next_run_time": "2024-12-07T12:00:00",
      "type": "interval",
      "description": "Memory consolidation and log analysis",
      "interval_minutes": 60
    }
  ],
  "count": 2
}
```

**POST /api/v1/scheduler/pause**
```json
{
  "status": "success",
  "message": "All background jobs paused"
}
```

**POST /api/v1/scheduler/resume**
```json
{
  "status": "success",
  "message": "All background jobs resumed"
}
```

### Watcher

**GET /api/v1/watcher/status**
```json
{
  "status": "success",
  "watcher": {
    "is_running": true,
    "workspace_root": "/path/to/workspace",
    "debounce_seconds": 5,
    "monitoring_extensions": [".py", ".md"]
  }
}
```

### Documenter

**GET /api/v1/documenter/status**
```json
{
  "status": "success",
  "documenter": {
    "enabled": true,
    "workspace_root": "/path/to/workspace",
    "processing_files": 0
  }
}
```

### Gardener

**GET /api/v1/gardener/status**
```json
{
  "status": "success",
  "gardener": {
    "is_running": true,
    "last_scan_time": "2024-12-07T11:30:00",
    "scan_interval_seconds": 300,
    "workspace_root": "/path/to/workspace",
    "monitored_files": 42,
    "idle_refactoring_enabled": true,
    "idle_refactoring_in_progress": false
  }
}
```

## WebSocket Events

New event types in `EventType`:

```python
# Background Tasks events
CODE_CHANGED = "CODE_CHANGED"
BACKGROUND_JOB_STARTED = "BACKGROUND_JOB_STARTED"
BACKGROUND_JOB_COMPLETED = "BACKGROUND_JOB_COMPLETED"
BACKGROUND_JOB_FAILED = "BACKGROUND_JOB_FAILED"
DOCUMENTATION_UPDATED = "DOCUMENTATION_UPDATED"
MEMORY_CONSOLIDATED = "MEMORY_CONSOLIDATED"
IDLE_REFACTORING_STARTED = "IDLE_REFACTORING_STARTED"
IDLE_REFACTORING_COMPLETED = "IDLE_REFACTORING_COMPLETED"
```

**Example event:**
```json
{
  "type": "CODE_CHANGED",
  "agent": null,
  "message": "File changed: main.py",
  "timestamp": "2024-12-07T11:34:00",
  "data": {
    "file_path": "/workspace/main.py",
    "relative_path": "main.py",
    "timestamp": 1733574840.123
  }
}
```

## Dashboard UI

New tab **"⚙️ Jobs"** in right panel:

### Sections:

1. **Scheduler Status**
   - Status (Running/Stopped)
   - Job count
   - Paused (Yes/No)

2. **Active Jobs**
   - Active job list
   - Next run time for each job
   - Job type (interval/cron)

3. **File Watcher**
   - Status (Watching/Stopped)
   - Workspace path
   - Monitored extensions

4. **Auto-Documentation**
   - Enabled/Disabled
   - Number of processing files

5. **Auto-Gardening**
   - Running status
   - Idle refactoring enabled
   - In progress status
   - Last scan time

### Controls:

- **⏸️ Pause** - Pause all tasks
- **▶️ Resume** - Resume tasks
- **🔄 Refresh** - Refresh status

## Use Case Scenarios

### 1. Live Documentation

**Scenario:**
1. I change function name in `venom_core/utils/helpers.py`
2. Save file (Ctrl+S)
3. FileWatcher detects change (after 5s debounce)
4. DocumenterAgent analyzes diff
5. Updates `docs/CHANGELOG_AUTO.md`
6. Commits: `docs: auto-update documentation for helpers.py`

**Result:** Documentation always up-to-date, without manual work.

### 2. Background Refactoring

**Scenario:**
1. Leave Venom running overnight
2. System idle for >15 minutes
3. GardenerAgent detects idle mode
4. Scans workspace with radon
5. Finds `complex_module.py` with complexity 15
6. Creates branch `refactor/auto-gardening`
7. (Future: refactors code)

**Result:** In the morning see PR with improved code.

### 3. Memory Consolidation

**Scenario:**
1. Intensive coding session (3h)
2. Every hour `consolidate_memory()` runs
3. (Future: Analyzes logs, extracts insights)
4. Saves key findings to VectorStore

**Result:** Venom "remembers" context of long sessions.

## Security

### Loop Prevention

**Problem:** Venom changes file → Watchdog detects → Venom reacts → loop

**Solutions:**
1. DocumenterAgent ignores changes from "venom-bot" user
2. Tracking recently processed files (60s timeout)
3. Debouncing in FileWatcher (5s quiet before reaction)

### Path Validation

All API endpoints validate paths:
- No `..` in path
- No absolute paths
- Everything within workspace_root

### Global Switch

`VENOM_PAUSE_BACKGROUND_TASKS=true` disables all background tasks.

## Tests

### Unit Tests
- `tests/test_scheduler.py` - BackgroundScheduler (7 tests)
- `tests/test_watcher.py` - FileWatcher (6 tests)
- `tests/test_documenter.py` - DocumenterAgent (5 tests)

### Integration Tests
- `tests/test_overmind_integration.py` - Component integration (6 tests)

**Execution:**
```bash
pytest tests/test_scheduler.py tests/test_watcher.py -v
pytest tests/test_overmind_integration.py -v
```

## Troubleshooting

### FileWatcher doesn't detect changes

**Causes:**
1. File in ignored patterns (.git, __pycache__)
2. Extension other than .py or .md
3. Watcher not started

**Solution:**
```bash
# Check status
curl http://localhost:8000/api/v1/watcher/status

# Check logs
tail -f logs/venom.log | grep FileWatcher
```

### Background tasks don't work

**Causes:**
1. `VENOM_PAUSE_BACKGROUND_TASKS=true`
2. Scheduler not started
3. Error in task function

**Solution:**
```bash
# Check scheduler status
curl http://localhost:8000/api/v1/scheduler/status

# Check job list
curl http://localhost:8000/api/v1/scheduler/jobs

# Resume tasks
curl -X POST http://localhost:8000/api/v1/scheduler/resume
```

### Documentation doesn't update

**Causes:**
1. `ENABLE_AUTO_DOCUMENTATION=false`
2. Missing GitSkill (workspace not Git repo)
3. Change made by venom-bot (ignored)

**Solution:**
```bash
# Check documenter status
curl http://localhost:8000/api/v1/documenter/status

# Check config
grep ENABLE_AUTO_DOCUMENTATION .env
```

## Future Extensions

1. **Intelligent refactoring**
   - Using LLM for complex code analysis and rewriting
   - Automatic tests after refactoring
   - PR with change description

2. **Memory consolidation**
   - semantic_kernel log analysis
   - Key insight extraction
   - GraphRAG storage

3. **Advanced health checks**
   - Docker container checking
   - LLM endpoint pinging
   - Resource usage monitoring

4. **Notifications**
   - Slack/Discord webhooks for important events
   - Email on problem detection
   - Dashboard toast notifications

## Dependencies

Added to `requirements.txt`:
```
apscheduler      # Background task scheduler
watchdog         # File system monitoring
radon            # Code complexity analysis
```

## Authors

- Implementation: GitHub Copilot (Copilot Workspace)
- Issue: mpieniak01 (#015_THE_OVERMIND)
- Repository: mpieniak01/Venom
