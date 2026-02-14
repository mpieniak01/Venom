# Provider Governance - Rules and Decision Table

## Overview
This document describes the governance rules, triggers, actions, and reason codes for the Provider Governance system implemented in issue #142.

## Governance Decision Table

| Rule Category | Trigger | Action | Reason Code | User Message (EN) | User Message (PL) |
|--------------|---------|--------|-------------|-------------------|-------------------|
| **Cost Limits - Soft** | Global cost exceeds soft limit ($10 default) | Allow + Warning log | None | Request allowed (warning: approaching budget limit) | Żądanie dozwolone (ostrzeżenie: zbliżanie do limitu budżetu) |
| **Cost Limits - Hard** | Global cost exceeds hard limit ($50 default) | Block request | `BUDGET_HARD_LIMIT_EXCEEDED` | Global hard limit exceeded: ${total} > ${limit} | Przekroczono globalny twardy limit: ${total} > ${limit} |
| **Cost Limits - Provider** | Provider cost exceeds hard limit ($25 default) | Block request | `PROVIDER_BUDGET_EXCEEDED` | Provider {provider} hard limit exceeded: ${total} > ${limit} | Przekroczono twardy limit providera {provider}: ${total} > ${limit} |
| **Rate Limits - Requests** | Requests per minute exceeds max (100 default) | Block request | `RATE_LIMIT_REQUESTS_EXCEEDED` | Global request rate limit exceeded: {count} > {max}/min | Przekroczono globalny limit liczby zapytań: {count} > {max}/min |
| **Rate Limits - Tokens** | Tokens per minute exceeds max (100k default) | Block request | `RATE_LIMIT_TOKENS_EXCEEDED` | Global token rate limit exceeded: {count} > {max}/min | Przekroczono globalny limit liczby tokenów: {count} > {max}/min |
| **Credentials - Missing** | OpenAI/Google API key not configured | Fallback to local provider | `FALLBACK_AUTH_ERROR` | Switched to {provider} due to missing credentials | Przełączono na {provider} z powodu braku danych uwierzytelniających |
| **Credentials - Invalid** | API key validation fails | Fallback to local provider | `FALLBACK_AUTH_ERROR` | Switched to {provider} due to invalid credentials | Przełączono na {provider} z powodu nieprawidłowych danych |
| **Fallback - Timeout** | Provider response time > threshold (30s default) | Switch to next in fallback order | `FALLBACK_TIMEOUT` | Switched to {provider} due to timeout | Przełączono na {provider} z powodu przekroczenia czasu |
| **Fallback - Budget** | Provider budget exceeded + fallback enabled | Switch to cheaper provider | `FALLBACK_BUDGET_EXCEEDED` | Switched to {provider} due to budget exceeded | Przełączono na {provider} z powodu przekroczenia budżetu |
| **Fallback - Degraded** | Provider status = degraded + fallback enabled | Switch to healthy provider | `FALLBACK_DEGRADED` | Switched to {provider} due to degradation | Przełączono na {provider} z powodu degradacji |
| **Fallback - Offline** | Provider status = offline | Switch to available provider | `FALLBACK_OFFLINE` | Switched to {provider} - original provider offline | Przełączono na {provider} - oryginalny provider offline |
| **Fallback - No Available** | All providers unavailable/blocked | Block request | `NO_PROVIDER_AVAILABLE` | No provider available: {reason} | Brak dostępnego providera: {reason} |

## Credential Status Codes

| Status Code | Description | When Used |
|------------|-------------|-----------|
| `configured` | Provider has valid credentials | OpenAI/Google API keys are set and validated |
| `missing_credentials` | Provider lacks required credentials | OpenAI/Google API keys are empty or not set |
| `invalid_credentials` | Provider has invalid credentials | API key format is invalid or auth fails |

## Fallback Policy Configuration

Default fallback order:
1. `ollama` (preferred - local, free)
2. `vllm` (local, free)
3. `openai` (cloud, paid)
4. `google` (cloud, paid)

Configurable settings:
- `preferred_provider`: Default provider to use (default: `ollama`)
- `fallback_order`: Ordered list of providers to try
- `enable_timeout_fallback`: Allow fallback on timeout (default: `true`)
- `enable_auth_fallback`: Allow fallback on auth error (default: `true`)
- `enable_budget_fallback`: Allow fallback on budget exceeded (default: `true`)
- `enable_degraded_fallback`: Allow fallback on provider degradation (default: `true`)
- `timeout_threshold_seconds`: Timeout threshold (default: `30.0`)

## Cost Limit Configuration

| Scope | Soft Limit (USD) | Hard Limit (USD) | Description |
|-------|------------------|------------------|-------------|
| Global | $10 | $50 | Total cost across all providers |
| Per-Provider | $5 | $25 | Cost per specific provider (configurable) |
| Per-Model | - | - | Not yet implemented (future enhancement) |

## Rate Limit Configuration

| Scope | Max Requests/min | Max Tokens/min | Description |
|-------|------------------|----------------|-------------|
| Global | 100 | 100,000 | Total rate across all providers |
| Per-Provider | - | - | Configurable per provider (future enhancement) |

## API Endpoints

### GET /api/v1/governance/status
Returns current governance status including:
- Active cost and rate limits
- Current usage metrics
- Recent fallback events (last 10)
- Fallback policy configuration

### GET /api/v1/governance/limits
Returns configured limits without usage data:
- Cost limits (soft/hard) per scope
- Rate limits (requests/tokens) per scope

### GET /api/v1/governance/providers/{provider}/credentials
Validates provider credentials without exposing secrets:
- Returns: `configured`, `missing_credentials`, or `invalid_credentials`
- Never exposes actual API keys in response

### POST /api/v1/governance/limits
Updates cost or rate limits dynamically:
- Payload: `{ limit_type: "cost"|"rate", scope: "global"|provider_name, ... }`
- Returns updated limit configuration

### POST /api/v1/governance/reset-usage
Resets usage counters:
- Query param `scope`: optional, resets specific scope or all if omitted
- Useful for testing or monthly reset

## Audit Trail

All fallback events are recorded with:
- Timestamp
- From provider
- To provider
- Reason code
- User message
- Technical details (optional)

History is maintained for last 100 events in memory.

## Security Features

### Secret Masking
- API keys are masked in logs: `sk-1234...ghij`
- Secrets never appear in API responses
- Config uses Pydantic `SecretStr` for sensitive data

### No Secret Leakage
- Credential validation never logs full keys
- Governance status endpoint never exposes credentials
- All tests verify no secrets in logs

## Testing Coverage

Comprehensive test suite with 42 tests covering:
- ✅ Credential validation (configured/missing/invalid)
- ✅ Secret masking and no leakage
- ✅ Cost limits (under/soft/hard)
- ✅ Rate limits (requests/tokens)
- ✅ Fallback policy (all reason codes)
- ✅ Governance status API
- ✅ Reason code stability
- ✅ Singleton pattern

**Coverage:** 94.3% for changed lines (above 80% threshold)

## Integration Points

### Existing Components
- **TokenEconomist**: Cost calculation and tracking
- **SETTINGS (config.py)**: Credential storage with SecretStr
- **Providers API**: Provider status and activation
- **StateManager**: Global cost mode (paid/free)

### Future Enhancements
1. Per-model cost limits
2. Per-provider rate limits
3. Time-window based limits (hourly/daily)
4. Budget reset automation
5. Alert/notification on limit thresholds
6. Integration with cloud provider billing APIs
7. Cost optimization suggestions
