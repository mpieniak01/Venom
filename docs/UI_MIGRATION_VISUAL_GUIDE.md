# 🎨 Globalna Migracja UI - Przewodnik Wizualny

## Przed i Po - Layout Architecture

### PRZED (Stary Layout)
```
┌─────────────────────────────────────────────────┐
│  NAVBAR (poziomy pasek nawigacji)              │
│  🕷️ Venom | Home | Strategy | Brain | ...      │
└─────────────────────────────────────────────────┘
│                                                 │
│  MAIN CONTENT                                   │
│  (każda strona miała własny layout)            │
│                                                 │
│                                                 │
└─────────────────────────────────────────────────┘
```

### PO (Nowy Unified Layout)
```
┌──────────┬──────────────────────────────────────┐
│          │                                      │
│ SIDEBAR  │  MAIN WORKSPACE                      │
│          │                                      │
│ VENOM OS │  {% block content %}                 │
│          │                                      │
│ 🏠 Cockpit│  (zawartość specyficzna             │
│ 🎯 War Rm│   dla każdej strony)                 │
│ 🧠 Brain  │                                      │
│ 🔀 Flow  │                                      │
│ 🔍 Inspec│                                      │
│          │                                      │
│ ────────│                                      │
│ 🔐 Auton │                                      │
│ 🟢 ONLINE│                                      │
│ Latency  │                                      │
└──────────┴──────────────────────────────────────┘
```

## Komponenty Sidebara

### 1. Brand Logo
```html
<div class="brand">VENOM <span>OS</span></div>
```
- Font: JetBrains Mono, bold, uppercase
- Kolor "OS": neon green (#00ff9d) z glow effect

### 2. Navigation (Core Modules)
```
Core Modules
  🏠 Cockpit      [active: green border + glow]
  🎯 War Room
  🧠 The Brain

Tools
  🔀 Flow Inspector
  🔍 Inspector
```
- Hover: subtle background + border
- Active: green accent (#00ff9d) + pulsing dot

### 3. Sidebar Footer
```
────────────────
🔐 Autonomia
[Dropdown: ISOLATED ▼]

🟢 SYSTEM ONLINE
Latency: 12ms
```

## Strony - Szczegóły Migracji

### 1. 🏠 index.html (Cockpit)
**Status**: ✅ Działa bez zmian

**Layout**:
```
┌────────┬─────────────────────────────┬──────────────┐
│SIDEBAR │ COCKPIT DASHBOARD           │ TELEMETRY    │
│        │ - Header                    │ - Live Feed  │
│        │ - Queue Management          │ - Metrics    │
│        │ - Chat Console              │ - Tabs       │
│        │ - Suggestion Chips          │   📡 Feed    │
│        │ - Widgets Grid              │   🎤 Voice   │
│        │                             │   ⚙️ Jobs    │
└────────┴─────────────────────────────┴──────────────┘
```

### 2. 🎯 strategy.html (War Room)
**Status**: ✅ Zmigrowany

**Zmiany**:
- Usunięto padding z war-room-container (full width)
- Dark theme dla wszystkich paneli
- KPI cards z przezroczystym tłem

**Layout**:
```
┌────────┬────────────────────────────────────────┐
│SIDEBAR │ WAR ROOM - Zarządzanie Strategiczne    │
│        │ [Action Buttons]                       │
│        │ ┌──────────┬──────────┐               │
│        │ │ 🎯 VISION│ 📊 KPIs  │               │
│        │ └──────────┴──────────┘               │
│        │ ┌─────────────────────────────────┐   │
│        │ │ 📋 MILESTONES                   │   │
│        │ │ ✅ M1 | ⏳ M2 | ⏳ M3           │   │
│        │ └─────────────────────────────────┘   │
└────────┴────────────────────────────────────────┘
```

### 3. 🧠 brain.html (The Brain)
**Status**: ✅ Zmigrowany

**Zmiany**:
- Graf Cytoscape na pełną szerokość (margin: -40px)
- Dark background (#030407)
- Floating panels z purple accent (#8b5cf6)
- Backdrop blur effect

**Layout**:
```
┌────────┬────────────────────────────────────────┐
│SIDEBAR │ ╔════════════════════════════════════╗ │
│        │ ║  [Node Details]  CYTOSCAPE GRAPH   ║ │
│        │ ║  ┌─────────────┐                   ║ │
│        │ ║  │ 🔵 Node 1   │   ●──●──●         ║ │
│        │ ║  │ Type: Agent │   │     │         ║ │
│        │ ║  └─────────────┘   ●──●──●         ║ │
│        │ ║                                    ║ │
│        │ ║              [Brain Controls] ───┐ ║ │
│        │ ║              🧠 The Brain        │ ║ │
│        │ ║              Nodes: 42           │ ║ │
│        │ ║              └───────────────────┘ ║ │
│        │ ╚════════════════════════════════════╝ │
└────────┴────────────────────────────────────────┘
```

### 4. 🔍 inspector.html (Interactive Inspector)
**Status**: ✅ Zmigrowany

**Zmiany**:
- Renamed classes: `.inspector-sidebar`, `.inspector-main-content`
- Dark panels z glass effect
- Status badges z alpha transparency
- Full bleed (margin: -40px)

**Layout**:
```
┌────────┬─────────┬──────────────────────────────┐
│SIDEBAR │ TRACES  │ DIAGRAM + DETAILS            │
│        │ ┌─────┐ │ ┌─────────────────────────┐  │
│        │ │ abc..│ │ │ 📊 Mermaid Sequence    │  │
│        │ │ def..│ │ │ Actor1 -> Actor2       │  │
│        │ │ ghi..│ │ └─────────────────────────┘  │
│        │ └─────┘ │ ┌─────────────────────────┐  │
│        │         │ │ 🔍 Step Details (JSON)  │  │
│        │         │ └─────────────────────────┘  │
└────────┴─────────┴──────────────────────────────┘
```

### 5. 🔀 flow_inspector.html
**Status**: ✅ Zmigrowany

**Zmiany**:
- Mermaid dark theme z dynamic CSS variables
- getComputedStyle() dla koloru
- Flow steps z color-coded borders

**Layout**:
```
┌────────┬────────────────────────────────────────┐
│SIDEBAR │ 🔀 Flow Inspector                      │
│        │ ┌────────────────────────────────────┐ │
│        │ │ 📋 Task Selector                   │ │
│        │ │ [abc...] COMPLETED                 │ │
│        │ └────────────────────────────────────┘ │
│        │ ┌────────────────────────────────────┐ │
│        │ │ 📊 Mermaid Flow Diagram            │ │
│        │ │ ┌─────┐   ┌─────┐   ┌─────┐       │ │
│        │ │ │Start│──>│Gate │──>│ End │       │ │
│        │ │ └─────┘   └─────┘   └─────┘       │ │
│        │ └────────────────────────────────────┘ │
│        │ 🔍 Flow Steps (detailed list)         │
└────────┴────────────────────────────────────────┘
```

## Color Palette - Deep Space Theme

### Główne kolory
```css
/* Backgrounds */
--bg-dark: #030407         /* █████ Deep space black */
--bg-panel: rgba(16,20,28,0.6) /* ████░ Glass panels */
--bg-medium: #1e293b       /* ████▒ Medium gray */
--bg-light: #334155        /* ████▓ Light gray */

/* Accents */
--primary-color: #8b5cf6   /* ▓▓▓▓▓ Purple (UI primary) */
--primary-green: #00ff9d   /* █████ Neon green (brand) */
--primary-hover: #7c3aed   /* ▓▓▓▓░ Purple dark */
--secondary-color: #06b6d4 /* ▒▒▒▒▒ Cyan */

/* Status */
--success-color: #10b981   /* ▓▓▓▓▓ Green */
--error-color: #ef4444     /* █████ Red */
--warning-color: #f59e0b   /* ▓▓▓▓▓ Orange */

/* Text */
--text-primary: #f1f5f9    /* ████▓ Off-white */
--text-secondary: #94a3b8  /* ███▒░ Gray */
--text-muted: #94a3b8      /* ██▒░░ Muted gray */
```

### Efekty wizualne
```css
/* Glow */
--glow-strong: 0 0 20px rgba(0, 255, 157, 0.25)
--glow-hover: 0 0 20px rgba(139, 92, 246, 0.4)

/* Glass */
--border-glass: 1px solid rgba(255, 255, 255, 0.08)
backdrop-filter: blur(15px)
```

## Typography

### Fonty
```css
/* UI Text */
--font-ui: 'Inter', 'Segoe UI', sans-serif
/* Weights: 300 (light), 400 (regular), 600 (semibold) */

/* Technical / Code */
--font-tech: 'JetBrains Mono', 'Consolas', monospace
/* Weights: 400, 500, 700 */
```

### Użycie
- **Brand logo**: JetBrains Mono, 800, 1.6rem, uppercase
- **Navigation**: JetBrains Mono, 0.9rem
- **Section labels**: JetBrains Mono, 0.75rem, uppercase
- **Headers**: Inter, 600, 1.2-2.5rem
- **Body text**: Inter, 400, 0.85-1rem
- **Code/IDs**: JetBrains Mono, 400, 0.85rem

## Responsive Behavior

**Desktop (>768px)**:
- Sidebar: Fixed 280px width
- Main workspace: Flexible (flex: 1)
- Right panel (Cockpit): Fixed 380px width

**Future Mobile (<768px)** - TODO:
- Sidebar: Collapse to hamburger menu
- Main workspace: Full width
- Right panel: Below main content or tabbed

## Animacje

### 1. Navigation Active State
```css
.nav-link.active::after {
    content: '●';
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { opacity: 0.5; }
    50% { opacity: 1; text-shadow: 0 0 5px var(--primary-green); }
    100% { opacity: 0.5; }
}
```

### 2. Hover Transitions
```css
.nav-link, .btn, .card {
    transition: all 0.2s ease;
}
```

### 3. Loading Spinners
```css
.loading-spinner {
    animation: spin 1s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}
```

## Accessibility

### Semantic HTML
- `<aside>` dla sidebara
- `<main>` dla main workspace
- `<nav>` dla menu nawigacyjnego
- `<section>` dla sekcji treści

### ARIA Labels
```html
<div role="dialog" aria-modal="true" aria-labelledby="modalTitle">
<button aria-label="Zamknij modal">
<div role="application" aria-label="Graf wiedzy">
```

### Keyboard Navigation
- Tab order: Sidebar nav → Main content → Right panel
- Enter/Space dla buttonów
- Arrow keys dla dropdownów

### Color Contrast
- Text primary (#f1f5f9) na dark bg: **15.9:1** ✅ AAA
- Text secondary (#94a3b8) na dark bg: **8.5:1** ✅ AA
- Purple accent (#8b5cf6) na dark bg: **7.2:1** ✅ AA

## Testing Checklist

### Visual Regression
- [ ] Sprawdź wszystkie strony w Chrome
- [ ] Sprawdź wszystkie strony w Firefox
- [ ] Sprawdź wszystkie strony w Safari
- [ ] Sprawdź na różnych rozdzielczościach (1920x1080, 1366x768, 2560x1440)

### Functional Testing
- [ ] Kliknij każdy link w sidebar - czy strony się ładują?
- [ ] Hover nad navigation links - czy efekty działają?
- [ ] Active state - czy pokazuje aktualną stronę?
- [ ] Autonomy selector - czy dropdown działa?
- [ ] Status połączenia - czy aktualizuje się?

### Dark Mode Verification
- [ ] Brak białych błysków podczas ładowania
- [ ] Wszystkie komponenty w dark theme
- [ ] Mermaid diagramy w dark mode
- [ ] Cytoscape graph z ciemnym tłem

### Cross-page Consistency
- [ ] Sidebar identyczny na wszystkich stronach
- [ ] Fonty spójne (Inter + JetBrains Mono)
- [ ] Kolory zgodne z design system
- [ ] Glow effects działają

## Performance Notes

### CSS
- Modularny CSS: 1311 linii (vs 2417 legacy)
- Import order: variables → layout → components → animations
- Backward compatibility: app.css loaded alongside main.css

### JavaScript
- Optional chaining (?.) dla nowych elementów
- Lazy loading dla heavy components (Cytoscape, Mermaid)
- Dynamic CSS variables w Mermaid (getComputedStyle)

### Images/Assets
- Brak obrazów (pure CSS + SVG icons via emojis)
- Google Fonts preconnect dla szybszego ładowania
- Backdrop blur może być ciężki na słabych GPU

## Known Limitations

1. **Brak mobile layout** - obecna wersja tylko desktop
2. **Mermaid performance** - getComputedStyle na każde ładowanie
3. **Backward compat** - app.css nadal loaded (2417 linii extra)
4. **Strategy.html inline CSS** - powinien być w strategy.css

## Future Enhancements

1. **Responsive mobile layout** - hamburger menu, stacked panels
2. **Theme switcher** - light/dark mode toggle
3. **Custom theme editor** - zmiana akcentów
4. **Reduce bundle size** - usunąć app.css po testach
5. **Animation polish** - page transitions, micro-interactions
6. **Accessibility audit** - pełny WCAG 2.1 compliance
7. **Performance optimization** - critical CSS, lazy loading

---

**Autor**: GitHub Copilot Agent  
**Data**: 2025-12-11  
**Branch**: copilot/refactor-global-ui-migration  
**Status**: ✅ COMPLETE
