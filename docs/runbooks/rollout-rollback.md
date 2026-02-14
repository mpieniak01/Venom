# Provider Configuration Rollout/Rollback Procedure

## Overview
Safe procedure for deploying and rolling back provider configuration changes.

## Principles
1. **Idempotency**: All operations should be safe to retry
2. **Auditability**: All changes logged in audit trail
3. **Reversibility**: Always possible to rollback
4. **Validation**: Test before committing

## Pre-Rollout Checklist

### 1. Backup Current Configuration
```bash
# Export current config
curl http://localhost:8000/api/v1/config/runtime > config-backup-$(date +%Y%m%d-%H%M%S).json

# Save current provider status
curl http://localhost:8000/api/v1/providers > providers-backup-$(date +%Y%m%d-%H%M%S).json
```

### 2. Review Change
- [ ] Change documented in ticket/issue
- [ ] Reviewed by second person
- [ ] Impact assessment completed
- [ ] Rollback plan prepared
- [ ] Monitoring in place

### 3. Test in Non-Production
```bash
# Test provider activation
curl -X POST http://localhost:8000/api/v1/providers/{provider}/test-connection

# Test preflight
curl -X POST http://localhost:8000/api/v1/providers/{provider}/preflight

# Verify results before proceeding
```

### 4. Schedule Change Window
- Prefer low-traffic periods
- Notify stakeholders
- Have rollback operator ready
- Monitor for 30 minutes post-change

## Rollout Procedure

### Step 1: Pre-Check
```bash
# Check system health
curl http://localhost:8000/api/v1/providers | jq '.providers[] | {name, connection_status}'

# Check current active provider
curl http://localhost:8000/api/v1/providers | jq '.active_provider'

# Verify no critical alerts
curl http://localhost:8000/api/v1/alerts?severity=critical
```

### Step 2: Apply Configuration Change

**For Provider Activation:**
```bash
# Test connection first
curl -X POST http://localhost:8000/api/v1/providers/{provider}/test-connection

# If test passes, activate
curl -X POST http://localhost:8000/api/v1/providers/{provider}/activate \
  -H "Content-Type: application/json" \
  -d '{"model": "model-name"}'
```

**For Environment Variable Changes:**
```bash
# 1. Update .env file
vim .env

# 2. Restart service
make api-stop
make api-start

# 3. Wait for startup (10-15 seconds)
sleep 15

# 4. Verify
curl http://localhost:8000/health
```

**For Governance Limits:**
```bash
# Update limits via API
curl -X POST http://localhost:8000/api/v1/governance/limits \
  -H "Content-Type: application/json" \
  -d '{
    "limit_type": "per_provider",
    "scope": "openai",
    "soft_limit_usd": 200.0,
    "hard_limit_usd": 250.0
  }'

# Verify
curl http://localhost:8000/api/v1/governance/status
```

### Step 3: Verify Change
```bash
# Check provider status
curl http://localhost:8000/api/v1/providers/{provider}/status

# Test actual request
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "test"}]}'

# Check audit log
curl http://localhost:8000/api/v1/admin/audit?limit=5
```

### Step 4: Monitor
Monitor for 30 minutes:
```bash
# Watch metrics
watch -n 10 'curl -s http://localhost:8000/api/v1/providers/{provider}/metrics | jq ".metrics"'

# Watch alerts
watch -n 30 'curl -s http://localhost:8000/api/v1/alerts | jq ".summary"'

# Check logs
tail -f logs/backend.log | grep -i error
```

### Step 5: Document
```bash
# Record in audit
# - What changed
# - Who made the change
# - Timestamp
# - Result

# Update operational log
# Add to change history
```

## Rollback Procedure

### When to Rollback
Rollback if any of these occur within 30 minutes:
- Provider status becomes `offline` or `degraded`
- Error rate > 5%
- Latency P95 > 2x baseline
- Critical alerts fire
- Unexpected behavior reported

### Rollback Steps

**Step 1: Assess**
```bash
# Check current state
curl http://localhost:8000/api/v1/providers | jq '.providers[] | {name, connection_status, is_active}'

# Check errors
curl http://localhost:8000/api/v1/alerts?severity=critical
```

**Step 2: Restore Previous Provider**
```bash
# Activate previous provider
curl -X POST http://localhost:8000/api/v1/providers/{previous_provider}/activate

# Verify
curl http://localhost:8000/api/v1/providers | jq '.active_provider'
```

**Step 3: Restore Configuration (if needed)**
```bash
# If .env was changed, restore backup
cp config-backup-TIMESTAMP.env .env

# Restart
make restart

# Wait and verify
sleep 15
curl http://localhost:8000/health
```

**Step 4: Verify Rollback**
```bash
# Test request works
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "rollback test"}]}'

# Check status stabilizes
curl http://localhost:8000/api/v1/providers/{provider}/status
```

**Step 5: Document Rollback**
- Log why rollback was necessary
- Capture error messages
- Note for post-mortem
- Update audit trail

## Gradual Rollout (Canary)

For high-risk changes:

### Step 1: Test with Single Request
```bash
# Send test request to new provider
curl -X POST http://localhost:8000/api/v1/providers/{new_provider}/activate

# Send test request
curl -X POST http://localhost:8000/api/v1/chat/completions ...

# Rollback immediately
curl -X POST http://localhost:8000/api/v1/providers/{old_provider}/activate
```

### Step 2: Gradual Traffic Shift
If routing logic supports it:
1. 10% traffic to new provider → monitor 1 hour
2. 25% traffic → monitor 1 hour
3. 50% traffic → monitor 2 hours
4. 100% traffic → monitor 4 hours

### Step 3: Stabilize
Monitor for 24 hours after 100% rollout before considering complete.

## Emergency Rollback

In production emergency:

```bash
# Fast rollback - single command
curl -X POST http://localhost:8000/api/v1/providers/{safe_provider}/activate

# Restart if needed
make restart

# Notify team
echo "Emergency rollback completed at $(date)" | mail -s "Provider Rollback" team@example.com
```

## Post-Change Review

After rollout or rollback:
1. Review metrics for 24 hours
2. Check error logs
3. Verify cost impact
4. Update documentation
5. Share learnings with team

## Automation

Consider automating:
```bash
#!/bin/bash
# scripts/provider-rollout.sh

PROVIDER=$1
MODEL=$2

# Backup
curl http://localhost:8000/api/v1/config/runtime > backup-$(date +%Y%m%d-%H%M%S).json

# Test
RESULT=$(curl -X POST http://localhost:8000/api/v1/providers/${PROVIDER}/test-connection)
if echo "$RESULT" | grep -q "success"; then
  # Activate
  curl -X POST http://localhost:8000/api/v1/providers/${PROVIDER}/activate \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"${MODEL}\"}"
else
  echo "Test failed, aborting"
  exit 1
fi
```

## Related Documents
- [Provider Offline Runbook](./provider-offline.md)
- [Before Release Checklist](./before-release-checklist.md)
