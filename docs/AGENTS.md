# Coding Agents Guidelines (EN)

This file contains **instructions for coding agents** working in this repository.

If you are looking for the list of Venom system agents, use:
- [SYSTEM_AGENTS_CATALOG.md](SYSTEM_AGENTS_CATALOG.md)

## Core Rules

- Keep changes small, testable, and easy to review.
- Maintain typing quality (`mypy venom_core` should pass).
- Keep security checks green (Sonar/Snyk findings should be addressed, not ignored).
- Avoid dead code and placeholder branches.
- Make error paths explicit and covered by tests where practical.

## Required Validation Before PR

- Run fast checks first (lint + targeted tests).
- Run relevant `pytest` groups for touched modules.
- Confirm no new critical/high security findings.

## Documentation Rule

- Functional catalog of Venom runtime agents belongs in `SYSTEM_AGENTS_CATALOG.md`.
- Implementation/process instructions for coding agents belong in this file.
