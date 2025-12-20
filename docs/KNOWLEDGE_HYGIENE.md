# Knowledge Hygiene Suite - Dokumentacja

## Przegląd

Knowledge Hygiene Suite to zestaw narzędzi zapobiegający zanieczyszczeniu systemu RAG "anty-wiedzą" podczas testów i debugowania. Składa się z dwóch głównych komponentów:

1. **Lab Mode (Memory Freeze)** - tryb efemeryczny dla zadań testowych
2. **Knowledge Pruning API** - narzędzia do czyszczenia zapisanej wiedzy

## Lab Mode (Tryb Laboratoryjny)

### Opis

Lab Mode pozwala na wykonywanie zadań bez trwałego zapisu lekcji do `LessonsStore`. Jest to niezbędne podczas:
- Testowania nowych funkcji
- Debugowania problemów
- Eksperymentowania z promptami
- Stabilizacji systemu

### Użycie w UI

1. Otwórz Venom Cockpit
2. Przy polu wprowadzania zadania zaznacz checkbox **🧪 Lab Mode**
3. Wprowadź zadanie i wyślij
4. System wykona zadanie normalnie, ale NIE zapisze lekcji do pamięci

### Użycie w API

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/tasks",
    json={
        "content": "Testowe zadanie",
        "store_knowledge": False  # Lab Mode włączony
    }
)
```

### Implementacja

```python
# venom_core/core/models.py
class TaskRequest(BaseModel):
    content: str
    store_knowledge: bool = True  # Domyślnie zapisuje wiedzę
```

## Knowledge Pruning API

### Endpointy

#### 1. Usuń n najnowszych lekcji

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/latest?count=5"
```

**Parametry:**
- `count` (wymagany): Liczba najnowszych lekcji do usunięcia

**Przykładowa odpowiedź:**
```json
{
  "status": "success",
  "message": "Usunięto 5 najnowszych lekcji",
  "deleted": 5
}
```

#### 2. Usuń lekcje z zakresu czasu

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/range?start=2024-01-01T00:00:00&end=2024-01-31T23:59:59"
```

**Parametry:**
- `start` (wymagany): Data początkowa w formacie ISO 8601
- `end` (wymagany): Data końcowa w formacie ISO 8601

**Obsługiwane formaty dat:**
- `2024-01-01T00:00:00`
- `2024-01-01T00:00:00Z`
- `2024-01-01T00:00:00+00:00`

**Przykładowa odpowiedź:**
```json
{
  "status": "success",
  "message": "Usunięto 12 lekcji z zakresu 2024-01-01T00:00:00 - 2024-01-31T23:59:59",
  "deleted": 12,
  "start": "2024-01-01T00:00:00",
  "end": "2024-01-31T23:59:59"
}
```

#### 3. Usuń lekcje po tagu

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/tag?tag=błąd"
```

**Parametry:**
- `tag` (wymagany): Tag do wyszukania

**Przykładowa odpowiedź:**
```json
{
  "status": "success",
  "message": "Usunięto 8 lekcji z tagiem 'błąd'",
  "deleted": 8,
  "tag": "błąd"
}
```

#### 4. Wyczyść całą bazę lekcji (NUCLEAR)

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/purge?force=true"
```

**Parametry:**
- `force` (wymagany): Musi być `true` dla potwierdzenia

**⚠️ UWAGA:** Ta operacja jest nieodwracalna!

**Przykładowa odpowiedź:**
```json
{
  "status": "success",
  "message": "💣 Wyczyszczono całą bazę lekcji (47 lekcji)",
  "deleted": 47
}
```

#### 5. TTL - usuń lekcje starsze niż N dni

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/ttl?days=30"
```

**Parametry:**
- `days` (wymagany): Liczba dni retencji

**Przykładowa odpowiedź:**
```json
{
  "status": "success",
  "message": "Usunięto 12 lekcji starszych niż 30 dni",
  "deleted": 12,
  "days": 30
}
```

#### 6. Deduplikacja lekcji

```bash
curl -X POST "http://localhost:8000/api/v1/memory/lessons/dedupe"
```

**Przykładowa odpowiedź:**
```json
{
  "status": "success",
  "message": "Usunięto 4 zduplikowanych lekcji",
  "removed": 4
}
```

#### 7. Globalny przełącznik uczenia

```bash
curl "http://localhost:8000/api/v1/memory/lessons/learning/status"
curl -X POST "http://localhost:8000/api/v1/memory/lessons/learning/toggle" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Przykładowa odpowiedź:**
```json
{
  "status": "success",
  "enabled": false
}
```

## Przykłady użycia

### Scenario 1: Czyszczenie po sesji testowej

Po zakończeniu sesji testowej, usuń wszystkie lekcje z tego okresu:

```python
from datetime import datetime, timedelta
import requests

# Sesja testowa trwała 2 godziny
end_time = datetime.now()
start_time = end_time - timedelta(hours=2)

response = requests.delete(
    "http://localhost:8000/api/v1/memory/lessons/prune/range",
    params={
        "start": start_time.isoformat(),
        "end": end_time.isoformat()
    }
)
print(f"Usunięto {response.json()['deleted']} lekcji testowych")
```

### Scenario 2: Usuwanie błędnych lekcji

Usuń wszystkie lekcje oznaczone jako błędy:

```bash
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/tag?tag=błąd"
```

### Scenario 3: Reset przed nową wersją

Przed wdrożeniem nowej wersji systemu, wyczyść starą wiedzę:

```bash
# UWAGA: To usuwa WSZYSTKO!
curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/purge?force=true"
```

## Bezpieczeństwo

### Thread Safety

Wszystkie operacje pruningowe są thread-safe:
```python
# Używamy kopii kluczy słownika
for lesson_id in list(self.lessons.keys()):
    # Bezpieczna iteracja
```

### Data Validation

- Daty są walidowane przed parsowaniem
- Niepoprawne formaty zwracają HTTP 400 z opisem błędu
- Puste stringi są odrzucane

### Persistence

Wszystkie operacje automatycznie zapisują zmiany na dysku gdy `auto_save=True`.

## Testowanie

### Unit Tests

```bash
# Z katalogu głównego projektu
python -m pytest tests/test_knowledge_hygiene.py -v
```

### Manual Testing

1. **Test Lab Mode:**
   - Włącz Lab Mode w UI
   - Wyślij zadanie testowe
   - Sprawdź `data/memory/lessons.json` - nie powinno być nowego wpisu

2. **Test Pruning:**
   ```bash
   # Dodaj testowe lekcje
   # Następnie usuń je
   curl -X DELETE "http://localhost:8000/api/v1/memory/lessons/prune/latest?count=1"
   ```

## Troubleshooting

### Problem: Lekcje nadal są zapisywane w Lab Mode

**Rozwiązanie:**
- Sprawdź czy checkbox jest zaznaczony
- Sprawdź console.log czy `store_knowledge` jest `false`
- Sprawdź czy `ENABLE_META_LEARNING` jest `True` w konfiguracji

### Problem: Błąd parsowania daty

**Rozwiązanie:**
- Użyj formatu ISO 8601: `YYYY-MM-DDTHH:MM:SS`
- System obsługuje również suffix `Z` (UTC)

### Problem: Nie można usunąć lekcji

**Rozwiązanie:**
- Sprawdź czy LessonsStore jest zainicjalizowany
- Sprawdź logi: `tail -f logs/venom.log`
- Sprawdź uprawnienia do pliku `data/memory/lessons.json`

## Najlepsze praktyki

1. **Zawsze używaj Lab Mode podczas testowania nowych funkcji**
2. **Regularnie przeglądaj i czyść błędne lekcje**
3. **Twórz backup przed operacją purge:**
   ```bash
   cp data/memory/lessons.json data/memory/lessons.json.backup
   ```
4. **Używaj tagów do kategoryzacji lekcji**
5. **Dokumentuj sesje testowe z zakresami czasu**

## API Reference

### LessonsStore Methods

```python
class LessonsStore:
    def delete_last_n(self, n: int) -> int:
        """Usuwa n najnowszych lekcji."""

    def delete_by_time_range(self, start: datetime, end: datetime) -> int:
        """Usuwa lekcje z zakresu czasu."""

    def delete_by_tag(self, tag: str) -> int:
        """Usuwa lekcje z danym tagiem."""

    def clear_all(self) -> bool:
        """Czyści całą bazę lekcji."""
```

## Changelog

### v1.0.0 (2025-12-10)
- ✨ Dodano Lab Mode (Memory Freeze)
- ✨ Dodano Knowledge Pruning API
- ✨ Dodano UI checkbox dla Lab Mode
- 🐛 Naprawiono parsing ISO 8601 z 'Z' suffix
- 🔧 Wydzielono metodę `_should_store_lesson()`
- ✅ Dodano unit tests

## Zobacz także

- [LessonsStore Documentation](./lessons_store.md)
- [API Documentation](./api.md)
- [Testing Guidelines](./testing.md)
