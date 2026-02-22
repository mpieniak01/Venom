# External Integrations - External Integration Layer

## Overview

The external integration module enables Venom to automatically handle tasks from external platforms (GitHub Issues), send notifications (Discord/Slack), search the web (Tavily), explore models (Hugging Face), and connect calendars (Google Calendar). All integrations are optional and only activate after `.env` configuration.

## Components

### 1. PlatformSkill (`venom_core/execution/skills/platform_skill.py`)

Wrapper for external platform APIs:

**GitHub functions:**
- `get_assigned_issues(state="open")` - Retrieves Issues assigned to bot
- `get_issue_details(issue_number)` - Retrieves Issue details with comments
- `create_pull_request(branch, title, body, base="main")` - Creates Pull Request
- `comment_on_issue(issue_number, text)` - Adds comment to Issue

**Communication functions:**
- `send_notification(message, channel="discord")` - Sends notification to Discord/Slack
- `check_connection()` - Checks connection status with platforms

### 2. WebSearchSkill (`venom_core/execution/skills/web_skill.py`)

External search integration:
- **Tavily API** (when `TAVILY_API_KEY` is set) for higher-quality results.
- **DuckDuckGo (DDG)** fallback without a key.

### 3. HuggingFaceSkill (`venom_core/execution/skills/huggingface_skill.py`)

Model and dataset exploration:
- model/dataset search,
- metadata retrieval,
- optional `HF_TOKEN` for private access.

### 4. GoogleCalendarSkill (`venom_core/execution/skills/google_calendar_skill.py`)

Calendar integration:
- read and write events (write-only to the Venom calendar),
- OAuth2 credentials in `config/*`.

### 5. IntegratorAgent 1.0 (`venom_core/agents/integrator.py`)

Extended DevOps agent with functions:

**New methods:**
- `poll_issues()` - Retrieves new Issues from GitHub
- `handle_issue(issue_number)` - Handles Issue: retrieves details, creates branch
- `finalize_issue(issue_number, branch_name, pr_title, pr_body)` - Finalizes: creates PR, comments, sends notification

### 6. Orchestrator Pipeline (`venom_core/core/orchestrator.py`)

**New method:**
- `handle_remote_issue(issue_number)` - Complete "Issue-to-PR" workflow:
  1. Integrator retrieves Issue and creates branch
  2. Architect creates fix plan
  3. Coder implements fix
  4. Integrator commits, pushes and creates PR
  5. Sends notification

## Configuration

Add to `.env`:

```env
# GitHub Integration
GITHUB_TOKEN=ghp_your_personal_access_token
GITHUB_REPO_NAME=username/repository

# Hugging Face (optional)
HF_TOKEN=

# Discord Notifications (optional)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Slack Notifications (optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Tavily AI Search (optional)
TAVILY_API_KEY=

# Google Calendar (optional)
ENABLE_GOOGLE_CALENDAR=false
GOOGLE_CALENDAR_CREDENTIALS_PATH=./config/google_calendar_credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=./config/google_calendar_token.json
VENOM_CALENDAR_ID=venom_work_calendar
VENOM_CALENDAR_NAME=Venom Work

# Issue Polling (optional)
ENABLE_ISSUE_POLLING=true
ISSUE_POLLING_INTERVAL_MINUTES=5
```

### Obtaining GitHub Token

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token
3. Check permissions:
   - `repo` (full access to private repositories)
   - `workflow` (if you want to manage workflows)
4. Copy token and add to `.env`

### Obtaining Discord Webhook URL

1. Go to Discord server settings
2. Integrations → Webhooks → New Webhook
3. Select channel and copy webhook URL
4. Add to `.env`

## Usage

### Example 1: Manual Issue handling

```python
from venom_core.core.orchestrator import Orchestrator

# Assuming you have configured orchestrator
result = await orchestrator.handle_remote_issue(issue_number=42)

if result["success"]:
    print(f"✅ Issue #{result['issue_number']} handled!")
    print(result["message"])
else:
    print(f"❌ Error: {result['message']}")
```

### Example 2: Polling Issues (in background task)

```python
from venom_core.agents.integrator import IntegratorAgent

# Creating agent
integrator = IntegratorAgent(kernel)

# Check new Issues
issues = await integrator.poll_issues()

for issue in issues:
    print(f"Found Issue: {issue}")
    # Handle each Issue
```

### Example 3: Sending notification

```python
from venom_core.execution.skills.platform_skill import PlatformSkill

skill = PlatformSkill()

# Send to Discord
await skill.send_notification(
    message="🚀 Deploy completed successfully!",
    channel="discord"
)

# Send to Slack
await skill.send_notification(
    message="⚠️ Critical error detected",
    channel="slack"
)
```

## "Issue-to-PR" Workflow

1. **User reports Issue on GitHub** (even from phone)
2. **Venom detects new Issue** (polling or webhook)
3. **Integrator retrieves details** and creates branch `issue-{number}`
4. **Architect analyzes** problem and creates fix plan
5. **Coder implements** fix according to plan
6. **Guardian validates** changes (if enabled)
7. **Integrator commits** and pushes changes
8. **Integrator creates PR** with link to Issue (`Closes #123`)
9. **Integrator adds comment** in Issue with PR information
10. **Integrator sends notification** to Discord/Slack

## Security

### Token masking in logs

PlatformSkill automatically masks tokens in logs:
```python
# Token: ghp_1234567890abcdef...
# In logs: ghp_1234...cdef
```

### Best practices

1. **DO NOT commit** `.env` to repository
2. **Use** Personal Access Tokens with minimal permissions
3. **Rotate** tokens regularly
4. **Monitor** API activity on GitHub
5. **Limit** IP if possible (GitHub Settings → Personal access tokens)

## Limitations

### Polling vs Webhooks

Implementation uses **polling** (querying API every N minutes) instead of webhooks because:
- Architecture simplicity (Local-First)
- No need for public IP
- No need for tunnel (ngrok)

GitHub API rate limits:
- Authenticated: 5000 requests/hour
- Polling every 5 minutes = 12 requests/hour ✅

### Additional limits and dependencies

- **Tavily** requires an API key; without it WebSearchSkill falls back to DDG.
- **Google Calendar** requires OAuth2 setup and first-time local login.

### Rate Limiting

PlatformSkill automatically handles rate limit errors, but:
- Don't implement aggressive polling (< 1 minute)
- Monitor remaining requests: `Github.get_rate_limit()`

## Global API Traffic Control (core)

Venom core enforces an additional global protection layer for API traffic:
- outbound controls (provider + method scopes),
- inbound controls (endpoint groups + actor/session/IP keys),
- unified `429`/`Retry-After` behavior,
- anti-loop safeguards (global request cap + degraded mode).

See: [`docs/API_TRAFFIC_CONTROL.md`](API_TRAFFIC_CONTROL.md)

## Testing

### Manual tests

Without full dependency installation, test:

1. **Configuration:**
```python
from venom_core.execution.skills.platform_skill import PlatformSkill

skill = PlatformSkill()
status = skill.check_connection()
print(status)
```

2. **Retrieving Issues:**
```python
result = await skill.get_assigned_issues()
print(result)
```

3. **Sending notifications:**
```python
result = await skill.send_notification("Test", "discord")
print(result)
```

### Unit tests

Tests require full dependency installation from `requirements-full.txt`.

Due to lack of disk space in test environment, full unit tests
can be run locally after installing all dependencies.

## Troubleshooting

### "GitHub not configured"

Check `.env`:
- `GITHUB_TOKEN` is set
- `GITHUB_REPO_NAME` has format `owner/repo`

### "Webhook URL not configured"

Check `.env`:
- `DISCORD_WEBHOOK_URL` or `SLACK_WEBHOOK_URL` is set

### "GitHub API Error: 401"

Token is invalid or expired:
- Generate new token
- Check if token has appropriate permissions

### "GitHub API Error: 403"

Rate limit reached:
- Increase polling interval
- Check remaining requests: `Github.get_rate_limit()`

### "GitHub API Error: 404"

Repository doesn't exist or no access:
- Check repository name in `GITHUB_REPO_NAME`
- Check token permissions

## Roadmap

### Implemented (v1.0)
- ✅ PlatformSkill (GitHub + Discord/Slack)
- ✅ IntegratorAgent 1.0 (Issue handling)
- ✅ Orchestrator pipeline (Issue-to-PR)
- ✅ Configuration and secret masking

### Planned (v1.0)
- ⏳ Background task for auto-polling Issues
- ⏳ Webhook support (alternative to polling)
- ⏳ Dashboard panel "External Integrations"
- ⏳ GitHub Projects support
- ⏳ GitHub Actions support (trigger workflows)
- ⏳ Slack interactive messages (buttons, selects)
- ⏳ MS Teams integration

## Authors

- **Implementation:** GitHub Copilot & mpieniak01
- **Architecture:** Venom Core Team
- **Issue:** #018_THE_TEAMMATE
