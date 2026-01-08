# Contributing to Venom 🧬

Thank you for wanting to help develop the project! Below you'll find rules, tips, and instructions on how you can get involved.

## Table of Contents

- [How to Report Bugs or Request Features](#how-to-report-bugs-or-request-features)
- [How to Contribute Code](#how-to-contribute-code)
- [Code Style and Commit Messages](#code-style-and-commit-messages)
- [Tests and CI](#tests-and-ci)
- [Code of Conduct](#code-of-conduct)
- [Contact / Questions](#contact)

---

## How to Report Bugs or Request Features

- Check if a similar issue already exists.
- If not — open a new issue, providing:
  - step-by-step reproduction (if it's a bug),
  - Python version and system,
  - optionally stack trace / logs,
  - expected result vs. actual result.

---

## How to Contribute Code

1. Fork the repo → create a branch `feat/`, `fix/`, or `chore/`.
2. Make changes, run `make lint && make test` (or locally `pre-commit run --all-files && pytest`).
3. Add tests / documentation if changing API / logic.
4. Use standard commit messages (see below).
5. Create a PR — if everything passes, we'll merge to `main`.

---

## Code Style and Commit Messages

- Python code: **PEP-8 / Black + Ruff + isort**.
- Before committing, run `pre-commit install`.
- Commit message:
  - format: `type(scope): short description` (e.g., `feat(core): add orchestrator`)
  - types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`.
  - first line ≤ 50 characters, then blank line, then details.

### Commit Message Examples

```
feat(agents): add ResearcherAgent with web search
fix(memory): resolve LanceDB connection timeout
docs(readme): update installation instructions
test(orchestrator): add integration tests for task routing
refactor(skills): simplify WebSearchSkill error handling
chore(deps): update semantic-kernel to v1.10.0
```

---

## Tests and CI

- All newly added functionality must have tests (pytest).
- We put tests in the `/tests` directory.
- CI will check: lint → tests → format → coverage report.

### Running Tests Locally

```bash
# All tests
pytest

# Specific test file
pytest tests/test_researcher_agent.py

# With coverage
pytest --cov=venom_core --cov-report=html

# Only fast tests (skip slow integration tests)
pytest -m "not slow"
```

### Test Guidelines

- Write clear test names: `test_researcher_finds_python_libraries`
- Use fixtures for common setup
- Mock external services (web requests, LLM calls)
- Keep tests fast and isolated
- Aim for >80% code coverage on new code

---

## Code of Conduct

All contributors commit to **respect, courtesy, and constructive collaboration**.
We do not tolerate: hate, insults, harassment, spamming.
If something concerns you — open an issue or contact directly.

### Expected Behavior

- Be respectful and inclusive
- Provide constructive feedback
- Accept constructive criticism gracefully
- Focus on what is best for the community
- Show empathy towards other community members

### Unacceptable Behavior

- Harassment, discrimination, or offensive comments
- Trolling, insulting/derogatory comments, or personal attacks
- Public or private harassment
- Publishing others' private information without permission
- Other conduct which could reasonably be considered inappropriate

---

## Development Setup

### Prerequisites

- Python 3.10+ (recommended 3.11)
- Git
- Optional: Docker (for integration tests)

### Setup Steps

```bash
# 1. Clone your fork
git clone https://github.com/YOUR_USERNAME/Venom.git
cd Venom

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install pre-commit hooks
pip install pre-commit
pre-commit install

# 5. Copy environment file
cp .env.example .env
# Edit .env with your settings

# 6. Run tests to verify setup
pytest
```

### Development Workflow

```bash
# 1. Create feature branch
git checkout -b feat/my-new-feature

# 2. Make changes
# ... edit files ...

# 3. Run linters
make lint
# or manually:
ruff check . --fix
ruff format .
isort . --profile black

# 4. Run tests
make test
# or manually:
pytest

# 5. Commit changes
git add .
git commit -m "feat(scope): description of changes"

# 6. Push to your fork
git push origin feat/my-new-feature

# 7. Open Pull Request on GitHub
```

---

## Project Structure

Understanding the project structure helps you navigate the codebase:

```
venom_core/
├── agents/              # AI agents (Researcher, Coder, etc.)
├── api/routes/          # FastAPI endpoints
├── core/flows/          # Business logic and orchestration
├── execution/           # Model routing and skills
│   └── skills/          # Executable skills (WebSearch, GitHub, etc.)
├── memory/              # Long-term memory (LanceDB)
├── ops/                 # Operations (CostGuard, WorkLedger)
└── infrastructure/      # Infrastructure services

tests/
├── test_agents/         # Agent tests
├── test_skills/         # Skill tests
├── test_integration/    # Integration tests
└── perf/                # Performance tests

docs/
├── THE_*.md             # Agent documentation
└── *_GUIDE.md           # Feature guides

web-next/                # Next.js frontend
```

---

## Areas for Contribution

### 🐛 Bug Fixes
Look for issues labeled `bug` or `good first issue`

### ✨ New Features
- New agents
- New skills
- Integrations with external services
- UI improvements

### 📖 Documentation
- Improve existing docs
- Add examples
- Translate documentation
- Create tutorials

### 🧪 Testing
- Increase test coverage
- Add integration tests
- Performance benchmarks
- Load testing

### 🎨 Frontend
- UI/UX improvements in web-next
- New dashboard components
- Accessibility improvements

---

## Pull Request Process

1. **Before Creating PR**:
   - Ensure all tests pass
   - Update documentation if needed
   - Add entry to CHANGELOG.md (if exists)
   - Rebase on latest main

2. **PR Description Should Include**:
   - What changes were made and why
   - How to test the changes
   - Screenshots (for UI changes)
   - Related issue numbers

3. **Review Process**:
   - Maintainers will review your PR
   - Address any feedback or requested changes
   - Once approved, PR will be merged

4. **After Merge**:
   - Delete your feature branch
   - Pull latest main
   - Celebrate! 🎉

---

## Getting Help

### Questions?
- Check existing documentation in `/docs`
- Search existing issues
- Ask in GitHub Discussions
- Open a new issue with `question` label

### Found a Bug?
- Check if it's already reported
- Open a new issue with detailed reproduction steps
- Include logs, error messages, and environment details

### Want to Add a Feature?
- Open an issue to discuss first (for large features)
- Get feedback from maintainers
- Then create your PR

---

## Recognition

Contributors will be:
- Listed in GitHub contributors page
- Mentioned in release notes (for significant contributions)
- Thanked publicly in project documentation

---

## Contact

**Author / Maintainer:** Mac_ (mpieniak01)
Email / Contact via GitHub – through Issues / Discussions.

Thanks for contributing — every PR and idea helps develop Venom!

---

## License

By contributing to Venom, you agree that your contributions will be licensed under the same license as the project.

---

**Happy Contributing! 🐍**
