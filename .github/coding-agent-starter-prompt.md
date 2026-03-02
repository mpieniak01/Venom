# Coding Agent Starter Prompt (Hard Gate)

Use this prompt when assigning coding tasks to GitHub Coding Agent:

```text
Implement the change end-to-end.
Before completion, run:
1) make pr-fast

Exception:
- If all changed files are `*.md`, you may skip `make pr-fast`.

If gate fails, fix and rerun until green.
If a test hangs/timeouts, treat it as a bug to fix (not a rerun-until-green loop).

Execution policy:
- Run heavy checks (CodeQL/code_review) only once at the end.
- During fix loops, run only targeted tests + `make pr-fast` (you may use `make agent-pr-fast` as a helper wrapper if available).
- Invoke a sub-agent task only once per phase; re-invoke only with explicit new reason.
- Do not restart from repository exploration after implementation already started.
- Do not run `make pr-fast` repeatedly without any code or environment change.
- Never infer green status from `grep`/`tail` snippets alone; verify command exit code.
- If output is truncated, inspect the full log file before deciding pass/fail.
- If CodeQL times out once in this session, do not rerun it; record environment blocker and continue with required hard gates.
- Keep a time reserve: when less than 10 minutes remain, skip non-blocking checks and finalize.

In the final summary include:
- commands run,
- pass/fail result per command,
- changed-lines coverage (or `N/A` for markdown-only change sets),
- known risks/skips with justification.
Do not mark task done with red gates.

Stop condition:
- After first confirmed green `make pr-fast` and final report generation, stop.
- Do not trigger additional `task` delegation or duplicate final reports.
```
