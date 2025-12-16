# ZADANIE 048: Porównanie ekranów Brain / Inspector / Strategy (web → web-next)

## Brain / Knowledge Graph
- ✅ **Panel sterowania + status**: dodano overlay z liczbą węzłów/krawędzi, spinnerem i komunikatem o stanie grafu; obsługujemy błąd ładowania Cytoscape.
- ✅ **Filtry wielozaznaczalne**: wprowadzono checkboxy typów węzłów (Agents/Files/Memories/Functions/Classes) z logiką filtrowania równoczesnego.
- ✅ **Podświetlenia + szczegóły węzła**: kliknięcie węzła przygasza inne elementy, panel boczny prezentuje typ, relacje, metadane – bez konieczności używania arkusza JSON.
- ✅ **Loading + error toast**: dodano dedykowany overlay oraz toast błędu dla grafu – zgodnie z oryginałem.
- ✅ **Historia operacji / log**: sekcja „Ostatnie operacje grafu” bazująca na Lessons/scan logach odwzorowuje feed z legacy (ostatnie wpisy, daty, tagi).

## Inspector / Trace Intelligence
- ✅ **Źródło danych diagramu**: front korzysta teraz z `/api/v1/flow/{id}` (tak jak legacy) i renderuje gotowy Mermaid sequence diagram z dedykowanym theme/fallback. Do dopracowania pozostają akcenty decision gates i dodatkowe markery.
- 🔁 **Manualne odświeżanie i panel JSON**: brakujące elementy (przycisk „Odśwież” ze spinnerem oraz blok `pre` z pełnym JSON-em kroku) zostały przeniesione do `docs/_to_do/051_backlog_niedobitki.md` (zadanie 051) jako follow-up.

## Strategy / War Room
- ✅ **Potwierdzenie akcji „Kampania”**: `handleStartCampaign` pyta teraz o potwierdzenie tak jak legacy.
- ✅ **Toast/alerty dla akcji**: wpięto globalne powiadomienia dla akcji Roadmapy/Kampanii/Statusu – feedback identyczny jak w legacy.
- ✅ **Szybki widok milestone/task summary**: akordeony pokazują teraz status emoji i completed/total (dane z `/api/v1/roadmap`).
- 🔁 **Widok KPI / timeline**: wypełnienie sekcji danymi z `/api/v1/tasks` / `/api/v1/history` jest śledzone w `docs/_to_do/051_backlog_niedobitki.md` (zadanie 051).

## Uwagi końcowe
- Można rozszerzyć dokumentację (np. nowy checkpoint w `docs/_to_do`) o follow-up, gdy powyższe moduły zostaną odświeżone i przetestowane (np. przywrócenie spinnerów, testy Playwright, walidacja `buildMermaid`).

## Wykonane kroki
- Dodano potwierdzenie „Uruchom Kampanię” w `web-next/app/strategy/page.tsx`, które pyta o zgodę (`confirm`) przed wysłaniem żądania do `/api/campaign/start`, żeby odwzorować modal z legacy interfejsu i uniknąć przypadkowych akcji.
- Zaimplementowano w widoku Brain overlay ładowania/błędu, podgląd zaznaczonego węzła z relacjami oraz wielokrotne filtry typów + podświetlanie sąsiadów, co odtwarza UX starego grafu (spinner, status, highlight).
- Inspector ma teraz ręczne odświeżanie historii, bogatszy Mermaid (statusy, notatki decyzji), overlay ładowania i panel JSON dla zaznaczonego kroku – odpowiada to dawnemu „generateMermaidDiagram” i panelowi detali.
- Diagram Mermaid w Inspectorze jest znów generowany po stronie web-next z sanitacją danych (sequenceDiagram z Decision Gate), więc requesty takie jak `2850d089-...` renderują się identycznie jak w starym panelu i nie blokują się na błędnych danych z API.
- Widok „Diagnoza przepływu” dopasowuje teraz rozmiar diagramu do szerokości panelu (auto-fit + zachowanie proporcji), więc sekwencja nie jest ani miniaturowa, ani rozciągnięta w pionie – pełne okno jest wykorzystane tak jak w legacy inspectorze.
- Na stronie Strategy pojawił się toast statusowy dla akcji (create/start/report) oraz w akordeonie milestone’ów wyświetla się szybkie podsumowanie zadań (emoji + completed/total), co przywraca feedback i „milestone summary” z legacy UI.
