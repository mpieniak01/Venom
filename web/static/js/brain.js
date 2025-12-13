const BRAIN_FILTER_MAP = {
    agents: 'agent',
    files: 'file',
    memories: 'memory',
    functions: 'function',
    classes: 'class'
};

class BrainGraph {
    constructor() {
        this.cy = null;
        this.graphData = null;
        this.isLoading = false;
        this.autoRefreshTimer = null;
        this.AUTO_REFRESH_INTERVAL = 60000;
        this.state = {
            filters: {
                agents: true,
                files: true,
                memories: true,
                functions: true,
                classes: true
            },
            searchQuery: '',
            autoRefresh: true,
            lastUpdated: null
        };

        this.preferences = this.loadPreferences();
        this.applyPreferencesToState();
        this.elements = this.cacheElements();
        this.applyStateToControls();
        this.bindEvents();
        this.initGraph();
    }

    cacheElements() {
        return {
            graphContainer: document.getElementById('cy'),
            statNodes: document.getElementById('brainStatNodes'),
            statEdges: document.getElementById('brainStatEdges'),
            nodesMeta: document.getElementById('brainNodesMeta'),
            edgesMeta: document.getElementById('brainEdgesMeta'),
            visibleNodes: document.getElementById('brainVisibleNodes'),
            visibleEdges: document.getElementById('brainVisibleEdges'),
            totalNodesLabel: document.getElementById('brainTotalNodes'),
            totalEdgesLabel: document.getElementById('brainTotalEdges'),
            filterSummary: document.getElementById('brainFilterSummary'),
            filterDetails: document.getElementById('brainFilterDetails'),
            statusLabel: document.getElementById('brainStatus'),
            lastUpdatedLabel: document.getElementById('brainLastUpdated'),
            filterInputs: document.querySelectorAll('.brain-filter-toggle input[type="checkbox"]'),
            searchInput: document.getElementById('brainSearchInput'),
            autoToggle: document.getElementById('brainAutoRefreshToggle'),
            refreshBtn: document.getElementById('brainRefreshBtn'),
            alertBox: document.getElementById('brainAlert'),
            loadingOverlay: document.getElementById('loadingOverlay'),
            detailPanel: document.getElementById('nodeDetails'),
            closeDetailsBtn: document.getElementById('closeNodeDetails'),
            detailTitle: document.getElementById('nodeDetailsLabel'),
            detailIcon: document.getElementById('nodeDetailsIcon'),
            detailContent: document.getElementById('nodeDetailsContent'),
            exportJsonBtn: document.getElementById('brainExportJson'),
            exportPngBtn: document.getElementById('brainExportPng')
        };
    }

    applyStateToControls() {
        this.elements.filterInputs.forEach((input) => {
            const filterKey = input.dataset.filter;
            if (!filterKey) return;
            input.checked = !!this.state.filters[filterKey];
        });

        if (this.elements.searchInput) {
            this.elements.searchInput.value = this.state.searchQuery || '';
        }

        if (this.elements.autoToggle) {
            this.elements.autoToggle.checked = this.state.autoRefresh;
        }

        this.updateFilterSummary();

        this.setExportButtonsEnabled(false);
    }

    loadPreferences() {
        const defaults = {
            filters: {
                agents: true,
                files: true,
                memories: true,
                functions: true,
                classes: true
            },
            searchQuery: '',
            autoRefresh: true
        };

        try {
            if (!window?.localStorage) return defaults;
            const raw = window.localStorage.getItem('brainPreferences');
            if (!raw) return defaults;
            const parsed = JSON.parse(raw);
            return {
                filters: { ...defaults.filters, ...(parsed?.filters || {}) },
                searchQuery: parsed?.searchQuery ?? defaults.searchQuery,
                autoRefresh:
                    parsed?.autoRefresh === undefined ? defaults.autoRefresh : !!parsed.autoRefresh
            };
        } catch (error) {
            console.warn('Nie można wczytać preferencji Brain:', error);
            return defaults;
        }
    }

    savePreferences() {
        try {
            if (!window?.localStorage) return;
            const payload = {
                filters: this.state.filters,
                searchQuery: this.state.searchQuery,
                autoRefresh: this.state.autoRefresh
            };
            window.localStorage.setItem('brainPreferences', JSON.stringify(payload));
        } catch (error) {
            console.warn('Nie można zapisać preferencji Brain:', error);
        }
    }

    applyPreferencesToState() {
        const prefs = this.preferences || {};
        if (prefs.filters) {
            this.state.filters = { ...this.state.filters, ...prefs.filters };
        }
        if (typeof prefs.searchQuery === 'string') {
            this.state.searchQuery = prefs.searchQuery;
        }
        if (typeof prefs.autoRefresh === 'boolean') {
            this.state.autoRefresh = prefs.autoRefresh;
        }
    }

    setExportButtonsEnabled(enabled) {
        [this.elements.exportJsonBtn, this.elements.exportPngBtn].forEach((btn) => {
            if (!btn) return;
            btn.disabled = !enabled;
            if (!enabled) btn.classList.remove('is-success');
        });
    }

    flashExportButton(button, label) {
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

    bindEvents() {
        this.elements.filterInputs.forEach((input) => {
            const filterKey = input.dataset.filter;
            if (!filterKey) return;
            this.state.filters[filterKey] = input.checked;
            input.addEventListener('change', (event) => {
                this.state.filters[filterKey] = event.target.checked;
                this.applyFilters();
                this.updateFilterSummary();
                this.savePreferences();
            });
        });

        if (this.elements.searchInput) {
            this.elements.searchInput.addEventListener('input', (event) => {
                this.state.searchQuery = (event.target.value || '').trim();
                this.applySearch();
                this.savePreferences();
            });
        }

        if (this.elements.autoToggle) {
            this.state.autoRefresh = this.elements.autoToggle.checked;
            this.elements.autoToggle.addEventListener('change', (event) => {
                this.state.autoRefresh = event.target.checked;
                if (this.state.autoRefresh) {
                    this.startAutoRefresh(true);
                } else {
                    this.stopAutoRefresh();
                }
                this.savePreferences();
            });
        }

        if (this.elements.refreshBtn) {
            this.elements.refreshBtn.addEventListener('click', () => {
                this.reloadGraph({ showLoading: true });
            });
        }

        if (this.elements.exportJsonBtn) {
            this.elements.exportJsonBtn.addEventListener('click', () => this.exportGraphJson());
        }

        if (this.elements.exportPngBtn) {
            this.elements.exportPngBtn.addEventListener('click', () => this.exportGraphPng());
        }

        if (this.elements.closeDetailsBtn) {
            this.elements.closeDetailsBtn.addEventListener('click', () => {
                this.hideNodeDetails();
            });
        }

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                this.hideNodeDetails();
            }
        });
    }

    async initGraph() {
        await this.reloadGraph({ showLoading: true });
        this.startAutoRefresh();
    }

    async reloadGraph(options = {}) {
        if (this.isLoading) {
            return;
        }

        const { showLoading = false } = options;
        this.isLoading = true;

        if (showLoading) {
            this.showLoading();
        }

        try {
            const response = await fetch('/api/v1/knowledge/graph');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            if (data.status !== 'success') {
                throw new Error(data.message || 'Błąd podczas ładowania danych grafu');
            }

            this.graphData = data;
            this.renderGraph(data.elements);
            this.updateStats(data.stats);
            this.updateStatus('Gotowy');
            this.state.lastUpdated = new Date();
            this.updateLastUpdatedLabel();
            this.applyFilters();
            this.applySearch();
            this.showAlert();
            this.setExportButtonsEnabled(true);
        } catch (error) {
            console.error('Błąd podczas ładowania grafu:', error);
            this.updateStatus('Błąd');
            this.showAlert('Nie udało się załadować grafu wiedzy. Spróbuj ponownie później.');
            this.setExportButtonsEnabled(false);
        } finally {
            this.isLoading = false;
            if (showLoading) {
                this.hideLoading();
            }
        }
    }

    renderGraph(elements = []) {
        if (!this.elements.graphContainer) return;
        if (this.cy) {
            this.cy.destroy();
        }

        this.cy = cytoscape({
            container: this.elements.graphContainer,
            elements,
            style: [
                {
                    selector: 'node',
                    style: {
                        'label': 'data(label)',
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'font-size': '12px',
                        'font-weight': 'bold',
                        'text-outline-color': '#0f172a',
                        'text-outline-width': 2,
                        'color': '#e2e8f0',
                        'width': 60,
                        'height': 60,
                        'border-width': 3,
                        'border-color': '#64748b',
                        'background-color': '#1e293b'
                    }
                },
                {
                    selector: 'node[type="agent"]',
                    style: {
                        'shape': 'diamond',
                        'background-color': '#a855f7',
                        'border-color': '#c084fc',
                        'width': 80,
                        'height': 80
                    }
                },
                {
                    selector: 'node[type="file"]',
                    style: {
                        'shape': 'square',
                        'background-color': '#3b82f6',
                        'border-color': '#60a5fa',
                        'width': 60,
                        'height': 60
                    }
                },
                {
                    selector: 'node[type="memory"]',
                    style: {
                        'shape': 'ellipse',
                        'background-color': '#10b981',
                        'border-color': '#34d399',
                        'width': 70,
                        'height': 70
                    }
                },
                {
                    selector: 'node[type="function"]',
                    style: {
                        'shape': 'round-rectangle',
                        'background-color': '#f59e0b',
                        'border-color': '#fbbf24',
                        'width': 55,
                        'height': 55
                    }
                },
                {
                    selector: 'node[type="class"]',
                    style: {
                        'shape': 'hexagon',
                        'background-color': '#ec4899',
                        'border-color': '#f472b6',
                        'width': 65,
                        'height': 65
                    }
                },
                {
                    selector: 'edge',
                    style: {
                        'width': 2,
                        'line-color': '#475569',
                        'target-arrow-color': '#475569',
                        'target-arrow-shape': 'triangle',
                        'curve-style': 'bezier',
                        'arrow-scale': 1.2,
                        'opacity': 0.6
                    }
                },
                {
                    selector: 'edge[type="DELEGATES"]',
                    style: {
                        'line-color': '#a855f7',
                        'target-arrow-color': '#a855f7'
                    }
                },
                {
                    selector: 'edge[type="EDITS"]',
                    style: {
                        'line-color': '#3b82f6',
                        'target-arrow-color': '#3b82f6'
                    }
                },
                {
                    selector: 'edge[type="LEARNS"]',
                    style: {
                        'line-color': '#10b981',
                        'target-arrow-color': '#10b981'
                    }
                },
                {
                    selector: 'edge[type="IMPORTS"]',
                    style: {
                        'line-color': '#f59e0b',
                        'target-arrow-color': '#f59e0b'
                    }
                },
                {
                    selector: 'node.highlighted',
                    style: {
                        'border-width': 5,
                        'border-color': '#fbbf24',
                        'z-index': 9999
                    }
                },
                {
                    selector: 'node.neighbor',
                    style: {
                        'opacity': 1,
                        'border-color': '#fbbf24'
                    }
                },
                {
                    selector: 'edge.highlighted',
                    style: {
                        'width': 4,
                        'opacity': 1,
                        'z-index': 9999
                    }
                },
                {
                    selector: 'node.faded',
                    style: {
                        'opacity': 0.3
                    }
                },
                {
                    selector: 'edge.faded',
                    style: {
                        'opacity': 0.1
                    }
                },
                {
                    selector: 'node.search-match',
                    style: {
                        'border-color': '#22d3ee',
                        'border-width': 6,
                        'shadow-blur': 20,
                        'shadow-color': '#22d3ee',
                        'shadow-opacity': 0.8
                    }
                },
                {
                    selector: 'node.search-dimmed',
                    style: {
                        'opacity': 0.2
                    }
                },
                {
                    selector: 'edge.search-dimmed',
                    style: {
                        'opacity': 0.15
                    }
                }
            ],
            layout: {
                name: 'cose',
                animate: true,
                animationDuration: 1000,
                animationEasing: 'ease-out',
                nodeRepulsion: 8000,
                idealEdgeLength: 100,
                edgeElasticity: 100,
                nestingFactor: 1.2,
                gravity: 1,
                numIter: 1000,
                initialTemp: 200,
                coolingFactor: 0.95,
                minTemp: 1.0
            },
            minZoom: 0.3,
            maxZoom: 3,
            wheelSensitivity: 0.2
        });

        this.setupEventHandlers();
    }

    setupEventHandlers() {
        if (!this.cy) return;
        this.cy.on('tap', 'node', (evt) => {
            const node = evt.target;
            this.showNodeDetails(node);
            this.highlightNode(node);
        });

        this.cy.on('tap', (evt) => {
            if (evt.target === this.cy) {
                this.hideNodeDetails();
                this.clearHighlights();
            }
        });

        this.cy.on('mouseover', 'node', (evt) => {
            const node = evt.target;
            if (!node.hasClass('highlighted')) {
                this.highlightNode(node, true);
            }
        });

        this.cy.on('mouseout', 'node', (evt) => {
            const node = evt.target;
            if (!node.hasClass('highlighted')) {
                this.clearHighlights();
            }
        });
    }

    highlightNode(node, isHover = false) {
        if (!this.cy) return;
        if (!isHover) {
            this.clearHighlights();
        }
        this.cy.elements().addClass('faded');
        node.removeClass('faded').addClass(isHover ? 'neighbor' : 'highlighted');
        const neighbors = node.neighborhood();
        neighbors.nodes().removeClass('faded').addClass('neighbor');
        neighbors.edges().removeClass('faded').addClass('highlighted');
    }

    clearHighlights() {
        if (!this.cy) return;
        this.cy.elements().removeClass('highlighted neighbor faded');
    }

    showNodeDetails(node) {
        if (!node || !this.elements.detailPanel) return;
        const data = node.data();
        const icons = {
            'agent': '🔷',
            'file': '📄',
            'memory': '💡',
            'function': '⚙️',
            'class': '🔶'
        };

        if (this.elements.detailIcon) {
            this.elements.detailIcon.textContent = icons[data.type] || '📦';
        }
        if (this.elements.detailTitle) {
            this.elements.detailTitle.textContent = data.label || 'Węzeł';
        }

        if (this.elements.detailContent) {
            const escapeHtml = (text) => {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            };

            let html = `
                <div class="brain-detail-row">
                    <div class="brain-detail-label">Typ</div>
                    <div class="brain-detail-value"><code>${escapeHtml(data.type || 'unknown')}</code></div>
                </div>
                <div class="brain-detail-row">
                    <div class="brain-detail-label">ID</div>
                    <div class="brain-detail-value"><code>${escapeHtml(data.id || 'n/a')}</code></div>
                </div>
            `;

            if (data.properties) {
                Object.entries(data.properties).forEach(([key, value]) => {
                    if (['id', 'label', 'type'].includes(key)) {
                        return;
                    }
                    html += `
                        <div class="brain-detail-row">
                            <div class="brain-detail-label">${escapeHtml(key)}</div>
                            <div class="brain-detail-value">${escapeHtml(JSON.stringify(value))}</div>
                        </div>
                    `;
                });
            }

            const edges = node.connectedEdges();
            html += `
                <div class="brain-detail-row">
                    <div class="brain-detail-label">Połączenia</div>
                    <div class="brain-detail-value">${edges.length}</div>
                </div>
            `;

            this.elements.detailContent.innerHTML = html;
        }

        this.elements.detailPanel.classList.add('visible');
    }

    hideNodeDetails() {
        if (this.elements.detailPanel) {
            this.elements.detailPanel.classList.remove('visible');
        }
        this.clearHighlights();
    }

    updateStats(stats = {}) {
        const nodes = stats.nodes ?? 0;
        const edges = stats.edges ?? 0;
        if (this.elements.statNodes) {
            this.elements.statNodes.textContent = nodes;
        }
        if (this.elements.statEdges) {
            this.elements.statEdges.textContent = edges;
        }
        if (this.elements.nodesMeta) {
            this.elements.nodesMeta.textContent = nodes;
        }
        if (this.elements.edgesMeta) {
            this.elements.edgesMeta.textContent = edges;
        }
    }

    updateStatus(statusText) {
        if (this.elements.statusLabel) {
            this.elements.statusLabel.textContent = statusText;
        }
    }

    updateLastUpdatedLabel() {
        if (this.elements.lastUpdatedLabel) {
            this.elements.lastUpdatedLabel.textContent = this.state.lastUpdated
                ? this.state.lastUpdated.toLocaleString('pl-PL')
                : '-';
        }
    }

    applyFilters() {
        if (!this.cy) return;
        this.cy.batch(() => {
            this.cy.elements().style('display', 'element');
            Object.entries(this.state.filters).forEach(([filterKey, enabled]) => {
                const typeName = BRAIN_FILTER_MAP[filterKey];
                if (!enabled && typeName) {
                    this.cy.nodes(`[type="${typeName}"]`).style('display', 'none');
                }
            });

            const hiddenNodeIds = new Set(
                this.cy.nodes()
                    .filter((node) => node.style('display') === 'none')
                    .map((node) => node.id())
            );

            if (hiddenNodeIds.size > 0) {
                this.cy.edges().forEach((edge) => {
                    if (
                        hiddenNodeIds.has(edge.source().id()) ||
                        hiddenNodeIds.has(edge.target().id())
                    ) {
                        edge.style('display', 'none');
                    }
                });
            }
        });
        this.applySearch();
        this.updateVisibilityCounters();
    }

    applySearch() {
        if (!this.cy) return;
        const query = this.state.searchQuery.toLowerCase();
        this.cy.elements().removeClass('search-match search-dimmed');

        if (!query) {
            this.updateVisibilityCounters();
            return;
        }

        const visibleNodes = this.cy.nodes().filter((node) => node.style('display') !== 'none');
        const matchingNodes = visibleNodes.filter((node) => {
            const label = (node.data('label') || '').toLowerCase();
            return label.includes(query);
        });

        if (matchingNodes.length === 0) {
            this.updateVisibilityCounters();
            return;
        }

        this.cy.nodes().addClass('search-dimmed');
        this.cy.edges().addClass('search-dimmed');

        matchingNodes.removeClass('search-dimmed').addClass('search-match');
        const connectedEdges = matchingNodes.connectedEdges();
        connectedEdges.removeClass('search-dimmed');
        connectedEdges.connectedNodes().removeClass('search-dimmed');
        this.updateVisibilityCounters();
    }

    updateVisibilityCounters() {
        if (!this.cy) return;
        const totalNodes = this.cy.nodes().length;
        const totalEdges = this.cy.edges().length;
        const visibleNodes = this.cy
            .nodes()
            .filter((node) => node.style('display') !== 'none' && !node.hasClass('search-dimmed'))
            .length;
        const visibleEdges = this.cy
            .edges()
            .filter((edge) => edge.style('display') !== 'none' && !edge.hasClass('search-dimmed'))
            .length;

        if (this.elements.visibleNodes) {
            this.elements.visibleNodes.textContent = visibleNodes;
        }
        if (this.elements.visibleEdges) {
            this.elements.visibleEdges.textContent = visibleEdges;
        }
        if (this.elements.totalNodesLabel) {
            this.elements.totalNodesLabel.textContent = totalNodes;
        }
        if (this.elements.totalEdgesLabel) {
            this.elements.totalEdgesLabel.textContent = totalEdges;
        }
    }

    updateFilterSummary() {
        if (!this.elements.filterSummary || !this.elements.filterDetails) return;
        const disabled = Object.entries(this.state.filters)
            .filter(([, enabled]) => !enabled)
            .map(([key]) => key);
        if (disabled.length === 0) {
            this.elements.filterSummary.textContent = 'Wszystkie typy aktywne';
            this.elements.filterDetails.textContent = 'Wyłączone: brak';
        } else {
            this.elements.filterSummary.textContent = 'Filtry niestandardowe';
            this.elements.filterDetails.textContent = `Wyłączone: ${disabled.join(', ')}`;
        }
    }

    startAutoRefresh(immediate = false) {
        if (!this.state.autoRefresh || this.autoRefreshTimer) {
            return;
        }

        if (immediate) {
            this.reloadGraph();
        }

        this.autoRefreshTimer = setInterval(() => {
            if (this.state.autoRefresh) {
                this.reloadGraph();
            }
        }, this.AUTO_REFRESH_INTERVAL);
    }

    stopAutoRefresh() {
        if (this.autoRefreshTimer) {
            clearInterval(this.autoRefreshTimer);
            this.autoRefreshTimer = null;
        }
    }

    exportGraphJson() {
        if (!this.graphData || !this.elements.exportJsonBtn) return;
        const filename = `brain-graph-${new Date().toISOString().slice(0, 19)}.json`;
        this.downloadBlob(
            JSON.stringify(this.graphData, null, 2),
            filename,
            'application/json'
        );
        this.flashExportButton(this.elements.exportJsonBtn, '✅ JSON');
    }

    exportGraphPng() {
        if (!this.cy || !this.elements.exportPngBtn) return;
        try {
            const pngData = this.cy.png({ scale: 2, bg: '#020617' });
            fetch(pngData)
                .then((response) => response.blob())
                .then((blob) => {
                    const filename = `brain-graph-${new Date().toISOString().slice(0, 19)}.png`;
                    this.downloadBlob(blob, filename, 'image/png');
                    this.flashExportButton(this.elements.exportPngBtn, '✅ PNG');
                })
                .catch((error) => {
                    console.error('Błąd eksportu grafu:', error);
                    this.flashExportButton(this.elements.exportPngBtn, '⚠️ Błąd');
                });
        } catch (error) {
            console.error('Błąd eksportu grafu:', error);
            this.flashExportButton(this.elements.exportPngBtn, '⚠️ Błąd');
        }
    }

    showAlert(message) {
        if (!this.elements.alertBox) return;
        if (!message) {
            this.elements.alertBox.textContent = '';
            this.elements.alertBox.classList.remove('is-visible');
            return;
        }
        this.elements.alertBox.textContent = message;
        this.elements.alertBox.classList.add('is-visible');
    }

    showLoading() {
        if (this.elements.loadingOverlay) {
            this.elements.loadingOverlay.classList.add('is-visible');
        }
    }

    hideLoading() {
        if (this.elements.loadingOverlay) {
            this.elements.loadingOverlay.classList.remove('is-visible');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (typeof cytoscape === 'undefined') {
        console.error('Cytoscape.js nie zostało załadowane');
        return;
    }
    new BrainGraph();
});
