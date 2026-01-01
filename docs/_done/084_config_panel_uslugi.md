# 084: Panel konfiguracji – usługi (status + sterowanie)
Status: **ZREALIZOWANE** ✅

## Cel
Ujednolicić panel usług na `/config`, tak aby:
- jasno rozróżniał **usługi sterowalne** od **tylko informacyjnych**, ✅
- nie pokazywał akcji tam, gdzie backend zwraca tylko placeholder, ✅
- prezentował spójny i prawdziwy obraz stosu Venom (runtime + monitor). ✅

## Zrealizowane zmiany

### Backend
1. **Pole `actionable` w ServiceInfo** (`runtime_controller.py`)
   - Dodano pole `actionable: bool` do dataclass `ServiceInfo`
   - Logika określania actionable: backend, ui, llm_ollama, llm_vllm = `True`, reszta = `False`
   - Usługi z ServiceMonitor (Redis, Docker, LanceDB) automatycznie mają `actionable=False`

2. **Aktualizacja API** (`system.py`)
   - Endpoint `/api/v1/runtime/status` zwraca pole `actionable` dla każdej usługi
   - Usługi z ServiceMonitor otrzymują `actionable=False` przy dodawaniu do listy

### Frontend
3. **Warunkowe wyświetlanie akcji** (`services-panel.tsx`)
   - Dodano pole `actionable: boolean` do interfejsu `ServiceInfo`
   - Dla `actionable=true`: wyświetlane przyciski Start/Stop/Restart
   - Dla `actionable=false`: wyświetlany info badge "Kontrolowane przez konfigurację"

### Testy
4. **Testy jednostkowe** (`test_runtime_controller_api.py`)
   - Zaktualizowano test `test_runtime_status_success` - weryfikacja pola actionable
   - Dodano test `test_runtime_status_with_non_actionable_services` - test rozróżnienia usług sterowalnych i konfigurowalnych

### Dokumentacja
5. **CONFIG_PANEL.md**
   - Dodano sekcję wyjaśniającą typy usług (sterowalne, konfigurowalne, monitorowane)
   - Zaktualizowano dokumentację API z opisem pola `actionable`
   - Dodano opis zachowania UI dla różnych typów usług

## Odpowiedzi na otwarte pytania
- **Czy UI ma też pozwalać na zmianę flag?** - Nie w tym PR. Zmiana flag pozostaje w zakładce "Parametry". Można rozważyć w przyszłości.
- **Pole `actionable` czy `source`?** - Wybrano `actionable` jako prostsze i bardziej czytelne dla UI.
- **Czy `stop_ui` ma rzeczywiście zatrzymywać proces?** - Nie zmieniamy implementacji, pozostaje komunikat (pośrednie sterowanie przez `make stop`).
