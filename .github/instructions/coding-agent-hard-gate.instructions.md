---
applyTo: "**"
---

# Coding Agent Hard Gate (Repository Instruction)

Before declaring task completion, always run:

1. `make pr-fast`

Exception:
1. For markdown-only change sets (all changed files end with `.md`), `make pr-fast` may be skipped.

If any command fails:

1. fix the issue,
2. rerun until it passes or there is a confirmed environment blocker.

Final completion summary (and PR description) must include:

1. executed validation commands,
2. pass/fail for each command,
3. changed-lines coverage percentage,
4. known skips/risks with explicit justification.

Never mark work as done with failing required quality gates.

## Execution Guardrails (Mandatory)

1. Do not invoke the same sub-agent in a loop.
2. Re-invoking a sub-agent is allowed only after a real state change:
   - new failing check class,
   - new user requirement,
   - or explicit recovery after tool crash.
3. Do not rerun `make pr-fast` without code or environment change.
4. Do not claim pass/fail from partial logs (`grep`, `head`, `tail`) without validating command exit status.
5. Run heavy optional checks (for example CodeQL/code review tooling) once per session.
6. If optional security tooling times out due to environment, report it as a blocker and do not rerun in the same session.
7. After first confirmed green `make pr-fast` and final report generation, stop execution.
8. Do not produce duplicate final reports or trigger additional implementation loops after completion.
