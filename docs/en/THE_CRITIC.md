# THE CRITIC - Code Quality & Security Review

## Role

Critic Agent is an expert in code security and quality in the Venom system. It plays the role of Senior Developer/QA, detecting logical errors, security vulnerabilities, and code quality issues before final approval.

## Responsibilities

- **Code quality assessment** - Verification of readability, documentation, best practices compliance
- **Security audit** - Detection of hardcoded credentials, SQL injection, dangerous commands
- **Correctness verification** - Checking logical errors, typing, syntax
- **Error source diagnostics** - Identifying problems in imported modules
- **Fix suggestions** - Concrete guidelines on how to fix problematic code

## Key Components

### 1. Code Evaluation System

**3 types of responses:**

**1. APPROVED** - Code is secure and of good quality
```
Code contains no problems. APPROVED
```

**2. Problems in analyzed code** - List of errors in text form
```
Found problems:
1. Line 15: Hardcoded API key - Use environment variable
2. Line 23: No error handling - Add try/except
3. Line 45: No type hint for parameter 'data' - Add type hint
```

**3. Problems in imported file** - JSON with target_file_change
```json
{
  "analysis": "ImportError: module 'config' missing function 'get_setting'",
  "suggested_fix": "Add function get_setting(key) in config.py",
  "target_file_change": "venom_core/config.py"
}
```

### 2. Detected Problems

**Security:**
- ❌ Hardcoded API keys (`api_key = "sk-..."`)
- ❌ Passwords in code (`password = "secret123"`)
- ❌ SQL queries without parameterization
- ❌ Dangerous shell commands (`rm -rf`, `eval()`)
- ❌ No user input validation

**Quality:**
- ❌ No function typing
- ❌ No docstrings
- ❌ No error handling (try/except)
- ❌ Magic numbers without constants
- ❌ Too long functions (>50 lines)

**Import errors:**
- ❌ ImportError - missing function/class in module
- ❌ AttributeError - missing attribute in object
- ❌ ModuleNotFoundError - missing module

### 3. PolicyEngine Integration

Critic uses **PolicyEngine** to verify project policies:

```python
from venom_core.core.policy_engine import PolicyEngine

policy_engine = PolicyEngine()

# Check if operation is allowed
is_allowed = policy_engine.is_allowed(
    operation="write_file",
    path="/etc/passwd"
)
# → False (outside workspace)
```

**Policies:**
- Sandbox filesystem (workspace only)
- Blocking dangerous shell commands
- Resource limits (CPU, RAM)
- Network access blocking (optional)

## System Integration

### Execution Flow

```
CoderAgent generates code
        ↓
CriticAgent.execute(code)
        ↓
CriticAgent:
  1. Code analysis (LLM with temperature=0.3)
  2. Security problem detection
  3. Quality and documentation check
  4. PolicyEngine.validate()
        ↓
Returns: "APPROVED" or list of problems
        ↓
If APPROVED → Code accepted
If problems → CoderAgent fixes (self-repair)
```

### Collaboration with Other Agents

- **CoderAgent** - Main client (generate → review → fix loop)
- **ArchitectAgent** - Plan verification for feasibility
- **PolicyEngine** - Enforcing security policies
- **ToolmakerAgent** - Review of generated tools

## Usage Examples

### Example 1: Code with Hardcoded Credentials
```python
# Code to review:
api_key = "sk-1234567890abcdef"
response = requests.get("https://api.example.com", headers={"Authorization": api_key})

# CriticAgent response:
"""
Found problems:
1. Line 1: Hardcoded API key 'sk-1234567890abcdef'
   Suggestion: Use environment variable
   ```python
   api_key = os.environ.get("API_KEY")
   if not api_key:
       raise ValueError("API_KEY not set")
   ```
"""
```

### Example 2: No Error Handling
```python
# Code to review:
def read_config():
    with open("config.json") as f:
        return json.load(f)

# CriticAgent response:
"""
Found problems:
1. Function 'read_config': No error handling (FileNotFoundError, JSONDecodeError)
   Suggestion: Add try/except with graceful degradation
   ```python
   def read_config():
       try:
           with open("config.json") as f:
               return json.load(f)
       except (FileNotFoundError, JSONDecodeError) as e:
           logger.error(f"Config read error: {e}")
           return {}  # Return default configuration
   ```
"""
```

### Example 3: Import Error (other file)
```python
# Code to review:
from config import get_database_url  # ImportError: missing function

# CriticAgent response (JSON):
{
  "analysis": "ImportError on line 1: module 'config' doesn't have function 'get_database_url'. Problem in file venom_core/config.py",
  "suggested_fix": "Add function get_database_url() in venom_core/config.py:\n\ndef get_database_url() -> str:\n    return os.environ.get('DATABASE_URL', 'sqlite:///default.db')",
  "target_file_change": "venom_core/config.py"
}
```

## Configuration

```bash
# In .env (no dedicated flags for Critic)
# Temperature for LLM set in code (0.3 for consistency of assessments)

# PolicyEngine settings
ENABLE_SANDBOX=true
WORKSPACE_ROOT=./workspace
```

## Metrics and Monitoring

**Key indicators:**
- Number of reviews per session
- APPROVED vs. rejected rate (% approved)
- Most common problem types (security, quality, imports)
- Average number of fix → review iterations (self-repair)
- Review time (typically <5s)

## Best Practices

1. **Always review before commit** - Every generated code through CriticAgent
2. **Fix iteratively** - Max 3 self-repair iterations, then escalation
3. **Log rejected** - Save problems to Work Ledger
4. **PolicyEngine ON** - Always verify policy compliance
5. **Low temperature** - 0.3 for consistency of assessments (not creativity)

## Known Limitations

- Static analysis (no code execution) - may miss runtime bugs
- LLM can give false positives (too rigorous assessments)
- No integration with external linters (ruff, mypy) - LLM only
- Max 3 self-repair iterations (then manual intervention)

## See also

- [THE_CODER.md](THE_CODER.md) - Code generation
- [BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md) - Backend architecture
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution rules (pre-commit hooks)
