# ZADANIE 047: Funkcjonalności do przeniesienia

## Cel
- Zarejestrować brakujące elementy starego kokpitu (web) i określić, co jeszcze trzeba odwzorować w `web-next`, aby nie utracić istotnych akcji ani widżetów.
- Ułożyć kolejność przeniesienia, zaczynając od funkcji krytycznych operacyjnie i tych, które otwierają pole do dalszych integracji.

## Funkcjonalności do przeniesienia
1. **Voice Command Center / IoT + audio WS**
   - Pełna zakładka „Głos” z przyciskiem push-to-talk, wskaźnikiem statusu audio, wizualizatorem i panelami transkrypcji/odpowiedzi nie istnieje jeszcze w Next (`web/templates/index.html:102-200`, `web/static/js/app.js:1985-2080`). To krytyczna część kokpitu, jeżeli operator nadal powinien korzystać z głosu i Rider-Pi/IoT.
2. **Integracje + Active Operations**
   - Stary dashboard renderował matrycę `/api/v1/system/services`, panel ostrzeżeń oraz listę aktywnych operacji/skillów z `/ws/events`. Nowa strona ma tylko prostą sekcję Agenci bez tabelki integracji, więc trzeba przenieść logikę fetchowania i renderu (z `web/static/js/app.js:2749-2950`) tam, gdzie ma sens (np. osobny panel/zakładka).
3. **Lekcje / graf wiedzy i Cost Mode modal**
   - Zakładka „Pamięć” zawierała listę lekcji, przycisk skanu grafu, statusy i modal potwierdzający włączenie trybu kosztowego (`web/templates/index.html:224-499`). Do tego dochodzi obsługa `useCostMode/setCostMode` i `useAutonomyLevel/setAutonomy`. Obecny Next nie ma tej przestrzeni, trzeba ją zmapować na nową sekcję i replikować modal.
4. **Detale kolejki (session cost, pause/resume, emergency stop)**
   - Panel `queue-governance` w web pokazywał liczniki aktywnych/pending/config limit, koszt sesji i wielkie przyciski pauzy/purge/emergency (`web/templates/index.html:345-389`). Next ma Quick Actions, ale nie ma kosztów sesji oraz awaryjnego stopu wprost na stronie głównej; warto odtworzyć metryki i akcje (np. badge) licząc `/api/v1/queue`.
5. **Modele – zużycie CPU/GPU/RAM/VRAM/Dysk**
   - W starej zakładce „Zbrojownia” były metryki zasobów (CPU/GPU/RAM/VRAM/Dysk) plus postęp pobierania, panic button i lista modeli (`web/templates/index.html:243-315`). Next ogranicza się do instalki i listy – trzeba dodać karty zasobów i postęp, żeby zachować kontrolę nad uruchomionymi modelami.
6. **Historia + szczegóły requestów (modal)**
   - W `web/static/js/app.js` historia była tablicą i modalem z JSON-em, a w Next mamy nowy `Sheet`, ale jeszcze trzeba przenieść logikę kopii JSON/kroków i potwierdzenia, żeby zachować ten UX (lokacje: `web/templates/index.html:318-339`, `web/static/js/app.js:1100-1200`, `web-next/app/page.tsx:1076-1180`).
7. **Terminal na żywo + integracje logów**
   - Terminal z `/ws/events`, filtr, przyciski czyszczenia i przypinania logów oraz pinned section (`web/templates/index.html:88-140`, `web/static/js/app.js:2420-2680`) jest już częściowo w Next, ale trzeba dopracować integracje (np. powiadomienia, pinned JSON export) i pokryć brakujące stany offline.
8. **Historyczne sugestie promptów / buttony chipów**
   - Stary ekran prezentował panel z chipami sugestii (kreacja/DevOps/Research itd.) w chat input (`web/templates/index.html:396-420`). W Next można je odtworzyć jako `QuickActions` lub `SuggestionPanel`, żeby nie stracić szybkich promptów i wstępnych treści dla operatora.
9. **Modal potwierdzenia dla Cost Mode + autopompa**
   - Stary „Cost Mode Confirmation Modal” (`web/templates/index.html:480-499`) powinien mieć odpowiednik (np. w Sidebarze lub sheetach), bo wymaga potwierdzenia przejścia w tryb płatny; obecnie nie ma tej kontroli w Next.

## Kolejność prac (tymczasowa propozycja)
1. Przenieść brakujące karty i akcje kolejki (sesja + emergency) oraz pełną historię requestów (JSON + kroki).
2. Dodać sekcję wizji głosowej i Log/Integrations matrix, żeby zachować więcej real-time danych.
3. Wdrożyć lekcje/graf/cost mode + resource metrics modeli i sugestie promptów.
4. Dopasować Quick Actions do zadań offline (wyświetlanie fallbacków) i wzbogacić o brakujące chipy promptów.

## Uwagi
- Można rozważyć dedykowaną zakładkę (np. `/inspector` lub `/inspector/logs`) dla Voice/Integracje, jeśli nie pasują na główny dashboard.
- Przenoszenie ich krok po kroku ułatwi testowanie (np. Playwright smoke z history sheet, queue actions, voice modal).
- Zachować dane telemetryczne (PDF) i copy JSON do schowka – albo z `navigator.clipboard` albo fallback `textarea`.

## Wykonane kroki
- Dodano panel „Queue governance” na stronie głównej (`web-next/app/page.tsx`), który pokazuje metryki `/api/v1/queue/status` (active/pending/limit) oraz przyciski „Wstrzymaj/Wznów kolejkę”, „Wyczyść kolejkę” i „Emergency stop” wraz z komunikatami o wyniku, co odwzorowuje panelek z legacy web.
