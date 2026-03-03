# Coding Agent Starter Prompt (Hard Gate, 1h Mode)

Use this prompt when assigning coding tasks to GitHub Coding Agent:

```text
Implement the change end-to-end in one focused session.

Mandatory 1h checkpoints:
1) 0-5 min: preflight only (target files, env/tools, no deep re-exploration).
   - If frontend scope exists: run `npm --prefix web-next ci` before frontend tests.
2) 5-25 min: implement minimal end-to-end slice.
3) <=30 min: create first commit (WIP allowed).
4) 30-50 min: finish scope + run targeted tests.
5) 50-60 min: run make pr-fast and finalize.

Hard rules:
- Do not restart repository exploration after implementation started.
- Max one sub-agent invocation per phase (explore/implement/verify).
- If no code change appears within 15 minutes: stop and report blocker.
- If the same gate fails twice without code/environment changes: stop and report blocker.
- Do not run extra heavy checks before make pr-fast is green.
- When adding tests: register them in `config/testing/test_catalog.json`, run `make test-groups-sync`, and verify they are present in `config/pytest-groups/sonar-new-code.txt`.
- Avoid slow-pattern tokens in new test filenames/paths for changed-code coverage selection (notably `benchmark`, `integration`).

Required gate before completion:
1) make pr-fast

Exception:
- If all changed files are `*.md`, you may skip `make pr-fast`.

If gate fails, fix and rerun until green (or report confirmed environment blocker).
Never infer green status from tail/grep snippets alone; verify command exit code.
If output is piped, use `set -o pipefail` and validate `PIPESTATUS[0]`.

Final summary must include:
- commands run,
- pass/fail per command,
- changed-lines coverage (or `N/A` for markdown-only change sets),
- known risks/skips with justification.

Stop condition:
- after first confirmed green make pr-fast + final report.
```
