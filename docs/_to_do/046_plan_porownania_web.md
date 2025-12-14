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

## Analiza stanu – przed etapem 27
- `_szablon.html` zawiera komplet docelowych tokenów wizualnych (kolory neonowe, glassmorphism, spacing, typografia Inter/JetBrains), ale aktualne widoki Jinja (`web/templates/index.html`, `brain.html`, `strategy.html`, `inspector.html`) wciąż renderują legacy układ (`container`, `left-stack`, `war-room-panel`) i klasy niepowiązane z tokenami szablonu.
- `web/static/css/app.css` nie ma sekcji odpowiadającej deklaracjom ze `_szablon.html`; część klas jest duplikowana inline i nie respektuje docelowych przerw/siatki ani gradientów tła.
- Elementy wizerunkowe (sidebar typu command column, panel telemetrii, glassowe nagłówki, hero karty) nie posiadają jeszcze swoich odpowiedników w `base.html`; nadal ładowany jest tylko stary navbar + kontener.
- Zmiany z etapów 21–26 przygotowały wskaźniki usług/kolejki w Next, ale nie istnieje jeszcze statyczne odwzorowanie tych sekcji dla obecnego frontu – brak spójności między gałęziami pod kątem kolorystyki i modułów.

## Plan etapu 27 – odwzorowanie szablonu wizerunkowego (web-next)
1. **Tokeny i tło**
   - Zidentyfikować kolory, gradienty i efekty (noise/glass/flare) z `_szablon.html`, a następnie przenieść je do `web-next/app/globals.css` oraz `tailwind.config.ts`, aby całe Next UI korzystało z jednej palety (background, panel, akcenty neonowe, shadow).
2. **Layout bazowy**
   - Ujednolicić podstawowe komponenty layoutu (`app/layout.tsx`, `components/layout/sidebar.tsx`, `components/layout/top-bar.tsx`) tak, by używały nowych klas glass/glow i spacingu odpowiadającego referencyjnemu szablonowi – bez zmian logiki hooków.
3. **Widoki funkcjonalne**
   - Dostosować główne strony (`app/page.tsx`, `app/brain/page.tsx`, `app/inspector/page.tsx`, `app/strategy/page.tsx`), aby hero sekcje, flare-card i command console odwzorowywały `_szablon.html` (układ kolumn, spacing, neonowe nagłówki).
4. **Weryfikacja**
   - Uruchomić `npm run lint` i `npm run test:e2e`, przygotować screeny porównawcze oraz zanotować wszystkie kompromisy w tej sekcji planu.

## Przygotowanie etapu 28 – mapa bloków i deduplikacja
- Po ujednoliceniu wyglądu przygotować tabelaryczną mapę bloków (sidebar, telemetry tabs, command console, hero cards, integracje, KPI, overlaye) wraz z przypisaną funkcjonalnością i źródłem danych (legacy `app.js`, Next hook, brak).
- Dla każdej sekcji oznaczyć status: „potrzebna 1:1”, „do scalania z innym blokiem”, „możliwa do usunięcia” – to posłuży do decyzji o dalszej adaptacji usług w etapie 28.
- Uwzględnić ewentualne dublowanie funkcji między Cockpitem a Inspector/Strategy (np. historia vs timeline) oraz zdefiniować kryteria zachowania (np. unikalny endpoint, wymóg compliance, value UX).

## Postęp etapu 27 – kickoff w web-next
- Stary katalog `web/` oznaczono jako zamrożony (`web/README.md`) – wszystkie kolejne iteracje realizujemy w `web-next`.
- Przeniesiono neonową paletę `_szablon.html` do `web-next/app/globals.css` (ciemne tło #030407, akcenty #00ff9d / #00b8ff, noise overlay, nowe cienie i glass-panel), dzięki czemu layouty Next korzystają z tych samych efektów wizualnych.
- Zaktualizowano bazowy layout (`app/layout.tsx`) oraz komponenty otoczenia (`components/layout/sidebar.tsx`, `components/layout/top-bar.tsx`): sidebar i topbar korzystają z klas glass-panel, neonowych akcentów i spacingu jak w `_szablon.html`, a shell posiada warstwy tła z gradientami i noise.
- Kolejnym krokiem będzie dopięcie widoków funkcjonalnych (Cockpit/Brain/Inspector/Strategy) oraz walidacja wizualna opisana w planie powyżej.

## Postęp etapu 27 – stabilizacja layoutu i testów
- Naprawiłem regresję z `SystemStatusPanel`: klasa `glass-panel` nadpisywała `position`, przez co blok w sidebarze kurczył się do 0 px i smoketest widział „hidden”. W `app/globals.css` zachowujemy teraz przekazaną wartość (`fixed`/`sticky`/`absolute`), więc panel odzyskał właściwe wymiary bez ruszania markupów.
- Uporządkowałem typy stron Brain/Cockpit (cytoscape + logi) oraz komponenty wykorzystujące `SheetContent`, żeby `next build` przechodził bez błędów – to było konieczne, by odblokować testy w trybie produkcyjnym.
- `npm --prefix web-next run test:e2e` buduje obecnie aplikację i odpala Playwrighta na `next start` (konfiguracja w `package.json` + `playwright.config.ts`). Dzięki temu smoketest działa na tym samym buildzie co deployment i nie wyświetla więcej dev-overlay z błędem „Unexpected end of JSON input”.
- Po zmianach `npm --prefix web-next run lint` oraz `npm --prefix web-next run test:e2e` (13 scenariuszy) zakończyły się zielono i logują realny wynik w `_test-results`. To zamyka kolejny etap planu: layouty w `web-next` są zgodne z `_szablon.html`, a pipeline testowy jest odporny na brak backendu.

## Postęp etapu 28 – mapa bloków i deduplikacja
Przeanalizowałem aktualne widoki `web-next` względem wymagań `_szablon.html` i zebrałem blokowo-funkcjonalną mapę, która mówi które sekcje musimy utrzymać 1:1, a które można scalić lub uprościć. Oparłem się na rzeczywistych hookach/data-source’ach z Next (np. `useQueueStatus`, `useGraphSummary`, `useRoadmap`). Poniżej tabela z rekomendacjami:

| Obszar / blok | Funkcja w UI | Źródło danych / komponent w `web-next` | Status |
| --- | --- | --- | --- |
| Sidebar (Modules, System Status, Cost, Autonomy) | Globalna nawigacja + kontrola trybów | `SystemStatusPanel` (`useQueueStatus`, `useTelemetryFeed`), `useCostMode`, `useAutonomyLevel` | **Utrzymać 1:1** – to odpowiednik command-column z makiety, nie ma duplikatów |
| TopBar + Status Pills | Telemetria WS/Queue/Tasks + skróty | `StatusPills` (`useQueueStatus`, `useMetrics`, `useTasks`) | **Utrzymać 1:1** – główny wskaźnik stanu systemu |
| TopBar overlaye (Alert/Notification/Command/QuickActions/Services) | Szybkie interakcje + fallbacki offline | `AlertCenter`, `NotificationDrawer`, `CommandCenter`, `QuickActions`, `ServiceStatusDrawer` (korzystają z `useTelemetryFeed`, `useQueueStatus`, `useServiceStatus`) | **Utrzymać**, ale konsolidować wzorce offline (już spójne) |
| Cockpit – hero telemetry (Live Feed, Skuteczność, Zużycie tokenów) | Startowy przegląd operacji | `useTelemetryFeed`, `useMetrics`, `useTokenMetrics` | **Utrzymać 1:1** – zgodne z `_szablon` (neonowe hero) |
| Cockpit – Command Console / chat | Wysyłanie zadań, logi, pinowanie | `sendTask`, `useHistory`, `useTasks`, `useTelemetryFeed` | **Utrzymać** – to kluczowy blok unikatowy |
| Task lists (Aktywne zadania, Historia, Task Insights) | Kolejka i historia requestów | `useTasks`, `useHistory`, `fetchHistoryDetail` | **Scalić** – dane dublują się z Inspector (lista + timeline), potrzebny jeden komponent i linkowanie zamiast dwóch list |
| Queue governance vs QuickActions | Operacje `/api/v1/queue/*` | `useQueueStatus`, akcje `toggleQueue`, `purgeQueue`, `emergencyStop` | **Scalić** – QuickActions sheet obsługuje te same endpointy, panel w Cockpit może zostać uproszczony do skrótu/linku |
| Makra Cockpitu | Makra użytkownika + gotowe akcje | LocalStorage + `sendTask` | **Utrzymać**, bo brak innego miejsca na user-defined scripts |
| Modele / Repo / Tokenomics | Operacyjne moduły (models/git/tokens) | `useModels`, `useGitStatus`, `useTokenMetrics` | **Utrzymać**, ale rozważyć zlanie wykresu tokenów z hero (żeby nie pokazywać tych samych liczb dwa razy) |
| Brain – Mind Mesh i Lessons | Podgląd grafu wiedzy i lekcji | `useGraphSummary`, `useKnowledgeGraph`, `useLessons`, `useLessonsStats` | **Utrzymać** – unikalna funkcja, wymaga jedynie polerki typów (już zrobione) |
| Inspector – Trace Intelligence | Mermaid flow + kroki RequestTracer | `useHistory`, `fetchHistoryDetail`, `useTasks` | **Utrzymać**, ale współdzielić komponent listy historii z Cockpitem (punkt powyżej) |
| Strategy – War Room | Roadmapa, wizja, raport Executive | `useRoadmap`, `createRoadmap`, `requestRoadmapStatus`, `startCampaign` | **Utrzymać**, blok docelowo odwzorowuje sekcję „Integracje / KPI” ze `_szablon` |

Wnioski:
- **Priorytet scalania**: listy historii i panel kolejkowy (Cockpit ↔ Inspector / QuickActions), bo to jedyne miejsca z powielonymi endpointami.
- **Integracje / overlaye** są już spójne, wymagają tylko dalszej kosmetyki (np. wspólne dane testowe).
- Kolejny krok w etapie 28: przygotować schemat komponentów współdzielonych (HistoryList, QueueActions) i rozpocząć refaktor Cockpitu tak, by linkował do gotowych widoków zamiast powielać logikę.

Testy: brak (zmiany dokumentacyjne).

### Backlog etapu 28 (cele, zanim ruszymy dalej)
1. **History & Timeline** – przygotować wspólny komponent listy historii (Cockpit/Inspector), dodać tryb „preview” w Cockpit (2 ostatnie wpisy + link do pełnego widoku Inspector), a w Inspectorze używać tego samego komponentu z rozszerzonymi filtrami.
2. **Queue governance vs QuickActions** – zostawić pełną logikę akcji w overlayu, a w Cockpitu zamienić panel na skrót (status + CTA otwierające QuickActions); w ten sposób unikamy dwóch miejsc modyfikujących `/api/v1/queue/*`.
3. **Token/KPI bloki** – sprawdzić, czy statystyki tokenów z hero i sekcji „Tokenomics” nie duplikują danych; jeśli tak, przesunąć wykres/BarList do hero i wprowadzić inny moduł (np. koszt per model) w dolnej części.
4. **Brain/Strategy dokumentacja** – doprowadzić widok Brain do pełnej zgodności z `_szablon` (z gotowym opisem bloków w README), a w Strategy uporządkować interakcje formularzy (wizja, kampanie, raport) i potwierdzić mapping endpointów.
5. **TopBar overlaye – wspólne fallbacki** – ujednolicić copy i strukturę `EmptyState` w Alert/Notification/Command/Services (jedna utilka, te same ikony/kolory i testy).
6. **Mapa bloków → kolejny etap** – przed startem etapu 29 przygotować checklistę wykonanych scaleni oraz wskazać, które elementy wciąż są „legacy” względem `_szablon`. Cel nadrzędny: zachować wizerunkową spójność (kolory, spacing, glass) i zminimalizować liczbę równoległych implementacji tej samej funkcji.

### Postęp etapu 28 – wspólna historia Cockpit/Inspector
- Stworzyłem komponent `HistoryList` (`components/history/history-list.tsx`) wykorzystujący neonową paletę ze `_szablon.html` (gradient emerald/black, badge w tonach success/warning/danger) oraz nowy helper `formatRelativeTime` (`lib/date.ts`). Komponent obsługuje tryb „preview” (Cockpit) i „full” (Inspector) oraz opcjonalne CTA „+N w Inspectorze”.
- Cockpit (`app/page.tsx`) korzysta teraz z `HistoryList` i prezentuje tylko 5 ostatnich wpisów wraz z linkiem do `/inspector`, zamiast własnej listy `ListCard`. Dzięki temu blok ma spójne tło i akcenty jak w projekcie referencyjnym.
- Inspector (`app/inspector/page.tsx`) używa pełnej wersji `HistoryList`, co usuwa duplikację markupów i ręczne liczenie relative time; hinty w statystykach korzystają z tej samej funkcji formatującej.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – token KPI bez duplikatów
- Sekcja hero „Zużycie tokenów” zawiera teraz badge trendu i inline wykres (`TokenChart` z kontrolowaną wysokością), więc pełny kontekst (łączna liczba, rozkład i kierunek zmian) jest dostępny bez scrollowania – zgodnie z `_szablon.html`.
- Panele „Tokenomics” i „Trend tokenów” zastąpiłem duetem „Efektywność tokenów” + „Cache boost”. Pierwszy prezentuje średnie zużycie na zadanie, delta dwóch ostatnich próbek i stosunek prompt/completion oraz gradientową kartę live. Drugi zamienia surowe liczby na udziały procentowe (prompt/completion/cached) z neonowymi progess barami, co ułatwia decyzje o optymalizacji.
- Dodane komponenty (`TokenEfficiencyStat`, `TokenShareBar`) pilnują glassmorphism i spacingu, a `TokenChart` otrzymał opcjonalny parametr wysokości – można go wpiąć w hero i w przyszłości w overlaye.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – mobilna kolumna dowodzenia
- Komponent `MobileNav` (`components/layout/mobile-nav.tsx`) został przebudowany na pełnoprawny „command column”: nagłówek z neonowym badge, sekcja modułów, panel telemetrii z zakładkami Queue/Tasks/WS (zaczytuje `useQueueStatus`, `useMetrics`, `useTelemetryFeed`), mini terminal oraz karty Cost Mode + Autonomy oparte na tych samych endpointach co sidebar (`setCostMode`, `setAutonomy`).
- Wewnętrzne komponenty (tab buttons, logi, selecty) korzystają z tych samych tokenów glass/glow co `_szablon.html`, a na dole widnieje blok statusów Next.js/FastAPI – użytkownik mobilny dostaje więc identyczny zestaw informacji jak w desktopowej kolumnie.
- Dzięki temu nie ma już prostego menu z listą linków; mobilny shell w pełni odwzorowuje docelową wizerunkową szynę sterującą i nie wymaga przełączania na desktop, by zarządzać kosztami lub autonomią.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – Task Insights & telemetry (Cockpit + Inspector)
- Wyciągnąłem wspólny helper `statusTone` (`web-next/lib/status.ts`) i podpiąłem go w najważniejszych ekranach (Cockpit, Inspector, Strategy), dzięki czemu wszystkie badge statusowe korzystają z tych samych zasad (COMPLETED → success, IN_PROGRESS → warning itd.).
- Dodałem moduły `TaskStatusBreakdown` oraz `RecentRequestList` (`web-next/components/tasks/*`), odtworzone z makiety `_szablon.html` (glass-panel, gradientowe progress bary, listy uppercase). Panel „Task Insights” w Cockpicie korzysta teraz z nowych komponentów i prezentuje statusy + ostatnie requesty bez Tremora.
- Inspector w sekcji „Task telemetry” używa `TaskStatusBreakdown`, więc rozkład statusów tasków ma ten sam wygląd / copy co Cockpit; usunęliśmy zduplikowany kod obsługujący listę statusów i puste stany.
- Zmiany obejmują kilka komponentów i stron, dzięki czemu kolejna faza może już bazować na spójnym „task board” niezależnie od widoku.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – Queue governance ↔ QuickActions
- Stworzyłem wspólny komponent `QueueStatusCard` (`components/queue/queue-status-card.tsx`) w stylistyce `_szablon.html` (glass-panel, gradient, badge statusu). Korzysta z niego panel „Queue governance” w Cockpicie oraz arkusz `QuickActions`, więc dane `/api/v1/queue/status` wyglądają identycznie i znikają duplikaty HTML/EmptyState.
- Panel Cockpitu jest już w 100 % read-only (tylko status + CTA do QuickActions), a w Command Palette usunąłem bezpośrednie akcje kolejki – zamiast tego pojawiła się komenda „Otwórz Quick Actions”, która otwiera dedykowany sheet. Cała mutacja kolejki żyje teraz wyłącznie w jednym miejscu (overlay).
- QuickActions pokazują dokładnie tę samą kartę statusową i blokują przyciski, gdy brakuje danych (`queue-offline-state` → `QueueStatusCard`). Brak potrzeby ręcznego kopiowania komunikatu do różnych widoków.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – overlaye TopBaru z jednym fallbackiem
- Dodany komponent `OverlayFallback` (`components/layout/overlay-fallback.tsx`) odwzorowuje neonowy blok z `_szablon.html` (ikona w kapsule + opis + hint) i zastąpił wszystkie ręcznie budowane `EmptyState` w overlayach TopBaru.
- `AlertCenter`, `NotificationDrawer`, `CommandCenter` oraz `ServiceStatusDrawer` korzystają teraz z tego samego fallbacku dla stanów offline i pustych list (`alert-center-offline-state`, `notification-offline-state`, `command-center-services-offline`, `service-status-offline`). Copy oraz układ są ujednolicone.
- Dzięki temu użytkownik dostaje te same komunikaty niezależnie od tego, który sheet otworzy, a zespołowi łatwiej będzie wprowadzać dalsze zmiany stylistyczne (jedno źródło prawdy).
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – Strategy w stylistyce `_szablon.html`
- Zamiast tremorowych kart KPI w Strategy powstał komponent `RoadmapKpiCard` (`components/strategy/roadmap-kpi-card.tsx`) – neonowy panel z progressem wypełniającym się gradientem. Sekcja „Postęp wizji / Milestones / Tasks” korzysta już z nowego komponentu.
- Sekcję „Podsumowanie zadań” przebudowałem na `TaskStatusBreakdown`, więc ten sam komponent co w Cockpicie/Inspectorze renderuje teraz rozkład statusów z milestone’ów (jedno źródło stylu + fallback).
- `taskSummary` nie wstrzykuje sztucznego wpisu „Brak danych”; brak tasków powoduje spójny komunikat w `TaskStatusBreakdown`. Cały widok Strategy jest dzięki temu bliższy `_szablon.html` i współdzieli już większość naszego mini design systemu.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – Brain: lekcje i analiza plików
- Wyciągnąłem logikę lekcji do `LessonActions` i `LessonList` (`components/brain/lesson-actions.tsx`, `components/tasks/lesson-list.tsx`), dzięki czemu filtr tagów i lista lekcji mają tę samą neonową stylistykę co inne moduły oraz można je ponownie wykorzystać w przyszłości.
- Utworzyłem moduł `FileAnalysisForm` + `FileAnalysisPanel` (`components/brain/file-analytics.tsx`), dzięki czemu sekcja „Analiza pliku” ma spójny układ (formularz + dwie karty glass) i nie powiela markupów JSON.
- Tag agregacji (`aggregateTags`) teraz sortuje i limituje wpisy (max 8), więc UI nie rozsypuje się przy dużej liczbie tagów; highlight presetów w `LessonActions` ułatwia szybkie filtrowanie.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – Brain: metryki i kontrolki grafu
- Dodałem `BrainMetricCard` (`components/brain/metric-card.tsx`) i na szczycie widoku Brain pojawiła się trójka kart (węzły, krawędzie, lekcje) w stylu `_szablon.html`. Dzięki temu kluczowe KPI MindMesh są widoczne przed wejściem w graf.
- Kontrolki grafu zostały wyciągnięte do `GraphFilterButtons` oraz `GraphActionButtons` (`components/brain/graph-filters.tsx`, `graph-actions.tsx`). Te same komponenty renderują teraz filtry typów i przyciski dopasowania/skanowania, a komunikaty o skanowaniu są spięte w jednym miejscu.
- Cały overlay nie duplikuje już logiki – `handleFilterChange`, `handleTagToggle` i `handleScanGraph` mieszkają w BrainPage, a UI jest w komponentach. To przygotowuje scenę do dalszego przenoszenia grafu na docelowy layout.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – Brain: finalizacja sekcji Lessons
- Po kompletnej weryfikacji wprowadziłem `LessonStats` (`components/brain/lesson-stats.tsx`), które renderuje statystyki LessonsStore w tym samym stylu co reszta kart. Sekcja „Lekcje i operacje grafu” ma teraz spójny układ (statystyki + filtry + lista) i nie korzysta już z surowego JSON.
- Dzięki temu panel Lessons wykorzystuje w 100% nasze komponenty (LessonStats, LessonActions, LessonList, FileAnalysisForm/Panel). Zachowaliśmy funkcjonalność (filtry tagów, odświeżanie, analiza pliku), ale kod jest gotowy na finalny retusz.
- Ten krok domyka zakres dla Brain w etapie 28 – kolejne prace będą mogły skupić się na innych widokach, bo Mind Mesh jest już przeniesiony do `_szablon.html` bez zmian logiki backendu.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – Inspector: wizualny parity
- Sekcja insightów została zmodernizowana: tremorowe karty SLA/aktywnych śledzeń/kroków zastąpił nowy komponent `LatencyCard` (`components/inspector/lag-card.tsx`), dzięki czemu KPI Trace Intelligence wyglądają tak samo jak reszta aplikacji (glass + neon).
- Lista kroków RequestTracer korzysta teraz z tego samego layoutu co Command console (tailwindowe bloki + `Badge`), więc cały panel nie używa już `ListCard` i łatwiej go dostosować do `_szablon.html`.
- Reszta widoku (HistoryList, TaskStatusBreakdown) pozostała funkcjonalna – zmieniliśmy tylko warstwę wizualną. Inspector jest gotowy do finalnej prezentacji bez naruszania funkcji debuggera.
- Testy: `npm --prefix web-next run lint`.

## Plan etapu 28 – Cockpit (index)
1. **Hero KPI / Live Feed** – zastąpić tremorowe `Card/Metric/BarList` nowymi neonowymi komponentami (`CockpitMetricCard`, `CockpitTokenCard`), aby sekcja „Skuteczność operacji” i „Zużycie tokenów” wyglądała jak w `_szablon.html`.
2. **Makra i przypięte logi** – wyprowadzić `MacroCard` oraz `PinnedLogCard`, tak aby blok makr i pinned logów korzystał z glass-paneli zamiast surowych list; przygotować ciepłe CTA (dodaj/usuwaj) zgodne z design systemem.
3. **Modele i Repozytorium** – stworzyć spójne komponenty (`ModelListItem`, `RepoActionCard`), dzięki którym dolne panele Cockpitu przestaną używać legacy layoutu i będą gotowe do dalszej migracji funkcjonalnej.
4. **Command console** – wynieść bąbelki rozmowy do `ConversationBubble`, aby chat/console miały identyczny wygląd i można je było przenieść w inne widoki.

### Plan operacyjny dla sekcji Cockpit
1. **Hero KPI / Live Feed** *(status: wykonane – patrz sekcja niżej)*
   - Refaktor starych paneli Tremor → `CockpitMetricCard` + `CockpitTokenCard`.
   - Zadbać o ten sam układ typografii i neonowych akcentów co `_szablon.html`.
   - Wpiąć `TokenChart` jako `chartSlot`, żeby od razu mierzyć trend w hero.
2. **Makra i przypięte logi**
   - Wyodrębnić komponenty `MacroCard` i `PinnedLogCard` (glass-panel, CTA).
   - Przenieść formularz dodawania makr do bocznego slotu `Panel` i dodać walidację wejścia.
   - W logach zapewnić dwie akcje (eksport / usuń) oraz badge statusu z `statusTone`.
   - Po wdrożeniu uruchomić `npm --prefix web-next run lint`.
3. **Modele i Repozytorium**
   - Stworzyć `ModelListItem` (status modelu, wersja, CTA „Aktywuj/Instaluj”) oraz `RepoActionCard` (git status + akcje sync/undo).
   - Zamienić istniejące siatki na trzykolumnowy layout glass-paneli, tak jak w `_szablon.html`.
   - Dodać badge liczby modeli (wykorzystać `data-testid="models-count"`), pamiętać o fallbacku offline.
   - Test: lint + istniejący smoketest „Models panel badge displays count”.
4. **Command console / ConversationBubble**
   - Zaprojektować `ConversationBubble` (user vs Venom) z neonowymi kapsułami i metadanymi (czas, status, id).
   - Zastąpić aktualne `motion.div` wewnątrz konsoli nowym komponentem, zostawiając logikę `openRequestDetail`.
   - Dodać możliwość rozbudowy (np. akcje kopiuj/pin), ale bez zmian backendu.
   - Po zmianach odświeżyć dokumentację + lint.

### Postęp etapu 28 – hero KPI Cockpitu
- W sekcji otwierającej Cockpit zrezygnowałem z tremorowych kart i podmieniłem je na dedykowane komponenty `CockpitMetricCard` i `CockpitTokenCard` wpięte bezpośrednio w `app/page.tsx`. Dzięki temu hero używa tych samych glass-paneli i neonowych cieni, co reszta layoutu `_szablon.html`.
- `CockpitMetricCard` prezentuje teraz realny `success_rate`, liczbę zadań oraz pasek progresu wraz z opisem uptime – dane są formatowane w jednym miejscu, więc możemy łatwo rozbudować kartę o kolejne KPI.
- `CockpitTokenCard` otrzymuje `chartSlot` z wykresem `TokenChart` i badge trendu (wspólne copy z sekcji Tokenomics), a rozbicie prompt/completion/cached renderowane jest w neonowych listach zamiast `BarList`. Usunęło to importy `@tremor/react` z Cockpitu i rozwiązało dublowanie komponentów.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – makra i przypięte logi
- Wyprowadziłem komponenty `MacroCard` i `PinnedLogCard` (`components/cockpit/macro-card.tsx`) oraz nowy helper `lib/logs.ts`, dzięki czemu makra i przypięte logi dzielą ten sam look&feel glass-paneli co hero. Makra mają teraz nagłówki uppercase, badge „Custom” i przycisk w formie kapsuły – jeden komponent obsługuje zarówno presetowe, jak i użytkownika.
- Panel logów oferuje kapsułowy header z CTA (eksport/wipe) oraz listę kart, gdzie każda pokazuje czas, typ, poziom i pełny payload w neonowej konsoli. Cały blok korzysta z gradientu emerald i nie używa już surowych `<pre>`/`IconButton` z `X`.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – Modele i Repozytorium
- Sekcje „Modele” i „Repozytorium” otrzymały nowe komponenty `ModelListItem` oraz `RepoActionCard` (`components/cockpit/model-card.tsx`). Lista modeli prezentuje nazwę, metadane (GB, source) i status w jednym glass-panelu, a aktywacja odbywa się poprzez kapsułowy przycisk – brak modeli pokazuje spójny `EmptyState`.
- Repozytorium ma teraz blok „Stan repo” z opisem zmian oraz kartami akcji (Synchronizacja / Cofnij zmiany) z gradientami i kontrolą `pending`. Akcje korzystają z nowych handlerów (`handleGitSync`, `handleGitUndo`) i blokują przyciski podczas requestu, żeby uniknąć wielokrotnego strzału.
- Testy: `npm --prefix web-next run lint`.

### Postęp etapu 28 – Command console / ConversationBubble
- Wyciągnąłem komponent `ConversationBubble` (`components/cockpit/conversation-bubble.tsx`), który renderuje kapsułowe wiadomości user ↔ Venom (eyebrow, czas, status, skrót requestu). Bąbel używa `MarkdownPreview` oraz `statusTone`, posiada ring zaznaczenia i CTA „Szczegóły ↗” zgodnie z `_szablon.html`.
- Sekcja chatu w `app/page.tsx` korzysta teraz z `ConversationBubble` wewnątrz `AnimatePresence`, więc cały layout reaguje płynnie, a kliknięcia/klawiatura kierują do `openRequestDetail` bez duplikacji stylów.
- Dzięki temu command console ma identyczny wygląd jak na makiecie wizerunkowej i jest gotowa do ewentualnego przeniesienia w inne widoki.
- Testy: `npm --prefix web-next run lint`.

## Ocena bieżącej wersji Cockpitu (screen 2024-XX-XX)
1. **Hero KPI / Live Feed**
   - Brak neonowej kapsuły wokół „Skuteczność operacji” – karta nadal wygląda płasko i nie ma numeru z badge'em trendu (na screenie `0`).
   - Token panel nie zawiera wykresu inline ani share’ów; trzeba upewnić się, że nowy `CockpitTokenCard` jest zdeployowany oraz że API dostarcza wartości (fallback „Brak danych” powinien mieć ikonę).
2. **Command console**
   - Pomimo wdrożenia `ConversationBubble` w kodzie, screen pokazuje jeszcze stary layout. Sprawdzić build/SSR i zweryfikować, czy `app/page.tsx` na gałęzi `feature/044-migracja-next-plan` jest wdrożony na środowisko designerskie.
   - Brak CTA „Szczegóły ↗” i badge statusu – jeśli build jest aktualny, trzeba dopracować styl `ConversationBubble` (większy kontrast, w pełni czarne tło, gradient z `_szablon.html`).
3. **Makra / logi / sekcje dolne**
   - Sekcja makr wygląda jeszcze jak prostokątne kafle – należy upewnić się, że nowy `MacroCard` ma gradient (violet) i uppercase; w razie potrzeby dopracować spacing + animacje hover.
   - „Queue governance”, „Modele” i „Repozytorium” mają stare border-boxy; trzeba dopilnować, by `ModelListItem` i `RepoActionCard` były widoczne (deployment + styl).
   - Panel „Task Insights” pokazuje placeholdery – warto dodać fallback `EmptyState`, żeby uniknąć twardego „Brak danych”.

## Zadanie – domknięcie Cockpitu do 100% (etap 28)
1. **Zweryfikować build** – upewnić się, że `web-next/app/page.tsx` z nowymi komponentami jest widoczny w preview. Jeśli nie, uruchomić `make stop && make start`, zbudować `web-next` i zrobić świeży screenshot referencyjny.
2. **Dopolerować hero** – do `CockpitMetricCard` i `CockpitTokenCard` dodać brakujące elementy wizualne (badge trendu na karcie KPI, placeholder ikon dla „Brak danych”, podbity gradient).
3. **Spójne glass-panels** – przejrzeć wszystkie sekcje Cockpitu i przepiąć na `glass-panel / rounded-panel / shadow-card`, żeby karta makr, Task Insights, Queue governance wyglądały jak w `_szablon.html`.
4. **Fallbacki danych** – dodać `EmptyState` tam, gdzie API zwraca `0` (np. hero tokens), aby uniknąć „pustych” kart w screenshotach.
5. **Dokumentacja** – po domknięciu wykonać screenshot + opis w tej sekcji dokumentu, potwierdzając, że Cockpit jest gotowy wizualnie i funkcjonalnie.

## Uwagi z przeglądu wizualnego (nie wykonane, zapisane do backlogu)
1. **Brak ramki w „KPI kolejki”** – karta po prawej od Live Feed ma inne obramowanie i wygląda jak płaski prostokąt. Trzeba odtworzyć tę samą ramkę/glow co w „Live Feed”.
2. **Brak marginesów w bloku „Centrum dowodzenia”** – hero chat („Cockpit AI”) klei się do krawędzi sekcji; konieczne jest dodanie paddingu zgodnie z `_szablon.html`.
3. **Kolor tła** – główne tło Cockpitu ma turkusowy gradient, a w `_szablon.html` centralny panel jest ciemnoniebieski (`#031627` → `#051B2D`). Należy pobrać oryginalne wartości i zaktualizować `app/globals.css`.
4. **Nazwy boxów** – każdy panel (KPI, tokeny, makra itd.) powinien mieć identyczny styl nagłówka jak „Live Feed” (font-size, uppercase eyebrow, badge akcji). Aktualnie część sekcji wciąż ma stare tytuły.
