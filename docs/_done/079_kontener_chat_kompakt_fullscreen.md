# 79: Kontener chat (kompakt + fullscreen)

## Cel
- Zbudowac stabilny kontener czatu w wersji kompaktowej i fullscreen.
- Zapewnic przewijanie tylko historii czatu, bez "plywania" inputu i kontrolek.
- Utrzymac obecna stylistyke i UX, ale naprawic uklady i overflow.
- Zapewnic poprawne dzialanie ocen (status + blokada ponownego klikniecia).

## Zakres
- Frontend: `web-next` (cockpit chat).
- Pliki docelowe: `web-next/components/cockpit/cockpit-home.tsx` + ewentualnie wspierajace style w `web-next/app/globals.css`.

## Wstepna analiza
- Kontener czatu ma warstwy: naglowek panelu, lista historii, kontener inputu, przyciski i selektory.
- System ocen ma dzialac jak obecnie
- Mozliwe jek klikniecie na szczegoly wygenerowanej odpowidzi i otworzy sie kontener jak obecnie.
- Problem: historia nie przewija sie wewnatrz panelu, input i przyciski "plywaja" poza kontenerem.
- Problem: brak stabilnych wysokosci i `min-h-0` w flexie powoduje zly overflow.
- Problem: przewijanie dotyczy calej strony zamiast listy historii.

## Plan prac (wieloetapowy)
1) Zmapowac obecne warstwy i overflow (naglowek panelu, lista historii, kontener inputu, kontrolki).
2) Zdefiniowac layout: kontener panelu (flex column), wewnetrzny box historii (flex-1 + min-h-0 + overflow), dolny kontener inputu (shrink-0).
3) Wprowadzic stabilne granice: `overflow-hidden` na panelu i boxie historii, scrollbar tylko w historii.
4) Ujednolicic wersje kompaktowa i fullscreen: te same elementy i funkcje (input + selektory + przyciski + status).
5) Zweryfikowac focus i interakcje (wpisywanie, przewijanie, ocena).
6) Sprawdzic visualy pod katem zgodnosci z obecna stylistyka.

## Kryteria wyjscia
- Chat ma przewijana historie wewnatrz panelu.
- Input i przyciski sa stale, nie "plywaja".
- Fullscreen i kompakt maja te same funkcje i kontrolki.
- Brak regresji w UX (pisanie, przewijanie, oceny).

## Kryteria akceptacji
- Poprawny raport refaktoryzacji z opisem zmian i uzasadnieniem.
- Brak regresji w testach po zmianach.
- Ewentualne dostosowanie testow do nowej struktury layoutu.
- Aktualizacja dokumentacji (funkcjonalnej/architektury), jesli wymagane.
- Zmiany w kodzie zostaly wykonane (nie tylko raport).

## Format raportu
Plik: `docs/_done/079_kontener_chat_kompakt_fullscreen_report.md`
- `Cel i zakres`
- `Kluczowe decyzje layoutu`
- `Zmiany w kontenerach (przed/po)`
- `Zmiany w overflow/scroll`
- `Zmiany w UX (input, kontrolki, oceny)`
- `Wplyw na testy`
- `Zmiany w dokumentacji` (jesli dotyczy)

## Wskazowki dla wykonawcy
- Uzyj `min-h-0` i `overflow-hidden` w kontenerach flex, aby przewijanie dzialalo tylko w historii.
- Input + kontrolki zawsze w osobnym `shrink-0` kontenerze.
- Zapewnij jednakowe elementy w fullscreen i kompakt (brak brakujacych przyciskow).
- Nie zmieniaj estetyki - tylko porzadkowanie i stabilizacja layoutu.

## Co nie jest celem
- Zmiana wygladu UI (kolory, fonty, glow).
- Przenoszenie czatu do nowego layoutu poza cockpit.
- Przepisywanie na nowy framework.
