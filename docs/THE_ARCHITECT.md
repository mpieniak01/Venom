# THE ARCHITECT - Strategic Planning & Task Decomposition

## Rola

Architect Agent to główny planista strategiczny i kierownik projektu w systemie Venom. Przyjmuje złożone cele użytkownika i rozbija je na konkretne, wykonalne kroki, zarządzając orkiestracją wielu wyspecjalizowanych agentów.

## Odpowiedzialności

- **Planowanie strategiczne** - Dekompozycja złożonych zadań na kroki wykonawcze
- **Zarządzanie przepływem pracy** - Określanie kolejności i zależności między krokami
- **Dobór wykonawców** - Przypisywanie odpowiednich agentów do konkretnych zadań
- **Optymalizacja planów** - Minimalizacja liczby kroków przy zachowaniu kompletności
- **Zarządzanie infrastrukturą** - Planowanie środowisk wielokontenerowych (Docker Compose)

## Kluczowe Komponenty

### 1. Logika Planowania (`venom_core/agents/architect.py`)

**Dostępni Wykonawcy:**
- `RESEARCHER` - Zbieranie wiedzy z Internetu, dokumentacji, przykładów
- `CODER` - Implementacja kodu, tworzenie plików, środowisk Docker Compose
- `LIBRARIAN` - Zarządzanie plikami, czytanie istniejącego kodu
- `TOOLMAKER` - Tworzenie nowych narzędzi/umiejętności dla systemu

**Zasady Planowania:**
1. Rozbij cel na małe, konkretne kroki (3-7 kroków optymalnie)
2. Każdy krok ma jednego wykonawcę
3. Kroki w logicznej kolejności z określonymi zależnościami
4. Zadania wymagające wiedzy technologicznej rozpoczynają się od RESEARCHER
5. Infrastruktura (bazy danych, cache) zarządzana przez CODER + ComposeSkill

**Format Planu (ExecutionPlan):**
```json
{
  "steps": [
    {
      "step_number": 1,
      "agent_type": "RESEARCHER",
      "instruction": "Znajdź dokumentację PyGame dot. kolizji i renderowania",
      "depends_on": null
    },
    {
      "step_number": 2,
      "agent_type": "CODER",
      "instruction": "Stwórz plik game.py z podstawową strukturą gry Snake",
      "depends_on": 1
    }
  ]
}
```

### 2. Przykłady Planów

**Przykład 1: Aplikacja webowa z bazą danych**
```
Zadanie: "Stwórz API REST z Redis cache"
Plan:
1. RESEARCHER - Znajdź dokumentację FastAPI i Redis client
2. CODER - Stwórz docker-compose.yml (api + redis) i uruchom stack
3. CODER - Zaimplementuj endpoints API z integracją Redis
```

**Przykład 2: Gra w PyGame**
```
Zadanie: "Stwórz grę Snake w PyGame"
Plan:
1. RESEARCHER - Znajdź dokumentację PyGame (kolizje, renderowanie)
2. CODER - Stwórz strukturę gry (main loop, klasy)
3. CODER - Zaimplementuj logikę węża i jedzenia
4. CODER - Dodaj system punktacji i game over
```

**Przykład 3: Nowe narzędzie**
```
Zadanie: "Dodaj możliwość wysyłania emaili"
Plan:
1. TOOLMAKER - Stwórz EmailSkill z metodami send_email, validate_email
2. CODER - Zintegruj EmailSkill z systemem
```

## Integracja z Systemem

### Przepływ Wykonania

```
Użytkownik: "Stwórz aplikację TODO z FastAPI + PostgreSQL"
        ↓
IntentManager: COMPLEX_PLANNING
        ↓
ArchitectAgent.plan_execution()
        ↓
ExecutionPlan (4 kroki):
  1. RESEARCHER - Dokumentacja FastAPI + PostgreSQL
  2. CODER - docker-compose.yml + uruchomienie stacka
  3. CODER - Modele SQLAlchemy + połączenie DB
  4. CODER - Endpoints CRUD dla TODO
        ↓
TaskDispatcher wykonuje kroki sekwencyjnie
        ↓
Wynik: Działająca aplikacja w Docker Compose
```

### Współpraca z Innymi Agentami

- **TaskDispatcher** - Przekazuje plan do wykonania krok po kroku
- **ResearcherAgent** - Dostarcza wiedzę techniczną na początku projektu
- **CoderAgent** - Implementuje kod zgodnie z instrukcjami
- **LibrarianAgent** - Sprawdza istniejące pliki przed rozpoczęciem pracy
- **ToolmakerAgent** - Tworzy brakujące narzędzia na żądanie planu

## Konfiguracja

```bash
# W .env (brak dedykowanych flag dla Architect)
# Architect jest zawsze dostępny w trybie COMPLEX_PLANNING
```

## Metryki i Monitoring

**Kluczowe wskaźniki:**
- Średnia liczba kroków w planie (optymalnie 3-7)
- Współczynnik sukcesu planu (% planów zakończonych bez błędów)
- Czas planowania (zazwyczaj <10s)
- Wykorzystanie różnych typów agentów (balans RESEARCHER/CODER/LIBRARIAN)

## Best Practices

1. **Rozpocznij od badań** - Złożone projekty powinny mieć krok RESEARCHER na początku
2. **Infrastruktura najpierw** - Stack Docker Compose przed kodem aplikacji
3. **Małe kroki** - Lepiej 5 małych kroków niż 2 duże
4. **Jasne instrukcje** - Każdy krok powinien być konkretny i zrozumiały
5. **Zależności** - Używaj `depends_on` do wymuszenia kolejności

## Znane Ograniczenia

- Plan jest liniowy (brak równoległego wykonania kroków)
- Brak automatycznej optymalizacji planu po niepowodzeniu kroku
- Maksymalna głębokość planowania: 1 poziom (brak zagnieżdżonych podplanów)

## Zobacz też

- [THE_CODER.md](THE_CODER.md) - Implementacja kodu
- [THE_RESEARCHER.md](THE_RESEARCHER.md) - Zbieranie wiedzy
- [THE_HIVE.md](THE_HIVE.md) - Rozproszone wykonanie planów
- [INTENT_RECOGNITION.md](INTENT_RECOGNITION.md) - Klasyfikacja intencji
