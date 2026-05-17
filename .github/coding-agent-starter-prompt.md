# Coding Agent Starter Prompt (Scoped + MCP + Hard Gate)

Use this prompt when assigning coding tasks to GitHub Coding Agent:

```text
Implement the change end-to-end in one focused run.

Execution contract:
1) Preflight first: identify branch, PR/task source of truth, in-scope files, out-of-scope files.
2) Build and follow a minimal implementation slice; avoid broad re-exploration once coding starts.
3) Prefer targeted tests before full gate.
4) Finish only after required gate is green (unless confirmed environment blocker).

Context and token discipline:
1) Keep prompts and reports compact; no raw log dumps.
2) For OpenAI/Codex product questions, use official docs through Docs MCP first.
3) Do not copy long external documentation into chat; summarize only decision-relevant facts.
4) Use repository source-of-truth files and scoped retrieval instead of full repository scanning.

Editing/output contract:
1) Return concrete file edits and concise rationale.
2) Prefer Search/Replace or unified diff style where practical.
3) Do not regenerate unchanged code blocks.

Quality contract:
1) If frontend scope exists, run `npm --prefix web-next ci` before frontend tests.
2) When adding tests: register in `config/testing/test_catalog.json`, run `make test-groups-sync`, verify entry in `config/pytest-groups/sonar-new-code.txt`.
3) Avoid slow-pattern tokens in new test names/paths (`benchmark`, `integration`) for changed-code coverage selection.
4) Required completion gate:
   - `make pr-fast`
5) Exception:
   - If all changed files are `*.md`, you may skip `make pr-fast`.

Failure handling:
1) If the same gate fails twice with no code/environment change, stop and report blocker.
2) Never infer success from truncated logs; validate exit code.
3) If output is piped, use `set -o pipefail` and check `PIPESTATUS[0]`.

Final report must include:
1) Commands executed.
2) Pass/fail per command.
3) Changed-lines coverage (or `N/A` for markdown-only changes).
4) Known risks/skips with explicit justification.
```
