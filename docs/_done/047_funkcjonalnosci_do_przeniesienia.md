# ZADANIE 047: Funkcjonalności do przeniesienia

## Cel
- Zarejestrować brakujące elementy starego kokpitu (web) i określić, co jeszcze trzeba odwzorować w `web-next`, aby nie utracić istotnych akcji ani widżetów.
- Ułożyć kolejność przeniesienia, zaczynając od funkcji krytycznych operacyjnie i tych, które otwierają pole do dalszych integracji.

## Funkcjonalności do przeniesienia
1. **Voice Command Center / IoT + audio WS** – ✅ zaimplementowano moduł głosowy (`VoiceCommandCenter` z push-to-talk, wizualizatorem i Rider-Pi) w `web-next/app/page.tsx`.
2. **Integracje + Active Operations** – ✅ panel `IntegrationMatrix` prezentuje `/api/v1/system/services` i aktywne eventy.
3. **Lekcje / graf wiedzy i Cost Mode modal** – ✅ sekcja lekcji i grafu przeniesiona, Cost Mode potwierdzany w sidebarze (Eco ↔ Paid).
4. **Detale kolejki (session cost, pause/resume, emergency stop)** – ✅ panel `Queue governance` + QuickActions odtwarzają pełną logikę.
5. **Modele – zużycie CPU/GPU/RAM/VRAM/Dysk** – ✅ karty zasobów modeli i PANIC button dostępne na Cockpicie.
6. **Historia + szczegóły requestów (modal)** – ✅ nowy `Sheet` zawiera JSON, logi i kroki; dodatkowe usprawnienia opisane w zadaniu 049.
7. **Terminal na żywo + integracje logów** – ✅ terminal z pinowaniem/eksportem działa w Next; dalsze drobne usprawnienia (pinned export, offline) śledzimy w zadaniu 051.
8. **Historyczne sugestie promptów / buttony chipów** – ✅ presetowe karty promptów działają w Cockpicie.
9. **Modal potwierdzenia dla Cost Mode + autopompa** – ✅ potwierdzenia i AutonomyGate przeniesione do Sidebara / dedykowanych sheetów.

## Kolejność prac
Wszystkie funkcjonalności z powyższej listy zostały odwzorowane w `web-next`. Dalsze usprawnienia/QA są śledzone w `docs/_to_do/051_backlog_niedobitki.md`.

## Uwagi
Szczegółowe follow-upy (QA, integracje offline) dokumentujemy w zadaniu 051.

## Wykonane kroki
- Dodano panel „Queue governance” na stronie głównej (`web-next/app/page.tsx`), który pokazuje metryki `/api/v1/queue/status` (active/pending/limit) oraz przyciski „Wstrzymaj/Wznów kolejkę”, „Wyczyść kolejkę” i „Emergency stop” wraz z komunikatami o wyniku, co odwzorowuje panelek z legacy web.
- W sidebarze pojawiło się potwierdzenie przełączenia trybu kosztowego (Eco ↔ Paid), dzięki czemu operator musi świadomie zaakceptować tryb płatnych modeli tak jak w starym kokpicie (`web-next/components/layout/sidebar.tsx`).
- Strona główna zawiera „Voice Command Center” z obsługą `/ws/audio`, wizualizatorem, transkrypcją i sekcją Rider-Pi (panel `VoiceCommandCenter`), co przenosi funkcję tablicy głosowej ze starego kokpitu.
- Dodano panel „Integracje i operacje” (`IntegrationMatrix`), który grupuje `/api/v1/system/services` oraz ostatnie eventy `/ws/events`, odtwarzając legacy matrix integracji i listę aktywnych sygnałów.
