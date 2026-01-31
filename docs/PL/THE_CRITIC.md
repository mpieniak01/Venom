# THE CRITIC - Code Quality & Security Review

## Rola

Critic Agent to ekspert w zakresie bezpieczeństwa i jakości kodu w systemie Venom. Pełni rolę Senior Developer/QA, wykrywając błędy logiczne, luki bezpieczeństwa oraz problemy z jakością kodu przed jego finalnym zatwierdzeniem.

## Odpowiedzialności

- **Ocena jakości kodu** - Weryfikacja czytelności, dokumentacji, zgodności z best practices
- **Audyt bezpieczeństwa** - Wykrywanie hardcoded credentials, SQL injection, niebezpiecznych komend
- **Weryfikacja poprawności** - Sprawdzanie błędów logicznych, typowania, składni
- **Diagnostyka źródeł błędów** - Identyfikacja problemów w importowanych modułach
- **Sugestie naprawy** - Konkretne wskazówki jak poprawić problematyczny kod

## Kluczowe Komponenty

### 1. System Oceny Kodu

**3 rodzaje odpowiedzi:**

**1. APPROVED** - Kod bezpieczny i dobrej jakości
```
Kod nie zawiera problemów. APPROVED
```

**2. Problemy w analizowanym kodzie** - Lista błędów w formie tekstowej
```
Znalezione problemy:
1. Linia 15: Hardcoded API key - Użyj zmiennej środowiskowej
2. Linia 23: Brak obsługi błędów - Dodaj try/except
3. Linia 45: Brak typowania parametru 'data' - Dodaj type hint
```

**3. Problemy w importowanym pliku** - JSON z target_file_change
```json
{
  "analysis": "ImportError: module 'config' brak funkcji 'get_setting'",
  "suggested_fix": "Dodaj funkcję get_setting(key) w config.py",
  "target_file_change": "venom_core/config.py"
}
```

### 2. Wykrywane Problemy

**Bezpieczeństwo:**
- ❌ Hardcoded API keys (`api_key = "sk-..."`)
- ❌ Hasła w kodzie (`password = "secret123"`)
- ❌ SQL queries bez parametryzacji
- ❌ Niebezpieczne komendy shell (`rm -rf`, `eval()`)
- ❌ Brak walidacji inputu użytkownika

**Jakość:**
- ❌ Brak typowania funkcji
- ❌ Brak docstringów
- ❌ Brak obsługi błędów (try/except)
- ❌ Magiczne liczby bez stałych
- ❌ Zbyt długie funkcje (>50 linii)

**Błędy importów:**
- ❌ ImportError - brakująca funkcja/klasa w module
- ❌ AttributeError - brak atrybutu w obiekcie
- ❌ ModuleNotFoundError - brak modułu

### 3. Integracja z PolicyEngine

Critic korzysta z **PolicyEngine** do weryfikacji zasad projektu:

```python
from venom_core.core.policy_engine import PolicyEngine

policy_engine = PolicyEngine()

# Sprawdź czy operacja jest dozwolona
is_allowed = policy_engine.is_allowed(
    operation="write_file",
    path="/etc/passwd"
)
# → False (poza workspace)
```

**Polityki:**
- Sandbox filesystem (tylko workspace)
- Blokada niebezpiecznych komend shell
- Limity zasobów (CPU, RAM)
- Blokada dostępu do sieci (opcjonalne)

## Integracja z Systemem

### Przepływ Wykonania

```
CoderAgent generuje kod
        ↓
CriticAgent.execute(kod)
        ↓
CriticAgent:
  1. Analiza kodu (LLM z temperature=0.3)
  2. Wykrywanie problemów bezpieczeństwa
  3. Sprawdzenie jakości i dokumentacji
  4. PolicyEngine.validate()
        ↓
Zwraca: "APPROVED" lub lista problemów
        ↓
Jeśli APPROVED → Kod zaakceptowany
Jeśli problemy → CoderAgent naprawia (self-repair)
```

### Współpraca z Innymi Agentami

- **CoderAgent** - Główny klient (pętla generate → review → fix)
- **ArchitectAgent** - Weryfikacja planów pod kątem wykonalności
- **PolicyEngine** - Egzekwowanie zasad bezpieczeństwa
- **ToolmakerAgent** - Review generowanych narzędzi

## Przykłady Użycia

### Przykład 1: Kod z Hardcoded Credentials
```python
# Kod do review:
api_key = "sk-1234567890abcdef"
response = requests.get("https://api.example.com", headers={"Authorization": api_key})

# CriticAgent odpowiedź:
"""
Znalezione problemy:
1. Linia 1: Hardcoded API key 'sk-1234567890abcdef'
   Sugestia: Użyj zmiennej środowiskowej
   ```python
   api_key = os.environ.get("API_KEY")
   if not api_key:
       raise ValueError("API_KEY not set")
   ```
"""
```

### Przykład 2: Brak Obsługi Błędów
```python
# Kod do review:
def read_config():
    with open("config.json") as f:
        return json.load(f)

# CriticAgent odpowiedź:
"""
Znalezione problemy:
1. Funkcja 'read_config': Brak obsługi błędów (FileNotFoundError, JSONDecodeError)
   Sugestia: Dodaj try/except z graceful degradation
   ```python
   def read_config():
       try:
           with open("config.json") as f:
               return json.load(f)
       except (FileNotFoundError, JSONDecodeError) as e:
           logger.error(f"Błąd odczytu config: {e}")
           return {}  # Zwróć domyślną konfigurację
   ```
"""
```

### Przykład 3: Import Error (inny plik)
```python
# Kod do review:
from config import get_database_url  # ImportError: brak funkcji

# CriticAgent odpowiedź (JSON):
{
  "analysis": "ImportError w linii 1: module 'config' nie posiada funkcji 'get_database_url'. Problem w pliku venom_core/config.py",
  "suggested_fix": "Dodaj funkcję get_database_url() w venom_core/config.py:\n\ndef get_database_url() -> str:\n    return os.environ.get('DATABASE_URL', 'sqlite:///default.db')",
  "target_file_change": "venom_core/config.py"
}
```

## Konfiguracja

```bash
# W .env (brak dedykowanych flag dla Critic)
# Temperature dla LLM ustawiona w kodzie (0.3 dla konsystencji ocen)

# PolicyEngine settings
ENABLE_SANDBOX=true
WORKSPACE_ROOT=./workspace
```

## Metryki i Monitoring

**Kluczowe wskaźniki:**
- Liczba review per sesja
- Współczynnik APPROVED vs. odrzucone (% approved)
- Najczęstsze typy problemów (security, quality, imports)
- Średnia liczba iteracji fix → review (self-repair)
- Czas review (zazwyczaj <5s)

## Best Practices

1. **Zawsze review przed commitm** - Każdy wygenerowany kod przez CriticAgent
2. **Fix iteracyjnie** - Max 3 iteracje self-repair, potem eskalacja
3. **Loguj odrzucone** - Zapisz problemy do Work Ledger
4. **PolicyEngine ON** - Zawsze weryfikuj zgodność z politykami
5. **Temperature niska** - 0.3 dla konsystencji ocen (nie kreatywność)

## Znane Ograniczenia

- Analiza statyczna (brak uruchomienia kodu) - może przeoczyć runtime bugs
- LLM może dać false positive (zbyt rygorystyczne oceny)
- Brak integracji z linterami zewnętrznymi (ruff, mypy) - tylko LLM
- Max 3 iteracje self-repair (potem manual intervention)

## Zobacz też

- [THE_CODER.md](THE_CODER.md) - Generowanie kodu
- [BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md) - Architektura backendu
- [CONTRIBUTING.md](CONTRIBUTING.md) - Zasady współpracy (pre-commit hooks)
