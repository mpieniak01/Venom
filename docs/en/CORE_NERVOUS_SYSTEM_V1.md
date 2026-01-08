# Venom Core Nervous System V1 - Documentation

## Overview

Core Nervous System V1 is an MVP asynchronous task management system for the Venom project. The system enables task acceptance via API, background processing, and state management with file persistence.

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

3. **Orchestrator** (`venom_core/core/orchestrator.py`)
   - Accepting tasks for processing
   - Asynchronous background task execution
   - Logging all stages
   - Error handling with automatic FAILED status setting

4. **API** (`venom_core/main.py`)
   - FastAPI-based REST API
   - Three main endpoints for task management

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

## Running

### Install dependencies
```bash
pip install fastapi uvicorn pydantic pydantic-settings loguru
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

- Single-process / single-instance
- Tasks executed locally (simulation with 2s delay)
- No production queue
- No database
- No retry mechanisms
- No task priorities

## Future Enhancements

- Migration to database (PostgreSQL/MongoDB)
- Task queue implementation (Redis/RabbitMQ)
- Distributed workers
- Retry mechanisms and priorities
- Monitoring and metrics
- Authentication and authorization
- WebSocket for real-time updates
