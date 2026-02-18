# Provider Governance - Zasady i Tabela Decyzyjna

> **Decyzja Architektoniczna**: Provider governance jest częścią strategii routingu zdefiniowanej w [ADR-001: Strategia Runtime](adr/ADR-001-runtime-strategy-llm-first.md). Ten dokument opisuje operacyjne zasady governance i tabele decyzyjne.

## Przegląd
Ten dokument opisuje zasady governance, wyzwalacze, akcje i kody przyczyn dla systemu Provider Governance zaimplementowanego w ramach zadania #142.

## Tabela Decyzyjna Governance

| Kategoria Reguły | Wyzwalacz | Akcja | Kod Przyczyny | Wiadomość Użytkownika (EN) | Wiadomość Użytkownika (PL) |
|------------------|-----------|-------|---------------|----------------------------|----------------------------|
| **Limity Kosztów - Soft** | Koszt globalny przekracza limit soft ($10 domyślnie) | Zezwól + Log ostrzeżenia | Brak | Request allowed (warning: approaching budget limit) | Żądanie dozwolone (ostrzeżenie: zbliżanie do limitu budżetu) |
| **Limity Kosztów - Hard** | Koszt globalny przekracza limit hard ($50 domyślnie) | Zablokuj żądanie | `BUDGET_HARD_LIMIT_EXCEEDED` | Global hard limit exceeded: ${total} > ${limit} | Przekroczono globalny twardy limit: ${total} > ${limit} |
| **Limity Kosztów - Provider** | Koszt providera przekracza limit hard ($25 domyślnie) | Zablokuj żądanie | `PROVIDER_BUDGET_EXCEEDED` | Provider {provider} hard limit exceeded: ${total} > ${limit} | Przekroczono twardy limit providera {provider}: ${total} > ${limit} |
| **Rate Limits - Żądania** | Liczba żądań na minutę przekracza max (100 domyślnie) | Zablokuj żądanie | `RATE_LIMIT_REQUESTS_EXCEEDED` | Global request rate limit exceeded: {count} > {max}/min | Przekroczono globalny limit liczby zapytań: {count} > {max}/min |
| **Rate Limits - Tokeny** | Liczba tokenów na minutę przekracza max (100k domyślnie) | Zablokuj żądanie | `RATE_LIMIT_TOKENS_EXCEEDED` | Global token rate limit exceeded: {count} > {max}/min | Przekroczono globalny limit liczby tokenów: {count} > {max}/min |
| **Dane Uwierzytelniające - Brak** | Klucz API OpenAI/Google nieskonfigurowany | Fallback do lokalnego providera | `FALLBACK_AUTH_ERROR` | Switched to {provider} due to missing credentials | Przełączono na {provider} z powodu braku danych uwierzytelniających |
| **Dane Uwierzytelniające - Błąd** | Walidacja klucza API nieudana | Fallback do lokalnego providera | `FALLBACK_AUTH_ERROR` | Switched to {provider} due to invalid credentials | Przełączono na {provider} z powodu nieprawidłowych danych |
| **Fallback - Timeout** | Czas odpowiedzi providera > próg (30s domyślnie) | Przełącz na następnego w kolejności | `FALLBACK_TIMEOUT` | Switched to {provider} due to timeout | Przełączono na {provider} z powodu przekroczenia czasu |
| **Fallback - Budżet** | Budżet providera przekroczony + fallback włączony | Przełącz na tańszego providera | `FALLBACK_BUDGET_EXCEEDED` | Switched to {provider} due to budget exceeded | Przełączono na {provider} z powodu przekroczenia budżetu |
| **Fallback - Degradacja** | Status providera = degraded + fallback włączony | Przełącz na zdrowego providera | `FALLBACK_DEGRADED` | Switched to {provider} due to degradation | Przełączono na {provider} z powodu degradacji |
| **Fallback - Offline** | Status providera = offline | Przełącz na dostępnego providera | `FALLBACK_OFFLINE` | Switched to {provider} - original provider offline | Przełączono na {provider} - oryginalny provider offline |
| **Fallback - Brak Dostępnych** | Wszyscy providerzy niedostępni/zablokowani | Zablokuj żądanie | `NO_PROVIDER_AVAILABLE` | No provider available: {reason} | Brak dostępnego providera: {reason} |

## Kody Statusu Danych Uwierzytelniających

| Kod Statusu | Opis | Kiedy Używany |
|------------|------|---------------|
| `configured` | Provider ma poprawne dane | Klucze API OpenAI/Google są ustawione i zweryfikowane |
| `missing_credentials` | Brak wymaganych danych | Klucze API OpenAI/Google są puste lub nieustawione |
| `invalid_credentials` | Dane są nieprawidłowe | Format klucza API jest błędny lub autoryzacja nieudana |

## Konfiguracja Polityki Fallback

Domyślna kolejność fallback:
1. `ollama` (preferowany - lokalny, darmowy)
2. `vllm` (lokalny, darmowy)
3. `openai` (chmura, płatny)
4. `google` (chmura, płatny)

Ustawienia konfigurowalne:
- `preferred_provider`: Domyślny provider (domyślnie: `ollama`)
- `fallback_order`: Lista kolejności providerów
- `enable_timeout_fallback`: Zezwól na fallback przy timeout (domyślnie: `true`)
- `enable_auth_fallback`: Zezwól na fallback przy błędzie autoryzacji (domyślnie: `true`)
- `enable_budget_fallback`: Zezwól na fallback przy przekroczeniu budżetu (domyślnie: `true`)
- `enable_degraded_fallback`: Zezwól na fallback przy degradacji (domyślnie: `true`)
- `timeout_threshold_seconds`: Próg timeoutu (domyślnie: `30.0`)

## Konfiguracja Limitów Kosztów

| Zakres | Limit Soft (USD) | Limit Hard (USD) | Opis |
|--------|------------------|------------------|------|
| Globalny | $10 | $50 | Całkowity koszt wszystkich providerów |
| Per-Provider | $5 | $25 | Koszt per konkretny provider (konfigurowalne) |
| Per-Model | - | - | Jeszcze nie zaimplementowane (przyszłe rozszerzenie) |

## Konfiguracja Limitów Rate

| Zakres | Max Żądań/min | Max Tokenów/min | Opis |
|--------|---------------|-----------------|------|
| Globalny | 100 | 100,000 | Całkowity rate wszystkich providerów |
| Per-Provider | - | - | Konfigurowalne per provider (przyszłe rozszerzenie) |

## Endpointy API

### GET /api/v1/governance/status
Zwraca aktualny status governance w tym:
- Aktywne limity kosztów i rate
- Aktualne metryki zużycia
- Ostatnie zdarzenia fallback (ostatnie 10)
- Konfiguracja polityki fallback

### GET /api/v1/governance/limits
Zwraca skonfigurowane limity bez danych o zużyciu:
- Limity kosztów (soft/hard) dla zakresów
- Limity rate (żądania/tokeny) dla zakresów

### GET /api/v1/governance/providers/{provider}/credentials
Waliduje dane uwierzytelniające providera bez ujawniania sekretów:
- Zwraca: `configured`, `missing_credentials`, lub `invalid_credentials`
- Nigdy nie ujawnia kluczy API w odpowiedzi

### POST /api/v1/governance/limits
Dynamicznie aktualizuje limity kosztów lub rate:
- Payload: `{ limit_type: "cost"|"rate", scope: "global"|provider_name, ... }`
- Zwraca zaktualizowaną konfigurację limitów

### POST /api/v1/governance/reset-usage
Resetuje liczniki zużycia:
- Query param `scope`: opcjonalny, resetuje konkretny zakres lub wszystko jeśli pominięty
- Przydatne do testów lub resetu miesięcznego

## Ścieżka Audytu (Audit Trail)

Wszystkie zdarzenia fallback są rejestrowane z:
- Znacznikiem czasu
- Od providera
- Do providera
- Kodem przyczyny
- Wiadomością użytkownika
- Szczegółami technicznymi (opcjonalnie)

Historia jest utrzymywana dla ostatnich 100 zdarzeń w pamięci.

## Funkcje Bezpieczeństwa

### Maskowanie Sekretów
- Klucze API są maskowane w logach: `sk-1234...ghij`
- Sekrety nigdy nie pojawiają się w odpowiedziach API
- Konfiguracja używa Pydantic `SecretStr` dla danych wrażliwych

### Brak Wycieków Sekretów
- Walidacja danych nigdy nie loguje pełnych kluczy
- Endpoint statusu governance nigdy nie ujawnia danych uwierzytelniających
- Wszystkie testy weryfikują brak sekretów w logach

## Pokrycie Testami

Kompletny zestaw testów (42 testy) pokrywający:
- ✅ Walidację danych (configured/missing/invalid)
- ✅ Maskowanie sekretów i brak wycieków
- ✅ Limity kosztów (under/soft/hard)
- ✅ Limity rate (żądania/tokeny)
- ✅ Politykę fallback (wszystkie kody przyczyn)
- ✅ API statusu governance
- ✅ Stabilność kodów przyczyn
- ✅ Wzorzec Singleton

## Punkty Integracji

### Istniejące Komponenty
- **TokenEconomist**: Obliczanie i śledzenie kosztów
- **SETTINGS (config.py)**: Przechowywanie danych z SecretStr
- **Providers API**: Status i aktywacja providerów
- **StateManager**: Tryb kosztów globalnych (paid/free)

### Przyszłe Rozszerzenia
1. Limity kosztów per-model
2. Limity rate per-provider
3. Limity oparte o okna czasowe (godzinowe/dzienne)
4. Automatyzacja resetu budżetu
5. Alerty/powiadomienia o progach limitów
6. Integracja z API bilingowym providerów chmurowych
7. Sugestie optymalizacji kosztów
