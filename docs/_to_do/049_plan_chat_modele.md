# ZADANIE 049: Chat + modele językowe na ekranie głównym

## Cel
- Doprowadzić główny ekran Cockpitu w `web-next` do parytetu z legacy web: chat musi działać jak w starej wersji (sugestie, skrót klawiszowy, historyczny kontekst), a panel modeli powinien dawać szybki wgląd w zasoby + kontrolę modeli.
- Stworzyć plan wykonania kolejnych kroków i odnotować już zrealizowane poprawki (sugestie i `Ctrl+Enter`).

## Stan obecny
- Główna strona ma chat z `textarea`, ale brak szybkich sugestii promptów i skrótu klawiszowego z poprzedniego UI (rozwiązanie: dodano `suggestionChips` plus `Ctrl+Enter` do wysyłki).
- Panel modeli pokazuje listę modeli i przyciski do instalacji/aktywacji, ale nie ma panelu „Resource usage” z CPU/GPU/RAM/VRAM/Dysk ani metryk kosztu sesji z starej zakładki (`web/templates/index.html:243-315` i `web/static/js/app.js`).

## Wykonane kroki
1. Zaimplementowano zestaw promptów kopiujących się do pola chatu (`suggestionChips` w `web-next/app/page.tsx`) – analogiczne do panelu z chipami na starej stronie.
2. Dodano obsługę `Ctrl+Enter` (i `Cmd+Enter`) do wysyłania zadań, co wyrównuje UX z poprzednim interfejsem oraz przyspiesza manualne wysyłki.
3. Udokumentowano plan dalszych działań poniżej, żeby można było wykonać kolejne etapy w porządku.
4. Dodano panel „Zasoby modeli” z CPU/GPU/RAM/VRAM/Dysk + koszt sesji (dane z `/api/v1/models/usage` i `/api/v1/metrics/tokens`), dzięki czemu operator widzi zużycie zasobów podobnie jak w legacy kokpicie.
5. Dodano przycisk „PANIC: Zwolnij zasoby”, który wywołuje `/api/v1/models/unload-all`, odświeża dane modeli/zadań/kolejki i informuje operatora o wyniku.
6. W panelu modeli pojawiła się dodatkowa sekcja historyczna z listą modeli, ich źródłem, rozmiarem, statusem i kwantyzacją – analogicznie do starego kokpitu.
7. Ulepszono `useModelsUsage`, by obsługiwał zarówno odpowiedź opakowaną w `usage`, jak i surowe metryki, dzięki czemu zasoby pokazują realne dane zamiast samych kresek.
8. Uproszczono nawigację boczną (czyste linki `<a>` bez dodatkowej logiki) i dodano brakujące akcenty kart statystyk, dzięki czemu kliknięcia w moduły zawsze prowadzą do właściwej podstrony i build przechodzi bez błędów typów.

## Kolejne kroki – walidacja
- Sprawdź, czy panel „Modele” i „Zasoby modeli” dostają dane z backendu `/api/v1/models` i `/api/v1/models/usage`, a liczba modeli pokrywa się z legacy API na porcie 8000.
- Zweryfikuj działanie przycisku „PANIC: Zwolnij zasoby” (wywołuje `/api/v1/models/unload-all`) i towarzyszące odświeżenie danych oraz informację zwrotną dla operatora.
- Jeśli to możliwe, dodaj ręczny test lub notatkę w Playwright/SUITE, która potwierdzi obecność historii modeli i działanie skrótu `Ctrl+Enter`.

## Walidacja
- Sprawdzić manualnie, że `Ctrl+Enter` wysyła zadanie oraz że kliknięcie chipów zastępuje treść promptu. Jeśli backend jest dostępny, zweryfikować, że nowe prompt jest wysyłany w historii.
- Przygotować test Playwright (lub notatkę) sprawdzającą widoczność prompt chips w interfejsie i działanie skrótu klawiszowego (można dorzucić do obecnego smoke suite).

## Rezultat
- Sugestie promptów i skrót klawiszowy są już dostępne na stronie głównej (`web-next/app/page.tsx`).
- Resztę planu wykonujemy w kolejnych etapach przez dodanie panelu zasobów modeli i ewentualnej integracji z `QuickActions/Cost Mode`.
