# ROLA: Senior Frontend Architect & UI/UX Designer

# CEL GŁÓWNY:
Przeprowadzić migrację dashboardu Venom do Next.js, tworząc interfejs klasy "Sci-Fi / Enterprise Command Center". Funkcjonalność 1:1 ze starym systemem, ale wygląd ma być nowoczesny, ciemny i "premium".

# KONTEKST PROJEKTU:
Backend: FastAPI (port 8000).
Nowy Frontend: Next.js (port 3000).

# WYMAGANY STOS TECHNOLOGICZNY (THE STACK):
1.  **Framework:** Next.js 14+ (App Router).
2.  **Styling:** Tailwind CSS + `tailwindcss-animate`.
3.  **UI Lib:** shadcn/ui (pełna baza).
4.  **Animacje:** `framer-motion` (Kluczowe dla efektu "płynności").
5.  **Viz:** Tremor (Dostosowany kolorystycznie do ciemnego motywu).
6.  **Icons:** Lucide React.
7.  **Fonts:** `Geist Sans` (UI) + `JetBrains Mono` (Kod/Logi).

# ZADANIE 1: STRUKTURA KATALOGÓW
(Bez zmian - zachowaj strukturę app/brain/inspector/strategy)

# ZADANIE 2: DESIGN SYSTEM & ESTETYKA (BARDZO WAŻNE)
Aplikacja ma wyglądać jak profesjonalne narzędzie developerskie (np. Vercel, Linear, Raycast).
1.  **Kolorystyka:**
    * Tło: `bg-zinc-950` (bardzo głęboka czerń/szarość).
    * Panele: `bg-zinc-900/50` z `backdrop-blur-md` (Glassmorphism).
    * Bordery: `border-zinc-800`.
    * Akcent (Primary): `violet-500` lub `indigo-500` (dla elementów AI).
2.  **Layout:**
    * Użyj `Grid` i `Flexbox` do idealnego rozmieszczenia paneli.
    * Główny Layout (`layout.tsx`) musi zawierać **Sidebar** (Pasek boczny) z ikonami nawigacji, który jest zawsze widoczny.
3.  **Interakcje:**
    * Wszystkie przyciski mają mieć stan `:hover` i `:active`.
    * Czat: Wiadomości mają pojawiać się z animacją (użyj `AnimatePresence` z framer-motion).
    * Logi: Terminal ma wyglądać jak prawdziwa konsola (czarne tło, monospaced font, zielony kursor).

# ZADANIE 3: SZCZEGÓŁOWY PLAN MIGRACJI EKRANÓW

## 1. Global Layout (`layout.tsx`)
* Stwórz stały **Sidebar** po lewej stronie (nawigacja do: Cockpit, Brain, Inspector, Strategy).
* Dodaj górny pasek (**TopBar**) ze statusem połączenia WebSocket (pulsująca kropka) i przełącznikiem trybu (Pro/Eco).

## 2. Cockpit View (`page.tsx`) - "Centrum Dowodzenia"
* **Układ:** 3 kolumny.
    * Lewa: Lista Agentów (Status aktywności, ostatnia akcja).
    * Środek (Szeroki): Okno Czatu (wygląd jak ChatGPT/Claude, ale z obsługą Markdown i składnią kodu). Input na dole przyklejony ("sticky").
    * Prawa: "Live Feed" (Logi systemowe) + Widgety Tremor (Koszt sesji, Zużycie Tokenów).

## 3. Brain View (`brain/page.tsx`) - "The Mind"
* Pełnoekranowy widok grafu.
* Na wierzchu (Overlay) pływający panel kontrolny (Glassmorphism) z filtrami: "Pokaż Agenty", "Pokaż Pliki".
* Kliknięcie w węzeł otwiera **Sheet** (panel boczny shadcn) ze szczegółami węzła.

## 4. Inspector View (`inspector/page.tsx`) - "Debugging"
* Lista zadań po lewej (ScrollArea).
* Główny obszar: Diagram Mermaid renderowany na ciemnym tle.
* Użyj `transform-zoom` (biblioteka `react-zoom-pan-pinch` lub podobna) do nawigacji po dużych diagramach.

## 5. Strategy View (`strategy/page.tsx`) - "War Room"
* Wygląd dashboardu menedżerskiego.
* Duże karty KPI na górze (Postęp wizji).
* Poniżej lista "Milestones" jako Accordion (rozwijane listy).
* Paski postępu (Progress Bar) powinny być animowane.

# INSTRUKCJA DLA AGENTA:
1.  Najpierw zainstaluj wymagane pakiety (`framer-motion`, `clsx`, `tailwind-merge`, etc.).
2.  Skonfiguruj `tailwind.config.ts` dodając kolory i animacje.
3.  Stwórz pliki komponentów UI (`components/ui/...`).
4.  Napisz kod dla `layout.tsx` i poszczególnych `page.tsx` dbając o bogaty, dopracowany wygląd (używaj klas takich jak `shadow-lg`, `ring-1`, `ring-white/10` dla efektu głębi).

Zacznij od podania listy komend instalacyjnych, a potem generuj kod plik po pliku.

## Postęp – 2025-12-13
- Dodano stack UI (framer-motion, Tremor, shadcn/Radix, react-zoom-pan-pinch, tailwindcss-animate) wraz z `tailwind.config.ts` i glassmorphism w `globals.css`.
- Layout otrzymał stały Sidebar + TopBar z przełącznikiem Pro/Eco, a Cockpit przebudowano na 3 kolumny (lista agentów, czat AnimatePresence, terminalowe logi + widgety Tremor).
- Brain ma pełnoekranowy graf z overlayem filtrów i panelem Sheet dla detali węzłów; Flow Inspector został przeniesiony do `/inspector` z zoomowalnym diagramem Mermaid i listą requestów.
- War Room (Strategy) przebudowany na dashboard KPI: hero panel z akcjami, karty Tremor + ProgressBar, accordion milestones z animowanymi paskami oraz panel wizji/raportów w stylu shadcn; dodano też bar listę statusów tasków.
- Inspector 2.0: dodano hero panel z telemetrią, karty Tremor, rozbudowaną listę requestów + task telemetry, kontrolki zoom/drag dla Mermaid, timeline kroków z filtrem/kopiowaniem JSON oraz panel telemetrii z kartami StatCard opisującymi status i metryki bieżącego flow.
- Cockpit Request Insight: czat otrzymał markdownowe bańki z możliwością otwarcia szczegółów requestu, a panel historii otwiera boczny Sheet z telemetrią (status, czasy, prompt) i listą kroków z kopiowaniem JSON + szybkim przejściem do Inspectora.
- Command Center (TopBar): dodano globalny panel dowodzenia (Sheet) wywoływany z TopBaru z szybkimi skrótami nawigacyjnymi, kartami Tremor dla kolejki/metryk, agregacją statusów zadań oraz listą usług z ich kondycją; TopBar ma teraz dedykowany przycisk „Command Center”.
- Alert Center: TopBar posiada przycisk Alert Center otwierający panel z feedem `/ws/events`, filtrami poziomów logów, kopiowaniem JSON i listą wpisów z kolorystycznym oznaczeniem poziomu – można szybko wychwycić błędy bez opuszczania bieżącego widoku.
- Mobile Nav: dodano mobilny przycisk menu (Sheet po lewej) z tymi samymi linkami co Sidebar + status systemu, dzięki czemu na telefonach/tabletach można przełączać się między widokami Cockpit/Brain/Inspector/Strategy.
- TopBar Status Pills: w pasku górnym wyświetlane są trzy kapsuły (Queue, Success, Tasks) korzystające z `useQueueStatus`, `useMetrics`, `useTasks`, dzięki czemu operator odczyta limity kolejki, pending i aktualny success rate bez schodzenia do Cockpitu.
- Quick Actions (TopBar): dodano przycisk otwierający panel z akcjami /api/v1/queue (pause/resume, purge, emergency stop) – dostępny globalnie w TopBarze obok Alert/Command Center, z informacją o stanie kolejki i komunikatami o wyniku operacji.
- Command Palette: TopBar obsługuje skrót `⌘K`/`Ctrl+K` oraz przycisk otwierający paletę komend z wyszukiwaniem nawigacji i akcji kolejki (toggle/purge/emergency) – wykonuje akcje asynchronicznie i pokazuje wynik, umożliwiając szybkie przełączanie ekranów i operacje bez opuszczania bieżącego widoku.
- Cockpit Macro Launcher: dodano sekcję makr z gotowymi poleceniami (graf scan, status usług, roadmap sync, git audit) – każde makro uruchamia `sendTask`, pokazuje stan wysyłki i odświeża kolejkę/task listę po sukcesie.
- Live Feed – Pinboard: strumień logów umożliwia przypinanie wpisów, kopiowanie ich payloadów do JSON oraz czyszczenie listy – dodano stan `pinnedLogs` z przyciskami przypnij/usuń, by operator mógł zachować kluczowe logi podczas debugowania.
- Notifications Drawer: TopBar ma dodatkowy przycisk otwierający szufladę z ostrzeżeniami/błędami (wydzielone z feedu `/ws/events`), filtrowanymi po poziomie logów i prezentowanymi w jednym miejscu.
- Task Insights: Cockpit obejmuje panel analityczny (BarList statusów historii + lista ostatnich requestów) bazujący na `useHistory`, który pomaga ocenić tempo realizacji i ostatnie statusy bez przechodzenia do Inspectora.
- Persistent Macros: makra Cockpitu zapisują się w `localStorage`, można je resetować jednym kliknięciem, a po odświeżeniu UI przywraca zestaw użytkownika.
- Live Feed Tools: terminal logów ma filtr tekstowy oraz możliwość eksportu przypiętych wpisów do pliku JSON – to uzupełnia wcześniejsze pinowanie i ułatwia analizę offline.
- Button refactor (TopBar): wprowadzono wspólny komponent `Button` z wariantami, który zastąpił ręcznie stylowane przyciski w TopBarze (Alert/Notifications/Command/Quick Actions), upraszczając klasy i ujednolicając hover/focus.
