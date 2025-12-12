# Lista podstron do migracji na nowy layout VENOM

| Strona (template) | Skrypt JS | Główna funkcja | Status migracji |
|-------------------|-----------|----------------|------------------|
| `index.html` (Cockpit) | `web/static/js/app.js` | Zarządzanie kolejką, chat, telemetry | w trakcie (plan 042) |
| `brain.html` (The Brain) | `web/static/js/brain.js` | Graf wiedzy Cytoscape, filtry | do migracji |
| `flow_inspector.html` (Flow Inspector) | `web/static/js/flow_inspector.js` | Podgląd przepływów zadań | do migracji |
| `inspector.html` (Inspector) | `web/static/js/inspector.js` | Szczegóły zadań/logów | do migracji |
| `strategy.html` (War Room) | `web/static/js/strategy.js` | Strategia / planowanie | do migracji |
| `index_.html` (legacy UI) | n/a | Stare demo | rozważ usunięcie po wdrożeniu |

> Po zakończeniu prac na `index.html` należy przenieść ten sam header/sidebar, design tokens i konwencje CSS do pozostałych stron. Każda z nich ma swój JS – trzeba zachować kompatybilne ID.
