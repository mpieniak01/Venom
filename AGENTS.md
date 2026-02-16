# AGENTS Entry Point

To avoid confusion between coding-agent instructions and the runtime agent catalog:

- English coding-agent instructions: [docs/AGENTS.md](docs/AGENTS.md)
- Polish coding-agent instructions: [docs/PL/AGENTS.md](docs/PL/AGENTS.md)
- Runtime agent catalog (EN): [docs/SYSTEM_AGENTS_CATALOG.md](docs/SYSTEM_AGENTS_CATALOG.md)
- Katalog agentów systemu (PL): [docs/PL/SYSTEM_AGENTS_CATALOG.md](docs/PL/SYSTEM_AGENTS_CATALOG.md)

## Hard Gate (Coding Agent)

For all coding-agent tasks in this repository:

1. Required before task completion:
   - `make pr-fast`
   - `make check-new-code-coverage`
2. If any gate fails:
   - do not mark the task as done,
   - fix issues and rerun both gates until green or a confirmed environment blocker.
3. Final report in PR/summary must include:
   - executed commands,
   - pass/fail status,
   - changed-lines coverage percentage,
   - known risks/skips with justification.

## Documentation-Only Fast Path (Exception)

For tasks where **all changed files** are documentation-only, hard gates can be skipped.

Allowed doc-only scope:
- `docs/**`
- `docs_dev/**`
- `README.md`
- `README_PL.md`
- other `*.md` files in repository root

Rules:
1. If the change touches code/config/build/test/runtime files outside doc-only scope, full hard-gate policy applies.
2. For doc-only scope, do not run `make pr-fast` / `make check-new-code-coverage`.
3. In final summary, explicitly state: "doc-only change, hard gates skipped by policy".

Canonical process details:
- [docs/AGENTS.md](docs/AGENTS.md)
- [.github/copilot-instructions.md](.github/copilot-instructions.md)
