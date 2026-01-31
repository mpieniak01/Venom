# THE CODER - Code Generation & Implementation

## Rola

Coder Agent to główny wykonawca implementacyjny w systemie Venom. Generuje czysty, udokumentowany kod, tworzy pliki w workspace, zarządza środowiskami Docker Compose i wykonuje komendy shell w bezpiecznym środowisku.

## Odpowiedzialności

- **Generowanie kodu** - Tworzenie kompletnego, gotowego do użycia kodu
- **Zarządzanie plikami** - Zapisywanie, odczyt, sprawdzanie istnienia plików
- **Orkiestracja Docker Compose** - Tworzenie stacków wielokontenerowych
- **Wykonywanie poleceń** - Bezpieczne uruchamianie komend shell
- **Samonaprawa** - Automatyczne wykrywanie i naprawa błędów w kodzie (opcjonalne)

## Kluczowe Komponenty

### 1. Dostępne Narzędzia

**FileSkill** (`venom_core/execution/skills/file_skill.py`):
- `write_file(path, content)` - Zapisuje kod do pliku w workspace
- `read_file(path)` - Odczytuje istniejący kod
- `list_files(directory)` - Listuje pliki w katalogu
- `file_exists(path)` - Sprawdza czy plik istnieje

**ShellSkill** (`venom_core/execution/skills/shell_skill.py`):
- `run_shell(command)` - Wykonuje komendę shell w sandbox

**ComposeSkill** (`venom_core/execution/skills/compose_skill.py`):
- `create_environment(name, compose_content, auto_start)` - Tworzy środowisko Docker Compose
- `destroy_environment(name)` - Usuwa środowisko i czyści zasoby
- `check_service_health(env_name, service_name)` - Sprawdza status i logi serwisu
- `list_environments()` - Lista aktywnych środowisk
- `get_environment_status(name)` - Szczegółowy status środowiska

### 2. Zasady Działania

**Generowanie kodu:**
1. Kod powinien być kompletny i gotowy do użycia
2. Komentarze tylko gdy logika jest złożona
3. Zgodność z dobrymi praktykami i konwencjami nazewnictwa
4. Użycie `write_file()` do fizycznego zapisu kodu (nie tylko markdown)

**Infrastruktura:**
- Gdy zadanie wymaga bazy danych, cache lub kolejki → `create_environment()` z docker-compose.yml
- Serwisy komunikują się przez nazwy sieciowe (np. `host='redis'`, `host='postgres'`)
- Stack jest izolowany w sieci Docker, dostępny z hosta przez mapowane porty

**Samonaprawa (opcjonalna):**
- Automatyczne wykrywanie błędów kompilacji/runtime
- Próba naprawy kodu (max 3 iteracje)
- Logowanie wszystkich prób naprawy

### 3. Przykłady Użycia

**Przykład 1: Prosty plik Python**
```
Użytkownik: "Stwórz plik hello.py z funkcją Hello World"
Akcja:
1. Generuj kod funkcji
2. write_file("hello.py", kod)
3. Potwierdź zapis
```

**Przykład 2: API z Redis**
```
Użytkownik: "Stwórz FastAPI z cache Redis"
Akcja:
1. Stwórz docker-compose.yml (api + redis)
2. create_environment("fastapi-redis", compose_content, auto_start=True)
3. Stwórz kod API z integracją Redis (host='redis')
4. write_file("main.py", kod)
5. write_file("requirements.txt", zależności)
```

**Przykład 3: Odczyt istniejącego kodu**
```
Użytkownik: "Co jest w pliku config.py?"
Akcja: read_file("config.py")
```

## Integracja z Systemem

### Przepływ Wykonania

```
ArchitectAgent tworzy plan:
  Krok 2: CODER - "Stwórz plik app.py z REST API"
        ↓
TaskDispatcher wywołuje CoderAgent.execute()
        ↓
CoderAgent:
  1. Generuje kod (LLM)
  2. Wywołuje write_file("app.py", kod)
  3. Opcjonalnie: run_shell("python app.py") - test
  4. Zwraca wynik
        ↓
TaskDispatcher przechodzi do następnego kroku
```

### Współpraca z Innymi Agentami

- **ArchitectAgent** - Otrzymuje instrukcje z planu wykonania
- **CriticAgent** - Weryfikuje jakość wygenerowanego kodu
- **LibrarianAgent** - Sprawdza istniejące pliki przed nadpisaniem
- **ResearcherAgent** - Dostarcza dokumentację i przykłady

## Konfiguracja

```bash
# W .env
WORKSPACE_ROOT=./workspace          # Katalog roboczy dla plików
ENABLE_SANDBOX=true                 # Czy uruchamiać kod w sandboxie
DOCKER_IMAGE_NAME=python:3.11-slim  # Obraz dla Docker sandbox
```

## Docker Compose Stack - Best Practices

### Struktura docker-compose.yml

```yaml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - postgres
    networks:
      - app-network

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    networks:
      - app-network

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_PASSWORD: dev_password
    ports:
      - "5432:5432"
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

### Komunikacja między Kontenerami

```python
# W kodzie aplikacji używaj nazw serwisów Docker (nie localhost!)
redis_client = redis.Redis(host='redis', port=6379)  # ✅ Poprawne
redis_client = redis.Redis(host='localhost', port=6379)  # ❌ Nie zadziała w kontenerze

# PostgreSQL connection
db_url = "postgresql://user:pass@postgres:5432/dbname"  # ✅ Poprawne
db_url = "postgresql://user:pass@localhost:5432/dbname"  # ❌ Nie zadziała
```

## Metryki i Monitoring

**Kluczowe wskaźniki:**
- Liczba wygenerowanych plików (per sesja)
- Średni rozmiar generowanego kodu (linie)
- Współczynnik błędów kompilacji/runtime
- Liczba iteracji samonaprawy (średnio)
- Wykorzystanie różnych skills (File/Shell/Compose)

## Best Practices

1. **Fizycznie zapisuj pliki** - Zawsze używaj `write_file()`, nie tylko markdown
2. **Testuj przed zapisem** - Opcjonalnie uruchom kod i sprawdź błędy
3. **Stack przed kodem** - Najpierw `create_environment()`, potem kod aplikacji
4. **Nazwy sieciowe** - W Docker Compose używaj nazw serwisów (nie localhost)
5. **Clean-up** - Użyj `destroy_environment()` gdy stack nie jest już potrzebny

## Znane Ograniczenia

- Samonaprawa ma limit 3 iteracji
- Sandbox Docker ma ograniczony dostęp do systemu plików
- Brak wsparcia dla języków wymagających kompilacji (C++, Rust) - tylko skrypty
- Docker Compose stacki są standalone (brak orchestracji z Kubernetes)

## Zobacz też

- [THE_ARCHITECT.md](THE_ARCHITECT.md) - Planowanie projektów
- [THE_CRITIC.md](THE_CRITIC.md) - Weryfikacja jakości kodu
- [THE_LIBRARIAN.md](THE_LIBRARIAN.md) - Zarządzanie plikami
- [BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md) - Architektura backendu
