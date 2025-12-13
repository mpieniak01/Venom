/**
 * inspector.js - Interaktywny Inspektor Przepływu
 * Vanilla JS + Mermaid.js + svg-pan-zoom
 */

// Sprawdź dostępność wymaganych bibliotek
if (typeof mermaid === 'undefined') {
    console.error('❌ Mermaid.js not loaded from CDN');
}

if (typeof svgPanZoom === 'undefined') {
    console.error('❌ svg-pan-zoom not loaded from CDN');
}

// Inicjalizacja Mermaid
if (typeof mermaid !== 'undefined') {
    mermaid.initialize({
        startOnLoad: false,
        theme: 'default',
        securityLevel: 'strict', // Bezpieczniejszy tryb - zapobiega XSS
        sequence: {
            showSequenceNumbers: true,
            actorMargin: 50,
            width: 150,
            height: 65,
            boxMargin: 10,
            noteMargin: 10
        }
    });
}

// Globalna zmienna dla svg-pan-zoom
let panZoomInstance = null;
const INSPECTOR_PREFS_KEY = 'venomInspectorUIPreferences';
const INSPECTOR_PREFS_DEFAULTS = {
    filterStatus: 'all',
    searchQuery: '',
    autoRefresh: true
};

/**
 * Sanityzuje tekst dla diagramu Mermaid aby zapobiec injection attacks
 * @param {string} text - Tekst do sanityzacji
 * @returns {string} - Bezpieczny tekst
 */
function sanitizeMermaidText(text) {
    if (!text) return '';

    // Usuń potencjalnie niebezpieczne znaki dla Mermaid
    return text
        .replace(/[<>]/g, '') // Usuń znaki HTML
        .replace(/[;\n\r]/g, ' ') // Usuń znaki nowej linii i średniki
        .replace(/\|/g, '│') // Zamień pipe na podobny znak (pipe ma specjalne znaczenie w Mermaid)
        .replace(/--/g, '−') // Zamień podwójny myślnik na minus
        .trim();
}

class InspectorApp {
    constructor() {
        this.preferences = this.loadUIPreferences();
        this.state = {
            traces: [],
            filterStatus: this.preferences.filterStatus,
            searchQuery: this.preferences.searchQuery,
            autoRefresh: this.preferences.autoRefresh,
            loading: false,
            traceError: null,
            currentTraceId: null,
            currentFlowData: null,
            selectedStep: null,
            lastUpdated: null,
            lastMermaidCode: '',
            lastDiagramSvg: null,
            pinnedTraces: []
        };

        this.autoRefreshTimer = null;
        this.elements = this.cacheElements();
        this.state.pinnedTraces = this.loadPinnedTraces();
        this.setExportButtonsEnabled(false);
        this.syncTraceDownloadAvailability();
        this.renderPinnedTraces();
        this.syncStepExportAvailability();
        this.bindEvents();
        this.applyUIPreferencesToControls();
        this.init();
    }

    cacheElements() {
        return {
            traceList: document.getElementById('inspectorTraceList'),
            pinnedContainer: document.getElementById('inspectorPinnedContainer'),
            pinnedList: document.getElementById('inspectorPinnedList'),
            clearPinnedBtn: document.getElementById('inspectorClearPinned'),
            filterButtons: document.querySelectorAll('.inspector-filter-btn'),
            searchInput: document.getElementById('inspectorSearchInput'),
            autoToggle: document.getElementById('inspectorAutoRefresh'),
            refreshBtn: document.getElementById('inspectorRefreshBtn'),
            lastUpdatedLabel: document.getElementById('inspectorLastUpdated'),
            traceStatsLabel: document.getElementById('inspectorTraceStats'),
            pinnedCountLabel: document.getElementById('inspectorPinnedCount'),
            diagramContainer: document.getElementById('mermaidSvgContainer'),
            diagramPlaceholder: document.getElementById('inspectorDiagramPlaceholder'),
            detailsPlaceholder: document.getElementById('inspectorDetailsPlaceholder'),
            detailsRaw: document.getElementById('inspectorDetailsRaw'),
            zoomInBtn: document.getElementById('inspectorZoomIn'),
            zoomOutBtn: document.getElementById('inspectorZoomOut'),
            zoomResetBtn: document.getElementById('inspectorZoomReset'),
            copyDiagramBtn: document.getElementById('inspectorCopyDiagram'),
            downloadDiagramBtn: document.getElementById('inspectorDownloadDiagram'),
            downloadTraceBtn: document.getElementById('inspectorDownloadTrace'),
            copyStepBtn: document.getElementById('inspectorCopyStep'),
            downloadStepBtn: document.getElementById('inspectorDownloadStep')
        };
    }

    downloadBlob(content, filename, type = 'application/octet-stream') {
        const blob = content instanceof Blob ? content : new Blob([content], { type });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    flashActionButton(button, label) {
        if (!button) return;
        const original = button.dataset.defaultLabel || button.textContent;
        button.dataset.defaultLabel = original;
        button.textContent = label;
        button.classList.add('is-success');
        setTimeout(() => {
            button.textContent = button.dataset.defaultLabel || original;
            button.classList.remove('is-success');
        }, 1500);
    }

    setExportButtonsEnabled(enabled) {
        const buttons = [
            this.elements.copyDiagramBtn,
            this.elements.downloadDiagramBtn,
            this.elements.downloadTraceBtn
        ];
        buttons.forEach((btn) => {
            if (!btn) return;
            btn.disabled = !enabled;
            if (!enabled) {
                btn.classList.remove('is-success');
            }
        });
        if (!enabled && this.elements.downloadTraceBtn && this.state.currentFlowData) {
            this.elements.downloadTraceBtn.disabled = false;
        }
    }

    syncTraceDownloadAvailability() {
        if (this.elements.downloadTraceBtn) {
            this.elements.downloadTraceBtn.disabled = !this.state.currentFlowData;
        }
    }

    loadPinnedTraces() {
        try {
            if (!window?.localStorage) return [];
            const raw = window.localStorage.getItem('inspectorPinnedTraces');
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch (error) {
            console.warn('Nie udało się odczytać przypiętych śladów:', error);
            return [];
        }
    }

    savePinnedTraces() {
        try {
            if (!window?.localStorage) return;
            window.localStorage.setItem(
                'inspectorPinnedTraces',
                JSON.stringify(this.state.pinnedTraces)
            );
        } catch (error) {
            console.warn('Nie udało się zapisać przypiętych śladów:', error);
        }
    }

    normalizePinnedTrace(trace) {
        if (!trace) return null;
        return {
            id: trace.request_id,
            prompt: trace.prompt || 'Brak opisu',
            status: trace.status || 'UNKNOWN',
            created_at: trace.created_at || null
        };
    }

    isTracePinned(traceId) {
        if (!traceId) return false;
        return this.state.pinnedTraces.some((pin) => pin.id === traceId);
    }

    addPinnedTrace(trace) {
        const payload = this.normalizePinnedTrace(trace);
        if (!payload || this.isTracePinned(payload.id)) return;
        this.state.pinnedTraces = [payload, ...this.state.pinnedTraces];
        this.savePinnedTraces();
    }

    removePinnedTrace(traceId) {
        if (!traceId) return;
        this.state.pinnedTraces = this.state.pinnedTraces.filter((pin) => pin.id !== traceId);
        this.savePinnedTraces();
    }

    togglePinTrace(trace) {
        if (!trace?.request_id) return;
        if (this.isTracePinned(trace.request_id)) {
            this.removePinnedTrace(trace.request_id);
        } else {
            this.addPinnedTrace(trace);
        }
        this.renderPinnedTraces();
        this.renderTraceList();
    }

    clearPinnedTraces() {
        this.state.pinnedTraces = [];
        this.savePinnedTraces();
        this.renderPinnedTraces();
        this.renderTraceList();
    }

    refreshPinnedMetadata() {
        if (!Array.isArray(this.state.pinnedTraces) || this.state.pinnedTraces.length === 0) {
            return;
        }
        const updatedPins = this.state.pinnedTraces.map((pin) => {
            const matching = this.state.traces.find((trace) => trace.request_id === pin.id);
            if (!matching) return pin;
            return {
                ...pin,
                prompt: matching.prompt || pin.prompt,
                status: matching.status || pin.status,
                created_at: matching.created_at || pin.created_at
            };
        });
        this.state.pinnedTraces = updatedPins;
        this.savePinnedTraces();
        this.renderPinnedTraces();
    }

    renderPinnedTraces() {
        const container = this.elements.pinnedContainer;
        const list = this.elements.pinnedList;
        if (!container || !list) return;

        list.innerHTML = '';
        if (!this.state.pinnedTraces.length) {
            container.classList.add('is-hidden');
            const empty = document.createElement('p');
            empty.className = 'inspector-pinned-empty';
            empty.textContent = 'Brak przypiętych śladów';
            list.appendChild(empty);
            this.updatePinnedCount();
            return;
        }

        container.classList.remove('is-hidden');
        this.state.pinnedTraces.forEach((pin) => {
            const chip = document.createElement('div');
            chip.className = 'inspector-pin-chip';
            chip.tabIndex = 0;
            chip.setAttribute('role', 'button');
            chip.setAttribute('aria-label', `Przejdź do śladu ${pin.id}`);
            chip.addEventListener('click', () => this.selectTrace(pin.id));
            chip.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    this.selectTrace(pin.id);
                }
            });

            const labels = document.createElement('div');
            labels.className = 'inspector-pin-chip__labels';
            const idSpan = document.createElement('span');
            idSpan.className = 'inspector-pin-chip__id';
            idSpan.textContent = `${pin.id.slice(0, 8)}...`;
            const descSpan = document.createElement('span');
            descSpan.className = 'inspector-pin-chip__desc';
            descSpan.textContent = pin.prompt || 'Brak opisu';
            labels.appendChild(idSpan);
            labels.appendChild(descSpan);

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'inspector-pin-chip__remove';
            removeBtn.setAttribute('aria-label', `Odepnij ślad ${pin.id}`);
            removeBtn.textContent = '×';
            removeBtn.addEventListener('click', (event) => {
                event.stopPropagation();
                this.removePinnedTrace(pin.id);
                this.renderPinnedTraces();
                this.renderTraceList();
            });

            chip.appendChild(labels);
            chip.appendChild(removeBtn);
            list.appendChild(chip);
        });
        this.updatePinnedCount();
    }

    syncStepExportAvailability() {
        const hasStep = !!this.state.selectedStep;
        if (this.elements.copyStepBtn) {
            this.elements.copyStepBtn.disabled = !hasStep;
        }
        if (this.elements.downloadStepBtn) {
            this.elements.downloadStepBtn.disabled = !hasStep;
        }
    }

    async copySelectedStepJson() {
        if (!this.state.selectedStep) return;
        const payload = JSON.stringify(this.state.selectedStep, null, 2);
        let success = false;
        try {
            if (navigator?.clipboard?.writeText) {
                await navigator.clipboard.writeText(payload);
                success = true;
            }
        } catch (error) {
            console.warn('Clipboard API error:', error);
        }

        if (!success) {
            const textarea = document.createElement('textarea');
            textarea.value = payload;
            textarea.setAttribute('readonly', '');
            textarea.style.position = 'absolute';
            textarea.style.left = '-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                success = document.execCommand('copy');
            } catch (error) {
                success = false;
            } finally {
                document.body.removeChild(textarea);
            }
        }

        this.flashActionButton(
            this.elements.copyStepBtn,
            success ? '✅ Skopiowano' : '⚠️ Błąd kopiowania'
        );
    }

    downloadSelectedStepJson() {
        if (!this.state.selectedStep) return;
        const stepLabel =
            this.state.selectedStep?.id ||
            this.state.selectedStep?.name ||
            this.state.selectedStep?.type ||
            'step';
        const safeStep = String(stepLabel).replace(/\s+/g, '-').slice(0, 16);
        const filename = `${this.state.currentTraceId || 'trace'}-${safeStep}.json`;
        this.downloadBlob(
            JSON.stringify(this.state.selectedStep, null, 2),
            filename,
            'application/json'
        );
        this.flashActionButton(this.elements.downloadStepBtn, '⬇️ Zapisano');
    }

    async copyMermaidCode() {
        if (!this.state.lastMermaidCode) return;
        let success = false;
        try {
            if (navigator?.clipboard?.writeText) {
                await navigator.clipboard.writeText(this.state.lastMermaidCode);
                success = true;
            }
        } catch (error) {
            console.warn('Clipboard API error:', error);
        }

        if (!success) {
            const textarea = document.createElement('textarea');
            textarea.value = this.state.lastMermaidCode;
            textarea.setAttribute('readonly', '');
            textarea.style.position = 'absolute';
            textarea.style.left = '-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                success = document.execCommand('copy');
            } catch (error) {
                success = false;
            } finally {
                document.body.removeChild(textarea);
            }
        }

        this.flashActionButton(
            this.elements.copyDiagramBtn,
            success ? '✅ Skopiowano' : '⚠️ Błąd'
        );
    }

    getDiagramDimensions(svg) {
        if (!svg) return { width: 0, height: 0 };
        const viewBox = svg.viewBox && svg.viewBox.baseVal;
        if (viewBox && viewBox.width && viewBox.height) {
            return { width: viewBox.width, height: viewBox.height };
        }
        const rect = svg.getBoundingClientRect();
        return {
            width: rect.width || svg.clientWidth || 1200,
            height: rect.height || svg.clientHeight || 600
        };
    }

    downloadDiagramPng() {
        const svg = this.state.lastDiagramSvg || this.elements.diagramContainer?.querySelector('svg');
        if (!svg) return;
        const serializer = new XMLSerializer();
        const svgString = serializer.serializeToString(svg);
        const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
        const image = new Image();
        image.crossOrigin = 'anonymous';
        const { width, height } = this.getDiagramDimensions(svg);
        const scale = Math.max(window.devicePixelRatio || 1, 2);
        const url = URL.createObjectURL(svgBlob);

        image.onload = () => {
            const canvas = document.createElement('canvas');
            canvas.width = width * scale;
            canvas.height = height * scale;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#020617';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
            URL.revokeObjectURL(url);

            canvas.toBlob((blob) => {
                if (blob) {
                    this.downloadBlob(
                        blob,
                        `inspector-${(this.state.currentTraceId || 'diagram').slice(0, 12)}.png`
                    );
                    this.flashActionButton(this.elements.downloadDiagramBtn, '✅ Zapisano');
                } else {
                    this.downloadBlob(
                        svgBlob,
                        `inspector-${(this.state.currentTraceId || 'diagram').slice(0, 12)}.svg`
                    );
                    this.flashActionButton(this.elements.downloadDiagramBtn, '⬇️ SVG');
                }
            }, 'image/png');
        };

        image.onerror = () => {
            URL.revokeObjectURL(url);
            this.downloadBlob(
                svgBlob,
                `inspector-${(this.state.currentTraceId || 'diagram').slice(0, 12)}.svg`
            );
            this.flashActionButton(this.elements.downloadDiagramBtn, '⬇️ SVG');
        };

        image.src = url;
    }

    downloadTraceJson() {
        if (!this.state.currentFlowData) return;
        const content = JSON.stringify(this.state.currentFlowData, null, 2);
        this.downloadBlob(
            content,
            `trace-${(this.state.currentTraceId || 'detail').slice(0, 16)}.json`,
            'application/json'
        );
        this.flashActionButton(this.elements.downloadTraceBtn, '✅ JSON');
    }

    bindEvents() {
        this.elements.filterButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const status = button.dataset.status || 'all';
                this.setFilter(status);
            });
        });

        if (this.elements.searchInput) {
            this.elements.searchInput.addEventListener('input', (event) => {
                this.state.searchQuery = (event.target.value || '').trim();
                this.persistUIPreferences({ searchQuery: this.state.searchQuery });
                this.renderTraceList();
            });
        }

        if (this.elements.autoToggle) {
            this.elements.autoToggle.addEventListener('change', (event) => {
                this.state.autoRefresh = event.target.checked;
                this.persistUIPreferences({ autoRefresh: this.state.autoRefresh });
                if (this.state.autoRefresh) {
                    this.startAutoRefresh(true);
                } else {
                    this.stopAutoRefresh();
                }
            });
        }

        if (this.elements.refreshBtn) {
            this.elements.refreshBtn.addEventListener('click', () => {
                this.loadTraces({ showLoading: true });
            });
        }

        if (this.elements.clearPinnedBtn) {
            this.elements.clearPinnedBtn.addEventListener('click', () => this.clearPinnedTraces());
        }

        if (this.elements.zoomInBtn) {
            this.elements.zoomInBtn.addEventListener('click', () => this.zoomIn());
        }

        if (this.elements.zoomOutBtn) {
            this.elements.zoomOutBtn.addEventListener('click', () => this.zoomOut());
        }

        if (this.elements.zoomResetBtn) {
            this.elements.zoomResetBtn.addEventListener('click', () => this.resetZoom());
        }

        if (this.elements.copyDiagramBtn) {
            this.elements.copyDiagramBtn.addEventListener('click', () => this.copyMermaidCode());
        }

        if (this.elements.downloadDiagramBtn) {
            this.elements.downloadDiagramBtn.addEventListener('click', () => this.downloadDiagramPng());
        }

        if (this.elements.downloadTraceBtn) {
            this.elements.downloadTraceBtn.addEventListener('click', () => this.downloadTraceJson());
        }

        if (this.elements.copyStepBtn) {
            this.elements.copyStepBtn.addEventListener('click', () => this.copySelectedStepJson());
        }

        if (this.elements.downloadStepBtn) {
            this.elements.downloadStepBtn.addEventListener('click', () => this.downloadSelectedStepJson());
        }

        window.addEventListener('beforeunload', () => this.stopAutoRefresh());
    }

    init() {
        this.loadTraces({ showLoading: true });
        this.startAutoRefresh();
    }

    async loadTraces(options = {}) {
        const { showLoading = false } = options;

        if (showLoading) {
            this.state.loading = true;
            this.renderTraceList();
        }

        this.state.traceError = null;

        try {
            const response = await fetch('/api/v1/history/requests?limit=50');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const traces = await response.json();
            this.state.traces = Array.isArray(traces) ? traces : [];
            this.state.lastUpdated = new Date();
            this.updateLastUpdated();
            this.refreshPinnedMetadata();
            this.updateTraceStats();
        } catch (error) {
            console.error('❌ Error loading traces:', error);
            this.state.traces = [];
            this.state.traceError = 'Błąd ładowania śladów';
            this.updateTraceStats();
        } finally {
            if (showLoading) {
                this.state.loading = false;
            }
            this.renderTraceList();
        }
    }

    getFilteredTraces() {
        const query = (this.state.searchQuery || '').toLowerCase();
        return this.state.traces.filter((trace) => {
            const status = (trace.status || '').toLowerCase();
            const matchesStatus =
                this.state.filterStatus === 'all' ? true : status === this.state.filterStatus;
            if (!matchesStatus) {
                return false;
            }
            if (!query) {
                return true;
            }
            const prompt = (trace.prompt || '').toLowerCase();
            const id = (trace.request_id || '').toLowerCase();
            return prompt.includes(query) || id.includes(query);
        });
    }

    renderTraceList() {
        const list = this.elements.traceList;
        if (!list) return;

        list.innerHTML = '';

        if (this.state.loading) {
            list.innerHTML = `
                <li class="inspector-loading">
                    <div class="inspector-spinner"></div>
                    <p>Ładowanie...</p>
                </li>
            `;
            return;
        }

        if (this.state.traceError) {
            list.innerHTML = `
                <li class="empty-state">
                    <p>${this.state.traceError}</p>
                </li>
            `;
            return;
        }

        const traces = this.getFilteredTraces();
        if (traces.length === 0) {
            list.innerHTML = `
                <li class="empty-state">
                    <p>Brak śladów w historii</p>
                </li>
            `;
            this.updateTraceStats();
            return;
        }

        traces.forEach((trace) => {
            const item = this.createTraceListItem(trace);
            list.appendChild(item);
        });
        this.updateTraceStats();
    }

    createTraceListItem(trace) {
        const item = document.createElement('li');
        const statusClass = (trace.status || '').toLowerCase();
        item.className = `inspector-trace-item status-${statusClass}`;
        item.dataset.traceId = trace.request_id;
        item.tabIndex = 0;
        item.setAttribute('role', 'button');
        item.setAttribute('aria-label', `Analizuj ślad ${trace.request_id}`);

        if (trace.request_id === this.state.currentTraceId) {
            item.classList.add('selected');
        }
        if (this.isTracePinned(trace.request_id)) {
            item.classList.add('is-pinned');
        }

        const header = document.createElement('div');
        header.className = 'inspector-trace-header';
        const headerContent = document.createElement('div');
        headerContent.className = 'inspector-trace-header-content';

        const idSpan = document.createElement('span');
        idSpan.className = 'inspector-trace-id';
        idSpan.textContent = `${trace.request_id?.slice(0, 8) || '---'}...`;

        const statusSpan = document.createElement('span');
        statusSpan.className = `inspector-trace-status status-${statusClass}`;
        statusSpan.textContent = trace.status || 'UNKNOWN';

        headerContent.appendChild(idSpan);
        headerContent.appendChild(statusSpan);

        const actions = document.createElement('div');
        actions.className = 'inspector-trace-actions';
        const pinBtn = document.createElement('button');
        pinBtn.type = 'button';
        pinBtn.className = 'inspector-pin-btn';
        const pinned = this.isTracePinned(trace.request_id);
        if (pinned) {
            pinBtn.classList.add('is-active');
        }
        pinBtn.innerHTML = pinned ? '★' : '☆';
        pinBtn.title = pinned ? 'Odepnij ślad' : 'Przypnij ślad';
        pinBtn.setAttribute(
            'aria-label',
            `${pinned ? 'Odepnij' : 'Przypnij'} ślad ${trace.request_id}`
        );
        pinBtn.addEventListener('click', (event) => {
            event.stopPropagation();
            this.togglePinTrace(trace);
        });
        actions.appendChild(pinBtn);

        header.appendChild(headerContent);
        header.appendChild(actions);

        const promptDiv = document.createElement('div');
        promptDiv.className = 'inspector-trace-prompt';
        promptDiv.textContent = trace.prompt || 'Brak opisu';

        const timeDiv = document.createElement('div');
        timeDiv.className = 'inspector-trace-time';
        timeDiv.textContent = this.formatTimestamp(trace.created_at);

        item.appendChild(header);
        item.appendChild(promptDiv);
        item.appendChild(timeDiv);

        item.addEventListener('click', () => this.selectTrace(trace.request_id));
        item.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                this.selectTrace(trace.request_id);
            }
        });

        return item;
    }

    formatTimestamp(value) {
        if (!value) {
            return '-';
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return '-';
        }
        return date.toLocaleString('pl-PL');
    }

    setFilter(status) {
        if (this.state.filterStatus === status) {
            return;
        }
        this.state.filterStatus = status;
        this.updateFilterButtons();
        this.persistUIPreferences({ filterStatus: this.state.filterStatus });
        this.renderTraceList();
    }

    updateFilterButtons() {
        this.elements.filterButtons.forEach((button) => {
            button.classList.toggle('active', button.dataset.status === this.state.filterStatus);
        });
    }

    startAutoRefresh(immediate = false) {
        this.stopAutoRefresh();
        if (!this.state.autoRefresh) {
            return;
        }
        if (immediate) {
            this.loadTraces();
        }
        this.autoRefreshTimer = setInterval(() => {
            if (this.state.autoRefresh) {
                this.loadTraces();
            }
        }, 5000);
    }

    stopAutoRefresh() {
        if (this.autoRefreshTimer) {
            clearInterval(this.autoRefreshTimer);
            this.autoRefreshTimer = null;
        }
    }

    async selectTrace(traceId) {
        if (!traceId) return;
        if (this.state.currentTraceId === traceId && this.state.currentFlowData) {
            this.highlightSelectedTrace();
            return;
        }

        this.state.currentTraceId = traceId;
        this.state.currentFlowData = null;
        this.syncTraceDownloadAvailability();
        this.setSelectedStep(null);
        this.highlightSelectedTrace();
        this.showDiagramPlaceholder('Ładowanie śladu...', 'loading');
        this.clearDiagram();

        try {
            const response = await fetch(`/api/v1/flow/${traceId}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            this.state.currentFlowData = await response.json();
            this.syncTraceDownloadAvailability();
            await this.renderDiagram();
        } catch (error) {
            console.error('❌ Error loading flow data:', error);
            this.showDiagramPlaceholder('Nie udało się załadować śladu.');
            this.setExportButtonsEnabled(false);
            this.state.currentFlowData = null;
            this.syncTraceDownloadAvailability();
        }
    }

    highlightSelectedTrace() {
        if (!this.elements.traceList) return;
        const items = this.elements.traceList.querySelectorAll('.inspector-trace-item');
        items.forEach((item) => {
            item.classList.toggle(
                'selected',
                item.dataset.traceId === this.state.currentTraceId
            );
        });
    }

    setSelectedStep(step) {
        this.state.selectedStep = step;
        this.renderStepDetails();
        this.syncStepExportAvailability();
    }

    renderStepDetails() {
        if (!this.elements.detailsPlaceholder || !this.elements.detailsRaw) return;
        if (!this.state.selectedStep) {
            this.elements.detailsPlaceholder.classList.remove('is-hidden');
            this.elements.detailsRaw.classList.add('is-hidden');
            this.elements.detailsRaw.textContent = '';
            return;
        }

        this.elements.detailsPlaceholder.classList.add('is-hidden');
        this.elements.detailsRaw.classList.remove('is-hidden');
        this.elements.detailsRaw.textContent = JSON.stringify(this.state.selectedStep, null, 2);
    }

    showDiagramPlaceholder(message, variant = 'info') {
        if (!this.elements.diagramPlaceholder) return;
        const messageNode = this.elements.diagramPlaceholder.querySelector('p');
        if (messageNode) {
            messageNode.textContent = message || '👈 Wybierz ślad z listy';
        }
        this.elements.diagramPlaceholder.classList.remove('is-hidden');
    }

    hideDiagramPlaceholder() {
        if (!this.elements.diagramPlaceholder) return;
        this.elements.diagramPlaceholder.classList.add('is-hidden');
    }

    clearDiagram() {
        if (this.elements.diagramContainer) {
            this.elements.diagramContainer.innerHTML = '';
        }
        if (panZoomInstance) {
            panZoomInstance.destroy();
            panZoomInstance = null;
        }
        this.state.lastMermaidCode = '';
        this.state.lastDiagramSvg = null;
        this.setExportButtonsEnabled(false);
    }

    generateMermaidDiagram(flowData) {
        const lines = ['sequenceDiagram', '    autonumber'];
        const participants = new Set(['User']);

        for (const step of flowData.steps || []) {
            if (step.component !== 'DecisionGate') {
                const safeComponent = sanitizeMermaidText(step.component);
                if (safeComponent) {
                    participants.add(safeComponent);
                }
            }
        }

        Array.from(participants)
            .sort()
            .forEach((participant) => {
                if (participant !== 'User') {
                    lines.push(`    participant ${participant}`);
                }
            });

        lines.push('');
        const safePrompt = sanitizeMermaidText(flowData.prompt);
        const promptText = safePrompt.length > 50 ? `${safePrompt.slice(0, 50)}...` : safePrompt;
        lines.push(`    User->>Orchestrator: ${promptText}`);

        let lastComponent = 'Orchestrator';

        (flowData.steps || []).forEach((step) => {
            if (step.is_decision_gate) {
                const safeDetails = sanitizeMermaidText(step.details || '');
                const safeAction = sanitizeMermaidText(step.action);
                const detailText =
                    safeDetails.length > 40 ? `${safeDetails.slice(0, 40)}...` : safeDetails;
                lines.push(`    rect rgb(255, 245, 224)`);
                lines.push(`        Note over Orchestrator: 🔀 ${safeAction}<br/>${detailText}`);
                lines.push(`    end`);
            } else {
                const safeComponent = sanitizeMermaidText(step.component);
                const safeAction = sanitizeMermaidText(step.action);
                const safeDetails = sanitizeMermaidText(step.details || '');
                const arrow = step.status === 'ok' ? '->>' : '--x';
                const detailText =
                    safeDetails.length > 40 ? `${safeDetails.slice(0, 40)}...` : safeDetails;
                const message = detailText ? `${safeAction}: ${detailText}` : safeAction;

                if (safeComponent && safeComponent !== lastComponent) {
                    lines.push(`    ${lastComponent}${arrow}${safeComponent}: ${message}`);
                    lastComponent = safeComponent;
                } else if (safeComponent) {
                    lines.push(`    Note right of ${safeComponent}: ${message}`);
                }
            }
        });

        if (flowData.status === 'COMPLETED') {
            lines.push(`    ${lastComponent}->>User: ✅ Task completed`);
        } else if (flowData.status === 'FAILED') {
            lines.push(`    ${lastComponent}--xUser: ❌ Task failed`);
        } else if (flowData.status === 'PROCESSING') {
            lines.push(`    Note over ${lastComponent}: ⏳ Processing...`);
        }

        return lines.join('\n');
    }

    async renderDiagram() {
        if (!this.state.currentFlowData) return;

        if (typeof mermaid === 'undefined') {
            console.error('❌ Mermaid.js library not available');
            this.showDiagramPlaceholder('Brak biblioteki Mermaid.js');
            return;
        }

        const container = this.elements.diagramContainer;
        if (!container) return;

        const mermaidCode = this.generateMermaidDiagram(this.state.currentFlowData);
        this.state.lastMermaidCode = mermaidCode;
        container.innerHTML = '';

        try {
            const { svg } = await mermaid.render('inspectorDiagram', mermaidCode);
            container.innerHTML = svg;
            this.hydrateDiagram(container);
            this.initPanZoom();
            this.hideDiagramPlaceholder();
            this.state.lastDiagramSvg = container.querySelector('svg');
            this.setExportButtonsEnabled(true);
            this.syncTraceDownloadAvailability();
        } catch (error) {
            console.error('❌ Error rendering Mermaid diagram:', error);
            container.innerHTML = `
                <div class="inspector-diagram-error">
                    <p class="inspector-diagram-error__title">Błąd renderowania diagramu</p>
                    <pre class="inspector-diagram-error__details">${mermaidCode}</pre>
                </div>
            `;
            this.setExportButtonsEnabled(false);
            this.syncTraceDownloadAvailability();
        }
    }

    hydrateDiagram(container) {
        const svg = container.querySelector('svg');
        if (!svg) return;

        const actors = svg.querySelectorAll('.actor');
        const messages = svg.querySelectorAll('.messageLine0, .messageLine1');
        const notes = svg.querySelectorAll('.note');

        const attachHandler = (elements, stepResolver) => {
            elements.forEach((element, index) => {
                element.classList.add('inspector-diagram-clickable');
                element.addEventListener('click', (event) => {
                    event.stopPropagation();
                    const step = stepResolver(element, index);
                    if (step) {
                        this.setSelectedStep(step);
                    }
                });
                element.addEventListener('mouseenter', () => element.classList.add('is-hovered'));
                element.addEventListener('mouseleave', () => element.classList.remove('is-hovered'));
            });
        };

        attachHandler(messages, (_element, index) => {
            return this.state.currentFlowData.steps?.[index];
        });

        attachHandler(notes, (_element, index) => {
            return this.state.currentFlowData.steps?.[index];
        });

        actors.forEach((actor) => {
            actor.classList.add('inspector-diagram-clickable');
            actor.addEventListener('click', (event) => {
                event.stopPropagation();
                const actorName = actor.querySelector('text')?.textContent || 'Unknown';
                this.setSelectedStep({
                    component: actorName,
                    action: 'Actor info',
                    details: `Uczestnik: ${actorName}`,
                    timestamp: new Date().toISOString()
                });
            });
            actor.addEventListener('mouseenter', () => actor.classList.add('is-hovered'));
            actor.addEventListener('mouseleave', () => actor.classList.remove('is-hovered'));
        });
    }

    initPanZoom() {
        if (typeof svgPanZoom === 'undefined') {
            console.error('❌ svg-pan-zoom library not available');
            return;
        }

        if (panZoomInstance) {
            panZoomInstance.destroy();
            panZoomInstance = null;
        }

        const svg = this.elements.diagramContainer?.querySelector('svg');
        if (!svg) return;

        try {
            panZoomInstance = svgPanZoom(svg, {
                zoomEnabled: true,
                controlIconsEnabled: false,
                fit: true,
                center: true,
                minZoom: 0.1,
                maxZoom: 10,
                zoomScaleSensitivity: 0.3
            });
        } catch (error) {
            console.error('❌ Error initializing pan-zoom:', error);
        }
    }

    zoomIn() {
        if (panZoomInstance) {
            panZoomInstance.zoomIn();
        }
    }

    zoomOut() {
        if (panZoomInstance) {
            panZoomInstance.zoomOut();
        }
    }

    resetZoom() {
        if (panZoomInstance) {
            panZoomInstance.reset();
        }
    }

    updateLastUpdated() {
        if (!this.elements.lastUpdatedLabel) return;
        this.elements.lastUpdatedLabel.textContent = this.state.lastUpdated
            ? this.state.lastUpdated.toLocaleString('pl-PL')
            : '-';
    }

    updateTraceStats() {
        if (!this.elements.traceStatsLabel) return;
        const filteredCount = this.getFilteredTraces().length;
        const totalCount = this.state.traces.length;
        this.elements.traceStatsLabel.textContent = `${filteredCount} / ${totalCount}`;
    }

    updatePinnedCount() {
        if (!this.elements.pinnedCountLabel) return;
        this.elements.pinnedCountLabel.textContent = String(this.state.pinnedTraces.length);
    }

    loadUIPreferences() {
        const defaults = { ...INSPECTOR_PREFS_DEFAULTS };
        try {
            if (!window?.localStorage) {
                return defaults;
            }
            const raw = window.localStorage.getItem(INSPECTOR_PREFS_KEY);
            if (!raw) {
                return defaults;
            }
            const parsed = JSON.parse(raw);
            return {
                filterStatus: parsed.filterStatus || defaults.filterStatus,
                searchQuery: parsed.searchQuery || defaults.searchQuery,
                autoRefresh:
                    parsed.autoRefresh === undefined ? defaults.autoRefresh : !!parsed.autoRefresh
            };
        } catch (error) {
            console.warn('Nie udało się wczytać preferencji Inspektora:', error);
            return defaults;
        }
    }

    saveUIPreferences() {
        try {
            if (!window?.localStorage) {
                return;
            }
            window.localStorage.setItem(INSPECTOR_PREFS_KEY, JSON.stringify(this.preferences));
        } catch (error) {
            console.warn('Nie udało się zapisać preferencji Inspektora:', error);
        }
    }

    persistUIPreferences(partial) {
        this.preferences = {
            ...this.preferences,
            ...partial
        };
        this.saveUIPreferences();
    }

    applyUIPreferencesToControls() {
        if (this.elements.searchInput) {
            this.elements.searchInput.value = this.state.searchQuery || '';
        }
        if (this.elements.autoToggle) {
            this.elements.autoToggle.checked = !!this.state.autoRefresh;
        }
        this.updateFilterButtons();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (typeof mermaid === 'undefined') {
        console.error('❌ Mermaid.js not loaded from CDN');
        return;
    }
    if (typeof svgPanZoom === 'undefined') {
        console.error('❌ svg-pan-zoom not loaded from CDN');
    }
    new InspectorApp();
});
