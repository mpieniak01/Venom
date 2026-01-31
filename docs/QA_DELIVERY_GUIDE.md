# Guide: QA & Delivery Layer

## Overview

Venom v1.0 includes a complete QA & Delivery layer that closes the software lifecycle. It covers:

1. **E2E Testing** - End‑to‑end tests for web apps
2. **Documentation Generation** - Automated docs generation
3. **Release Management** - Releases and changelog management

---

## 1. E2E Testing (End-to-End)

### BrowserSkill

Skill for browser interaction (headless Chromium via Playwright).

**Basic operations:**

```python
from venom_core.execution.skills.browser_skill import BrowserSkill

browser = BrowserSkill()

# Visit page
await browser.visit_page("http://localhost:3000")

# Click a button
await browser.click_element("#login-button")

# Fill a form
await browser.fill_form("#username", "user@example.com")
await browser.fill_form("#password", "secretpass")

# Take screenshot
await browser.take_screenshot("login-page.png")

# Get text
text = await browser.get_text_content(".welcome-message")

# Close browser
await browser.close_browser()
```

### TesterAgent

QA agent executing E2E tests.

**Via Orchestrator:**

```python
# Venom auto-detects E2E_TESTING intent
response = await orchestrator.process_task(
    "Test the login form on http://localhost:3000"
)
```

**Direct usage:**

```python
from venom_core.agents.tester import TesterAgent
from venom_core.execution.kernel_builder import KernelBuilder

kernel = KernelBuilder().build_kernel()
tester = TesterAgent(kernel)

# Test with LLM (agent writes scenario)
result = await tester.process(
    "Test localhost:3000 - check if the 'Login' button works"
)

# Test with defined scenario
scenario = [
    {"action": "visit", "url": "http://localhost:3000"},
    {"action": "wait", "selector": "#app"},
    {"action": "click", "selector": ".menu-button"},
    {"action": "verify_text", "selector": ".title", "expected": "Dashboard"},
    {"action": "screenshot", "filename": "dashboard.png"},
]

result = await tester.run_e2e_scenario("http://localhost:3000", scenario)
```

**Visual verification support:**

TesterAgent can analyze screenshots using Eyes (Vision AI), if available:

```python
# Screenshot will be analyzed by GPT-4o or a local vision model
await tester.process(
    "Check if the login page looks correct - take a screenshot and describe it"
)
```

---

## 2. Documentation Generation

### DocsSkill

Skill to build documentation from Markdown using MkDocs.

**Basic operations:**

```python
from venom_core.execution.skills.docs_skill import DocsSkill

docs = DocsSkill()

# Check docs/ structure
structure = await docs.check_docs_structure()
print(structure)

# Generate mkdocs.yml
config = await docs.generate_mkdocs_config(
    site_name="My Project",
    theme="material",
    repo_url="https://github.com/user/project"
)

# Build HTML site
result = await docs.build_docs_site(clean=True)
# Site available at: workspace/site/index.html
```

### PublisherAgent

Agent managing documentation publication.

**Via Orchestrator:**

```python
# Venom auto-detects DOCUMENTATION intent
response = await orchestrator.process_task(
    "Generate documentation for project MyApp"
)
```

**Direct usage:**

```python
from venom_core.agents.publisher import PublisherAgent
from venom_core.execution.kernel_builder import KernelBuilder

kernel = KernelBuilder().build_kernel()
publisher = PublisherAgent(kernel)

# Quick publish
result = await publisher.quick_publish(
    project_name="MyApp",
    theme="material"
)

# Or via LLM (agent decides)
result = await publisher.process(
    "Generate professional documentation from docs/"
)
```

**Directory structure:**

```
workspace/
├── docs/                  # Markdown sources
│   ├── index.md          # Homepage (required)
│   ├── guide.md
│   ├── api/
│   │   └── reference.md
│   └── examples/
│       └── tutorial.md
├── mkdocs.yml            # Config (generated)
└── site/                 # HTML output
    ├── index.html
    ├── guide/
    ├── api/
    └── assets/
```

**Theme customization:**

Generated `mkdocs.yml` includes:
- Material theme with features (navigation.tabs, search, toc)
- Markdown extensions (code highlighting, admonitions)
- Auto navigation from directory structure

---

## 3. Release Management

### ReleaseManagerAgent

Agent for versioning and changelog management.

**Via Orchestrator:**

```python
# Venom auto-detects RELEASE_PROJECT intent
response = await orchestrator.process_task(
    "Release a new version - generate changelog from recent commits"
)
```

**Direct usage:**

```python
from venom_core.agents.release_manager import ReleaseManagerAgent
from venom_core.execution.kernel_builder import KernelBuilder

kernel = KernelBuilder().build_kernel()
release_mgr = ReleaseManagerAgent(kernel)

# Auto-detect release type (major/minor/patch)
result = await release_mgr.prepare_release(
    version_type="auto",
    commit_count=20
)

# Or set type manually
result = await release_mgr.prepare_release(
    version_type="minor",  # feat release
    commit_count=50
)
```

**Conventional Commits:**

ReleaseManager recognizes commit types:
- `feat:` → increments MINOR (0.1.0)
- `fix:` → increments PATCH (0.0.1)
- `feat!:` or `BREAKING CHANGE:` → increments MAJOR (1.0.0)
- `docs:`, `chore:`, `refactor:` → no version impact

**CHANGELOG format:**

```markdown
# Changelog

## [Unreleased] - 2024-12-07

### Breaking Changes
- feat!: API endpoint /users change (abc1234)

### Features
- feat(auth): added OAuth login (def5678)
- feat: new admin dashboard (ghi9012)

### Bug Fixes
- fix: cache issue fixed (jkl3456)
- fix(api): form validation corrected (mno7890)

### Other Changes
- docs: README updated (pqr1234)
- chore: dependency upgrades (stu5678)
```

**Workflow after preparing a release:**

```bash
# 1. Review generated CHANGELOG.md
cat CHANGELOG.md

# 2. Update version in files (package.json, pyproject.toml, etc.)
# e.g. change 1.0.0 to 1.1.0

# 3. Commit
git add CHANGELOG.md package.json
git commit -m "chore: prepare release v1.1.0"

# 4. Tag
git tag v1.1.0

# 5. Push
git push && git push --tags
```

---

## 4. Orchestrator Integration

New intents are auto-detected by IntentManager.

**Example prompts:**

```python
# E2E Testing
await orchestrator.process_task(
    "Test the contact form on localhost:8080"
)

# Documentation
await orchestrator.process_task(
    "Generate documentation for MyAPI"
)

# Release
await orchestrator.process_task(
    "Prepare a release - generate changelog from last 30 commits"
)
```

---

## 5. Installation & Configuration

### Required dependencies:

```bash
pip install playwright mkdocs mkdocs-material
playwright install chromium
```

### Optional configuration:

**Eyes (Vision AI) for screenshot analysis:**
- Requires `OPENAI_API_KEY` in `.env` for GPT-4o
- Or local vision model in Ollama (llava, moondream)

**MkDocs Material (themes):**
- Default theme: `material`
- Alternative: `readthedocs`

---

## 6. Best Practices

### E2E Testing:
1. Always start the app before tests (localhost:PORT)
2. Use waits (`wait_for_element`) on dynamic pages
3. Take screenshots at key points for debugging
4. Close the browser after each test

### Documentation:
1. Keep `docs/index.md` as the homepage
2. Use sensible filenames (snake_case or kebab-case)
3. Group topics into subfolders (api/, guide/, examples/)
4. Build docs regularly to catch broken links

### Release:
1. Use Conventional Commits
2. Run `prepare_release` before each release
3. Review generated CHANGELOG before committing
4. Tag versions with SemVer (vMAJOR.MINOR.PATCH)

---

## 7. Example Full Workflow

```python
# 1. Build the app (e.g., CoderAgent)
await orchestrator.process_task("Create a Todo app with FastAPI")

# 2. Run E2E tests
await orchestrator.process_task(
    "Test Todo app - add task and verify it is visible"
)

# 3. Generate documentation
await orchestrator.process_task("Generate API documentation for Todo app")

# 4. Prepare release
await orchestrator.process_task("Release version 1.0.0 for Todo app")

# Done! You now have:
# - Working app
# - E2E tests with reports
# - HTML documentation
# - CHANGELOG and release tag
```

---

## Troubleshooting

**Playwright not working:**
```bash
# Install browsers
playwright install chromium

# In Docker/CI add system deps
apt-get install -y libnss3 libatk-bridge2.0-0
```

**MkDocs build fails:**
```bash
# Check installation
mkdocs --version

# Install with theme
pip install mkdocs mkdocs-material
```

**Eyes does not analyze screenshots:**
- Set `OPENAI_API_KEY` in `.env` for GPT-4o
- Or run local model: `ollama run llava`

---

## Resources

- [Playwright Docs](https://playwright.dev/python/)
- [MkDocs Guide](https://www.mkdocs.org/)
- [Material Theme](https://squidfunk.github.io/mkdocs-material/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)
