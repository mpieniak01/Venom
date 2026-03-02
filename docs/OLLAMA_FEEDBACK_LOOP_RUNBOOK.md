# Ollama Feedback-Loop Runbook

## Goal
Control model resolution for coding feedback-loop class `OpenCodeInterpreter-Qwen2.5-7B`.

Policy in runtime:
- primary: `qwen2.5-coder:7b`
- fallbacks: `qwen2.5-coder:3b`, `codestral:latest`

## Check Runtime State
```bash
curl -s http://127.0.0.1:8000/api/v1/system/llm-runtime/options | jq '.feedback_loop, .active'
```

Key fields:
- `requested_model_alias`
- `resolved_model_id`
- `resolution_reason` (`exact` | `fallback` | `resource_guard`)

## Install By Alias (idempotent)
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/models/install \
  -H 'Content-Type: application/json' \
  -d '{"name":"OpenCodeInterpreter-Qwen2.5-7B"}'
```

Expected behavior:
- if already installed: returns `already_installed=true`
- if primary blocked by resource guard: installer plans fallback candidate

## Activate With Fallback Allowed
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/system/llm-servers/active \
  -H 'Content-Type: application/json' \
  -d '{"server_name":"ollama","model_alias":"OpenCodeInterpreter-Qwen2.5-7B"}'
```

## Activate Exact-Only (no fallback)
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/system/llm-servers/active \
  -H 'Content-Type: application/json' \
  -d '{"server_name":"ollama","model_alias":"OpenCodeInterpreter-Qwen2.5-7B","exact_only":true}'
```

Expected behavior:
- returns 409 when primary is unavailable or blocked by resource guard
- payload/error includes recommendation to use fallback or tune profile/resources

## Common Fixes
1. Resource guard triggered on low profile:
- set `VENOM_OLLAMA_PROFILE=balanced-12-24gb`
2. 7B unavailable in local catalog:
- install `qwen2.5-coder:7b`
3. Host too weak for 7B:
- use fallback `qwen2.5-coder:3b`
