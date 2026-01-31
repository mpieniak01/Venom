# Venom Core Nervous System V1 - Documentation

## Overview

Core Nervous System V1 is Venom's asynchronous task management system. It accepts tasks via API, queues and processes them in the background, streams events, and manages state with file persistence. It also supports an optional distributed mode (Hive) based on Redis + ARQ.

## Architecture

### Components

1. **Models** (`venom_core/core/models.py`)
   - `TaskStatus`: Enum for task statuses (PENDING, PROCESSING, COMPLETED, FAILED)
   - `VenomTask`: Task model with full metadata
   - `TaskRequest`: DTO for task creation
   - `TaskResponse`: DTO for response after task creation

2. **StateManager** (`venom_core/core/state_manager.py`)
   - In-memory task state management
   - Automatic persistence to JSON file
   - State loading on startup
   - I/O error handling

3. **QueueManager** (`venom_core/core/queue_manager.py`)
   - Queue pause/resume, purge, emergency stop
   - Concurrency limits and queue status
   - Abort operations for individual tasks

4. **Orchestrator** (`venom_core/core/orchestrator.py`)
   - Accepting tasks for processing
   - Asynchronous background task execution
   - Stage logging and status updates
   - Error handling with automatic FAILED status setting

5. **API** (`venom_core/main.py`)
   - FastAPI-based REST API
   - Task + queue + event endpoints

6. **Event Stream** (`venom_core/api/stream.py`)
   - WebSocket for status and system events

## API Endpoints

### 1. Create task
```bash
POST /api/v1/tasks
Content-Type: application/json

{
  "content": "Task content"
}
```

**Response:**
```json
{
  "task_id": "uuid",
  "status": "PENDING"
}
```

### 2. Get task details
```bash
GET /api/v1/tasks/{task_id}
```

**Response:**
```json
{
  "id": "uuid",
  "content": "Task content",
  "created_at": "2025-12-06T14:22:52.927944",
  "status": "COMPLETED",
  "result": "Processed: Task content",
  "logs": [
    "Task started: 2025-12-06T14:22:52.928194",
    "Processing started: 2025-12-06T14:22:52.929935",
    "Processing completed: 2025-12-06T14:22:54.931036"
  ]
}
```

### 3. List all tasks
```bash
GET /api/v1/tasks
```

**Response:**
```json
[
  {
    "id": "uuid",
    "content": "Task content",
    ...
  },
  ...
]
```

### 4. Queue status and control
```bash
GET /api/v1/queue/status
POST /api/v1/queue/pause
POST /api/v1/queue/resume
POST /api/v1/queue/purge
POST /api/v1/queue/emergency-stop
POST /api/v1/queue/task/{task_id}/abort
```

### 5. Event stream
```bash
WS /ws/events
```

## Running

### Install dependencies
```bash
pip install fastapi uvicorn pydantic pydantic-settings loguru
```
Optional for Hive mode (distributed queues):
```bash
pip install redis arq
```

### Start server
```bash
uvicorn venom_core.main:app --host 0.0.0.0 --port 8000
```

### Example usage

```bash
# Create task
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"content": "My task"}'

# Get status
curl http://localhost:8000/api/v1/tasks/{task_id}

# List all tasks
curl http://localhost:8000/api/v1/tasks
```

## Persistence

The system automatically saves the state of all tasks to the file `data/memory/state_dump.json`.
After server restart, the state is automatically restored from the file.

### Configuration

The state file path can be configured in the `.env` file:
```
STATE_FILE_PATH=./data/memory/state_dump.json
```

## Testing

### Run tests
```bash
# All tests
pytest tests/

# Integration tests only
pytest tests/test_core_nervous_system.py

# Unit tests only
pytest tests/test_state_and_orchestrator.py
```

### Test coverage

- ✅ 9 integration tests (API, async execution)
- ✅ 13 unit tests (StateManager, Orchestrator)
- ✅ Edge cases and error handling
- ✅ Persistence and state recovery

## Error Handling

The system handles the following cases:

1. **Non-existent task**: HTTP 404
2. **Invalid request**: HTTP 422
3. **Internal error**: HTTP 500 (without exposing details)
4. **Corrupted state file**: Start with empty state + error log
5. **Processing error**: FAILED status + error log
6. **State save error**: Error log, attempt to continue

## MVP Limitations

- Single-instance by default (no distribution)
- Tasks executed locally without external broker
- No database (file-based persistence)
- Retry and priority available only in Hive (Redis + ARQ)
- No API-level authentication/authorization

## Future Enhancements

- Migration to database (PostgreSQL/MongoDB)
- Full cluster mode expansion (Hive/Nexus)
- Distributed workers
- Retry mechanisms and priorities
- Monitoring and metrics
- Authentication and authorization
- WebSocket for real-time updates
