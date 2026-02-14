# Coding Agent Starter Prompt (Hard Gate)

Use this prompt when assigning coding tasks to GitHub Coding Agent:

```text
Implement the change end-to-end.
Before completion, run:
1) make pr-fast
2) make check-new-code-coverage

If any gate fails, fix and rerun both gates until green.
If a test hangs/timeouts, treat it as a bug to fix (not a rerun-until-green loop).

In the final summary include:
- commands run,
- pass/fail result per command,
- changed-lines coverage,
- known risks/skips with justification.
Do not mark task done with red gates.
```
