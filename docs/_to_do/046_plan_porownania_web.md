# ZADANIE 046: Porównanie szablonu web z gałęzią `feature/044-migracja-next-plan`

## Cel
1. Uzyskać wizualny efekt zbliżony do dopracowanego UI (gałąź `feature/044-migracja-next-plan`) przy minimalnym koszcie kodu/stylów (optymalizacja).
2. W drugim etapie odwzorować pełną funkcjonalność po stronie frontu (bez regresji) - ale bez kopiowania juz istenijacych.

## Zakres
- Analiza różnic wizualnych między bieżącą gałęzią a `feature/044-migracja-next-plan`.
- Plan optymalizacji CSS/komponentów, by utrzymać lub poprawić wygląd przy mniejszym narzucie.
- Plan odwzorowania funkcjonalności (hooki, akcje kolejki, makra, panele).

## Etapy
1. **Discovery wizualny**
   - Zrzuty ekranu/porównanie: Cockpit, Brain, Inspector, Strategy, TopBar/Sidebar.
   - Wypisanie elementów krytycznych dla UX (szkło, gradienty, spacing, ikonografia).
   - Identyfikacja duplikatów stylów/komponentów (Badge/Panel/Sheet/Command).
2. **Plan optymalizacji UI**
   - Ujednolicenie tokenów (kolory, cienie, promienie, spacing) – 1 źródło prawdy.
   - Refaktoryzacja powtarzalnych bloków (stat cards, listy z przyciskami, sekcje logów).
   - Sprawdzenie wag CSS i nieużywanych klas; redukcja inline klas jeśli powtarzają się >3×.
3. **Plan odwzorowania funkcjonalności**
   - Mapowanie endpointów i hooków na ekrany (Cockpit, Inspector, Brain, Strategy).
   - Lista akcji operacyjnych do zachowania: queue (toggle/purge/emergency), git, models, cost/autonomy, makra, telemetry, command/alert/notification center.
   - Scenariusze offline (API off) – stany pustych danych/fallbacki.
4. **Walidacja i testy**
   - Lint + Playwright smoke na bazie dostępnego suite.
   - Checklisty UX (responsywność, kontrast, focus states).
   - Krótkie demo/preview (np. storybook lub nagranie) – opcjonalnie.

## Deliverables
- Raport porównawczy (krótka lista różnic i rekomendacji optymalizacji).
- Zaktualizowany UI (po optymalizacji) w gałęzi roboczej.
- Wdrożone (lub zaplanowane) zmiany funkcjonalne zgodne z mapą endpointów.
- Aktualizacja dokumentacji postępu (045) o wykonany etap.

## Definition of Done
- Spisana lista różnic wizualnych + rekomendacje optymalizacji (z priorytetem).
- Wprowadzone i potwierdzone poprawki UI zgodnie z rekomendacjami.
- Scenariusze funkcjonalne zmapowane i zaplanowane (drugi etap).
- Lint + smoke Playwright zielone.

## Discovery wizualny – notatki (etap 1)
- **Motyw/glas**: spójny kierunek (zinc + glass + neon), ale wiele paneli używa inline klas `rounded-2xl border bg-white/5 p-4`; rekomendacja: 1 wariant w `Panel/StatCard` + tokeny radius/spacing/shadow w `globals.css`.
- **TopBar**: obecnie 5 przycisków (MobileNav, Alert, Notifications, Command Palette, Quick Actions) z duplikatem klas; warto dodać wariant `IconButton` i wyrównać padding/ikonografie, by uniknąć powtórzeń.
- **Karty KPI/Statystyki**: tremor + StatCard występują na Cockpit/Strategy/Inspector; można ujednolicić rozmiary fontów i gradienty (jedna paleta violet/indigo/emerald) oraz dodać lekki wariant „ghost” dla kart o niskiej ważności.
- **Listy/logi**: Live Feed, pinned logs, task lists i history używają podobnych kontenerów; do rozważenia wspólna „ListCard” (header + body + akcje) i standaryzacja stanów pustych (tekst + ikona).
- **Makra/aktywacje**: przyciski makr i akcji queue mają wiele klas; wydzielenie `PrimaryButton`/`GhostButton` zmniejszy kod i poprawi spójność hover/focus.
- **Responsywność**: sekcje makr, Task Insights i pinned logs mogą rozlewać się w pionie na mobile; warto dodać `max-h` + `ScrollArea` lub akordeon dla mobile.
- **Tło/siatka**: powtarza się `bg-[url('/grid.svg')]`; upewnić się, że skala/pozycja jest jednolita i nie konkuruje z gradientami paneli.

### Rekomendacje optymalizacji (wysoki priorytet)
1. Stworzyć małą bibliotekę wariantów: `Button`, `IconButton`, `ListCard`, `Badge` (tone + size), `Panel` (default/ghost). Ograniczyć inline Tailwind w miejscach powtarzalnych.
2. Wyekstrahować tokeny (radius, padding, shadow, gradient) do CSS variables lub `globals.css` i użyć w Panel/StatCard.
3. Ujednolicić nagłówki sekcji (uppercase tracking + font size) w panelach/kartach.
4. Uporządkować stany pustych danych (tekst + piktogram) i dodać `ScrollArea` dla sekcji z rosnącą listą (pinned logs, makra na mobile).

## Postęp etapu 2 – unifikacja przycisków (Cockpit)
- Dodano wspólny komponent `Button` (warianty: primary, secondary, outline, subtle, warning, danger; rozmiary xs–md) z domyślnym `type="button"`.
- Podmieniono kluczowe akcje Cockpitu na `Button`: wysyłka/clear zadania, logi (pin/export/clear), makra (run/add/reset), kolejka (toggle/purge/emergency), modele (install/refresh/activate), git (sync/undo), cost/autonomy, copy JSON w szczegółach requestu.
- Efekt: spójne stany hover/focus, mniej inline Tailwind, lepsza dostępność (focus/disabled) i przygotowanie pod kolejne komponenty (`IconButton`/`ListCard`).
- Kolejny krok: ujednolicić karty/listy (panele logów, stat cards, puste stany) i ewentualnie wprowadzić wariant `IconButton` dla drobnych akcji (TopBar/LogEntry) oraz tokeny spacing/shadow w `globals.css`.

## Postęp etapu 3 – listy + akcje ikonowe
- Dodano `ListCard` (powtarzalne karty list) oraz `IconButton` dla małych akcji.
- Cockpit: listy zadań i historii korzystają z `ListCard` (spójne border/hover/selected). Akcje pin/usuń w logach używają `IconButton` z ikonami Pin/PinOff/X.
- Dzięki temu zmniejszono duplikację klas w listach i uproszczono drobne akcje w logach; podstawę pod dalszą standaryzację pustych stanów/ListCard w innych widokach.

## Postęp etapu 4 – spójne puste stany
- Dodano komponent `EmptyState` (ikona, tytuł, opis) dla powtarzalnych pustych widoków.
- Cockpit: sekcja Aktywne zadania, Historia oraz lista modeli korzystają z `EmptyState` z ikonami Inbox/History/Cube i opisem, co robić dalej.
- Przygotowanie pod rozszerzenie pustych stanów na inne widoki (Inspector/Strategy/Brain) bez duplikacji inline klas.

## Postęp etapu 5 – standaryzacja Inspector
- Inspector korzysta z nowych komponentów: `ListCard` dla historii requestów i kroków, `EmptyState` dla pustej historii/kroków/telemetrii tasków, `IconButton` dla zoom/controls, `Button` dla kopiowania JSON.
- Dzięki temu panel historii/kroków ma spójne hover/selected, puste stany są opisane i nie duplikują klas, a kontrolki zoom/reset są jednolite stylistycznie.

## Postęp etapu 6 – Strategy i Brain
- Strategy: akcje główne (refresh, wizja, kampania, raport) na `Button`; puste stany wizji/raportu/kamieni milowych na `EmptyState`, spójne CTA; progres i raporty bez duplikacji klas.
- Brain: filtry grafu i kontrolki skanu/dopasowania na `Button`; statystyki/lekcje oraz LessonsStore fallbacky na `EmptyState`; przyciski file info/impact na wspólnym wzorcu.
- Efekt: spójne hover/focus dla paneli strategicznych, zredukowane inline klasy w Brain/Strategy, gotowe do dalszej tokenizacji.

## Postęp etapu 7 – tokeny radius/shadow
- Dodano zmienne CSS w `globals.css`: `--radius-panel`, `--radius-card`, `--shadow-card`, `--surface-muted` + klasy pomocnicze (`rounded-panel`, `shadow-card`, `surface-card`).
- Panel korzysta z `shadow-card`/`rounded-panel`, dzięki czemu głębokość i promień są kontrolowane z jednego miejsca.
- Przygotowanie pod dalszą tokenizację spacing/gradientów i ewentualne użycie `surface-card` w innych komponentach, aby ograniczyć powtarzanie klas Tailwind.

## Postęp etapu 8 – overlayy i drawer
- Command Center, Alert Center i Notification Drawer korzystają z `ListCard` + `EmptyState`, dzięki czemu listy skrótów, tasków, usług, powiadomień i alertów są spójne (border, spacing, hover, brak duplikacji klas).
- Sekcje w sheetach używają klasy `surface-card`, a CTA (filtry, kopiowanie, quick links) bazują na `Button`, co standaryzuje hover/focus i ułatwia dodanie nowych komponentów w overlayach.
- Kolejny krok: rozważyć zastosowanie `surface-card` i `ListCard` w dodatkowych drawerach (QuickActions, Notifications) oraz pełne udokumentowanie tokenów w `README`.

## Postęp etapu 9 – QuickActions i akcje kolejki
- QuickActions zbudowany wokół `ListCard` + `surface-card`, dzięki czemu lista działań (pause/resume, purge, emergency stop) pokazuje endpointy, ikony i stany `running`.
- Akcje są opakowane w indeksowany zestaw (`QuickActionItem`), więc potwierdzenia i statusy przychodzą z jednego miejsca; `Badge`/meta informują o endpointach i flagach.
- Dzięki temu overlay kolejki ma spójny spacing, debugging akcji nie wymaga duplikacji klas, a dalsze interakcje można dodawać jako elementy listy.

## Plan etapu 10 – TopBar/Sidebar + IconButton
- Przejrzeć TopBar (Alert/Notifications/Command Palette/Quick Actions) i Sidebar, zidentyfikować powtarzające się ikonowe przyciski.
- Wprowadzić komponent `IconButton` (wariant outline/ghost) oraz `surface-card` dla wszystkich pasków statusów i CTA, by hover/focus/padding były jednolite.
- Uporządkować stan `status-pills`/`quick-actions` w TopBarze tak, aby korzystały z tokenów (`surface-card`, `rounded-panel`, `shadow-card`) zamiast ręcznych klas, oraz zaktualizować dokumentację (README lub plan) o nowe tokeny i komponenty.
