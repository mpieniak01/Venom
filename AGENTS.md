# AGENTS Entry Point

To avoid confusion between coding-agent instructions and the runtime agent catalog:

- English coding-agent instructions: [docs/AGENTS.md](docs/AGENTS.md)
- Polish coding-agent instructions: [docs/PL/AGENTS.md](docs/PL/AGENTS.md)
- Runtime agent catalog (EN): [docs/SYSTEM_AGENTS_CATALOG.md](docs/SYSTEM_AGENTS_CATALOG.md)
- Katalog agentów systemu (PL): [docs/PL/SYSTEM_AGENTS_CATALOG.md](docs/PL/SYSTEM_AGENTS_CATALOG.md)

## Hard Gate (Coding Agent)

Use `docs/AGENTS.md` as the canonical ruleset. This file is intentionally short.

Minimal contract:
1. Before completion, run `make pr-fast`.
2. If gate fails, fix and rerun until green (or confirmed environment blocker path from `docs/AGENTS.md`).
3. For markdown-only changes (all changed files are `*.md`, regardless of directory) hard gates may be skipped.
4. Final report must include commands run, pass/fail, changed-lines coverage (from `pr-fast` output), and known risks/skips.

Canonical process details:
- [docs/AGENTS.md](docs/AGENTS.md)
- [.github/copilot-instructions.md](.github/copilot-instructions.md)
