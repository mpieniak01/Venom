# 78: Standaryzacja stylow w web-next (CSS/komponenty)

## Cel
- Sprawdzic, czy te same elementy UI maja rozne style i gdzie brakuje standaryzacji.
- Ujednolicic bazowe wzorce dla kart/paneli, przyciskow i naglowkow.
- Wykryc i naprawic rozjazdy miedzy dokumentacja (`web-next/README.md`) a kodem.

## Zakres
- Tylko `web-next` (CSS + React/TSX).
- Komponenty UI: `web-next/components/ui/*`, `web-next/app/globals.css`.
- Widoki: `web-next/components/**`, `web-next/app/**`.

## Wstepna analiza (na teraz)
- Karty/panele sa stylowane roznymi zestawami klas (`glass-panel`, `rounded-3xl border border-white/10 bg-white/5 p-4 text-sm text-white shadow-card`, itd.).
- `surface-card` jest uzywane w kilku miejscach, ale nie ma definicji w `web-next/app/globals.css` mimo ze README to deklaruje.
- Przyciski: istnieje `Button`/`IconButton`, ale sporo widokow korzysta z surowych `<button>` z recznie dobranymi klasami.
- Naglowki sekcji: jest `SectionHeading`, ale wiele widokow buduje naglowki recznie z innym `tracking` i rozmiarami.

## Kandydaci do standaryzacji (priorytet)
### 1) Karty/panele
- Ujednolicic wzorzec kart oparty o `Panel`/`glass-panel` oraz `shadow-card`.
- Kandydaci do migracji na wspolny wrapper:
  - `web-next/components/cockpit/model-card.tsx`
  - `web-next/components/cockpit/kpi-card.tsx`
  - `web-next/components/brain/metric-card.tsx`
  - `web-next/components/strategy/roadmap-kpi-card.tsx`
  - `web-next/components/inspector/lag-card.tsx`
  - `web-next/components/layout/system-status-panel.tsx` (uzywa `surface-card`)

### 2) `surface-card` (brak definicji)
- Zdefiniowac `surface-card` w `web-next/app/globals.css` albo zastapic uzycia `glass-panel`/`Panel`.
- Kandydaci:
  - `web-next/components/layout/system-status-panel.tsx`
  - `web-next/components/layout/command-center.tsx`
  - `web-next/components/layout/service-status-drawer.tsx`

### 3) Przyciski (CTA)
- Ustandaryzowac uzycie `Button`/`IconButton` zamiast recznych `<button>`.
- Kandydaci do migracji:
  - `web-next/components/layout/top-bar.tsx`
  - `web-next/components/layout/mobile-nav.tsx`
  - `web-next/components/brain/brain-home.tsx`
  - `web-next/components/calendar/*`
  - `web-next/components/config/*`

### 4) Naglowki sekcji
- Ujednolicic naglowki przez `SectionHeading` (lub wspolny wariant klas).
- Kandydaci:
  - `web-next/components/layout/system-status-panel.tsx`
  - `web-next/components/brain/brain-home.tsx`
  - `web-next/components/cockpit/cockpit-home.tsx` (lokalne sekcje)

## Dodatkowe obserwacje (spojnosc HTML/CSS na podstronach)
- Standaryzacja jest czesciowa: `SectionHeading` jest uzywany tylko w czesci widokow, reszta ma reczne naglowki z innym `tracking` i rozmiarami.
- W wielu miejscach nadal uzywane sa surowe `<button>` zamiast `Button`/`IconButton`.
- Karty/panele wystepuja w kilku wariantach (`glass-panel`, `surface-card`, `card-shell`/`card-base`) bez jednego wzorca.
- To oznacza brak jednolitej logiki HTML i mapowania do CSS dla tych samych elementow UI.

## Wymaganie
- Nalezy wystandaryzowac logike HTML i mapowanie do CSS dla podstawowych elementow UI (karty/panele, przyciski, naglowki) na wszystkich podstronach `web-next`.
- Boxy (karty/panele) oraz sekcje tytulu/naglowka maja byc budowane podobnie w calym systemie.
- Dopuszczalne sa 2-3 warianty (np. primary/secondary/compact), ale z zachowaniem jednego standardu klas i struktury HTML.

## Gleboka analiza (co jest niespojnie)
### Karty/panele (boxy)
- Obecnie rownolegle istnieja 3 style: `glass-panel`, `surface-card`, `card-shell/card-base`.
- W `components/ui/Panel` obowiazuje `glass-panel`, ale wiele kart nie korzysta z tego wzorca.
- Skutek: te same typy boxow maja inna ramke, tlo, promienie i cien.

### Naglowki sekcji
- `SectionHeading` wystepuje tylko w wybranych widokach.
- Reszta sekcji ma recznie skladane naglowki z innym `tracking`, rozmiarami i spacingiem.
- Skutek: brak jednolitej hierarchii typografii.

### Przyciski
- `Button`/`IconButton` sa standardem w UI, ale liczne widoki uzywaja `<button>` z recznymi klasami.
- Skutek: niespojne stany hover/focus/disabled i rozne warianty CTA.

### Tokeny z README vs CSS
- `surface-card` deklarowane w README, ale do niedawna brak definicji w CSS.
- Skutek: rozjazd dokumentacji i implementacji.

## Mapa hierarchii naglowkow (H1-H4)
### H1 (tytul strony + eyebrow + opis)
Uzycie `SectionHeading` z `as="h1"`, `size="lg"`:
- Cockpit: `web-next/components/cockpit/cockpit-home.tsx` (Dashboard Control / Centrum Dowodzenia AI)
- Strategy: `web-next/app/strategy/page.tsx`
- Benchmark: `web-next/app/benchmark/page.tsx`
- Brain: `web-next/components/brain/brain-home.tsx`
- Calendar: `web-next/components/calendar/calendar-home.tsx`
- Config: `web-next/components/config/config-home.tsx`
- Inspector: `web-next/app/inspector/page.tsx`
- Docs LLM Models: `web-next/app/docs/llm-models/page.tsx`

### H2 (naglowki boxow/sekcji na stronie)
Obecne H2:
- `web-next/components/cockpit/cockpit-home.tsx` — "Aktywnosc systemowa" (text-lg).
- `web-next/components/config/services-panel.tsx` — "Profile szybkie", "Historia akcji" (text-lg).
- `web-next/components/calendar/calendar-view.tsx` — naglowek sekcji (text-xl + border-bottom).

Docelowo H2 powinno obejmowac rowniez:
- "Command Console / Cockpit AI / Chat operacyjny..." (obecnie `SectionHeading` z `as="h1"` w `web-next/components/cockpit/cockpit-home.tsx`) — do korekty na H2.

### H3 (podsekcje w ramach boxow/sekcji)
Obecne H3:
- `web-next/components/layout/command-center.tsx` (powtarzalne naglowki kart).
- `web-next/components/cockpit/macro-card.tsx`
- `web-next/app/strategy/page.tsx` (Vision)
- `web-next/components/ui/panel.tsx` i `web-next/components/ui/sheet.tsx` (komponenty bazowe)
- `web-next/components/config/parameters-panel.tsx` (sekcje)
- `web-next/components/config/services-panel.tsx` (tytuly serwisow)
- `web-next/components/calendar/event-form.tsx`
- `web-next/components/calendar/calendar-view.tsx` (naglowki eventow)

### H4 (subsekcje w ramach boxow)
Obecne H4:
- `web-next/components/brain/brain-home.tsx` (podsumowania/statystyki/lekcje)
- `web-next/components/benchmark/benchmark-results.tsx`
- `web-next/components/benchmark/benchmark-console.tsx`
- `web-next/components/cockpit/cockpit-home.tsx` (sekcje w kartach)
- `web-next/app/inspector/page.tsx` (szczegoly sekcji)

### Rozjazdy wizualne (duze odchylenia)
- `web-next/components/calendar/event-form.tsx` ma `h3` w rozmiarze `text-xl`, gdy reszta H3 jest zwykle `text-lg`.
- `web-next/components/calendar/calendar-view.tsx` ma H2 w `text-xl` + border-bottom (bardziej "page-header" niz box).
- `web-next/components/config/services-panel.tsx` uzywa H3 w `text-sm` dla nazw serwisow, co odbiega od standardu `text-lg`.
- `web-next/components/cockpit/cockpit-home.tsx` ma dodatkowy `SectionHeading` dla "Command Console" ustawiony jako H1 (powinno byc H2).

## Lista zmian do wykonania (propozycja)
### 1) Standaryzacja boxow
- Ustal jeden bazowy komponent/klase dla kart (np. `card-shell` + warianty `card-base` / `card-accent`).
- Zmapuj `surface-card` jako jeden z wariantow (np. overlay/compact).
- Zaktualizuj wszystkie karty w widokach do wspolnego wzorca.

### 2) Standaryzacja naglowkow
- Ustal standard `SectionHeading` jako domyslny dla sekcji.
- Dopusc 2-3 warianty (np. `lg`, `md`, `sm`) i stosuj je konsekwentnie.
- Usun reczne naglowki tam, gdzie to mozliwe.

### 3) Standaryzacja przyciskow
- Zastap reczne `<button>` w kluczowych widokach `Button`/`IconButton`.
- Dopusc reczne `<button>` tylko w miejscach, gdzie wymaga tego layout (np. customowe dropdowny).

### 4) Porzadek w tokenach CSS
- Zweryfikuj `globals.css` vs `web-next/README.md`.
- Dopisz brakujace tokeny albo zaktualizuj README.

## Priorytety
1) Karty/panele (najwiekszy rozjazd wizualny).
2) Naglowki sekcji.
3) Przyciski.
4) Tokeny/dokumentacja.

## Standard docelowy (web-next)
### Karty/panele (boxy)
- Dozwolone warianty (max 3):
  1) `card-shell card-base` (domyslny box)
  2) `card-shell card-accent` (wariant z gradientem/akcentem)
  3) `surface-card` (overlay/utility w panelach bocznych i drawerach)
- Zakaz: tworzenia nowych kombinacji boxow bez uzasadnienia w raporcie.

### Naglowki sekcji
- Dozwolone warianty: `SectionHeading` z `size=lg|md|sm`.
- Ręczne naglowki tylko w wyjatkowych layoutach (uzasadnienie w raporcie).

### Przyciski
- Dozwolone warianty: `Button`/`IconButton` z ustalonymi `variant` i `size`.
- Ręczne `<button>` tylko dla elementow sterowanych przez biblioteki zewnetrzne.

### Tokeny i README
- `web-next/README.md` musi odzwierciedlac realne tokeny i klasy w `globals.css`.
## Plan prac
1) Inwentaryzacja elementow UI: karty/panele, przyciski, naglowki, listy/empty states.
2) Mapa rozjazdow: gdzie jest manualne stylowanie vs gdzie sa komponenty UI.
3) Ustalenie standardu: ktore klasy/komponenty sa bazowe i kiedy je stosujemy.
4) Minimalny refaktor: ujednolicenie klas lub migracja do komponentow UI.
5) Aktualizacja dokumentacji (README lub inny plik) jesli zmiany tego wymagaja.

## Kryteria wyjscia
- Lista miejsc z niespojnymi stylami (karty/panele, przyciski, naglowki).
- Wskazane komponenty/klasy bazowe do standaryzacji.
- Zidentyfikowane braki w CSS (np. `surface-card`).

## Kryteria akceptacji
- Raport refaktoryzacji z opisem zmian i uzasadnieniem.
- Brak regresow w testach po zmianach.
- Ewentualne dostosowanie testow do nowej struktury komponentow.
- Aktualizacja dokumentacji projektu, jesli zmiany tego wymagaja.
- Zmiany w kodzie zostaly wprowadzone (nie tylko raport).

## Format raportu
Plik raportu: `docs/_done/078_standaryzacja_css_web_next_report.md`
- `Cel i zakres`
- `Najwazniejsze ryzyka`
- `Mapa niespojnosci` (karty/panele, przyciski, naglowki)
- `Rekomendacje standaryzacji`
- `Zmiany w kodzie` (lista plikow + uzasadnienie)
- `Wplyw na testy`
- `Zmiany w dokumentacji`

## Wskazowki dla wykonawcy
- W pierwszej kolejnosci sprawdz komponenty UI: `Button`, `IconButton`, `Panel`, `SectionHeading`, `ListCard`, `EmptyState`.
- Weryfikuj definicje tokenow w `web-next/app/globals.css` i zgodnosc z `web-next/README.md`.
- Utrzymaj obecny look-and-feel; nie rob redesignu.
- Nie tworz nadmiernej liczby nowych plikow lub klas bez realnego uzycia.

## Checklist dla wykonawcy
### Przygotowanie
- [ ] Przejrzyj `web-next/README.md` (sekcja tokenow i komponentow UI).
- [ ] Sprawdz `web-next/app/globals.css` (czy `surface-card` istnieje).
- [ ] Zidentyfikuj wszystkie uzycia `glass-panel`, `surface-card`, `rounded-3xl` w komponentach.

### Karty/panele
- [ ] Zdecyduj: `Panel`/`glass-panel` jako standard dla kart.
- [ ] Ujednolic klasy w `model-card.tsx`, `kpi-card.tsx`, `metric-card.tsx`, `roadmap-kpi-card.tsx`, `lag-card.tsx`.
- [ ] Zweryfikuj, czy `shadow-card` jest stosowany spójnie.

### `surface-card`
- [ ] Jesli `surface-card` ma zostac: dodaj definicje w `web-next/app/globals.css`.
- [ ] Jesli nie: zamien uzycia `surface-card` na `glass-panel`/`Panel`.
- [ ] Potwierdz zgodnosc z README po zmianach.

### Przyciski
- [ ] Zastap reczne `<button>` tam, gdzie mozna, komponentami `Button`/`IconButton`.
- [ ] Zweryfikuj stany `disabled/hover/focus` w nowych uzyciach.
- [ ] Utrzymaj obecne warianty CTA (primary/secondary/outline/ghost).

### Naglowki sekcji
- [ ] Ustandaryzuj naglowki przez `SectionHeading` lub wspolne klasy.
- [ ] Sprawdz spojnosc `tracking` i rozmiarow w widokach.

### Walidacja
- [ ] Uruchom `npm --prefix web-next run test:e2e` lub zaznacz brak mozliwosci uruchomienia.
- [ ] Zrob szybki smoke-check w: Cockpit, Brain, Strategy, Inspector.
- [ ] Zaktualizuj raport `docs/_done/078_standaryzacja_css_web_next_report.md`.

## Co nie jest celem
- Nie zmieniac brandingu ani kolorystyki.
- Nie przepisywac widokow na nowe komponenty bez uzasadnienia w raporcie.
- Nie zmieniac stosu technologicznego (Tailwind zostaje).
