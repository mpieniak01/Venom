# Runbook: Budget Exhaustion

## Overview
This runbook addresses cost budget exhaustion for cloud AI providers.

## Symptoms
- Reason code: `BUDGET_EXCEEDED`
- Requests blocked with budget error
- Cost alerts firing
- Provider fallback to cheaper alternatives

## Common Causes
1. Unexpected spike in usage
2. Cost limits set too low
3. Expensive model selection
4. Missing cost optimization
5. Token usage higher than expected
6. No budget monitoring

## Diagnostic Steps

### 1. Check Current Budget Status
```bash
# Get cost governance status
curl http://localhost:8000/api/v1/governance/status

# Check provider metrics
curl http://localhost:8000/api/v1/providers/{provider_name}/metrics
```

### 2. Review Cost Breakdown
```bash
# Get detailed cost metrics
curl http://localhost:8000/api/v1/providers/openai/metrics | jq '.metrics.cost'
curl http://localhost:8000/api/v1/providers/google/metrics | jq '.metrics.cost'
```

### 3. Check Budget Configuration
```bash
# Via API
curl http://localhost:8000/api/v1/governance/status | jq '.cost_limits'

# Via UI
# Navigate to /config → Cost Guard section
```

### 4. Review Recent Usage
```bash
# Check alerts
curl "http://localhost:8000/api/v1/alerts?provider={provider_name}"

# Check audit log
curl "http://localhost:8000/api/v1/admin/audit?limit=50" | jq '.entries[] | select(.details.cost)'
```

### 5. Identify Cost Drivers
```bash
# Check token usage
curl http://localhost:8000/api/v1/providers/{provider_name}/metrics | jq '.metrics.cost.total_tokens'

# Check request volume
curl http://localhost:8000/api/v1/providers/{provider_name}/metrics | jq '.metrics.total_requests'
```

## Resolution Steps

### Immediate Mitigation

**Option 1: Increase Budget (if justified)**
```bash
# Via API
curl -X POST http://localhost:8000/api/v1/governance/limits \
  -H "Content-Type: application/json" \
  -d '{
    "limit_type": "per_provider",
    "scope": "openai",
    "soft_limit_usd": 100.0,
    "hard_limit_usd": 150.0
  }'
```

Or via UI:
1. Navigate to `/config`
2. Go to Cost Guard section
3. Update provider limits
4. Click "Save"

**Option 2: Switch to Cheaper Provider**
```bash
# Activate Ollama (free local provider)
curl -X POST http://localhost:8000/api/v1/providers/ollama/activate

# Or enable automatic fallback
# In .env:
ENABLE_BUDGET_FALLBACK=true
FALLBACK_ORDER=ollama,vllm,openai,google
```

**Option 3: Temporarily Disable Expensive Provider**
1. In UI, go to `/config` → Providers
2. Deactivate expensive provider
3. Activate local alternative

### Long-term Optimization

**Option 1: Optimize Model Selection**
```bash
# Use cheaper GPT-4o-mini instead of GPT-4
curl -X POST http://localhost:8000/api/v1/providers/openai/activate \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini"}'

# Cost comparison (approximate):
# - GPT-4o: $10/1M input tokens, $30/1M output
# - GPT-4o-mini: $0.15/1M input tokens, $0.60/1M output
```

**Option 2: Implement Smart Routing**
1. Configure tiered routing:
   - Simple queries → Ollama (free)
   - Medium complexity → GPT-4o-mini (cheap)
   - Complex queries → GPT-4o (expensive)
   
2. Enable based on query complexity analysis

**Option 3: Enable Caching**
```bash
# Reduce duplicate requests
# Configure in .env:
ENABLE_RESPONSE_CACHE=true
CACHE_TTL_SECONDS=3600
```

**Option 4: Set Up Budget Alerts**
1. Configure soft limits for warnings:
   - Soft limit: 80% of budget (warning)
   - Hard limit: 100% of budget (block)

2. Via UI or API:
   ```bash
   curl -X POST http://localhost:8000/api/v1/governance/limits \
     -H "Content-Type: application/json" \
     -d '{
       "limit_type": "global",
       "scope": "global",
       "soft_limit_usd": 400.0,
       "hard_limit_usd": 500.0
     }'
   ```

**Option 5: Optimize Prompts**
- Reduce prompt length
- Remove unnecessary context
- Use more concise instructions
- Avoid repeating information

### Budget Recovery

**Option 1: Reset Budget Period**
This typically resets monthly automatically, but can be manually reset:
```bash
# Requires admin action
# Contact system administrator
```

**Option 2: Allocate Emergency Budget**
If critical and justified:
1. Review cost justification
2. Get approval from budget owner
3. Increase hard limit temporarily
4. Set reminder to review and reduce later

**Option 3: Redistribute Budget**
- Move budget from underutilized providers
- Adjust per-model allocations
- Review global vs per-provider limits

## Prevention

### 1. Set Appropriate Limits
```bash
# Example configuration
Global soft limit: $400/month
Global hard limit: $500/month

Per-provider:
- OpenAI soft: $200, hard: $250
- Google soft: $150, hard: $200
- Ollama/vLLM: No limit (local, free)
```

### 2. Monitor Continuously
- Review cost dashboard daily
- Set up alerts:
  - 50% budget: Info alert
  - 80% budget: Warning alert
  - 95% budget: Critical alert

### 3. Optimize Usage Patterns
- Prefer local providers for development/testing
- Use cloud providers for production only
- Implement request batching
- Enable response caching

### 4. Regular Reviews
- Weekly cost review
- Monthly budget planning
- Quarterly optimization review
- Track cost per request trends

### 5. Cost-Aware Development
- Include cost in request routing logic
- Show cost estimates to users
- Implement per-user quotas if needed
- Track cost by feature/component

## Troubleshooting Edge Cases

### Budget Shows as Exceeded But Usage is Low
1. Check if budget period has reset
2. Verify budget configuration
3. Check for configuration errors
4. Review audit log for manual changes

### Different Cost in Dashboard vs Provider
1. May include pending/processing requests
2. Check calculation method
3. Verify token counting matches provider
4. Contact support if significant discrepancy

### Sudden Cost Spike
1. Review audit log for unusual activity
2. Check for potential abuse or attack
3. Verify no test scripts running in production
4. Review recent code changes

## Escalation
If budget issues persist:
1. Gather cost reports:
   ```bash
   curl http://localhost:8000/api/v1/governance/status > cost-status.json
   curl http://localhost:8000/api/v1/providers/openai/metrics > openai-metrics.json
   curl http://localhost:8000/api/v1/providers/google/metrics > google-metrics.json
   ```
2. Review with finance/budget owner
3. Consider architectural changes:
   - More local inference
   - Fine-tuned smaller models
   - Hybrid approach

## Related Runbooks
- [Provider Offline](./provider-offline.md)
- [Auth Failures](./auth-failures.md)
- [Latency Spike](./latency-spike.md)

## Verification
After resolution:
1. Verify budget status:
   ```bash
   curl http://localhost:8000/api/v1/governance/status
   ```
2. Check no budget alerts active
3. Test requests complete successfully
4. Monitor cost rate over 24 hours
5. Verify fallback works if budget hit again
