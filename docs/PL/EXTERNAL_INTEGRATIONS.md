# External Integrations - Warstwa Integracji Zewnętrznej

## Przegląd

Moduł integracji zewnętrznej umożliwia Venomowi automatyczną obsługę zadań z platform zewnętrznych (GitHub Issues), wysyłanie powiadomień (Discord/Slack), wyszukiwanie w sieci (Tavily), eksplorację modeli (Hugging Face) oraz integrację kalendarza (Google Calendar). Wszystkie integracje są opcjonalne i działają tylko po konfiguracji w `.env`.

## Komponenty

### 1. PlatformSkill (`venom_core/execution/skills/platform_skill.py`)

Wrapper dla API platform zewnętrznych:

**Funkcje GitHub:**
- `get_assigned_issues(state="open")` - Pobiera Issues przypisane do bota
- `get_issue_details(issue_number)` - Pobiera szczegóły Issue z komentarzami
- `create_pull_request(branch, title, body, base="main")` - Tworzy Pull Request
- `comment_on_issue(issue_number, text)` - Dodaje komentarz do Issue

**Funkcje komunikacji:**
- `send_notification(message, channel="discord")` - Wysyła powiadomienie na Discord/Slack
- `check_connection()` - Sprawdza status połączenia z platformami

### 2. WebSearchSkill (`venom_core/execution/skills/web_skill.py`)

Integracja wyszukiwania zewnętrznego:
- **Tavily API** (jeśli `TAVILY_API_KEY` jest ustawiony) dla lepszej jakości wyników.
- **DuckDuckGo (DDG)** jako fallback bez klucza.

### 3. HuggingFaceSkill (`venom_core/execution/skills/huggingface_skill.py`)

Eksploracja modeli i datasetów:
- wyszukiwanie modeli/datasetów,
- pobieranie metadanych,
- wsparcie tokenem `HF_TOKEN` (opcjonalnie, prywatne modele).

### 4. GoogleCalendarSkill (`venom_core/execution/skills/google_calendar_skill.py`)

Integracja kalendarza:
- odczyt i zapis zdarzeń (write-only do kalendarza Venoma),
- OAuth2 credentials w `config/*`.

### 5. IntegratorAgent 1.0 (`venom_core/agents/integrator.py`)

Rozszerzony agent DevOps z funkcjami:

**Nowe metody:**
- `poll_issues()` - Pobiera nowe Issues z GitHub
- `handle_issue(issue_number)` - Obsługuje Issue: pobiera szczegóły, tworzy branch
- `finalize_issue(issue_number, branch_name, pr_title, pr_body)` - Finalizuje: tworzy PR, komentuje, wysyła powiadomienie

### 6. Orchestrator Pipeline (`venom_core/core/orchestrator.py`)

**Nowa metoda:**
- `handle_remote_issue(issue_number)` - Kompletny workflow "Issue-to-PR":
  1. Integrator pobiera Issue i tworzy branch
  2. Architekt tworzy plan naprawy
  3. Coder implementuje fix
  4. Integrator commituje, pushuje i tworzy PR
  5. Wysyła powiadomienie

## Konfiguracja

Dodaj do `.env`:

```env
# GitHub Integration
GITHUB_TOKEN=ghp_your_personal_access_token
GITHUB_REPO_NAME=username/repository

# Hugging Face (opcjonalne)
HF_TOKEN=

# Discord Notifications (opcjonalne)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Slack Notifications (opcjonalne)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Tavily AI Search (opcjonalne)
TAVILY_API_KEY=

# Google Calendar (opcjonalne)
ENABLE_GOOGLE_CALENDAR=false
GOOGLE_CALENDAR_CREDENTIALS_PATH=./config/google_calendar_credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=./config/google_calendar_token.json
VENOM_CALENDAR_ID=venom_work_calendar
VENOM_CALENDAR_NAME=Venom Work

# Issue Polling (opcjonalne)
ENABLE_ISSUE_POLLING=true
ISSUE_POLLING_INTERVAL_MINUTES=5
```

### Uzyskanie GitHub Token

1. Przejdź do GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token
3. Zaznacz uprawnienia:
   - `repo` (pełny dostęp do repozytoriów prywatnych)
   - `workflow` (jeśli chcesz zarządzać workflow)
4. Skopiuj token i dodaj do `.env`

### Uzyskanie Discord Webhook URL

1. Przejdź do ustawień serwera Discord
2. Integrations → Webhooks → New Webhook
3. Wybierz kanał i skopiuj URL webhooka
4. Dodaj do `.env`

## Użycie

### Przykład 1: Ręczna obsługa Issue

```python
from venom_core.core.orchestrator import Orchestrator

# Załóżmy że masz skonfigurowany orchestrator
result = await orchestrator.handle_remote_issue(issue_number=42)

if result["success"]:
    print(f"✅ Issue #{result['issue_number']} obsłużone!")
    print(result["message"])
else:
    print(f"❌ Błąd: {result['message']}")
```

### Przykład 2: Polling Issues (w background task)

```python
from venom_core.agents.integrator import IntegratorAgent

# Tworzenie agenta
integrator = IntegratorAgent(kernel)

# Sprawdź nowe Issues
issues = await integrator.poll_issues()

for issue in issues:
    print(f"Znaleziono Issue: {issue}")
    # Obsłuż każde Issue
```

### Przykład 3: Wysłanie powiadomienia

```python
from venom_core.execution.skills.platform_skill import PlatformSkill

skill = PlatformSkill()

# Wyślij na Discord
await skill.send_notification(
    message="🚀 Deploy zakończony sukcesem!",
    channel="discord"
)

# Wyślij na Slack
await skill.send_notification(
    message="⚠️ Wykryto krytyczny błąd",
    channel="slack"
)
```

## Workflow "Issue-to-PR"

1. **Użytkownik zgłasza Issue na GitHubie** (nawet z telefonu)
2. **Venom wykrywa nowe Issue** (polling lub webhook)
3. **Integrator pobiera szczegóły** i tworzy branch `issue-{number}`
4. **Architekt analizuje** problem i tworzy plan naprawy
5. **Coder implementuje** fix zgodnie z planem
6. **Guardian waliduje** zmiany (jeśli włączone)
7. **Integrator commituje** i pushuje zmiany
8. **Integrator tworzy PR** z linkiem do Issue (`Closes #123`)
9. **Integrator dodaje komentarz** w Issue z informacją o PR
10. **Integrator wysyła powiadomienie** na Discord/Slack

## Bezpieczeństwo

### Maskowanie tokenów w logach

PlatformSkill automatycznie maskuje tokeny w logach:
```python
# Token: ghp_1234567890abcdef...
# W logach: ghp_1234...cdef
```

### Best practices

1. **NIE commituj** `.env` do repozytorium
2. **Używaj** Personal Access Tokens z minimalnymi uprawnieniami
3. **Rotuj** tokeny regularnie
4. **Monitoruj** aktywność API na GitHubie
5. **Ogranicz** IP jeśli to możliwe (GitHub Settings → Personal access tokens)

## Ograniczenia

### Polling vs Webhooks

Implementacja używa **polling** (odpytywanie API co N minut) zamiast webhooków z powodu:
- Prostota architektury (Local-First)
- Brak potrzeby publicznego IP
- Brak potrzeby tunelu (ngrok)

Rate limits GitHub API:
- Authenticated: 5000 requests/hour
- Polling co 5 minut = 12 requests/hour ✅

### Limity i zależności dodatkowe

- **Tavily** wymaga aktywnego klucza API; bez niego WebSearchSkill użyje DDG.
- **Google Calendar** wymaga konfiguracji OAuth2 i pierwszego logowania w trybie lokalnym.

### Rate Limiting

PlatformSkill automatycznie obsługuje błędy rate limit, ale:
- Nie implementuj agresywnego pollingu (< 1 minuta)
- Monitoruj pozostałe requesty: `Github.get_rate_limit()`

## Globalna kontrola ruchu API (core)

Venom core wymusza dodatkową globalną warstwę ochrony ruchu API:
- kontrolę outbound (scope provider + metoda),
- kontrolę inbound (grupy endpointów + actor/session/IP),
- spójne zachowanie `429`/`Retry-After`,
- zabezpieczenia anti-loop (globalny cap requestów + tryb degraded).
- obowiązkową ścieżkę outbound dla nowych modułów: `TrafficControlledHttpClient` (bez surowego `httpx/aiohttp/requests` w ścieżkach core do zewnętrznych API).

Zobacz: [`docs/PL/API_TRAFFIC_CONTROL.md`](API_TRAFFIC_CONTROL.md)

## Testowanie

### Testy manualne

Bez pełnej instalacji zależności, przetestuj:

1. **Konfigurację:**
```python
from venom_core.execution.skills.platform_skill import PlatformSkill

skill = PlatformSkill()
status = skill.check_connection()
print(status)
```

2. **Pobieranie Issues:**
```python
result = await skill.get_assigned_issues()
print(result)
```

3. **Wysyłanie powiadomień:**
```python
result = await skill.send_notification("Test", "discord")
print(result)
```

### Testy jednostkowe

Testy wymagają pełnej instalacji zależności z `requirements-full.txt`.

Ze względu na brak miejsca na dysku w środowisku testowym, pełne testy jednostkowe
mogą być uruchomione lokalnie po instalacji wszystkich zależności.

## Troubleshooting

### "GitHub nie skonfigurowany"

Sprawdź `.env`:
- `GITHUB_TOKEN` jest ustawiony
- `GITHUB_REPO_NAME` ma format `owner/repo`

### "Webhook URL nie skonfigurowany"

Sprawdź `.env`:
- `DISCORD_WEBHOOK_URL` lub `SLACK_WEBHOOK_URL` jest ustawiony

### "Błąd GitHub API: 401"

Token jest nieprawidłowy lub wygasł:
- Wygeneruj nowy token
- Sprawdź czy token ma odpowiednie uprawnienia

### "Błąd GitHub API: 403"

Rate limit osiągnięty:
- Zwiększ interwał pollingu
- Sprawdź pozostałe requesty: `Github.get_rate_limit()`

### "Błąd GitHub API: 404"

Repository nie istnieje lub brak dostępu:
- Sprawdź nazwę repozytorium w `GITHUB_REPO_NAME`
- Sprawdź uprawnienia tokena

## Wdrożone funkcje

- ✅ PlatformSkill (GitHub + Discord/Slack)
- ✅ IntegratorAgent 1.0 (Issue handling)
- ✅ Orchestrator pipeline (Issue-to-PR)
- ✅ Konfiguracja i maskowanie sekretów

## Autorzy

- **Implementacja:** GitHub Copilot & mpieniak01
- **Architektura:** Venom Core Team
- **Issue:** #018_THE_TEAMMATE
