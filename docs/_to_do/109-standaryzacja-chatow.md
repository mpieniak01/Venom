# 109 - Standaryzacja chatow i chronologii

## Cel
Ujednolicic format wszystkich widokow chatu i zapewnic stabilna, chronologiczna kolejnosc: najstarsze u gory, najnowsze na dole, para pytanie -> odpowiedz w kolejnosci czasowej.

## Problem
- Kolejnosc wiadomosci skacze; nowe wiadomosci czasem pojawiaja sie na gorze.
- Timestamps dla starych wiadomosci sa nadpisywane podczas streamingu / update'ow, co burzy sortowanie.
- Rozne chaty (Cockpit + inne widoki) moga miec inne reguly sortowania / zrodel czasu.

## Zakres
- Frontend (web-next) - unifikacja sortowania i timestampow.
- Backend (venom_core) - weryfikacja, czy API nie nadpisuje timestampow dla historii.
- Dokumentacja - opis jednolitego formatu wpisu chatu.

## Wymagania funkcjonalne
- Chronologiczna lista: najstarsze u gory, najnowsze na dole.
- Wpisy w parach: user -> assistant dla tego samego request_id.
- Timestamp wiadomosci (created_at) nie moze byc zmieniany po utworzeniu.
- Dopuszczalne jest osobne pole updated_at dla streamingu.

## Sugerowane kroki
1. Wydzielic standardowy model wpisu chatu (created_at, updated_at, request_id, role, content, status).
2. W frontendzie:
   - nie nadpisywac created_at przy update'ach strumienia.
   - sortowac po created_at, a nie po updated_at.
3. W backendzie:
   - zwracac created_at i updated_at jawnie.
   - upewnic sie, ze history API nie aktualizuje created_at przy zapisie.
4. Dodac testy sortowania dla wszystkich widokow chatu.

## Akceptacja
- Zadna wiadomosc nie przeskakuje na gore przy update'ach.
- Wszystkie widoki chatu maja identyczne zachowanie kolejnosci.
- Kolejnosc jest stabilna po odswiezeniu strony.
