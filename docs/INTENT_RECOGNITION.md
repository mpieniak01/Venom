# Hybrid Intent Recognition (Local-First Brain)

User intent classification system using local or cloud LLMs.

## Configuration

### Local Mode (default)

Create `.env` file in project root directory:

```env
LLM_SERVICE_TYPE=local
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1
LLM_MODEL_NAME=phi3:latest
LLM_LOCAL_API_KEY=venom-local
```

### Cloud Mode (OpenAI)

```env
LLM_SERVICE_TYPE=openai
LLM_MODEL_NAME=gpt-4o
OPENAI_API_KEY=sk-your-api-key-here
```

## Intent Types

System classifies user input into one of three categories:

1. **CODE_GENERATION** - code requests, scripts, refactoring
   - Example: "Write a Python function for sorting"

2. **KNOWLEDGE_SEARCH** - knowledge questions, facts, explanations
   - Example: "What is GraphRAG?"

3. **GENERAL_CHAT** - general conversation, greetings
   - Example: "Hello Venom, how are you?"

## Usage in Code

### Basic Usage with Orchestrator

```python
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.core.models import TaskRequest

# Initialization
state_manager = StateManager(state_file_path="./data/state.json")
orchestrator = Orchestrator(state_manager)

# Submit task - intent will be automatically classified
response = await orchestrator.submit_task(
    TaskRequest(content="Write a sorting function")
)

# Check result
task = state_manager.get_task(response.task_id)
print(f"Result: {task.result}")  # Contains classified intent
```

### Direct IntentManager Usage

```python
from venom_core.core.intent_manager import IntentManager

# Use default configuration
manager = IntentManager()

# Classify intent
intent = await manager.classify_intent("Write Python code")
print(f"Intent: {intent}")  # Output: CODE_GENERATION
```

### Custom Configuration

```python
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.core.intent_manager import IntentManager
from pydantic_settings import BaseSettings

# Custom settings
class CustomSettings(BaseSettings):
    LLM_SERVICE_TYPE: str = "local"
    LLM_LOCAL_ENDPOINT: str = "http://localhost:8000/v1"
    LLM_MODEL_NAME: str = "mistral:latest"
    LLM_LOCAL_API_KEY: str = "custom-key"

# Build kernel with custom settings
builder = KernelBuilder(settings=CustomSettings())
kernel = builder.build_kernel()

# Create IntentManager with custom kernel
manager = IntentManager(kernel=kernel)
```

## Requirements

### Local Mode

Required local LLM server compatible with OpenAI API, e.g.:

- [Ollama](https://ollama.ai/) - simplest solution
  ```bash
  ollama serve
  ollama pull phi3
  ```

- [vLLM](https://vllm.ai/) - more efficient for production
- [LocalAI](https://localai.io/) - alternative

### Cloud Mode

Required OpenAI API key.

## Tests

```bash
# All tests
pytest tests/test_kernel_builder.py tests/test_intent_manager.py tests/test_orchestrator_intent.py -v

# KernelBuilder tests only
pytest tests/test_kernel_builder.py -v

# IntentManager tests only
pytest tests/test_intent_manager.py -v
```

## Troubleshooting

### Connection Error with Local Server

Make sure local LLM server is running:

```bash
# For Ollama
curl http://localhost:11434/v1/models

# Check if model is downloaded
ollama list
```

### Slow Responses

Local models may respond slower than cloud. Consider:
- Using smaller model (e.g., `phi3:mini`)
- GPU acceleration (`ollama run phi3 --gpu`)
- Increasing timeouts in configuration

## License and Privacy

Local mode maintains full privacy - no data leaves your computer.
