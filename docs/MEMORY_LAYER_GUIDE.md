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

### 4. Memory Integration in Orchestrator

Memory is used in two ways:

1. **Session memory** - short-term context (SessionStore)
2. **Global memory** - long-term semantic memory (VectorStore + LessonsStore)

Orchestrator builds context using:
- recent session history
- optional summary
- conditional retrieval from vector memory

### 5. SessionStore - Source of Truth

**Location:** `venom_core/services/session_store.py`

SessionStore keeps the entire history for a given `session_id`.

- Stored in `data/memory/session_store.json`
- Used for conversation continuity
- Cleared on backend restart (current behavior)

## Memory Flow

```
User prompt
   ↓
SessionStore (history)
   ↓
VectorStore / LessonsStore (conditional)
   ↓
Orchestrator builds context
   ↓
LLM generates response
```

## Meta-Learning

Meta-learning uses LessonsStore to improve future behavior:

- Records failures and resolutions
- Suggests better strategies
- Builds an internal knowledge loop

### Example lesson entry

```json
{
  "situation": "User asked for SSH key setup",
  "action": "Provided generic steps",
  "result": "User still had issues",
  "feedback": "Include key permissions and ssh-add",
  "tags": ["ssh", "permissions"]
}
```

## API Quick Reference

- `GET /api/v1/graph/summary`
- `POST /api/v1/graph/scan`
- `GET /api/v1/lessons`
- `POST /api/v1/lessons`
- `POST /api/v1/lessons/search`
- `GET /api/v1/lessons/stats`

## Operational Notes

- Memory features require `data/memory/` to be writable
- VectorStore uses local disk (LanceDB) - no cloud dependency
- If VectorStore is disabled, LessonsStore still works (without embeddings)

## Future Roadmap

- Auto-summary for long sessions
- Session-only memory mode
- TTL policies for lessons
- User-facing memory controls

## Troubleshooting

**Problem:** No lessons are saved
- Check `data/memory/lessons_store.json` permissions
- Ensure LessonsStore is initialized in `main.py`

**Problem:** Vector search returns empty results
- Ensure embeddings are generated (VectorStore init)
- Verify LanceDB files exist in `data/memory/`

**Problem:** Session history missing
- Check `session_store.json`
- Confirm session_id handling in UI

## License

This component is part of the Venom project and is covered by the same license as the parent project.
