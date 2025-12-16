# ZADANIE 051: Backlog niedobitków UI (web-next)

## Cel
Skonsolidować wszystkie otwarte „niedobitki” przeniesione z wcześniejszych planów (np. zadanie 046), tak aby każdy zaległy temat miał jedno źródło prawdy i można go było odhaczyć bez szukania w rozproszonych notatkach.

## Status źródłowy: zadanie 046 (Plan porównania web ↔ web-next)

### 1. Brain / Strategy – dokumentacja i testy ✅
- Sekcja źródeł danych + checklista testów została dodana do `docs/FRONTEND_NEXT_GUIDE.md` (rozdz. 1–2) oraz zlinkowana w README.

### 2. Mapa bloków → przygotowanie etapu 29 ✅
- W `docs/FRONTEND_NEXT_GUIDE.md` (rozdz. 3) znajduje się lista elementów legacy oraz kryteria wejścia do etapu 29.

### 3. Otwarte działania (grudzień 2025) ✅
1. Sekcja „Brain & Strategy – źródła danych i testy” – wykonana (zob. README oraz `docs/FRONTEND_NEXT_GUIDE.md`).
2. Checklistę legacy + kryteria startu etapu 29 opisano w punkcie 3.2 przewodnika.

### 4. Zadanie – domknięcie Cockpitu do 100% ✅
1. Hero KPI i token metrics korzystają z `Panel` + klasy `kpi-panel`; brak danych wyświetla `EmptyState`.
2. Queue governance ma własny panel (`queue-panel`) + fallback offline i spójne stat cards.
3. Command console używa klasy `command-console-panel` (większy padding), a tło całego dashboardu ma gradient `#031627 → #051B2D`.
4. `app/page.tsx` zawiera dodatkowy panel z systemowymi KPI + placeholdery, które zapobiegają pustym kartom przy braku danych.

### 5. Uwagi z przeglądu wizualnego (QA) ✅
1. Ramka/glow KPI → klasy `kpi-panel`/`queue-panel`.
2. Padding konsoli → `command-console-panel`.
3. Kolor tła → aktualizacja `web-next/app/globals.css`.
4. Nagłówki/eyebrow pozostają w `SectionHeading`/Panel; hero opis korzysta z tych samych styli.

### 6. Inspector / Strategy – follow-up po zadaniu 048 ✅
1. Ręczne odświeżanie historii + spinner: dostępne w `web-next/app/inspector/page.tsx` (panel „Kolejka requestów”).
2. Panel JSON `pre` dla kroków: sekcja „Telemetria requestu” renderuje pełne dane i pozwala kopiować kroki.
3. Strategia – timeline KPI: `web-next/app/strategy/page.tsx` zawiera panele „Live KPIs” (dane z `/api/v1/tasks`) i „Timeline KPI” (`/api/v1/history`) z fallbackami.

### 7. Testy Playwright – Chat + Modele (zadanie 049) ✅
- Ustabilizowano wszystkie 15 scenariuszy w `web-next/tests/smoke.spec.ts`: topbarowe dialogi (Alert Center/Notifications/Command Center/Service Status) korzystają z `data-testid`, a status pillsy raportują zarówno fallback, jak i realne liczby.
- „Chat preset…” oraz „PANIC: Zwolnij zasoby…” nadal stubują kluczowe endpointy, a `npm --prefix web-next run test:e2e` przechodzi w trybie prod bez backendu (fallbacki telemetrii są pokryte).
- Pozostałe rozszerzenia (historia modeli/makra) mogą zostać dopisane w nowym sprincie – smoke suite jest stabilny i może być uruchamiany w CI jako regresja.

## Definicja ukończenia zadania 051
- Każdy z powyższych punktów posiada osobny status (DoD) i po zakończeniu jest odhaczany w tym pliku.
- Po zrealizowaniu wszystkich niedobitków zadanie 051 zostanie przeniesione do `docs/_done`.
