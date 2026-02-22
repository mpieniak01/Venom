# Workflow Control Plane & Composer

## Overview

This document defines the API contract for the Workflow Control Plane and the Visual Composer interface. It provides centralized management of the entire Venom stack configuration.

Operator guide (UX flow, source semantics, troubleshooting): `docs/THE_WORKFLOW_CONTROL.md`.

## Visual Composer (UX)

The Workflow Control screen introduces a **Visual Composer** based on React Flow.

### Swimlanes
The diagram is organized into domains:
1. **Decision & Intent**: Strategy (Heuristic/LLM) and Intent Classification.
2. **Kernel & Embedding**: Execution Engine (Python/Docker) and Vector Embeddings.
3. **Runtime & Provider**: LLM Server (Ollama/vLLM/ONNX) and Model Provider (Local/Cloud).

### Connection Rules
The Composer enforces valid connections:
- `decision_strategy` -> `intent_mode`
- `intent_mode` -> `embedding_model` (if required)
- `runtime` -> `provider`
- `provider` -> `model`

Invalid connections are blocked with specific `reason_code`.

## API Contract

## Base URL

All endpoints are prefixed with: `/api/v1/workflow/control`

## Core Concepts

### Apply Modes

| Mode | Value | Description |
|------|-------|-------------|
| HOT_SWAP | `hot_swap` | Change applied immediately without restart |
| RESTART_REQUIRED | `restart_required` | Change requires service restart to take effect |
| REJECTED | `rejected` | Change was rejected due to validation failure |

### Reason Codes

#### Success Codes
- `success_hot_swap` - Change applied successfully without restart
- `success_restart_pending` - Change applied, restart required to take effect

#### Rejection Codes
- `invalid_configuration` - Configuration is invalid
- `incompatible_combination` - Incompatible component combination
- `dependency_missing` - Required dependency is missing
- `service_unavailable` - Required service is unavailable
- `forbidden_transition` - State transition is not allowed
- `invalid_state` - Current state doesn't allow this operation

#### Validation Codes
- `kernel_runtime_mismatch` - Kernel not compatible with runtime
- `provider_model_mismatch` - Provider doesn't support model
- `embedding_incompatible` - Embedding model incompatible with provider
- `intent_mode_conflict` - Intent mode conflicts with configuration

#### Operation Codes
- `operation_in_progress` - Operation is still running
- `operation_completed` - Operation completed successfully
- `operation_failed` - Operation failed
- `operation_cancelled` - Operation was cancelled

### Resource Types

- `decision_strategy` - Decision routing strategy
- `intent_mode` - Intent classification mode
- `kernel` - Execution kernel type
- `runtime` - Runtime environment
- `provider` - LLM provider
- `embedding_model` - Embedding model type
- `workflow` - Workflow instance
- `config` - General configuration

## Endpoints

### 1. Plan Changes

**Endpoint:** `POST /plan`

Plans configuration changes and validates compatibility before applying.

**Request:**
```json
{
  "changes": [
    {
      "resource_type": "kernel",
      "resource_id": "standard",
      "action": "update",
      "current_value": "standard",
      "new_value": "optimized",
      "metadata": {}
    }
  ],
  "dry_run": false,
  "force": false,
  "metadata": {}
}
```

**Response:**
```json
{
  "execution_ticket": "uuid-here",
  "valid": true,
  "reason_code": "success_restart_pending",
  "compatibility_report": {
    "compatible": true,
    "issues": [],
    "warnings": [],
    "affected_services": ["backend"]
  },
  "planned_changes": [
    {
      "resource_type": "kernel",
      "resource_id": "standard",
      "action": "update",
      "apply_mode": "restart_required",
      "reason_code": "success_restart_pending",
      "message": "Kernel updated, restart required",
      "timestamp": "2024-01-01T00:00:00Z"
    }
  ],
  "hot_swap_changes": [],
  "restart_required_services": ["backend"],
  "rejected_changes": [],
  "estimated_duration_seconds": 1.0
}
```

### 2. Apply Changes

**Endpoint:** `POST /apply`

Applies previously planned changes using execution ticket.

**Request:**
```json
{
  "execution_ticket": "uuid-from-plan",
  "confirm_restart": true,
  "metadata": {}
}
```

**Response:**
```json
{
  "execution_ticket": "uuid-from-plan",
  "apply_mode": "restart_required",
  "reason_code": "success_restart_pending",
  "message": "Changes applied, restart required",
  "applied_changes": [
    {
      "resource_type": "kernel",
      "resource_id": "standard",
      "action": "update",
      "apply_mode": "restart_required",
      "reason_code": "success_restart_pending",
      "message": "Kernel updated",
      "timestamp": "2024-01-01T00:00:00Z"
    }
  ],
  "pending_restart": ["backend"],
  "failed_changes": [],
  "rollback_available": true
}
```

### 3. Get System State

**Endpoint:** `GET /state`

Returns current state of the entire system.

**Response:**
```json
{
  "system_state": {
    "timestamp": "2024-01-01T00:00:00Z",
    "decision_strategy": "standard",
    "intent_mode": "simple",
    "kernel": "standard",
    "runtime": {
      "services": [
        {
          "name": "backend",
          "status": "running",
          "uptime_seconds": 1234
        }
      ]
    },
    "provider": {
      "active": "ollama",
      "available": ["ollama", "huggingface", "openai"]
    },
    "embedding_model": "sentence-transformers",
    "workflow_status": "idle",
    "active_operations": [],
    "health": {
      "overall": "healthy"
    }
  },
  "last_operation": null,
  "pending_changes": []
}
```

### 4. Get Audit Trail

**Endpoint:** `GET /audit`

Retrieves audit trail of control plane operations.

**Query Parameters:**
- `operation_type` (optional) - Filter by operation type
- `resource_type` (optional) - Filter by resource type
- `triggered_by` (optional) - Filter by user
- `result` (optional) - Filter by result (success, failure, cancelled)
- `page` (optional, default: 1) - Page number
- `page_size` (optional, default: 50) - Results per page

**Response:**
```json
{
  "entries": [
    {
      "operation_id": "uuid",
      "timestamp": "2024-01-01T00:00:00Z",
      "triggered_by": "admin",
      "operation_type": "plan",
      "resource_type": "config",
      "resource_id": "system",
      "params": {},
      "result": "success",
      "reason_code": "success_hot_swap",
      "duration_ms": 50.0,
      "error_message": null
    }
  ],
  "total_count": 1,
  "page": 1,
  "page_size": 50
}
```

## Compatibility Matrix

The Control Plane validates compatibility between:

1. **Kernel × Runtime**
   - Standard kernel: python, docker, hybrid
   - Optimized kernel: python, docker
   - Minimal kernel: python only

2. **Runtime × Provider**
   - Python runtime: huggingface, ollama, openai, google
   - Docker runtime: vllm, ollama, huggingface
   - Hybrid runtime: ollama, openai, google

3. **Provider × Model**
   - Each provider supports specific model families
   - Validated during plan phase

4. **Embedding × Provider**
   - sentence-transformers: huggingface, ollama
   - openai-embeddings: openai
   - google-embeddings: google

5. **Intent Mode Requirements**
   - Simple: No embedding required
   - Advanced: Embedding required
   - Expert: Embedding required, larger model

## Workflow

1. **Plan** - Validate changes and get execution ticket
2. **Review** - Check compatibility report and required restarts
3. **Apply** - Execute changes with ticket
4. **Verify** - Check system state and audit trail

## Error Handling

All endpoints return standard HTTP status codes:
- `200` - Success
- `400` - Invalid request or execution ticket
- `500` - Internal server error

Error responses include:
```json
{
  "detail": "Error message here"
}
```

## Audit Trail

All operations are logged with:
- Operation ID (for tracking)
- Timestamp (UTC)
- User/system that triggered operation
- Operation type and parameters
- Result and reason code
- Duration in milliseconds
- Error message (if failed)

## Security

- User identification via request headers or auth middleware
- Localhost-only restrictions for admin operations (inherited from system)
- Audit trail for compliance

## Version

API Version: v1 (2024)
