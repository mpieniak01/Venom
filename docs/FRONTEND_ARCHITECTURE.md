# Venom OS - Architektura Modularna Frontend

## 📋 Przegląd

Frontend Venoma został zrefaktoryzowany z monolitycznej struktury (app.js ~3777 linii, app.css ~2416 linii) na modularną architekturę zgodną z wzorcem "Venom OS Unified Config" (Deep Space theme).

## 🎨 Struktura CSS

### Moduły CSS (`web/static/css/modules/`)

```
modules/
├── variables.css      # Design Tokens (Deep Space theme)
├── layout.css         # Layout system (sidebar, grid, tabs, panels)
├── components.css     # UI Components (buttons, cards, forms, terminal)
└── animations.css     # Animations (pulse, slideIn, glow, spin)
```

### Główny plik (`web/static/css/main.css`)

```css
@import url('modules/variables.css');
@import url('modules/layout.css');
@import url('modules/components.css');
@import url('modules/animations.css');
```

**Kolejność importu jest ważna:** variables → layout → components → animations

### Design Tokens (Deep Space Theme)

```css
:root {
    /* Palette */
    --bg-dark: #030407;
    --bg-panel: rgba(16, 20, 28, 0.6);
    
    /* Neon Accents */
    --primary: #00ff9d;
    --secondary: #00b8ff;
    
    /* Glow Effects */
    --glow-strong: 0 0 20px rgba(0, 255, 157, 0.25);
    --glow-hover: 0 0 20px rgba(0, 255, 157, 0.4);
    
    /* Typography */
    --font-ui: 'Inter', 'Segoe UI', sans-serif;
    --font-tech: 'JetBrains Mono', 'Consolas', monospace;
}
```

## 🔧 Struktura JavaScript

### Moduły JS (`web/static/js/modules/`)

```
modules/
├── api.js       # REST API Client (34 metody)
├── socket.js    # WebSocket Manager (auto-reconnect)
├── ui.js        # UI Rendering & DOM Manipulation
└── audio.js     # Audio/Voice (Push-to-Talk, Visualization)
```

### `api.js` - REST API Client

**Eksportuje:** `ApiClient`

**Metody:**
- Task Management: `sendTask()`, `abortTask()`
- Metrics: `fetchMetrics()`, `fetchTokenomics()`
- Queue: `fetchQueueStatus()`, `pauseQueue()`, `resumeQueue()`, `purgeQueue()`, `emergencyStop()`
- Memory: `fetchLessons()`, `fetchGraphSummary()`, `triggerGraphScan()`
- Models: `fetchModels()`, `installModel()`, `unloadAllModels()`
- Repository: `fetchRepositoryStatus()`
- Integrations: `fetchIntegrations()`
- History: `fetchHistory()`, `fetchHistoryDetails()`
- Cost Guard: `fetchCostMode()`, `setCostMode()`

### `socket.js` - WebSocket Manager

**Eksportuje:** `SocketManager`

**Funkcjonalność:**
- Auto-reconnect z exponential backoff (max 5 prób)
- Obsługa wszystkich typów eventów (TASK_CREATED, AGENT_THOUGHT, itp.)
- Delegacja eventów do głównego dashboard

### `ui.js` - UI Manager

**Eksportuje:** `UIManager`

**Funkcjonalność:**
- Chat messages rendering (z badges dla modeli i źródeł)
- Log entries (live feed)
- Notifications (toast messages)
- Metrics display
- Queue status updates
- Connection status
- Tab switching

### `audio.js` - Audio Manager

**Eksportuje:** `AudioManager`

**Funkcjonalność:**
- Push-to-Talk (mousedown/mouseup, touch support)
- Audio visualization (canvas + Web Audio API)
- MediaRecorder integration
- Transcription via `/api/v1/audio/transcribe`

## 🔄 Integracja z istniejącym kodem

### Opcja 1: Stopniowa migracja (zalecana)

Obecny `app.js` pozostaje niezmieniony. Nowe moduły mogą być używane w nowych funkcjach:

```javascript
import { ApiClient } from './modules/api.js';
import { SocketManager } from './modules/socket.js';

const api = new ApiClient(dashboard);
const socket = new SocketManager(dashboard);
```

### Opcja 2: Pełna refaktoryzacja (przyszłość)

Przekształcenie `app.js` w orchestrator:

```javascript
import { ApiClient } from './modules/api.js';
import { SocketManager } from './modules/socket.js';
import { UIManager } from './modules/ui.js';
import { AudioManager } from './modules/audio.js';

class VenomDashboard {
    constructor() {
        this.api = new ApiClient(this);
        this.socket = new SocketManager(this);
        this.ui = new UIManager(this);
        this.audio = new AudioManager(this);
    }

    init() {
        this.socket.init();
        this.audio.init();
        // ... rest of initialization
    }
}
```

## 🐛 Naprawione błędy

### Zadanie 0: Layout czatu

**Problem:** `.chat-input-container` używało `display: flex` bez `flex-direction`, powodując układ poziomy (textarea obok przycisków).

**Rozwiązanie:** Dodano `flex-direction: column` w `app.css` (linia 406).

```css
.chat-input-container {
    padding: 1rem;
    border-top: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;  /* ← FIX */
    gap: 0.5rem;
    background: var(--bg-medium);
    flex-shrink: 0;
}
```

## 📦 Kompatybilność wsteczna

### CSS
- `main.css` ładowany jako pierwszy (nowe style)
- `app.css` ładowany jako drugi (fallback dla niezmigowanych stylów)

W `base.html`:
```html
<link rel="stylesheet" href="/static/css/main.css">
<link rel="stylesheet" href="/static/css/app.css">
```

### JavaScript
- Moduły przygotowane jako ES6 modules
- Istniejący `app.js` pozostaje niezmieniony
- Można używać modułów stopniowo w nowych funkcjach

## 🚀 Jak używać

### 1. Dodawanie nowych stylów

Edytuj odpowiedni moduł zamiast `app.css`:

- **Kolory/zmienne** → `modules/variables.css`
- **Layout/grid** → `modules/layout.css`
- **Komponenty UI** → `modules/components.css`
- **Animacje** → `modules/animations.css`

### 2. Dodawanie nowych funkcji API

```javascript
// W modules/api.js
async myNewEndpoint() {
    const response = await fetch(`${this.baseUrl}/my-endpoint`);
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
}
```

### 3. Obsługa nowych typów WebSocket eventów

```javascript
// W app.js (w handleWebSocketEvent)
case 'MY_NEW_EVENT':
    this.handleMyNewEvent(eventData);
    break;
```

### 4. Dodawanie nowych widoków UI

```javascript
// W modules/ui.js
renderMyNewWidget(data) {
    const container = document.getElementById('myContainer');
    // ... render logic
}
```

## 🎯 Zachowane funkcjonalności

✅ WebSocket z auto-reconnect  
✅ Chat interface z suggestion chips  
✅ Audio/Voice z wizualizacją  
✅ Widget rendering (Chart.js, Mermaid)  
✅ Queue Governance (PAUZA, EMERGENCY STOP)  
✅ Repository status  
✅ Cost Guard  
✅ Model management (THE_ARMORY)  
✅ Memory & Knowledge Graph  
✅ Wszystkie zakładki w panelu bocznym  

## 📝 TODO (przyszłość)

- [ ] Pełna migracja `app.js` do architektury modułowej
- [ ] Usunięcie `app.css` (po przeniesieniu wszystkich stylów do modułów)
- [ ] Dodanie TypeScript dla lepszej type safety
- [ ] Unit testy dla modułów JS
- [ ] Lazy loading dla ciężkich bibliotek (Chart.js, Mermaid)
- [ ] Service Worker dla offline support

## 🔒 Bezpieczeństwo

✅ CodeQL scan: 0 alertów  
✅ XSS protection: `escapeHtml()` w UI rendering  
✅ Input sanitization w WebSocket message handling  
✅ CSP-ready (brak inline scripts w nowych modułach)  

## 📚 Referencje

- [Unified Config Design](_szablon.html) - Wzorzec Deep Space theme
- [CSS Variables MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/Using_CSS_custom_properties)
- [ES6 Modules MDN](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules)
- [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)
