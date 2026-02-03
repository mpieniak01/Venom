# ZADANIE 052: Pasek statusu operacyjnego (floating bottom bar)

## Cel
- Dodać do `web-next` kompaktową dolną belkę statusową, która stale informuje o stanie zasobów oraz statusie repozytorium/wersji aplikacji – bez konieczności przewijania do panelu „Zasoby” lub sekcji Git.
- Zapewnić wizualną spójność z istniejącym TopBar-em (gradient, blur, neonowe obramowanie), jednocześnie zachowując jeden wiersz informacji, aby nie zasłaniać kokpitu.

## Zakres funkcjonalny
1. **UI/UX**
   - Pasek przyklejony do dołu widoku (`position: sticky/fixed`, pełna szerokość, maks. 48px wysokości).
   - Stylizacja: analogia do górnej belki (`bg-black/60`, `backdrop-blur`, `border-white/10`, delikatny gradient), z responsywnym układem `flex` + `gap`.
   - Zawartość jednej linii: sekcja metryk (CPU/GPU/RAM/VRAM/Dysk/Koszt) + separator + sekcja repo (wersja, commit, status git).
   - W mobile <1024px: pasek również widoczny, ale wartości skracane (np. `CPU 42%`, `GPU 3%`, `RAM 8/16 GB`, `VRAM 12/24 GB`, `Dysk 40%`, `Cost $0.12`).
2. **Dane z „Zasoby”**
   - Wykorzystać istniejące hooki (`useModelsUsage`, `usageMetrics` z `web-next/app/page.tsx`) i funkcje formatowania (`formatPercentMetric`, `formatGbPair`, `formatVramMetric`).
   - Zaprezentować w pasku skrócone wartości (np. `CPU 34% | GPU 2% | RAM 7/16 GB | VRAM 10/24 GB | Dysk 20% | Koszt $0.31`), a w trybie offline pokazać fallback `—` oraz tooltip „Brak danych API”.
   - Aktualizacja co 10 s (taki sam interwał jak panel), pamiętać o `usePolling` aby dane odświeżały się również poza kokpitem.
3. **Wersjonowanie + git**
   - Wykorzystać `useGitStatus()` do odczytu `branch`, `dirty` oraz `changes/status`.
   - Dodać informację o aktualnym commicie/wersji: w trakcie buildu Next.js generować plik (np. `public/meta.json` lub `NEXT_PUBLIC_APP_VERSION`) zawierający `shortSha`, `buildNumber`, `buildTimestamp`. W pasku wyświetlać `vX.Y.Z (#<shortSha>)`.
   - Pokazywać stan repo: `Repo: czyste` (ikona ✅) gdy `dirty === false`, oraz `Repo: zmiany lokalne` (ikona ⚠️) gdy `dirty === true`, z tooltipem z `git.changes`.
4. **Wejścia/wyjścia**
   - Pasek ma być niezależnym komponentem (np. `components/layout/system-status-bar.tsx`) i podłączony globalnie w `app/layout.tsx` tuż nad `</body>`, aby był widoczny w każdym widoku (Cockpit, Brain, Inspector, Strategy).
   - Zapewnić `data-testid="bottom-status-bar"` + sub-selektory (`data-testid="status-bar-resources"`, `status-bar-version`, `status-bar-repo`), aby Playwright mógł weryfikować treści.

## Stan na dziś
- Panel „Zasoby” (`web-next/app/page.tsx`, linie ~1140–1185) prezentuje wszystkie wymagane metryki, ale tylko w kokpicie i nie w kompaktowej formie.
- Hook `useModelsUsage` oraz pomocnicze funkcje formatowania już istnieją i zwracają CPU/GPU/RAM/VRAM/Dysk oraz licznik modeli.
- Sekcja Git znajduje się w kokpicie (`Panel "Status git"`), wykorzystuje `useGitStatus`, jednak brak informacji o aktualnym shorcie commita/wersji aplikacji – API nie zwraca tej danej.
- TopBar zapewnia wizualny wzorzec gradientu/neonu; brak odpowiednika przy dolnej krawędzi.

## Plan wdrożenia
1. ✅ **Meta-wersja w buildzie**
   - Skrypt `scripts/generate-meta.mjs` tworzy `public/meta.json`, a `useAppMeta()` odczytuje dane wersji/commita w UI.
2. ✅ **Nowy komponent belki**
   - `SystemStatusBar` agreguje `useModelsUsage`, `useTokenMetrics`, `useGitStatus`, `useTranslation` oraz `useAppMeta`, zapewniając layout zgodny z wymaganiami.
3. ✅ **Fallbacki i odświeżanie**
   - Braki danych API skutkują czytelnymi fallbackami (`—`, komunikaty repo offline), a pobieranie odbywa się poprzez istniejące hooki pollingowe.
4. ✅ **Testy i dokumentacja**
   - Playwright zawiera scenariusz „Bottom status bar jest widoczna na każdej podstronie”; README/plan opisują źródła metryk i meta wersji.

## Definicja ukończenia
- Pasek dostępny i czytelny na wszystkich widokach (Desktop + Mobile), zajmuje maks. jeden wiersz.
- W trybie offline pokazuje jednoznaczny komunikat + brak błędów w konsoli.
- `npm --prefix web-next run test:e2e` zawiera nowy test dla dolnej belki i przechodzi.
- Dokumentacja (`docs/FRONTEND_NEXT_GUIDE.md` lub README) opisuje strukturę danych oraz sposób aktualizacji meta wersji.

## Ryzyka / pytania
- API `/api/v1/git/status` nie zwraca shorcie commita – konieczne rozszerzenie backendu lub generacja pliku meta po stronie buildu (preferowana opcja, ale wymaga dodatkowego kroku CI).
- Pasek nie może zasłaniać krytycznych elementów (np. aliasy w Dockach) – należy sprawdzić overlay vs. scroll i dodać `padding-bottom` w `layout` aby kontent nie był przykryty.
- W scenariuszach kioskowych (np. fullscreen) trzeba zapewnić, że pasek nie koliduje z modals (Command Center, Quick Actions).

## Status realizacji
- ✅ Dodano skrypt `scripts/generate-meta.mjs`, który przed `dev/build` zapisuje `public/meta.json` z wersją, shorciem commita i timestampem (wykorzystywanym przez UI).
- ✅ Utworzono komponent `SystemStatusBar` wyświetlany na każdej podstronie (`app/layout.tsx`), korzystający z hooków `useModelsUsage`, `useTokenMetrics`, `useGitStatus` oraz nowego hooka `useAppMeta` – pasek odwzorowuje skrócone wartości CPU/GPU/RAM/VRAM/Dysk/Koszt + status repo/wersję.
- ✅ Dodano tłumaczenia (`pl/en/de`), test Playwrighta pokrywający obecność belki na `/` i `/brain` oraz dodatkowy padding w layoucie, aby kokpit nie był zasłonięty.
