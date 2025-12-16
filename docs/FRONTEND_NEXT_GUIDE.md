# FRONTEND NEXT – CHECKLISTA MIGRACYJNA

Dokument rozszerza `docs/DASHBOARD_GUIDE.md` o informacje specyficzne dla wersji `web-next`. Zawiera:
1. Opis źródeł danych wykorzystywanych przez kluczowe widoki (Brain, Strategy) – łącznie z fallbackami.
2. Checklistę testów ręcznych i Playwright, która potwierdza gotowość funkcjonalną.
3. Kryteria wejścia do **Etapu 29** i listę elementów uznanych nadal za „legacy”.

---

## 1. Brain / Strategy – Źródła danych i hooki

| Widok / moduł                     | Endpointy / hooki                                                                                              | Fallback / uwagi                                                                                           |
|----------------------------------|----------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| **Brain** – Mind Mesh            | `useKnowledgeGraph` → `/api/v1/graph/summary`, `/api/v1/graph/scan`, `/api/v1/graph/file`, `/api/v1/graph/impact` | W przypadku błędu HTTP renderuje `OverlayFallback` i blokuje akcje (scan/upload).                          |
| **Brain** – Lessons & stats      | `useLessons`, `useLessonsStats`, `LessonActions` (tagi), `FileAnalysisForm`                                     | Brak danych wyświetla `EmptyState` z CTA „Odśwież lekcje”.                                                  |
| **Brain** – Kontrolki grafu      | `GraphFilterButtons`, `GraphActionButtons` + `useGraphSummary`                                                 | Wersje offline (np. brak `/api/v1/graph/summary`) pokazują badge `offline` w kartach BrainMetricCard.      |
| **Strategy** – KPI / Vision      | `useRoadmap` (`/api/v1/roadmap`), `requestRoadmapStatus`, `createRoadmap`, `startCampaign`                      | Wszystkie akcje owinięte w `useToast`; w razie 4xx/5xx panel wyświetla `OverlayFallback`.                   |
| **Strategy** – Milestones/Tasks  | `RoadmapKpiCard`, `TaskStatusBreakdown` (wykorzystuje `/api/v1/roadmap` oraz `/api/v1/tasks` dla statusów)      | Brak zadań → komunikat „Brak zdefiniowanych milestone’ów” (EmptyState).                                     |
| **Strategy** – Kampanie          | `handleStartCampaign` pyta `window.confirm` (jak legacy), po czym wysyła `/api/campaign/start`.                 | W razie braku API informuje użytkownika toastem i nie zmienia lokalnego stanu.                              |

> **Notatka:** wszystkie hooki korzystają z `lib/api-client.ts`, który automatycznie pobiera bazowy URL z `NEXT_PUBLIC_API_BASE` lub rewritów Next. Dzięki temu UI działa zarówno na HTTP jak i HTTPS bez ręcznej konfiguracji.

---

## 2. Testy – Brain / Strategy (manualne + Playwright)

### 2.1 Manual smoke (po każdym release)
1. **Brain**
   - `Scan graph` zwraca spinner i nowy log w „Ostatnie operacje grafu”.
   - Kliknięcie w węzeł otwiera panel z relacjami, tagami i akcjami (file impact, lessons).
2. **Strategy**
   - Odśwież roadmapę (`refreshRoadmap`) i sprawdź, że KPI/Milestones pokazują dane z API.
   - `Start campaign` → confirm prompt → komunikat sukcesu/błędu + log w toastach.

### 2.2 Playwright (do dodania / rozszerzenia)
| Nazwa scenariusza                    | Wejście / oczekiwania                                                                 |
|-------------------------------------|----------------------------------------------------------------------------------------|
| `brain-can-open-node-details`       | `page.goto("/brain")`, kliknięcie w pierwszy węzeł (seed data) → widoczny panel detali |
| `strategy-campaign-confirmation`    | Otwórz `/strategy`, kliknij „Uruchom kampanię”, sprawdź confirm + komunikat offline    |
| `strategy-kpi-offline-fallback`     | Przy wyłączonym backendzie widoczny `OverlayFallback` + tekst „Brak danych”.           |

> TODO: scenariusze powyżej dodajemy do `web-next/tests/smoke.spec.ts` po ustabilizowaniu CI. Dokument zostanie zaktualizowany wraz z PR-em dodającym testy.

---

## 3. Mapa bloków → etap 29

### 3.1 Checklist „legacy vs. next”
- [x] Sidebar / TopBar – korzystają z tokenów glass i wspólnych komponentów.
- [x] Cockpit – hero, command console, makra, modele, repo → wszystkie w stylu `_szablon.html`.
- [x] Brain / Strategy – opisane powyżej.
- [ ] Inspector – brak ręcznego „Odśwież” + panelu JSON (zadanie 051, sekcja 6).
- [ ] Strategy KPI timeline – wymaga realnych danych z `/api/v1/tasks` (zadanie 051, sekcja 6.3).

### 3.2 Kryteria wejścia do **Etapu 29**
1. **Parzystość funkcjonalna** – każde legacy view ma odpowiednik w `web-next`; brak duplikatów paneli.
2. **Komponenty współdzielone** – wszystkie listy/historie używają `HistoryList`/`TaskStatusBreakdown`.
3. **Testy** – Playwright obejmuje Cockpit, Brain, Inspector, Strategy + krytyczne overlaye.
4. **Dokumentacja** – niniejszy plik + README posiadają sekcję źródeł danych i testów.
5. **QA** – lista uwag z zadania 051 (sekcje 4–7) oznaczona jako ✅.

Po spełnieniu powyższych punktów można oficjalnie zamknąć etap 28 i przejść do 29 (np. optymalizacje wydajności, A/B testy UI).
