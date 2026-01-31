# THE LIBRARIAN - File Management & Project Structure

## Rola

Librarian Agent to bibliotekarz projektu w systemie Venom, specjalizujący się w nawigacji po plikach, zarządzaniu strukturą workspace oraz utrzymywaniu wiedzy o organizacji projektu.

## Odpowiedzialności

- **Nawigacja po plikach** - Listowanie, sprawdzanie istnienia, odczyt plików
- **Zarządzanie wiedzą** - Zapisywanie ważnych informacji o strukturze do pamięci
- **Audyt projektu** - Sprawdzanie co już istnieje przed rozpoczęciem pracy
- **Dokumentacja struktury** - Utrzymywanie mapy plików i katalogów
- **Integracja z pamięcią** - Zapisywanie i przywołanie informacji o plikach

## Kluczowe Komponenty

### 1. Dostępne Narzędzia

**FileSkill** (`venom_core/execution/skills/file_skill.py`):
- `list_files(directory)` - Lista plików i katalogów
- `file_exists(path)` - Sprawdzenie czy plik istnieje
- `read_file(path)` - Odczyt zawartości pliku

**MemorySkill** (`venom_core/memory/memory_skill.py`):
- `memorize(content, tags)` - Zapisanie ważnych informacji (np. struktura, konfiguracja)
- `recall(query)` - Przywołanie informacji z pamięci

### 2. Zasady Działania

**Kiedy używać narzędzi:**
- ✅ Pytania o pliki/struktury w workspace: `list_files`, `read_file`
- ✅ Pytania o dokumentację/konfigurację: `read_file` + opcjonalnie `memorize`
- ✅ Sprawdzenie czy plik istnieje: `file_exists`
- ❌ Pytania ogólne (matematyka, definicje): NIE używaj narzędzi, odpowiedz wprost

**Workflow:**
1. Użytkownik pyta o strukturę → `list_files(".")`
2. Użytkownik pyta o konkretny plik → `file_exists()` lub `read_file()`
3. Czytasz ważny plik (config, docs) → rozważ `memorize()` dla przyszłych zapytań
4. Przed odpowiedzią możesz sprawdzić pamięć: `recall()`

**Przykłady:**
```
Użytkownik: "Jakie mam pliki?"
→ list_files(".") i pokaż wynik

Użytkownik: "Czy istnieje plik test.py?"
→ file_exists("test.py") i odpowiedź

Użytkownik: "Co jest w pliku config.json?"
→ read_file("config.json"), pokaż zawartość
→ Rozważ: memorize("Konfiguracja: ...", tags=["config"])

Użytkownik: "Co to jest trójkąt?"
→ Odpowiedź wprost, NIE używaj list_files
```

### 3. Integracja z Pamięcią

Librarian zapisuje ważne informacje o projekcie do pamięci długoterminowej:

**Co zapisywać:**
- Struktura katalogów (po `list_files` głównego katalogu)
- Zawartość plików konfiguracyjnych (`config.json`, `.env.example`)
- Ważne pliki dokumentacji (`README.md`, `CONTRIBUTING.md`)
- Zależności projektu (`requirements.txt`, `package.json`)

**Tagi:**
- `["project-structure"]` - Struktura katalogów
- `["config"]` - Pliki konfiguracyjne
- `["documentation"]` - Pliki dokumentacji
- `["dependencies"]` - Zależności projektu

## Integracja z Systemem

### Przepływ Wykonania

```
ArchitectAgent tworzy plan:
  Krok 1: LIBRARIAN - "Sprawdź czy istnieje plik app.py"
        ↓
TaskDispatcher wywołuje LibrarianAgent.execute()
        ↓
LibrarianAgent:
  1. file_exists("app.py")
  2. Jeśli istnieje: read_file("app.py") dla szczegółów
  3. Zwraca wynik (tak/nie + opcjonalnie zawartość)
        ↓
ArchitectAgent: Jeśli plik istnieje, pomiń tworzenie, przejdź do edycji
```

### Współpraca z Innymi Agentami

- **ArchitectAgent** - Sprawdzanie istniejących plików przed planowaniem
- **CoderAgent** - Weryfikacja czy plik istnieje przed nadpisaniem
- **ChatAgent** - Odpowiadanie na pytania użytkownika o strukturę projektu
- **MemorySkill** - Długoterminowa pamięć o strukturze projektu

## Przykłady Użycia

### Przykład 1: Audyt Struktury Projektu
```python
# Użytkownik: "Pokaż strukturę projektu"
# Librarian:
files = await list_files(".")
await memorize(f"Struktura główna: {files}", tags=["project-structure"])
# Zwraca: Lista katalogów i plików z opisem
```

### Przykład 2: Sprawdzenie Konfiguracji
```python
# Użytkownik: "Jakie mam zmienne w .env.example?"
# Librarian:
content = await read_file(".env.example")
await memorize(f"Zmienne env: {summary}", tags=["config"])
# Zwraca: Lista zmiennych środowiskowych z opisem
```

### Przykład 3: Przed Tworzeniem Pliku
```python
# ArchitectAgent: Plan - Krok 1: LIBRARIAN - "Sprawdź czy app.py istnieje"
# Librarian:
exists = await file_exists("app.py")
if exists:
    content = await read_file("app.py")
    return f"Plik istnieje. Zawartość: {content[:200]}..."
else:
    return "Plik nie istnieje. Można tworzyć."
```

## Konfiguracja

```bash
# W .env
WORKSPACE_ROOT=./workspace  # Katalog workspace (scope operacji)
MEMORY_ROOT=./data/memory   # Pamięć długoterminowa
```

**Bezpieczeństwo:**
- Wszystkie operacje ograniczone do `WORKSPACE_ROOT`
- Brak dostępu poza workspace (sandbox)
- Tylko odczyt - Librarian NIE może zapisywać/usuwać plików

## Metryki i Monitoring

**Kluczowe wskaźniki:**
- Liczba odczytów plików (per sesja)
- Współczynnik cache hit (% zapytań z pamięci)
- Najczęściej czytane pliki (top 10)
- Liczba zapisów do pamięci (per sesja)

## Best Practices

1. **Pamięć dla konfiguracji** - Zapisuj `config.json`, `.env.example` do pamięci
2. **Struktura projektu** - Po pierwszym `list_files` zapisz strukturę
3. **Weryfikuj przed zapisem** - Zawsze sprawdź `file_exists` przed `write_file` (inny agent)
4. **Nie nadużywaj narzędzi** - Dla pytań ogólnych odpowiadaj wprost
5. **Tagi spójne** - Używaj standaryzowanych tagów dla łatwiejszego wyszukiwania

## Znane Ograniczenia

- Tylko odczyt (brak `write_file`, `delete_file`) - użyj CoderAgent do zapisu
- Scope ograniczony do `WORKSPACE_ROOT` (brak dostępu do systemu plików)
- `list_files` może być wolne dla dużych katalogów (>1000 plików)
- Brak wsparcia dla binarnych plików (tylko tekst)

## Zobacz też

- [THE_CODER.md](THE_CODER.md) - Tworzenie i edycja plików
- [THE_ARCHITECT.md](THE_ARCHITECT.md) - Planowanie z wykorzystaniem audytu
- [MEMORY_LAYER_GUIDE.md](MEMORY_LAYER_GUIDE.md) - Pamięć długoterminowa
- [BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md) - Architektura backendu
