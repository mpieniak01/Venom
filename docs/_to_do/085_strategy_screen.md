# 085: Ekran strategii (/strategy) – zakres, stan i plan PR
Status: do zrobienia (PR plan + analiza stanu obecnego).

## Cel
Ustabilizować i doprecyzować ekran `/strategy` jako centrum „War Room”:
- jasny podział między **danymi live** a **cache**,
- czytelne źródła danych (API, raporty, kampanie),
- spójne komunikaty, gdy dane są puste lub tylko częściowo dostępne.

## Kontekst (co jest zaimplementowane vs. placeholder)
### Zaimplementowane (działa realnie)
- **Roadmapa** z `/api/roadmap`:
  - wizja (title, status, description),
  - milestones + tasks,
  - report (pełny raport).
- **Raport statusu** z `/api/roadmap/status` (pobierany ręcznie + auto-refresh co 60s).
- **KPI** wyliczane z roadmapy (postęp wizji, milestones, tasks).
- **Live KPI** z `/api/v1/tasks` (aktywni / w kolejce / niepowodzenia).
- **Timeline KPI** z `/api/v1/history` (ostatnie requesty).
- **SessionStorage cache** dla roadmapy i raportu statusu.

### Placeholder / ograniczenia
- Jeśli API nie zwróci danych, UI pokazuje tylko empty-state, bez wyjaśnienia *dlaczego* (brak backendu, brak danych, brak kampanii).
- Raport statusu jest tylko tekstem; brak metadanych (kiedy wygenerowano, jak długo ważny, z jakiego runtime).
- Start kampanii `/api/campaign/start` – brak powiązania z UI feedback (czy kampania faktycznie wystartowała i czy roadmapa/raport aktualizują się automatycznie).
- Brak jasnego rozróżnienia „danych live” vs „danych z cache”.

## Zakres PR (plan)
1) **Źródła danych i statusy**
   - dodać w UI mini-wskaźniki: live/cache/stale dla roadmapy i raportu statusu,
   - wprost pokazać timestamp raportu (z `REPORT_TS_KEY`).
2) **Lepsze empty-states**
   - rozróżnić „brak danych” vs „backend niedostępny” vs „kampania nie uruchomiona”.
3) **Sekcja akcji**
   - po uruchomieniu kampanii automatycznie odświeżyć roadmapę i raport (lub wyświetlić instrukcję, co się stanie).
4) **Czytelność metryk**
   - KPI opisane, skąd pochodzą (np. „Roadmapa – milestones”).

## Kryteria akceptacji
- Użytkownik rozumie, czy widzi dane live czy cache.
- Raport statusu pokazuje datę wygenerowania i komunikat o „stale” po przekroczeniu progu.
- Empty-state nie jest „pusty”: ma jasny powód i sugestię akcji.
- Ekran pozostaje spójny z resztą War Room (styl, nomenklatura).

## Otwarte pytania
- Czy `/api/roadmap/status` ma zwracać metadane (timestamp, runtime) czy UI ma bazować wyłącznie na cache?
- Czy po `startCampaign` automatycznie uruchamiać `fetchStatusReport` i `refreshRoadmap`?
- Jak definiujemy „stale”: tylko czas raportu czy też brak heartbeat z backendu?
