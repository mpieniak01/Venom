# ZADANIE 048: Porównanie ekranów Brain / Inspector / Strategy (web → web-next)

## Brain / Knowledge Graph
- ✅ **Panel sterowania + status**: dodano overlay z liczbą węzłów/krawędzi, spinnerem i komunikatem o stanie grafu; obsługujemy błąd ładowania Cytoscape.
- ✅ **Filtry wielozaznaczalne**: wprowadzono checkboxy typów węzłów (Agents/Files/Memories/Functions/Classes) z logiką filtrowania równoczesnego.
- ✅ **Podświetlenia + szczegóły węzła**: kliknięcie węzła przygasza inne elementy, panel boczny prezentuje typ, relacje, metadane – bez konieczności używania arkusza JSON.
- ✅ **Loading + error toast**: dodano dedykowany overlay oraz toast błędu dla grafu – zgodnie z oryginałem.
- ✅ **Historia operacji / log**: sekcja „Ostatnie operacje grafu” bazująca na Lessons/scan logach odwzorowuje feed z legacy (ostatnie wpisy, daty, tagi).

## Inspector / Trace Intelligence
- ✅ **Źródło danych diagramu**: front korzysta teraz z `/api/v1/flow/{id}` (tak jak legacy) i renderuje gotowy Mermaid sequence diagram z dedykowanym theme/fallback. Do dopracowania pozostają akcenty decision gates i dodatkowe markery.
- **Manualne odświeżanie + loading**: `inspector.html` ma przycisk „🔄” i widok ładowania w liście (`web/templates/inspector.html:33-101`), a `inspector.js` ustawia `loading` flagę podczas fetchowania trace’ów (`inspector.js:60-110`). Obecna wersja bazuje wyłącznie na polllingu `useHistory` i nie pokazuje spinnera ani przycisku „Odśwież” — warto przywrócić opcję ręcznego odświeżenia z widocznym stanem ładowania, aby operator miał kontrolę.
- **Panel szczegółów kroków**: stary `details panel` pokazywał JSON `selectedStep` w `pre` i zachęcał do klikania elementów diagramu (`web/templates/inspector.html:200-250`). W Next pod nagłówkiem „Telemetria requestu” opisuje się jeden krok, ale nie ma osadzonego JSON-a. Warto dodać dodatkowy blok z pełnym JSON/konsolą, żeby nie tracić szczegółów (np. `historyDetail.steps` w formacie `pre`).

## Strategy / War Room
- **Potwierdzenie akcji „Kampania”**: `strategy.js` pyta o confirm przed wysłaniem `/api/campaign/start` (`web/static/js/strategy.js:170-185`). W `web-next/app/strategy/page.tsx` `handleStartCampaign` wywołuje endpoint bez potwierdzenia – należy dodać modal/confirm, aby nie uruchamiać kampanii przypadkowo tak jak w poprzednim kokpicie.
- ✅ **Toast/alerty dla akcji**: wpięto globalne powiadomienia dla akcji Roadmapy/Kampanii/Statusu – feedback identyczny jak w legacy.
- ✅ **Szybki widok milestone/task summary**: akordeony pokazują teraz status emoji i completed/total (dane z `/api/v1/roadmap`).
- ⏳ **Widok KPI / timeline**: należy zasilić puste sekcje danymi (`/api/v1/tasks`, `/api/v1/history`) – do zaplanowania.

## Uwagi końcowe
- Można rozszerzyć dokumentację (np. nowy checkpoint w `docs/_to_do`) o follow-up, gdy powyższe moduły zostaną odświeżone i przetestowane (np. przywrócenie spinnerów, testy Playwright, walidacja `buildMermaid`).

## Wykonane kroki
- Dodano potwierdzenie „Uruchom Kampanię” w `web-next/app/strategy/page.tsx`, które pyta o zgodę (`confirm`) przed wysłaniem żądania do `/api/campaign/start`, żeby odwzorować modal z legacy interfejsu i uniknąć przypadkowych akcji.
- Zaimplementowano w widoku Brain overlay ładowania/błędu, podgląd zaznaczonego węzła z relacjami oraz wielokrotne filtry typów + podświetlanie sąsiadów, co odtwarza UX starego grafu (spinner, status, highlight).
- Inspector ma teraz ręczne odświeżanie historii, bogatszy Mermaid (statusy, notatki decyzji), overlay ładowania i panel JSON dla zaznaczonego kroku – odpowiada to dawnemu „generateMermaidDiagram” i panelowi detali.
- Diagram Mermaid w Inspectorze jest znów generowany po stronie web-next z sanitacją danych (sequenceDiagram z Decision Gate), więc requesty takie jak `2850d089-...` renderują się identycznie jak w starym panelu i nie blokują się na błędnych danych z API.
- Widok „Diagnoza przepływu” dopasowuje teraz rozmiar diagramu do szerokości panelu (auto-fit + zachowanie proporcji), więc sekwencja nie jest ani miniaturowa, ani rozciągnięta w pionie – pełne okno jest wykorzystane tak jak w legacy inspectorze.
- Na stronie Strategy pojawił się toast statusowy dla akcji (create/start/report) oraz w akordeonie milestone’ów wyświetla się szybkie podsumowanie zadań (emoji + completed/total), co przywraca feedback i „milestone summary” z legacy UI.
