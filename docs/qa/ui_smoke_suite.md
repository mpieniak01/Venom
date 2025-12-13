# Venom UI – Smoke Test Suite

Ten dokument opisuje znormalizowany zestaw kroków QA, który należy wykonać przed merge'em zmian w interfejsie VENOM. Został przygotowany pod nowe layouty oparte na `_szablon.html` i obejmuje wszystkie główne moduły.

## 1. Przygotowanie środowiska
1. `make qa` – automatyczne odpalenie `scripts/qa/run_ui_suite.sh` (tworzy `.venv`, instaluje pytest i odpala `pytest -q`; traktujemy to jako sanity backendu przed testami manualnymi).
2. `npm install` – instalacja zależności JS (Chart.js, Mermaid, DOMPurify, Marked są serwowane lokalnie).
3. `npm run build` – opcjonalny sanity check bundla front-endowego (w projekcie CLI to stub, ale command powinien przejść).
4. Uruchom backend (np. `make run` lub `venom_core` wg instrukcji repo) i otwórz `http://localhost:8000`.
5. Wyczyść cache przeglądarki (Ctrl+Shift+R) aby załadować świeże assety CSS/JS.

## 2. Cockpit (web/templates/index.html)
### 2.1. Layout i status
- Zweryfikuj, że lewa kolumna zawiera menu Venom + telemetry terminal, a prawa `cockpit-grid`.
- Sprawdź status repo (`repoStatus`) – zmiana branch powoduje aktualizację bannera.

### 2.2. Zakładki + Insights
1. Przeklikaj zakładki: Feed, Voice, Jobs, Memory, Models, History.
2. `localStorage.venomActiveTab` powinien zapamiętywać ostatnią zakładkę (odśwież stronę).
3. W Feed zobacz kartę metryk oraz sekcje Integracje/Operacje/Terminal.
4. W Jobs/Memory/Models/History pojawiają się Insight cards z liczbami (≥1 danych API).
5. `jobsState`, `memoryState` i `historyState` zapisują: filtr, wyszukiwarkę, auto-refresh (odśwież stronę i upewnij się, że stan wraca).
6. Ustaw inną zakładkę jako domyślną przyciskiem ⭐; po odświeżeniu `localStorage.venomUIPreferences.general.defaultTab` wskazuje nową wartość, a znacznik ⭐ pojawia się przy odpowiednim przycisku. Przywróć Transmisję przyciskiem „Reset domyślnej”.

### 2.3. Konsola czatu
1. Wpisz zadanie, wyślij (`Ctrl+Enter` i kliknięciem).
2. Przełącz Lab Mode – `localStorage.venomUIPreferences.console.labMode` powinno się zmieniać; nowe zadanie pokazuje toast „Lab Mode”.

### 2.4. Queue Governance i notyfikacje
1. Sprawdź, że licznik aktywnych/pending zadań odświeża się co 2 sekundy.
2. Kliknięcie `Pause/Resume/Purge` powinno pokazać odpowiadające toasty (wywołania do API można stubować w dev).

## 3. War Room (web/templates/strategy.html)
1. Upewnij się, że hero `venom-page` pokazuje metryki: completion, milestones, health.
2. Przełącz `Auto Refresh` – `localStorage.venomWarRoomPreferences` powinno zapisać stan; po odświeżeniu checkbox zachowuje wartość.
3. Kliknij `Odśwież` – sekcje (Vision, Milestones, KPI, Report) pokazują spinner (`aria-busy`) i aktualizują datę.
4. Akcje `Zdefiniuj wizję`, `Start campaign`, `Raport statusu` powinny pokazywać komunikaty (w dev mogą zwracać błędy – obsługa ma zostać).

## 4. Flow Inspector (web/templates/flow_inspector.html)
1. Panel hero pokazuje liczbę aktywnych zadań i ostatni refresh.
2. Wyszukiwarka, filtry statusów i auto-refresh są zapamiętane w `localStorage.venomFlowInspectorPrefs` (sprawdź po odświeżeniu).
3. Wybór zadania renderuje sekwencję Mermaid, przyciski `Skopiuj` / `Pobierz` działają (clipboard, PNG/SVG fallback).
4. Auto-refresh zadań odświeża listę co 5 s, diagram co 3 s dla zadań w statusie processing.

## 5. Inspector (web/templates/inspector.html)
1. Hero `venom-page` pokazuje liczbę widocznych śladów oraz przypiętych.
2. Filtry/wyszukiwarka/auto-refresh zapisują się w `localStorage.venomInspectorUIPreferences`.
3. Wybór śladu renderuje Mermaid + szczegóły kroku; `Kopiuj` / `Pobierz` (diagram i krok) działają.
4. Pinowanie śladów aktualizuje listę + sekcję „Przypięte”; stan pinów siedzi w `localStorage.inspectorPinnedTraces`.

## 6. The Brain (web/templates/brain.html)
1. Sprawdź, że hero pokazuje węzły/krawędzie/status/timestamp.
2. Filtry, wyszukiwarka i auto-refresh zapisują się (sprawdź `localStorage.brainPreferences`).
3. Graf Cytoscape reaguje na filtrowanie; eksport JSON/PNG generuje pliki.

## 7. Checklist końcowa
- [ ] Wszystkie moduły wczytują się bez błędów w konsoli przeglądarki.
- [ ] Preferencje zapisują się i są respektowane po refreshu.
- [ ] Wszystkie nowe Insight cards mają dane (lub stany pustek).
- [ ] Akcje wymagające backendu zwracają poprawne komunikaty błędu, jeśli API nie działa.

## 8. Centrum preferencji (Cockpit)
1. Otwórz modal z panelu „Preferencje” przy zakładkach.
2. Użyj przycisku „Eksportuj konfigurację” – w dev weryfikujemy, że wygenerowany JSON zawiera bloki `cockpit`, `flow`, `inspector`, `warRoom`, `brain` oraz timestamp.
3. Kliknij „Resetuj wszystko” – po zamknięciu modala wszystkie zakładki wracają do ustawień domyślnych (`venomUIPreferences` wyczyszczone), a UI przełącza się na zakładkę Transmisja.
4. Kliknij „Pobierz plik” – w katalogu pobrań pojawia się plik `venom-preferences-*.json` (zawiera sekcje `cockpit`, `external`, `generatedAt`).
5. W panelu importu użyj przycisku „Wybierz plik”, wskaż pobrany JSON i upewnij się, że textarea została wypełniona treścią oraz etykieta pokazuje nazwę pliku.
6. Zaimportuj uprzednio zapisany plik JSON – interfejs powinien natychmiast odtworzyć poprzednią konfigurację (np. wskazania domyślnej zakładki, stan Lab Mode, filtry Historia/Zadania/Pamięć). W logu konsoli brak błędów.

> Dokument aktualizujemy przy każdej większej zmianie interfejsu (np. nowe zakładki, nowe panele Insights, kolejne strony z listy 043).***
