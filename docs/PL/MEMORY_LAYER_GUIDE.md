# Przewodnik: Warstwa Pamięci i Meta-Uczenia

Ten przewodnik opisuje wyłącznie pamięć i meta-uczenie. Aby zacząć workflow Copilot chatu w Venom, użyj `THE_CHAT.md` i `CHAT_OPERATOR.md`.

## Przegląd

Venom v1.0 został rozszerzony o zaawansowaną warstwę pamięci, która przekształca system z prostego "wyszukiwania tekstowego" w inteligentną "sieć powiązań" z możliwością uczenia się na błędach.

## Komponenty

### 1. CodeGraphStore - Graf Wiedzy o Kodzie

**Lokalizacja:** `venom_core/memory/graph_store.py`

Graf wiedzy analizuje strukturę kodu projektu używając AST (Abstract Syntax Tree) i buduje graf zależności między plikami, klasami i funkcjami.

#### Kluczowe funkcje:

- **Skanowanie workspace:** Automatyczne skanowanie wszystkich plików Python w projekcie
- **Ekstrakcja węzłów:** Pliki, klasy, funkcje, metody
- **Ekstrakcja krawędzi:** IMPORTS, INHERITS_FROM, CALLS, CONTAINS
- **Analiza zależności:** Wykrywanie plików zależnych od danego pliku
- **Impact Analysis:** Określanie wpływu usunięcia/modyfikacji pliku

#### Przykład użycia:

```python
from venom_core.memory.graph_store import CodeGraphStore

# Inicjalizacja
graph_store = CodeGraphStore()

# Skanowanie workspace
stats = graph_store.scan_workspace()
print(f"Znaleziono {stats['nodes']} węzłów, {stats['edges']} krawędzi")

# Analiza wpływu
impact = graph_store.get_impact_analysis("venom_core/core/orchestrator.py")
print(f"Usunięcie tego pliku wpłynie na {impact['impact_score']} plików")

# Informacje o pliku
info = graph_store.get_file_info("venom_core/agents/coder.py")
print(f"Klasy: {len(info['classes'])}, Funkcje: {len(info['functions'])}")

# Zapisz/załaduj graf
graph_store.save_graph()
graph_store.load_graph()
```

#### API Endpoints:

- `GET /api/v1/graph/summary` - Podsumowanie grafu (liczba węzłów, krawędzi, typy)
- `GET /api/v1/graph/file/{path}` - Informacje o pliku z grafu
- `GET /api/v1/graph/impact/{path}` - Analiza wpływu usunięcia pliku
- `POST /api/v1/graph/scan` - Wyzwolenie manualnego skanowania

#### Kontrakt odpowiedzi `/api/v1/graph/summary` (standaryzacja)
Endpoint zwraca ustandaryzowany obiekt `summary` (snake_case) oraz pola na poziomie root dla kompatybilności wstecznej:

```json
{
  "status": "success",
  "summary": {
    "nodes": 123,
    "edges": 456,
    "last_updated": "2026-01-30T12:34:56+00:00",
    "total_nodes": 123,
    "total_edges": 456
  },
  "nodes": 123,
  "edges": 456,
  "lastUpdated": "2026-01-30T12:34:56+00:00"
}
```

Zalecenie: nowy kod powinien używać pól z `summary`, a `nodes/edges/lastUpdated` traktować jako legacy.

### 2. LessonsStore - Magazyn Lekcji

**Lokalizacja:** `venom_core/memory/lessons_store.py`

Magazyn lekcji przechowuje doświadczenia Venoma - zarówno sukcesy jak i porażki. Każda lekcja zawiera:

- **Situation:** Opis sytuacji/zadania
- **Action:** Co zostało zrobione
- **Result:** Rezultat (sukces/błąd)
- **Feedback:** Wnioski i co poprawić
- **Tags:** Tagi do kategoryzacji
- **Metadata:** Dodatkowe informacje (timestamp, task_id, etc.)

#### Przykład użycia:

```python
from venom_core.memory.lessons_store import LessonsStore

# Inicjalizacja (z opcjonalnym vector_store do semantycznego wyszukiwania)
lessons_store = LessonsStore(vector_store=vector_store)

# Dodanie lekcji
lesson = lessons_store.add_lesson(
    situation="Próba użycia biblioteki requests",
    action="Wygenerowano kod z metodą requests.post()",
    result="BŁĄD: SSL Certificate verification failed",
    feedback="W przyszłości dodaj parametr verify=False lub użyj kontekstu SSL",
    tags=["requests", "ssl", "błąd"]
)

# Wyszukiwanie semantyczne
lessons = lessons_store.search_lessons(
    query="problemy z certyfikatami SSL",
    limit=3
)

# Pobieranie po tagach
error_lessons = lessons_store.get_lessons_by_tags(["błąd"])

# Statystyki
stats = lessons_store.get_statistics()
print(f"Łącznie lekcji: {stats['total_lessons']}")
print(f"Najczęstsze tagi: {stats['tag_distribution']}")
```

#### API Endpoints:

- `GET /api/v1/lessons?limit=10&tags=python,error` - Lista lekcji
- `GET /api/v1/lessons/stats` - Statystyki magazynu lekcji

### 3. GardenerAgent - Agent Ogrodnik

**Lokalizacja:** `venom_core/agents/gardener.py`

Agent Ogrodnik działa w tle i automatycznie aktualizuje graf wiedzy gdy wykryje zmiany w plikach workspace.

#### Funkcje:

- **Monitoring plików:** Sprawdzanie zmian w plikach Python
- **Auto-reindeksacja:** Automatyczna aktualizacja grafu po zmianach
- **Background service:** Działa asynchronicznie bez blokowania głównego wątku
- **Manualne skanowanie:** Możliwość wywołania skanowania na żądanie

#### Przykład użycia:

```python
from venom_core.agents.gardener import GardenerAgent
from venom_core.memory.graph_store import CodeGraphStore

# Inicjalizacja
graph_store = CodeGraphStore()
gardener = GardenerAgent(
    graph_store=graph_store,
    scan_interval=300  # Skanuj co 5 minut
)

# Uruchomienie w tle
await gardener.start()

# Status
status = gardener.get_status()
print(f"Running: {status['is_running']}")
print(f"Last scan: {status['last_scan_time']}")

# Manualne skanowanie
stats = gardener.trigger_manual_scan()

# Zatrzymanie
await gardener.stop()
```

#### API Endpoints:

- `GET /api/v1/gardener/status` - Status agenta Ogrodnika

### 4. Semantic Cache (Hidden Prompts)

**Lokalizacja:** `venom_core/core/hidden_prompts.py`

Mechanizm Semantic Cache służy do optymalizacji czatu poprzez zapamiętywanie zatwierdzonych par Pytanie-Odpowiedź i serwowanie ich dla semantycznie podobnych zapytań bez angażowania LLM.

#### Działanie:
1.  **Exact Match:** Najpierw sprawdza dokładne dopasowanie w plikach JSONL.
2.  **Semantic Match:** Jeśli brak dokładnego dopasowania, przeszukuje wektorową bazę danych (LanceDB).
3.  **Threshold:** Akceptuje wynik tylko, gdy podobieństwo (cosine similarity) przekracza `SEMANTIC_CACHE_THRESHOLD` (domyślnie 0.85).

#### Konfiguracja (constants.py):
- `SEMANTIC_CACHE_THRESHOLD = 0.85`
- `SEMANTIC_CACHE_COLLECTION_NAME = "hidden_prompts"`

#### Integracja:
Cache wykorzystuje `VectorStore` (tę samą klasę co Memory/Lessons) oraz model embeddingów `sentence-transformers/all-MiniLM-L6-v2`.

### 5. Orchestrator - Pętla Meta-Uczenia

**Lokalizacja:** `venom_core/core/orchestrator.py`

Orchestrator został rozszerzony o mechanizm meta-uczenia:

#### Pre-Flight Check:

Przed rozpoczęciem zadania, Orchestrator:
1. Wyszukuje relevantne lekcje z przeszłości
2. Dołącza je do kontekstu zadania jako ostrzeżenia
3. Agent widzi "Nauczyłem się wcześniej..." w promptcie

#### Refleksja Post-Task:

Po zakończeniu zadania (sukces lub porażka), Orchestrator:
1. Analizuje wyniki i logi
2. Tworzy lekcję z doświadczenia
3. Zapisuje w LessonsStore
4. Indeksuje dla przyszłego wyszukiwania

#### Konfiguracja:

```python
# W venom_core/core/orchestrator.py
ENABLE_META_LEARNING = True  # Włącz/wyłącz meta-uczenie
MAX_LESSONS_IN_CONTEXT = 3   # Ile lekcji dołączać do promptu
```

#### Przykładowy flow:

```
Zadanie 1: "Napisz kod używający biblioteki X"
→ Venom generuje kod z przestarzałą metodą
→ BŁĄD: Method X.old_method() not found
→ Lekcja zapisana: "Biblioteka X w wersji Y nie ma metody old_method()"

---

Zadanie 2 (Nowa sesja): "Napisz kod używający biblioteki X"
→ Pre-flight check znajduje lekcję
→ Prompt zawiera: "📚 LEKCJE: Uważaj, metoda old_method() nie istnieje w wersji Y"
→ Venom od razu generuje poprawny kod z nową metodą
→ SUKCES ✅
```

## Dashboard - Wizualizacja

### Nowa zakładka "Memory"

Dashboard został rozszerzony o zakładkę "🧠 Memory" z dwiema sekcjami:

#### 1. Lekcje (📚)

- Lista ostatnich 10 lekcji
- Kolorowanie: zielony = sukces, czerwony = błąd
- Wyświetla: sytuację, feedback, tagi
- Przycisk odświeżania

#### 2. Graf Wiedzy (🕸️)

- Statystyki grafu:
  - Liczba węzłów (nodes)
  - Liczba krawędzi (edges)
  - Pliki, klasy, funkcje
- Przycisk "Skanuj" do manualnej aktualizacji

### Dostęp:

1. Uruchom Venom: `uvicorn venom_core.main:app --reload`
2. Otwórz przeglądarkę: `http://localhost:8000`
3. Przełącz się na zakładkę "🧠 Memory"

## Testy

### Uruchomienie testów:

```bash
# Wszystkie testy pamięci
pytest tests/test_graph_store.py tests/test_lessons_store.py -v

# Tylko graph_store
pytest tests/test_graph_store.py -v

# Tylko lessons_store
pytest tests/test_lessons_store.py -v
```

### Pokrycie testami:

- **CodeGraphStore:** 11 testów jednostkowych
- **LessonsStore:** 16 testów jednostkowych
- **Łącznie:** 27 testów, 100% pass rate

## Wymagania

### Minimalne zależności:

```
networkx>=3.0          # Graf in-memory
pydantic>=2.7,<3.0    # Walidacja
python-dotenv         # Konfiguracja
```

### Opcjonalne (dla pełnej funkcjonalności):

```
lancedb              # Vector store (dla semantycznego wyszukiwania lekcji)
sentence-transformers # Embeddingi
```

## Konfiguracja

### Zmienne środowiskowe (.env):

```bash
# Workspace
WORKSPACE_ROOT=./workspace

# Pamięć
MEMORY_ROOT=./data/memory

# Meta-uczenie (w kodzie)
ENABLE_META_LEARNING=True
MAX_LESSONS_IN_CONTEXT=3
```

### Ścieżki plików:

- Graf: `data/memory/code_graph.json`
- Lekcje: `data/memory/lessons.json`
- Vector DB: `data/memory/lancedb/`

## Najlepsze praktyki

### 1. Regularne skanowanie

```python
# Skanuj workspace przy starcie aplikacji
graph_store.scan_workspace()

# Lub uruchom GardenerAgent dla auto-aktualizacji
await gardener.start()
```

### 2. Tagowanie lekcji

Używaj spójnych tagów dla łatwiejszego wyszukiwania:
- Język: `python`, `javascript`
- Typ: `błąd`, `sukces`, `ostrzeżenie`
- Obszar: `api`, `database`, `ml`
- Biblioteka: `requests`, `pandas`, `pytorch`

### 3. Czyszczenie starych lekcji

```python
# Usuń przestarzałe lekcje
old_lessons = lessons_store.get_all_lessons(limit=None)
for lesson in old_lessons:
    if should_delete(lesson):
        lessons_store.delete_lesson(lesson.lesson_id)
```

### 4. Backup

```python
# Graf i lekcje są automatycznie zapisywane do JSON
# Backup regularnie te pliki:
import shutil
from datetime import datetime

backup_dir = f"./backups/{datetime.now().strftime('%Y%m%d')}"
shutil.copy("data/memory/code_graph.json", backup_dir)
shutil.copy("data/memory/lessons.json", backup_dir)
```

## Troubleshooting

### Graf nie aktualizuje się automatycznie

Sprawdź czy GardenerAgent jest uruchomiony:
```bash
curl http://localhost:8000/api/v1/gardener/status
```

### Lekcje nie są wyszukiwane semantycznie

Upewnij się że VectorStore jest zainicjalizowany:
```python
vector_store = VectorStore()
lessons_store = LessonsStore(vector_store=vector_store)
```

### Wysokie użycie pamięci przy dużym grafie

Rozważ:
1. Filtrowanie plików (ignoruj `__pycache__`, `venv`)
2. Okresowe czyszczenie grafu
3. Zapisywanie tylko najważniejszych metadanych

## Dalszy rozwój

Planowane rozszerzenia:

1. **Wizualizacja grafu** - Interaktywna wizualizacja z `vis.js` lub `d3.js`
2. **Export grafu** - Do formatów GraphML, GEXF
3. **Zaawansowane query** - Cypher-like query language dla grafu
4. **Clustering lekcji** - Automatyczne grupowanie podobnych lekcji
5. **Confidence scoring** - Ocena pewności lekcji na podstawie liczby użyć

## Licencja

Ten moduł jest częścią projektu Venom i podlega tej samej licencji co główny projekt.
