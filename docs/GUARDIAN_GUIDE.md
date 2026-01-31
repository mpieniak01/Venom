# THE_GUARDIAN - Autonomous Testing & Self-Healing Pipeline

## Overview

THE_GUARDIAN is an automated testing and self-healing system implemented in Venom. It runs a "Test-Diagnose-Fix" loop that can autonomously detect and repair errors in code.

## Components

### 1. TestSkill (`venom_core/execution/skills/test_skill.py`)

A skill responsible for running tests and the linter inside an isolated Docker environment.

**Functions:**
- `run_pytest(test_path, timeout)` - Runs pytest in a container
- `run_linter(path, timeout)` - Runs a linter (ruff or flake8)

**Example usage:**
```python
from venom_core.execution.skills.test_skill import TestSkill
from venom_core.infrastructure.docker_habitat import DockerHabitat

habitat = DockerHabitat()
test_skill = TestSkill(habitat=habitat)

# Run tests
result = await test_skill.run_pytest(test_path="tests/")
print(result)
```

**Test report:**
```
✅ TESTS PASSED

Passed: 5
Failed: 0
```

or

```
❌ TESTS FAILED

Exit Code: 1
Passed: 2
Failed: 1

ERRORS:
1. FAILED tests/test_example.py::test_divide - AssertionError
```

### 2. GuardianAgent (`venom_core/agents/guardian.py`)

QA agent responsible for analyzing test results and creating fix tickets.

**Role:**
- DOES NOT write new code
- Analyzes test output and traceback
- Diagnoses root causes
- Creates precise fix tickets for the CoderAgent

**Example usage:**
```python
from venom_core.agents.guardian import GuardianAgent

guardian = GuardianAgent(kernel=kernel, test_skill=test_skill)

# Analyze test results
result = await guardian.process("Run tests and analyze results")

# Or create a fix ticket directly
ticket = await guardian.analyze_test_failure(
    test_output="FAILED test.py - AssertionError: Expected 10, got 0"
)
```

**Fix ticket format:**
```
FILE: src/calculator.py
LINE: 15
ERROR: AssertionError: Expected 10, got 0
CAUSE: divide() returns 0 instead of division result
ACTION: Fix division logic - return a/b instead of 0
```

### 3. Healing Cycle (Self-Healing Loop)

Implemented in `Orchestrator.execute_healing_cycle()`.

**Algorithm:**

```
Iteration 1-3:
    ┌─────────────────────┐
    │ PHASE 1: CHECK      │
    │ Guardian runs tests │
    │ in Docker           │
    └──────┬──────────────┘
           │
           ├─ exit_code == 0? ──> ✅ SUCCESS (done)
           │
           └─ exit_code != 0
                    │
           ┌────────▼─────────────┐
           │ PHASE 2: DIAGNOSE    │
           │ Guardian analyzes    │
           │ error and ticket     │
           └────────┬─────────────┘
                    │
           ┌────────▼─────────────┐
           │ PHASE 3: FIX         │
           │ Coder generates      │
           │ patch                │
           └────────┬─────────────┘
                    │
           ┌────────▼─────────────┐
           │ PHASE 4: APPLY       │
           │ Code is saved        │
           └────────┬─────────────┘
                    │
                    └─> Back to PHASE 1

After 3 iterations: ⚠️ FAIL FAST - manual intervention required
```

**Example usage:**
```python
from venom_core.core.orchestrator import Orchestrator

orchestrator = Orchestrator(state_manager, ...)

# Run healing loop for a task
result = await orchestrator.execute_healing_cycle(
    task_id=task_id,
    test_path="tests/"
)

if result["success"]:
    print(f"✅ Tests passed after {result['iterations']} iterations")
else:
    print(f"⚠️ {result['message']}")
```

## Dashboard Integration

The system emits WebSocket events to the dashboard in real time.

### New event types:

- `HEALING_STARTED` - Start of self-healing loop
- `TEST_RUNNING` - Tests running (with iteration number)
- `TEST_RESULT` - Test result (success/failure)
- `HEALING_FAILED` - Failure after 3 iterations
- `HEALING_ERROR` - Error during the process

### UI visualization:

Dashboard shows:
- 🟢 Green bar for passing tests
- 🔴 Red bar for failing tests
- Iteration counter
- Toast notifications with progress
- Real-time logs

## Configuration

### Environment requirements:

1. **Docker** - required to run DockerHabitat
2. **Python 3.11+**
3. **Dependencies in container:**
   - pytest
   - ruff or flake8

### Settings:

```python
# Maximum healing iterations
MAX_HEALING_ITERATIONS = 3

# Test timeout (seconds)
TEST_TIMEOUT = 60

# Dependency install timeout
INSTALL_TIMEOUT = 120
```

## Example usage scenario

### 1. User requests a buggy function:

```
User: "Write a divide(a, b) function that divides two numbers"
```

### 2. CoderAgent generates buggy code:

```python
def divide(a, b):
    return 0  # Bug: always returns 0
```

### 3. Guardian runs tests:

```
❌ TESTS FAILED
FAILED test_calculator.py::test_divide - AssertionError: Expected 5, got 0
```

### 4. Guardian diagnoses:

```
FILE: calculator.py
LINE: 2
CAUSE: Function always returns 0 instead of division result
ACTION: Replace return 0 with return a / b
```

### 5. Coder fixes:

```python
def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```

### 6. Guardian reruns tests:

```
✅ TESTS PASSED
Passed: 3
Failed: 0
```

### 7. System reports success:

```
✅ Code fixed automatically in 2 iterations
```

## Security

### Isolation:
- All tests run ONLY in Docker containers
- Host does not need pytest installed
- Process and filesystem isolation

### Timeouts:
- Protection against hanging tests (60s)
- Protection against hanging installs (120s)

### Fail Fast:
- Max 3 healing iterations
- After limit - manual intervention required
- Prevents infinite loops

## Metrics and monitoring

System metrics:
- Number of healing loop runs
- Average iterations to success
- Auto-fix rate (%)
- Duration per iteration

Available via:
- Dashboard (Live Feed)
- WebSocket events
- System logs

## Development

### Planned improvements:

1. **Intelligent caching:**
   - Remember similar errors
   - Faster diagnosis for known issues

2. **Coverage analysis:**
   - Check test coverage
   - Suggest new tests

3. **CI/CD integration:**
   - Auto-run before commit
   - Block merge when tests fail

4. **Extended diagnostics:**
   - Performance analysis
   - Memory leak detection
   - Security analysis

## Troubleshooting

### Problem: "Docker is not available"
**Solution:** Ensure Docker daemon is running: `docker ps`

### Problem: "Tests hang"
**Solution:** Increase timeout in `execute_healing_cycle` or verify tests are not waiting for input

### Problem: "Failed to heal after 3 iterations"
**Solution:** Normal for complex issues. Check Live Feed logs and fix manually.

### Problem: "Linter does not work"
**Solution:** Ensure ruff or flake8 is installed in the Docker container

## License

This component is part of the Venom project and is covered by the same license as the parent project.
