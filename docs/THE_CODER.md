# THE CODER - Code Generation & Implementation

## Role

Coder Agent is the main implementation executor in the Venom system. It generates clean, documented code, creates files in workspace, manages Docker Compose environments, and executes shell commands in a secure environment.

## Responsibilities

- **Code generation** - Creating complete, ready-to-use code
- **File management** - Writing, reading, checking file existence
- **Docker Compose orchestration** - Creating multi-container stacks
- **Command execution** - Safely running shell commands
- **Self-repair** - Automatic detection and fixing of code errors (optional)

## Key Components

### 1. Available Tools

**FileSkill** (`venom_core/execution/skills/file_skill.py`):
- `write_file(path, content)` - Writes code to file in workspace
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

**Code generation:**
1. Code should be complete and ready to use
2. Comments only when logic is complex
3. Compliance with best practices and naming conventions
4. Use `write_file()` for physical code writing (not just markdown)

**Infrastructure:**
- When task requires database, cache or queue → `create_environment()` with docker-compose.yml
- Services communicate through network names (e.g., `host='redis'`, `host='postgres'`)
- Stack is isolated in Docker network, accessible from host through mapped ports

**Self-repair (optional):**
- Automatic detection of compilation/runtime errors
- Code repair attempt (max 3 iterations)
- Logging of all repair attempts

### 3. Usage Examples

**Example 1: Simple Python file**
```
User: "Create hello.py file with Hello World function"
Action:
1. Generate function code
2. write_file("hello.py", code)
3. Confirm writing
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

**Example 3: Reading existing code**
```
User: "What's in config.py file?"
Action: read_file("config.py")
```

## System Integration

### Execution Flow

```
ArchitectAgent creates plan:
  Step 2: CODER - "Create app.py file with REST API"
        ↓
TaskDispatcher calls CoderAgent.execute()
        ↓
CoderAgent:
  1. Generate code (LLM)
  2. Call write_file("app.py", code)
  3. Optionally: run_shell("python app.py") - test
  4. Return result
        ↓
TaskDispatcher proceeds to next step
```

### Collaboration with Other Agents

- **ArchitectAgent** - Receives instructions from execution plan
- **CriticAgent** - Verifies generated code quality
- **LibrarianAgent** - Checks existing files before overwriting
- **ResearcherAgent** - Provides documentation and examples

## Configuration

```bash
# In .env
WORKSPACE_ROOT=./workspace          # Working directory for files
ENABLE_SANDBOX=true                 # Whether to run code in sandbox
DOCKER_IMAGE_NAME=python:3.11-slim  # Image for Docker sandbox
```

## Docker Compose Stack - Best Practices

### docker-compose.yml Structure

```yaml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - postgres
    networks:
      - app-network

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    networks:
      - app-network

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_PASSWORD: dev_password
    ports:
      - "5432:5432"
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

### Communication Between Containers

```python
# In application code use Docker service names (not localhost!)
redis_client = redis.Redis(host='redis', port=6379)  # ✅ Correct
redis_client = redis.Redis(host='localhost', port=6379)  # ❌ Won't work in container

# PostgreSQL connection
db_url = "postgresql://user:pass@postgres:5432/dbname"  # ✅ Correct
db_url = "postgresql://user:pass@localhost:5432/dbname"  # ❌ Won't work
```

## Metrics and Monitoring

**Key indicators:**
- Number of generated files (per session)
- Average generated code size (lines)
- Compilation/runtime error rate
- Number of self-repair iterations (average)
- Usage of different skills (File/Shell/Compose)

## Best Practices

1. **Physically write files** - Always use `write_file()`, not just markdown
2. **Test before writing** - Optionally run code and check errors
3. **Stack before code** - First `create_environment()`, then application code
4. **Network names** - In Docker Compose use service names (not localhost)
5. **Clean-up** - Use `destroy_environment()` when stack is no longer needed

## Known Limitations

- Self-repair has 3 iteration limit
- Docker sandbox has limited file system access
- No support for languages requiring compilation (C++, Rust) - scripts only
- Docker Compose stacks are standalone (no Kubernetes orchestration)

## See also

- [THE_ARCHITECT.md](THE_ARCHITECT.md) - Project planning
- [THE_CRITIC.md](THE_CRITIC.md) - Code quality verification
- [THE_LIBRARIAN.md](THE_LIBRARIAN.md) - File management
- [BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md) - Backend architecture
