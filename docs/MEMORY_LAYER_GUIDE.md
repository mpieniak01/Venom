# Guide: Memory Layer and Meta-Learning

## Overview

Venom v1.0 has been extended with an advanced memory layer that transforms the system from simple “text search” into an intelligent “relationship network” with the ability to learn from mistakes.

## Components

### 1. CodeGraphStore - Code Knowledge Graph

**Location:** `venom_core/memory/graph_store.py`

The knowledge graph analyzes project code structure using AST (Abstract Syntax Tree) and builds a dependency graph between files, classes, and functions.

#### Key capabilities:

- **Workspace scanning:** Automatic scan of all Python files
- **Node extraction:** Files, classes, functions, methods
- **Edge extraction:** IMPORTS, INHERITS_FROM, CALLS, CONTAINS
- **Dependency analysis:** Detect files depending on a given file
- **Impact Analysis:** Estimate impact of removing/modifying a file

#### Example usage:

```python
from venom_core.memory.graph_store import CodeGraphStore

# Init
graph_store = CodeGraphStore()

# Scan workspace
stats = graph_store.scan_workspace()
print(f"Found {stats['nodes']} nodes, {stats['edges']} edges")

# Impact analysis
impact = graph_store.get_impact_analysis("venom_core/core/orchestrator.py")
print(f"Removing this file affects {impact['impact_score']} files")

# File info
info = graph_store.get_file_info("venom_core/agents/coder.py")
print(f"Classes: {len(info['classes'])}, Functions: {len(info['functions'])}")

# Save/load graph
graph_store.save_graph()
graph_store.load_graph()
```

#### API Endpoints:

- `GET /api/v1/graph/summary` - Graph summary (node/edge counts, types)
- `GET /api/v1/graph/file/{path}` - File info from graph
- `GET /api/v1/graph/impact/{path}` - Impact analysis for file removal
- `POST /api/v1/graph/scan` - Trigger manual scan

#### Response contract `/api/v1/graph/summary` (standardization)
Endpoint returns standardized `summary` (snake_case) plus root fields for backward compatibility:

```json
{
  "status": "success",
  "summary": {
    "nodes": 123,
    "edges": 456,
    "last_updated": "2026-01-30T12:34:56+00:00",
    "total_nodes": 123,
    "total_edges": 456
  },
  "nodes": 123,
  "edges": 456,
  "lastUpdated": "2026-01-30T12:34:56+00:00"
}
```

Recommendation: new code should use fields from `summary`, and treat `nodes/edges/lastUpdated` as legacy.

### 2. LessonsStore - Lessons Repository

**Location:** `venom_core/memory/lessons_store.py`

LessonsStore stores Venom’s experiences - both successes and failures. Each lesson contains:

- **Situation:** Description of the situation/task
- **Action:** What was done
- **Result:** Outcome (success/error)
- **Feedback:** Conclusions and what to improve
- **Tags:** Categorization tags
- **Metadata:** Additional info (timestamp, task_id, etc.)

#### Example usage:

```python
from venom_core.memory.lessons_store import LessonsStore

# Init (with optional vector_store for semantic search)
lessons_store = LessonsStore(vector_store=vector_store)

# Add a lesson
lesson = lessons_store.add_lesson(
    situation="Tried using requests library",
    action="Generated code with requests.post()",
    result="ERROR: SSL Certificate verification failed",
    feedback="Next time add verify=False or use SSL context",
    tags=["requests", "ssl", "error"]
)

# Semantic search
lessons = lessons_store.search_lessons(
    query="SSL certificate problems",
    limit=3
)

# Fetch by tags
error_lessons = lessons_store.get_lessons_by_tags(["error"])

# Stats
stats = lessons_store.get_statistics()
print(f"Total lessons: {stats['total_lessons']}")
print(f"Top tags: {stats['tag_distribution']}")
```

#### Storage
- Lessons stored in `data/memory/lessons_store.json`
- If `vector_store` is available, embeddings are stored in LanceDB

#### API Endpoints:
- `GET /api/v1/lessons` - list lessons
- `POST /api/v1/lessons` - add a lesson
- `POST /api/v1/lessons/search` - semantic search
- `GET /api/v1/lessons/tags/{tags}` - list by tags
- `GET /api/v1/lessons/stats` - statistics

### 3. VectorStore - Semantic Memory

**Location:** `venom_core/memory/vector_store.py`

VectorStore provides semantic search over:
- conversation fragments
- lesson feedback
- extracted facts

Uses LanceDB as local vector database.

#### Features:
- Automatic embedding generation
- Cosine similarity search
- Metadata filters (session_id, type, tags)

#### Example usage:

```python
from venom_core.memory.vector_store import VectorStore

vector_store = VectorStore()

# Add a record
vector_store.add_text(
    text="User asked about Docker Compose",
    metadata={"type": "conversation", "session_id": "abc"}
)

# Search
results = vector_store.search("compose stack", limit=5)
```

### 4. GardenerAgent - Gardener Agent

**Location:** `venom_core/agents/gardener.py`

The Gardener Agent runs in the background and automatically updates the knowledge graph when it detects changes in workspace files.

#### Functions:

- **File Monitoring:** Checking for changes in Python files.
- **Auto-reindexing:** Automatic graph update after changes.
- **Background Service:** Runs asynchronously without blocking the main thread.
- **Manual Scanning:** Ability to trigger scanning on demand.

#### Example usage:

```python
from venom_core.agents.gardener import GardenerAgent
from venom_core.memory.graph_store import CodeGraphStore

# Initialization
graph_store = CodeGraphStore()
gardener = GardenerAgent(
    graph_store=graph_store,
    scan_interval=300  # Scan every 5 minutes
)

# Start in the background
await gardener.start()

# Status
status = gardener.get_status()
print(f"Running: {status['is_running']}")
print(f"Last scan: {status['last_scan_time']}")

# Manual scan
stats = gardener.trigger_manual_scan()

# Stop
await gardener.stop()
```

#### API Endpoints:

- `GET /api/v1/gardener/status` - Gardener Agent status.

### 5. Semantic Cache (Hidden Prompts)

**Location:** `venom_core/core/hidden_prompts.py`

The Semantic Cache mechanism is used to optimize chat by remembering approved Question-Answer pairs and serving them for semantically similar queries without involving the LLM.

#### Operation:
1. **Exact Match:** First checks for an exact match in JSONL files.
2. **Semantic Match:** If there is no exact match, it searches the vector database (LanceDB).
3. **Threshold:** Accepts the result only when similarity (cosine similarity) exceeds `SEMANTIC_CACHE_THRESHOLD` (default 0.85).

#### Configuration (constants.py):
- `SEMANTIC_CACHE_THRESHOLD = 0.85`
- `SEMANTIC_CACHE_COLLECTION_NAME = "hidden_prompts"`

#### Integration:
The cache uses `VectorStore` (the same class as Memory/Lessons) and the embedding model `sentence-transformers/all-MiniLM-L6-v2`.

### 6. Orchestrator - Meta-Learning Loop

**Location:** `venom_core/core/orchestrator.py`

The Orchestrator has been extended with a meta-learning mechanism:

#### Pre-Flight Check:

Before starting a task, the Orchestrator:
1. Searches for relevant lessons from the past.
2. Attaches them to the task context as warnings.
3. The agent sees "I learned earlier..." in the prompt.

#### Post-Task Reflection:

After completing the task (success or failure), the Orchestrator:
1. Analyzes results and logs.
2. Creates a lesson from the experience.
3. Saves it in LessonsStore.
4. Indexes it for future searches.

#### Configuration:

```python
# In venom_core/core/orchestrator.py
ENABLE_META_LEARNING = True  # Enable/disable meta-learning
MAX_LESSONS_IN_CONTEXT = 3   # How many lessons to attach to the prompt
```

#### Example flow:

```
Task 1: "Write code using library X"
→ Venom generates code with an outdated method
→ ERROR: Method X.old_method() not found
→ Lesson saved: "Library X in version Y does not have the old_method() method"

---

Task 2 (New session): "Write code using library X"
→ Pre-flight check finds the lesson
→ Prompt contains: "📚 LESSONS: Watch out, the old_method() method does not exist in version Y"
→ Venom immediately generates correct code with the new method
→ SUCCESS ✅
```

## Dashboard - Visualization

### New "Memory" Tab

The Dashboard has been extended with a "🧠 Memory" tab with two sections:

#### 1. Lessons (📚)

- List of the last 10 lessons.
- Coloring: green = success, red = failure.
- Displays: situation, feedback, tags.
- Refresh button.

#### 2. Knowledge Graph (🕸️)

- Graph statistics:
  - Number of nodes.
  - Number of edges.
  - Files, classes, functions.
- "Scan" button for manual update.

### Access:

1. Run Venom: `uvicorn venom_core.main:app --reload`
2. Open browser: `http://localhost:8000`
3. Switch to the "🧠 Memory" tab.

## Tests

### Running tests:

```bash
# All memory tests
pytest tests/test_graph_store.py tests/test_lessons_store.py -v

# Only graph_store
pytest tests/test_graph_store.py -v

# Only lessons_store
pytest tests/test_lessons_store.py -v
```

### Test coverage:

- **CodeGraphStore:** 11 unit tests.
- **LessonsStore:** 16 unit tests.
- **Total:** 27 tests, 100% pass rate.

## License

This component is part of the Venom project and is covered by the same license as the parent project.
