# 110 - Stabilizacja testów perf (SSE + API)

## Cel
Zatrzymac wieszanie sie testow perf i ograniczyc niekontrolowane zuzycie GPU/CPU przy uruchamianiu grup pytest.

## Problem
- Testy perf uruchamiane domyslnie w grupie "heavy" potrafia mielic GPU/CPU i wisiec.
- SSE bez twardego timeoutu potrafi blokowac bieg testow, nawet gdy backend odpowiada.
- API base jest domyslnie ustawiony na port 8000, co nie zawsze jest aktualne.

## Plan
1. Wprowadzic globalny guard dla testow perf (VENOM_RUN_PERF=1).
2. Dodac twarde timeouty dla SSE (read + overall).
3. Ustandaryzowac sposob ustawiania API base (VENOM_API_BASE lub APP_PORT).
4. Dokumentacja: jak uruchamiac perf swiadomie.

## Analiza (2026-02-05)
- W heavy grupa testow perf wiesza sie mimo backendu aktywnego.
- Przyczyna: SSE bez twardych timeoutow oraz brak auto-detekcji backendu powoduje dlugie blokady.
- Dodatkowo API base domyslnie wskazuje na 8000; jesli API jest gdzie indziej, testy nie potrafia tego wykryc.

## Zrealizowane
- Dodano twarde timeouty w SSE (read + overall).
- Domyslne ustawienia perf: `VENOM_FORCE_INTENT=HELP_REQUEST`, niskie concurrency i krotkie timeouty.
- Auto-detekcja backendu: testy perf sa skipowane, jesli `/healthz` nie odpowiada.
- Uelastyczniono API base: `VENOM_API_BASE`, `API_PROXY_TARGET`, `NEXT_PUBLIC_API_BASE`, `API_BASE_URL` lub `APP_PORT`.
- make pytest przekazuje `VENOM_API_BASE` z Makefile (`HOST_DISPLAY:PORT`).
- W run-pytest-optimal dodano `-rs`, aby widziec etykiety (powody skipow).

## Do sprawdzenia
- Uruchomic heavy testy pojedynczo i wskazac, ktory nadal wiesza.
- Sprawdzic, czy API base jest poprawny w srodowisku bez weba na 8000.
 - Zweryfikowac, czy backend jest widoczny z miejsca uruchamiania pytest (healthz).

## Akceptacja
- make pytest nie uruchamia kosztownych testow perf bez swiadomej zgody.
- testy perf nie wisza na SSE; timeout jest czytelny.
- ustawienie API base nie wymaga zmiany kodu testow.
