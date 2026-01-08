# THE ACADEMY - Knowledge Distillation & Autonomous Fine-Tuning

## Overview

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

## Configuration

### System Requirements

**Minimum (CPU only):**
- Docker installed
- 8 GB RAM
- Python 3.10+

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

## Roadmap

- [ ] Full Arena implementation (automated evaluation)
- [ ] Dashboard - real-time visualization
- [ ] PEFT integration for KernelBuilder
- [ ] Multi-modal learning (images, audio)
- [ ] Distributed training (multiple GPUs)
- [ ] A/B testing for models

## References

- [Unsloth](https://github.com/unslothai/unsloth) - very fast fine-tuning
- [LoRA Paper](https://arxiv.org/abs/2106.09685) - Low-Rank Adaptation
- [PEFT](https://github.com/huggingface/peft) - Parameter-Efficient Fine-Tuning

---

**Status:** ✅ Core features implemented
**Version:** 1.0 (PR 022)
**Author:** Venom Team
