# Refactor interfejsu VENOM (szablon `_szablon.html`)

## 1. Cel i zakres
- Zastąpić aktualny layout Cockpitu layoutem z `_szablon.html` (nowa grafika) i jednocześnie wystandaryzować strukturę HTML, CSS i JS.
- Zachować kompatybilność z obecnym kodem aplikacji (`web/templates/index.html`, `web/static/js/app.js`, API REST).
- Uporządkować style (design tokens, komponenty, reset) i sposób ładowania bibliotek JS (Chart.js, Mermaid, DOMPurify, Marked).

## 2. Analiza obecnego `_szablon.html`
- **Inline CSS**: całe UI zdefiniowane w `<style>` – trzeba wyprowadzić do `web/static/css/app.css` (ew. dedykowanego pliku) i zadbać o namespace zmiennych (prefiks `--venom-`).
- **Reset + layout**: globalne `* { margin:0 }`, custom scrollbar, 2 kolumny (`.sidebar`, `.main-workspace`). U nas istnieje już reset + `main-layout`, więc trzeba pogodzić/respektować obie warstwy.
- **Komponenty**: sidebar telemetry tabs, repo badge, stat cards, console / chips, form wejściowy. Wiele elementów wykorzystuje ID używane w `app.js` (`liveFeed`, `metricTasks`, `taskInput`, `sendButton`, `queueActive`, `clearWidgetsBtn`, itd.) – zachowanie identyfikatorów jest krytyczne.
- **Zewnętrzne biblioteki**: w `<head>` importy CDN Chart.js, mermaid, DOMPurify, marked. W produkcie część jest już w bundlerze – decyzja: trzymać globalnie (np. w base template) lub dynamicznie ładować moduły w `app.js`.
- **HTML struktura**: brak istniejących bloków (np. `queue-tabs-panel`, `right-panel`). Migracja będzie polegała na zastąpieniu `index.html` markupem z `_szablon.html`, ale musimy odwzorować placeholdery slotów (live feed, metrics, history table) i dodać makra Jinja, jeżeli są.

## 3. Plan działania (wysoki poziom)
1. **Przeniesienie design tokens**
   - Wynieść sekcję `:root` i reset do `app.css` z komentarzem, by uniknąć konfliktów.
   - Ustawić nazwy zmiennych z prefiksem (`--venom-primary` itp.) i mapować na obecne `var(--primary-color)` – albo odwrotnie poprzez aliasy.
2. **Refaktoryzacja CSS**
   - Podzielić style na moduły: `layout`, `sidebar`, `cards`, `console`, `chips`, `modal`.
   - Uzgodnić spacingi, typografię (Inter / JetBrains) i upewnić się, że globalne literówki (np. `margin-top: 15px`) są poprawne.
   - Zachować responsywność (sidebar w mobile, siatka kart).
3. **Integracja HTML**
   - Zastąpić zawartość `web/templates/index.html` nową strukturą, zachowując bloki Jinja (extends `base.html`, `block content` itd.).
   - Upewnić się, że elementy z ID (np. `historyModal`, `queueActive`, `metricNetwork`) znajdują się dokładnie tam, gdzie oczekuje `app.js`.
   - Dodając nowy sidebar, usunąć stare `main-layout` i `left-stack`, dopasować do nowego markup.
4. **Aktualizacja JS**
   - Przejrzeć `web/static/js/app.js` / `modules` – zaktualizować selektory, jeżeli klasy/ID się zmienią.
   - Dodać inicjalizację nowych elementów (np. telemetry tab buttons `data-tab` już istnieją – sprawdzić event binding).
   - Zająć się dynamicznym ładowaniem widgetów (czy nowy markup wymaga innych kontenerów?).
5. **Biblioteki zewnętrzne**
   - Sprawdzić, które importy z `_szablon.html` są potrzebne i jak je włączyć (np. dodać do `base.html` lub bundla Vite/Webpack).
6. **QA i testy**
   - Uruchomić `npm run build`/`python -m pytest` (jeśli UI integruje się z backendem), manualnie zweryfikować zachowanie: sidebar, telemetry tabs, chat, history, modale cost-mode.

## 4. Najlepsze praktyki / standardy front-end
**CSS / Layout**
- System design tokens – wszystkie kolory, spacing, promienie, typografia jako zmienne CSS w jednym miejscu; aliasy mapujące stary i nowy theme. Ułatwia dark/light theme i współdzielenie styli.
- Layout przy użyciu CSS Grid + Flex – grid dla struktur makro (np. układ 2 kolumn, siatka statystyk), flex do wewnętrznych modułów (sidebar, przyciski). Pozwala to na responsywność bez hacków.
- BEM/semantyczne klasy – nazwy w stylu `.sidebar__nav`, `.console__wrapper` dzięki czemu CSS jest czytelny, a JS może targetować jasne selektory.
- Kontrolowane przewijanie (`min-height:0`, `overflow:auto`) w panelach (chat, telemetry) i media queries (~1200px, ~900px), aby uniknąć globalnego scrolla.
- Wspólne mixiny/utilities (np. `.panel`, `.chip`) – komponenty wielokrotnego użytku zamiast duplikacji w każdej stronie.

**HTML**
- Semantyczne znaczniki (nagłówki zachowują hierarchię, listy/`dl` dla metryk) i definicja regionów (`<main>`, `<aside>`, `<nav>`).
- Zachowanie stałych identyfikatorów wymaganych przez JS (`id="liveFeed"`, `id="historyModal"`) oraz data-attributes dla logiki (np. `data-tab`).
- Dostępność: aria-label dla ikon, role dla kontenerów, odpowiednie `button type="button"` aby unikać domyślnego submit.
- Minimalizacja inline-style; preferowana konfiguracja przez klasy + CSS variables.

**JavaScript**
- Rozdzielenie logiki od prezentacji: JS manipuluje klasami (`classList.add/remove`) i atrybutami, nie wstrzykuje “sztywnych” styli.
- Hooki DOM w `initElements()` – wszystkie selektory w jednym miejscu, dzięki czemu łatwo śledzić zależności między template a JS.
- Modularność: pliki takie jak `app.js`, `brain.js` utrzymują lokalne funkcje, deklarują dependencies (Chart, Mermaid) i korzystają z `async/await` + `try/catch`.
- Reużywalne utilsy (formatowanie czasu, obsługa modali) zamiast powtórzeń w każdej podstronie.
- Kontrola zasobów zewnętrznych: biblioteki (Chart.js, Mermaid, DOMPurify, Marked) ładowane raz przez bundler, wersje przypięte, brak globalnych `eval`.
- Wsparcie dla dostępności: focus management w modalach, asynchroniczne operacje zakończone user feedback (toast/alert).

## 5. Wpływ na pozostałe widoki i JS
- **Lista szablonów**: oprócz `web/templates/index.html` Cockpit, w repo są m.in. `web/templates/brain.html`, `web/templates/inspector.html`, `web/templates/war_room.html`, `web/templates/flow_inspector.html`. Każdy ma własny layout, ale niektóre korzystają z tych samych elementów (`historyModal`, telemetry). Po zatwierdzeniu nowego wyglądu Cockpitu trzeba sukcesywnie migrować pozostałe podstrony do wspólnego układu (`sidebar + main-workspace`) i współdzielić komponenty CSS.
- **Skrypty JS**: główna logika interfejsu mieszka w `web/static/js/app.js` (Cockpit) oraz w dedykowanych plikach (`brain.js`, `flow_inspector.js`, `inspector.js`, itd.). Każdy z nich manipuluje DOM przez określone identyfikatory (`cy`, `knowledgeStats`, `taskList`, `historyTableBody`). Nowy layout **musi zachować** te ID albo zapewnić adaptery, żeby uniknąć regresji. Po wdrożeniu Cockpitu należy przejrzeć inne skrypty i zaktualizować ich selektory/style (np. `brain.js` używa `#cy`, `#knowledge-stats`, `#filters`).
- **Konwencje HTML/CSS**: gdy Cockpit będzie działał z nowym theme, przenosimy te same klasy oraz zmienne do wspólnego zestawu (np. `.sidebar`, `.console-wrapper`) i stosujemy je w innych widokach. Dzięki temu CSS będzie współdzielony, a kolejne strony będą mogły korzystać z tych samych tokenów (czcionki, spacing).
- **Biblioteki i bundling**: jeżeli Chart.js, Mermaid czy DOMPurify mają być w całym UI, dodajemy je do globalnego bundla i upewniamy się, że np. `brain.js` dalej dostaje `cytoscape` bez konfliktu.


## 6. Kwestie wymagające decyzji
- Jak wpiąć nowy sidebar w istniejące blocki base template? (np. `nav`/`header` w `base.html` vs. nowy UI).
- Czy zachować obecne nazwy zmiennych CSS, czy wprowadzić aliasy? (uniknięcie regresji w innych widokach).
