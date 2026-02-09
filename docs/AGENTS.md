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

## CI Stack Awareness Rule

- Before adding/updating tests for CI-lite, verify which dependencies and tools are available in the CI-lite stack.
- Use `requirements-ci-lite.txt`, `config/pytest-groups/ci-lite.txt`, and `scripts/audit_lite_deps.py` as the source of truth.
- If a test needs an optional dependency that is not guaranteed in CI-lite, use `pytest.importorskip(...)` or move that test out of the lite lane.

## Quality and Security Toolchain (Project Standard)

- **SonarCloud (PR gate):** mandatory pull request analysis for bugs, vulnerabilities, code smells, duplications, and maintainability.
- **Snyk (periodic scan):** recurring dependency and container security scans for newly disclosed CVEs.
- **CI Lite:** fast PR checks (lint + selected unit tests).
- **pre-commit:** local hooks expected before push.
- **Local static checks:** `ruff`, `mypy venom_core`.
- **Local tests:** `pytest` (targeted suites at minimum for changed modules).

Recommended local command sequence:

```bash
pre-commit run --all-files
ruff check . --fix
ruff format .
mypy venom_core
pytest -q
```

## Canonical Reference

- Source of truth for quality/security gates: `README.md` section **"Quality and Security Gates"**.

## Architecture References

- System vision: `docs/VENOM_MASTER_VISION_V1.md`
- Backend architecture: `docs/BACKEND_ARCHITECTURE.md`
- Repository tree / directories map: `docs/TREE.md`

## Documentation Rule

- Functional catalog of Venom runtime agents belongs in `SYSTEM_AGENTS_CATALOG.md`.
- Implementation/process instructions for coding agents belong in this file.
