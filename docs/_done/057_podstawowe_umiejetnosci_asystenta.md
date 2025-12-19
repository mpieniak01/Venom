# ZADANIE 057: Podstawowe umiejętności asystenta

## Status: ✅ UKOŃCZONE

## Cel
Dopisać bazowe umiejętności, które powinny być zawsze dostępne w asystencie.

## Zaimplementowane umiejętności

### 1. AssistantSkill - Podstawowy Skill Asystenta

Lokalizacja: `venom_core/execution/skills/assistant_skill.py`

#### Funkcje:

##### `get_current_time(format_type: str = "full") -> str`
Zwraca aktualny czas lokalny.

**Parametry:**
- `format_type`: Format odpowiedzi
  - `"short"` - tylko godzina (HH:MM)
  - `"full"` - pełna data, godzina i strefa czasowa (domyślnie)

**Przykłady użycia:**
```python
# Format krótki
result = await assistant_skill.get_current_time(format_type="short")
# 🕐 Aktualna godzina: 14:30

# Format pełny
result = await assistant_skill.get_current_time()
# 📅 Środa, 2025-12-19
# 🕐 Godzina: 14:30:45
# Strefa czasowa: UTC
```

**Cechy:**
- Nie wymaga konfiguracji
- Automatycznie tłumaczy nazwy dni na polski
- Pokazuje strefę czasową systemu

##### `get_weather(location: str, units: str = "metric") -> str`
Zwraca aktualną pogodę dla podanej lokalizacji.

**Parametry:**
- `location`: Nazwa miasta lub lokalizacji (np. "Warszawa", "London")
- `units`: System jednostek
  - `"metric"` - Celsjusz (domyślnie)
  - `"imperial"` - Fahrenheit

**Przykłady użycia:**
```python
result = await assistant_skill.get_weather(location="Warsaw")
# 🌤️  Pogoda dla: Warsaw, Poland
#
# 🌡️  Temperatura: 15°C (odczuwalna: 13°C)
# ☁️  Warunki: Partly cloudy
# 💧 Wilgotność: 65%
# 💨 Wiatr: 10 km/h (NW)
```

**Cechy:**
- Używa darmowego API wttr.in - **nie wymaga klucza API**
- Działa bez dodatkowej konfiguracji
- Automatycznie wykrywa najbliższą lokalizację
- Timeout: 10 sekund
- Pokazuje temperaturę odczuwalną, wilgotność, wiatr

##### `check_services(detailed: bool = False) -> str`
Sprawdza status uruchomionych usług systemowych.

**Parametry:**
- `detailed`: Czy pokazać szczegółowe informacje o każdej usłudze

**Przykłady użycia:**
```python
# Podstawowe podsumowanie
result = await assistant_skill.check_services(detailed=False)
# 🔍 Status usług systemowych
#
# ✅ Online: 3/5
# ❌ Offline: 2/5
#
# ⚠️  UWAGA: Krytyczne usługi offline:
#   • Local LLM

# Szczegółowe informacje
result = await assistant_skill.check_services(detailed=True)
# ... podsumowanie jak wyżej, plus:
#
# 📋 Szczegóły usług:
#
# ✅ Local LLM
#    Typ: api
#    Endpoint: http://localhost:11434/v1/models
#    Latencja: 42.50ms
#
# ❌ Docker Daemon
#    Typ: docker
#    Błąd: Connection refused
```

**Cechy:**
- Sprawdza wszystkie zarejestrowane usługi systemowe
- Wykrywa usługi krytyczne (LLM, Docker, itp.)
- Pokazuje latencję i szczegóły błędów
- Integracja z `ServiceHealthMonitor`

## Wymagania i zależności

**Bez dodatkowej konfiguracji:**
- `get_current_time` - działa natychmiast po instalacji
- `get_weather` - wymaga połączenia internetowego
- `check_services` - korzysta z istniejącego `ServiceRegistry`

**Zależności (już zainstalowane w projekcie):**
- `aiohttp` - dla zapytań HTTP (pogoda)
- `semantic_kernel` - dekoratory funkcji
- `datetime` - obsługa czasu (stdlib)

## Testy

Lokalizacja: `tests/test_assistant_skill.py`

**Pokrycie testów:**
- ✅ Inicjalizacja skill
- ✅ Pobieranie czasu w formacie krótkim
- ✅ Pobieranie czasu w formacie pełnym
- ✅ Domyślny format czasu
- ✅ Pobieranie pogody - sukces
- ✅ Pobieranie pogody - jednostki imperialne
- ✅ Pobieranie pogody - lokalizacja nie znaleziona
- ✅ Pobieranie pogody - timeout
- ✅ Sprawdzanie usług - podstawowe
- ✅ Sprawdzanie usług - szczegółowe
- ✅ Sprawdzanie usług - krytyczna offline
- ✅ Sprawdzanie usług - pusty rejestr
- ✅ Sprawdzanie usług - z latencją
- ✅ Sprawdzanie usług - z błędami
- ✅ Obsługa wyjątków

**Wynik testów:** 15/15 passed ✅

## Integracja

Skill został dodany do:
- `venom_core/execution/skills/__init__.py` - lazy import jako `AssistantSkill`

**Jak używać:**
```python
from venom_core.execution.skills import AssistantSkill

# Podstawowa inicjalizacja
assistant = AssistantSkill()

# Z własnym rejestrem usług (opcjonalnie)
from venom_core.core.service_monitor import ServiceRegistry
registry = ServiceRegistry()
assistant = AssistantSkill(service_registry=registry)

# Użycie funkcji
time_result = await assistant.get_current_time()
weather_result = await assistant.get_weather(location="Warszawa")
services_result = await assistant.check_services(detailed=True)
```

## Zgodność z zasadami Venom v2

✅ **Komunikacja po polsku** - komentarze i komunikaty w języku polskim  
✅ **Format/styl** - kod przeszedł przez Black, Ruff, isort  
✅ **Testy** - pełne pokrycie testami jednostkowymi z pytest  
✅ **Konfiguracja** - brak hardcoded secrets, fallbacki dla opcji  
✅ **Dokumentacja** - pełna dokumentacja API i przykłady użycia  
✅ **Brak ciężkich zależności** - wykorzystanie istniejących bibliotek  

## Różnice względem istniejących skills

**ChronoSkill** (`chrono_skill.py`):
- Zarządza timeline/checkpointy/state
- AssistantSkill jest prostszy - tylko podstawowe info

**Inne skills** nie pokrywają się z funkcjonalnością AssistantSkill:
- Czas lokalny - nowa funkcjonalność
- Pogoda - nowa funkcjonalność (WebSkill ma wyszukiwanie, nie pogodę)
- Status usług - wykorzystuje istniejący ServiceMonitor, ale z user-friendly interfejsem

## Dalszy rozwój (opcjonalnie)

Możliwe rozszerzenia w przyszłości:
- [ ] Integracja z wieloma serwisami pogodowymi
- [ ] Cache dla pogody (unikanie nadmiernych zapytań)
- [ ] Personalizacja formatów czasowych
- [ ] Alerty przy krytycznych usługach offline
- [ ] Historia statusów usług

## Podsumowanie

Wszystkie trzy podstawowe umiejętności zostały zaimplementowane zgodnie z wymaganiami:

1. ✅ **"Podaj godzinę"** - `get_current_time()` - zwraca aktualny czas lokalny
2. ✅ **"Podaj pogodę"** - `get_weather()` - zwraca pogodę dla lokalizacji  
3. ✅ **"Sprawdź usługi"** - `check_services()` - podsumowanie statusu usług

**Działają bez dodatkowej konfiguracji po instalacji.**  
**Wyniki są krótkie i jednoznaczne, z opcją rozszerzenia szczegółów.**
