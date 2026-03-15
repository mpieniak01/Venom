# THE ACADEMY - Knowledge Distillation & Autonomous Fine-Tuning

## Overview

> Source-of-truth note:
> README contains only a short Academy overview. This document is the dedicated
> module reference for architecture, setup, API, and operations.

THE ACADEMY is a machine learning system that enables Venom to improve autonomously through:
- **Knowledge Distillation** - extraction of valuable patterns from action history
- **LoRA Fine-tuning** - rapid model training without overwriting base knowledge
- **Hot Swap** - seamless "brain" replacement with newer version
- **Intelligence Genealogy** - tracking model evolution

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      THE ACADEMY                             │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐        ┌──────────────┐                   │
│  │  Lessons     │        │  Git History │                   │
│  │  Store       │        │  & Tasks     │                   │
│  └──────┬───────┘        └──────┬───────┘                   │
│         │                       │                            │
│         └───────────┬───────────┘                            │
│                     ▼                                        │
│            ┌────────────────┐                                │
│            │ DatasetCurator │                                │
│            └────────┬───────┘                                │
│                     │ dataset.jsonl                          │
│                     ▼                                        │
│            ┌────────────────┐                                │
│            │   Professor    │ ◄─── Decisions, parameters    │
│            └────────┬───────┘                                │
│                     │                                        │
│                     ▼                                        │
│            ┌────────────────┐                                │
│            │  GPUHabitat    │ ◄─── Docker training          │
│            └────────┬───────┘                                │
│                     │ adapter.pth                            │
│                     ▼                                        │
│            ┌────────────────┐                                │
│            │ ModelManager   │ ◄─── Hot Swap, Versioning     │
│            └────────────────┘                                │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. DatasetCurator (`venom_core/learning/dataset_curator.py`)

**Purpose:** Convert raw data into training format (JSONL).

**Data Sources:**
- **LessonsStore** - (Situation → Solution) pairs
- **Git History** - commit analysis (Diff → Commit Message)
- **Task History** - successful conversations with orchestrator

**Output Formats:**
- **Alpaca** - instruction-input-output format
- **ShareGPT** - conversations format (system-human-gpt)

**Usage Example:**

```python
from venom_core.learning.dataset_curator import DatasetCurator
from venom_core.memory.lessons_store import LessonsStore

# Initialize
lessons_store = LessonsStore()
curator = DatasetCurator(lessons_store=lessons_store)

# Collect data
curator.collect_from_lessons(limit=200)
curator.collect_from_git_history(max_commits=100)

# Filter
curator.filter_low_quality()

# Save
dataset_path = curator.save_dataset(format="alpaca")
print(f"Dataset saved: {dataset_path}")

# Statistics
stats = curator.get_statistics()
print(f"Number of examples: {stats['total_examples']}")
```

### 2. GPUHabitat (`venom_core/infrastructure/gpu_habitat.py`)

**Purpose:** Manage training environment with GPU support.

**Features:**
- Automatic GPU detection and nvidia-container-toolkit
- Running containers with Unsloth (very fast fine-tuning)
- Training job monitoring
- CPU fallback if no GPU

**Usage Example:**

```python
from venom_core.infrastructure.gpu_habitat import GPUHabitat

# Initialize
habitat = GPUHabitat(enable_gpu=True)

# Run training
job_info = habitat.run_training_job(
    dataset_path="./data/training/dataset.jsonl",
    base_model="unsloth/Phi-3-mini-4k-instruct",
    output_dir="./data/models/training_0",
    lora_rank=16,
    learning_rate=2e-4,
    num_epochs=3,
)

print(f"Job ID: {job_info['job_name']}")
print(f"Container: {job_info['container_id']}")

# Monitor progress
status = habitat.get_training_status(job_info['job_name'])
print(f"Status: {status['status']}")
print(f"Logs:\n{status['logs']}")
```

### 3. Professor (`venom_core/agents/professor.py`)

**Purpose:** Data Scientist Agent - learning process supervisor.

**Responsibilities:**
- Decision to start training (minimum 100 lessons)
- Parameter selection (learning rate, epochs, LoRA rank)
- Model evaluation (Arena - version comparison)
- Promotion of better models

**Commands:**

```python
from venom_core.agents.professor import Professor

# Initialize
professor = Professor(kernel, dataset_curator, gpu_habitat, lessons_store)

# Check readiness
decision = professor.should_start_training()
if decision["should_train"]:
    print("✅ Ready for training!")

# Generate dataset
result = await professor.process("prepare learning materials")

# Start training
result = await professor.process("start training")

# Check progress
result = await professor.process("check training progress")

# Evaluate model
result = await professor.process("evaluate model")
```

### 4. ModelManager (`venom_core/core/model_manager.py`)

**Purpose:** Model version management and Hot Swap.

**Features:**
- Model version registration
- Hot swap (replacement without restart)
- Intelligence Genealogy (version history)
- Metrics comparison between versions
- Ollama integration (Modelfile creation)

**Usage Example:**

```python
from venom_core.core.model_manager import ModelManager

# Initialize
manager = ModelManager()

# Register versions
manager.register_version(
    version_id="v1.0",
    base_model="phi3:latest",
    performance_metrics={"accuracy": 0.85}
)

manager.register_version(
    version_id="v1.1",
    base_model="phi3:latest",
    adapter_path="./data/models/adapter",
    performance_metrics={"accuracy": 0.92}
)

# Activate new version (hot swap)
manager.activate_version("v1.1")

# Compare versions
comparison = manager.compare_versions("v1.0", "v1.1")
print(f"Improvement: {comparison['metrics_diff']['accuracy']['diff_pct']:.1f}%")

# Genealogy
genealogy = manager.get_genealogy()
for version in genealogy['versions']:
    print(f"{version['version_id']}: {version['performance_metrics']}")
```

## Workflow: From Lesson to Model

```
1. Experience Collection
   └─> LessonsStore.add_lesson() after each success

2. Dataset Curation (automatic or on-demand)
   └─> DatasetCurator.collect_from_*()
   └─> Optional: include files marked "Use for training" in Academy → Data Conversion (right column: converted files)
   └─> Minimum 50-100 examples

3. Training Decision
   └─> Professor.should_start_training()
   └─> Checks: lesson count, interval from last training

4. Training (in background, Docker + GPU)
   └─> GPUHabitat.run_training_job()
   └─> Unsloth + LoRA (fast, VRAM-efficient)

5. Evaluation (Arena)
   └─> Professor evaluates: Old Model vs New Model
   └─> Test suite (10 coding questions)

6. Promotion
   └─> ModelManager.activate_version()
   └─> Hot swap - Venom uses new model

7. Monitoring
   └─> Dashboard: Loss charts, statistics, genealogy
```

## Ollama LoRA Deployment Path (External Training)

The Academy contract separates training and runtime deployment:

1. **Training engine (external):**
  - LoRA/QLoRA training runs in Academy (HF/PEFT/Unsloth pipeline).
  - Ollama is not used as a native LoRA trainer in this repository contract.

2. **Runtime deployment engine (Ollama):**
  - Academy exports and activates adapter artifacts.
  - Runtime capabilities are exposed via `GET /api/v1/system/llm-runtime/options`:
    - `supports_native_training`
    - `supports_adapter_import_safetensors`
    - `supports_adapter_import_gguf`
    - `supports_adapter_runtime_apply`

3. **Compatibility guard (blocking):**
  - During adapter deploy to Ollama, Academy validates adapter `base_model` against selected runtime `FROM` model.
  - On mismatch, deploy is blocked with HTTP `400` and reason code:
    - `ADAPTER_BASE_MODEL_MISMATCH`

Deployment checklist:

1. Train adapter from a known base model in Academy.
2. Select runtime server and runtime model first (`server -> model -> adapter`).
3. Activate adapter with deploy flag.
4. If mismatch is reported, switch runtime model to matching base model and retry.

Operational note:

1. Academy no longer supports manual repair flow for legacy adapters.
2. Canonical adapter metadata is mandatory.
3. Adapters without complete `metadata.json` are invalid artifacts and should be deleted/regenerated, not patched in place.

## ONNX LoRA Deployment Path (Direct Adapter Deploy)

Academy supports direct ONNX runtime deployment for LoRA adapters through merge/export pipeline:

1. Training output:
   - adapter artifacts in `data/models/<job_id>/adapter`.
2. Deploy pipeline:
   - LoRA merge to HF runtime directory (`runtime_vllm`),
   - ONNX export with `onnxruntime-genai` builder (`-i <merged_path>`),
   - runtime activation: `runtime_id=onnx`, `deploy_to_chat_runtime=true`.
3. Gemma-3 contract normalization:
   - export path prepares a temporary text-only input config for builder,
   - generated runtime config is normalized to `model.type=gemma3_text`,
   - decoder input contract uses `input_ids` (not `inputs_embeds`) for runtime generation.

Validated E2E (live):
- full cycle `activate -> inference SSE -> deactivate` completed with HTTP `200/200/200`
- artifact run: `test-results/202d/full_cycle_20260315_093542`

## Configuration

### System Requirements

**Minimum (CPU only):**
- Docker installed
- 8 GB RAM
- Python 3.12+

**Recommended (GPU):**
- NVIDIA GPU (min. 8 GB VRAM)
- nvidia-container-toolkit
- CUDA 12.0+
- 16 GB RAM

### Installing nvidia-container-toolkit (Ubuntu/Debian)

```bash
# Add NVIDIA repository
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# Install
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Restart Docker
sudo systemctl restart docker

# Test
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

### Environment Configuration (`.env`)

```bash
# Paths
WORKSPACE_ROOT=./workspace
MEMORY_ROOT=./data/memory

# Base model for fine-tuning
DEFAULT_BASE_MODEL=unsloth/Phi-3-mini-4k-instruct

# Training parameters
DEFAULT_LORA_RANK=16
DEFAULT_LEARNING_RATE=2e-4
DEFAULT_NUM_EPOCHS=3

# GPU
ENABLE_GPU=true
TRAINING_IMAGE=unsloth/unsloth:latest

# Training criteria
MIN_LESSONS_FOR_TRAINING=100
MIN_TRAINING_INTERVAL_HOURS=24
```

## Example: Automation with Scheduler

```python
from venom_core.core.scheduler import BackgroundScheduler
from venom_core.agents.professor import Professor

async def auto_training_job():
    """Periodic task - checks if training time."""
    decision = professor.should_start_training()
    if decision["should_train"]:
        logger.info("Starting automatic training...")
        await professor.process("prepare learning materials")
        await professor.process("start training")

# Add to scheduler (every 24h)
scheduler = BackgroundScheduler()
scheduler.add_interval_job(
    func=auto_training_job,
    minutes=60 * 24,  # Once per day
    job_id="auto_training",
    description="Automatic Venom training"
)
```

## Best Practices

1. **Quality > Quantity**
   - Filter incorrect examples
   - Verify output before adding to LessonsStore
   - Use tags for categorization

2. **Start with Small Datasets**
   - 50-100 examples to start
   - Monitor overfitting

3. **Regularity > Massiveness**
   - Better 100 new examples weekly than 1000 once a year
   - Model "doesn't forget" thanks to LoRA

4. **Test Before Promotion**
   - Arena - compare on test set
   - Check regression (whether new model is worse at something)

5. **Backup Models**
   - ModelManager keeps history
   - You can revert to previous version

## Troubleshooting

**Problem:** Training hangs
- **Solution:** Decrease `batch_size` or `max_seq_length`

**Problem:** CUDA Out of Memory
- **Solution:** Enable `load_in_4bit=True` (already default), decrease `lora_rank`

**Problem:** Dataset too small (< 50 examples)
- **Solution:** Collect more lessons, enable Task History, analyze more commits

**Problem:** Model doesn't improve
- **Solution:**
  - Increase `num_epochs` (e.g., 5-10)
  - Check dataset quality (are there errors?)
  - Use higher `learning_rate` (e.g., 3e-4)

## API Reference (v2.0 - FastAPI)

The Academy is now fully integrated with the FastAPI backend and web UI.

### Installation

```bash
# Install Academy dependencies
pip install -r requirements-academy.txt

# Enable in .env
ENABLE_ACADEMY=true
ACADEMY_ENABLE_GPU=true
```

### REST API Endpoints

All endpoints are available at `/api/v1/academy/`:

#### **GET /api/v1/academy/status**
Get Academy system status.

**Response:**
```json
{
  "enabled": true,
  "components": {
    "professor": true,
    "dataset_curator": true,
    "gpu_habitat": true,
    "lessons_store": true,
    "model_manager": true
  },
  "gpu": {
    "available": true,
    "enabled": true
  },
  "lessons": {
    "total_lessons": 250
  },
  "jobs": {
    "total": 5,
    "running": 1,
    "finished": 3,
    "failed": 1
  },
  "config": {
    "min_lessons": 100,
    "training_interval_hours": 24,
    "default_base_model": "unsloth/Phi-3-mini-4k-instruct"
  }
}
```

#### **POST /api/v1/academy/dataset**
Curate training dataset from LessonsStore and Git history.

**Request:**
```json
{
  "lessons_limit": 200,
  "git_commits_limit": 100,
  "format": "alpaca"
}
```

**Response:**
```json
{
  "success": true,
  "dataset_path": "./data/training/dataset_20240101_120000.jsonl",
  "statistics": {
    "total_examples": 190,
    "lessons_collected": 150,
    "git_commits_collected": 50,
    "removed_low_quality": 10,
    "avg_input_length": 250,
    "avg_output_length": 180
  },
  "message": "Dataset curated successfully: 190 examples"
}
```

#### **POST /api/v1/academy/train**
Start a new training job.

**Request:**
```json
{
  "lora_rank": 16,
  "learning_rate": 0.0002,
  "num_epochs": 3,
  "batch_size": 4,
  "max_seq_length": 2048
}
```

**Response:**
```json
{
  "success": true,
  "job_id": "training_20240101_120000",
  "message": "Training started successfully",
  "parameters": {
    "lora_rank": 16,
    "learning_rate": 0.0002,
    "num_epochs": 3,
    "batch_size": 4
  }
}
```

#### **GET /api/v1/academy/train/{job_id}/status**
Get training job status and logs.

**Response:**
```json
{
  "job_id": "training_20240101_120000",
  "status": "running",
  "logs": "Epoch 1/3...\nTraining loss: 0.45...",
  "started_at": "2024-01-01T12:00:00",
  "finished_at": null,
  "adapter_path": null
}
```

Status values: `queued`, `preparing`, `running`, `finished`, `failed`, `cancelled`

#### **GET /api/v1/academy/jobs**
List all training jobs.

**Query parameters:**
- `limit` (int): Maximum jobs to return (1-500, default: 50)
- `status` (str): Filter by status

**Response:**
```json
{
  "count": 2,
  "jobs": [
    {
      "job_id": "training_002",
      "status": "running",
      "started_at": "2024-01-02T10:00:00",
      "parameters": {
        "lora_rank": 16,
        "num_epochs": 3
      }
    },
    {
      "job_id": "training_001",
      "status": "finished",
      "started_at": "2024-01-01T10:00:00",
      "finished_at": "2024-01-01T11:30:00",
      "adapter_path": "./data/models/training_001/adapter"
    }
  ]
}
```

#### **GET /api/v1/academy/adapters**
List available trained adapters.

**Response:**
```json
[
  {
    "adapter_id": "training_20240101_120000",
    "adapter_path": "./data/models/training_20240101_120000/adapter",
    "base_model": "unsloth/Phi-3-mini-4k-instruct",
    "created_at": "2024-01-01T12:00:00",
    "training_params": {
      "lora_rank": 16,
      "num_epochs": 3
    },
    "is_active": false
  }
]
```

#### **POST /api/v1/academy/adapters/activate**
Activate a LoRA adapter (hot-swap).

**Request:**
```json
{
  "adapter_id": "training_20240101_120000",
  "adapter_path": "./data/models/training_20240101_120000/adapter",
  "runtime_id": "ollama",
  "model_id": "gemma3:latest",
  "deploy_to_chat_runtime": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Adapter activated and deployed to chat runtime (ollama:venom-adapter-training_20240101_120000)",
  "adapter_id": "training_20240101_120000",
  "deployed": true,
  "runtime_id": "ollama",
  "chat_model": "venom-adapter-training_20240101_120000"
}
```

Notes:
1. `deploy_to_chat_runtime` is optional (defaults to `false`).
2. When `deploy_to_chat_runtime=true`, both `runtime_id` and `model_id` must be provided explicitly.
3. Runtime auto-deploy is implemented for `ollama` and `vllm`.
4. `onnx` remains guardrails-only for adapter deploy and returns `runtime_not_supported:onnx`.
5. Cloud runtimes are not valid targets for Academy adapter deploy.
6. Academy does not guess runtime/model from config, previous runtime state, or legacy adapter metadata.

#### **POST /api/v1/academy/adapters/deactivate**
Deactivate current adapter (rollback to base model).

Optional query parameter:
1. `deploy_to_chat_runtime=true|false` (default `true`)

**Response:**
```json
{
  "success": true,
  "message": "Adapter deactivated and chat runtime rolled back to phi3:latest",
  "rolled_back": true,
  "runtime_id": "ollama",
  "chat_model": "phi3:latest"
}
```

Model/adapter contract in Chat:
1. `Model` selector = runtime-servable model (from `/api/v1/system/llm-runtime/options`).
2. `Adapter` selector = Academy adapter overlay (optional deploy depending on runtime capability).
3. Runtime capability is exposed in runtime options as:
   - `adapter_deploy_supported`
   - `adapter_deploy_mode`
4. Invalid adapters without canonical metadata are blocked and should not be migrated manually.

#### **GET /api/v1/academy/train/{job_id}/logs/stream**
Stream training logs in real-time (SSE).

**Response:** Server-Sent Events stream

**Event Types:**
```json
// Connection established
{"type": "connected", "job_id": "training_20240101_120000"}

// Log line
{"type": "log", "line": 42, "message": "Epoch 1/3...", "timestamp": "2024-01-01T10:00:00Z"}

// Status change
{"type": "status", "status": "completed"}

// Error
{"type": "error", "message": "Container not found"}
```

**Headers:**
- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`
- `Connection: keep-alive`

#### **DELETE /api/v1/academy/train/{job_id}**
Cancel a running training job.

**Response:**
```json
{
  "success": true,
  "message": "Training job cancelled",
  "job_id": "training_20240101_120000"
}
```

**Note:** Cancelling a job automatically stops and removes the Docker container.

#### **PR 191: Self-Learning API (`/api/v1/academy/self-learning/*`)**
Self-learning extends Academy with autonomous ingestion from repository sources (`docs`, `docs_dev`, `code`) in two modes:
- `llm_finetune` - prepare dataset and start LoRA/QLoRA-compatible training flow
- `rag_index` - chunk and index content into vector store

Available endpoints:
- `POST /api/v1/academy/self-learning/start`
- `GET /api/v1/academy/self-learning/capabilities`
- `GET /api/v1/academy/self-learning/{run_id}/status`
- `GET /api/v1/academy/self-learning/list?limit=...`
- `DELETE /api/v1/academy/self-learning/{run_id}`
- `DELETE /api/v1/academy/self-learning/all`

Status model:
- `pending | running | completed | completed_with_warnings | failed`

Safety defaults:
- allowlisted roots (`docs/`, `docs_dev/`, `venom_core/`, `web-next/`, `scripts/`)
- blocked paths (`.git/`, `.venv/`, `node_modules/`, `data/`, `test-results/`, `dist/`, `build/`)
- extension, file-size, file-count and total-size limits.

## Web UI

Academy dashboard is available at **http://localhost:3000/academy**

### Features:

1. **Overview Panel**
   - System status and component health
   - GPU availability and detailed info (VRAM, utilization)
   - LessonsStore statistics
   - Job statistics (total, running, finished, failed)
   - Configuration display

2. **Dataset Panel**
   - Dataset curation interface
   - Configure lessons and git commits limits
   - View statistics (examples collected, removed, avg lengths)
   - Dataset path display

3. **Training Panel**
   - Training parameter configuration (LoRA rank, learning rate, epochs, batch size)
   - Start training jobs with validation
   - Job history with status indicators
   - Auto-refresh for running jobs (10s interval)
   - Cancel running jobs with automatic container cleanup
   - **Real-time log viewer** with SSE streaming
   - **Live metrics display** - Epoch progress, loss tracking
   - **Progress indicators** - Visual bars and percentages
   - Pause/resume log streaming
   - Auto-scroll with manual override
   - Line numbers and timestamps in logs
   - Best/current/average loss tracking

4. **Adapters Panel**
   - List all trained adapters with active state highlighting
   - View adapter metadata (parameters, creation date)
   - Activate adapters (hot-swap without backend restart)
   - Deactivate/rollback to base model
   - Active adapter indicator

5. **Self-Learning Panel (PR 191)**
   - Mode switch: `LLM fine-tune` / `RAG index`
   - Source selector: `docs`, `docs_dev`, `code`
   - Live run status + logs + history
   - Preflight-aware embedding/runtime checks for RAG mode

### Dev Stability Note (web-next)
- Default local dev runtime uses webpack:
  - `npm --prefix web-next run dev` -> `next dev --webpack`
  - `npm --prefix web-next run dev:turbo` -> optional Turbopack mode (`next dev --turbo`)
- Turbopack regression smoke:
  - `npm --prefix web-next run test:dev:turbo:smoke:clean`
- Keep one active dev instance to avoid `.next/dev/lock` conflicts.

## Roadmap

- [x] REST API endpoints (v2.0)
- [x] Web UI Dashboard (v2.0)
- [x] Job persistence and history (v2.0)
- [x] Adapter activation/deactivation (v2.1)
- [x] Container management and cleanup (v2.1)
- [x] GPU monitoring (v2.1)
- [x] **Real-time log streaming (SSE)** (v2.2)
- [x] **Training metrics parsing** (v2.3)
- [x] **Progress indicators** (v2.3)
- [ ] ETA calculation
- [ ] Full Arena implementation (automated evaluation)
- [ ] PEFT integration for KernelBuilder
- [ ] Multi-modal learning (images, audio)
- [ ] Distributed training (multiple GPUs)
- [ ] A/B testing for models

## References

- [Unsloth](https://github.com/unslothai/unsloth) - very fast fine-tuning
- [LoRA Paper](https://arxiv.org/abs/2106.09685) - Low-Rank Adaptation
- [PEFT](https://github.com/huggingface/peft) - Parameter-Efficient Fine-Tuning

---

**Status:** ✅ Full monitoring stack with metrics parsing and progress tracking
**Version:** 2.3 (PR 090 Phase 4)
**Author:** Venom Team

## Changelog

### v2.3 (Phase 4 - Current)
- ✅ Training metrics parser (epoch, loss, lr, accuracy)
- ✅ Real-time metrics extraction from logs
- ✅ Progress indicators with visual bars
- ✅ Loss tracking (current, best, average)
- ✅ Metrics display in LogViewer
- ✅ Support for multiple log formats
- ✅ 17 comprehensive test cases for parser

### v2.2 (Phase 3)
- ✅ Real-time log streaming via SSE
- ✅ Live log viewer component with auto-scroll
- ✅ Pause/resume log streaming
- ✅ Connection status indicators
- ✅ Timestamped log lines
- ✅ Graceful error handling

### v2.1 (Phase 2)
- ✅ ModelManager adapter integration (activate/deactivate)
- ✅ Container cleanup on job cancellation
- ✅ GPU detailed monitoring (nvidia-smi)
- ✅ Adapter rollback functionality
- ✅ Active adapter state tracking
- ✅ Comprehensive test coverage (18 test cases)

### v2.0 (Phase 1 - MVP)
- ✅ REST API endpoints (11 endpoints)
- ✅ Web UI Dashboard (4 panels)
- ✅ Job persistence and history
- ✅ Dataset curation
- ✅ Training job management
