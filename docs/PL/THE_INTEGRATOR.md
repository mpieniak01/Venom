# THE INTEGRATOR - Git & DevOps Management

## Rola

Integrator Agent to ekspert DevOps i Release Engineer w systemie Venom. Zarządza repozytorium Git, tworzy semantyczne commity, Pull Requesty oraz integruje się z platformami zewnętrznymi (GitHub, Discord, Slack).

## Odpowiedzialności

- **Zarządzanie Git** - Operacje repo (init, checkout, commit, push, pull)
- **Semantic Commits** - Tworzenie commitów zgodnych z Conventional Commits
- **Zarządzanie branchami** - Tworzenie feature branches, merge, checkout
- **Pull Requesty** - Automatyczne tworzenie PR z opisem i labelsami
- **Integracje platformowe** - GitHub Issues, Discord/Slack notifications
- **Release Management** - Tagowanie wersji, CHANGELOG

## Kluczowe Komponenty

### 1. GitSkill (`venom_core/execution/skills/git_skill.py`)

**Dostępne operacje:**
- `init_repo(path, remote_url)` - Inicjalizuj lub klonuj repozytorium
- `checkout(branch, create_new)` - Przełącz branch lub utwórz nowy
- `get_status()` - Sprawdź status zmian (modified, added, deleted)
- `get_diff(staged)` - Zobacz szczegóły zmian
- `add_files(patterns)` - Stage'uj pliki do commita
- `commit(message)` - Utwórz commit
- `push(branch, remote)` - Wypchnij zmiany do remote
- `get_last_commit_log(count)` - Zobacz historię commitów
- `get_current_branch()` - Sprawdź aktualny branch

**Przykład użycia:**
```python
from venom_core.execution.skills.git_skill import GitSkill

git = GitSkill()

# Inicjalizacja repo
git.init_repo("./project", "https://github.com/user/repo.git")

# Nowy feature branch
git.checkout("feature/new-api", create_new=True)

# Status zmian
status = git.get_status()
# → "Modified: app.py, config.py | Added: tests/test_api.py"

# Stage i commit
git.add_files(["app.py", "config.py", "tests/test_api.py"])
git.commit("feat(api): add new REST endpoints")

# Push do remote
git.push("feature/new-api", "origin")
```

### 2. PlatformSkill (`venom_core/execution/skills/platform_skill.py`)

**GitHub Integration:**
- `get_assigned_issues()` - Pobierz Issues przypisane do bota
- `get_issue_details(issue_number)` - Pobierz szczegóły Issue (z komentarzami)
- `create_pull_request(title, body, head, base)` - Utwórz Pull Request
- `comment_on_issue(issue_number, comment)` - Dodaj komentarz do Issue
- `add_labels_to_issue(issue_number, labels)` - Dodaj labels do Issue

**Notifications:**
- `send_notification(message, platform)` - Wyślij powiadomienie (Discord/Slack)

**Przykład użycia:**
```python
from venom_core.execution.skills.platform_skill import PlatformSkill

platform = PlatformSkill()

# Pobierz przypisane Issues
issues = platform.get_assigned_issues()
# → [{"number": 42, "title": "Add login feature", "state": "open"}]

# Stwórz PR
pr = platform.create_pull_request(
    title="feat: Add user authentication",
    body="Implements login/logout with JWT tokens. Closes #42",
    head="feature/auth",
    base="main"
)

# Komentarz na Issue
platform.comment_on_issue(
    issue_number=42,
    comment="✅ PR created: #123. Ready for review!"
)

# Powiadomienie na Discord
platform.send_notification(
    message="🚀 New PR #123: User Authentication",
    platform="discord"
)
```

### 3. Conventional Commits

**Format:**
```
<typ>(<zakres>): <opis>

[opcjonalne ciało]

[opcjonalne stopki]
```

**Typy commitów:**
- `feat` - Nowa funkcjonalność
- `fix` - Naprawa błędu
- `docs` - Zmiany w dokumentacji
- `style` - Formatowanie (bez zmian logiki)
- `refactor` - Refaktoryzacja kodu
- `test` - Dodanie/poprawka testów
- `chore` - Zmiany w buildzie, zależnościach

**Przykłady:**
```bash
feat(git): add GitSkill implementation
fix(docker): resolve permission denied in habitat
docs(readme): update installation instructions
refactor(auth): simplify login logic
test(api): add integration tests for endpoints
chore(deps): update semantic-kernel to 1.9.0
```

## Integracja z Systemem

### Przepływ Wykonania (Issue → PR)

```
GitHub Issue #42: "Add login feature"
        ↓
IntegratorAgent.get_assigned_issues()
        → Issue #42 detected
        ↓
ArchitectAgent.plan_execution(issue_description)
        → Plan: [CODER - implement auth, TESTER - write tests]
        ↓
Git workflow:
  1. checkout("feature/auth-42", create_new=True)
  2. [Wykonanie planu - CODER, TESTER]
  3. add_files(["auth.py", "tests/test_auth.py"])
  4. commit("feat(auth): implement JWT authentication (#42)")
  5. push("feature/auth-42", "origin")
        ↓
PlatformSkill:
  1. create_pull_request(
       title="feat(auth): JWT authentication",
       body="Implements #42. Added login/logout with JWT.",
       head="feature/auth-42",
       base="main"
     )
  2. comment_on_issue(42, "✅ PR #123 created")
  3. send_notification("🚀 PR #123 ready", "discord")
        ↓
Human review & merge
```

### Współpraca z Innymi Agentami

- **ArchitectAgent** - Planuje implementację Issues
- **CoderAgent** - Generuje kod dla feature branch
- **CriticAgent** - Weryfikuje kod przed commitem
- **TesterAgent** - Generuje testy dla PR
- **ReleaseManager** - Tagowanie wersji, CHANGELOG

## Przykłady Użycia

### Przykład 1: Automatyczne Przetwarzanie Issue
```
User: "Sprawdź czy są nowe Issues na GitHubie"

IntegratorAgent:
1. get_assigned_issues()
   → Issue #42: "Add dark mode"
2. get_issue_details(42)
   → Description: "Add dark theme toggle in settings"
3. checkout("feature/dark-mode-42", create_new=True)
4. [Delegacja do ArchitectAgent → CoderAgent]
5. commit("feat(ui): add dark mode toggle (#42)")
6. push("feature/dark-mode-42")
7. create_pull_request(...)
8. comment_on_issue(42, "PR #123 created")
```

### Przykład 2: Release Workflow
```
User: "Stwórz release v1.2.0"

IntegratorAgent:
1. checkout("main")
2. git.tag("v1.2.0", "Release 1.2.0 - Dark mode & auth")
3. git.push("v1.2.0", remote="origin")
4. platform.create_release(
     tag="v1.2.0",
     name="Version 1.2.0",
     body=CHANGELOG_CONTENT
   )
5. send_notification("🎉 v1.2.0 released!", "discord")
```

### Przykład 3: Hotfix Workflow
```
User: "Napraw bug w autentykacji (Issue #55)"

IntegratorAgent:
1. checkout("hotfix/auth-55", create_new=True)
2. [CODER naprawia bug]
3. commit("fix(auth): prevent token expiry race condition (#55)")
4. push("hotfix/auth-55")
5. create_pull_request(
     title="fix(auth): token expiry race condition",
     base="main",
     labels=["hotfix", "priority:high"]
   )
```

## Konfiguracja

```bash
# W .env
# GitHub Integration
GITHUB_TOKEN=ghp_your_personal_access_token
GITHUB_REPO_NAME=username/repo

# Issue Polling (opcjonalne)
ENABLE_ISSUE_POLLING=false
ISSUE_POLLING_INTERVAL_MINUTES=5

# Hugging Face (opcjonalne)
HF_TOKEN=

# Tavily (opcjonalne)
TAVILY_API_KEY=

# Google Calendar (opcjonalne)
ENABLE_GOOGLE_CALENDAR=false
GOOGLE_CALENDAR_CREDENTIALS_PATH=./data/config/google_calendar_credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=./data/config/google_calendar_token.json
VENOM_CALENDAR_ID=venom_work_calendar
VENOM_CALENDAR_NAME=Venom Work

# Notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

## Metryki i Monitoring

**Kluczowe wskaźniki:**
- Liczba automatycznie przetworzonych Issues (per tydzień)
- Średni czas Issue → PR (time-to-PR)
- Liczba commitów per branch (średnio)
- Współczynnik merge PR (% PR zaakceptowanych)
- Liczba powiadomień wysłanych (Discord/Slack)

## Best Practices

1. **Semantic commits zawsze** - Ułatwia automatyczne generowanie CHANGELOG
2. **Feature branch per Issue** - `feature/nazwa-42` (42 = Issue number)
3. **Link Issues w PR** - "Closes #42" lub "Fixes #55" w body
4. **Powiadomienia dla ludzi** - Discord/Slack dla ważnych eventów
5. **Review przed merge** - Nawet automatyczne PR wymagają human review

## Znane Ograniczenia

- Brak automatycznego merge (wymaga human approval)
- GitHub Token musi mieć uprawnienia repo + issues
- Issue polling nie wspiera webhooków (tylko periodic check)
- Brak integracji z GitLab/Bitbucket (tylko GitHub)

## Zobacz też

- [THE_LAUNCHPAD.md](THE_LAUNCHPAD.md) - Release workflow i deployment
- [EXTERNAL_INTEGRATIONS.md](EXTERNAL_INTEGRATIONS.md) - GitHub/Discord/Slack/Tavily/HF/Calendar
- [CONTRIBUTING.md](CONTRIBUTING.md) - Zasady commitów i PR
