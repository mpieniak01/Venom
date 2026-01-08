# Hybrid AI Engine - Documentation

## Overview

The Hybrid AI Engine is a key component of the Venom system that manages intelligent routing of queries between local LLM and cloud. The system prioritizes privacy and zero operational cost through a "Local First" strategy.

## Architecture

### Components

1. **HybridModelRouter** (`venom_core/execution/model_router.py`)
   - Main query routing logic
   - Operating mode management (LOCAL/HYBRID/CLOUD)
   - Sensitive data detection

2. **KernelBuilder** (`venom_core/execution/kernel_builder.py`)
   - Building Semantic Kernel with appropriate connectors
   - Local LLM support (Ollama/vLLM)
   - Google Gemini support
   - OpenAI support
   - Azure OpenAI stub

3. **Configuration** (`venom_core/config.py`)
   - AI mode parameters
   - API keys
   - Model settings

## Operating Modes

### LOCAL (Default)
```env
AI_MODE=LOCAL
```
- **All** queries directed to local LLM
- Cloud **completely blocked**
- 100% privacy, $0 costs
- Ideal for offline work

### HYBRID (Intelligent)
```env
AI_MODE=HYBRID
GOOGLE_API_KEY=your_key_here
```
- Simple tasks → Local LLM
- Complex tasks → Cloud (Gemini/OpenAI)
- Sensitive data → **ALWAYS Local**
- Fallback to Local if cloud unavailable

### CLOUD
```env
AI_MODE=CLOUD
GOOGLE_API_KEY=your_key_here
```
- All queries (except sensitive) → Cloud
- Sensitive data → **ALWAYS Local**

## Task Routing

### TaskType

| Task Type | LOCAL Mode | HYBRID Mode | CLOUD Mode |
|-----------|------------|-------------|------------|
| `STANDARD` | Local | Local | Cloud |
| `CHAT` | Local | Local | Cloud |
| `CODING_SIMPLE` | Local | Local | Cloud |
| `CODING_COMPLEX` | Local | Cloud* | Cloud |
| `SENSITIVE` | Local | Local | Local |
| `ANALYSIS` | Local | Cloud* | Cloud |
| `GENERATION` | Local | Cloud* | Cloud |

\* = If API key available, otherwise fallback to Local

## Privacy Protection

### Hard Block for Sensitive Data

The system automatically detects sensitive content and **never** sends it to cloud:

```python
# Detected keywords:
- password, hasło
- token, key, klucz
- secret
- api_key, apikey
- credentials, uwierzytelnienie
```

### SENSITIVE_DATA_LOCAL_ONLY Flag

```env
SENSITIVE_DATA_LOCAL_ONLY=True  # Enabled by default
```

When enabled, **all** queries are scanned for sensitive content, regardless of TaskType.

## Configuration

### Minimal (Local Only - $0)

```env
AI_MODE=LOCAL
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1
LLM_MODEL_NAME=llama3
```

### Hybrid with Google Gemini

```env
AI_MODE=HYBRID
GOOGLE_API_KEY=your_google_api_key
HYBRID_CLOUD_PROVIDER=google
HYBRID_LOCAL_MODEL=llama3
HYBRID_CLOUD_MODEL=gemini-1.5-pro
```

### Hybrid with OpenAI

```env
AI_MODE=HYBRID
OPENAI_API_KEY=your_openai_api_key
HYBRID_CLOUD_PROVIDER=openai
HYBRID_LOCAL_MODEL=llama3
HYBRID_CLOUD_MODEL=gpt-4o
```

## Usage in Code

### Example Integration

```python
from venom_core.execution.model_router import HybridModelRouter, TaskType

# Initialization (usually in agent __init__)
router = HybridModelRouter()

# Get routing decision for simple query
routing_info = router.get_routing_info_for_task(
    task_type=TaskType.CHAT,
    prompt="Hello, how are you?"
)
print(f"Would use: {routing_info['provider']} ({routing_info['model_name']})")

# Get routing decision for complex task
routing_info = router.get_routing_info_for_task(
    task_type=TaskType.CODING_COMPLEX,
    prompt="Analyze architecture of 10 microservices..."
)
print(f"Would use: {routing_info['provider']} ({routing_info['model_name']})")

# Get decision for sensitive data (ALWAYS local)
routing_info = router.get_routing_info_for_task(
    task_type=TaskType.SENSITIVE,
    prompt="My password is abc123"
)
print(f"Would use: {routing_info['provider']}")  # Always 'local'
```

### Agent Integration Pattern

```python
class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="MyAgent")
        self.router = HybridModelRouter()
        
    async def execute(self, task: str) -> Result:
        # Classify task type
        task_type = self._classify_task(task)
        
        # Get routing info
        routing = self.router.get_routing_info_for_task(
            task_type=task_type,
            prompt=task
        )
        
        # Build appropriate kernel
        kernel = await self.router.build_kernel()
        
        # Execute with routed model
        result = await kernel.invoke(
            prompt=task,
            settings=routing['settings']
        )
        
        return result
```

## Fallback Mechanism

The system implements graceful degradation:

1. **Primary**: Try cloud provider (if HYBRID/CLOUD mode)
2. **Fallback**: Use local LLM if cloud fails
3. **Error Handling**: Return informative error if both fail

```python
# Example fallback flow
try:
    # Try cloud first (in HYBRID mode for complex task)
    result = await cloud_model.generate(prompt)
except CloudAPIError:
    logger.warning("Cloud unavailable, falling back to local")
    result = await local_model.generate(prompt)
except LocalModelError:
    logger.error("Both cloud and local failed")
    raise ModelUnavailableError()
```

## Cost Optimization

### Token Tracking

```python
from venom_core.ops.cost_guard import CostGuard

guard = CostGuard()

# Before API call
routing = router.get_routing_info_for_task(task_type, prompt)

# After API call
guard.track_usage(
    provider=routing['provider'],
    tokens_used=response.usage.total_tokens,
    cost_usd=calculate_cost(response.usage)
)
```

### Budget Alerts

```env
# Set budget limits
DEFAULT_MAX_TOKENS=100000
DEFAULT_MAX_COST_USD=10.0
```

The system will:
- Warn at 50%, 75%, 90% usage
- Block at 100% usage
- Suggest switching to local mode

## Performance Considerations

### Local LLM (Ollama/vLLM)

**Pros:**
- Zero cost
- Complete privacy
- No network dependency
- Consistent latency

**Cons:**
- Slower inference (depends on hardware)
- Limited model size (RAM/VRAM constrained)
- Lower quality for complex tasks

### Cloud LLM (Gemini/GPT-4)

**Pros:**
- Faster inference
- Larger, more capable models
- Better for complex reasoning

**Cons:**
- API costs
- Network dependency
- Latency variance
- Privacy concerns

### Hybrid Strategy

Optimal balance:
- Use local for: chat, simple code, quick queries
- Use cloud for: complex analysis, large generation, specialized tasks
- Always local for: sensitive data, private information

## Model Selection Guidelines

### When to Use Local

- ✅ Simple conversations
- ✅ Code snippets (<100 lines)
- ✅ Quick Q&A
- ✅ Sensitive data processing
- ✅ Offline scenarios

### When to Use Cloud

- ✅ Complex reasoning tasks
- ✅ Large code generation (>500 lines)
- ✅ Multi-step analysis
- ✅ Specialized domains
- ✅ High-quality requirements

## Security Best Practices

1. **Never hardcode API keys**
   ```python
   # ❌ Bad
   api_key = "sk-abc123..."
   
   # ✅ Good
   api_key = os.getenv("OPENAI_API_KEY")
   ```

2. **Validate sensitive data detection**
   ```python
   # Test with known sensitive content
   assert router.contains_sensitive_data("password: abc123")
   ```

3. **Monitor API usage**
   ```python
   # Regular budget checks
   status = cost_guard.get_status("openai")
   if status['usage_percent'] > 80:
       alert_admin("High API usage detected")
   ```

4. **Use environment-specific configs**
   ```bash
   # Development
   AI_MODE=LOCAL
   
   # Production
   AI_MODE=HYBRID
   GOOGLE_API_KEY=${PROD_GOOGLE_KEY}
   ```

## Troubleshooting

### Issue: "Model not available"
**Solution:**
- Check if Ollama/vLLM is running: `curl http://localhost:11434/v1/models`
- Verify `LLM_LOCAL_ENDPOINT` is correct
- Check if model is downloaded: `ollama list`

### Issue: "API key invalid"
**Solution:**
- Verify API key in `.env`
- Check key permissions and quotas
- Ensure key is for correct provider

### Issue: "Slow local inference"
**Solution:**
- Use smaller model (e.g., llama3:8b instead of llama3:70b)
- Enable GPU acceleration
- Increase RAM allocation
- Consider vLLM for better performance

### Issue: "High API costs"
**Solution:**
- Review `TaskType` classification
- Increase local usage in HYBRID mode
- Set stricter budgets
- Cache frequent queries

## Monitoring and Metrics

```python
# Collect metrics
metrics = router.get_metrics()

print(f"Total requests: {metrics['total_requests']}")
print(f"Local requests: {metrics['local_requests']}")
print(f"Cloud requests: {metrics['cloud_requests']}")
print(f"Sensitive data blocks: {metrics['sensitive_blocks']}")
print(f"Fallback count: {metrics['fallback_count']}")
print(f"Total tokens: {metrics['total_tokens']}")
print(f"Total cost: ${metrics['total_cost_usd']:.2f}")
```

## API Reference

### HybridModelRouter

```python
class HybridModelRouter:
    def get_routing_info_for_task(
        self,
        task_type: TaskType,
        prompt: str
    ) -> Dict[str, Any]:
        """
        Determine routing for a task.
        
        Args:
            task_type: Type of task
            prompt: Task prompt (checked for sensitive data)
            
        Returns:
            Dict with: provider, model_name, settings
        """
        pass
    
    async def build_kernel(self) -> Kernel:
        """Build Semantic Kernel with configured providers."""
        pass
    
    def contains_sensitive_data(self, text: str) -> bool:
        """Check if text contains sensitive information."""
        pass
```

### TaskType Enum

```python
class TaskType(Enum):
    STANDARD = "standard"
    CHAT = "chat"
    CODING_SIMPLE = "coding_simple"
    CODING_COMPLEX = "coding_complex"
    SENSITIVE = "sensitive"
    ANALYSIS = "analysis"
    GENERATION = "generation"
```

## Related Documentation

- [Model Management](MODEL_MANAGEMENT.md)
- [Cost Guard](COST_GUARD.md)
- [Configuration Panel](CONFIG_PANEL.md)
- [Backend Architecture](BACKEND_ARCHITECTURE.md)

---

**Version:** 1.0
**Last Updated:** 2024-12-30
