# PR240 Artifact Inventory

This document defines the stable scope for PR240 cleanup and keeps product work separate from diagnostics and generated artifacts.

## In Scope

### Product

- `.github/agents/venom-full-agent.agent.md`
- `.github/agents/venom-local-first-orchestrator.agent.md`
- `.github/copilot-instructions.md`
- `venom_core/agents/integrator.py`
- `venom_core/execution/skills/git_skill.py`
- `tools/vscode-chat-executor/package.json`
- `tools/vscode-chat-executor/package-lock.json`
- `tools/vscode-chat-executor/src/extension.ts`
- `tools/vscode-chat-executor/README.md`
- `tools/vscode-chat-executor/.vscode/launch.json`
- `tools/vscode-chat-executor/.vscode/extensions.json`
- `tools/vscode-chat-executor/.gitignore`

### Documentation

- `docs/CHAT_OPERATOR.md`
- `docs/PL/CHAT_OPERATOR.md`
- this document

### Sensible tests and gates

- `tests/test_git_skill.py`
- `tests/test_integrator_agent.py`
- `make pr-fast`
- `make local-first-pr239-selftest`
- `make local-first-pr240-orchestrator-routing-probe`
- `make local-first-pr240-full-agent-handoff-probe`
- `make local-first-agent-config-validate`

## Out of Scope

### Diagnostic noise

- blind probes that only reflect file presence or static text
- exploratory logs and exported debug traces
- temporary `test-results/*` outputs

### Generated artifacts

- `tools/vscode-chat-executor/node_modules/`
- `tools/vscode-chat-executor/out/`
- compiled JS maps and generated build output

### Side threads

- alternative routing experiments that do not change the product
- duplicate command plans
- UI-only narrative flows that do not produce real execution evidence

## Working rule

If a file does not either:

1. ship the product,
2. guard the product with a meaningful regression test,
3. or explain the product to the operator,

then it does not belong in the final PR240 scope.
