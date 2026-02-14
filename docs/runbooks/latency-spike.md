# Runbook: Latency Spike

## Overview
This runbook addresses sudden increases in provider response latency.

## Symptoms
- Provider response time significantly higher than baseline
- Reason codes: `TIMEOUT`, `PROVIDER_DEGRADED`
- Slow user experience
- Queue buildup

## Common Causes
1. Provider service degradation
2. Network congestion
3. Model overload
4. Resource constraints (CPU, memory, GPU)
5. Rate limiting active
6. Large request payload

## Diagnostic Steps

### 1. Check Current Latency
```bash
# Get provider metrics
curl http://localhost:8000/api/v1/providers/{provider_name}/metrics

# Check health status
curl http://localhost:8000/api/v1/providers/{provider_name}/health
```

### 2. Review Historical Metrics
```bash
# Get recent alerts
curl "http://localhost:8000/api/v1/alerts?provider={provider_name}&severity=warning"
```

### 3. Check Provider Health

**For Ollama:**
```bash
# Check response time
time curl http://localhost:11434/api/tags

# Check system resources
htop  # or top
nvidia-smi  # if using GPU
```

**For vLLM:**
```bash
# Check health endpoint
time curl http://localhost:8001/health

# Check metrics
curl http://localhost:8001/metrics

# Check GPU utilization
nvidia-smi
```

**For Cloud Providers:**
```bash
# Check provider status pages
# OpenAI: https://status.openai.com
# Google: https://status.cloud.google.com
```

### 4. Check Network Latency
```bash
# Local providers
ping localhost
traceroute localhost

# Cloud providers
ping api.openai.com
traceroute api.openai.com
```

### 5. Review System Resources
```bash
# CPU and memory
free -h
top -bn1 | head -20

# Disk I/O
iostat -x 1 5

# GPU (if applicable)
nvidia-smi
```

## Resolution Steps

### For Local Provider Degradation

**Option 1: Restart Service**
```bash
# Ollama
make ollama-restart

# vLLM
make vllm-restart
```

**Option 2: Reduce Load**
1. Check concurrent requests:
   ```bash
   curl http://localhost:8000/api/v1/governance/status
   ```
2. Enable rate limiting if not active
3. Consider scaling to multiple instances

**Option 3: Optimize Model**
For Ollama:
```bash
# Use smaller/faster model
ollama pull llama2:7b  # instead of :13b or :70b

# Update active model in config
curl -X POST http://localhost:8000/api/v1/system/llm-servers/active \
  -H "Content-Type: application/json" \
  -d '{"server_type": "ollama", "model_name": "llama2:7b"}'
```

**Option 4: Check Resource Constraints**
```bash
# If GPU memory is full
nvidia-smi
# Consider:
# - Reducing batch size
# - Using quantized model
# - Adding GPU memory
```

### For Cloud Provider Degradation

**Option 1: Enable Fallback**
1. Configure fallback provider in UI (`/config`)
2. Enable automatic fallback:
   ```bash
   # In .env
   ENABLE_DEGRADED_FALLBACK=true
   TIMEOUT_THRESHOLD_SECONDS=10
   ```
3. Set fallback order: `ollama -> vllm -> openai -> google`

**Option 2: Switch Provider Manually**
```bash
# Activate faster/available provider
curl -X POST http://localhost:8000/api/v1/providers/ollama/activate
```

**Option 3: Adjust Timeout**
```bash
# In .env, increase if needed
REQUEST_TIMEOUT_SECONDS=60  # default is 30
```

### For Rate Limiting

**Option 1: Check Limits**
```bash
curl http://localhost:8000/api/v1/governance/status
```

**Option 2: Adjust Rate Limits**
1. Via UI: Navigate to `/config` → Governance
2. Increase limits if appropriate:
   - `max_requests_per_minute`
   - `max_tokens_per_minute`

**Option 3: Distribute Load**
- Use multiple providers
- Enable round-robin if available
- Implement request queuing

### For Network Issues

**Option 1: Check DNS**
```bash
nslookup api.openai.com
dig api.openai.com
```

**Option 2: Check Firewall/Proxy**
```bash
# Check if requests are being blocked
curl -v https://api.openai.com
```

**Option 3: Use Alternative Endpoint**
- For local providers, try `127.0.0.1` instead of `localhost`
- Check if different network interface helps

## Prevention

### 1. Set Up Monitoring
- Configure latency alerts (already in place via SLO monitoring)
- Set thresholds:
  - P95 latency warning: > 2s
  - P99 latency critical: > 5s

### 2. Enable Auto-Scaling
```bash
# For local providers with multiple instances
# Configure load balancer
# Set up horizontal pod autoscaling (Kubernetes)
```

### 3. Implement Caching
- Enable response caching for common queries
- Use semantic caching for similar requests

### 4. Optimize Requests
- Reduce prompt length where possible
- Use streaming for long responses
- Batch similar requests

### 5. Regular Maintenance
- Monitor resource usage trends
- Plan capacity based on growth
- Test failover procedures regularly

## Troubleshooting Edge Cases

### Latency Only for Specific Model
- Switch to alternative model
- Check model-specific metrics
- Consider model optimization (quantization)

### Latency Only at Peak Times
- Implement request throttling
- Add capacity during peak hours
- Consider auto-scaling

### Latency After Recent Change
- Review recent configuration changes
- Check audit log for admin actions
- Consider rollback if safe

## Escalation
If latency remains high:
1. Check provider status pages for outages
2. Review application logs for errors
3. Collect diagnostic data:
   ```bash
   # Metrics snapshot
   curl http://localhost:8000/api/v1/providers/{provider_name}/metrics > metrics.json
   
   # Recent alerts
   curl http://localhost:8000/api/v1/alerts > alerts.json
   
   # Audit log
   curl http://localhost:8000/api/v1/admin/audit?limit=50 > audit.json
   ```
4. Contact support with diagnostic data

## Related Runbooks
- [Provider Offline](./provider-offline.md)
- [Budget Exhaustion](./budget-exhaustion.md)

## Verification
After resolution:
1. Check latency metrics:
   ```bash
   curl http://localhost:8000/api/v1/providers/{provider_name}/metrics
   ```
2. Verify P95 < 2s, P99 < 5s
3. Test actual user request
4. Monitor for 15 minutes to ensure stability
5. Check no latency alerts are firing
