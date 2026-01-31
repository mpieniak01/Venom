# Contributing to Venom 🧬

Thank you for wanting to help develop the project! Below you'll find guidelines, tips, and instructions on how you can get involved.

## Table of Contents

- [How to report bugs / feature requests](#how-to-report-bugs-or-request-features)
- [How to propose changes / code](#how-to-contribute-code)
- [Code style and commit messages](#code-style-and-commit-messages)
- [Tests and CI](#tests-and-ci)
- [Code of conduct and ethics](#code-of-conduct)
- [Contact / questions](#contact)

---

## How to report bugs or request features

- Check if a similar issue already exists.
- If not — open a new issue, providing:
  - reproduction steps description (if it's a bug),
  - Python version and system,
  - optionally stack trace / logs,
  - expected result vs. actual result.

---

## How to contribute code

1. Fork the repo → create a `feat/`, `fix/`, or `chore/` branch.
2. Make changes, run `make lint && make test` (or locally `pre-commit run --all-files && pytest`).
3. Add tests / documentation if you're changing API / logic.
4. Use standard commit messages (see below).
5. Create PR — if everything passes, we'll merge to `main`.

---

## Code style and commit messages

- Python code: **PEP-8 / Black + Ruff + isort**.
- Before committing, run `pre-commit install`.
- Commit message:
  - format: `type(scope): short description` (e.g., `feat(core): add orchestrator`)
  - types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`.
  - first line ≤ 50 characters, then blank line, then details.

---

## Tests and CI

- All newly added functionality must have tests (pytest).
- Tests go into the `/tests` directory.
- CI will check: lint → tests → format → coverage report.

---

## Code of Conduct

All contributors commit to **respect, courtesy, and constructive collaboration**.
We don't tolerate: hate, insults, harassment, spamming.
If something concerns you — open an issue or contact directly.

---

## Contact

Author / Maintainer: **Mac_** (mpieniak01)
Email / contact on GitHub – through Issues / Discussions.

Thanks for contributing — every PR and idea helps develop Venom!
