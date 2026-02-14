# Before Release Checklist - Model/Provider Layer

## Overview
This checklist ensures provider and model configurations are production-ready before release.

## Phase 1: Configuration Validation

### Provider Configuration
- [ ] All required environment variables set:
  - [ ] `OPENAI_API_KEY` (if using OpenAI)
  - [ ] `GOOGLE_API_KEY` (if using Google)
  - [ ] `VLLM_ENDPOINT` (if using vLLM)
- [ ] No test/dummy credentials in production config
- [ ] API keys have appropriate scopes/permissions
- [ ] Credentials stored securely (not in code/logs)

### Connection Tests
- [ ] Test connection to each configured provider:
  ```bash
  curl -X POST http://localhost:8000/api/v1/providers/ollama/test-connection
  curl -X POST http://localhost:8000/api/v1/providers/vllm/test-connection
  curl -X POST http://localhost:8000/api/v1/providers/openai/test-connection
  curl -X POST http://localhost:8000/api/v1/providers/google/test-connection
  ```
- [ ] All tests return `status: "success"`
- [ ] Latency within acceptable range (< 2s for local, < 5s for cloud)

### Preflight Checks
- [ ] Run preflight for each provider:
  ```bash
  curl -X POST http://localhost:8000/api/v1/providers/{provider}/preflight
  ```
- [ ] All preflight checks pass (`ready_for_activation: true`)
- [ ] Review any warnings or degraded status

## Phase 2: Governance Configuration

### Cost Limits
- [ ] Global budget limits configured:
  ```bash
  curl http://localhost:8000/api/v1/governance/status | jq '.cost_limits'
  ```
- [ ] Per-provider limits set:
  - [ ] OpenAI: soft/hard limits appropriate for usage
  - [ ] Google: soft/hard limits appropriate for usage
  - [ ] Local providers: N/A (free)
- [ ] Budget alert thresholds set (50%, 80%, 95%)
- [ ] Budget period configured correctly (monthly reset)

### Rate Limits
- [ ] Rate limits configured per provider:
  - [ ] Max requests per minute
  - [ ] Max tokens per minute
- [ ] Limits match provider API tier
- [ ] Overhead margin included (e.g., 80% of provider limit)

### Fallback Policy
- [ ] Fallback provider order configured:
  ```bash
  # Example: ollama -> vllm -> openai -> google
  ```
- [ ] Fallback triggers enabled:
  - [ ] Timeout fallback
  - [ ] Auth error fallback
  - [ ] Budget exhaustion fallback
  - [ ] Degraded provider fallback
- [ ] Fallback tested manually

## Phase 3: Monitoring & Observability

### Metrics Collection
- [ ] Metrics collector initialized
- [ ] Provider metrics tracking:
  - [ ] Latency (P50, P95, P99)
  - [ ] Error rates
  - [ ] Cost tracking
  - [ ] Request volume
- [ ] Test metrics endpoint:
  ```bash
  curl http://localhost:8000/api/v1/providers/{provider}/metrics
  ```

### SLO Configuration
- [ ] SLO targets defined per provider:
  - [ ] Availability target (e.g., 99.9%)
  - [ ] Latency P99 target (e.g., < 5s)
  - [ ] Error rate target (e.g., < 1%)
  - [ ] Cost budget
- [ ] SLO breach detection working
- [ ] Test health endpoint:
  ```bash
  curl http://localhost:8000/api/v1/providers/{provider}/health
  ```

### Alerting
- [ ] Alert system configured
- [ ] Alert types enabled:
  - [ ] Provider offline
  - [ ] High latency
  - [ ] High error rate
  - [ ] Budget warning/exceeded
  - [ ] SLO breach
- [ ] Alert destinations configured (logs, monitoring system)
- [ ] Test alert endpoint:
  ```bash
  curl http://localhost:8000/api/v1/alerts
  ```

## Phase 4: Security & Audit

### Credential Security
- [ ] API keys masked in logs
- [ ] API keys masked in API responses
- [ ] No credentials in error messages
- [ ] Credentials not in git/version control
- [ ] `.env` file in `.gitignore`

### Audit Trail
- [ ] Audit trail enabled
- [ ] Test audit logging:
  ```bash
  curl http://localhost:8000/api/v1/admin/audit?limit=10
  ```
- [ ] Audit entries include:
  - [ ] Timestamp
  - [ ] User/actor
  - [ ] Action type
  - [ ] Provider affected
  - [ ] Result (success/failure)

### Access Control
- [ ] Admin endpoints restricted (localhost only or auth required)
- [ ] Test connection endpoint idempotent (safe to retry)
- [ ] No destructive operations without confirmation
- [ ] Audit trail for all admin actions

## Phase 5: Error Handling

### Error Mappings
- [ ] Error mappings defined for all reason codes:
  - [ ] `connection_failed`
  - [ ] `AUTH_ERROR`
  - [ ] `missing_api_key`
  - [ ] `TIMEOUT`
  - [ ] `BUDGET_EXCEEDED`
  - [ ] `PROVIDER_DEGRADED`
  - [ ] `PROVIDER_OFFLINE`
  - [ ] Others...
- [ ] User messages user-friendly
- [ ] Admin messages include technical details
- [ ] Recovery hints provided
- [ ] Runbook links work

### Runbook Availability
- [ ] Runbooks created and accessible:
  - [ ] [Provider Offline](./runbooks/provider-offline.md)
  - [ ] [Auth Failures](./runbooks/auth-failures.md)
  - [ ] [Latency Spike](./runbooks/latency-spike.md)
  - [ ] [Budget Exhaustion](./runbooks/budget-exhaustion.md)
- [ ] Runbooks tested with actual scenarios
- [ ] Runbook links in UI work

## Phase 6: Performance Testing

### Load Testing
- [ ] Test under expected load:
  - [ ] Concurrent requests: ___
  - [ ] Requests per minute: ___
  - [ ] Peak load capacity: ___
- [ ] Measure baseline latency
- [ ] Measure resource usage (CPU, memory, GPU)
- [ ] Verify no memory leaks over time

### Failover Testing
- [ ] Test provider failover:
  ```bash
  # Stop primary provider
  # Verify automatic fallback
  # Restart primary
  # Verify recovery
  ```
- [ ] Measure failover time (should be < 5s)
- [ ] Verify no request loss during failover
- [ ] Test manual provider switching

### Recovery Testing
- [ ] Test recovery from offline provider:
  - [ ] Provider goes offline → handled gracefully
  - [ ] Provider comes back online → auto-recovered
- [ ] Test recovery from auth failure
- [ ] Test recovery from budget exhaustion

## Phase 7: Documentation

### Operational Docs
- [ ] Deployment guide updated
- [ ] Configuration guide updated
- [ ] Troubleshooting guide updated
- [ ] Runbooks accessible to ops team

### Admin UI Documentation
- [ ] Admin UI screenshots current
- [ ] Configuration steps documented
- [ ] Test connection procedure documented
- [ ] Error recovery procedures documented

## Phase 8: Pre-Release Validation

### Smoke Tests
- [ ] Run smoke test suite:
  ```bash
  make test-smoke
  ```
- [ ] All smoke tests pass
- [ ] No critical errors in logs

### Integration Tests
- [ ] Run integration tests:
  ```bash
  make test
  ```
- [ ] Provider integration tests pass
- [ ] Governance tests pass
- [ ] Audit trail tests pass

### Quality Gates
- [ ] `make pr-fast` passes
- [ ] `make check-new-code-coverage` passes
- [ ] Backend linting clean:
  ```bash
  pre-commit run --all-files
  ```
- [ ] Frontend linting clean:
  ```bash
  npm --prefix web-next run lint
  ```
- [ ] Frontend tests pass:
  ```bash
  npm --prefix web-next run test:unit
  ```

## Phase 9: Deployment Readiness

### Environment Verification
- [ ] Production environment variables set
- [ ] Production credentials configured
- [ ] Production provider endpoints verified
- [ ] Production monitoring connected

### Rollback Plan
- [ ] Rollback procedure documented
- [ ] Configuration backup created
- [ ] Rollback tested in staging
- [ ] Rollback owner assigned

### Monitoring Setup
- [ ] Dashboards configured
- [ ] Alerts configured and tested
- [ ] On-call rotation updated
- [ ] Runbooks linked in monitoring

## Phase 10: Post-Release

### Monitoring Window
- [ ] Monitor for first 30 minutes continuously
- [ ] Monitor for first 24 hours frequently
- [ ] Check metrics hourly for first day

### Validation
- [ ] Verify all providers operational
- [ ] Verify no unexpected errors
- [ ] Verify cost tracking accurate
- [ ] Verify audit trail working

### Documentation
- [ ] Update release notes
- [ ] Document any issues encountered
- [ ] Update runbooks if needed
- [ ] Share learnings with team

## Sign-Off

- [ ] Technical lead review: _____________
- [ ] Operations review: _____________
- [ ] Security review: _____________
- [ ] Release approved: _____________
- [ ] Deployment date/time: _____________

## Related Documents
- [Rollout/Rollback Procedure](./runbooks/rollout-rollback.md)
- [Provider Offline Runbook](./runbooks/provider-offline.md)
- [Auth Failures Runbook](./runbooks/auth-failures.md)
- [Latency Spike Runbook](./runbooks/latency-spike.md)
- [Budget Exhaustion Runbook](./runbooks/budget-exhaustion.md)
