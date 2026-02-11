# Coding Agent Hooks

This directory contains optional GitHub Coding Agent hooks.

- Config: `.github/hooks/hard-gate.json`
- Commands:
  - `scripts/agent_hard_gate.sh`
  - `scripts/agent_pr_summary_hint.sh`

## Purpose

1. Enforce hard quality gates at session end.
2. Remind the agent to include the PR validation report format.

## Notes

- Hooks are an additional enforcement layer.
- Primary enforcement still comes from repository instructions and required CI checks.
- Access/MCP governance:
  - `.github/CODING_AGENT_ACCESS_MANAGEMENT.md`
  - `.github/CODING_AGENT_MCP_POLICY.md`
