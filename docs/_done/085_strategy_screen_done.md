# 085: Ekran strategii (/strategy) – DONE
Status: ✅ Zakończone

## Cel
Ustabilizować i doprecyzować ekran `/strategy` jako centrum „War Room":
- jasny podział między **danymi live** a **cache**,
- czytelne źródła danych (API, raporty, kampanie),
- spójne komunikaty, gdy dane są puste lub tylko częściowo dostępne.

## Zaimplementowane zmiany

### 1. Wskaźniki statusu danych (DataSourceIndicator)
Utworzono nowy komponent `/web-next/components/strategy/data-source-indicator.tsx`:
- **Statusy**: live (🟢), cache (💾), stale (⚠️), offline (🔴)
- **Timestamp**: wyświetla czas ostatniej aktualizacji danych w formacie względnym (np. "2m temu")
- **Funkcja calculateDataSourceStatus**: automatycznie określa status na podstawie dostępności danych live/cache i timestampu

### 2. Rozbudowany RoadmapKpiCard
Zaktualizowano `/web-next/components/strategy/roadmap-kpi-card.tsx`:
- Dodano opcjonalne pole `source` pokazujące źródło danych (np. "Roadmapa")
- Czytelne oznaczenie źródła metryki w interfejsie

### 3. Usprawnienia ekranu strategii
Zaktualizowano `/web-next/app/strategy/page.tsx`:

#### a) Śledzenie timestampów
- Dodano `ROADMAP_TS_KEY` do śledzenia czasu aktualizacji roadmapy
- Timestamp zapisywany w sessionStorage przy każdej aktualizacji
- Automatyczne odczytywanie timestampów przy inicjalizacji

#### b) Wskaźniki statusu danych
- Panel "Wizja" pokazuje status roadmapy (live/cache/stale/offline)
- Panel "Raport statusu" pokazuje status raportu z timestampem
- Wskaźniki aktualizują się automatycznie

#### c) Lepsze komunikaty empty-state
- **Wizja**: rozróżnienie między "Backend niedostępny" (gdy `roadmapError`) a "Brak zdefiniowanej wizji"
- **Raport statusu**: jasny komunikat o braku raportu z instrukcją
- Wszystkie empty-states mają ikonę, tytuł i opis z sugestią akcji

#### d) Auto-refresh po kampanii
- Po uruchomieniu kampanii (`startCampaign`) automatycznie odświeża roadmapę i raport statusu po 2 sekundach
- Użytkownik otrzymuje feedback o sukcesie/błędzie

#### e) Źródła danych w KPI
- Wszystkie karty KPI (Postęp wizji, Milestones, Tasks) pokazują źródło: "Roadmapa"

### 4. Testy
Utworzono `/web-next/tests/data-source-indicator.test.ts`:
- Test wszystkich statusów: live, cache, stale, offline
- Test edge cases: brak timestampu, różne progi staleness
- ✅ Wszystkie testy przechodzą

## Kryteria akceptacji - STATUS

✅ **Użytkownik rozumie, czy widzi dane live czy cache**
- Wskaźniki statusu w panelach "Wizja" i "Raport statusu"
- Kolory i ikony jasno komunikują stan danych

✅ **Raport statusu pokazuje datę wygenerowania i komunikat o "stale"**
- Timestamp wyświetlany w formacie względnym
- Status "Stare dane" (⚠️) po przekroczeniu 60s

✅ **Empty-state nie jest "pusty": ma jasny powód i sugestię akcji**
- Rozróżnienie między "Backend niedostępny" a "Brak danych"
- Każdy empty-state ma ikonę, tytuł i opis z instrukcją

✅ **Ekran pozostaje spójny z resztą War Room**
- Używa istniejących komponentów (Badge, Panel, EmptyState)
- Spójna nomenklatura i styl wizualny

## Odpowiedzi na otwarte pytania

### Czy `/api/roadmap/status` ma zwracać metadane (timestamp, runtime)?
**Rozwiązanie**: UI bazuje na cache i timestampach w sessionStorage. Nie wymaga zmian w API.

### Czy po `startCampaign` automatycznie uruchamiać `fetchStatusReport` i `refreshRoadmap`?
**Rozwiązanie**: ✅ TAK - zaimplementowane. Po 2 sekundach od startu kampanii automatycznie odświeżamy dane.

### Jak definiujemy "stale"?
**Rozwiązanie**: Dane są "stale" gdy timestamp przekracza próg `REPORT_STALE_MS` (60 sekund). Dotyczy to tylko danych z cache - live data nigdy nie są stale.

## Pliki zmodyfikowane
1. `/web-next/components/strategy/data-source-indicator.tsx` - NOWY
2. `/web-next/components/strategy/roadmap-kpi-card.tsx` - ZMODYFIKOWANY
3. `/web-next/app/strategy/page.tsx` - ZMODYFIKOWANY
4. `/web-next/tests/data-source-indicator.test.ts` - NOWY

## Testy
- ✅ Lint OK
- ✅ TypeScript compilation OK
- ✅ Unit tests OK
- ⚠️ Build - nie udało się z powodu problemów sieciowych (Google Fonts), ale TypeScript compilation przeszła pomyślnie

## Notatki techniczne
- Użyto istniejącego `formatRelativeTime` z `@/lib/date` do formatowania timestampów
- `calculateDataSourceStatus` jako czysta funkcja, łatwa do testowania
- Minimalne zmiany w istniejącym kodzie - tylko rozszerzenia
- Backwards compatible - wszystkie nowe pola są opcjonalne
