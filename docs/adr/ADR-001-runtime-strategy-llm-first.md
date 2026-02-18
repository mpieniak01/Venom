# ADR-001: Runtime Strategy - LLM-First with ONNX Fallback

**Status**: Accepted  
**Date**: 2026-02-18  
**Decision Makers**: Venom Core Team  
**Related**: Issue #156, `HYBRID_AI_ENGINE.md`, `PROVIDER_GOVERNANCE.md`, `MODEL_MANAGEMENT.md`

---

## Context and Problem Statement

Venom requires a clear, enforceable runtime strategy that defines how AI workloads are routed between different execution environments. The system must balance:

1. **Privacy**: Sensitive data must never leave the local environment
2. **Cost Efficiency**: Minimize cloud API costs through intelligent routing
3. **Quality**: Complex tasks requiring advanced reasoning capabilities
4. **Performance**: Acceptable latency for user experience (p95 < 3s, p99 < 5s)
5. **Reliability**: Graceful fallback when providers are unavailable

Currently, the system has routing logic (`HybridModelRouter`), provider governance (`ProviderGovernance`), and policy enforcement (`PolicyGate`), but lacks a unified contract defining:
- When to choose LLM-first vs ONNX-first
- How provider selection interacts with governance and policy gates
- What KPIs and thresholds govern routing decisions
- Explicit reason codes for observability and debugging

## Decision Drivers

1. **Privacy-first principle**: Established in `HYBRID_AI_ENGINE.md` as "Local First" strategy
2. **Zero operational cost baseline**: Default mode should be cost-free (Eco Mode)
3. **Existing infrastructure**: Ollama and vLLM as local runtime, OpenAI/Google as cloud
4. **Provider governance maturity**: Existing fallback chains and budget controls
5. **Gradual cloud adoption**: Users opt-in to paid cloud providers explicitly
6. **Task complexity heuristics**: Working classification (STANDARD, CHAT, CODING_SIMPLE/COMPLEX, etc.)

## Considered Options

### Option 1: ONNX-First Strategy
**Description**: Prioritize lightweight ONNX models for inference, fallback to LLM only when structured output or reasoning is required.

**Pros**:
- Extremely low latency (< 100ms)
- Minimal memory footprint
- Portable across hardware

**Cons**:
- Limited to classification/regression tasks
- No natural language generation capability
- Not applicable to conversational AI or code generation
- Would require major architecture redesign

**Verdict**: ❌ Rejected - Does not align with Venom's core use cases (chat, coding assistance, research)

---

### Option 2: LLM-First (Local), Cloud as Premium
**Description**: Default to local LLM (Ollama/vLLM) for all workloads. Cloud LLMs (OpenAI/Google) available only when:
- User explicitly enables paid mode
- Task complexity exceeds local capability threshold
- Sensitive data check passes

**Pros**:
- ✅ Aligns with existing "Local First" strategy
- ✅ Privacy-preserving by default
- ✅ Zero operational cost baseline
- ✅ Minimal code changes required
- ✅ Graceful fallback to cloud when needed

**Cons**:
- Higher latency for local inference (1-3s vs cloud 300-800ms)
- Requires capable local hardware (8GB+ VRAM)
- Quality dependent on local model size

**Verdict**: ✅ **SELECTED** - Best fit for Venom's principles and current architecture

---

### Option 3: Cloud-First with Local Fallback
**Description**: Route all tasks to cloud providers by default, fallback to local only on failure.

**Pros**:
- Highest quality responses (GPT-4, Gemini Pro)
- Lower latency for cloud requests
- Simpler infrastructure (no local runtime required)

**Cons**:
- ❌ Privacy concerns (all data sent to cloud)
- ❌ Operational costs from day 1
- ❌ Contradicts established "Local First" principle
- ❌ Requires API keys for basic functionality

**Verdict**: ❌ Rejected - Violates privacy-first and cost-free baseline principles

---

## Decision

**Adopt LLM-First (Local) with Cloud as Premium strategy** (Option 2)

### Default Behavior
1. **Eco Mode (Default)**: All tasks routed to local LLM (Ollama/vLLM)
   - No API keys required
   - Zero cloud costs
   - 100% privacy guaranteed
   - Target: p95 latency < 3s, p99 < 5s

2. **Paid Mode (Opt-In)**: Intelligent routing enabled
   - Simple tasks → Local LLM (cost-free)
   - Complex tasks → Cloud LLM (pay-per-use)
   - Sensitive tasks → **Always Local** (privacy override)
   - Target: p95 latency < 2s, p99 < 4s

### Task Complexity Routing Matrix

| Task Type | Complexity Score | Default Route (Eco) | Paid Mode Route |
|-----------|------------------|---------------------|-----------------|
| STANDARD | 0-3 | Local | Local |
| CHAT | 2-5 | Local | Local |
| CODING_SIMPLE | 3-6 | Local | Local |
| CODING_COMPLEX | 7-10 | Local | Cloud (if budget allows) |
| ANALYSIS | 5-8 | Local | Cloud (if budget allows) |
| GENERATION | 4-7 | Local | Local or Cloud (cost-optimized) |
| RESEARCH | 6-9 | Local | Cloud (if budget allows) |
| SENSITIVE | N/A | **Local** | **Local** (privacy override) |

**Complexity Scoring**:
- Base score from task type
- +1 for every 500 characters in prompt
- +2 if prompt contains code blocks
- +1 if requires structured output
- Capped at 10

### Provider Selection Order

**Eco Mode (paid_mode_enabled=False)**:
1. `ollama` (preferred)
2. `vllm` (fallback)
3. Block request if both unavailable

**Paid Mode - Low Complexity (<6)**:
1. `ollama` (preferred, cost-free)
2. `vllm` (fallback, cost-free)
3. Block request if both unavailable (don't escalate to cloud for simple tasks)

**Paid Mode - High Complexity (≥6)**:
1. Check cost budget remaining
2. If budget OK:
   - `openai` (GPT-4o-mini preferred for cost)
   - `google` (Gemini 1.5 Flash fallback)
3. If budget exceeded or API failure:
   - Fallback to `ollama`
   - Fallback to `vllm`
4. Block if all unavailable

**Sensitive Content Override**:
- **Always route to local providers only**, regardless of complexity or budget

---

## Routing Decision Contract

### Data Structure

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List

class RuntimeTarget(Enum):
    """Target runtime environment"""
    LOCAL_OLLAMA = "ollama"
    LOCAL_VLLM = "vllm"
    CLOUD_OPENAI = "openai"
    CLOUD_GOOGLE = "google"

class ReasonCode(Enum):
    """Reason for routing decision"""
    # Primary routing reasons
    DEFAULT_ECO_MODE = "default_eco_mode"
    TASK_COMPLEXITY_LOW = "task_complexity_low"
    TASK_COMPLEXITY_HIGH = "task_complexity_high"
    SENSITIVE_CONTENT_OVERRIDE = "sensitive_content_override"
    
    # Fallback reasons
    FALLBACK_TIMEOUT = "fallback_timeout"
    FALLBACK_AUTH_ERROR = "fallback_auth_error"
    FALLBACK_BUDGET_EXCEEDED = "fallback_budget_exceeded"
    FALLBACK_PROVIDER_DEGRADED = "fallback_provider_degraded"
    FALLBACK_PROVIDER_OFFLINE = "fallback_provider_offline"
    FALLBACK_RATE_LIMIT = "fallback_rate_limit"
    
    # Policy blocks
    POLICY_BLOCKED_BUDGET = "policy_blocked_budget"
    POLICY_BLOCKED_RATE_LIMIT = "policy_blocked_rate_limit"
    POLICY_BLOCKED_NO_PROVIDER = "policy_blocked_no_provider"
    POLICY_BLOCKED_CONTENT = "policy_blocked_content"

class RoutingDecision:
    """Contract for routing decision output"""
    
    # Primary decision
    target_runtime: RuntimeTarget
    provider: str  # "ollama", "openai", etc.
    model: str     # Specific model name
    
    # Decision metadata
    reason_code: ReasonCode
    complexity_score: float  # 0-10
    is_sensitive: bool
    
    # Governance state
    fallback_applied: bool
    fallback_chain: List[str]  # Providers attempted before success
    policy_gate_passed: bool
    
    # Cost/budget tracking
    estimated_cost_usd: float
    budget_remaining_usd: Optional[float]
    
    # Observability
    decision_timestamp: str  # ISO 8601
    decision_latency_ms: float
```

---

## Consequences

### Positive
1. ✅ **Privacy preserved**: Sensitive data never leaves local environment
2. ✅ **Cost predictable**: Default mode is $0, paid mode has explicit budgets
3. ✅ **Backward compatible**: No breaking changes to existing API 1.x
4. ✅ **Observable**: Explicit reason codes enable debugging and monitoring
5. ✅ **Extensible**: Contract supports future providers (Azure, Anthropic, etc.)
6. ✅ **User control**: Users choose when to enable cloud via paid mode

### Negative
1. ⚠️ **Local hardware dependency**: Eco mode requires 8GB+ VRAM for good performance
2. ⚠️ **Quality variance**: Local models may produce lower quality than GPT-4 for complex tasks
3. ⚠️ **Complexity overhead**: Routing logic adds 50-150ms latency for decision-making
4. ⚠️ **Fallback chain length**: Multiple fallback attempts can delay final response

### Mitigation Strategies
1. **Hardware guidance**: Document minimum requirements in `DEPLOYMENT_NEXT.md`
2. **Quality benchmarking**: Establish task-specific quality baselines in `docs/MODEL_TUNING_GUIDE.md`
3. **Caching**: Cache routing decisions for identical prompts (TTL: 5 minutes)
4. **Circuit breaker**: Skip unhealthy providers in fallback chain to reduce latency

---

## Key Performance Indicators (KPIs)

### 1. Cost KPIs
| Metric | Target | Alert Threshold | Measurement |
|--------|--------|-----------------|-------------|
| **Daily Cost (Eco Mode)** | $0.00 | $0.01 | Real-time spend tracking |
| **Daily Cost (Paid Mode)** | < $5.00 | $10.00 (soft), $50.00 (hard) | Per governance config |
| **Cost Per Request** | < $0.01 | $0.05 | Per-request cost estimation |
| **Cloud Usage Ratio** | < 20% | 50% | Requests routed to cloud / total |

### 2. Latency KPIs
| Metric | Target | Alert Threshold | Measurement |
|--------|--------|-----------------|-------------|
| **Routing Decision Latency** | < 100ms | 200ms | Time to select provider |
| **Local Inference (p50)** | < 1.5s | 3s | Ollama/vLLM response time |
| **Local Inference (p95)** | < 3s | 5s | 95th percentile |
| **Cloud Inference (p95)** | < 2s | 4s | OpenAI/Google response time |
| **Total Request (p99)** | < 5s | 10s | End-to-end including routing |

### 3. Quality KPIs
| Metric | Target | Alert Threshold | Measurement |
|--------|--------|-----------------|-------------|
| **Task Success Rate** | > 95% | < 90% | Non-error responses / total |
| **Structured Output Validity** | > 98% | < 95% | Valid JSON/format / total |
| **Fallback Success Rate** | > 90% | < 80% | Successful fallback / attempts |
| **Sensitive Data Leak Rate** | 0% | > 0% | Privacy override violations |

### 4. Reliability KPIs
| Metric | Target | Alert Threshold | Measurement |
|--------|--------|-----------------|-------------|
| **Provider Availability (Local)** | > 99% | < 95% | Uptime percentage |
| **Provider Availability (Cloud)** | > 99.9% | < 99% | SLA from providers |
| **Fallback Chain Exhaustion** | < 1% | > 5% | No provider available |

---

## Integration Map

### 1. HybridModelRouter → RoutingDecision Contract
**File**: `venom_core/execution/model_router.py`

**Changes**:
- Return `RoutingDecision` object instead of simple provider string
- Include complexity score, reason code, and fallback chain
- Record decision latency for observability

**Example**:
```python
def route_task(self, task_type: TaskType, prompt: str) -> RoutingDecision:
    start_time = time.time()
    
    # Check sensitive content
    is_sensitive = self._is_sensitive_content(prompt)
    
    # Calculate complexity
    complexity = self._calculate_complexity(task_type, prompt)
    
    # Make routing decision
    if is_sensitive:
        decision = self._route_sensitive(task_type, prompt)
    elif not self.cost_guard.paid_mode_enabled:
        decision = self._route_eco_mode(task_type, prompt)
    else:
        decision = self._route_paid_mode(task_type, prompt, complexity)
    
    # Add metadata
    decision.decision_latency_ms = (time.time() - start_time) * 1000
    decision.decision_timestamp = datetime.now(timezone.utc).isoformat()
    
    return decision
```

---

### 2. ProviderGovernance Integration
**File**: `venom_core/core/provider_governance.py`

**Changes**:
- Accept `RoutingDecision` as input to `select_provider_with_fallback()`
- Update decision object with fallback events
- Populate `fallback_chain` and `reason_code` from governance events

**Example**:
```python
def select_provider_with_fallback(
    self, 
    decision: RoutingDecision
) -> RoutingDecision:
    """Apply governance rules and fallback policy"""
    
    # Validate credentials
    if not self._validate_provider_credentials(decision.provider):
        decision = self._apply_fallback(
            decision, 
            reason=ReasonCode.FALLBACK_AUTH_ERROR
        )
    
    # Check budget
    if not self._check_budget(decision.provider, decision.estimated_cost_usd):
        decision = self._apply_fallback(
            decision,
            reason=ReasonCode.FALLBACK_BUDGET_EXCEEDED
        )
    
    # Check rate limits
    if not self._check_rate_limits(decision.provider):
        decision = self._apply_fallback(
            decision,
            reason=ReasonCode.FALLBACK_RATE_LIMIT
        )
    
    return decision
```

---

### 3. PolicyGate Integration
**File**: `venom_core/core/policy_gate.py`

**Changes**:
- Evaluate routing decision before execution
- Block or modify decision based on security/compliance rules
- Update `policy_gate_passed` flag

**Example**:
```python
def evaluate_routing_decision(
    self, 
    decision: RoutingDecision,
    context: Dict[str, Any]
) -> PolicyDecision:
    """Evaluate if routing decision complies with policies"""
    
    if not self.enabled:
        return PolicyDecision.ALLOW
    
    # Check privacy policy
    if decision.is_sensitive and decision.target_runtime not in [
        RuntimeTarget.LOCAL_OLLAMA, 
        RuntimeTarget.LOCAL_VLLM
    ]:
        decision.policy_gate_passed = False
        decision.reason_code = ReasonCode.POLICY_BLOCKED_CONTENT
        return PolicyDecision.BLOCK
    
    # Check budget policy
    if decision.estimated_cost_usd > self.max_cost_per_request:
        decision.policy_gate_passed = False
        decision.reason_code = ReasonCode.POLICY_BLOCKED_BUDGET
        return PolicyDecision.BLOCK
    
    decision.policy_gate_passed = True
    return PolicyDecision.ALLOW
```

---

### 4. Observability Integration

**Metrics Collection**:
```python
# Prometheus-style metrics
routing_decisions_total = Counter(
    'venom_routing_decisions_total',
    'Total routing decisions',
    ['target_runtime', 'reason_code', 'is_sensitive']
)

routing_decision_latency = Histogram(
    'venom_routing_decision_latency_seconds',
    'Time to make routing decision',
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5]
)

provider_fallback_total = Counter(
    'venom_provider_fallback_total',
    'Provider fallback events',
    ['from_provider', 'to_provider', 'reason_code']
)

task_cost_usd = Histogram(
    'venom_task_cost_usd',
    'Estimated cost per task',
    ['provider', 'task_type'],
    buckets=[0, 0.001, 0.01, 0.05, 0.1, 0.5]
)
```

**Logging Example**:
```json
{
  "timestamp": "2026-02-18T10:30:45.123Z",
  "event": "routing_decision",
  "target_runtime": "ollama",
  "provider": "ollama",
  "model": "gemma2:9b-instruct-q8_0",
  "reason_code": "task_complexity_low",
  "complexity_score": 3.5,
  "is_sensitive": false,
  "fallback_applied": false,
  "policy_gate_passed": true,
  "estimated_cost_usd": 0.0,
  "decision_latency_ms": 45.2
}
```

---

## Rollout Plan

### Phase 1: Documentation and Contract (Current)
**Timeline**: Sprint 1 (Week 1)
- ✅ Publish ADR-001
- ✅ Define `RoutingDecision` contract in code
- ✅ Update architectural documentation

**Deliverables**:
- `docs/adr/ADR-001-runtime-strategy-llm-first.md`
- `venom_core/contracts/routing.py` (new module)
- Updated `HYBRID_AI_ENGINE.md`, `PROVIDER_GOVERNANCE.md`

**Success Criteria**:
- ADR reviewed and accepted by team
- Contract approved in design review
- No breaking changes to existing API

---

### Phase 2: Router Refactoring
**Timeline**: Sprint 2-3 (Weeks 2-3)
- Refactor `HybridModelRouter` to return `RoutingDecision` objects
- Add complexity scoring enhancements
- Implement decision caching (5-minute TTL)

**Deliverables**:
- Updated `venom_core/execution/model_router.py`
- Unit tests for routing logic (>90% coverage)
- Integration tests for decision contract

**Success Criteria**:
- All existing tests pass
- New tests cover reason codes and fallback scenarios
- Routing decision latency < 100ms (p95)

---

### Phase 3: Governance Integration
**Timeline**: Sprint 4 (Week 4)
- Integrate `ProviderGovernance` with `RoutingDecision`
- Add fallback chain tracking
- Implement budget/rate limit checks in routing

**Deliverables**:
- Updated `venom_core/core/provider_governance.py`
- Contract tests for governance rules
- Observability dashboard updates

**Success Criteria**:
- Fallback events properly recorded in decision object
- Budget limits enforced before provider selection
- Audit trail includes full decision context

---

### Phase 4: Policy Gate Enhancement
**Timeline**: Sprint 5 (Week 5)
- Implement policy evaluation for routing decisions
- Add privacy override enforcement
- Enable policy gate in production (feature flag)

**Deliverables**:
- Updated `venom_core/core/policy_gate.py`
- Policy rule configuration (YAML/JSON)
- Security audit report

**Success Criteria**:
- Sensitive content never routed to cloud (100% enforcement)
- Policy blocks properly logged and alerted
- Zero policy violations in staging environment

---

### Phase 5: Observability and Monitoring
**Timeline**: Sprint 6 (Week 6)
- Deploy Prometheus metrics
- Create Grafana dashboards for KPIs
- Set up alerts for threshold violations

**Deliverables**:
- Metrics instrumentation in all routing code
- Grafana dashboard JSON exports
- Alert rules for Prometheus Alertmanager

**Success Criteria**:
- All KPIs measurable in real-time
- Alerts fire within 1 minute of threshold breach
- 30-day historical data retained

---

### Phase 6: Validation and Optimization
**Timeline**: Sprint 7-8 (Weeks 7-8)
- Run A/B test: current routing vs. new contract
- Collect performance and cost data
- Optimize based on production metrics

**Deliverables**:
- A/B test report with statistical analysis
- Performance tuning recommendations
- Updated operational runbooks

**Success Criteria**:
- No regression in latency or quality
- Cost reduction of ≥10% vs. baseline
- User satisfaction score ≥4.5/5

---

## Rollback Plan

### Trigger Conditions
Rollback initiated if any of:
1. **P95 latency regression** > 20% from baseline
2. **Task failure rate** > 10% for 5 consecutive minutes
3. **Sensitive data leak** detected (policy override failure)
4. **Cost overrun** > 200% of daily budget

### Rollback Procedure

#### Step 1: Feature Flag Disable (< 1 minute)
```python
# In venom_core/config.py or environment
ENABLE_ROUTING_CONTRACT = False  # Revert to legacy routing
```

#### Step 2: Deploy Previous Router Version (< 5 minutes)
```bash
# Revert to last stable commit
git revert <routing-contract-commit-range>
git push origin main

# Deploy
make deploy-backend
```

#### Step 3: Verify Rollback (< 10 minutes)
```bash
# Check metrics dashboard
curl http://localhost:8000/health/routing-status

# Validate legacy behavior
pytest tests/integration/test_routing_legacy.py
```

#### Step 4: Incident Review (Within 24 hours)
- Root cause analysis
- Document failure modes
- Update ADR-001 with lessons learned
- Plan remediation work

### Rollback Testing
- Monthly chaos engineering drills
- Automated rollback in CI/CD pipeline
- Documented runbook: `docs/runbooks/rollback-routing-contract.md`

---

## Operational Documentation

### Example Scenarios

#### Scenario 1: Standard Chat Request (Eco Mode)
**Input**:
```json
{
  "task_type": "CHAT",
  "prompt": "What is the capital of France?",
  "user_id": "user123"
}
```

**Routing Decision**:
```json
{
  "target_runtime": "LOCAL_OLLAMA",
  "provider": "ollama",
  "model": "gemma2:9b-instruct-q8_0",
  "reason_code": "default_eco_mode",
  "complexity_score": 2.0,
  "is_sensitive": false,
  "fallback_applied": false,
  "fallback_chain": [],
  "policy_gate_passed": true,
  "estimated_cost_usd": 0.0,
  "budget_remaining_usd": null
}
```

**Explanation**: Simple factual question routed to free local model.

---

#### Scenario 2: Complex Code Generation (Paid Mode, Budget OK)
**Input**:
```json
{
  "task_type": "CODING_COMPLEX",
  "prompt": "Write a Python function to implement the A* pathfinding algorithm with diagonal movement and obstacle avoidance. Include comprehensive docstrings and type hints.",
  "user_id": "user456"
}
```

**Routing Decision**:
```json
{
  "target_runtime": "CLOUD_OPENAI",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "reason_code": "task_complexity_high",
  "complexity_score": 8.5,
  "is_sensitive": false,
  "fallback_applied": false,
  "fallback_chain": [],
  "policy_gate_passed": true,
  "estimated_cost_usd": 0.015,
  "budget_remaining_usd": 42.50
}
```

**Explanation**: High complexity + long prompt → cloud model for best quality.

---

#### Scenario 3: Sensitive Data Override
**Input**:
```json
{
  "task_type": "ANALYSIS",
  "prompt": "Analyze this API key: sk-proj-abc123xyz...",
  "user_id": "user789"
}
```

**Routing Decision**:
```json
{
  "target_runtime": "LOCAL_OLLAMA",
  "provider": "ollama",
  "model": "gemma2:9b-instruct-q8_0",
  "reason_code": "sensitive_content_override",
  "complexity_score": 6.0,
  "is_sensitive": true,
  "fallback_applied": false,
  "fallback_chain": [],
  "policy_gate_passed": true,
  "estimated_cost_usd": 0.0,
  "budget_remaining_usd": 42.50
}
```

**Explanation**: Privacy override forces local routing despite paid mode enabled.

---

#### Scenario 4: Budget Exhausted with Fallback
**Input**:
```json
{
  "task_type": "RESEARCH",
  "prompt": "Compare the performance characteristics of PostgreSQL vs. MongoDB for time-series data.",
  "user_id": "user101"
}
```

**Routing Decision**:
```json
{
  "target_runtime": "LOCAL_VLLM",
  "provider": "vllm",
  "model": "Qwen2.5-14B-Instruct",
  "reason_code": "fallback_budget_exceeded",
  "complexity_score": 7.5,
  "is_sensitive": false,
  "fallback_applied": true,
  "fallback_chain": ["openai", "vllm"],
  "policy_gate_passed": true,
  "estimated_cost_usd": 0.0,
  "budget_remaining_usd": 0.25
}
```

**Explanation**: Attempted cloud routing but budget low, fell back to local vLLM.

---

#### Scenario 5: All Providers Offline
**Input**:
```json
{
  "task_type": "STANDARD",
  "prompt": "Hello, how are you?",
  "user_id": "user202"
}
```

**Routing Decision**:
```json
{
  "target_runtime": null,
  "provider": null,
  "model": null,
  "reason_code": "policy_blocked_no_provider",
  "complexity_score": 1.0,
  "is_sensitive": false,
  "fallback_applied": true,
  "fallback_chain": ["ollama", "vllm"],
  "policy_gate_passed": false,
  "estimated_cost_usd": 0.0,
  "budget_remaining_usd": null,
  "error": "No provider available: all local providers offline"
}
```

**Explanation**: Circuit breaker - no provider available, request blocked.

---

## Governance and Review

### Maintenance Schedule
- **Quarterly Review**: Assess KPI targets and adjust thresholds
- **Bi-annual Audit**: Security and compliance review of routing decisions
- **Annual Strategy Review**: Reevaluate LLM-first strategy vs. emerging alternatives

### Change Process
1. Propose changes via new ADR (ADR-XXX supersedes ADR-001)
2. Submit PR with updated contract and tests
3. Require 2+ approvals from core team
4. Validate in staging for 1 week minimum
5. Gradual rollout: 10% → 50% → 100% traffic

### Deprecation Policy
- Breaking changes to `RoutingDecision` contract require 6-month deprecation notice
- Legacy routing API maintained for 1 year after contract adoption
- Telemetry to track usage of deprecated fields

---

## References

### Related Documentation
- [Hybrid AI Engine Guide](../HYBRID_AI_ENGINE.md)
- [Provider Governance Rules](../PROVIDER_GOVERNANCE.md)
- [Cost Guard Documentation](../COST_GUARD.md)
- [Model Management System](../MODEL_MANAGEMENT.md)
- [Testing Policy](../TESTING_POLICY.md)

### Implementation Files
- `venom_core/execution/model_router.py` - Routing logic
- `venom_core/core/provider_governance.py` - Governance rules
- `venom_core/core/policy_gate.py` - Policy enforcement
- `venom_core/api/routes/governance.py` - Governance API endpoints

### External References
- [Architecture Decision Records](https://adr.github.io/)
- [OWASP AI Security and Privacy Guide](https://owasp.org/www-project-ai-security-and-privacy-guide/)
- [Google Cloud AI Best Practices](https://cloud.google.com/architecture/ai-ml/best-practices)

---

## Changelog

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-18 | Venom Core Team | Initial ADR accepted |

---

## Approval

**Approved by**:
- [ ] Lead Architect
- [ ] Tech Lead
- [ ] Security Officer
- [ ] Product Owner

**Approval Date**: _To be filled upon approval_
