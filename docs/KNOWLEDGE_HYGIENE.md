# Knowledge Hygiene Suite - Documentation

## Overview

Knowledge Hygiene Suite is a set of tools that prevents contaminating the RAG system with "anti‑knowledge" during tests and debugging. It consists of two main components:

1. **Lab Mode (Memory Freeze)** - ephemeral mode for test tasks
2. **Knowledge Pruning API** - tools to clean stored knowledge

## Lab Mode

### Description

Lab Mode lets you run tasks without permanently writing lessons to `LessonsStore`. It is essential for:
- testing new features
- debugging issues
- experimenting with prompts
- system stabilization

### UI Usage

1. Open Venom Cockpit
2. Check **🧪 Lab Mode** next to the input
3. Submit the task
4. The system executes normally, but does NOT save lessons

### API Usage

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/tasks",
    json={
        "content": "Test task",
        "store_knowledge": False  # Lab Mode enabled
    }
)
```

### Implementation

```python
# venom_core/core/models.py
class TaskRequest(BaseModel):
    content: str
    store_knowledge: bool = True  # Saves knowledge by default
```

## Knowledge Pruning API

### Endpoints

#### 1. Delete N latest lessons

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/latest?count=5"
```

**Parameters:**
- `count` (required): Number of newest lessons to delete

**Sample response:**
```json
{
  "status": "success",
  "message": "Deleted 5 latest lessons",
  "deleted": 5
}
```

#### 2. Delete lessons by time range

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/range?start=2024-01-01T00:00:00&end=2024-01-31T23:59:59"
```

**Parameters:**
- `start` (required): Start date in ISO 8601
- `end` (required): End date in ISO 8601

**Supported date formats:**
- `2024-01-01T00:00:00`
- `2024-01-01T00:00:00Z`
- `2024-01-01T00:00:00+00:00`

**Sample response:**
```json
{
  "status": "success",
  "message": "Deleted 12 lessons in range 2024-01-01T00:00:00 - 2024-01-31T23:59:59",
  "deleted": 12,
  "start": "2024-01-01T00:00:00",
  "end": "2024-01-31T23:59:59"
}
```

#### 3. Delete lessons by tag

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/tag?tag=error"
```

**Parameters:**
- `tag` (required): Tag to search for

**Sample response:**
```json
{
  "status": "success",
  "message": "Deleted 8 lessons with tag 'error'",
  "deleted": 8,
  "tag": "error"
}
```

#### 4. Purge all lessons (NUCLEAR)

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/purge?force=true"
```

**Parameters:**
- `force` (required): Must be `true` to confirm

**⚠️ WARNING:** This operation is irreversible!

**Sample response:**
```json
{
  "status": "success",
  "message": "💣 Purged all lessons (47 lessons)",
  "deleted": 47
}
```

#### 5. TTL - delete lessons older than N days

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/ttl?days=30"
```

**Parameters:**
- `days` (required): Retention days

**Sample response:**
```json
{
  "status": "success",
  "message": "Deleted 12 lessons older than 30 days",
  "deleted": 12,
  "days": 30
}
```

#### 6. Lesson deduplication

```bash
curl -X POST "http://localhost:8000/api/v1/memory/lessons/dedupe"
```

**Sample response:**
```json
{
  "status": "success",
  "message": "Removed 4 duplicate lessons",
  "removed": 4
}
```

#### 7. Global learning switch

```bash
curl "http://localhost:8000/api/v1/memory/lessons/learning/status"
curl -X POST "http://localhost:8000/api/v1/memory/lessons/learning/toggle" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Sample response:**
```json
{
  "status": "success",
  "enabled": false
}
```

## Usage Examples

### Scenario 1: Cleanup after a test session

After a test session, remove all lessons from that window:

```python
from datetime import datetime, timedelta
import requests

# Test session took 2 hours
end_time = datetime.now()
start_time = end_time - timedelta(hours=2)

response = requests.delete(
    "http://localhost:8000/api/v1/memory/lessons/prune/range",
    params={
        "start": start_time.isoformat(),
        "end": end_time.isoformat()
    }
)
print(f"Deleted {response.json()['deleted']} test lessons")
```

### Scenario 2: Remove erroneous lessons

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/tag?tag=error"
```

### Scenario 3: Reset before a new release

```bash
# WARNING: This removes EVERYTHING!
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/purge?force=true"
```

## Security

### Thread Safety

All pruning operations are thread-safe:
```python
# We iterate over a copy of keys
for lesson_id in list(self.lessons.keys()):
    # Safe iteration
```

### Data Validation

- Dates are validated before parsing
- Invalid formats return HTTP 400 with error details
- Empty strings are rejected

### Persistence

All operations automatically persist to disk when `auto_save=True`.

## Testing

### Unit Tests

```bash
# From project root
python -m pytest tests/test_knowledge_hygiene.py -v
```

### Manual Testing

1. **Test Lab Mode:**
   - Enable Lab Mode in UI
   - Submit a test task
   - Check `data/memory/lessons.json` - no new entry should appear

2. **Test Pruning:**
   ```bash
   # Add test lessons
   # Then delete them
   curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/latest?count=1"
   ```

## Troubleshooting

### Problem: Lessons still saved in Lab Mode

**Solution:**
- Ensure checkbox is enabled
- Check console.log for `store_knowledge=false`
- Ensure `ENABLE_META_LEARNING` is `True` in config

### Problem: Date parsing error

**Solution:**
- Use ISO 8601: `YYYY-MM-DDTHH:MM:SS`
- `Z` suffix (UTC) is supported

### Problem: Cannot delete lessons

**Solution:**
- Ensure LessonsStore is initialized
- Check logs: `tail -f logs/venom.log`
- Check file permissions for `data/memory/lessons.json`

## Best Practices

1. **Always use Lab Mode when testing new features**
2. **Regularly review and clean bad lessons**
3. **Create a backup before purge:**
   ```bash
   cp data/memory/lessons.json data/memory/lessons.json.backup
   ```
4. **Use tags to categorize lessons**
5. **Document test sessions with time ranges**

## API Reference

### LessonsStore Methods

```python
class LessonsStore:
    def delete_last_n(self, n: int) -> int:
        """Deletes the N newest lessons."""

    def delete_by_time_range(self, start: datetime, end: datetime) -> int:
        """Deletes lessons in a time range."""

    def delete_by_tag(self, tag: str) -> int:
        """Deletes lessons with a given tag."""

    def clear_all(self) -> bool:
        """Clears the entire lessons database."""
```

## Changelog

### v1.0.0 (2025-12-10)
- ✨ Added Lab Mode (Memory Freeze)
- ✨ Added Knowledge Pruning API
- ✨ Added Lab Mode checkbox in UI
- 🐛 Fixed ISO 8601 parsing with 'Z' suffix
- 🔧 Extracted `_should_store_lesson()`
- ✅ Added unit tests

## See also

- [AGENTS_INDEX.md](./AGENTS_INDEX.md) - Main documentation index
- [THE_ACADEMY.md](./THE_ACADEMY.md) - Academy documentation
- [MEMORY_LAYER_GUIDE.md](./MEMORY_LAYER_GUIDE.md) - Memory layer guide
