# ADR-003 — Chat 2.0 jako osobna powłoka w obecnej aplikacji

> Decyzja o wdrożeniu została częściowo zastąpiona przez [ADR-004](ADR-004-studio-runtime-composition.md) 2026-10-31: Studio ma też osobną kompozycję web/API. Poniższe wspólne kontrakty rozmowy, materiałów, głosu i kwalifikacji nadal obowiązują.

Data: 2026-10-30. Status: decyzja implementacyjna; odbiór funkcjonalny i wizualny w B07.
Baza: grupa A, main e01e7b08, PR 571/570/572. Pełny kontrakt: [ADR EN](../../adr/ADR-003-chat-2-shell.md).

## Decyzja

- Wspólny Next.js i FastAPI, istniejące sesje, historia i adaptery. Nowa trasa `/chat2` włączana przez `NEXT_PUBLIC_FEATURE_CHAT2=true`; powrót do `/chat`. To wybór powłoki, niezależny od theme, profilu Full/Light, środowiska i bundlera.
- Root layout zawiera tylko infrastrukturę wspólną. Osobna grupa tras istniejącej aplikacji posiada sidebar, top bar, status bar i zależne providery. Chat 2.0 nie montuje ich ani telemetrii kokpitu. Dotychczasowe adresy nie zmieniają się.
- Wariant bazowy Studio: wąski pasek nawigacji, kontekstowy wybór rozmowy, centralny wątek/composer i materiały obok. Mobile otwiera panele na żądanie. Nie kopiujemy innych ekranów ani menu.
- Jeden wspólny kontroler rozmowy obu ekranów: historia, wysłanie, stream, Stop, tożsamość, błędy i szkic zapisany per sesja. Jeden właściciel rozmowy po nawigacji, bez Git/grafu/metryk/logów w kontrolerze.
- Katalog/runtime określa model i dostępne tryby. Nieznane możliwości/ceny pozostają nieznane. Wybór modelu nie uruchamia generacji, droższego fallbacku ani drugiego silnika i nie usuwa szkicu/materiałów.
- Dokumenty UTF-8 TXT/MD/CSV/JSON mają trwały identyfikator sesji i ograniczony tekst dodawany przed wyceną. Obrazy tylko dla potwierdzonej lokalnej Ollamy z vision i sprawdzonym adapterem. Zdalne obrazy bez rozliczenia, PDF, natywne audio i wideo są jawnie niedostępne do wdrożenia ich adapterów.
- Dyktowanie tworzy szkic wymagający wysłania. Jawnie rozpoczęta rozmowa głosowa używa tego samego kontrolera i istniejącego STT/TTS. Osobne Stop odpowiedzi, wyciszenie i koniec głosu. Nawigacja/sesja usuwa stare wyniki i zwalnia zasoby; samo wejście nie uruchamia mikrofonu.
- PL/EN/DE, klawiatura, focus, puste/ładowanie/błąd/stream/Stop/reconnect, długie wiadomości i mobile należą do odbioru. B07 porównuje ten sam Turbo i warunki; pamięć procesu nie jest stertą JS.

## Zakres i wycofanie

Automatyczne testy korzystają z atrap. Test Zero dostawcy, prawdziwy mikrofon i robot wymagają osobnego zlecenia. Zachowujemy Full/dev/Turbo i jakość głosu. Rider 503 pozostaje do osobnej naprawy na decyzję operatora.

Wyłączenie nowego wejścia przywraca dotychczasową aplikację bez kasowania historii, materiałów i wyboru modelu. Inne ekrany nie są migrowane ani projektowane w ramach grupy B.
