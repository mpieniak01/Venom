# Raport standaryzacji stylow w web-next - Zadanie 078

## Cel i zakres
- Standaryzacja bazowych stylow kart/paneli i CTA w `web-next`.
- Uzgodnienie implementacji `surface-card` z deklaracja w `web-next/README.md`.
- Zakres: `web-next/app/globals.css`, wybrane komponenty kart oraz kluczowe elementy layoutu.

## Najwazniejsze ryzyka
- Zmiana bazowego tła kart mogla delikatnie zmienic kontrast w niektorych widokach.
- Standaryzacja powinna unikac naruszenia obecnego look-and-feel (brak redesignu).

## Znaleziska i decyzje
- `surface-card` bylo uzywane, ale brakowalo definicji w CSS mimo opisu w README.
- W wielu komponentach kart uzywano powtarzalnego zestawu klas Tailwind.
- Wprowadzono wspolne klasy bazowe kart i zastosowano je w najczesciej powtarzanych komponentach.

## Zmiany w kodzie
### Dodane klasy (globals.css)
- `--surface-muted` oraz `.surface-card`
- `.card-shell` (ramka, cien, kolor tekstu)
- `.card-base` (bazowe tlo karty)

### Zmienione komponenty kart i layoutu
- `web-next/components/cockpit/model-card.tsx`
- `web-next/components/cockpit/kpi-card.tsx`
- `web-next/components/cockpit/macro-card.tsx`
- `web-next/components/cockpit/cockpit-home.tsx` (karta serwerow LLM)
- `web-next/components/brain/metric-card.tsx`
- `web-next/components/inspector/lag-card.tsx`
- `web-next/components/strategy/roadmap-kpi-card.tsx`
- `web-next/components/queue/queue-status-card.tsx`
- `web-next/components/layout/mobile-nav.tsx`
- `web-next/components/layout/top-bar.tsx`
- `web-next/components/layout/overlay-fallback.tsx`
- `web-next/components/layout/command-palette.tsx`
- `web-next/components/voice/voice-command-center.tsx`
- `web-next/components/tasks/task-status-breakdown.tsx`
- `web-next/components/tasks/recent-request-list.tsx`
- `web-next/components/brain/brain-home.tsx`
- `web-next/app/inspector/page.tsx` (tryb pelnej szerokosci dla diagnozy przeplywu)

## Wplyw na testy
- Brak zmian funkcjonalnych, oczekiwany brak regresji.
- Rekomendowane: `npm --prefix web-next run test:e2e`.

## Zmiany w dokumentacji
- `web-next/README.md` uzupelnione o `card-shell`/`card-base`.

## Podsumowanie
- Ujednolicono bazowy wzorzec kart i wiodace boxy w kluczowych widokach.
- Uzupełniono brakujaca definicje `surface-card` zgodnie z dokumentacja.
- CTA w top-bar i mobile-nav korzystaja z `Button`/wspolnych klas.
- Zachowano dotychczasowy styl UI bez redesignu.
