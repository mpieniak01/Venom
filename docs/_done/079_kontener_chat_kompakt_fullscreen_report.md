# 79: Kontener chat (kompakt + fullscreen) — raport realizacji

## Cel i zakres
- Ustabilizowac kontener czatu (kompakt + fullscreen).
- Przeniesc przewijanie do historii czatu, a nie calej strony.
- Zachowac input i kontrolki jako statyczny blok.

## Etap 1: Mapowanie warstw i overflow
- Zidentyfikowano hierarchie: panel czatu (glass-panel) -> box historii (box-muted) -> lista (scroll) -> blok inputu.
- Zidentyfikowano problem: input i kontrolki nie byly izolowane w bloku `shrink-0`, a scroll dotyczył calego panelu.

## Etap 2: Ustalenie layoutu kontenera
- Panel czatu utrzymany jako `flex-col` z `min-h-0` i `overflow-hidden`.
- Box historii otrzymal `overflow-hidden` i `min-h-0`, aby poprawnie ograniczac scroll.
- Lista historii ma `flex-1` i `overflow-y-auto`.
- Input + kontrolki opakowane w blok `shrink-0` dla stabilnosci.

## Etap 3: Wewnetrzne przewijanie historii
- Scroll przeniesiony na liste historii (tylko wewnetrzny scroll).
- Dodano `scrollbar-gutter: stable` na historii, aby przewijanie bylo widoczne i stabilne.

## Etap 4: Spójnosc kompakt/fullscreen
- Ten sam kontener i struktura w obu trybach.
- Ten sam zestaw kontrolek i przyciskow w dolnym bloku.

## Zmiany w kodzie
- `web-next/components/cockpit/cockpit-home.tsx`
  - Historia czatu: klasa `chat-history-scroll` + `overflow-y-auto`.
  - Box historii: `overflow-hidden`, `min-h-0`.
  - Dolny blok inputu opakowany w `shrink-0`.
  - Panel czatu: `min-h-0`, `overflow-hidden`, `max-h` ograniczajacy wysokosc.
- `web-next/app/globals.css`
  - Dodana klasa `.chat-history-scroll` z `scrollbar-gutter: stable both-edges`.

## Wplyw na testy
- Nie uruchamiano testow.

## Zmiany w dokumentacji
- Brak zmian wymaganych.
