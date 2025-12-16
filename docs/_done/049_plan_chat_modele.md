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
9. Zweryfikowano, że panel „Modele” oraz „Zasoby modeli” zaciągają dane z `/api/v1/models` i `/api/v1/models/usage` – wskaźnik liczby modeli aktualizuje się po instalacji/odświeżeniu, a metryki CPU/GPU/RAM/VRAM/Dysk reagują wraz z odświeżaniem hooka (manualne sprawdzenie podczas pracy UI).
10. Przećwiczono przycisk „PANIC: Zwolnij zasoby” (`/api/v1/models/unload-all`) – po wywołaniu panel natychmiast pokazuje komunikat, a `refreshModels()`, `refreshModelsUsage()` oraz odświeżenie kolejki/zadań czyszczą listę modeli (potwierdzone ręcznie, bez testów automatycznych na ten moment).
11. Command Console łączy teraz historię requestów z wynikami `/api/v1/tasks`, więc w kolumnie czatu widać klasyczny układ pytanie → odpowiedź (prompt, wynik, status i czas), a panel szczegółów pokazuje również logi zadania oraz wynik końcowy.
12. Zestaw gotowych promptów został przepisany na karty z ikonami i opisami 1:1 ze starego UI – kliknięcie natychmiast podmienia treść w czacie i działa w Lab/Prod razem z `Ctrl+Enter`.
13. Panel szczegółów historii dociąga teraz dane pojedynczego zadania przez `/api/v1/tasks/{id}` (pełne logi + wynik), a dodatkowy efekt nasłuchuje na aktualizacje `useTasks`, dzięki czemu logi pojawiają się bez ręcznego odświeżania.
14. Obsłużono scenariusz, w którym backend chwilowo zwraca błąd historii – panel pokazuje czytelny komunikat, a dane zadania są pobierane niezależnie (fallback do `/api/v1/tasks/{id}`), więc logi są widoczne nawet jeśli timeline jeszcze się nie wygenerował. Dodatkowo textarea czatu czyści się od razu po wysyłce i przy błędzie przywraca poprzednią treść.

## Kolejne kroki – walidacja
- ✅ Panel „Modele” i „Zasoby modeli” potwierdzony w integracji z `/api/v1/models` i `/api/v1/models/usage` (sprawdzone ręcznie na porcie 3000 vs. legacy).
- ✅ Przyciski instalacji/odświeżenia i „PANIC: Zwolnij zasoby” (POST `/api/v1/models/unload-all`) przetestowane manualnie – natychmiast aktualizują listę modeli oraz metryki.
- ✅ Command Console: ręcznie potwierdzono, że historia, wynik zadania i logi są spięte (klik w bańkę otwiera realne dane requestu wraz z logami z `/api/v1/tasks`).
- 🔁 Testy Playwright (historia modeli, `Ctrl+Enter`) przeniesiono do `docs/_to_do/051_backlog_niedobitki.md` i zostaną dodane po stabilizacji UI.

## Walidacja
- ✅ Ręcznie zweryfikowano, że `Ctrl+Enter` wysyła zadanie oraz że chipy promptów podmieniają treść textarea; nowe zadania trafiają do historii.
- ✅ Ręczna walidacja Q&A: wysyłka zadania z legacy promptu, sprawdzenie, że w kolumnie czatu pojawia się para wiadomości oraz że panel szczegółów zawiera wynik + logi zadania.
- ✅ Sprawdzenie requestów dłużej wykonywanych – po kliknięciu w „Szczegóły” logi i wynik dociągają się po zakończeniu zadania, bo panel pobiera je bezpośrednio z `/api/v1/tasks/{id}`.
- 🔁 Automatyczne testy Playwright (chips + skrót) – włączone do zadania 051.

## Rezultat
- Sugestie promptów, skrót klawiszowy oraz klasyczny widok „pytanie-odpowiedź” (łącznie z logami zadania) są już dostępne na stronie głównej (`web-next/app/page.tsx`).
- Resztę planu wykonujemy w kolejnych etapach przez dodanie panelu zasobów modeli i ewentualnej integracji z `QuickActions/Cost Mode`.

## Następny krok – mapowanie czatu i promptów (legacy → web-next)
1. **Audyt legacy – zrealizowany**
   - Kategorie promptów (Kreacja, DevOps, Status projektu, Research, Kod, Pomoc) odwzorowane z `web/templates/index.html`, łącznie z ikonami i opisami.
2. **Implementacja presetów – zrealizowana**
   - `web-next/app/page.tsx` posiada strukturę kart presetów; kliknięcie wstawia treść do czatu i można ją wysłać skrótem lub przyciskiem.
   - Command Console pokazuje wynik zadania i logi, aby rozmowa wyglądała jak klasyczny chat.
3. **Walidacja UX**
   - ✅ Ręczne testy potwierdzające działanie w trybie Lab/Prod.
   - 🔁 Automatyczny test Playwright (widoczność presetów + `Ctrl+Enter`) śledzony w zadaniu 051.
