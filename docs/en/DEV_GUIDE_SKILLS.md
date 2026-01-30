# Skills Development Guide in Venom

This document describes the standards for creating new Skills in the Venom system. Thanks to the `BaseSkill` class, the process is simplified and secure.

## 1. Quick Start

To create a new skill, create a new file in `venom_core/execution/skills/` (e.g., `my_custom_skill.py`) and inherit from `BaseSkill`.

```python
from typing import Annotated
from semantic_kernel.functions import kernel_function
from venom_core.execution.skills.base_skill import BaseSkill, async_safe_action

class MyCustomSkill(BaseSkill):
    """
    Short description of what this skill does.
    """

    @kernel_function(
        name="do_something",
        description="Function description visible to LLM.",
    )
    @async_safe_action
    async def do_something(
        self,
        param_name: Annotated[str, "Parameter description for LLM"],
    ) -> str:
        """
        Function docstring.
        """
        # Your logic
        result = perform_logic(param_name)

        # Logging (you have access to self.logger)
        self.logger.info(f"Action performed: {result}")

        return f"✅ Success: {result}"
```

## 2. Key Components

### `BaseSkill` Class
Provides:
- **Logger (`self.logger`)**: Automatically configured logger.
- **Workspace (`self.workspace_root`)**: Safe path to the working directory.
- **Helper methods**: e.g., `validate_path(path)` for file safety.

### Decorators
Use `safe_action` (for synchronous methods) or `async_safe_action` (for asynchronous ones) to:
- Automatically catch exceptions.
- Log errors.
- Return a formatted error message ("❌ ...") instead of crashing the agent.

**Example:**
```python
@async_safe_action
async def risky_method(self):
    raise ValueError("Oops!")
    # Returns: "❌ Error occurred: Oops!"
```

### Typing
Use `Annotated[Type, "Description"]` for all `@kernel_function` arguments. These descriptions are crucial for the LLM to understand how to use the tool.

## 3. Security

If your skill operates on files, **ALWAYS** use `self.validate_path(path)`.
This method ensures the path does not escape the allowed `workspace_root` (prevents Path Traversal).

```python
def read(self, path: str):
    safe_path = self.validate_path(path)
    # Now safe_path is safe to use
    with open(safe_path, 'r') as f: ...
```

## 4. Testing

Every new skill must have unit tests in `tests/`.
- Test success ("✅").
- Test errors (expect return string with error "❌", not exception raising).
- Use `pytest.mark.asyncio` for asynchronous methods.

***

## 5. MCP Tools Import (Model Context Protocol)

Venom supports the **MCP (Model Context Protocol)** standard, allowing you to import tools directly from Git repositories without writing your own wrapper.

### How it works?
1.  **Agents use the `McpManagerSkill`**.
2.  System clones the repository to `venom_core/skills/mcp/_repos`.
3.  An isolated `venv` environment is created for the tool.
4.  Generator creates a `.py` file in `custom/` that acts as a "Proxy" to the MCP server.

### Usage Example (by Agent)
```python
# Agent requests tool download
await mcp_manager.import_mcp_tool_from_git(
    repo_url="https://github.com/modelcontextprotocol/servers",
    tool_name="sqlite",
    server_entrypoint="python src/sqlite/server.py" # Relative path in repo
)
```

After this operation, a new skill (e.g., `SqliteMcpSkill`) appears in the system, exposing MCP server functions (e.g., `query`, `list_tables`) as native `@kernel_function`.

### MCP Structure in Venom
*   `venom_core/skills/mcp/` - Manager and generator logic.
*   `venom_core/skills/mcp/_repos/` - Cloned repositories (do not edit manually).
*   `venom_core/skills/custom/mcp_*.py` - Generated wrappers (can be viewed, do not edit).
