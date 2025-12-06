# Venom Dashboard - Instrukcja Uruchomienia

## Opis

Venom Cockpit to dashboard do monitorowania i kontrolowania systemu Venom w czasie rzeczywistym.
Dashboard oferuje:
- **Live Feed**: Strumień zdarzeń systemowych w czasie rzeczywistym przez WebSocket
- **Chat Console**: Interfejs do wysyłania zadań bezpośrednio z przeglądarki
- **Task Monitor**: Lista aktywnych zadań z ich statusem
- **Metrics**: Metryki wydajności systemu (liczba zadań, success rate, uptime)

## Wymagania

- Python 3.10+
- Zainstalowane zależności z `requirements.txt`
- Port 8000 dostępny dla serwera

## Uruchomienie

### 1. Instalacja zależności

```bash
pip install -r requirements.txt
```

### 2. Konfiguracja (opcjonalna)

Utwórz plik `.env` w katalogu głównym projektu:

```env
LLM_SERVICE_TYPE=local
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1
LLM_MODEL_NAME=phi3:latest
```

### 3. Uruchomienie serwera

```bash
cd venom_core
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Otwarcie dashboardu

Otwórz przeglądarkę i przejdź do:
```
http://localhost:8000
```

## Struktura Plików

```
venom_core/
├── api/
│   ├── __init__.py
│   └── stream.py              # WebSocket server i EventBroadcaster
├── core/
│   ├── metrics.py             # System metryk
│   ├── orchestrator.py        # Zmodyfikowany orchestrator z broadcasting
│   └── dispatcher.py          # Dispatcher z event broadcasting
├── agents/
│   └── architect.py           # Agent architekta z event broadcasting
└── main.py                    # FastAPI app z WebSocket i static files

web/
├── templates/
│   └── index.html             # Główny template dashboardu
└── static/
    ├── css/
    │   └── app.css            # Style dashboardu
    └── js/
        └── app.js             # JavaScript: WebSocket client, UI logic
```

## API Endpoints

### REST API

- `GET /` - Dashboard UI
- `GET /healthz` - Health check
- `POST /api/v1/tasks` - Utworzenie nowego zadania
- `GET /api/v1/tasks` - Lista wszystkich zadań
- `GET /api/v1/tasks/{task_id}` - Szczegóły zadania
- `GET /api/v1/metrics` - Metryki systemowe

### WebSocket

- `WS /ws/events` - WebSocket endpoint dla streamingu zdarzeń

## Typy Zdarzeń WebSocket

Dashboard odbiera następujące typy zdarzeń:

- `TASK_CREATED` - Utworzono nowe zadanie
- `TASK_STARTED` - Rozpoczęto przetwarzanie zadania
- `TASK_COMPLETED` - Zadanie ukończone pomyślnie
- `TASK_FAILED` - Zadanie nie powiodło się
- `PLAN_CREATED` - Architekt utworzył plan
- `PLAN_STEP_STARTED` - Rozpoczęto krok planu
- `PLAN_STEP_COMPLETED` - Ukończono krok planu
- `AGENT_ACTION` - Agent wykonuje akcję
- `AGENT_THOUGHT` - "Myśl" agenta
- `SYSTEM_LOG` - Log systemowy

## Testowanie

### Test manualny

1. Uruchom serwer zgodnie z instrukcją powyżej
2. Otwórz dashboard w przeglądarce
3. Sprawdź status połączenia (zielona kropka w prawym górnym rogu)
4. Wpisz przykładowe zadanie, np.:
   ```
   Zrób research o Python 3.12
   ```
5. Obserwuj:
   - Live Feed: Logi pojawiające się w czasie rzeczywistym
   - Task Monitor: Nowe zadanie z jego statusem
   - Chat Console: Odpowiedź od agenta
   - Metrics: Aktualizacja liczników

### Test automatyczny

```bash
pytest tests/test_dashboard_api.py -v
```

## Troubleshooting

### WebSocket nie łączy się

- Sprawdź czy serwer jest uruchomiony
- Sprawdź czy port 8000 nie jest zablokowany przez firewall
- Sprawdź konsolę przeglądarki (F12) dla błędów

### Dashboard nie ładuje się

- Sprawdź czy katalog `web/` istnieje i zawiera pliki
- Sprawdź logi serwera dla błędów montowania StaticFiles

### Metryki nie aktualizują się

- Sprawdź endpoint `/api/v1/metrics` ręcznie w przeglądarce
- Sprawdź czy zadania są tworzone poprawnie

## Rozwój

### Dodanie nowych typów zdarzeń

1. Dodaj typ zdarzenia do `EventType` w `venom_core/api/stream.py`
2. Wywołaj `event_broadcaster.broadcast_event()` w odpowiednim miejscu
3. Obsłuż zdarzenie w `web/static/js/app.js` w metodzie `handleWebSocketMessage()`

### Modyfikacja UI

- Edytuj `web/templates/index.html` dla struktury HTML
- Edytuj `web/static/css/app.css` dla stylów
- Edytuj `web/static/js/app.js` dla logiki JavaScript

## Licencja

Część projektu Venom Meta-Intelligence
