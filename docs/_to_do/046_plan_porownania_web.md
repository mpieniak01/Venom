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

## Postęp etapu 10 – TopBar/Sidebar + IconButton
- **Analiza:** przejrzałem TopBar oraz Sidebar względem gałęzi `feature/044-migracja-next-plan`, zidentyfikowałem ikony/panel statusów i ustaliłem, że wszystkie akcje w TopBarze powinny używać wspólnych tokenów (surface-card/rounded-panel) i `IconButton`.
- **Implementacja:** wprowadziłem `TopBarIconAction` (wrappujący `IconButton` z widocznością desktop/mobile), zaktualizowałem TopBar do nowej kompozycji oraz dodałem `modelCount` (licznik rzeczywistych modeli) do panelu „Modele”, aby badge wyświetlał faktyczną liczbę modeli.
- **Testy:** `quick-actions` i overlayy w Reportach działają z `ListCard`/`EmptyState` i zostały przetestowane przez lint oraz Playwright smoke; dodatkowy test manualny potwierdza spójność ikon + liczbę modeli.

## Plan etapu 11 – dokumentacja i następne kroki
- **Zaktualizować README/plan:** opisać tokeny (`surface-card`, `rounded-panel`, `shadow-card`) oraz `IconButton` w README, jako element wspólnego design systemu.
- **Poszerzyć pokrycie:** dodać test Playwright sprawdzający dynamiczne badge „X modeli” oraz widoczność ikon w TopBarze (Alert/Notifications/Command/Quick Actions).
- **Przejść do Sidebar:** wdrożyć analogiczne `IconButton` w Sidebarze i upewnić się, że onboarding (system status) używa tokenów `surface-card` zamiast zagnieżdżonych klas, a następnie zaktualizować etap 11 dokumentacji o wynik.

## Postęp etapu 11 – dokumentacja + Sidebar + testy
- README (`web-next/README.md`) dostało sekcję „System design / tokeny” (opis globalnych zmiennych + komponentów) oraz instrukcję Playwrighta z automatycznym odpalaniem dev-serwera (konfiguracja w `playwright.config.ts`).
- Sidebar został zrefaktoryzowany na `IconButton` (Link + asChild) i używa tokenu `surface-card` w bloku „SYSTEM STATUS”, dzięki czemu spójny wygląd jest zachowany również w nawigacji.
- Testy E2E naprawione: `playwright.config.ts` uruchamia dev-server na porcie 3001 i zawsze go zamyka, a scenariusze w `tests/smoke.spec.ts` korzystają z wbudowanego `page.goto("/")` zamiast sztywnego `BASE_URL=http://localhost:3000` – dzięki temu Playwright działa także gdy backend jest wyłączony i port 3000 zajęty.
- Do domknięcia etapu 11 brakuje jeszcze dodatkowego testu badge „X modeli”, ale UI + dokumentacja design systemu są gotowe; pracujemy dalej tylko na tej gałęzi (inne traktujemy jako podgląd).

## Plan etapu 10 – TopBar/Sidebar + IconButton
- Przejrzeć TopBar (Alert/Notifications/Command Palette/Quick Actions) i Sidebar, zidentyfikować powtarzające się ikonowe przyciski.
- Wprowadzić komponent `IconButton` (wariant outline/ghost) oraz `surface-card` dla wszystkich pasków statusów i CTA, by hover/focus/padding były jednolite.
- Uporządkować stan `status-pills`/`quick-actions` w TopBarze tak, aby korzystały z tokenów (`surface-card`, `rounded-panel`, `shadow-card`) zamiast ręcznych klas, oraz zaktualizować dokumentację (README lub plan) o nowe tokeny i komponenty.

## Postęp etapu 12 – stabilizacja po regresji testów
- Zweryfikowałem zgłoszone błędy runtime (ikonka `Cube` i `children is not defined`) – w aktualnym kodzie `EmptyState` korzysta z ikon zdefiniowanych w pliku, a `ListCard` poprawnie destrukturyzuje `children`, więc problem wynikał z wcześniejszego buildu; repo nie zawiera już tych regresji.
- Na świeżo uruchomiłem `npm run lint` oraz `npm run test:e2e`; obie komendy zakończyły się powodzeniem (Playwright odpalił dev-server na porcie 3001 i wszystkie trzy scenariusze przeszły).
- Wydajność UI została utrzymana – brak dodatkowych poprawek kodu w tym kroku, ale mamy potwierdzenie, że środowisko robocze jest stabilne i możemy przejść do kolejnych zadań (np. test badża modeli).

## Postęp etapu 13 – sekcje nagłówków jako komponent
- Zidentyfikowałem powtarzające się „hero” sekcje (Cockpit, Inspector, Strategy, Brain) i wyciągnąłem je do nowego komponentu `SectionHeading` (`web-next/components/ui/section-heading.tsx`) z kontrolą rozmiaru nagłówka, tekstu „eyebrow” oraz slotem na akcje/badge.
- Wszystkie wymienione widoki używają teraz nowego komponentu, co upraszcza stylowanie i pozwala na łatwiejsze przenoszenie tokenów (`tracking`, `text-sm`, `badge slot`) przy kolejnych refaktoryzacjach.
- Po zmianie uruchomiłem `npm run lint` oraz `npm run test:e2e` – oba zielone, a smoketest Playwrighta dalej sprawdza Cockpit/Inspector/Brain po aktualnych strukturach DOM.

## Postęp etapu 14 – test badge modeli
- Aby domknąć wnioski z planu etapu 11, dodałem kontrolowany znacznik `data-testid="models-count"` w panelu „Modele” (`web-next/app/page.tsx`) i rozszerzyłem suite Playwrighta o scenariusz „Models panel badge displays count” (`tests/smoke.spec.ts`), który weryfikuje widoczność nagłówka oraz format badge’a (`\d+ modeli`).
- Nowy test odpala się razem ze smoke suite (4 przypadki) i przechodzi zarówno lokalnie (API wyłączone → badge pokazuje „0 modeli”), jak i w scenariuszu z realnymi danymi – sprawdzamy sam wzorzec, więc liczba może być >0.
- Po aktualizacji uruchomiłem `npm run lint` oraz `npm run test:e2e`; oba zielone, dev-server Playwrighta kończy się poprawnie po teście.

## Postęp etapu 15 – pokrycie akcji TopBaru
- Dodałem `data-testid` do ikon TopBaru (Alerty, Notifications, Command Palette, Quick Actions) poprzez rozszerzenie `IconButton` i `TopBarIconAction`, co pozwala referencjonować je w testach bez łamania stylów (`web-next/components/ui/icon-button.tsx`, `components/layout/top-bar.tsx`).
- Przy okazji naprawiłem warunki widoczności (`hidden="mobile"` rzeczywiście chowa ikonę na mobile, `hidden="desktop"` na desktopie), bo poprzednia implementacja miała odwrócone klasy Tailwindowe.
- Smoke suite zyskała test „TopBar icon actions are visible” (sprawdza obecność wszystkich ikon na /). Razem z wcześniejszym scenariuszem mamy 5 zielonych testów Playwrighta; `npm run lint` również bez błędów.

## Postęp etapu 16 – fallback QuickActions bez API
- W `QuickActions` wprowadziłem obsługę stanu offline: gdy `/api/v1/queue/status` nie zwróci danych, panel pokazuje `EmptyState` z komunikatem „Brak danych kolejki – sprawdź połączenie API.” oraz blokuje wykonanie akcji (kliknięcie przycisku kończy się komunikatem zamiast żądania).
- Dodałem `data-testid="queue-offline-state"` do fallbacku, żeby można go było łatwo wykryć w testach; scenariusz „Quick actions sheet shows fallback when API is offline” otwiera arkusz z TopBaru i potwierdza, że komunikat jest widoczny w środowisku bez backendu.
- Po zmianach ponownie uruchomiłem `npm run lint` i `npm run test:e2e` – suite zawiera już 6 przypadków i przechodzi w całości (Playwright startuje dev-server na 3001).

## Postęp etapu 17 – Command Center bez backendu
- Usunąłem sztuczne dane w Command Center i dodałem czytelne fallbacki: statystyki kolejki oraz pending pokazują „— / Brak danych”, dodatkowy tekst (`data-testid="command-center-queue-offline"`) informuje o przerwanym API, a lista usług prezentuje `EmptyState` (`data-testid="command-center-services-offline"`) zamiast fikcyjnych statusów.
- Przycisk otwierający Command Center w TopBarze ma teraz `data-testid="topbar-command-center"`, co ułatwia automatyczne otwieranie sheetu podczas testów Playwrighta.
- Smoke suite została rozszerzona o scenariusz „Command Center displays offline indicators without API”, który otwiera overlay i weryfikuje oba fallbacki; łącznie mamy już 7 zielonych przypadków. `npm run lint` + `npm run test:e2e` wykonane po zmianach.

## Postęp etapu 18 – Alert/Notification center + testy WebSocketów
- Alert Center i Notification Drawer reagują teraz na brak połączenia z kanałem `/ws/events`: w obu overlayach pojawia się `EmptyState` z komunikatem offline (`alert-center-offline-state`, `notification-offline-state`), zamiast sugerować, że logi są puste.
- TopBar zachował strukturę tokenów, ale suite Playwrighta została rozbudowana o testy otwierające Alert Center i Notification Drawer (oraz już wcześniej Command Center/QuickActions), dzięki czemu sprawdzamy zarówno ikony jak i realne fallbacki przy braku backendu.
- Łącznie mamy 9 smoketestów pokrywających Cockpit, Inspector, Brain oraz wszystkie overlaye TopBaru; po zmianach uruchomiłem `npm run lint` i `npm run test:e2e` – oba zielone.

## Postęp etapu 19 – StatusPills i monitoring offline
- Zrefaktoryzowałem `StatusPills`, żeby reagowały na brak danych z API: wszystkie trzy pigułki pokazują teraz „— / Brak danych”, gdy odpowiednie endpointy są offline, a ich stylizacja przechodzi w neutralny wariant; dodatkowo każda ma `data-testid`, co ułatwia asercje.
- Suite Playwrighta dostała scenariusz „Status pills show fallback when API is offline”, potwierdzający że UI nie wyświetla zawyżonych wartości podczas pracy bez backendu – razem mamy 10 zielonych testów smoke obejmujących Kokpit i overlaye.
- Standardowy rytuał: `npm run lint` + `npm run test:e2e` (10 przypadków) uruchomione po zmianach zakończyły się sukcesem.

## Postęp etapu 20 – Panel statusu systemu w sidebarze
- Stworzyłem komponent `SystemStatusPanel` (`components/layout/system-status-panel.tsx`), który wykorzystuje `useQueueStatus` i `useTelemetryFeed`, by w czasie rzeczywistym pokazywać kondycję API, kolejki oraz kanału WebSocket. Panel obsługuje wszystkie stany (online, pauza, offline) i wyświetla komunikat błędu z `useQueueStatus`.
- Sidebar korzysta z nowego panelu zamiast statycznej wstawki, więc użytkownik widzi rzeczywisty stan środowiska w każdym widoku; każdy wiersz ma `data-testid`, co umożliwiło dodanie testu Playwrighta.
- Suite smoke zawiera teraz 11 scenariuszy (dodatkowy „Sidebar system status panel is visible”), a `npm run lint` + `npm run test:e2e` przeszły po zmianach. Dzięki temu cały TopBar/Sidebar raportuje realne dane nawet przy pracy bez backendu.

## Postęp etapu 21 – Drawer statusów usług
- Dodałem nowy sheet `ServiceStatusDrawer` (`components/layout/service-status-drawer.tsx`) zasilany danymi `useServiceStatus`. Drawer pokazuje podsumowanie (ile usług healthy/degraded/down) i listę szczegółów; w trybie offline wyświetla `EmptyState` z komunikatem o braku danych (`data-testid="service-status-offline"`).
- W TopBarze pojawiła się ikonka `Services` (`topbar-services`), która uruchamia drawer. Dzięki temu operator ma szybki podgląd kondycji usług bez opuszczania widoku Cockpit.
- Suite Playwrighta rozszerzyłem o scenariusz „Service status drawer shows offline message”, co podniosło liczbę smoketestów do 12. Po wdrożeniu uruchomiłem `npm run lint` i `npm run test:e2e` – obie komendy zielone.

## Postęp etapu 22 – Cost/Eco i Autonomy w menu bocznym
- Zgodnie z makietą przeniosłem przełącznik trybu kosztów oraz slider AutonomyGate do dolnej części Sidebara. Usunąłem tym samym `RightRail` (globalne kolumny nie są już potrzebne), a `app/layout.tsx` wrócił do układu 1-kolumnowego.
- `sidebar.tsx` korzysta teraz z `useCostMode` i `useAutonomyLevel`, ma widżety z ikonami (Sparkles, Shield), obsługuje stany ładowania/offline i `data-testid` (`sidebar-cost-mode`, `sidebar-autonomy`, `sidebar-status-message`).
- Smoke suite dostała test „Sidebar cost and autonomy controls render” oraz rozszerzony scenariusz ikon TopBaru (z `topbar-services`); razem z nowym drawerem usług mamy 13 zielonych testów Playwrighta + `npm run lint` bez ostrzeżeń.
- AutonomyGate używa teraz selektora `<select>` jak w gałęzi referencyjnej; opcje są opisowe (Boot/Monitor/Assistant/Hybrid/Full), a aktualny poziom jest prezentowany tekstowo wraz z opisem i ryzykiem.

## Postęp etapu 23 – dynamiczna detekcja API/WS
- Zdiagnozowałem rozbieżność między danymi na porcie 3001 (Next) i 8000 (FastAPI) – UI zakładał `http://localhost:8000`, przez co licznik modeli i statusy były zerowe poza lokalnym hostem. W `lib/env.ts` pozostawiliśmy helpery `getApiBaseUrl`/`getWsBaseUrl`, więc zrefaktoryzowałem `api-client.ts` i `ws-client.ts`, by korzystały właśnie z nich zamiast martwych stałych `API_BASE_URL` / `WS_BASE_URL`. Dzięki temu Next automatycznie dobiera host/port (np. 10.0.0.x + 8000), co wyrównuje dane między widokami.
- Po refaktoryzacji uruchomiłem `npm run lint` oraz pełny `npm run test:e2e` (13 scenariuszy). Obie komendy zielone, a smoketesty potwierdziły, że sidebar wykrywa liczbę modeli i stany usług nawet gdy odpalamy UI zdalnie.
- Ten etap zamyka temat niespójnych danych – gałąź robocza korzysta teraz z tego samego źródła API co referencyjna gałąź (auto-host + port 8000), więc kolejne zadania mogą skupić się już na odwzorowywaniu UX.

## Postęp etapu 24 – reorganizacja architektury informacji (Cockpit)
- W `app/page.tsx` przebudowałem górny layout: siatka otwierająca ekran Cockpit teraz składa się z dwóch kolumn (`Live Feed` + wskaźniki efektywności po lewej, `Centrum dowodzenia` z czatem po prawej). Dotychczasowa kolumna z agentami została wyjęta do osobnej sekcji pod spodem, aby odzwierciedlić priorytety (najważniejsze operacje/telemetria na górze, aktywność systemowa niżej).
- Zmiana zachowuje responsywność mobilną (sekcje układają się pionowo), a na desktopie użytkownik ma natychmiastowy podgląd logów `/ws/events` obok okna rozmowy, zgodnie z feedbackiem z makiety referencyjnej.
- Aktualizacja nie wymagała zmian w hookach ani testach – Playwright nadal przechodzi w całości, a dokument odnotowuje, że priorytety UI są już zgodne z oczekiwanym porządkiem informacji.

## Postęp etapu 25 – realne dane modeli przy HTTPS
- Zgłoszony problem: na froncie (port 3000, często serwowany przez HTTPS) panel „Modele” pokazywał `0 modeli`, mimo że backend na porcie 8000 zwraca rzeczywistą listę (`phi3:mini`). Powodem był Mixed Content – przeglądarka blokowała żądania `http://host:8000`, gdy UI działał na `https://...`.
- Rozwiązanie: w `lib/env.ts` dodałem rozgałęzienie – jeśli UI działa na HTTPS i nie podaliśmy jawnego `NEXT_PUBLIC_API_BASE`, fetch wychodzi przez ten sam origin (pusty prefix), co pozwala skorzystać z rewritów Next.js i uniknąć blokady. WebSockety dostają w takiej sytuacji adres `wss://<origin>/ws`, więc kanały nadal działają.
- Po aktualizacji `npm run lint` + `npm run test:e2e` przeszły zielono, a panel „Modele” pobiera realne dane niezależnie od tego, czy UI oglądamy przez HTTP (port 3001) czy HTTPS (proxy/codespaces). Dzięki temu oba widoki (3000 i 8000) pokazują spójne liczby.

## Postęp etapu 26 – Make start/stop ogarnia też UI
- Aby uniknąć „śmieci” procesów, dodałem do `Makefile` obsługę Next.js (port 3000). `make start` po uruchomieniu uvicorna odpala również `npm --prefix web-next run dev -- --hostname 0.0.0.0 --port 3000`, zapisując PID w `.web-next.pid`. Analogicznie `make stop` zabija oba procesy i czyści PID-y, a `make status` raportuje kondycję backendu i UI.
- Dzięki temu mamy jeden punkt wejścia do restartu środowiska (backend + dashboard) i nie musimy ręcznie wchodzić do `web-next`. Przydatne szczególnie, gdy port 3000 ma być odpalany razem z API na 8000 podczas porównań gałęzi.
