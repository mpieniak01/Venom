# Strategy Screen - Visual Summary of Changes

## Before vs After

### Before (Issues)
```
❌ Brak informacji czy dane są live czy z cache
❌ Brak timestampu raportu statusu
❌ Empty-states bez wyjaśnienia przyczyny
❌ Brak automatycznego odświeżania po kampanii
❌ Brak informacji skąd pochodzą KPI
```

### After (Resolved)
```
✅ Wskaźniki statusu: Live 🟢 / Cache 💾 / Stale ⚠️ / Offline 🔴
✅ Timestamp w formacie "2m temu" przy każdym źródle danych
✅ Empty-states z jasnym komunikatem i sugestią akcji
✅ Auto-refresh roadmapy i raportu po starcie kampanii
✅ Każde KPI pokazuje źródło: "Roadmapa"
```

## Component Structure

```
StrategyPage
├── SectionHeading (War Room)
├── Toast notifications
├── Actions Panel
│   ├── 🔄 Odśwież Roadmapę
│   ├── ✨ Zdefiniuj Wizję
│   ├── 🚀 Uruchom Kampanię (+ auto-refresh)
│   └── 📊 Raport Statusu
│
├── Vision Form (conditional)
│
├── KPI Cards Grid (3 columns)
│   ├── Postęp wizji [Źródło: Roadmapa]
│   ├── Milestones [Źródło: Roadmapa]
│   └── Tasks [Źródło: Roadmapa]
│
├── Main Content Grid (2 columns)
│   ├── Wizja Panel
│   │   ├── Header + DataSourceIndicator [Live/Cache/Stale/Offline + timestamp]
│   │   └── Content OR EmptyState (backend niedostępny / brak wizji)
│   │
│   ├── Raport statusu Panel
│   │   ├── Header + DataSourceIndicator [Cache/Stale/Offline + timestamp]
│   │   └── Content OR EmptyState (brak raportu)
│   │
│   └── Podsumowanie zadań Panel
│
├── Live/Timeline KPIs Grid (2 columns)
│   ├── Live KPIs (/api/v1/tasks)
│   └── Timeline KPI (/api/v1/history)
│
├── Milestones Panel (Accordion)
└── Pełny raport Panel
```

## Data Flow

```
1. Initial Load
   ├── Load from sessionStorage (cache)
   │   ├── ROADMAP_CACHE_KEY → roadmapData
   │   ├── ROADMAP_TS_KEY → roadmapTimestamp
   │   ├── REPORT_CACHE_KEY → statusReport
   │   └── REPORT_TS_KEY → reportTimestamp
   │
   └── Fetch live data (polling)
       └── useRoadmap (30s interval)

2. Status Calculation
   ├── calculateDataSourceStatus(hasLive, hasCache, timestamp, threshold)
   │   ├── hasLive → "live" 🟢
   │   ├── !hasCache → "offline" 🔴
   │   ├── timestamp > threshold → "stale" ⚠️
   │   └── else → "cache" 💾
   │
   ├── roadmapDataStatus = f(liveRoadmap, cachedRoadmap, roadmapTimestamp, 60s)
   └── reportDataStatus = f(false, statusReport, reportTimestamp, 60s)

3. Data Updates
   ├── Live roadmap received
   │   ├── Update cachedRoadmap
   │   ├── Save to sessionStorage (ROADMAP_CACHE_KEY)
   │   ├── Save timestamp (ROADMAP_TS_KEY)
   │   └── Update roadmapTimestamp state
   │
   └── Manual report fetch
       ├── Update statusReport
       ├── Save to sessionStorage (REPORT_CACHE_KEY)
       ├── Save timestamp (REPORT_TS_KEY)
       └── Update reportTimestamp state

4. Campaign Start Flow
   ├── User clicks "Uruchom Kampanię"
   ├── Confirm dialog
   ├── Call startCampaign() API
   ├── Show success/error toast
   └── setTimeout(AUTO_REFRESH_DELAY_MS)
       ├── refreshRoadmap()
       └── fetchStatusReport({ silent: true })
```

## Constants Configuration

```typescript
// Cache keys
ROADMAP_CACHE_KEY = "strategy-roadmap-cache"
REPORT_CACHE_KEY = "strategy-status-report"
ROADMAP_TS_KEY = "strategy-roadmap-ts"
REPORT_TS_KEY = "strategy-status-report-ts"

// Thresholds
REPORT_STALE_MS = 60_000 // 60 seconds
AUTO_REFRESH_DELAY_MS = 2000 // 2 seconds

// Labels
SOURCE_LABEL = "Źródło:"
```

## Status Badge Matrix

| Condition | Status | Badge | Tone |
|-----------|--------|-------|------|
| Live data available | live | 🟢 Live | success |
| Cache fresh (< 60s) | cache | 💾 Cache | warning |
| Cache old (> 60s) | stale | ⚠️ Stare dane | danger |
| No data | offline | 🔴 Offline | danger |

## Empty State Decision Tree

```
Wizja Panel:
├── roadmapData?.vision exists? → Show vision details
├── roadmapError? → Show "Backend niedostępny" ⚠️
└── else → Show "Brak zdefiniowanej wizji" ✨

Raport Panel:
├── statusReport exists? → Show markdown report
└── else → Show "Brak raportu" 📊 + instrukcja

Live KPIs:
├── liveTasksLoading? → "Ładuję metryki zadań…"
├── liveTaskStats.length? → Show stat cards
└── else → "Brak danych o zadaniach" 🛰️

Timeline KPI:
├── timelineLoading? → "Ładuję historię requestów…"
├── timelineEntries.length? → Show timeline entries
└── else → "Brak historii" 🕒
```

## Test Coverage

```typescript
// calculateDataSourceStatus tests
✅ Live data available → "live"
✅ Cache fresh → "cache"
✅ Cache stale → "stale"
✅ No data → "offline"
✅ Cache without timestamp → "cache"
```

## Integration Points

```
External APIs:
├── /api/roadmap (polling 30s)
├── /api/roadmap/status (manual + auto)
├── /api/roadmap/create (POST)
├── /api/campaign/start (POST)
├── /api/v1/tasks (polling 5s)
└── /api/v1/history (polling 10s)

SessionStorage:
├── strategy-roadmap-cache (JSON)
├── strategy-roadmap-ts (timestamp)
├── strategy-status-report (string)
└── strategy-status-report-ts (timestamp)

Hooks:
├── useRoadmap()
├── useTasks()
├── useHistory()
└── useTaskStream()
```
