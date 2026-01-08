# THE LIBRARIAN - File Management & Project Structure

## Role

Librarian Agent is the project librarian in the Venom system, specializing in file navigation, workspace structure management, and maintaining knowledge about project organization.

## Responsibilities

- **File navigation** - Listing, checking existence, reading files
- **Knowledge management** - Saving important information about structure to memory
- **Project audit** - Checking what already exists before starting work
- **Structure documentation** - Maintaining map of files and directories
- **Memory integration** - Saving and retrieving file information

## Key Components

### 1. Available Tools

**FileSkill** (`venom_core/execution/skills/file_skill.py`):
- `list_files(directory)` - List files and directories
- `file_exists(path)` - Check if file exists
- `read_file(path)` - Read file contents

**MemorySkill** (`venom_core/memory/memory_skill.py`):
- `memorize(content, tags)` - Save important information (e.g., structure, configuration)
- `recall(query)` - Retrieve information from memory

### 2. Operating Principles

**When to use tools:**
- ✅ Questions about files/structures in workspace: `list_files`, `read_file`
- ✅ Questions about documentation/configuration: `read_file` + optionally `memorize`
- ✅ Check if file exists: `file_exists`
- ❌ General questions (math, definitions): DON'T use tools, answer directly

**Workflow:**
1. User asks about structure → `list_files(".")`
2. User asks about specific file → `file_exists()` or `read_file()`
3. You read important file (config, docs) → consider `memorize()` for future queries
4. Before answering you can check memory: `recall()`

**Examples:**
```
User: "What files do I have?"
→ list_files(".") and show result

User: "Does test.py file exist?"
→ file_exists("test.py") and answer

User: "What's in config.json file?"
→ read_file("config.json"), show contents
→ Consider: memorize("Configuration: ...", tags=["config"])

User: "What is a triangle?"
→ Answer directly, DON'T use list_files
```

### 3. Memory Integration

Librarian saves important project information to long-term memory:

**What to save:**
- Directory structure (after `list_files` of main directory)
- Configuration file contents (`config.json`, `.env.example`)
- Important documentation files (`README.md`, `CONTRIBUTING.md`)
- Project dependencies (`requirements.txt`, `package.json`)

**Tags:**
- `["project-structure"]` - Directory structure
- `["config"]` - Configuration files
- `["documentation"]` - Documentation files
- `["dependencies"]` - Project dependencies

## System Integration

### Execution Flow

```
ArchitectAgent creates plan:
  Step 1: LIBRARIAN - "Check if app.py file exists"
        ↓
TaskDispatcher calls LibrarianAgent.execute()
        ↓
LibrarianAgent:
  1. file_exists("app.py")
  2. If exists: read_file("app.py") for details
  3. Returns result (yes/no + optionally contents)
        ↓
ArchitectAgent: If file exists, skip creation, proceed to editing
```

### Collaboration with Other Agents

- **ArchitectAgent** - Checking existing files before planning
- **CoderAgent** - Verifying file exists before overwriting
- **ChatAgent** - Answering user questions about project structure
- **MemorySkill** - Long-term memory about project structure

## Usage Examples

### Example 1: Project Structure Audit
```python
# User: "Show project structure"
# Librarian:
files = await list_files(".")
await memorize(f"Main structure: {files}", tags=["project-structure"])
# Returns: List of directories and files with description
```

### Example 2: Configuration Check
```python
# User: "What variables are in .env.example?"
# Librarian:
content = await read_file(".env.example")
await memorize(f"Env variables: {summary}", tags=["config"])
# Returns: List of environment variables with description
```

### Example 3: Before File Creation
```python
# ArchitectAgent: Plan - Step 1: LIBRARIAN - "Check if app.py exists"
# Librarian:
exists = await file_exists("app.py")
if exists:
    content = await read_file("app.py")
    return f"File exists. Contents: {content[:200]}..."
else:
    return "File doesn't exist. Can create."
```

## Configuration

```bash
# In .env
WORKSPACE_ROOT=./workspace  # Workspace directory (operation scope)
MEMORY_ROOT=./data/memory   # Long-term memory
```

**Security:**
- All operations limited to `WORKSPACE_ROOT`
- No access outside workspace (sandbox)
- Read-only - Librarian CANNOT write/delete files

## Metrics and Monitoring

**Key indicators:**
- Number of file reads (per session)
- Cache hit rate (% queries from memory)
- Most frequently read files (top 10)
- Number of memory saves (per session)

## Best Practices

1. **Memory for configuration** - Save `config.json`, `.env.example` to memory
2. **Project structure** - After first `list_files` save structure
3. **Verify before writing** - Always check `file_exists` before `write_file` (other agent)
4. **Don't overuse tools** - For general questions answer directly
5. **Consistent tags** - Use standardized tags for easier searching

## Known Limitations

- Read-only (no `write_file`, `delete_file`) - use CoderAgent for writing
- Scope limited to `WORKSPACE_ROOT` (no file system access)
- `list_files` can be slow for large directories (>1000 files)
- No support for binary files (text only)

## See also

- [THE_CODER.md](THE_CODER.md) - File creation and editing
- [THE_ARCHITECT.md](THE_ARCHITECT.md) - Planning with audit utilization
- [MEMORY_LAYER_GUIDE.md](MEMORY_LAYER_GUIDE.md) - Long-term memory
- [BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md) - Backend architecture
