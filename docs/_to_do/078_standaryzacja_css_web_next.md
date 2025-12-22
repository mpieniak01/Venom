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
