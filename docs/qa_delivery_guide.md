# Przewodnik: Warstwa QA & Delivery

## Przegląd

Venom v2 zawiera kompletną warstwę jakości i dostarczania (QA & Delivery), która domyka cykl życia oprogramowania. Obejmuje:

1. **E2E Testing** - Testy end-to-end aplikacji webowych
2. **Documentation Generation** - Automatyczne generowanie dokumentacji
3. **Release Management** - Zarządzanie wydaniami i changelog

---

## 1. Testowanie E2E (End-to-End)

### BrowserSkill

Umiejętność pozwalająca na interakcję z przeglądarką (headless Chromium via Playwright).

**Podstawowe operacje:**

```python
from venom_core.execution.skills.browser_skill import BrowserSkill

browser = BrowserSkill()

# Odwiedź stronę
await browser.visit_page("http://localhost:3000")

# Kliknij przycisk
await browser.click_element("#login-button")

# Wypełnij formularz
await browser.fill_form("#username", "user@example.com")
await browser.fill_form("#password", "secretpass")

# Zrób screenshot
await browser.take_screenshot("login-page.png")

# Pobierz tekst
text = await browser.get_text_content(".welcome-message")

# Zamknij przeglądarkę
await browser.close_browser()
```

### TesterAgent

Agent QA wykonujący testy E2E.

**Użycie przez Orchestrator:**

```python
# Venom automatycznie wykryje intencję E2E_TESTING
response = await orchestrator.process_task(
    "Przetestuj formularz logowania na http://localhost:3000"
)
```

**Bezpośrednie użycie:**

```python
from venom_core.agents.tester import TesterAgent
from venom_core.execution.kernel_builder import KernelBuilder

kernel = KernelBuilder().build_kernel()
tester = TesterAgent(kernel)

# Test z LLM (agent sam pisze scenariusz)
result = await tester.process(
    "Przetestuj stronę localhost:3000 - sprawdź czy przycisk 'Login' działa"
)

# Test ze zdefiniowanym scenariuszem
scenario = [
    {"action": "visit", "url": "http://localhost:3000"},
    {"action": "wait", "selector": "#app"},
    {"action": "click", "selector": ".menu-button"},
    {"action": "verify_text", "selector": ".title", "expected": "Dashboard"},
    {"action": "screenshot", "filename": "dashboard.png"},
]

result = await tester.run_e2e_scenario("http://localhost:3000", scenario)
```

**Wsparcie dla weryfikacji wizualnej:**

TesterAgent automatycznie analizuje screenshoty za pomocą Eyes (Vision AI), jeśli są dostępne:

```python
# Screenshot zostanie przeanalizowany przez GPT-4o lub lokalny model vision
await tester.process(
    "Sprawdź czy strona logowania wygląda poprawnie - zrób screenshot i opisz co widzisz"
)
```

---

## 2. Generowanie Dokumentacji

### DocsSkill

Umiejętność do tworzenia dokumentacji z Markdown przy użyciu MkDocs.

**Podstawowe operacje:**

```python
from venom_core.execution.skills.docs_skill import DocsSkill

docs = DocsSkill()

# Sprawdź strukturę docs/
structure = await docs.check_docs_structure()
print(structure)

# Wygeneruj mkdocs.yml
config = await docs.generate_mkdocs_config(
    site_name="My Project",
    theme="material",
    repo_url="https://github.com/user/project"
)

# Zbuduj stronę HTML
result = await docs.build_docs_site(clean=True)
# Strona dostępna w: workspace/site/index.html
```

### PublisherAgent

Agent zarządzający publikacją dokumentacji.

**Użycie przez Orchestrator:**

```python
# Venom automatycznie wykryje intencję DOCUMENTATION
response = await orchestrator.process_task(
    "Wygeneruj dokumentację projektu MyApp"
)
```

**Bezpośrednie użycie:**

```python
from venom_core.agents.publisher import PublisherAgent
from venom_core.execution.kernel_builder import KernelBuilder

kernel = KernelBuilder().build_kernel()
publisher = PublisherAgent(kernel)

# Szybka publikacja
result = await publisher.quick_publish(
    project_name="MyApp",
    theme="material"
)

# Lub z LLM (agent sam podejmuje decyzje)
result = await publisher.process(
    "Wygeneruj profesjonalną dokumentację z plików w docs/"
)
```

**Struktura katalogów:**

```
workspace/
├── docs/                  # Pliki Markdown (źródło)
│   ├── index.md          # Strona główna (wymagana)
│   ├── guide.md
│   ├── api/
│   │   └── reference.md
│   └── examples/
│       └── tutorial.md
├── mkdocs.yml            # Konfiguracja (generowana)
└── site/                 # Strona HTML (output)
    ├── index.html
    ├── guide/
    ├── api/
    └── assets/
```

**Customizacja motywu:**

Wygenerowany `mkdocs.yml` zawiera:
- Motyw Material z features (navigation.tabs, search, toc)
- Markdown extensions (code highlighting, admonitions)
- Automatyczna nawigacja z struktury katalogów

---

## 3. Zarządzanie Release'ami

### ReleaseManagerAgent

Agent do zarządzania wersjonowaniem i changelog.

**Użycie przez Orchestrator:**

```python
# Venom automatycznie wykryje intencję RELEASE_PROJECT
response = await orchestrator.process_task(
    "Wydaj nową wersję - wygeneruj changelog z ostatnich commitów"
)
```

**Bezpośrednie użycie:**

```python
from venom_core.agents.release_manager import ReleaseManagerAgent
from venom_core.execution.kernel_builder import KernelBuilder

kernel = KernelBuilder().build_kernel()
release_mgr = ReleaseManagerAgent(kernel)

# Automatyczne wykrycie typu release'u (major/minor/patch)
result = await release_mgr.prepare_release(
    version_type="auto",
    commit_count=20
)

# Lub ręczne określenie typu
result = await release_mgr.prepare_release(
    version_type="minor",  # feat release
    commit_count=50
)
```

**Conventional Commits:**

ReleaseManager rozpoznaje typy commitów:
- `feat:` → zwiększa MINOR (0.1.0)
- `fix:` → zwiększa PATCH (0.0.1)
- `feat!:` lub `BREAKING CHANGE:` → zwiększa MAJOR (1.0.0)
- `docs:`, `chore:`, `refactor:` → nie wpływa na wersję

**Format CHANGELOG:**

```markdown
# Changelog

## [Unreleased] - 2024-12-07

### Breaking Changes
- feat!: zmiana API endpointu /users (abc1234)

### Features
- feat(auth): dodano logowanie przez OAuth (def5678)
- feat: nowy dashboard administratora (ghi9012)

### Bug Fixes
- fix: naprawiono problem z cache (jkl3456)
- fix(api): poprawiono walidację formularzy (mno7890)

### Other Changes
- docs: zaktualizowano README (pqr1234)
- chore: upgrade dependencies (stu5678)
```

**Workflow po przygotowaniu release'u:**

```bash
# 1. Sprawdź wygenerowany CHANGELOG.md
cat CHANGELOG.md

# 2. Zaktualizuj wersję w plikach (package.json, pyproject.toml, etc.)
# np. zmień z 1.0.0 na 1.1.0

# 3. Commitnij
git add CHANGELOG.md package.json
git commit -m "chore: prepare release v1.1.0"

# 4. Utwórz tag
git tag v1.1.0

# 5. Wypchnij
git push && git push --tags
```

---

## 4. Integracja z Orchestrator

Nowe intencje są automatycznie wykrywane przez IntentManager.

**Przykłady zapytań:**

```python
# E2E Testing
await orchestrator.process_task(
    "Przetestuj formularz kontaktowy na localhost:8080"
)

# Documentation
await orchestrator.process_task(
    "Wygeneruj dokumentację projektu MyAPI"
)

# Release
await orchestrator.process_task(
    "Przygotuj release - wygeneruj changelog z ostatnich 30 commitów"
)
```

---

## 5. Instalacja i Konfiguracja

### Wymagane zależności:

```bash
pip install playwright mkdocs mkdocs-material
playwright install chromium
```

### Opcjonalna konfiguracja:

**Eyes (Vision AI) dla analizy screenshotów:**
- Wymaga OPENAI_API_KEY w `.env` dla GPT-4o
- Lub lokalny model vision w Ollama (llava, moondream)

**MkDocs Material (motywy):**
- Domyślnie używany motyw: `material`
- Alternatywa: `readthedocs`

---

## 6. Best Practices

### Testowanie E2E:
1. Zawsze uruchom aplikację przed testami (localhost:PORT)
2. Używaj oczekiwania na elementy (`wait_for_element`) dla dynamicznych stron
3. Rób screenshoty w kluczowych momentach dla debugowania
4. Zamykaj przeglądarkę po każdym teście

### Dokumentacja:
1. Utrzymuj plik `docs/index.md` jako stronę główną
2. Używaj sensownych nazw plików (snake_case lub kebab-case)
3. Grupuj tematy w podkatalogi (api/, guide/, examples/)
4. Buduj dokumentację regularnie aby sprawdzić broken links

### Release:
1. Stosuj Conventional Commits w swojej pracy
2. Uruchamiaj `prepare_release` przed każdym wydaniem
3. Przeglądaj wygenerowany CHANGELOG przed commitowaniem
4. Taguj wersje zgodnie z SemVer (vMAJOR.MINOR.PATCH)

---

## 7. Przykładowy Pełny Workflow

```python
# 1. Zbuduj aplikację (np. CoderAgent)
await orchestrator.process_task("Stwórz aplikację Todo z FastAPI")

# 2. Przetestuj E2E
await orchestrator.process_task(
    "Przetestuj aplikację Todo - dodaj zadanie i sprawdź czy się wyświetla"
)

# 3. Wygeneruj dokumentację
await orchestrator.process_task("Wygeneruj dokumentację API dla aplikacji Todo")

# 4. Przygotuj release
await orchestrator.process_task("Wydaj wersję 1.0.0 aplikacji Todo")

# Gotowe! Masz:
# - Działającą aplikację
# - Testy E2E z raportami
# - Dokumentację w HTML
# - CHANGELOG i tag release'owy
```

---

## Troubleshooting

**Playwright nie działa:**
```bash
# Zainstaluj przeglądarki
playwright install chromium

# W Docker/CI dodaj zależności systemowe
apt-get install -y libnss3 libatk-bridge2.0-0
```

**MkDocs nie buduje:**
```bash
# Sprawdź czy jest zainstalowany
mkdocs --version

# Zainstaluj z motywem
pip install mkdocs mkdocs-material
```

**Eyes nie analizuje screenshotów:**
- Ustaw `OPENAI_API_KEY` w `.env` dla GPT-4o
- Lub uruchom lokalny model: `ollama run llava`

---

## Zasoby

- [Playwright Docs](https://playwright.dev/python/)
- [MkDocs Guide](https://www.mkdocs.org/)
- [Material Theme](https://squidfunk.github.io/mkdocs-material/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)
