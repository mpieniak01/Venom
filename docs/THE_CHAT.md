# THE CHAT - Conversational Assistant

## Rola

Chat Agent to przyjazny asystent konwersacyjny w systemie Venom, specjalizujący się w naturalnych rozmowach z użytkownikiem, odpowiadaniu na pytania ogólne oraz zarządzaniu prostymi zadaniami bez konieczności złożonego planowania.

## Odpowiedzialności

- **Rozmowa naturalna** - Odpowiadanie na pytania w przyjazny, pomocny sposób
- **Integracja z pamięcią** - Wykorzystywanie i zapisywanie informacji do pamięci długoterminowej
- **Zarządzanie kalendarzem** - Integracja z Google Calendar (odczyt, planowanie zadań)
- **Wiedza ogólna** - Odpowiadanie na pytania faktograficzne
- **Asystent osobisty** - Pomoc w codziennych zadaniach

## Kluczowe Komponenty

### 1. Dostępne Narzędzia

**MemorySkill** (`venom_core/memory/memory_skill.py`):
- `recall(query)` - Przywołanie informacji z pamięci długoterminowej
- `memorize(content, tags)` - Zapisanie ważnych informacji

**GoogleCalendarSkill** (`venom_core/execution/skills/google_calendar_skill.py`):
- `read_agenda(days_ahead)` - Odczyt kalendarza na najbliższe dni
- `schedule_task(summary, start_time, duration_minutes, description)` - Dodanie wydarzenia

### 2. Zasady Działania

**Kolejność operacji:**
1. **Najpierw pamięć** - Zawsze sprawdź `recall()` czy nie ma zapisanych informacji
2. **Wykorzystaj wiedzę** - Jeśli znaleziono w pamięci, użyj w odpowiedzi
3. **Odpowiedz naturalnie** - Użyj przyjaznego, zwięzłego języka
4. **Zapisz ważne** - Po ważnej rozmowie rozważ `memorize()`

**Przykłady interakcji:**
```
Użytkownik: "Cześć Venom, jak się masz?"
Chat Agent: "Cześć! Świetnie się mam, dziękuję. Gotowy do pomocy!"

Użytkownik: "Jaka jest stolica Francji?"
Chat Agent: "Stolicą Francji jest Paryż."

Użytkownik: "Co mam w planach dziś?"
Chat Agent: [wywołuje read_agenda(1)] 
           "Dziś masz zaplanowane: 1. Spotkanie z zespołem o 10:00..."

Użytkownik: "Zapamiętaj że lubię kawę o 8 rano"
Chat Agent: [wywołuje memorize("Użytkownik pije kawę o 8:00", tags=["preferences"])]
           "Zapamiętałem! Kawę o 8 rano."
```

### 3. Integracja z Google Calendar

**Konfiguracja:**
```bash
# W .env
ENABLE_GOOGLE_CALENDAR=true
GOOGLE_CALENDAR_CREDENTIALS_PATH=./data/config/google_calendar_credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=./data/config/google_calendar_token.json
VENOM_CALENDAR_ID=your_calendar_id  # NIE 'primary', osobny kalendarz
```

**Przykłady użycia:**
```
Użytkownik: "Co mam jutro?"
→ read_agenda(days_ahead=1)

Użytkownik: "Dodaj spotkanie z Janem jutro o 14:00"
→ schedule_task("Spotkanie z Janem", "2024-01-15T14:00:00", 60)
```

## Integracja z Systemem

### Przepływ Wykonania

```
IntentManager: GENERAL_CHAT
        ↓
ChatAgent.execute(user_message)
        ↓
ChatAgent:
  1. recall(user_message) - sprawdź pamięć
  2. Generuj odpowiedź (LLM) z kontekstem pamięci
  3. Opcjonalnie: read_agenda() dla pytań o kalendarz
  4. Opcjonalnie: memorize() dla ważnych informacji
  5. Zwróć odpowiedź
```

### Współpraca z Innymi Agentami

- **IntentManager** - Przekazuje pytania ogólne (GENERAL_CHAT)
- **MemorySkill** - Długoterminowa pamięć rozmów
- **Orchestrator** - Routuje proste zapytania bezpośrednio do Chat (bez planowania)

## Typy Intencji Obsługiwane przez Chat

**GENERAL_CHAT:**
- Powitania ("Cześć", "Witaj")
- Pytania ogólne ("Jaka jest stolica...", "Co to jest...")
- Żarty i small talk
- Polecenia kalendarzowe ("Co mam jutro?")
- Zarządzanie pamięcią ("Zapamiętaj że...")

**Nie obsługiwane (przekazywane do innych agentów):**
- CODE_GENERATION → CoderAgent
- COMPLEX_PLANNING → ArchitectAgent
- RESEARCH → ResearcherAgent
- KNOWLEDGE_SEARCH → LibrarianAgent / MemorySkill

## Konfiguracja

```bash
# W .env
# Model dla Chat Agent (zazwyczaj szybki, lokalny)
AI_MODE=LOCAL
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1
LLM_MODEL_NAME=llama3  # lub phi3, gemma

# Google Calendar (opcjonalne)
ENABLE_GOOGLE_CALENDAR=false

# Pamięć długoterminowa
MEMORY_ROOT=./data/memory
```

## Metryki i Monitoring

**Kluczowe wskaźniki:**
- Średni czas odpowiedzi (zazwyczaj <2s dla lokalnych modeli)
- Współczynnik użycia pamięci (% zapytań wykorzystujących `recall`)
- Liczba zapisów do pamięci (per sesja)
- Liczba zapytań do Google Calendar (per dzień)

## Best Practices

1. **Pamięć najpierw** - Zawsze sprawdź `recall()` przed odpowiedzią
2. **Zapisuj ważne** - Użyj `memorize()` dla preferencji, faktów o użytkowniku
3. **Zwięzłość** - Odpowiedzi krótkie ale kompletne
4. **Naturalność** - Unikaj formalnego języka, bądź przyjazny
5. **Kalendarz** - Używaj osobnego kalendarza (NIE 'primary') dla zadań Venom

## Znane Ograniczenia

- Brak dostępu do bieżących wydarzeń (wymagany ResearcherAgent + WebSearch)
- Google Calendar wymaga OAuth2 setup (credentials.json)
- Pamięć jest wektorowa (semantyczna), nie zawsze precyzyjna dla dat/liczb
- Brak zarządzania wieloma kontekstami rozmów jednocześnie

## Zobacz też

- [THE_RESEARCHER.md](THE_RESEARCHER.md) - Wyszukiwanie bieżących informacji
- [MEMORY_LAYER_GUIDE.md](MEMORY_LAYER_GUIDE.md) - Pamięć długoterminowa
- [INTENT_RECOGNITION.md](INTENT_RECOGNITION.md) - Klasyfikacja intencji
