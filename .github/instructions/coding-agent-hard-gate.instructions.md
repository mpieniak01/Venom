---
applyTo: "**"
---

# Coding Agent Hard Gate (Repository Instruction)

Before declaring task completion, always run:

1. `make pr-fast`

If any command fails:

1. fix the issue,
2. rerun until it passes or there is a confirmed environment blocker.

Final completion summary (and PR description) must include:

1. executed validation commands,
2. pass/fail for each command,
3. changed-lines coverage percentage,
4. known skips/risks with explicit justification.

Never mark work as done with failing required quality gates.
