# THE CODER - Code Generation & Implementation

## Role

The Coder Agent is the main implementation executor in the Venom system. It generates clean, documented code, creates files in workspace, manages Docker Compose environments, and executes shell commands in a safe environment.

## Responsibilities

- **Code Generation** - Creating complete, ready-to-use code
- **File Management** - Saving, reading, checking file existence
- **Docker Compose Orchestration** - Creating multi-container stacks
- **Command Execution** - Safely running shell commands
- **Self-Repair** - Automatic detection and fixing of code errors (optional)

## Key Components

### 1. Available Tools

**FileSkill** (`venom_core/execution/skills/file_skill.py`):
- `write_file(path, content)` - Saves code to file in workspace
- `read_file(path)` - Reads existing code
- `list_files(directory)` - Lists files in directory
- `file_exists(path)` - Checks if file exists

**ShellSkill** (`venom_core/execution/skills/shell_skill.py`):
- `run_shell(command)` - Executes shell command in sandbox

**ComposeSkill** (`venom_core/execution/skills/compose_skill.py`):
- `create_environment(name, compose_content, auto_start)` - Creates Docker Compose environment
- `destroy_environment(name)` - Removes environment and cleans resources
- `check_service_health(env_name, service_name)` - Checks service status and logs
- `list_environments()` - Lists active environments
- `get_environment_status(name)` - Detailed environment status

### 2. Operating Principles

**Code Generation:**
1. Code should be complete and ready to use
2. Comments only when logic is complex
3. Follow best practices and naming conventions
4. Use `write_file()` for physical code saving (not just markdown)

**Infrastructure:**
- When task requires database, cache, or queue → `create_environment()` with docker-compose.yml
- Services communicate via network names (e.g., `host='redis'`, `host='postgres'`)
- Stack is isolated in Docker network, accessible from host via mapped ports

**Self-Repair (optional):**
- Automatic detection of compilation/runtime errors
- Code repair attempts (max 3 iterations)
- Logging of all repair attempts

### 3. Usage Examples

**Example 1: Simple Python File**
```
User: "Create hello.py file with Hello World function"
Action:
1. Generate function code
2. write_file("hello.py", code)
3. Confirm save
```

**Example 2: API with Redis**
```
User: "Create FastAPI with Redis cache"
Action:
1. Create docker-compose.yml (api + redis)
2. create_environment("fastapi-redis", compose_content, auto_start=True)
3. Create API code with Redis integration (host='redis')
4. write_file("main.py", code)
5. write_file("requirements.txt", dependencies)
```

**Example 3: Reading Existing Code**
```
User: "What's in config.py file?"
Action: read_file("config.py")
```

## Detailed Examples

### Example 1: Web Scraper

```python
from venom_core.agents.coder import CoderAgent

coder = CoderAgent()

# Generate web scraper code
result = await coder.generate_code(
    task="Create Python web scraper for news articles with BeautifulSoup"
)

# Coder will:
# 1. Generate scraper.py with BeautifulSoup code
# 2. Create requirements.txt
# 3. Save both files using write_file()
# 4. Return file paths and summary
```

### Example 2: Microservices Stack

```python
# Create multi-service environment
result = await coder.create_docker_environment(
    task="Set up microservices with API, database, and message queue"
)

# Coder will:
# 1. Create docker-compose.yml with:
#    - FastAPI service
#    - PostgreSQL database
#    - RabbitMQ queue
# 2. Create Dockerfile for API
# 3. Generate API code with DB and queue connections
# 4. Start the stack
# 5. Verify all services are healthy
```

### Example 3: Testing and Validation

```python
# Generate code with tests
result = await coder.generate_code(
    task="Create REST API for user management with pytest tests",
    include_tests=True
)

# Coder will:
# 1. Create main.py with API endpoints
# 2. Create test_api.py with pytest tests
# 3. Create requirements.txt
# 4. Save all files
# 5. Optionally run tests to verify
```

## Integration with Other Agents

### With Architect
```python
# Architect creates plan, Coder executes implementation steps
plan = await architect.create_plan("Build REST API")

for step in plan.steps:
    if step.agent_type == "CODER":
        result = await coder.execute(step.instruction)
```

### With Critic
```python
# Coder generates, Critic verifies
code = await coder.generate_code(task)
review = await critic.review_code(code)

if review.has_issues:
    # Coder fixes based on feedback
    fixed_code = await coder.fix_code(code, review.issues)
```

### With Researcher
```python
# Researcher finds best practices, Coder implements
knowledge = await researcher.research(
    "FastAPI async best practices"
)
code = await coder.generate_code_with_knowledge(
    task="Create async API",
    knowledge=knowledge
)
```

## Docker Compose Integration

### Example Environment

```yaml
# Generated docker-compose.yml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - postgres
    environment:
      - REDIS_HOST=redis
      - POSTGRES_HOST=postgres
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_PASSWORD=secret
    ports:
      - "5432:5432"
```

### Environment Management

```python
# List active environments
envs = await coder.list_docker_environments()
print(f"Active environments: {envs}")

# Check service health
health = await coder.check_service_health("myapp", "api")
if health.is_healthy:
    print("API is running!")
else:
    print(f"API issues: {health.logs}")

# Clean up
await coder.destroy_environment("myapp")
```

## Self-Repair Feature

### How It Works

1. **Generate Code**: Initial code generation
2. **Test**: Attempt to run/validate code
3. **Detect Errors**: Capture errors if any
4. **Analyze**: Understand error cause
5. **Fix**: Modify code to address issue
6. **Retry**: Test again (max 3 attempts)

### Example

```python
# Enable self-repair
coder.enable_self_repair(max_attempts=3)

result = await coder.generate_code(
    task="Create Python script to process CSV file"
)

# If code has errors:
# Attempt 1: Generate initial code → Error: missing import
# Attempt 2: Add missing import → Error: wrong function name
# Attempt 3: Fix function name → Success!

print(f"Repair attempts: {result.repair_attempts}")
print(f"Final status: {result.status}")
```

## Configuration

**Environment Variables** (`.env`):
```bash
# Workspace settings
WORKSPACE_PATH=./workspace
MAX_FILE_SIZE_MB=10

# Docker Compose
COMPOSE_PROJECT_PREFIX=venom
AUTO_CLEANUP_ENVS=true

# Self-repair
ENABLE_SELF_REPAIR=true
MAX_REPAIR_ATTEMPTS=3

# Code generation
DEFAULT_LANGUAGE=python
INCLUDE_COMMENTS=true
INCLUDE_DOCSTRINGS=true
```

## Best Practices

### 1. Specific Requirements
❌ Bad: "Create an API"
✅ Good: "Create FastAPI REST API with /users endpoint, PostgreSQL database, and JWT authentication"

### 2. File Organization
```python
# Good structure
workspace/
├── src/
│   ├── main.py
│   ├── models.py
│   └── utils.py
├── tests/
│   └── test_main.py
├── requirements.txt
└── docker-compose.yml
```

### 3. Error Handling
```python
try:
    result = await coder.generate_code(task)
except CodeGenerationError as e:
    print(f"Generation failed: {e.message}")
except FileWriteError as e:
    print(f"Could not save file: {e.path}")
```

### 4. Validation
```python
# Validate before saving
result = await coder.generate_code(task, validate=True)

if result.is_valid:
    await coder.save_code(result)
else:
    print(f"Validation errors: {result.errors}")
```

## Security Considerations

### Sandbox Execution
```python
# All shell commands run in sandbox
result = await coder.run_command("npm install")
# Safe - isolated from host system
```

### File System Restrictions
```python
# Only workspace is accessible
await coder.write_file("../../../etc/passwd", "hack")
# Fails - path outside workspace
```

### Docker Isolation
```python
# Each environment is isolated
env1 = await coder.create_environment("app1", compose1)
env2 = await coder.create_environment("app2", compose2)
# Completely separate networks and resources
```

## Metrics

```python
{
  "total_code_generated": 250,
  "successful_generations": 238,
  "failed_generations": 12,
  "average_generation_time_ms": 3500,
  "total_files_created": 890,
  "docker_environments_created": 45,
  "self_repair_success_rate": 0.85
}
```

## API Reference

### CoderAgent Methods

```python
class CoderAgent:
    async def generate_code(
        self,
        task: str,
        language: str = "python",
        validate: bool = True
    ) -> CodeResult:
        """Generate code for task"""
        pass
    
    async def write_file(
        self,
        path: str,
        content: str
    ) -> bool:
        """Write file to workspace"""
        pass
    
    async def create_docker_environment(
        self,
        name: str,
        compose_content: str,
        auto_start: bool = True
    ) -> EnvironmentResult:
        """Create Docker Compose environment"""
        pass
    
    async def fix_code(
        self,
        code: str,
        issues: List[str]
    ) -> str:
        """Attempt to fix code issues"""
        pass
```

### CodeResult Model

```python
@dataclass
class CodeResult:
    code: str                          # Generated code
    language: str                      # Programming language
    files_created: List[str]           # List of created files
    is_valid: bool                     # Validation status
    errors: Optional[List[str]]        # Errors if any
    repair_attempts: int               # Number of repair attempts
```

## Related Documentation

- [FileSkill](../execution/skills/file_skill.py)
- [ComposeSkill](../execution/skills/compose_skill.py)
- [Critic Agent](THE_CRITIC.md) *(Polish only)*
- [Architect Agent](THE_ARCHITECT_EN.md)

---

**Version:** 1.0
**Last Updated:** 2024-12-30
