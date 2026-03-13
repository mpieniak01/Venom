# Runbook: Ghost Desktop Automation

Runbook definiuje operacyjny przebieg bezpiecznego uruchamiania automatyzacji desktop Ghost (PyAutoGUI + fallback vision).

## 1. Zakres

Stosuj runbook przy manualnych uruchomieniach desktop automation w środowiskach preprod/lab:

- wykonanie przez API Ghost (`/api/v1/ghost/start|status|cancel`),
- walidacja hardware-in-loop,
- emergency stop i triage.

## 2. Warunki wstępne

1. Konfiguracja:
- `ENABLE_GHOST_AGENT=True`
- `ENABLE_GHOST_API=True`
- `GHOST_RUNTIME_PROFILE=desktop_safe` (domyślnie na pierwszy przebieg)

2. Wymagania hosta:
- aktywna sesja desktop (X11/Wayland/Windows),
- kontrola okna na pierwszym planie,
- operator z dostępem do emergency stop.

3. Governance:
- poziom autonomii dopuszcza mutacje desktop input,
- audit stream jest aktywny.

## 3. Checklista bezpiecznego startu

1. Potwierdź, że fokus nie jest na aplikacji z danymi wrażliwymi.
2. Zamknij niepowiązane okna i powiadomienia.
3. Ustaw mysz w neutralnym miejscu (nie w rogu `(0,0)`).
4. Otwórz podgląd audytu i potwierdź wpisy Ghost:
- `source=api.ghost`,
- `source=core.ghost`.
5. Startuj od profilu `desktop_safe`.

## 4. Kalibracja

1. Zweryfikuj stałe DPI/skalowanie i rozdzielczość.
2. Wykonaj jeden scenariusz operatorski na celu niedestrukcyjnym (lokalne okno harness).
3. Potwierdź:
- współrzędne kliknięcia trafiają w oczekiwany obszar,
- fokus klawiatury trafia do oczekiwanego pola,
- fail-closed blokuje niebezpieczny fallback w `desktop_safe`.

## 5. Scenariusze hardware-in-loop

Uruchom manualne testy HIL:

```bash
VENOM_GHOST_HIL=1 .venv/bin/pytest tests/test_ghost_agent_hil.py -v
```

Scenariusze krytyczne:

1. `desktop_safe` blokuje fallback click, gdy brak trafienia vision.
2. `desktop_power` dopuszcza fallback click, wpisanie tekstu i submit z klawiatury.

Oczekiwany wynik: plik testowy przechodzi (2 scenariusze).

## 6. Uruchomienie runtime przez API

1. Start zadania:
- `POST /api/v1/ghost/start`
2. Podgląd statusu:
- `GET /api/v1/ghost/status`
3. Anulowanie:
- `POST /api/v1/ghost/cancel`

Zasady operacyjne:

1. `status=failed` traktuj jako twardy stop i triage.
2. Dla akcji krytycznych używaj `desktop_safe`, chyba że istnieje jawna zgoda na odstępstwo.
3. `desktop_power` nie używaj w środowiskach produkcyjnych bez jawnego wpisu zmian.

## 7. Emergency stop

Natychmiastowe zatrzymanie:

1. Wywołaj `POST /api/v1/ghost/cancel`.
2. Alternatywnie uruchom fizyczny fail-safe ruchem kursora do rogu `(0,0)`.

Po zatrzymaniu:

1. Zapisz ostatnie wpisy audytu (`api.ghost`, `core.ghost`).
2. Zanotuj `task_id`, profil runtime i kontekst błędu.
3. Potwierdź brak aktywnego taska w `/ghost/status`.

## 8. Checklista triage

1. Zidentyfikuj fazę błędu:
- locate vision,
- input click/type/hotkey,
- verification.
2. Zweryfikuj gate policy/autonomy i kontekst aktora.
3. Porównaj profil runtime (`desktop_safe` vs `desktop_power`) z oczekiwanym zachowaniem.
4. Dołącz dowody:
- wpisy audit,
- screenshot/video (jeśli dostępne),
- output testów HIL.

## 9. Kryteria zamknięcia

1. Scenariusze HIL przeszły na docelowym setupie desktop.
2. Ścieżka API start/status/cancel została zwalidowana.
3. Emergency stop został zweryfikowany.
4. Dowody auditowe dołączono do change record.
