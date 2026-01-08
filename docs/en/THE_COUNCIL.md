# The Council - AutoGen Swarm Intelligence

## Overview

The Council is a Swarm Intelligence system based on the AutoGen library, which allows Venom agents to collaborate autonomously through conversation instead of manual orchestration.

## Architecture

### Main components:

1. **VenomAgent (swarm.py)** - Wrapper connecting Semantic Kernel agents with AutoGen ConversableAgent
2. **CouncilConfig (council.py)** - Group Chat configuration and participants
3. **CouncilSession (council.py)** - Conversation session between agents
4. **Orchestrator** - Decision logic: Council vs standard flow

### Council participants:

- **User** (UserProxy) - Represents user, assigns task
- **Architect** - Plans structure and action sequence
- **Coder** - Writes code, creates files
- **Critic** - Checks code quality and security
- **Guardian** - Verifies tests, approves final version

### Conversation flow graph:

```
User → Architect → Coder ↔ Critic
                    ↓
                Guardian → User (TERMINATE)
```

## How does it work?

### 1. Automatic decision

Orchestrator automatically decides whether to use Council based on:

- **COMPLEX_PLANNING intent** - always uses Council
- **Task length** > 100 characters + presence of keywords:
  - "project", "application", "system"
  - "create game", "build"
  - "design", "implement"
  - "complete", "whole application"

### 2. Conversation process

```python
# Example task requiring Council:
task = "Write a snake game in Python with GUI using pygame"

# Conversation flow:
# 1. User assigns task
# 2. Architect plans structure (main loop, graphics, logic)
# 3. Coder writes code
# 4. Critic checks code, points out errors
# 5. Coder fixes (loop 3-4 repeats)
# 6. Guardian runs tests
# 7. If tests OK: Guardian says "TERMINATE"
```

> **⚠️ Note on termination:**
> GuardianAgent currently doesn't have a built-in mechanism for automatically sending "TERMINATE".
> For conversation to end properly, you should:
> 1. Configure GuardianAgent SYSTEM_PROMPT so that in case of positive test verification it clearly sends a message containing the word "TERMINATE"
> 2. If Guardian doesn't send "TERMINATE", conversation will end automatically after reaching max_round=20 rounds limit
> 3. **Recommended:** Add clear instruction to Guardian prompt: *"If all tests pass successfully, end your response with the word: TERMINATE"*
>
> In future versions, automatic termination mechanism after test success may be added.

### 3. Streaming to WebSocket

All conversation messages are streamed to clients via WebSocket:

```javascript
// New event types:
// - COUNCIL_STARTED
// - COUNCIL_MEMBERS
// - COUNCIL_COMPLETED
// - COUNCIL_ERROR
// - COUNCIL_AGENT_SPEAKING (TODO: add in future)
```

## Configuration

### Local-First LLM

The Council uses local model (Ollama) by default:

```python
from venom_core.core.council import create_local_llm_config

# Default configuration
llm_config = create_local_llm_config()
# {
#   "config_list": [{
#     "model": "llama3",
#     "base_url": "http://localhost:11434/v1",
#     "api_key": "EMPTY"
#   }],
#   "temperature": 0.7
# }

# Custom configuration
llm_config = create_local_llm_config(
    base_url="http://localhost:8080/v1",
    model="mixtral",
    temperature=0.5
)
```

### Enabling/disabling Council

In `orchestrator.py`:

```python
ENABLE_COUNCIL_MODE = True  # Set False to disable
COUNCIL_TASK_THRESHOLD = 100  # Minimum task length

# Edit keywords
COUNCIL_COLLABORATION_KEYWORDS = [
    "project", "application", ...
]
```

## Usage Examples

### Example 1: Simple task (uses standard flow)

```python
request = TaskRequest(content="Write hello world function")
# → Orchestrator will use CoderAgent directly
```

### Example 2: Complex task (uses Council)

```python
request = TaskRequest(content="""
Create complete TODO list application in Python with:
- FastAPI backend with REST API
- SQLite database
- Simple HTML/CSS frontend
- Unit tests
""")
# → Orchestrator activates The Council
# → Architect plans project structure
# → Coder writes successive components
# → Critic checks each component
# → Guardian verifies tests
```

### Example 3: Manual Council usage (programmatic)

```python
from venom_core.core.council import CouncilConfig, CouncilSession, create_local_llm_config

# Setup
llm_config = create_local_llm_config()
council_config = CouncilConfig(
    coder_agent=coder,
    critic_agent=critic,
    architect_agent=architect,
    guardian_agent=guardian,
    llm_config=llm_config
)

# Create session
user_proxy, group_chat, manager = council_config.create_council()
session = CouncilSession(user_proxy, group_chat, manager)

# Run conversation
result = await session.run("Write Snake game")

# Conversation analysis
print(f"Message count: {session.get_message_count()}")
print(f"Participants: {session.get_speakers()}")
```

## Requirements

### Software:

1. **Python 3.10+**
2. **pyautogen>=0.2.0** (installed automatically)
3. **semantic-kernel>=1.9.0** (required by Venom)
4. **Local LLM Server** (optional, but recommended):
   - Ollama with llama3/mixtral model
   - LiteLLM
   - vLLM
   - Llama.cpp server

### Ollama installation (recommended):

```bash
# Linux/WSL2
curl -fsSL https://ollama.com/install.sh | sh

# Run model
ollama pull llama3
ollama serve

# Test
curl http://localhost:11434/v1/models
```

## Troubleshooting

### Problem: "Connection refused to localhost:11434"

**Solution**: Make sure Ollama is running:

```bash
ollama serve
```

### Problem: Council doesn't activate for my task

**Solution**: Check task length and keywords, or force through COMPLEX_PLANNING:

```python
# In intent_manager.py - add rule for your task type
```

### Problem: Council conversation takes too long

**Solution**: Decrease `max_round` in GroupChat:

```python
# In council.py
group_chat = GroupChat(
    agents=agents,
    max_round=10,  # Instead of 20
    ...
)
```

## Metrics and monitoring

### Available WebSocket events:

```python
COUNCIL_STARTED      # Council started work
COUNCIL_MEMBERS      # Participant list
COUNCIL_COMPLETED    # Discussion completed
COUNCIL_ERROR        # Error during discussion
```

### Logs:

```python
# Enable debug logging
import logging
logging.getLogger("venom_core.core.council").setLevel(logging.DEBUG)
logging.getLogger("venom_core.core.swarm").setLevel(logging.DEBUG)
```

## Further development

### Planned features:

- [ ] Streaming individual agent messages (COUNCIL_AGENT_SPEAKING)
- [ ] User interrupt conversation capability
- [ ] Saving Council conversation history to database
- [ ] Dashboard with conversation graph visualization
- [ ] Custom flow graphs (configurable transitions)
- [ ] More specialist agents (Tester, DevOps, Security)

## See also

- [AutoGen Documentation](https://microsoft.github.io/autogen/)
- [Semantic Kernel Documentation](https://learn.microsoft.com/en-us/semantic-kernel/)
- [Venom Architecture Overview](../README.md)
