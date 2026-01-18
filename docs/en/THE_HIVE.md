# THE HIVE - Distributed Processing Architecture

> [!NOTE]
> **Hive Definition in v1.0:** This document describes the **Internal Hive**, a local cluster of Spore nodes.
> The concept of **Global Hive**, where Venom acts as a single IoT device connected to a cloud registry, is planned for **Venom 2.0**.

## Overview

THE HIVE is a distributed processing architecture that transforms loosely connected Spore nodes into one synchronized compute cluster. The system enables parallel task execution, dynamic load distribution, and code synchronization across nodes.

## Architecture

```
┌─────────────┐
│   NEXUS     │ ◄─── Master Node
│  (Master)   │
└──────┬──────┘
       │
       │ Redis Pub/Sub + Task Queue
       │
       ├────────────┬────────────┬────────────┐
       ▼            ▼            ▼            ▼
   ┌──────┐    ┌──────┐    ┌──────┐    ┌──────┐
   │Spore1│    │Spore2│    │Spore3│    │SporeN│
   │Worker│    │Worker│    │Worker│    │Worker│
   └──────┘    └──────┘    └──────┘    └──────┘
```

## Main Components

### 1. Message Broker (`venom_core/infrastructure/message_broker.py`)

**Role:** Task queuing infrastructure based on Redis + ARQ.

**Functionality:**
- Task queue management (high_priority, background)
- Redis Pub/Sub for broadcast control
- Task status monitoring
- Zombie task detection
- Retry mechanism for failed tasks

**Queues:**
- `venom:tasks:high` - High priority tasks (user interactions)
- `venom:tasks:background` - Background tasks (scraping, training)
- `venom:broadcast` - Broadcast channel (system commands)

**Usage Example:**
```python
from venom_core.infrastructure.message_broker import MessageBroker

# Initialization
broker = MessageBroker()
await broker.connect()

# Add task to queue
task_id = await broker.enqueue_task(
    task_type="web_scraping",
    payload={"url": "https://example.com"},
    priority="background"
)

# Check status
status = await broker.get_task_status(task_id)
print(f"Status: {status.status}")

# Broadcast to all nodes
await broker.broadcast_control("UPDATE_SYSTEM", {"version": "1.2.0"})
```

### 2. Foreman Agent (`venom_core/agents/foreman.py`)

**Role:** Load Balancer & Watchdog for the cluster.

**Functionality:**
- Node load monitoring (CPU, RAM, task count)
- Intelligent task routing to best nodes
- Watchdog - zombie task detection
- Automatic retry for failed tasks
- Cluster status management

**Load Balancing Algorithm:**
```python
load_score = cpu_usage * 0.4 + memory_usage * 0.3 + (active_tasks/10) * 0.3
```
Node with lowest `load_score` is selected for new tasks.

**Usage Example:**
```python
from venom_core.agents.foreman import ForemanAgent

# Initialization
foreman = ForemanAgent(kernel, message_broker, node_manager)
await foreman.start()

# Select best node
node_id = foreman.select_best_node(task_requirements={"gpu": True})

# Assign task
await foreman.assign_task("task_123", task_requirements={"gpu": True})

# Cluster status
status = foreman.get_cluster_status()
print(f"Nodes online: {status['online_nodes']}/{status['total_nodes']}")
print(f"Average CPU load: {status['avg_cpu_usage']}%")
```

### 3. Parallel Skill (`venom_core/execution/skills/parallel_skill.py`)

**Role:** Parallel processing skill for Architect (Map-Reduce).

**Functionality:**
- `map_reduce()` - Process lists of items in parallel
- `parallel_execute()` - Parallel execution of sub-tasks
- `get_task_status()` - Check task progress

**Map-Reduce Flow:**
1. **MAP** - Split task into N sub-tasks
2. **DISTRIBUTE** - Add to Redis queue
3. **WAIT** - Asynchronously wait for results
4. **REDUCE** - Aggregate results

**Usage Example:**
```python
from venom_core.execution.skills.parallel_skill import ParallelSkill

skill = ParallelSkill(message_broker)

# Map-Reduce on list of URLs
urls = ["https://site1.com", "https://site2.com", "https://site3.com"]
result = await skill.map_reduce(
    task_description="Fetch article content and summarize to 3 sentences",
    items=json.dumps(urls),
    priority="high_priority",
    wait_timeout=300
)

# Result contains summary + results
data = json.loads(result)
print(f"Completed: {data['summary']['completed']}/{data['summary']['total_tasks']}")
```

### 4. OTA Manager (`venom_core/core/ota_manager.py`)

**Role:** Over-The-Air Updates for Spore nodes.

**Functionality:**
- Create update packages (ZIP)
- Checksum verification (SHA256)
- Broadcast UPDATE_SYSTEM to nodes
- Safe installation on nodes
- Automatic dependency installation
- Backup files before overwriting

**Update Process:**
1. Nexus creates package with new code
2. Nexus sends UPDATE_SYSTEM broadcast
3. Spores download package
4. Checksum verification
5. Unpack and copy files
6. Install dependencies (`pip install`)
7. Process restart

**Usage Example (Nexus):**
```python
from venom_core.core.ota_manager import OTAManager

ota = OTAManager(message_broker)

# Create package
package = await ota.create_package(
    version="1.2.0",
    description="New Hive features",
    source_paths=[Path("venom_core"), Path("venom_spore")],
    include_dependencies=True
)

# Broadcast to nodes
await ota.broadcast_update(package, target_nodes=["spore-1", "spore-2"])
```

**Usage Example (Spore):**
```python
# SECURITY WARNING: In production, verify update source!
# Listen to broadcast
pubsub = await message_broker.subscribe_broadcast()

async for message in pubsub.listen():
    if message["type"] == "message":
        data = json.loads(message["data"])
        if data["command"] == "UPDATE_SYSTEM":
            # STEP 1: Verify package_url comes from trusted source
            # STEP 2: Optionally: verify digital signature of package
            # STEP 3: Apply update
            await ota.apply_update(
                package_url=data["data"]["package_url"],
                expected_checksum=data["data"]["checksum"],
                restart_after=True
            )
```

**⚠️ OTA SECURITY WARNING:**
The above example is simplified for demonstration. In production:
1. **Source authentication**: Verify updates only from trusted Nexus
2. **Digital signatures**: Sign OTA packages with Nexus private key, verify on Spores
3. **URL whitelist**: Limit package_url to trusted hosts only
4. **Authorization token**: Add NEXUS_SHARED_TOKEN to broadcast data
5. **Redis auth**: Always use REDIS_PASSWORD in production

## Configuration

### Docker Compose - Redis Stack (Production)

⚠️ **CRITICAL**: Default Redis configuration is NOT secure for production!

**Secured Configuration (RECOMMENDED):**

```yaml
version: '3.8'

services:
  redis:
    image: redis:alpine
    container_name: venom-hive-redis
    # DO NOT expose port to host in production!
    # ports:
    #   - "6379:6379"
    environment:
      # CRITICAL: Set strong password!
      REDIS_PASSWORD: ${REDIS_PASSWORD:-changeme}
    volumes:
      - redis_data:/data
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD:-changeme}
      --appendonly yes
      --bind 0.0.0.0
    restart: unless-stopped
    networks:
      - venom-internal  # Internal network only!

networks:
  venom-internal:
    driver: bridge
    internal: true  # No external access

volumes:
  redis_data:
```

**Minimal Configuration (Development/demo ONLY):**

```yaml
version: '3.8'

services:
  redis:
    image: redis:alpine
    container_name: venom-hive-redis
    ports:
      - "127.0.0.1:6379:6379"  # Bind to localhost only!
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    restart: unless-stopped

volumes:
  redis_data:
```

Stack deployment:
```python
from venom_core.infrastructure.stack_manager import StackManager

manager = StackManager()
success, msg = manager.deploy_default_hive_stack()
```

### Environment Variables (.env)

```bash
# THE_HIVE Configuration
ENABLE_HIVE=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Queues
HIVE_HIGH_PRIORITY_QUEUE=venom:tasks:high
HIVE_BACKGROUND_QUEUE=venom:tasks:background
HIVE_BROADCAST_CHANNEL=venom:broadcast

# Timeouts
HIVE_TASK_TIMEOUT=300
HIVE_MAX_RETRIES=3
HIVE_ZOMBIE_TASK_TIMEOUT=600
```

## Use Cases

### 1. Bulk Processing

**Problem:** Fetch and summarize 20 articles from different sites.

**Solution:**
```python
# Architect splits task
urls = ["url1", "url2", ..., "url20"]

# Uses Parallel Skill
result = await parallel_skill.map_reduce(
    task_description="Fetch article and summarize to 3 sentences",
    items=json.dumps(urls),
    priority="high_priority"
)

# 5 Spores work simultaneously (each processes 4 articles)
# Time: ~5x faster than sequential
```

### 2. Parallel Repository Scanning

**Problem:** Scan entire repository for security issues.

**Solution:**
```python
subtasks = [
    "Scan /src directory",
    "Scan /tests directory",
    "Scan /config directory",
    "Scan requirements.txt dependencies"
]

result = await parallel_skill.parallel_execute(
    task_description="Repository security audit",
    subtasks=json.dumps(subtasks),
    priority="high_priority"
)
```

### 3. Automatic Node Updates

**Problem:** Nexus received new code version (PR merge).

**Solution:**
```python
# 1. Create package
package = await ota.create_package(
    version="1.3.0",
    description="PR #45: New feature X",
    source_paths=[Path("venom_core")],
    include_dependencies=True
)

# 2. Broadcast
await ota.broadcast_update(package)

# 3. All Spores automatically:
#    - Download new code
#    - Verify checksum
#    - Install dependencies
#    - Restart
```

## Monitoring & Debugging

### Cluster Status

```python
# Foreman Status
status = foreman.get_cluster_status()
print(f"""
Nodes: {status['online_nodes']}/{status['total_nodes']} online
Average CPU: {status['avg_cpu_usage']}%
Average RAM: {status['avg_memory_usage']}%
Active tasks: {status['total_active_tasks']}
""")
```

### Queue Statistics

```python
stats = await message_broker.get_queue_stats()
print(f"""
High Priority Queue: {stats['high_priority_queue']}
Background Queue: {stats['background_queue']}
Pending: {stats['tasks_pending']}
Running: {stats['tasks_running']}
Completed: {stats['tasks_completed']}
Failed: {stats['tasks_failed']}
""")
```

### Zombie Tasks

```python
# Foreman automatically detects and retries
zombies = await message_broker.detect_zombie_tasks()
for zombie in zombies:
    print(f"Zombie task: {zombie.task_id}, elapsed: {datetime.now() - zombie.started_at}")
```

## Best Practices

### 1. Idempotency

Tasks should be idempotent (safe to execute multiple times):

```python
# ✅ GOOD - Idempotent
async def process_url(url: str):
    # Check if already processed
    if await cache.exists(url):
        return await cache.get(url)

    # Process
    result = await scrape(url)
    await cache.set(url, result)
    return result

# ❌ BAD - Not idempotent
async def increment_counter():
    counter = await db.get_counter()
    await db.set_counter(counter + 1)  # On retry will increment twice!
```

### 2. Error Handling

Always handle errors and return meaningful messages:

```python
try:
    result = await process_task(task_data)
    await message_broker.update_task_status(task_id, "completed", result=result)
except Exception as e:
    logger.error(f"Task failed: {e}")
    await message_broker.update_task_status(task_id, "failed", error=str(e))
```

### 3. Timeouts

Set reasonable timeouts for long-running tasks:

```python
# Scraping task (max 5 min)
await skill.map_reduce(
    task_description="Scrape articles",
    items=json.dumps(urls),
    wait_timeout=300  # 5 minutes
)

# ML inference task (max 10 min)
await skill.parallel_execute(
    task_description="Run model inference",
    subtasks=json.dumps(batches),
    wait_timeout=600  # 10 minutes
)
```

### 4. Prioritization

Use priorities consciously:

```python
# High priority - user interactions
await broker.enqueue_task("user_query", data, priority="high_priority")

# Background - batch tasks
await broker.enqueue_task("bulk_scraping", data, priority="background")
```

## Troubleshooting

### Problem: Redis connection failed

**Solution:**
```bash
# Check if Redis is running
docker ps | grep redis

# Start Redis stack
cd venom_core/infrastructure
docker compose up -d

# Or use StackManager
python -c "from venom_core.infrastructure.stack_manager import StackManager; StackManager().deploy_default_hive_stack()"
```

### Problem: Zombie tasks

**Solution:**
- Foreman automatically detects and retries
- Check node logs: `docker logs venom-spore-1`
- Increase timeout if tasks are intensive:
  ```bash
  HIVE_ZOMBIE_TASK_TIMEOUT=1200  # 20 minutes
  ```

### Problem: Node offline

**Solution:**
```python
# Check node status
status = foreman.get_cluster_status()
for node in status['nodes']:
    if not node['is_online']:
        print(f"Node {node['node_name']} offline!")
        # Restart node
```

## Integration Examples

### Integration with Architect Agent

```python
# In Architect's prompt you can use:
"""
If task requires processing many items in parallel,
use ParallelSkill.map_reduce():

EXAMPLE:
Task: "Fetch 50 articles and extract key information"
Plan:
1. RESEARCHER - Find 50 article URLs
2. CODER - Use ParallelSkill.map_reduce() for parallel processing
"""
```

### Integration with Spore Nodes

```python
# In venom_spore/main.py
from venom_core.infrastructure.message_broker import MessageBroker

broker = MessageBroker()
await broker.connect()

# Listen for tasks
while True:
    task = await get_next_task_from_queue()
    result = await execute_skill(task)
    await broker.update_task_status(task.id, "completed", result=result)
```

## Metrics & Performance

### Throughput
- **Single Spore:** ~10-20 tasks/minute (depending on type)
- **5 Spore Cluster:** ~50-100 tasks/minute
- **Speedup:** ~5x for parallel tasks

### Latency
- **Task enqueue:** <10ms
- **Task routing (Foreman):** <50ms
- **Broadcast:** <100ms

### Scaling
- Linear for most tasks
- Redis overhead: marginal (<5%)
- Bottleneck: Usually I/O, not CPU

## Security

### ⚠️ CRITICAL: Production Security

THE HIVE requires special security attention due to:
- Distributed architecture with multiple nodes
- Remote code execution (OTA updates)
- Shared Redis as single point of trust

### Redis Security

**Minimum requirements:**
1. **Password**: Always set `requirepass` (REDIS_PASSWORD)
2. **Binding**: Bind to `127.0.0.1` or internal network, NOT `0.0.0.0` on public interface
3. **Firewall**: Limit access to port 6379 to trusted nodes only
4. **TLS**: Consider Redis TLS for communication over Internet

**Secure Redis configuration:**
```bash
# .env
REDIS_PASSWORD=very_strong_password_here_min_32_chars

# redis.conf or command
requirepass ${REDIS_PASSWORD}
bind 127.0.0.1  # or internal IP
protected-mode yes
```

### Pickle Serialization Security

MessageBroker uses pickle for TaskMessage serialization:
- **Risk**: Pickle can execute arbitrary code on deserialization
- **Mitigation**: All nodes must be trusted
- **Alternative**: Use JSON with custom serializers for simple tasks

**Safe usage rules:**
1. All Hive nodes in closed, trusted network (VPN, private network)
2. Redis auth (password) for additional layer
3. Monitor Redis access (logs, metrics)
4. For public deployments: consider JSON instead of pickle

### OTA Updates Security

**Problem**: OTA updates can be used for RCE if source is not verified.

**Required security measures for production:**

1. **Source authentication**:
```python
# Check that broadcast comes from trusted Nexus
if data.get("nexus_token") != SETTINGS.NEXUS_SHARED_TOKEN.get_secret_value():
    logger.error("Unauthorized OTA update attempt!")
    return
```

2. **Digital package signatures** (recommended):
```python
# Nexus: sign package
import hmac
signature = hmac.new(secret_key, package_data, hashlib.sha256).hexdigest()

# Spore: verify signature
if not hmac.compare_digest(signature, expected_signature):
    raise SecurityError("Invalid package signature!")
```

3. **Package URL whitelist**:
```python
ALLOWED_PACKAGE_HOSTS = ["nexus.internal", "localhost"]
parsed_url = urlparse(package_url)
if parsed_url.hostname not in ALLOWED_PACKAGE_HOSTS:
    raise SecurityError(f"Package URL not whitelisted: {parsed_url.hostname}")
```

4. **requirements.txt validation**:
```python
# Before pip install, check content
with open(requirements_path) as f:
    for line in f:
        if line.strip().startswith(("http://", "https://", "git+")):
            logger.error("Direct URL installs not allowed!")
            return False
```

5. **Rate limiting**:
```python
# Limit OTA update frequency (max 1 per hour)
if last_update_time and (datetime.now() - last_update_time) < timedelta(hours=1):
    logger.warning("OTA update rate limit exceeded")
    return False
```

### Task Execution Security

**Sandbox isolation**: Consider running tasks in isolated Docker containers for additional security.

**Input validation**: Always validate task payloads before execution.

### Network Security

**Recommended network architecture:**
```
Internet
    |
    v
[Firewall]
    |
    v
[Nexus Node] ----+
                 |
    [VPN/Private Network]
    |            |            |
    v            v            v
[Spore-1]   [Spore-2]   [Spore-3]
    |            |            |
    +------------+------------+
                 |
                 v
            [Redis Server]
         (internal network only)
```

### Security Checklist

Before production deployment, verify:

- [ ] Redis has strong password (`requirepass`)
- [ ] Redis not publicly accessible (firewall/binding)
- [ ] NEXUS_SHARED_TOKEN is unique and long (min 32 chars)
- [ ] OTA updates have source authentication
- [ ] Package URLs are whitelisted
- [ ] Monitoring and alerts for suspicious activity
- [ ] Backup and disaster recovery plan
- [ ] All nodes in closed network (VPN/private)
- [ ] Logs collected and analyzed
- [ ] Regular security updates for Redis and Python packages

### Incident Response

In case of suspected compromise:
1. Immediately change REDIS_PASSWORD and NEXUS_SHARED_TOKEN
2. Restart all nodes
3. Check Redis and node logs
4. Verify checksums of installed code
5. Consider reinstallation from clean images

## Roadmap

### Planned Features
- [ ] Hive Monitor dashboard (cluster visualization)
- [ ] Auto-scaling nodes (Kubernetes)
- [ ] Multi-level priorities (0-10)
- [ ] Task dependencies (DAG)
- [ ] Streaming results (partial results)
- [ ] **Digital signatures for OTA packages**
- [ ] **Redis TLS support**
- [ ] **Audit logging for security events**

## References

- [Redis Documentation](https://redis.io/docs/)
- [Redis Security](https://redis.io/docs/management/security/)
- [ARQ Documentation](https://arq-docs.helpmanual.io/)
- [MapReduce Paper](https://research.google/pubs/pub62/)
- [Python Pickle Security](https://docs.python.org/3/library/pickle.html#module-pickle)
