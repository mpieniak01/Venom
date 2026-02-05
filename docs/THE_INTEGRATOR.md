# THE INTEGRATOR - Git & DevOps Management

## Role

Integrator Agent is a DevOps expert and Release Engineer in the Venom system. It manages Git repository, creates semantic commits, Pull Requests, and integrates with external platforms (GitHub, Discord, Slack).

## Responsibilities

- **Git management** - Repo operations (init, checkout, commit, push, pull)
- **Semantic Commits** - Creating commits compliant with Conventional Commits
- **Branch management** - Creating feature branches, merge, checkout
- **Pull Requests** - Automatic PR creation with description and labels
- **Platform integrations** - GitHub Issues, Discord/Slack notifications
- **Release Management** - Version tagging, CHANGELOG

## Key Components

### 1. GitSkill (`venom_core/execution/skills/git_skill.py`)

**Available operations:**
- `init_repo(path, remote_url)` - Initialize or clone repository
- `checkout(branch, create_new)` - Switch branch or create new
- `get_status()` - Check change status (modified, added, deleted)
- `get_diff(staged)` - See change details
- `add_files(patterns)` - Stage files for commit
- `commit(message)` - Create commit
- `push(branch, remote)` - Push changes to remote
- `get_last_commit_log(count)` - View commit history
- `get_current_branch()` - Check current branch

**Usage example:**
```python
from venom_core.execution.skills.git_skill import GitSkill

git = GitSkill()

# Repository initialization
git.init_repo("./project", "https://github.com/user/repo.git")

# New feature branch
git.checkout("feature/new-api", create_new=True)

# Change status
status = git.get_status()
# → "Modified: app.py, config.py | Added: tests/test_api.py"

# Stage and commit
git.add_files(["app.py", "config.py", "tests/test_api.py"])
git.commit("feat(api): add new REST endpoints")

# Push to remote
git.push("feature/new-api", "origin")
```

### 2. PlatformSkill (`venom_core/execution/skills/platform_skill.py`)

**GitHub Integration:**
- `get_assigned_issues()` - Get Issues assigned to bot
- `get_issue_details(issue_number)` - Get Issue details (with comments)
- `create_pull_request(title, body, head, base)` - Create Pull Request
- `comment_on_issue(issue_number, comment)` - Add comment to Issue
- `add_labels_to_issue(issue_number, labels)` - Add labels to Issue

**Notifications:**
- `send_notification(message, platform)` - Send notification (Discord/Slack)

**Usage example:**
```python
from venom_core.execution.skills.platform_skill import PlatformSkill

platform = PlatformSkill()

# Get assigned Issues
issues = platform.get_assigned_issues()
# → [{"number": 42, "title": "Add login feature", "state": "open"}]

# Create PR
pr = platform.create_pull_request(
    title="feat: Add user authentication",
    body="Implements login/logout with JWT tokens. Closes #42",
    head="feature/auth",
    base="main"
)

# Comment on Issue
platform.comment_on_issue(
    issue_number=42,
    comment="✅ PR created: #123. Ready for review!"
)

# Notification on Discord
platform.send_notification(
    message="🚀 New PR #123: User Authentication",
    platform="discord"
)
```

### 3. Conventional Commits

**Format:**
```
<type>(<scope>): <description>

[optional body]

[optional footers]
```

**Commit types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation changes
- `style` - Formatting (no logic changes)
- `refactor` - Code refactoring
- `test` - Adding/fixing tests
- `chore` - Build changes, dependencies

**Examples:**
```bash
feat(git): add GitSkill implementation
fix(docker): resolve permission denied in habitat
docs(readme): update installation instructions
refactor(auth): simplify login logic
test(api): add integration tests for endpoints
chore(deps): update semantic-kernel to 1.9.0
```

## System Integration

### Execution Flow (Issue → PR)

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
  2. [Execute plan - CODER, TESTER]
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

### Collaboration with Other Agents

- **ArchitectAgent** - Plans Issue implementation
- **CoderAgent** - Generates code for feature branch
- **CriticAgent** - Verifies code before commit
- **TesterAgent** - Generates tests for PR
- **ReleaseManager** - Version tagging, CHANGELOG

## Usage Examples

### Example 1: Automatic Issue Processing
```
User: "Check if there are new Issues on GitHub"

IntegratorAgent:
1. get_assigned_issues()
   → Issue #42: "Add dark mode"
2. get_issue_details(42)
   → Description: "Add dark theme toggle in settings"
3. checkout("feature/dark-mode-42", create_new=True)
4. [Delegation to ArchitectAgent → CoderAgent]
5. commit("feat(ui): add dark mode toggle (#42)")
6. push("feature/dark-mode-42")
7. create_pull_request(...)
8. comment_on_issue(42, "PR #123 created")
```

### Example 2: Release Workflow
```
User: "Create release v1.2.0"

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

### Example 3: Hotfix Workflow
```
User: "Fix bug in authentication (Issue #55)"

IntegratorAgent:
1. checkout("hotfix/auth-55", create_new=True)
2. [CODER fixes bug]
3. commit("fix(auth): prevent token expiry race condition (#55)")
4. push("hotfix/auth-55")
5. create_pull_request(
     title="fix(auth): token expiry race condition",
     base="main",
     labels=["hotfix", "priority:high"]
   )
```

## Configuration

```bash
# In .env
# GitHub Integration
GITHUB_TOKEN=ghp_your_personal_access_token
GITHUB_REPO_NAME=username/repo

# Issue Polling (optional)
ENABLE_ISSUE_POLLING=false
ISSUE_POLLING_INTERVAL_MINUTES=5

# Hugging Face (optional)
HF_TOKEN=

# Tavily (optional)
TAVILY_API_KEY=

# Google Calendar (optional)
ENABLE_GOOGLE_CALENDAR=false
GOOGLE_CALENDAR_CREDENTIALS_PATH=./config/google_calendar_credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=./config/google_calendar_token.json
VENOM_CALENDAR_ID=venom_work_calendar
VENOM_CALENDAR_NAME=Venom Work

# Notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

## Metrics and Monitoring

**Key indicators:**
- Number of automatically processed Issues (per week)
- Average Issue → PR time (time-to-PR)
- Number of commits per branch (average)
- PR merge rate (% PRs accepted)
- Number of notifications sent (Discord/Slack)

## Best Practices

1. **Semantic commits always** - Facilitates automatic CHANGELOG generation
2. **Feature branch per Issue** - `feature/name-42` (42 = Issue number)
3. **Link Issues in PR** - "Closes #42" or "Fixes #55" in body
4. **Notifications for humans** - Discord/Slack for important events
5. **Review before merge** - Even automatic PRs require human review

## Known Limitations

- No automatic merge (requires human approval)
- GitHub Token must have repo + issues permissions
- Issue polling doesn't support webhooks (periodic check only)
- No integration with GitLab/Bitbucket (GitHub only)

## See also

- [THE_LAUNCHPAD.md](THE_LAUNCHPAD.md) - Release workflow and deployment
- [EXTERNAL_INTEGRATIONS.md](EXTERNAL_INTEGRATIONS.md) - GitHub/Discord/Slack/Tavily/HF/Calendar
- [CONTRIBUTING.md](CONTRIBUTING.md) - Commit and PR rules
