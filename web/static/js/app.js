// Venom Cockpit - Main Application

class VenomDashboard {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.tasks = new Map();
        this.widgets = new Map(); // THE_CANVAS: Widget storage
        this.chartInstances = new Map(); // Chart.js instances
        this.activeOperations = new Map(); // Track active skill operations
        this.activeTab = null;

        // Constants
        this.TASK_CONTENT_TRUNCATE_LENGTH = 50;
        this.LOG_ENTRY_MAX_COUNT = 100;

        // Initialize Mermaid
        if (typeof mermaid !== 'undefined') {
            mermaid.initialize({
                startOnLoad: false,
                theme: 'dark',
                themeVariables: {
                    darkMode: true,
                    background: '#1e1e1e',
                    primaryColor: '#3b82f6',
                    primaryTextColor: '#fff',
                    primaryBorderColor: '#3b82f6',
                    lineColor: '#6b7280',
                    secondaryColor: '#10b981',
                    tertiaryColor: '#f59e0b'
                }
            });
        }

        this.historyRefreshTimer = null;
        this.historyLoading = false;
        this.historyBackgroundLoading = false;
        this.historyState = {
            requests: [],
            filter: 'all',
            query: '',
            autoRefresh: true,
            lastUpdated: null
        };
        this.memoryRefreshTimer = null;
        this.memoryState = {
            lessons: [],
            filter: 'all',
            query: '',
            autoRefresh: true,
            loading: false,
            error: null,
            lastUpdated: null,
            graphSummary: {
                total_nodes: 0,
                total_edges: 0
            }
        };
        this.jobsRefreshTimer = null;
        this.jobsState = {
            jobs: [],
            filter: 'all',
            query: '',
            autoRefresh: true,
            loading: false,
            error: null,
            lastUpdated: null
        };
        this.modelsState = {
            list: [],
            lastUpdated: null
        };
        this.consoleState = {
            labMode: false
        };
        this.defaultTab = 'feed';
        this.preferences = this.loadUIPreferences();
        this.applyUIPreferences();
        this.selectedHistoryId = null;
        this.historyDetailAutoRefresh = false;

        this.initElements();
        this.initConsoleControls();
        this.initTabNavigation();
        this.initTabPreferencesControls();
        this.initPreferencesCenter();
        this.initWebSocket();
        this.initEventHandlers();
        this.startMetricsPolling();
        this.startRepositoryStatusPolling();
        this.startIntegrationsPolling(); // Dashboard v2.1
        this.startQueueStatusPolling(); // Dashboard v2.3
        this.startTokenomicsPolling(); // Dashboard v2.3
        this.startCostModePolling(); // Dashboard v2.4: Cost Guard
        this.initNotificationContainer();
        this.initHistoryControls();
        this.initHistoryInteractions();
        this.initJobsControls();
        this.restoreSavedTabPreference();
    }

    applySuggestionText(suggestion) {
        if (!suggestion || !this.elements.taskInput) return;
        this.elements.taskInput.value = suggestion;
        this.elements.taskInput.focus();
    }

    getSuggestionPrompt(chip) {
        if (!chip) return null;
        const prompt = chip.getAttribute('data-prompt') || chip.getAttribute('data-suggestion');
        if (prompt && prompt.trim().length > 0) {
            return prompt;
        }
        return (chip.textContent || '').trim();
    }

    initHistoryInteractions() {
        const historyBody = this.elements?.historyTableBody;
        if (!historyBody) return;

        const activateRow = (event) => {
            const row = event.target.closest('.history-row');
            if (!row) return;
            const requestId = row.dataset.requestId;
            if (requestId) {
                this.showHistoryDetail(requestId);
            }
        };

        historyBody.addEventListener('click', activateRow);
        historyBody.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter' && event.key !== ' ') {
                return;
            }
            event.preventDefault();
            activateRow(event);
        });
    }

    initHistoryControls() {
        const searchInput = this.elements?.historySearchInput;
        if (searchInput) {
            searchInput.value = this.historyState.query || '';
            searchInput.addEventListener('input', (event) => {
                this.historyState.query = event.target.value || '';
                this.renderHistoryTable();
                this.updateUIPreferences('history', { query: this.historyState.query });
            });
        }

        const filterButtons = this.elements?.historyFilterButtons || [];
        filterButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const status = button.dataset.status || 'all';
                this.setHistoryFilter(status);
            });
        });

        const autoToggle = this.elements?.historyAutoRefreshToggle;
        if (autoToggle) {
            autoToggle.checked = this.historyState.autoRefresh;
            autoToggle.addEventListener('change', (event) => {
                this.toggleHistoryAutoRefresh(event.target.checked);
            });
        }

        const resetButton = this.elements?.historyResetButton;
        if (resetButton) {
            resetButton.addEventListener('click', () => this.resetHistoryPreferences());
        }

        this.updateHistoryFilterButtons();
        this.updateHistoryLastUpdated();
    }

    setHistoryFilter(status) {
        this.historyState.filter = status;
        this.updateHistoryFilterButtons();
        this.renderHistoryTable();
        this.updateUIPreferences('history', { filter: this.historyState.filter });
    }

    updateHistoryFilterButtons() {
        const buttons = this.elements?.historyFilterButtons || [];
        buttons.forEach((button) => {
            button.classList.toggle('active', button.dataset.status === this.historyState.filter);
        });
    }

    toggleHistoryAutoRefresh(enabled) {
        this.historyState.autoRefresh = enabled;
        if (this.elements.historyAutoRefreshToggle) {
            this.elements.historyAutoRefreshToggle.checked = enabled;
        }
        this.updateUIPreferences('history', { autoRefresh: this.historyState.autoRefresh });
        if (enabled && this.isHistoryTabActive()) {
            this.startHistoryAutoRefresh({ immediate: true });
        } else {
            this.stopHistoryAutoRefresh();
        }
    }

    resetHistoryPreferences(options = {}) {
        const { silent = false } = options;
        this.historyState.filter = 'all';
        this.historyState.query = '';
        if (this.elements.historySearchInput) {
            this.elements.historySearchInput.value = '';
        }
        this.updateHistoryFilterButtons();
        this.renderHistoryTable();
        this.toggleHistoryAutoRefresh(true);
        this.updateUIPreferences('history', { filter: 'all', query: '' });

        if (this.isHistoryTabActive()) {
            this.loadHistory({ showLoading: true });
        }

        if (!silent) {
            this.showNotification('Przywrócono domyślne filtry historii', 'info');
        }
    }

    isHistoryTabActive() {
        const historyTab = document.getElementById('historyTab');
        return !!(historyTab && historyTab.classList.contains('active'));
    }

    updateHistoryLastUpdated() {
        if (!this.elements.historyLastUpdated) return;
        const timestamp = this.historyState.lastUpdated;
        this.elements.historyLastUpdated.textContent = timestamp
            ? timestamp.toLocaleString('pl-PL')
            : '-';
    }

    getFilteredHistoryRequests() {
        const filter = this.historyState.filter;
        const query = (this.historyState.query || '').toLowerCase();
        return this.historyState.requests.filter((request) => {
            const status = (request.status || '').toLowerCase();
            const statusMatch = filter === 'all' ? true : status === filter;
            if (!statusMatch) return false;
            if (!query) return true;
            const prompt = (request.prompt || '').toLowerCase();
            const id = (request.request_id || '').toLowerCase();
            return prompt.includes(query) || id.includes(query);
        });
    }

    renderHistoryPlaceholder(message, className = 'empty-state') {
        if (!this.elements.historyTableBody) return;
        this.elements.historyTableBody.innerHTML = `
            <tr>
                <td colspan="3" class="${className}">${message}</td>
            </tr>
        `;
    }

    setHistoryLoadingState(message = 'Odświeżanie historii...') {
        this.renderHistoryPlaceholder(message, 'loading-state');
    }

    updateHistoryInsights(requests = []) {
        const total = Array.isArray(requests) ? requests.length : 0;
        let success = 0;
        let failed = 0;
        let durationSum = 0;
        let durationCount = 0;

        if (total > 0) {
            requests.forEach((request) => {
                const status = (request.status || '').toLowerCase();
                if (['completed', 'success', 'successful'].includes(status)) {
                    success++;
                } else if (['failed', 'error', 'errored'].includes(status)) {
                    failed++;
                }

                const rawDuration = request.duration_seconds ?? request.duration;
                const duration = parseFloat(rawDuration);
                if (!Number.isNaN(duration) && duration > 0) {
                    durationSum += duration;
                    durationCount++;
                }
            });
        }

        const successRate = total > 0 ? `${Math.round((success / total) * 100)}%` : '0%';
        const avgDuration = durationCount > 0 ? `${(durationSum / durationCount).toFixed(1)}s` : '-';
        const sampleSize = this.historyState?.requests?.length || 0;

        this.setElementText(this.elements.historyTotalCount, total, '0');
        this.setElementText(this.elements.historySuccessCount, success, '0');
        this.setElementText(this.elements.historySuccessRate, successRate);
        this.setElementText(this.elements.historyFailedCount, failed, '0');
        this.setElementText(this.elements.historyAvgDuration, avgDuration);
        this.setElementText(this.elements.historySampleSize, sampleSize, '0');

        if (this.elements.historyFailedCard) {
            this.elements.historyFailedCard.classList.toggle('is-danger', failed > 0);
        }
    }

    renderHistoryTable() {
        if (!this.elements.historyTableBody) return;
        const requests = this.getFilteredHistoryRequests();
        this.updateHistoryInsights(requests);

        if (requests.length === 0) {
            this.renderHistoryPlaceholder('Brak wpisów spełniających kryteria');
            return;
        }

        this.elements.historyTableBody.innerHTML = '';
        requests.forEach((request) => {
            const row = this.createHistoryRow(request);
            this.elements.historyTableBody.appendChild(row);
        });

        this.highlightHistorySelection();

        if (
            this.historyDetailAutoRefresh &&
            this.selectedHistoryId &&
            this.isModalVisible(this.elements.historyModal)
        ) {
            this.showHistoryDetail(this.selectedHistoryId, { refreshOnly: true });
        }
    }

    initJobsControls() {
        const searchInput = this.elements?.jobsSearchInput;
        if (searchInput) {
            searchInput.value = this.jobsState.query || '';
            searchInput.addEventListener('input', (event) => {
                this.jobsState.query = event.target.value || '';
                this.renderJobsList();
                this.updateUIPreferences('jobs', { query: this.jobsState.query });
            });
        }

        const filterButtons = this.elements?.jobsFilterButtons || [];
        filterButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const type = button.dataset.type || 'all';
                this.setJobsFilter(type);
            });
        });

        const autoToggle = this.elements?.jobsAutoRefreshToggle;
        if (autoToggle) {
            autoToggle.checked = this.jobsState.autoRefresh;
            autoToggle.addEventListener('change', (event) => {
                this.toggleJobsAutoRefresh(event.target.checked);
            });
        }

        if (this.elements.refreshJobsBtn) {
            this.elements.refreshJobsBtn.addEventListener('click', () => {
                this.fetchBackgroundJobsStatus({ showLoading: true });
            });
        }

        const resetButton = this.elements?.jobsResetButton;
        if (resetButton) {
            resetButton.addEventListener('click', () => this.resetJobsPreferences());
        }

        this.updateJobsFilterButtons();
        this.renderJobsList();
        this.updateJobsLastUpdated();
    }

    setJobsFilter(filter) {
        this.jobsState.filter = filter;
        this.updateJobsFilterButtons();
        this.renderJobsList();
        this.updateUIPreferences('jobs', { filter: this.jobsState.filter });
    }

    updateJobsFilterButtons() {
        const buttons = this.elements?.jobsFilterButtons || [];
        buttons.forEach((button) => {
            button.classList.toggle('active', button.dataset.type === this.jobsState.filter);
        });
    }

    toggleJobsAutoRefresh(enabled) {
        this.jobsState.autoRefresh = enabled;
        if (this.elements.jobsAutoRefreshToggle) {
            this.elements.jobsAutoRefreshToggle.checked = enabled;
        }
        this.updateUIPreferences('jobs', { autoRefresh: this.jobsState.autoRefresh });
        if (enabled && this.isJobsTabActive()) {
            this.startJobsAutoRefresh({ immediate: true });
        } else {
            this.stopJobsAutoRefresh();
        }
    }

    resetJobsPreferences(options = {}) {
        const { silent = false } = options;
        this.jobsState.filter = 'all';
        this.jobsState.query = '';
        if (this.elements.jobsSearchInput) {
            this.elements.jobsSearchInput.value = '';
        }
        this.updateJobsFilterButtons();
        this.renderJobsList();
        this.toggleJobsAutoRefresh(true);
        this.updateUIPreferences('jobs', { filter: 'all', query: '' });

        if (this.isJobsTabActive()) {
            this.fetchBackgroundJobsStatus({ showLoading: true });
        }

        if (!silent) {
            this.showNotification('Przywrócono domyślne filtry zadań w tle', 'info');
        }
    }

    isJobsTabActive() {
        const jobsTab = document.getElementById('jobsTab');
        return !!(jobsTab && jobsTab.classList.contains('active'));
    }

    startJobsAutoRefresh(options = {}) {
        if (!this.jobsState.autoRefresh) return;
        if (!this.isJobsTabActive()) return;
        if (this.jobsRefreshTimer) return;

        const { immediate = true } = options;
        if (immediate) {
            this.fetchBackgroundJobsStatus();
        }

        this.jobsRefreshTimer = setInterval(() => {
            this.fetchBackgroundJobsStatus();
        }, 5000);
    }

    stopJobsAutoRefresh() {
        if (this.jobsRefreshTimer) {
            clearInterval(this.jobsRefreshTimer);
            this.jobsRefreshTimer = null;
        }
    }

    updateJobsLastUpdated() {
        if (!this.elements.jobsLastUpdated) return;
        const timestamp = this.jobsState.lastUpdated;
        this.elements.jobsLastUpdated.textContent = timestamp
            ? timestamp.toLocaleString('pl-PL')
            : '-';
    }

    getFilteredJobs() {
        const filter = this.jobsState.filter;
        const query = (this.jobsState.query || '').toLowerCase();

        return this.jobsState.jobs.filter((job) => {
            const type = (job.type || 'interval').toLowerCase();
            const matchesType = filter === 'all' ? true : type === filter;
            if (!matchesType) {
                return false;
            }
            if (!query) {
                return true;
            }
            const id = (job.id || '').toLowerCase();
            const description = (job.description || '').toLowerCase();
            return id.includes(query) || description.includes(query) || type.includes(query);
        });
    }

    renderJobsList() {
        const container = this.elements?.jobsList;
        if (!container) return;

        const jobs = this.getFilteredJobs();
        this.updateJobsInsights(jobs);

        if (this.jobsState.loading) {
            container.innerHTML = `
                <div class="flow-loading">
                    <div class="flow-spinner"></div>
                    <p>Odświeżanie zadań...</p>
                </div>
            `;
            return;
        }

        if (this.jobsState.error) {
            container.innerHTML = `
                <p class="error-state">${this.jobsState.error}</p>
            `;
            return;
        }

        if (jobs.length === 0) {
            const message = this.jobsState.jobs.length === 0
                ? 'Brak aktywnych zadań'
                : 'Brak wpisów spełniających kryteria';
            container.innerHTML = `<p class="empty-state">${message}</p>`;
            return;
        }

        container.innerHTML = jobs.map((job) => this.renderJobItem(job)).join('');
    }

    renderJobItem(job) {
        const nextRun = job.next_run_time ? new Date(job.next_run_time) : null;
        const nextRunLabel = nextRun && !Number.isNaN(nextRun.getTime())
            ? nextRun.toLocaleString('pl-PL')
            : 'brak danych';
        const type = (job.type || 'interval').toLowerCase();
        const typeLabel = type.toUpperCase();

        return `
            <div class="job-item">
                <div class="job-header">
                    <span class="job-id">${this.escapeHtml(job.id || '---')}</span>
                    <span class="job-type">${this.escapeHtml(typeLabel)}</span>
                </div>
                <div class="job-description">${this.escapeHtml(job.description || 'Brak opisu')}</div>
                <div class="job-next-run">Następne uruchomienie: ${this.escapeHtml(nextRunLabel)}</div>
            </div>
        `;
    }

    setJobsStatusPill(elementId, label, isActive) {
        const pill = document.getElementById(elementId);
        if (!pill) return;
        pill.textContent = label;
        pill.classList.toggle('is-active', !!isActive);
        pill.classList.toggle('is-inactive', !isActive);
    }

    updateJobsInsights(filteredJobs = []) {
        if (!this.elements.jobsVisibleCount) return;
        const visibleCount = Array.isArray(filteredJobs) ? filteredJobs.length : this.getFilteredJobs().length;
        const totalCount = this.jobsState.jobs.length;
        this.elements.jobsVisibleCount.textContent = visibleCount;
        if (this.elements.jobsTotalCount) {
            this.elements.jobsTotalCount.textContent = totalCount;
        }

        const statusBuckets = this.jobsState.jobs.reduce(
            (acc, job) => {
                const status = (job.status || job.state || 'unknown').toLowerCase();
                acc[status] = (acc[status] || 0) + 1;
                return acc;
            },
            {}
        );

        const runningStates = ['running', 'in_progress', 'active', 'executing'];
        const failedStates = ['failed', 'error', 'stopped', 'blocked'];
        const runningCount = runningStates.reduce(
            (sum, key) => sum + (statusBuckets[key] || 0),
            0
        );
        const failedCount = failedStates.reduce(
            (sum, key) => sum + (statusBuckets[key] || 0),
            0
        );

        if (this.elements.jobsRunningCount) {
            this.elements.jobsRunningCount.textContent = runningCount;
        }
        if (this.elements.jobsFailedCount) {
            this.elements.jobsFailedCount.textContent = failedCount;
        }

        if (this.elements.jobsFilterSummary) {
            const filterLabels = {
                all: 'wszystkie',
                interval: 'interwały',
                cron: 'cron',
                date: 'jednorazowe'
            };
            const filterLabel =
                filterLabels[this.jobsState.filter] || this.jobsState.filter || 'wszystkie';
            const query = (this.jobsState.query || '').trim();
            this.elements.jobsFilterSummary.textContent = query
                ? `Filtr: ${filterLabel} · Fraza: "${query}"`
                : `Filtr: ${filterLabel}`;
        }
    }

    initMemoryControls() {
        const searchInput = this.elements?.memorySearchInput;
        if (searchInput) {
            searchInput.value = this.memoryState.query || '';
            searchInput.addEventListener('input', (event) => {
                this.memoryState.query = event.target.value || '';
                this.renderLessonsList();
                this.updateUIPreferences('memory', { query: this.memoryState.query });
            });
        }

        const filterButtons = this.elements?.memoryFilterButtons || [];
        filterButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const status = button.dataset.status || 'all';
                this.setMemoryFilter(status);
            });
        });

        const autoToggle = this.elements?.memoryAutoRefreshToggle;
        if (autoToggle) {
            autoToggle.checked = this.memoryState.autoRefresh;
            autoToggle.addEventListener('change', (event) => {
                this.toggleMemoryAutoRefresh(event.target.checked);
            });
        }

        const resetButton = this.elements?.memoryResetButton;
        if (resetButton) {
            resetButton.addEventListener('click', () => this.resetMemoryPreferences());
        }

        this.updateMemoryFilterButtons();
        if (this.memoryState.lessons.length === 0) {
            this.memoryState.loading = true;
        }
        this.renderLessonsList();
        this.updateMemoryLastUpdated();
    }

    setMemoryFilter(filter) {
        this.memoryState.filter = filter;
        this.updateMemoryFilterButtons();
        this.renderLessonsList();
        this.updateUIPreferences('memory', { filter: this.memoryState.filter });
    }

    updateMemoryFilterButtons() {
        const buttons = this.elements?.memoryFilterButtons || [];
        buttons.forEach((button) => {
            button.classList.toggle('active', button.dataset.status === this.memoryState.filter);
        });
    }

    toggleMemoryAutoRefresh(enabled) {
        this.memoryState.autoRefresh = enabled;
        if (this.elements.memoryAutoRefreshToggle) {
            this.elements.memoryAutoRefreshToggle.checked = enabled;
        }
        this.updateUIPreferences('memory', { autoRefresh: this.memoryState.autoRefresh });
        if (enabled && this.isMemoryTabActive()) {
            this.startMemoryAutoRefresh({ immediate: true });
        } else {
            this.stopMemoryAutoRefresh();
        }
    }

    resetMemoryPreferences(options = {}) {
        const { silent = false } = options;
        this.memoryState.filter = 'all';
        this.memoryState.query = '';
        if (this.elements.memorySearchInput) {
            this.elements.memorySearchInput.value = '';
        }
        this.updateMemoryFilterButtons();
        this.renderLessonsList();
        this.toggleMemoryAutoRefresh(true);
        this.updateUIPreferences('memory', { filter: 'all', query: '' });

        if (this.isMemoryTabActive()) {
            this.fetchLessons({ showLoading: true });
            this.fetchGraphSummary();
        }

        if (!silent) {
            this.showNotification('Przywrócono domyślne filtry pamięci', 'info');
        }
    }

    isMemoryTabActive() {
        const memoryTab = document.getElementById('memoryTab');
        return !!(memoryTab && memoryTab.classList.contains('active'));
    }

    startMemoryAutoRefresh(options = {}) {
        if (!this.memoryState.autoRefresh) return;
        if (!this.isMemoryTabActive()) return;
        if (this.memoryRefreshTimer) return;

        const { immediate = true } = options;
        if (immediate) {
            this.fetchLessons();
        }

        this.memoryRefreshTimer = setInterval(() => {
            this.fetchLessons();
        }, 10000);
    }

    stopMemoryAutoRefresh() {
        if (this.memoryRefreshTimer) {
            clearInterval(this.memoryRefreshTimer);
            this.memoryRefreshTimer = null;
        }
    }

    updateMemoryLastUpdated() {
        if (!this.elements.memoryLastUpdated) return;
        const timestamp = this.memoryState.lastUpdated;
        this.elements.memoryLastUpdated.textContent = timestamp
            ? timestamp.toLocaleString('pl-PL')
            : '-';
    }

    updateMemoryInsights(filteredLessons = null) {
        if (!filteredLessons) {
            filteredLessons = this.getFilteredLessons();
        }
        const totalLessons = this.memoryState.lessons.length;
        const visibleLessons = Array.isArray(filteredLessons) ? filteredLessons.length : 0;
        const successCount = Array.isArray(filteredLessons)
            ? filteredLessons.filter((lesson) => this.getLessonStatus(lesson) === 'success').length
            : 0;
        const errorCount = visibleLessons - successCount;

        if (this.elements.memoryVisibleLessons) {
            this.elements.memoryVisibleLessons.textContent = visibleLessons;
        }
        if (this.elements.memoryTotalLessons) {
            this.elements.memoryTotalLessons.textContent = totalLessons;
        }
        if (this.elements.memorySuccessCount) {
            this.elements.memorySuccessCount.textContent = successCount;
        }
        if (this.elements.memoryErrorCount) {
            this.elements.memoryErrorCount.textContent = errorCount < 0 ? 0 : errorCount;
        }
        if (this.elements.memoryFilterSummary) {
            const filterLabels = {
                all: 'wszystkie',
                success: 'sukcesy',
                error: 'błędy'
            };
            const filterLabel =
                filterLabels[this.memoryState.filter] || this.memoryState.filter || 'wszystkie';
            const query = (this.memoryState.query || '').trim();
            this.elements.memoryFilterSummary.textContent = query
                ? `Filtr: ${filterLabel} · Fraza: "${query}"`
                : `Filtr: ${filterLabel}`;
        }

        this.updateMemoryGraphInsights();
    }

    updateMemoryGraphInsights() {
        const summary = this.memoryState.graphSummary || {};
        const nodes = summary.total_nodes || 0;
        const edges = summary.total_edges || 0;
        if (this.elements.memoryGraphNodes) {
            this.elements.memoryGraphNodes.textContent = nodes;
        }
        if (this.elements.memoryGraphEdges) {
            this.elements.memoryGraphEdges.textContent = edges;
        }
    }

    getLessonStatus(lesson) {
        const result = (lesson?.result || '').toLowerCase();
        if (result.includes('błąd') || result.includes('error') || result.includes('fail')) {
            return 'error';
        }
        return 'success';
    }

    getFilteredLessons() {
        const filter = this.memoryState.filter;
        const query = (this.memoryState.query || '').toLowerCase();

        return this.memoryState.lessons.filter((lesson) => {
            const status = this.getLessonStatus(lesson);
            const matchesFilter = filter === 'all' ? true : status === filter;
            if (!matchesFilter) {
                return false;
            }
            if (!query) {
                return true;
            }
            const situation = (lesson.situation || '').toLowerCase();
            const feedback = (lesson.feedback || '').toLowerCase();
            return situation.includes(query) || feedback.includes(query);
        });
    }

    renderLessonsList() {
        const container = this.elements?.lessonsList;
        if (!container) return;

        const lessons = this.getFilteredLessons();
        this.updateMemoryInsights(lessons);

        if (this.memoryState.loading) {
            container.innerHTML = `
                <div class="flow-loading">
                    <div class="flow-spinner"></div>
                    <p>Odświeżanie lekcji...</p>
                </div>
            `;
            return;
        }

        if (this.memoryState.error) {
            container.innerHTML = `<p class="error-state">${this.memoryState.error}</p>`;
            return;
        }

        if (lessons.length === 0) {
            const message = this.memoryState.lessons.length === 0
                ? 'Brak lekcji'
                : 'Brak wyników spełniających kryteria';
            container.innerHTML = `<p class="empty-state">${message}</p>`;
            return;
        }

        container.innerHTML = lessons.map((lesson) => this.renderLessonItem(lesson)).join('');
    }

    renderLessonItem(lesson) {
        const status = this.getLessonStatus(lesson);
        const situation = lesson.situation || 'Brak kontekstu';
        const feedback = lesson.feedback || '';
        const tags = Array.isArray(lesson.tags) ? lesson.tags : [];
        const trimmedSituation =
            situation.length > 120 ? `${situation.slice(0, 117)}...` : situation;
        const trimmedFeedback =
            feedback.length > 160 ? `${feedback.slice(0, 157)}...` : feedback;

        const tagsHtml = tags.length > 0
            ? `<div class="lesson-tags">
                ${tags.map(tag => `<span class="lesson-tag">${this.escapeHtml(tag)}</span>`).join('')}
               </div>`
            : '';

        return `
            <div class="lesson-item ${status}">
                <div class="lesson-situation">${this.escapeHtml(trimmedSituation)}</div>
                <div class="lesson-feedback">💡 ${this.escapeHtml(trimmedFeedback || 'Brak feedbacku')}</div>
                ${tagsHtml}
            </div>
        `;
    }

    createHistoryRow(request) {
        const row = document.createElement('tr');
        row.className = `status-${(request.status || '').toLowerCase()} history-row`;
        row.dataset.requestId = request.request_id;
        this.configureHistoryRow(row, request);

        const statusCell = document.createElement('td');
        const statusBadge = document.createElement('span');
        statusBadge.className = `status-badge status-${(request.status || '').toLowerCase()}`;
        statusBadge.textContent = `${this.getStatusIcon(request.status)} ${request.status}`;
        statusCell.appendChild(statusBadge);
        row.appendChild(statusCell);

        const promptCell = document.createElement('td');
        const promptText = document.createElement('div');
        promptText.className = 'prompt-text';
        promptText.textContent = request.prompt;
        promptText.title = request.prompt;
        promptCell.appendChild(promptText);
        row.appendChild(promptCell);

        const timeCell = document.createElement('td');
        const timeText = document.createElement('div');
        timeText.className = 'time-text';
        const createdDate = request.created_at ? new Date(request.created_at) : null;
        const duration = request.duration_seconds
            ? `(${request.duration_seconds.toFixed(1)}s)`
            : '';
        timeText.textContent = createdDate ? `${this.formatTime(createdDate)} ${duration}` : '-';
        timeCell.appendChild(timeText);
        row.appendChild(timeCell);

        return row;
    }

    initNotificationContainer() {
        // Create notification container for toast messages
        const container = document.createElement('div');
        container.id = 'notification-container';
        container.className = 'notification-container';
        document.body.appendChild(container);
        return container;
    }

    showNotification(message, type = 'info') {
        const container =
            document.getElementById('notification-container') || this.initNotificationContainer();
        const notification = document.createElement('div');
        notification.className = `notification notification--${type}`;
        notification.textContent = message;

        container.appendChild(notification);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            notification.classList.add('notification--hiding');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 5000);
    }

    showModal(modal) {
        if (!modal) return;
        modal.classList.add('is-visible');
    }

    hideModal(modal) {
        if (!modal) return;
        modal.classList.remove('is-visible');
    }

    isModalVisible(modal) {
        return !!(modal && modal.classList.contains('is-visible'));
    }

    initElements() {
        this.elements = {
            connectionStatus: document.getElementById('connectionStatus'),
            statusText: document.getElementById('statusText'),
            statusBannerDot: document.getElementById('statusBannerDot'),
            statusBannerText: document.getElementById('statusBannerText'),
            workspacePathValue: document.getElementById('workspacePath'),
            repoBannerMessage: document.getElementById('repoBannerMessage'),
            taskInput: document.getElementById('taskInput'),
            sendButton: document.getElementById('sendButton'),
            chatMessages: document.getElementById('chatMessages'),
            chatScrollArea: document.getElementById('chatScrollArea'),
            suggestionPanel: document.getElementById('suggestionPanel'),
            liveFeed: document.getElementById('liveFeed'),
            taskList: document.getElementById('taskList'),
            defaultTabLabel: document.getElementById('defaultTabLabel'),
            setDefaultTabBtn: document.getElementById('setDefaultTabBtn'),
            resetDefaultTabBtn: document.getElementById('resetDefaultTabBtn'),
            metricTasks: document.getElementById('metricTasks'),
            metricSuccess: document.getElementById('metricSuccess'),
            metricUptime: document.getElementById('metricUptime'),
            // Repository status elements
            branchName: document.getElementById('branchName'),
            changesText: document.getElementById('changesText'),
            repoChanges: document.getElementById('repoChanges'),
            syncRepoBtn: document.getElementById('syncRepoBtn'),
            undoChangesBtn: document.getElementById('undoChangesBtn'),
            initRepoBtn: document.getElementById('initRepoBtn'),
            // THE_CANVAS: Widget elements
            widgetsGrid: document.getElementById('widgetsGrid'),
            clearWidgetsBtn: document.getElementById('clearWidgetsBtn'),
            // History elements
            historyTableBody: document.getElementById('historyTableBody'),
            refreshHistory: document.getElementById('refreshHistory'),
            historySearchInput: document.getElementById('historySearchInput'),
            historyAutoRefreshToggle: document.getElementById('historyAutoRefreshToggle'),
            historyResetButton: document.getElementById('historyResetFilters'),
            historyFilterButtons: document.querySelectorAll('.history-filter-btn'),
            historyLastUpdated: document.getElementById('historyLastUpdated'),
            historyModal: document.getElementById('historyModal'),
            historyModalBody: document.getElementById('historyModalBody'),
            closeHistoryModal: document.getElementById('closeHistoryModal'),
            historyTotalCount: document.getElementById('historyTotalCount'),
            historySuccessCount: document.getElementById('historySuccessCount'),
            historySuccessRate: document.getElementById('historySuccessRate'),
            historyFailedCount: document.getElementById('historyFailedCount'),
            historyAvgDuration: document.getElementById('historyAvgDuration'),
            historySampleSize: document.getElementById('historySampleSize'),
            historyFailedCard: document.getElementById('historyFailedCard'),
            // Memory tab
            lessonsList: document.getElementById('lessonsList'),
            memorySearchInput: document.getElementById('memorySearchInput'),
            memoryFilterButtons: document.querySelectorAll('.memory-filter-btn'),
            memoryAutoRefreshToggle: document.getElementById('memoryAutoRefreshToggle'),
            memoryResetButton: document.getElementById('memoryResetFilters'),
            memoryLastUpdated: document.getElementById('memoryLastUpdated'),
            refreshLessons: document.getElementById('refreshLessons'),
            scanGraph: document.getElementById('scanGraph'),
            memoryVisibleLessons: document.getElementById('memoryVisibleLessons'),
            memoryTotalLessons: document.getElementById('memoryTotalLessons'),
            memorySuccessCount: document.getElementById('memorySuccessCount'),
            memoryErrorCount: document.getElementById('memoryErrorCount'),
            memoryFilterSummary: document.getElementById('memoryFilterSummary'),
            memoryGraphNodes: document.getElementById('memoryGraphNodes'),
            memoryGraphEdges: document.getElementById('memoryGraphEdges'),
            // Background jobs
            jobsList: document.getElementById('jobsList'),
            jobsSearchInput: document.getElementById('jobsSearchInput'),
            jobsFilterButtons: document.querySelectorAll('.jobs-filter-btn'),
            jobsAutoRefreshToggle: document.getElementById('jobsAutoRefreshToggle'),
            jobsLastUpdated: document.getElementById('jobsLastUpdated'),
            refreshJobsBtn: document.getElementById('refreshJobsBtn'),
            jobsResetButton: document.getElementById('jobsResetFilters'),
            jobsVisibleCount: document.getElementById('jobsVisibleCount'),
            jobsTotalCount: document.getElementById('jobsTotalCount'),
            jobsRunningCount: document.getElementById('jobsRunningCount'),
            jobsFailedCount: document.getElementById('jobsFailedCount'),
            jobsFilterSummary: document.getElementById('jobsFilterSummary'),
            // Models tab
            modelsInstalledCount: document.getElementById('modelsInstalledCount'),
            modelsActiveCount: document.getElementById('modelsActiveCount'),
            modelsTotalSize: document.getElementById('modelsTotalSize'),
            modelsQuantSummary: document.getElementById('modelsQuantSummary'),
            modelsLastUpdated: document.getElementById('modelsLastUpdated'),
            // Console / chat controls
            labModeCheckbox: document.getElementById('labModeCheckbox'),
            // Preferences Center
            openPreferencesCenterBtn: document.getElementById('openPreferencesCenterBtn'),
            preferencesModal: document.getElementById('preferencesModal'),
            closePreferencesModal: document.getElementById('closePreferencesModal'),
            preferencesSummary: document.getElementById('preferencesSummary'),
            externalPreferencesSummary: document.getElementById('externalPreferencesSummary'),
            resetCockpitPreferencesBtn: document.getElementById('resetCockpitPreferencesBtn'),
            resetExternalPreferencesBtn: document.getElementById('resetExternalPreferencesBtn'),
            resetAllPreferencesBtn: document.getElementById('resetAllPreferencesBtn'),
            preferencesExportPayload: document.getElementById('preferencesExportPayload'),
            copyPreferencesExportBtn: document.getElementById('copyPreferencesExportBtn'),
            refreshPreferencesExportBtn: document.getElementById('refreshPreferencesExportBtn'),
            preferencesImportInput: document.getElementById('preferencesImportInput'),
            downloadPreferencesExportBtn: document.getElementById('downloadPreferencesExportBtn'),
            preferencesImportFileInput: document.getElementById('preferencesImportFileInput'),
            preferencesImportFileName: document.getElementById('preferencesImportFileName'),
            applyPreferencesImportBtn: document.getElementById('applyPreferencesImportBtn'),
            // Dashboard v2.3: Queue Governance
            queueActive: document.getElementById('queueActive'),
            queuePending: document.getElementById('queuePending'),
            queueLimit: document.getElementById('queueLimit'),
            sessionCost: document.getElementById('sessionCost'),
            pauseResumeBtn: document.getElementById('pauseResumeBtn'),
            purgeQueueBtn: document.getElementById('purgeQueueBtn'),
            emergencyStopBtn: document.getElementById('emergencyStopBtn'),
            governancePanel: document.querySelector('.queue-governance-panel'),
            // Telemetry log feed
            clearLiveFeedBtn: document.getElementById('clearLiveFeedBtn'),
            // Dashboard v2.4: Cost Mode (Global Cost Guard)
            costModeToggle: document.getElementById('costModeToggle'),
            costModeLabel: document.getElementById('costModeLabel'),
            costModeStatusLabel: document.getElementById('costModeStatusLabel'),
            costModeModal: document.getElementById('costModeModal'),
            closeCostModeModal: document.getElementById('closeCostModeModal'),
            confirmCostMode: document.getElementById('confirmCostMode'),
            cancelCostMode: document.getElementById('cancelCostMode'),
            // System Guard status
            autonomyStatusLabel: document.getElementById('autonomyStatusLabel'),
        };
    }

    initConsoleControls() {
        const labModeCheckbox = this.elements?.labModeCheckbox;
        if (!labModeCheckbox) return;

        labModeCheckbox.checked = !!this.consoleState.labMode;
        labModeCheckbox.addEventListener('change', (event) => {
            this.consoleState.labMode = !!event.target.checked;
            this.updateUIPreferences('console', { labMode: this.consoleState.labMode });
            if (this.consoleState.labMode) {
                this.showNotification('🧪 Lab Mode aktywny – nowe zadania nie zapisują lekcji', 'info');
            }
        });
    }

    initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/events`;

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('Połączono z WebSocket');
                this.updateConnectionStatus(true);
                this.reconnectAttempts = 0;
                this.addLogEntry('info', 'Połączono z telemetrią Venoma');
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };

            this.ws.onerror = (error) => {
                console.error('Błąd WebSocket:', error);
                this.addLogEntry('error', 'Błąd połączenia WebSocket');
            };

            this.ws.onclose = () => {
                console.log('Połączenie WebSocket zamknięte');
                this.updateConnectionStatus(false);
                this.attemptReconnect();
            };
        } catch (error) {
            console.error('Nie można utworzyć WebSocket:', error);
            this.updateConnectionStatus(false);
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);

            this.addLogEntry('warning', `Ponowna próba za ${delay/1000}s... (podejście ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

            setTimeout(() => {
                this.initWebSocket();
            }, delay);
        } else {
            this.addLogEntry('error', 'Nie można połączyć z serwerem. Odśwież stronę.');
        }
    }

    updateConnectionStatus(connected) {
        const {
            connectionStatus,
            statusText,
            statusBannerDot,
            statusBannerText
        } = this.elements;

        if (connected) {
            connectionStatus?.classList.add('connected');
            statusBannerDot?.classList.add('connected');
            if (statusText) statusText.textContent = 'Połączono';
            if (statusBannerText) statusBannerText.textContent = 'Połączono';
        } else {
            connectionStatus?.classList.remove('connected');
            statusBannerDot?.classList.remove('connected');
            if (statusText) statusText.textContent = 'Rozłączono';
            if (statusBannerText) statusBannerText.textContent = 'Rozłączono';
        }
    }

    setRepoBannerMessage(message, variant = 'info') {
        const banner = this.elements.repoBannerMessage;
        if (!banner) return;

        const variants = ['info', 'success', 'warning', 'error'];
        variants.forEach(v => banner.classList.remove(`status-alert--${v}`));

        if (!message) {
            banner.textContent = '';
            banner.classList.add('is-hidden');
            return;
        }

        if (variant) {
            banner.classList.add(`status-alert--${variant}`);
        }

        banner.textContent = message;
        banner.classList.remove('is-hidden');
    }

    handleWebSocketMessage(data) {
        const { type, agent, message, data: eventData } = data;

        // Add to live feed
        const logLevel = this.getLogLevel(type);
        if (type !== 'SYSTEM_LOG') {
            this.addLogEntry(logLevel, `[${type}] ${agent ? agent + ': ' : ''}${message}`);
        }

        // Handle specific event types
        switch (type) {
            case 'TASK_CREATED':
                this.handleTaskCreated(eventData);
                break;
            case 'TASK_STARTED':
                this.handleTaskStarted(eventData);
                break;
            case 'TASK_COMPLETED':
                this.handleTaskCompleted(eventData);
                break;
            case 'TASK_FAILED':
                this.handleTaskFailed(eventData);
                break;
            case 'PLAN_CREATED':
                this.handlePlanCreated(eventData);
                break;
            case 'HEALING_STARTED':
                this.handleHealingStarted(eventData);
                break;
            case 'TEST_RUNNING':
                this.handleTestRunning(eventData);
                break;
            case 'TEST_RESULT':
                this.handleTestResult(eventData, message);
                break;
            case 'HEALING_FAILED':
                this.handleHealingFailed(eventData);
                break;
            case 'HEALING_ERROR':
                this.handleHealingError(eventData);
                break;
            case 'AGENT_ACTION':
            case 'AGENT_THOUGHT':
                // Pass metadata if available for research source badges
                const metadata = eventData ? {
                    search_source: eventData.search_source
                } : null;
                this.addChatMessage('assistant', message, agent, metadata);
                break;
            // THE_CANVAS: Widget rendering events
            case 'RENDER_WIDGET':
                this.handleRenderWidget(eventData);
                break;
            case 'UPDATE_WIDGET':
                this.handleUpdateWidget(eventData);
                break;
            case 'REMOVE_WIDGET':
                this.handleRemoveWidget(eventData);
                break;
            // Dashboard v2.1: Skill execution events
            case 'SKILL_STARTED':
                this.handleSkillStarted(eventData);
                break;
            case 'SKILL_COMPLETED':
                this.handleSkillCompleted(eventData);
                break;
            case 'SKILL_FAILED':
                this.handleSkillFailed(eventData);
                break;
            // Dashboard v2.3: System logs
            case 'SYSTEM_LOG':
                this.handleSystemLog(eventData, message);
                break;
            // Dashboard v2.3: Queue events
            case 'QUEUE_PAUSED':
            case 'QUEUE_RESUMED':
            case 'QUEUE_PURGED':
            case 'TASK_ABORTED':
                // Just refresh queue status
                fetch('/api/v1/queue/status')
                    .then(r => r.json())
                    .then(status => this.updateQueueStatus(status))
                    .catch(e => console.error('Error refreshing queue:', e));
                break;
        }
    }

    getLogLevel(eventType) {
        if (eventType.includes('FAILED') || eventType.includes('ERROR')) {
            return 'error';
        }
        if (eventType.includes('WARNING')) {
            return 'warning';
        }
        return 'info';
    }

    handleTaskCreated(data) {
        if (data && data.task_id) {
            this.tasks.set(data.task_id, {
                id: data.task_id,
                content: data.content || 'Nowe zadanie',
                status: 'PENDING',
                created: new Date()
            });
            this.updateTaskList();
        }
    }

    handleTaskStarted(data) {
        if (data && data.task_id) {
            const task = this.tasks.get(data.task_id);
            if (task) {
                task.status = 'PROCESSING';
                this.updateTaskList();
            }
        }
    }

    handleTaskCompleted(data) {
        if (data && data.task_id) {
            const task = this.tasks.get(data.task_id);
            if (task) {
                task.status = 'COMPLETED';
                this.updateTaskList();
            }
        }
    }

    handleTaskFailed(data) {
        if (data && data.task_id) {
            const task = this.tasks.get(data.task_id);
            if (task) {
                task.status = 'FAILED';
                task.error = data.error;
                this.updateTaskList();
            }
        }
    }

    handlePlanCreated(data) {
        // Could add plan visualization here
        this.addChatMessage('assistant', 'Plan utworzony - szczegóły w transmisji na żywo', 'Architekt');
    }

    handleHealingStarted(data) {
        if (data && data.task_id) {
            this.showNotification('🔄 Rozpoczynam automatyczne testy i naprawy', 'info');
            this.addChatMessage('assistant', `Uruchamiam pętlę samonaprawy (max ${data.max_iterations} iteracji)`, 'Strażnik');
        }
    }

    handleTestRunning(data) {
        if (data && data.task_id) {
            const iterationInfo = data.iteration ? ` - Próba ${data.iteration}` : '';
            this.addChatMessage('assistant', `🔍 Uruchamiam testy${iterationInfo}`, 'Strażnik');
        }
    }

    handleTestResult(data, message) {
        if (data && data.task_id) {
            if (data.success) {
                // Testy przeszły ✅
                this.showNotification('✅ Wszystkie testy przeszły pomyślnie!', 'success');
                this.addChatMessage('assistant', `✅ ${message}`, 'Strażnik');

                // Pokaż zielony pasek
                this.showTestProgressBar(data.task_id, true, data.iterations || 1);
            } else {
                // Testy nie przeszły ❌
                this.addChatMessage('assistant', `❌ ${message}`, 'Strażnik');

                // Pokaż czerwony pasek
                this.showTestProgressBar(data.task_id, false, data.iteration || 1);
            }
        }
    }

    handleHealingFailed(data) {
        if (data && data.task_id) {
            this.showNotification('⚠️ Nie udało się naprawić kodu automatycznie', 'warning');
            this.addChatMessage('assistant',
                `⚠️ FAIL FAST: Nie udało się naprawić kodu w ${data.iterations} iteracjach. Wymagana interwencja ręczna.`,
                'Strażnik'
            );

            // Pokaż fragment raportu jeśli dostępny
            if (data.final_report) {
                const reportPreview = data.final_report.substring(0, 200);
                this.addChatMessage('assistant', `Ostatni raport: ${reportPreview}...`, 'Strażnik');
            }
        }
    }

    handleHealingError(data) {
        if (data && data.task_id) {
            this.showNotification('❌ Błąd podczas pętli samonaprawy', 'error');
            this.addChatMessage('assistant', `❌ Błąd: ${data.error}`, 'Strażnik');
        }
    }

    showTestProgressBar(taskId, success, iteration) {
        // Stwórz lub zaktualizuj pasek postępu testów
        let progressBar = document.getElementById(`test-progress-${taskId}`);

        const baseClass = success ? 'test-progress--success' : 'test-progress--error';

        if (!progressBar) {
            // Utwórz nowy pasek postępu
            progressBar = document.createElement('div');
            progressBar.id = `test-progress-${taskId}`;
            progressBar.className = `test-progress ${baseClass}`;

            // Dodaj do chat messages
            this.elements.chatMessages.appendChild(progressBar);
        } else {
            progressBar.className = `test-progress ${baseClass}`;
        }

        // Zaktualizuj zawartość
        const emoji = success ? '🟢' : '🔴';
        const statusText = success ? 'SUKCES' : 'BŁĄD';

        progressBar.innerHTML = `
            <div class="test-progress__body">
                <div class="test-progress__icon">${emoji}</div>
                <div class="test-progress__text">
                    <div class="test-progress__status">${statusText}</div>
                    <div class="test-progress__iteration">Iteracja: ${iteration}</div>
                </div>
            </div>
        `;

        // Auto-scroll
        this.scrollChatToBottom();
    }

    addLogEntry(level, message) {
        if (!this.elements.liveFeed) {
            return;
        }
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${level}`;

        const now = new Date();
        const timestamp = now.toLocaleTimeString('pl-PL');

        const timestampSpan = document.createElement('span');
        timestampSpan.className = 'timestamp';
        timestampSpan.textContent = `[${timestamp}]`;

        const messageSpan = document.createElement('span');
        messageSpan.className = 'message';
        messageSpan.textContent = message;

        logEntry.appendChild(timestampSpan);
        logEntry.appendChild(messageSpan);

        this.elements.liveFeed.appendChild(logEntry);

        // Auto-scroll
        this.elements.liveFeed.scrollTop = this.elements.liveFeed.scrollHeight;

        // Limit number of logs
        while (this.elements.liveFeed.children.length > this.LOG_ENTRY_MAX_COUNT) {
            this.elements.liveFeed.removeChild(this.elements.liveFeed.firstChild);
        }
    }

    clearLiveFeed() {
        if (!this.elements.liveFeed) return;
        this.elements.liveFeed.innerHTML = `
            <div class="terminal-line terminal-line--accent">&gt; System wyczyszczony.</div>
            <div class="terminal-line terminal-line--muted">&gt; Oczekiwanie na zadania...</div>
        `;
    }

    addChatMessage(role, content, agent = null, metadata = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        if (agent) {
            const agentSpan = document.createElement('strong');
            agentSpan.textContent = agent + ': ';
            messageDiv.appendChild(agentSpan);
        } else {
            messageDiv.classList.add('no-agent');
        }

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.innerHTML = this.formatMessageContent(content);
        messageDiv.appendChild(contentDiv);

        // Dashboard v2.5: Research source badge
        if (metadata && metadata.search_source) {
            const badge = document.createElement('span');
            badge.className = 'research-source-badge';

            if (metadata.search_source === 'google_grounding') {
                badge.classList.add('google-grounded');
                badge.textContent = '🌍 Źródło: Google Grounding';
            } else if (metadata.search_source === 'duckduckgo') {
                badge.classList.add('web-search');
                badge.textContent = '🦆 Wyszukiwanie w sieci';
            }

            messageDiv.appendChild(badge);
        }

        // Dashboard v2.4: Model Attribution Badge
        // metadata jest opcjonalne - backward compatibility
        if (metadata && typeof metadata === 'object' && metadata.model_name) {
            const badge = document.createElement('span');
            badge.className = metadata.is_paid ? 'model-badge paid' : 'model-badge free';

            const icon = metadata.is_paid ? '⚡' : '🤖';
            const modelName = metadata.model_name || 'Nieznany';

            badge.textContent = `${icon} ${modelName}`;
            badge.title = `Dostawca: ${metadata.provider || 'nieznany'}`;

            messageDiv.appendChild(badge);
        }

        this.elements.chatMessages.appendChild(messageDiv);
        this.scrollChatToBottom();
    }

    formatMessageContent(text) {
        if (!text) {
            return '';
        }
        const safeText = this.escapeHtml(text);
        return safeText.replace(/(?:\r\n|\r|\n)/g, '<br>');
    }

    scrollChatToBottom() {
        const scrollTarget = this.elements.chatScrollArea || this.elements.chatMessages;
        if (scrollTarget) {
            scrollTarget.scrollTop = scrollTarget.scrollHeight;
        }
    }

    setElementText(element, value, fallback = '-') {
        if (!element) return;
        const shouldUseFallback =
            value === null ||
            value === undefined ||
            (typeof value === 'string' && value.trim() === '');
        element.textContent = shouldUseFallback ? fallback : value;
    }

    updateTaskList() {
        if (!this.elements.taskList) {
            return;
        }

        const taskList = this.elements.taskList;
        // Clear task list
        taskList.innerHTML = '';

        if (this.tasks.size === 0) {
            // Brak aktywnych zadań - use DOM methods for consistency
            const emptyState = document.createElement('p');
            emptyState.className = 'empty-state';
            emptyState.textContent = 'Brak aktywnych zadań';
            taskList.appendChild(emptyState);
            return;
        }

        const tasksArray = Array.from(this.tasks.values()).reverse();

        tasksArray.forEach(task => {
            const statusEmoji = {
                'PENDING': '⏳',
                'PROCESSING': '⚙️',
                'COMPLETED': '✅',
                'FAILED': '❌'
            }[task.status] || '❓';

            const statusClass = task.status.toLowerCase();
            const truncatedContent = task.content.substring(0, this.TASK_CONTENT_TRUNCATE_LENGTH);

            // Create task item using DOM methods
            const taskItem = document.createElement('div');
            taskItem.className = `task-item ${statusClass}`;
            taskItem.dataset.taskId = task.id;

            const contentDiv = document.createElement('div');
            contentDiv.className = 'task-content';
            const strong = document.createElement('strong');
            strong.textContent = `${statusEmoji} ${truncatedContent}...`;
            contentDiv.appendChild(strong);

            const statusDiv = document.createElement('div');
            statusDiv.className = 'task-status';
            const statusLabels = {
                'PENDING': 'Oczekuje',
                'PROCESSING': 'W toku',
                'COMPLETED': 'Zakończone',
                'FAILED': 'Błąd'
            };
            const statusLabel = statusLabels[task.status] || task.status;
            statusDiv.textContent = `Status: ${statusLabel}`;

            taskItem.appendChild(contentDiv);
            taskItem.appendChild(statusDiv);

            // Dashboard v2.3: Add abort button for PROCESSING tasks
            if (task.status === 'PROCESSING') {
                const abortBtn = document.createElement('button');
                abortBtn.className = 'task-abort-btn';
                abortBtn.textContent = '⛔ Zatrzymaj';
                abortBtn.dataset.taskId = task.id;
                abortBtn.title = 'Przerwij zadanie';
                taskItem.appendChild(abortBtn);
            }

            taskList.appendChild(taskItem);
        });
    }

    initEventHandlers() {
        // Send task
        this.elements.sendButton.addEventListener('click', () => {
            this.sendTask();
        });

        // Ctrl+Enter in textarea
        this.elements.taskInput.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                this.sendTask();
            }
        });

        // Suggestion chips click handlers (both static section and dynamic messages)
        const handleSuggestionClick = (event) => {
            const chip = event.target.closest('.suggestion-chip');
            if (!chip) return;
            const prompt = this.getSuggestionPrompt(chip);
            if (!prompt) return;
            event.preventDefault();
            this.applySuggestionText(prompt);
        };
        document.addEventListener('click', handleSuggestionClick);

        // Repository quick actions
        const syncBtn = this.elements.syncRepoBtn;
        if (syncBtn) {
            syncBtn.addEventListener('click', () => {
                this.handleSyncRepo();
            });
        }

        const undoBtn = this.elements.undoChangesBtn;
        if (undoBtn) {
            undoBtn.addEventListener('click', () => {
                this.handleUndoChanges();
            });
        }

        const initBtn = this.elements.initRepoBtn;
        if (initBtn) {
            initBtn.addEventListener('click', () => {
                this.initRepositoryFlow();
            });
        }

        // THE_CANVAS: Clear widgets button
        if (this.elements.clearWidgetsBtn) {
            this.elements.clearWidgetsBtn.addEventListener('click', () => {
                this.clearAllWidgets();
            });
        }

        // History: Refresh button
        if (this.elements.refreshHistory) {
            this.elements.refreshHistory.addEventListener('click', () => {
                this.loadHistory({ showLoading: true });
            });
        }

        // History: Close modal button
        if (this.elements.closeHistoryModal) {
            this.elements.closeHistoryModal.addEventListener('click', () => {
                this.closeHistoryModal();
            });
        }

        // History: Click outside modal to close
        if (this.elements.historyModal) {
            this.elements.historyModal.addEventListener('click', (e) => {
                if (e.target === this.elements.historyModal) {
                    this.closeHistoryModal();
                }
            });
        }

        // History: Close modal on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isModalVisible(this.elements.historyModal)) {
                this.closeHistoryModal();
            }
        });

        // Dashboard v2.3: Queue Governance
        if (this.elements.pauseResumeBtn) {
            this.elements.pauseResumeBtn.addEventListener('click', () => {
                this.handlePauseResume();
            });
        }

        if (this.elements.purgeQueueBtn) {
            this.elements.purgeQueueBtn.addEventListener('click', () => {
                this.handlePurgeQueue();
            });
        }

        if (this.elements.emergencyStopBtn) {
            this.elements.emergencyStopBtn.addEventListener('click', () => {
                this.handleEmergencyStop();
            });
        }

        if (this.elements.clearLiveFeedBtn) {
            this.elements.clearLiveFeedBtn.addEventListener('click', () => {
                this.clearLiveFeed();
            });
        }

        // Task list delegation for abort buttons
        if (this.elements.taskList) {
            this.elements.taskList.addEventListener('click', (e) => {
                if (e.target.closest('.task-abort-btn')) {
                    const taskId = e.target.closest('.task-abort-btn').dataset.taskId;
                    this.handleAbortTask(taskId);
                }
            });
        }

        // Dashboard v2.4: Cost Mode (Global Cost Guard)
        if (this.elements.costModeToggle) {
            this.elements.costModeToggle.addEventListener('change', (e) => {
                this.handleCostModeToggle(e.target.checked);
            });
        }

        if (this.elements.closeCostModeModal) {
            this.elements.closeCostModeModal.addEventListener('click', () => {
                this.closeCostModeModal();
            });
        }

        if (this.elements.confirmCostMode) {
            this.elements.confirmCostMode.addEventListener('click', () => {
                this.confirmCostModeChange();
            });
        }

        if (this.elements.cancelCostMode) {
            this.elements.cancelCostMode.addEventListener('click', () => {
                this.cancelCostModeChange();
            });
        }

        // Close cost mode modal on Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isModalVisible(this.elements.costModeModal)) {
                this.cancelCostModeChange();
            }
        });
    }

    async sendTask() {
        const content = this.elements.taskInput.value.trim();

        if (!content) {
            this.showNotification('Wprowadź treść zadania', 'warning');
            return;
        }

        // Disable button
        this.elements.sendButton.disabled = true;

        try {
            // Add user message to chat
            this.addChatMessage('user', content);

            // Pobierz stan Lab Mode
            const isLabModeEnabled = this.consoleState?.labMode ?? false;

            // Jeśli Lab Mode jest włączony, pokaż wizualne wskazanie
            if (isLabModeEnabled) {
                this.showNotification('🧪 Lab Mode: To zadanie nie zapisze lekcji', 'info');
            }

            // Send via API
            const response = await fetch('/api/v1/tasks', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    content: content,
                    store_knowledge: !isLabModeEnabled, // Jeśli Lab Mode ON, store_knowledge OFF
                }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();

            // Clear input
            this.elements.taskInput.value = '';

        this.addLogEntry('info', `Zadanie wysłane: ${result.task_id}`);
            this.showNotification('Zadanie wysłane pomyślnie', 'success');

        } catch (error) {
            console.error('Error sending task:', error);
            this.addLogEntry('error', `Nie można wysłać zadania: ${error.message}`);
            this.showNotification('Błąd wysyłania zadania. Sprawdź konsolę.', 'error');
        } finally {
            this.elements.sendButton.disabled = false;
        }
    }

    async fetchMetrics() {
        try {
            const response = await fetch('/api/v1/metrics');

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const metrics = await response.json();
            this.updateMetrics(metrics);

        } catch (error) {
            console.error('Error fetching metrics:', error);
        }
    }

    updateMetrics(metrics) {
        if (metrics.tasks) {
            this.elements.metricTasks.textContent = metrics.tasks.created || 0;
            this.elements.metricSuccess.textContent = `${metrics.tasks.success_rate || 0}%`;
        }

        if (metrics.uptime_seconds !== undefined) {
            this.elements.metricUptime.textContent = this.formatUptime(metrics.uptime_seconds);
        }

        // Dashboard v2.1: Network I/O
        if (metrics.network && metrics.network.total_bytes !== undefined) {
            const totalKB = Math.round(metrics.network.total_bytes / 1024);
            const metricNetwork = document.getElementById('metricNetwork');
            if (metricNetwork) {
                metricNetwork.textContent = totalKB >= 1024
                    ? `${(totalKB / 1024).toFixed(1)} MB`
                    : `${totalKB} KB`;
            }
        }
    }

    formatUptime(seconds) {
        if (seconds < 60) {
            return `${Math.floor(seconds)}s`;
        }

        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) {
            return `${minutes}m`;
        }

        const hours = Math.floor(minutes / 60);
        const remainingMinutes = minutes % 60;
        return `${hours}h ${remainingMinutes}m`;
    }

    startMetricsPolling() {
        // Fetch metrics immediately
        this.fetchMetrics();

        // Then every 5 seconds
        setInterval(() => {
            this.fetchMetrics();
        }, 5000);
    }

    startRepositoryStatusPolling() {
        // Fetch repository status immediately
        this.fetchRepositoryStatus();

        // Then every 3 seconds
        setInterval(() => {
            this.fetchRepositoryStatus();
        }, 3000);
    }

    async fetchRepositoryStatus() {
        try {
            const response = await fetch('/api/v1/git/status');

            if (!response.ok) {
                // If endpoint returns error, don't update UI
                this.setRepoBannerMessage('Nie udało się pobrać statusu repozytorium', 'error');
                return;
            }

            const data = await response.json();

            if (data.workspace_path && this.elements.workspacePathValue) {
                this.elements.workspacePathValue.textContent = data.workspace_path;
            }

            if (data.status === 'success' && data.is_git_repo) {
                this.updateRepositoryStatus(
                    data.branch,
                    data.has_changes,
                    data.modified_count
                );
            } else if (data.message) {
                this.updateRepositoryStatus('-', false, 0, data.message);
            } else {
                // Not a git repo or error
                const noRepoMessage = 'Brak repozytorium Git w workspace';
                this.updateRepositoryStatus('-', false, 0, noRepoMessage, 'info');
            }

        } catch (error) {
            console.error('Error fetching repository status:', error);
            this.setRepoBannerMessage('Błąd pobierania statusu repozytorium', 'error');
        }
    }

    refreshTabAccessibilityStates() {
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach((button) => {
            const isActive = button.classList.contains('active');
            button.setAttribute('role', 'tab');
            button.setAttribute('aria-selected', isActive ? 'true' : 'false');
            button.setAttribute('tabindex', isActive ? '0' : '-1');

            const tabName = button.dataset.tab;
            if (tabName) {
                button.setAttribute('aria-controls', `${tabName}Tab`);
            }
        });

        const tabContents = document.querySelectorAll('.tab-content');
        tabContents.forEach((content) => {
            content.setAttribute('role', 'tabpanel');
            const isActive = content.classList.contains('active');
            if (typeof content.toggleAttribute === 'function') {
                content.toggleAttribute('hidden', !isActive);
            } else if (!isActive) {
                content.setAttribute('hidden', 'hidden');
            } else {
                content.removeAttribute('hidden');
            }
        });

        this.updateTabDefaultIndicator();
    }

    initTabNavigation() {
        const tabButtons = Array.from(document.querySelectorAll('.tab-button'));
        if (!tabButtons.length) return;

        this.refreshTabAccessibilityStates();

        tabButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const tabName = button.dataset.tab;
                if (tabName) {
                    this.switchTab(tabName);
                }
            });

            button.addEventListener('keydown', (event) => {
                if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') {
                    return;
                }
                event.preventDefault();

                const direction = event.key === 'ArrowRight' ? 1 : -1;
                const currentIndex = tabButtons.indexOf(button);
                const nextIndex = (currentIndex + direction + tabButtons.length) % tabButtons.length;
                const nextButton = tabButtons[nextIndex];
                nextButton.focus();
                const nextTab = nextButton?.dataset?.tab;
                if (nextTab) {
                    this.switchTab(nextTab);
                }
            });
        });
    }

    initTabPreferencesControls() {
        if (this.elements.setDefaultTabBtn) {
            this.elements.setDefaultTabBtn.addEventListener('click', () => {
                if (this.activeTab) {
                    this.setDefaultTab(this.activeTab);
                }
            });
        }

        if (this.elements.resetDefaultTabBtn) {
            this.elements.resetDefaultTabBtn.addEventListener('click', () => {
                this.resetDefaultTab();
            });
        }

        this.updateDefaultTabLabel();
        this.updateTabDefaultIndicator();
    }

    initPreferencesCenter() {
        const modal = this.elements?.preferencesModal;
        const openBtn = this.elements?.openPreferencesCenterBtn;
        if (!modal || !openBtn) return;

        openBtn.addEventListener('click', () => {
            this.renderPreferencesSummary();
            this.populatePreferencesExportPayload(true);
            this.clearPreferencesImportField();
            this.showModal(modal);
        });

        this.elements?.closePreferencesModal?.addEventListener('click', () => {
            this.hideModal(modal);
        });

        modal.addEventListener('click', (event) => {
            if (event.target === modal) {
                this.hideModal(modal);
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && this.isModalVisible(modal)) {
                this.hideModal(modal);
            }
        });

        this.elements?.resetCockpitPreferencesBtn?.addEventListener('click', () => {
            this.resetCockpitPreferences();
        });

        this.elements?.resetExternalPreferencesBtn?.addEventListener('click', () => {
            this.resetExternalPreferences();
        });

        this.elements?.resetAllPreferencesBtn?.addEventListener('click', () => {
            this.resetAllPreferences();
        });

        this.elements?.copyPreferencesExportBtn?.addEventListener('click', () => {
            this.copyPreferencesExportPayload();
        });

        this.elements?.refreshPreferencesExportBtn?.addEventListener('click', () => {
            this.populatePreferencesExportPayload(true);
        });

        this.elements?.downloadPreferencesExportBtn?.addEventListener('click', () => {
            this.downloadPreferencesExport();
        });

        this.elements?.applyPreferencesImportBtn?.addEventListener('click', () => {
            this.applyPreferencesImport();
        });

        this.elements?.preferencesImportFileInput?.addEventListener('change', (event) => {
            const input = event.target;
            const file = input?.files?.[0];
            this.handlePreferencesFileSelection(file);
        });
    }

    renderPreferencesSummary() {
        if (this.elements?.preferencesSummary) {
            const cockpitItems = this.getCockpitPreferenceItems();
            this.elements.preferencesSummary.innerHTML = cockpitItems.length
                ? cockpitItems.map((item) => this.renderPreferenceCard(item)).join('')
                : this.renderEmptyPreferencesMessage('Brak zapisanych preferencji Cockpitu');
        }

        if (this.elements?.externalPreferencesSummary) {
            const externalItems = this.getExternalPreferenceItems();
            this.elements.externalPreferencesSummary.innerHTML = externalItems.length
                ? externalItems.map((item) => this.renderPreferenceCard(item)).join('')
                : this.renderEmptyPreferencesMessage('Brak zapisanych ustawień innych modułów');
        }
    }

    renderPreferenceCard(item) {
        const label = this.escapeHtml(item.label || '');
        const value = this.escapeHtml(item.value || '—');
        const meta = item.meta
            ? `<div class="preference-card__meta">${this.escapeHtml(item.meta)}</div>`
            : '';
        return `
            <article class="preference-card">
                <div class="preference-card__label">${label}</div>
                <div class="preference-card__value">${value}</div>
                ${meta}
            </article>
        `;
    }

    renderEmptyPreferencesMessage(message) {
        return `<div class="preferences-empty">${this.escapeHtml(message)}</div>`;
    }

    getCockpitPreferenceItems() {
        const items = [];
        const history = this.preferences?.history || {};
        const memory = this.preferences?.memory || {};
        const jobs = this.preferences?.jobs || {};
        const consolePrefs = this.preferences?.console || {};
        const general = this.preferences?.general || {};
        const lastActiveTab = this.safeGetLocalStorageItem('venomActiveTab');

        items.push({
            label: 'Domyślna zakładka',
            value: this.getTabDisplayName(general.defaultTab || 'feed'),
            meta: `Ostatnio otwarta: ${this.getTabDisplayName(lastActiveTab || this.activeTab || this.defaultTab || 'feed')}`
        });

        items.push({
            label: 'Historia',
            value: `Filtr: ${this.formatFilterLabel(history.filter)}`,
            meta: `Fraza: ${this.formatQueryLabel(history.query)} • Auto-refresh: ${this.formatBooleanLabel(history.autoRefresh, true)}`
        });

        items.push({
            label: 'Zadania w tle',
            value: `Filtr: ${this.formatFilterLabel(jobs.filter)}`,
            meta: `Fraza: ${this.formatQueryLabel(jobs.query)} • Auto-refresh: ${this.formatBooleanLabel(jobs.autoRefresh, true)}`
        });

        items.push({
            label: 'Pamięć',
            value: `Filtr: ${this.formatFilterLabel(memory.filter)}`,
            meta: `Fraza: ${this.formatQueryLabel(memory.query)} • Auto-refresh: ${this.formatBooleanLabel(memory.autoRefresh, true)}`
        });

        items.push({
            label: 'Lab Mode',
            value: this.consoleState.labMode ? 'Aktywny' : 'Wyłączony',
            meta: this.consoleState.labMode
                ? 'Nowe zadania nie zapisują lekcji'
                : 'Lekcje zapisywane są domyślnie'
        });

        return items;
    }

    getExternalPreferenceItems() {
        const items = [];

        const flowPrefs = this.safeParseJSON(this.safeGetLocalStorageItem('venomFlowInspectorPrefs'));
        items.push({
            label: 'Flow Inspector',
            value: flowPrefs ? `Filtr: ${this.formatFilterLabel(flowPrefs.filterStatus)}` : 'Domyślne ustawienia',
            meta: flowPrefs
                ? `Fraza: ${this.formatQueryLabel(flowPrefs.searchQuery)} • Auto-refresh: ${this.formatBooleanLabel(flowPrefs.autoRefresh, true)}`
                : 'Brak zapisanych preferencji Flow Inspector'
        });

        const inspectorPrefs = this.safeParseJSON(
            this.safeGetLocalStorageItem('venomInspectorUIPreferences')
        );
        const pinnedTraces = this.safeParseJSON(
            this.safeGetLocalStorageItem('inspectorPinnedTraces'),
            []
        );
        items.push({
            label: 'Inspector',
            value: inspectorPrefs
                ? `Filtr: ${this.formatFilterLabel(inspectorPrefs.filterStatus)}`
                : 'Domyślne ustawienia',
            meta: `Fraza: ${this.formatQueryLabel(inspectorPrefs?.searchQuery)} • Auto-refresh: ${this.formatBooleanLabel(inspectorPrefs?.autoRefresh, true)} • Przypięte ślady: ${
                Array.isArray(pinnedTraces) ? pinnedTraces.length : 0
            }`
        });

        const warRoomPrefs = this.safeParseJSON(this.safeGetLocalStorageItem('venomWarRoomPreferences'));
        items.push({
            label: 'War Room',
            value: warRoomPrefs ? 'Stan zapisany' : 'Domyślne ustawienia',
            meta: `Auto-refresh: ${this.formatBooleanLabel(warRoomPrefs?.autoRefresh, true)}`
        });

        const brainPrefs = this.safeParseJSON(this.safeGetLocalStorageItem('brainPreferences'));
        const enabledFilters = brainPrefs?.filters
            ? Object.values(brainPrefs.filters).filter(Boolean).length
            : 0;
        items.push({
            label: 'The Brain',
            value: brainPrefs
                ? `Aktywne filtry: ${enabledFilters}/${brainPrefs.filters ? Object.keys(brainPrefs.filters).length : 5}`
                : 'Domyślne ustawienia',
            meta: `Fraza: ${this.formatQueryLabel(brainPrefs?.searchQuery)} • Auto-refresh: ${this.formatBooleanLabel(brainPrefs?.autoRefresh, true)}`
        });

        return items;
    }

    resetCockpitPreferences(options = {}) {
        const { silent = false } = options;
        this.clearLocalStorageKeys(['venomUIPreferences', 'venomActiveTab']);
        this.preferences = this.loadUIPreferences();
        this.applyUIPreferences();
        this.saveUIPreferences();
        this.resetHistoryPreferences({ silent: true });
        this.resetJobsPreferences({ silent: true });
        this.resetMemoryPreferences({ silent: true });
        this.consoleState.labMode = false;
        if (this.elements.labModeCheckbox) {
            this.elements.labModeCheckbox.checked = false;
        }
        this.updateUIPreferences('console', { labMode: false });
        this.updateDefaultTabLabel();
        this.updateTabDefaultIndicator();
        this.switchTab(this.defaultTab || 'feed');

        if (!silent) {
            this.showNotification('Wyczyszczono preferencje Cockpitu', 'success');
        }
        this.renderPreferencesSummary();
    }

    resetExternalPreferences(options = {}) {
        const { silent = false } = options;
        this.clearLocalStorageKeys([
            'venomFlowInspectorPrefs',
            'venomInspectorUIPreferences',
            'inspectorPinnedTraces',
            'venomWarRoomPreferences',
            'brainPreferences'
        ]);
        if (!silent) {
            this.showNotification('Usunięto preferencje pozostałych modułów', 'info');
        }
        this.renderPreferencesSummary();
    }

    resetAllPreferences() {
        this.resetCockpitPreferences({ silent: true });
        this.resetExternalPreferences({ silent: true });
        this.showNotification('Wyczyszczono wszystkie preferencje VENOM UI', 'success');
        this.renderPreferencesSummary();
        this.populatePreferencesExportPayload();
    }

    formatBooleanLabel(value, defaultValue = false) {
        const normalized = value === undefined ? !!defaultValue : !!value;
        return normalized ? 'włączony' : 'wyłączony';
    }

    formatQueryLabel(value) {
        const trimmed = (value || '').trim();
        return trimmed ? `„${trimmed}”` : '—';
    }

    formatFilterLabel(value) {
        if (!value || value === 'all') {
            return 'wszystkie';
        }
        return value.replace(/_/g, ' ');
    }

    safeGetLocalStorageItem(key) {
        try {
            if (!window?.localStorage) return null;
            return window.localStorage.getItem(key);
        } catch (error) {
            console.warn('Nie można odczytać localStorage:', error);
            return null;
        }
    }

    safeParseJSON(value, fallback = null) {
        if (!value) return fallback;
        try {
            return JSON.parse(value);
        } catch (error) {
            console.warn('Nie można sparsować JSON z preferencji:', error);
            return fallback;
        }
    }

    clearLocalStorageKeys(keys = []) {
        keys.forEach((key) => {
            try {
                window?.localStorage?.removeItem(key);
            } catch (error) {
                console.warn(`Nie można usunąć klucza localStorage: ${key}`, error);
            }
        });
    }

    getPreferencesSnapshot() {
        return {
            generatedAt: new Date().toISOString(),
            cockpit: {
                venomUIPreferences: this.safeParseJSON(
                    this.safeGetLocalStorageItem('venomUIPreferences'),
                    {}
                ),
                venomActiveTab: this.safeGetLocalStorageItem('venomActiveTab'),
                labMode: !!this.consoleState.labMode
            },
            external: {
                flowInspector: this.safeParseJSON(
                    this.safeGetLocalStorageItem('venomFlowInspectorPrefs')
                ),
                inspector: this.safeParseJSON(
                    this.safeGetLocalStorageItem('venomInspectorUIPreferences')
                ),
                inspectorPinnedTraces: this.safeParseJSON(
                    this.safeGetLocalStorageItem('inspectorPinnedTraces'),
                    []
                ),
                warRoom: this.safeParseJSON(
                    this.safeGetLocalStorageItem('venomWarRoomPreferences')
                ),
                brain: this.safeParseJSON(this.safeGetLocalStorageItem('brainPreferences'))
            }
        };
    }

    populatePreferencesExportPayload(force = false) {
        if (!this.elements?.preferencesExportPayload) return;
        if (!force && this.elements.preferencesExportPayload.value) return;
        const snapshot = this.getPreferencesSnapshot();
        this.elements.preferencesExportPayload.value = JSON.stringify(snapshot, null, 2);
    }

    copyPreferencesExportPayload() {
        const textarea = this.elements?.preferencesExportPayload;
        if (!textarea) return;
        textarea.select();
        textarea.setSelectionRange(0, textarea.value.length);
        let copied = false;
        try {
            copied = document.execCommand('copy');
        } catch (error) {
            copied = false;
        }

        if (!copied && navigator?.clipboard?.writeText) {
            navigator.clipboard
                .writeText(textarea.value)
                .then(() => {
                    copied = true;
                })
                .catch(() => {
                    copied = false;
                });
        }

        this.showNotification(
            copied ? 'Skopiowano JSON z preferencjami' : 'Nie udało się skopiować JSON',
            copied ? 'success' : 'error'
        );
    }

    downloadPreferencesExport() {
        const snapshot = this.getPreferencesSnapshot();
        const filename = `venom-preferences-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
        const payload = JSON.stringify(snapshot, null, 2);
        try {
            const blob = new Blob([payload], { type: 'application/json' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(link.href);
            this.showNotification('Pobrano plik z ustawieniami', 'success');
        } catch (error) {
            console.error('Download preferences error:', error);
            this.showNotification('Nie udało się pobrać pliku z ustawieniami', 'error');
        }
    }

    clearPreferencesImportField() {
        if (this.elements?.preferencesImportInput) {
            this.elements.preferencesImportInput.value = '';
        }
        this.clearPreferencesImportFileInput();
    }

    applyPreferencesImport() {
        const input = this.elements?.preferencesImportInput;
        if (!input) return;
        const raw = input.value.trim();
        if (!raw) {
            this.showNotification('Wklej JSON z ustawieniami, aby rozpocząć import', 'warning');
            return;
        }

        try {
            const payload = JSON.parse(raw);
            const snapshot = this.normalizePreferencesImport(payload);
            this.persistImportedPreferences(snapshot);
            this.showNotification('Zaimportowano ustawienia – odświeżam Cockpit…', 'success');
            this.clearPreferencesImportFileInput();
            setTimeout(() => window.location.reload(), 800);
        } catch (error) {
            console.error('Import preferences error:', error);
            this.showNotification('Nie udało się sparsować JSON z ustawieniami', 'error');
        }
    }

    handlePreferencesFileSelection(file) {
        if (!file) {
            this.updateImportFileName('Brak wybranego pliku');
            return;
        }

        const reader = new FileReader();
        reader.onload = () => {
            const text = typeof reader.result === 'string' ? reader.result : '';
            if (this.elements?.preferencesImportInput) {
                this.elements.preferencesImportInput.value = text;
            }
            this.updateImportFileName(file.name, true);
            this.showNotification(
                `Wczytano ${file.name}. Zweryfikuj dane i kliknij „Wczytaj JSON”.`,
                'info'
            );
        };
        reader.onerror = () => {
            console.error('File import error:', reader.error);
            this.showNotification('Nie udało się odczytać pliku JSON', 'error');
            this.clearPreferencesImportFileInput();
        };

        reader.readAsText(file, 'utf-8');
    }

    clearPreferencesImportFileInput() {
        if (this.elements?.preferencesImportFileInput) {
            this.elements.preferencesImportFileInput.value = '';
        }
        this.updateImportFileName('Brak wybranego pliku');
    }

    updateImportFileName(label, loaded = false) {
        const target = this.elements?.preferencesImportFileName;
        if (!target) return;
        target.textContent = label || 'Brak wybranego pliku';
        target.classList.toggle('is-loaded', !!loaded);
    }

    normalizePreferencesImport(payload) {
        if (!payload || typeof payload !== 'object') {
            throw new Error('Nieprawidłowy format JSON');
        }

        if (payload.cockpit || payload.external) {
            return payload;
        }

        // Backwards compatibility: treat payload itself as cockpit prefs
        return {
            cockpit: {
                venomUIPreferences: payload.venomUIPreferences || payload.cockpit || {},
                venomActiveTab: payload.venomActiveTab || payload.activeTab || 'feed',
                labMode: payload.labMode
            },
            external: payload.external || {}
        };
    }

    persistImportedPreferences(snapshot) {
        if (!snapshot || typeof snapshot !== 'object') return;
        const cockpit = snapshot.cockpit || {};
        const external = snapshot.external || {};

        if (cockpit.venomUIPreferences) {
            try {
                window?.localStorage?.setItem(
                    'venomUIPreferences',
                    JSON.stringify(cockpit.venomUIPreferences)
                );
            } catch (error) {
                console.warn('Nie można zapisać venomUIPreferences z importu', error);
            }
        }

        if (cockpit.venomActiveTab) {
            try {
                window?.localStorage?.setItem('venomActiveTab', cockpit.venomActiveTab);
            } catch (error) {
                console.warn('Nie można zapisać venomActiveTab z importu', error);
            }
        }

        if (typeof cockpit.labMode === 'boolean') {
            this.preferences.console = { ...(this.preferences.console || {}), labMode: cockpit.labMode };
            this.saveUIPreferences();
        }

        if (external.flowInspector) {
            this.persistExternalKey('venomFlowInspectorPrefs', external.flowInspector);
        }
        if (external.inspector) {
            this.persistExternalKey('venomInspectorUIPreferences', external.inspector);
        }
        if (external.inspectorPinnedTraces) {
            this.persistExternalKey('inspectorPinnedTraces', external.inspectorPinnedTraces);
        }
        if (external.warRoom) {
            this.persistExternalKey('venomWarRoomPreferences', external.warRoom);
        }
        if (external.brain) {
            this.persistExternalKey('brainPreferences', external.brain);
        }
    }

    persistExternalKey(key, value) {
        try {
            window?.localStorage?.setItem(key, JSON.stringify(value));
        } catch (error) {
            console.warn(`Nie można zapisać ${key} z importu`, error);
        }
    }

    setDefaultTab(tabName) {
        if (!tabName) return;
        this.defaultTab = tabName;
        this.updateUIPreferences('general', { defaultTab: tabName });
        this.persistActiveTab(tabName);
        this.updateDefaultTabLabel();
        this.updateTabDefaultIndicator();
        this.showNotification(
            `Domyślna zakładka ustawiona na: ${this.getTabDisplayName(tabName)}`,
            'success'
        );
    }

    resetDefaultTab() {
        if (this.defaultTab === 'feed') {
            this.showNotification('Domyślna zakładka to już Transmisja', 'info');
            return;
        }
        this.defaultTab = 'feed';
        this.updateUIPreferences('general', { defaultTab: 'feed' });
        this.persistActiveTab('feed');
        this.updateDefaultTabLabel();
        this.updateTabDefaultIndicator();
        this.showNotification('Przywrócono domyślną zakładkę: Transmisja', 'info');
    }

    updateDefaultTabLabel() {
        if (this.elements.defaultTabLabel) {
            this.elements.defaultTabLabel.textContent = this.getTabDisplayName(this.defaultTab);
        }
    }

    updateTabDefaultIndicator() {
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach((btn) => {
            const isDefault = btn.dataset.tab === this.defaultTab;
            btn.classList.toggle('is-default', isDefault);
        });
    }

    getTabDisplayName(tabName) {
        const labels = {
            feed: 'Transmisja',
            voice: 'Głos',
            jobs: 'Zadania',
            memory: 'Pamięć',
            models: 'Modele',
            history: 'Historia'
        };
        return labels[tabName] || tabName;
    }

    persistActiveTab(tabName) {
        try {
            if (window?.localStorage) {
                window.localStorage.setItem('venomActiveTab', tabName);
            }
        } catch (error) {
            console.warn('Nie można zapisać aktywnej zakładki:', error);
        }
    }

    restoreSavedTabPreference() {
        let restored = false;
        try {
            if (window?.localStorage) {
                const savedTab = window.localStorage.getItem('venomActiveTab');
                if (savedTab && document.querySelector(`.tab-button[data-tab="${savedTab}"]`)) {
                    this.switchTab(savedTab);
                    restored = true;
                }
            }
        } catch (error) {
            console.warn('Nie można odczytać aktywnej zakładki:', error);
        }

        if (!restored) {
            this.switchTab(this.defaultTab || 'feed');
        }
    }

    loadUIPreferences() {
        const defaults = {
            general: { defaultTab: 'feed' },
            history: { filter: 'all', query: '', autoRefresh: true },
            memory: { filter: 'all', query: '', autoRefresh: true },
            jobs: { filter: 'all', query: '', autoRefresh: true },
            console: { labMode: false }
        };

        try {
            if (!window?.localStorage) {
                return defaults;
            }
            const raw = window.localStorage.getItem('venomUIPreferences');
            if (!raw) return defaults;
            const parsed = JSON.parse(raw);
            return {
                general: { ...defaults.general, ...(parsed?.general || {}) },
                history: { ...defaults.history, ...(parsed?.history || {}) },
                memory: { ...defaults.memory, ...(parsed?.memory || {}) },
                jobs: { ...defaults.jobs, ...(parsed?.jobs || {}) },
                console: { ...defaults.console, ...(parsed?.console || {}) }
            };
        } catch (error) {
            console.warn('Nie można wczytać preferencji UI:', error);
            return defaults;
        }
    }

    saveUIPreferences() {
        try {
            if (!window?.localStorage) {
                return;
            }
            window.localStorage.setItem('venomUIPreferences', JSON.stringify(this.preferences));
        } catch (error) {
            console.warn('Nie można zapisać preferencji UI:', error);
        }
    }

    applyUIPreferences() {
        const history = this.preferences.history || {};
        this.historyState.filter = history.filter || 'all';
        this.historyState.query = history.query || '';
        this.historyState.autoRefresh =
            history.autoRefresh === undefined ? true : !!history.autoRefresh;

        const memory = this.preferences.memory || {};
        this.memoryState.filter = memory.filter || 'all';
        this.memoryState.query = memory.query || '';
        this.memoryState.autoRefresh =
            memory.autoRefresh === undefined ? true : !!memory.autoRefresh;

        const jobs = this.preferences.jobs || {};
        this.jobsState.filter = jobs.filter || 'all';
        this.jobsState.query = jobs.query || '';
        this.jobsState.autoRefresh =
            jobs.autoRefresh === undefined ? true : !!jobs.autoRefresh;

        const consolePrefs = this.preferences.console || {};
        this.consoleState.labMode =
            consolePrefs.labMode === undefined ? false : !!consolePrefs.labMode;

        const generalPrefs = this.preferences.general || {};
        this.defaultTab = generalPrefs.defaultTab || 'feed';
    }

    updateUIPreferences(section, values) {
        if (!this.preferences[section]) {
            this.preferences[section] = {};
        }
        this.preferences[section] = {
            ...this.preferences[section],
            ...values
        };
        this.saveUIPreferences();
    }

    // Memory Tab Functions
    initMemoryTab() {
        this.initMemoryControls();

        if (this.elements.refreshLessons) {
            this.elements.refreshLessons.addEventListener('click', () => {
                this.fetchLessons({ showLoading: true });
            });
        }

        if (this.elements.scanGraph) {
            this.elements.scanGraph.addEventListener('click', () => {
                this.triggerGraphScan();
            });
        }

        // Initial load
        this.fetchLessons({ showLoading: true });
        this.fetchGraphSummary();
    }

    switchTab(tabName) {
        if (!tabName) return;
        if (this.activeTab === tabName) {
            this.refreshTabAccessibilityStates();
            return;
        }

        const targetButton = document.querySelector(`.tab-button[data-tab="${tabName}"]`);
        const targetContent = document.getElementById(`${tabName}Tab`);
        if (!targetButton || !targetContent) {
            return;
        }

        document.querySelectorAll('.tab-button').forEach((btn) => {
            btn.classList.toggle('active', btn === targetButton);
        });

        document.querySelectorAll('.tab-content').forEach((content) => {
            content.classList.toggle('active', content === targetContent);
        });

        this.refreshTabAccessibilityStates();

        this.stopJobsAutoRefresh();
        this.stopMemoryAutoRefresh();
        if (tabName !== 'history') {
            this.stopHistoryAutoRefresh();
        }

        switch (tabName) {
            case 'voice':
                break;
            case 'jobs': {
                const shouldShowLoading = this.jobsState.jobs.length === 0;
                this.fetchBackgroundJobsStatus({ showLoading: shouldShowLoading });
                if (this.jobsState.autoRefresh) {
                    this.startJobsAutoRefresh({ immediate: false });
                }
                break;
            }
            case 'memory': {
                const shouldShowLoading = this.memoryState.lessons.length === 0;
                this.fetchLessons({ showLoading: shouldShowLoading });
                this.fetchGraphSummary();
                if (this.memoryState.autoRefresh) {
                    this.startMemoryAutoRefresh({ immediate: false });
                }
                break;
            }
            case 'models':
                this.fetchModels();
                this.fetchModelsUsage();
                break;
            case 'history': {
                if (this.historyState.autoRefresh) {
                    this.startHistoryAutoRefresh({ immediate: true });
                } else {
                    const shouldShowLoading = this.historyState.requests.length === 0;
                    this.loadHistory({ showLoading: shouldShowLoading });
                }
                break;
            }
            default:
                // feed tab: nothing special
                break;
        }

        this.activeTab = tabName;
        this.persistActiveTab(tabName);
    }

    async fetchLessons(options = {}) {
        const { showLoading = false } = options;
        if (showLoading) {
            this.memoryState.loading = true;
            this.memoryState.error = null;
            this.renderLessonsList();
        }

        try {
            const response = await fetch('/api/v1/lessons?limit=10');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            if (data.status === 'success' && Array.isArray(data.lessons)) {
                this.memoryState.lessons = data.lessons;
                this.memoryState.error = null;
            } else {
                this.memoryState.lessons = [];
                this.memoryState.error = 'Brak lekcji';
            }
        } catch (error) {
            console.error('Error fetching lessons:', error);
            this.memoryState.lessons = [];
            this.memoryState.error = 'Błąd ładowania lekcji';
        } finally {
            this.memoryState.loading = false;
            this.memoryState.lastUpdated = new Date();
            this.updateMemoryLastUpdated();
            this.renderLessonsList();
        }
    }

    async fetchGraphSummary() {
        const defaultSummary = { total_nodes: 0, total_edges: 0 };
        try {
            const response = await fetch('/api/v1/graph/summary');
            const data = await response.json();

            const graphSummary = document.getElementById('graphSummary');
            if (!graphSummary) return;

            if (data.status === 'success' && data.summary) {
                const summary = data.summary;
                this.memoryState.graphSummary = {
                    total_nodes: summary.total_nodes || 0,
                    total_edges: summary.total_edges || 0
                };
                this.updateMemoryGraphInsights();

                // Wyczyść poprzednią zawartość
                graphSummary.innerHTML = '';

                // Helper do tworzenia statystyki - bezpieczne użycie textContent
                const createStat = (label, value) => {
                    const statDiv = document.createElement('div');
                    statDiv.className = 'graph-stat';

                    const labelSpan = document.createElement('span');
                    labelSpan.className = 'graph-stat-label';
                    labelSpan.textContent = label;

                    const valueSpan = document.createElement('span');
                    valueSpan.className = 'graph-stat-value';
                    valueSpan.textContent = String(value);

                    statDiv.appendChild(labelSpan);
                    statDiv.appendChild(valueSpan);
                    return statDiv;
                };

                // Dodaj statystyki używając bezpiecznego DOM manipulation
                graphSummary.appendChild(createStat('Węzły', summary.total_nodes || 0));
                graphSummary.appendChild(createStat('Krawędzie', summary.total_edges || 0));
                graphSummary.appendChild(createStat('Pliki', (summary.node_types && summary.node_types.file) || 0));
                graphSummary.appendChild(createStat('Klasy', (summary.node_types && summary.node_types.class) || 0));
                graphSummary.appendChild(createStat('Funkcje', (summary.node_types && summary.node_types.function) || 0));
            } else {
                this.memoryState.graphSummary = defaultSummary;
                this.updateMemoryGraphInsights();
                graphSummary.textContent = '';
                const p = document.createElement('p');
                p.className = 'empty-state';
                p.textContent = 'Brak danych grafu';
                graphSummary.appendChild(p);
            }
        } catch (error) {
            console.error('Error fetching graph summary:', error);
            const graphSummary = document.getElementById('graphSummary');
            if (graphSummary) {
                graphSummary.textContent = '';
                const p = document.createElement('p');
                p.className = 'empty-state';
                p.textContent = 'Błąd ładowania grafu';
                graphSummary.appendChild(p);
            }
            this.memoryState.graphSummary = defaultSummary;
            this.updateMemoryGraphInsights();
        }
    }

    async triggerGraphScan() {
        try {
            const scanButton = document.getElementById('scanGraph');
            if (scanButton) {
                scanButton.textContent = '⏳ Skanowanie...';
                scanButton.disabled = true;
            }

            const response = await fetch('/api/v1/graph/scan', {
                method: 'POST'
            });
            const data = await response.json();

            if (data.status === 'success') {
                this.showNotification('Skanowanie zakończone pomyślnie', 'success');
                // Odśwież podsumowanie
                setTimeout(() => {
                    this.fetchGraphSummary();
                }, 1000);
            } else {
                this.showNotification('Błąd skanowania', 'error');
            }
        } catch (error) {
            console.error('Error triggering graph scan:', error);
            this.showNotification('Błąd podczas skanowania', 'error');
        } finally {
            const scanButton = document.getElementById('scanGraph');
            if (scanButton) {
                scanButton.textContent = '🛰️ Zeskanuj graf';
                scanButton.disabled = false;
            }
        }
    }

    // Models Tab Functions (THE_ARMORY)
    initModelsTab() {
        // Setup refresh button
        const refreshModels = document.getElementById('refreshModels');
        if (refreshModels) {
            refreshModels.addEventListener('click', () => {
                this.fetchModels();
                this.fetchModelsUsage();
            });
        }

        // Setup install button
        const installModelBtn = document.getElementById('installModelBtn');
        if (installModelBtn) {
            installModelBtn.addEventListener('click', () => {
                this.installModel();
            });
        }

        // Setup unload all button
        const unloadAllBtn = document.getElementById('unloadAllBtn');
        if (unloadAllBtn) {
            unloadAllBtn.addEventListener('click', () => {
                this.unloadAllModels();
            });
        }

        // Setup input enter key
        const modelNameInput = document.getElementById('modelNameInput');
        if (modelNameInput) {
            modelNameInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.installModel();
                }
            });
        }
    }

    async fetchModels() {
        try {
            const response = await fetch('/api/v1/models');
            const data = await response.json();

            const modelsList = document.getElementById('modelsList');
            if (!modelsList) return;

            if (data.success && data.models && data.models.length > 0) {
                this.modelsState.list = data.models;
                this.modelsState.lastUpdated = new Date();
                modelsList.innerHTML = '';
                data.models.forEach(model => {
                    const modelItem = this.createModelElement(model);
                    modelsList.appendChild(modelItem);
                });
                this.updateModelsInsights();
            } else {
                this.modelsState.list = [];
                this.modelsState.lastUpdated = new Date();
                modelsList.innerHTML = '<p class="empty-state">Brak modeli</p>';
                this.updateModelsInsights([]);
            }
        } catch (error) {
            console.error('Error fetching models:', error);
            const modelsList = document.getElementById('modelsList');
            if (modelsList) {
                modelsList.innerHTML = '<p class="empty-state">Błąd ładowania modeli</p>';
            }
            this.modelsState.list = [];
            this.updateModelsInsights([]);
        }
    }

    createModelElement(model) {
        const container = document.createElement('article');
        container.className = 'model-card';
        if (model.active) {
            container.classList.add('model-card--active');
        }

        const header = document.createElement('div');
        header.className = 'model-card__header';

        const nameDiv = document.createElement('div');
        nameDiv.className = 'model-card__name';
        nameDiv.textContent = model.name || '---';

        const typeSpan = document.createElement('span');
        typeSpan.className = 'model-card__type';
        typeSpan.textContent = (model.type || 'unknown').toUpperCase();

        header.appendChild(nameDiv);
        header.appendChild(typeSpan);

        const info = document.createElement('div');
        info.className = 'model-card__meta';
        const sizeValue = Number(model.size_gb);
        const sizeLabel = Number.isFinite(sizeValue) ? `${sizeValue.toFixed(2)} GB` : 'N/A';
        const metaParts = [`Rozmiar: ${sizeLabel}`];
        if (model.quantization && model.quantization !== 'unknown') {
            metaParts.push(`Kwantyzacja: ${model.quantization}`);
        }
        info.textContent = metaParts.join(' · ');

        const actions = document.createElement('div');
        actions.className = 'model-card__actions';

        const activateBtn = document.createElement('button');
        activateBtn.type = 'button';
        activateBtn.className = 'btn-small model-action model-action--activate';
        activateBtn.textContent = model.active ? '✅ Aktywny' : '🔄 Aktywuj';
        if (model.active) {
            activateBtn.classList.add('is-active');
            activateBtn.disabled = true;
        } else {
            activateBtn.addEventListener('click', () => {
                this.switchModel(model.name);
            });
        }

        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'btn-small model-action model-action--danger';
        deleteBtn.textContent = '🗑️ Usuń';
        deleteBtn.addEventListener('click', () => {
            this.deleteModel(model.name);
        });

        actions.appendChild(activateBtn);
        actions.appendChild(deleteBtn);

        container.appendChild(header);
        container.appendChild(info);
        container.appendChild(actions);

        return container;
    }

    updateModelsInsights(list = null) {
        const models = Array.isArray(list) ? list : this.modelsState.list || [];
        const installed = models.length;
        const active = models.filter((model) => !!model.active).length;
        const totalSize = models.reduce((sum, model) => {
            const size = Number(model.size_gb);
            return sum + (Number.isFinite(size) ? size : 0);
        }, 0);
        const quantizations = [...new Set(models.map((m) => (m.quantization || 'unknown').toUpperCase()))]
            .filter((q) => q && q !== 'UNKNOWN');

        if (this.elements.modelsInstalledCount) {
            this.elements.modelsInstalledCount.textContent = installed;
        }
        if (this.elements.modelsActiveCount) {
            this.elements.modelsActiveCount.textContent = active;
        }
        if (this.elements.modelsTotalSize) {
            this.elements.modelsTotalSize.textContent = `${totalSize.toFixed(1)} GB`;
        }
        if (this.elements.modelsQuantSummary) {
            this.elements.modelsQuantSummary.textContent = quantizations.length
                ? `Quant: ${quantizations.join(', ')}`
                : 'Quant: -';
        }
        if (this.elements.modelsLastUpdated) {
            const timestamp = this.modelsState.lastUpdated;
            this.elements.modelsLastUpdated.textContent = timestamp
                ? timestamp.toLocaleTimeString('pl-PL')
                : '-';
        }
    }

    async fetchModelsUsage() {
        try {
            const response = await fetch('/api/v1/models/usage');
            const data = await response.json();

            if (data.success && data.usage) {
                const usage = data.usage;

                const cpuUsageEl = document.getElementById('modelsCpuUsage');
                if (cpuUsageEl) {
                    cpuUsageEl.textContent = typeof usage.cpu_usage_percent === 'number'
                        ? `${usage.cpu_usage_percent.toFixed(1)}%`
                        : 'N/A';
                }

                const gpuUsageEl = document.getElementById('modelsGpuUsage');
                if (gpuUsageEl) {
                    if (typeof usage.gpu_usage_percent === 'number') {
                        gpuUsageEl.textContent = `${usage.gpu_usage_percent.toFixed(1)}%`;
                    } else if (typeof usage.vram_usage_mb === 'number' && usage.vram_usage_mb > 0) {
                        gpuUsageEl.textContent = 'Aktywne';
                    } else {
                        gpuUsageEl.textContent = 'N/A';
                    }
                }

                const ramUsageEl = document.getElementById('modelsRamUsage');
                const ramPercentEl = document.getElementById('modelsRamPercent');
                if (ramUsageEl) {
                    if (typeof usage.memory_used_gb === 'number' && typeof usage.memory_total_gb === 'number') {
                        ramUsageEl.textContent = `${usage.memory_used_gb.toFixed(1)} GB / ${usage.memory_total_gb.toFixed(1)} GB`;
                    } else {
                        ramUsageEl.textContent = 'N/A';
                    }
                }
                if (ramPercentEl) {
                    ramPercentEl.textContent = typeof usage.memory_usage_percent === 'number'
                        ? `${usage.memory_usage_percent.toFixed(0)}%`
                        : 'N/A';
                }

                // Update disk usage
                const diskUsageEl = document.getElementById('modelsDiskUsage');
                const diskPercentEl = document.getElementById('modelsDiskPercent');
                if (diskUsageEl) {
                    diskUsageEl.textContent = `${usage.disk_usage_gb.toFixed(2)} GB / ${usage.disk_limit_gb} GB`;
                }
                if (diskPercentEl) {
                    diskPercentEl.textContent = typeof usage.disk_usage_percent === 'number'
                        ? `${usage.disk_usage_percent.toFixed(1)}%`
                        : 'N/A';
                }

                // Update VRAM usage
                const vramUsageEl = document.getElementById('modelsVramUsage');
                const vramPercentEl = document.getElementById('modelsVramPercent');
                if (vramUsageEl) {
                    if (typeof usage.vram_usage_mb === 'number' && usage.vram_usage_mb > 0) {
                        const usedGb = usage.vram_usage_mb / 1024;
                        if (typeof usage.vram_total_mb === 'number' && usage.vram_total_mb > 0) {
                            const totalGb = usage.vram_total_mb / 1024;
                            vramUsageEl.textContent = `${usedGb.toFixed(1)} GB / ${totalGb.toFixed(1)} GB`;
                        } else {
                            vramUsageEl.textContent = `${usedGb.toFixed(1)} GB`;
                        }
                    } else {
                        vramUsageEl.textContent = 'N/A';
                    }
                }
                if (vramPercentEl) {
                    if (typeof usage.vram_usage_percent === 'number') {
                        vramPercentEl.textContent = `${usage.vram_usage_percent.toFixed(0)}%`;
                    } else if (
                        typeof usage.vram_usage_mb === 'number' &&
                        typeof usage.vram_total_mb === 'number' &&
                        usage.vram_total_mb > 0
                    ) {
                        const percent = (usage.vram_usage_mb / usage.vram_total_mb) * 100;
                        vramPercentEl.textContent = `${percent.toFixed(0)}%`;
                    } else {
                        vramPercentEl.textContent = 'N/A';
                    }
                }

                // Update models count
                const modelsCountEl = document.getElementById('modelsCount');
                if (modelsCountEl) {
                    modelsCountEl.textContent = usage.models_count;
                }
            }
        } catch (error) {
            console.error('Error fetching models usage:', error);
        }
    }

    async installModel() {
        const modelNameInput = document.getElementById('modelNameInput');
        const installBtn = document.getElementById('installModelBtn');
        const progressDiv = document.getElementById('downloadProgress');
        const progressBar = document.getElementById('downloadProgressBar');
        const progressText = document.getElementById('downloadProgressText');

        if (!modelNameInput || !installBtn) return;

        const modelName = modelNameInput.value.trim();
        if (!modelName) {
            this.showNotification('Wprowadź nazwę modelu', 'warning');
            return;
        }

        try {
            installBtn.disabled = true;
            installBtn.textContent = '⏳ Pobieranie...';

            const response = await fetch('/api/v1/models/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: modelName })
            });

            const data = await response.json();

            if (!response.ok) {
                // Resource Guard blocked or other error
                if (response.status === 400) {
                    this.showNotification('Brak miejsca na dysku! Usuń nieużywane modele.', 'error');
                } else {
                    this.showNotification(data.detail || 'Błąd podczas pobierania', 'error');
                }
                return;
            }

            if (data.success) {
                // Show progress bar
                if (progressDiv) {
                    progressDiv.classList.remove('is-hidden');
                    if (progressBar) progressBar.style.width = '10%';
                    if (progressText) progressText.textContent = `Pobieranie ${modelName}...`;
                }

                this.showNotification(`Pobieranie ${modelName} rozpoczęte w tle`, 'info');
                modelNameInput.value = '';

                // TODO: Zastąpić symulacją przez rzeczywisty progress tracking z WebSocket
                // Simulate progress (temporary - should use WebSocket updates in production)
                let progress = 10;
                let progressInterval = null;
                let checkInterval = null;

                try {
                    progressInterval = setInterval(() => {
                        progress += 5;
                        if (progress >= 90) {
                            if (progressInterval) clearInterval(progressInterval);
                            if (progressText) progressText.textContent = 'Finalizowanie...';
                        }
                        if (progressBar) progressBar.style.width = `${progress}%`;
                    }, 1000);

                    // Zamiast sztywnego timeoutu, okresowo sprawdzaj status instalacji modelu
                    checkInterval = setInterval(async () => {
                        try {
                            const response = await fetch('/api/v1/models');
                            const data = await response.json();
                            const model = data.models.find(m => m.name === modelName);
                            if (model) {
                                if (checkInterval) clearInterval(checkInterval);
                                if (progressInterval) clearInterval(progressInterval);
                                if (progressDiv) progressDiv.classList.add('is-hidden');
                                if (progressBar) progressBar.style.width = '0%';
                                this.fetchModels();
                                this.fetchModelsUsage();
                                this.showNotification(`Model ${modelName} zainstalowany`, 'success');
                            }
                        } catch (error) {
                            console.error('Error checking model status:', error);
                        }
                    }, 5000); // Sprawdzaj co 5 sekund
                } catch (error) {
                    if (progressInterval) clearInterval(progressInterval);
                    if (checkInterval) clearInterval(checkInterval);
                    throw error;
                }
            }
        } catch (error) {
            console.error('Error installing model:', error);
            this.showNotification('Błąd podczas pobierania modelu', 'error');
        } finally {
            if (installBtn) {
                installBtn.disabled = false;
                installBtn.textContent = '📥 Pobierz';
            }
        }
    }

    async switchModel(modelName) {
        if (!confirm(`Czy na pewno chcesz aktywować model: ${modelName}?`)) {
            return;
        }

        try {
            const response = await fetch('/api/v1/models/switch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: modelName })
            });

            const data = await response.json();

            if (data.success) {
                this.showNotification(`Model ${modelName} aktywowany`, 'success');
                await this.fetchModels();
            } else {
                this.showNotification('Błąd podczas zmiany modelu', 'error');
            }
        } catch (error) {
            console.error('Error switching model:', error);
            this.showNotification('Błąd podczas zmiany modelu', 'error');
        }
    }

    async deleteModel(modelName) {
        if (!confirm(`Czy na pewno chcesz usunąć model: ${modelName}?\n\nTej operacji nie można cofnąć.`)) {
            return;
        }

        try {
            const response = await fetch(`/api/v1/models/${encodeURIComponent(modelName)}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (!response.ok) {
                if (response.status === 400) {
                    this.showNotification('Nie można usunąć aktywnego modelu', 'warning');
                } else {
                    this.showNotification(data.detail || 'Błąd podczas usuwania', 'error');
                }
                return;
            }

            if (data.success) {
                this.showNotification(`Model ${modelName} usunięty`, 'success');
                await this.fetchModels();
                await this.fetchModelsUsage();
            }
        } catch (error) {
            console.error('Error deleting model:', error);
            this.showNotification('Błąd podczas usuwania modelu', 'error');
        }
    }

    async unloadAllModels() {
        if (!confirm('🚨 PANIC BUTTON\n\nCzy na pewno chcesz zwolnić wszystkie zasoby modeli?\n\nTo może wymagać restartu serwisu Ollama.')) {
            return;
        }

        try {
            const response = await fetch('/api/v1/models/unload-all', {
                method: 'POST'
            });

            const data = await response.json();

            if (data.success) {
                this.showNotification('Wszystkie zasoby zwolnione', 'success');
                await this.fetchModels();
                await this.fetchModelsUsage();
            } else {
                this.showNotification('Błąd podczas zwalniania zasobów', 'error');
            }
        } catch (error) {
            console.error('Error unloading models:', error);
            this.showNotification('Błąd podczas zwalniania zasobów', 'error');
        }
    }

    // Update repository status in header
    updateRepositoryStatus(branch, hasChanges, changeCount = 0, message = null, messageVariant = 'warning') {
        if (!this.elements.branchName || !this.elements.repoChanges) {
            return;
        }

        const hasRepo = !message;

        if (this.elements.workspacePathValue) {
            this.elements.workspacePathValue.classList.toggle('is-hidden', !hasRepo);
        }

        if (this.elements.syncRepoBtn) {
            this.elements.syncRepoBtn.disabled = !hasRepo;
            this.elements.syncRepoBtn.title = hasRepo
                ? 'Synchronizuj repozytorium'
                : 'Synchronizacja dostępna po utworzeniu repozytorium';
        }

        if (this.elements.undoChangesBtn) {
            this.elements.undoChangesBtn.disabled = !hasRepo;
            this.elements.undoChangesBtn.title = hasRepo
                ? 'Cofnij wszystkie zmiany'
                : 'Brak repozytorium - najpierw je zainicjalizuj';
        }

        if (this.elements.initRepoBtn) {
            this.elements.initRepoBtn.classList.toggle('is-hidden', hasRepo);
        }

        // Update branch name
        this.elements.branchName.textContent = branch || '-';

        if (message) {
            this.elements.repoChanges.classList.remove('dirty');
            this.elements.repoChanges.innerHTML = `⚪ <span id="changesText">Niedostępne</span>`;
            this.setRepoBannerMessage(message, messageVariant);
            this.elements.changesText = document.getElementById('changesText');
            return;
        }

        // Update changes status
        if (hasChanges) {
            this.elements.repoChanges.classList.add('dirty');
            const filesText = changeCount === 1 ? 'zmodyfikowany plik' : 'zmodyfikowanych plików';
            this.elements.repoChanges.innerHTML = `🔴 <span id="changesText">${changeCount} ${filesText}</span>`;
            this.setRepoBannerMessage(`Wykryto ${changeCount} ${filesText}`, 'warning');
        } else {
            this.elements.repoChanges.classList.remove('dirty');
            this.elements.repoChanges.innerHTML = `🟢 <span id="changesText">Brak zmian</span>`;
            this.setRepoBannerMessage('Repozytorium zsynchronizowane', 'success');
        }

        // Re-cache the changesText reference after innerHTML update
        this.elements.changesText = document.getElementById('changesText');
    }

    async initRepositoryFlow() {
        const promptMessage = [
            'Workspace nie jest repozytorium Git.',
            'Podaj nazwę lub URL repozytorium do sklonowania.',
            'Pozostaw puste aby utworzyć lokalne repozytorium.'
        ].join('\n');

        const userInput = window.prompt(promptMessage, '');
        if (userInput === null) {
            return;
        }

        const trimmed = userInput.trim();
        const payload = trimmed ? { url: trimmed } : {};

        try {
            const response = await fetch('/api/v1/git/init', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (!response.ok || data.status === 'error') {
                const message = data.message || data.detail || 'Nie udało się zainicjalizować repozytorium';
                this.showNotification(message, 'error');
                return;
            }

            this.showNotification(data.message || 'Repozytorium zainicjalizowane', 'success');
            this.fetchRepositoryStatus();
        } catch (error) {
            console.error('Error initializing repository:', error);
            this.showNotification('Błąd podczas inicjalizacji repozytorium', 'error');
        }
    }

    async handleSyncRepo() {
        try {
            this.showNotification('Sprawdzam możliwość synchronizacji...', 'info');

            const response = await fetch('/api/v1/git/sync', {
                method: 'POST'
            });

            if (response.status === 501) {
                // Not implemented
                const data = await response.json();
                this.showNotification(data.detail || 'Funkcja nie jest jeszcze dostępna', 'warning');
                return;
            }

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            this.showNotification(data.message || 'Synchronizacja zakończona', 'success');
        } catch (error) {
            console.error('Error syncing repository:', error);
            this.showNotification('Błąd podczas synchronizacji', 'error');
        }
    }

    async handleUndoChanges() {
        // Ask for confirmation before destructive operation
        if (!confirm('Czy na pewno chcesz cofnąć wszystkie zmiany? Ta operacja jest nieodwracalna!')) {
            return;
        }

        try {
            this.showNotification('Sprawdzam możliwość cofnięcia zmian...', 'warning');

            const response = await fetch('/api/v1/git/undo', {
                method: 'POST'
            });

            if (response.status === 501) {
                // Not implemented
                const data = await response.json();
                this.showNotification(data.detail || 'Funkcja nie jest jeszcze dostępna', 'warning');
                return;
            }

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            this.showNotification(data.message || 'Zmiany cofnięte', 'success');
            // Refresh status after undo
            this.fetchRepositoryStatus();
        } catch (error) {
            console.error('Error undoing changes:', error);
            this.showNotification('Błąd podczas cofania zmian', 'error');
        }
    }

    // Background Jobs Tab Functions
    initBackgroundJobsTab() {
        // Setup control buttons
        const pauseBtn = document.getElementById('pauseJobsBtn');
        const resumeBtn = document.getElementById('resumeJobsBtn');

        if (pauseBtn) {
            pauseBtn.addEventListener('click', () => this.pauseBackgroundJobs());
        }

        if (resumeBtn) {
            resumeBtn.addEventListener('click', () => this.resumeBackgroundJobs());
        }
    }

    async fetchBackgroundJobsStatus(options = {}) {
        const { showLoading = false } = options;
        if (showLoading) {
            this.jobsState.loading = true;
            this.jobsState.error = null;
            this.renderJobsList();
        }

        try {
            await Promise.all([
                this.fetchSchedulerStatus(),
                this.fetchSchedulerJobs(),
                this.fetchWatcherStatus(),
                this.fetchDocumenterStatus(),
                this.fetchGardenerStatus()
            ]);
            this.jobsState.lastUpdated = new Date();
        } catch (error) {
            console.error('Error fetching background jobs:', error);
        } finally {
            this.jobsState.loading = false;
            this.updateJobsLastUpdated();
            this.renderJobsList();
        }
    }

    async fetchSchedulerStatus() {
        try {
            const response = await fetch('/api/v1/scheduler/status');
            if (!response.ok) throw new Error('Failed to fetch scheduler status');

            const data = await response.json();
            const statusDiv = document.getElementById('schedulerStatus');

            if (data.status === 'success') {
                const scheduler = data.scheduler;
                statusDiv.innerHTML = `
                    <div class="status-item">
                        <span class="status-label">Status:</span>
                        <span class="status-value ${scheduler.is_running ? 'status-active' : 'status-inactive'}">
                            ${scheduler.is_running ? '🟢 Działa' : '🔴 Zatrzymany'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Liczba zadań:</span>
                        <span class="status-value">${scheduler.jobs_count}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Wstrzymany:</span>
                        <span class="status-value">${scheduler.paused ? '⏸️ Tak' : '▶️ Nie'}</span>
                    </div>
                `;
                this.setJobsStatusPill(
                    'schedulerStatusPill',
                    scheduler.is_running ? 'Aktywny' : 'Zatrzymany',
                    scheduler.is_running
                );
            } else {
                statusDiv.innerHTML = '<p class="error-state">❌ Nie można pobrać statusu schedulera</p>';
                this.setJobsStatusPill('schedulerStatusPill', 'Błąd', false);
            }
        } catch (error) {
            console.error('Error fetching scheduler status:', error);
            document.getElementById('schedulerStatus').innerHTML =
                '<p class="error-state">❌ Nie można pobrać statusu schedulera</p>';
            this.setJobsStatusPill('schedulerStatusPill', 'Błąd', false);
        }
    }

    async fetchSchedulerJobs() {
        try {
            const response = await fetch('/api/v1/scheduler/jobs');
            if (!response.ok) throw new Error('Failed to fetch jobs');

            const data = await response.json();
            this.jobsState.jobs = Array.isArray(data.jobs) ? data.jobs : [];
            this.jobsState.error = null;
        } catch (error) {
            console.error('Error fetching jobs:', error);
            this.jobsState.jobs = [];
            this.jobsState.error = '❌ Nie można pobrać listy zadań';
        }
    }

    async fetchWatcherStatus() {
        try {
            const response = await fetch('/api/v1/watcher/status');
            if (!response.ok) throw new Error('Failed to fetch watcher status');

            const data = await response.json();
            const statusDiv = document.getElementById('watcherStatus');

            if (data.status === 'success') {
                const watcher = data.watcher;
                const workspaceRoot = this.escapeHtml(watcher.workspace_root || '-');
                const extensions = Array.isArray(watcher.monitoring_extensions)
                    ? watcher.monitoring_extensions.join(', ')
                    : 'brak danych';
                statusDiv.innerHTML = `
                    <div class="status-item">
                        <span class="status-label">Status:</span>
                        <span class="status-value ${watcher.is_running ? 'status-active' : 'status-inactive'}">
                            ${watcher.is_running ? '🟢 Aktywny' : '🔴 Zatrzymany'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Katalog roboczy:</span>
                        <span class="status-value">${workspaceRoot}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Monitorowane rozszerzenia:</span>
                        <span class="status-value">${this.escapeHtml(extensions)}</span>
                    </div>
                `;
                this.setJobsStatusPill('watcherStatusPill', watcher.is_running ? 'Aktywny' : 'Zatrzymany', watcher.is_running);
            } else {
                statusDiv.innerHTML = '<p class="error-state">❌ Nie można pobrać statusu watchera</p>';
                this.setJobsStatusPill('watcherStatusPill', 'Błąd', false);
            }
        } catch (error) {
            console.error('Error fetching watcher status:', error);
            document.getElementById('watcherStatus').innerHTML =
                '<p class="error-state">❌ Nie można pobrać statusu watchera</p>';
            this.setJobsStatusPill('watcherStatusPill', 'Błąd', false);
        }
    }

    async fetchDocumenterStatus() {
        try {
            const response = await fetch('/api/v1/documenter/status');
            if (!response.ok) throw new Error('Failed to fetch documenter status');

            const data = await response.json();
            const statusDiv = document.getElementById('documenterStatus');

            if (data.status === 'success') {
                const documenter = data.documenter;
                statusDiv.innerHTML = `
                    <div class="status-item">
                        <span class="status-label">Włączony:</span>
                        <span class="status-value ${documenter.enabled ? 'status-active' : 'status-inactive'}">
                            ${documenter.enabled ? '🟢 Tak' : '🔴 Nie'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Przetwarzane pliki:</span>
                        <span class="status-value">${this.escapeHtml(String(documenter.processing_files || '0'))}</span>
                    </div>
                `;
                this.setJobsStatusPill(
                    'documenterStatusPill',
                    documenter.enabled ? 'Aktywny' : 'Nieaktywny',
                    documenter.enabled
                );
            } else {
                statusDiv.innerHTML = '<p class="error-state">❌ Nie można pobrać statusu documentera</p>';
                this.setJobsStatusPill('documenterStatusPill', 'Błąd', false);
            }
        } catch (error) {
            console.error('Error fetching documenter status:', error);
            document.getElementById('documenterStatus').innerHTML =
                '<p class="error-state">❌ Nie można pobrać statusu documentera</p>';
            this.setJobsStatusPill('documenterStatusPill', 'Błąd', false);
        }
    }

    async fetchGardenerStatus() {
        try {
            const response = await fetch('/api/v1/gardener/status');
            if (!response.ok) throw new Error('Failed to fetch gardener status');

            const data = await response.json();
            const statusDiv = document.getElementById('gardenerStatus');

            if (data.status === 'success') {
                const gardener = data.gardener;
                statusDiv.innerHTML = `
                    <div class="status-item">
                        <span class="status-label">Uruchomiony:</span>
                        <span class="status-value ${gardener.is_running ? 'status-active' : 'status-inactive'}">
                            ${gardener.is_running ? '🟢 Tak' : '🔴 Nie'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Refaktoryzacja w bezczynności:</span>
                        <span class="status-value">${gardener.idle_refactoring_enabled ? '✅ Aktywna' : '❌ Wyłączona'}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">W trakcie:</span>
                        <span class="status-value">${gardener.idle_refactoring_in_progress ? '🔄 Tak' : '✅ Nie'}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Ostatnie skanowanie:</span>
                        <span class="status-value">${this.escapeHtml(gardener.last_scan_time ? new Date(gardener.last_scan_time).toLocaleString() : 'Nigdy')}</span>
                    </div>
                `;
                this.setJobsStatusPill(
                    'gardenerStatusPill',
                    gardener.is_running ? 'Aktywny' : 'Nieaktywny',
                    gardener.is_running
                );
            } else {
                statusDiv.innerHTML = '<p class="error-state">❌ Nie można pobrać statusu gardenera</p>';
                this.setJobsStatusPill('gardenerStatusPill', 'Błąd', false);
            }
        } catch (error) {
            console.error('Error fetching gardener status:', error);
            document.getElementById('gardenerStatus').innerHTML =
                '<p class="error-state">❌ Nie można pobrać statusu gardenera</p>';
            this.setJobsStatusPill('gardenerStatusPill', 'Błąd', false);
        }
    }

    async pauseBackgroundJobs() {
        try {
            const response = await fetch('/api/v1/scheduler/pause', { method: 'POST' });
            if (!response.ok) throw new Error('Failed to pause jobs');

            this.showNotification('Zadania w tle wstrzymane', 'success');
            this.fetchBackgroundJobsStatus();
        } catch (error) {
            console.error('Error pausing jobs:', error);
            this.showNotification('Błąd podczas wstrzymywania zadań', 'error');
        }
    }

    async resumeBackgroundJobs() {
        try {
            const response = await fetch('/api/v1/scheduler/resume', { method: 'POST' });
            if (!response.ok) throw new Error('Failed to resume jobs');

            this.showNotification('Zadania w tle wznowione', 'success');
            this.fetchBackgroundJobsStatus();
        } catch (error) {
            console.error('Error resuming jobs:', error);
            this.showNotification('Błąd podczas wznawiania zadań', 'error');
        }
    }

    // ========================================
    // Voice Command Center
    // ========================================

    initVoiceTab() {
        this.audioWs = null;
        this.isRecording = false;
        this.audioContext = null;
        this.mediaStream = null;
        this.audioChunks = [];

        const micButton = document.getElementById('micButton');
        const refreshIoTBtn = document.getElementById('refreshIoTBtn');

        if (micButton) {
            // Connect to audio WebSocket
            this.connectAudioWebSocket();

            // Push-to-Talk: Hold to record
            micButton.addEventListener('mousedown', () => this.startRecording());
            micButton.addEventListener('mouseup', () => this.stopRecording());
            micButton.addEventListener('mouseleave', () => {
                if (this.isRecording) this.stopRecording();
            });

            // Touch support for mobile
            micButton.addEventListener('touchstart', (e) => {
                e.preventDefault();
                this.startRecording();
            });
            micButton.addEventListener('touchend', (e) => {
                e.preventDefault();
                this.stopRecording();
            });
        }

        if (refreshIoTBtn) {
            refreshIoTBtn.addEventListener('click', () => this.refreshIoTStatus());
        }

        // Initialize audio visualizer
        this.initAudioVisualizer();
    }

    connectAudioWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/audio`;

        try {
            this.audioWs = new WebSocket(wsUrl);

            this.audioWs.onopen = () => {
                console.log('Audio WebSocket connected');
                this.updateAudioConnectionStatus('connected');
                document.getElementById('micButton').disabled = false;
            };

            this.audioWs.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleAudioMessage(data);
                } catch (error) {
                    console.error('Error parsing audio message:', error);
                }
            };

            this.audioWs.onerror = (error) => {
                console.error('Audio WebSocket error:', error);
                this.updateAudioConnectionStatus('disconnected');
            };

            this.audioWs.onclose = () => {
                console.log('Audio WebSocket disconnected');
                this.updateAudioConnectionStatus('disconnected');
                document.getElementById('micButton').disabled = true;

                // Try to reconnect after 5 seconds
                setTimeout(() => this.connectAudioWebSocket(), 5000);
            };
        } catch (error) {
            console.error('Error connecting to audio WebSocket:', error);
            this.updateAudioConnectionStatus('disconnected');
        }
    }

    updateAudioConnectionStatus(status) {
        const statusDot = document.getElementById('audioConnectionStatus');
        const statusText = document.getElementById('audioStatusText');

        if (statusDot) {
            statusDot.className = 'status-dot ' + status;
        }

        if (statusText) {
            const statusTexts = {
                'connected': 'Połączony',
                'disconnected': 'Rozłączony',
                'connecting': 'Łączenie...'
            };
            statusText.textContent = statusTexts[status] || 'Nieznany';
        }
    }

    async startRecording() {
        if (!this.audioWs || this.audioWs.readyState !== WebSocket.OPEN) {
            this.showNotification('Audio WebSocket nie jest połączony', 'error');
            return;
        }

        if (this.isRecording) return;

        try {
            // Request microphone access
            this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.isRecording = true;
            this.audioChunks = [];

            // Update UI
            const micButton = document.getElementById('micButton');
            micButton.classList.add('recording');
            micButton.querySelector('.mic-text').textContent = 'Nagrywanie...';

            // Send start recording command
            this.audioWs.send(JSON.stringify({ command: 'start_recording' }));

            // Setup audio recording
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = this.audioContext.createMediaStreamSource(this.mediaStream);
            // NOTE: createScriptProcessor is deprecated but widely supported.
            // TODO: Migrate to AudioWorkletNode for better performance in the future.
            const processor = this.audioContext.createScriptProcessor(4096, 1, 1);

            source.connect(processor);
            processor.connect(this.audioContext.destination);

            processor.onaudioprocess = (e) => {
                if (!this.isRecording) return;

                const inputData = e.inputBuffer.getChannelData(0);
                const audioData = new Int16Array(inputData.length);

                // Convert Float32 to Int16
                for (let i = 0; i < inputData.length; i++) {
                    audioData[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
                }

                // Send audio chunk
                if (this.audioWs && this.audioWs.readyState === WebSocket.OPEN) {
                    this.audioWs.send(audioData.buffer);
                }

                // Update visualizer
                this.updateVisualizer(inputData);
            };

            this.audioProcessor = processor;

        } catch (error) {
            console.error('Error starting recording:', error);
            this.showNotification('Nie udało się uruchomić mikrofonu', 'error');
            this.isRecording = false;
        }
    }

    stopRecording() {
        if (!this.isRecording) return;

        this.isRecording = false;

        // Update UI
        const micButton = document.getElementById('micButton');
        micButton.classList.remove('recording');
        micButton.querySelector('.mic-text').textContent = 'Przytrzymaj i mów';

        // Stop audio processing
        if (this.audioProcessor) {
            this.audioProcessor.disconnect();
            this.audioProcessor = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }

        // Send stop recording command
        if (this.audioWs && this.audioWs.readyState === WebSocket.OPEN) {
            this.audioWs.send(JSON.stringify({ command: 'stop_recording' }));
        }

        // Clear visualizer
        this.clearVisualizer();
    }

    handleAudioMessage(data) {
        switch (data.type) {
            case 'recording_started':
                console.log('Recording started');
                break;

            case 'processing':
                console.log('Processing:', data.status);
                document.getElementById('transcriptionText').textContent =
                    `Przetwarzanie (${data.status})...`;
                break;

            case 'transcription':
                console.log('Transcription:', data.text);
                document.getElementById('transcriptionText').textContent =
                    data.text || 'Nie rozpoznano mowy';
                break;

            case 'response_text':
                console.log('Response:', data.text);
                document.getElementById('responseText').textContent = data.text;
                break;

            case 'audio_response':
                console.log('Audio response received');
                this.playAudioResponse(data.audio, data.sample_rate);
                break;

            case 'complete':
                console.log('Processing complete');
                break;

            case 'error':
                console.error('Audio error:', data.message);
                this.showNotification('Błąd: ' + data.message, 'error');
                break;

            case 'pong':
                // Keep-alive response
                break;
        }
    }

    playAudioResponse(base64Audio, sampleRate) {
        try {
            // Decode base64 audio
            const binaryString = atob(base64Audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            // Create audio context
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();

            // Convert Int16 to Float32 for playback
            const audioData = new Int16Array(bytes.buffer);
            const floatData = new Float32Array(audioData.length);
            for (let i = 0; i < audioData.length; i++) {
                floatData[i] = audioData[i] / 32768.0;
            }

            // Create audio buffer
            const audioBuffer = audioContext.createBuffer(1, floatData.length, sampleRate || 22050);
            audioBuffer.getChannelData(0).set(floatData);

            // Play audio
            const source = audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContext.destination);
            source.start();

        } catch (error) {
            console.error('Error playing audio response:', error);
        }
    }

    initAudioVisualizer() {
        this.visualizerCanvas = document.getElementById('visualizerCanvas');
        this.visualizerCtx = this.visualizerCanvas ? this.visualizerCanvas.getContext('2d') : null;
    }

    updateVisualizer(audioData) {
        if (!this.visualizerCtx) return;

        const canvas = this.visualizerCanvas;
        const ctx = this.visualizerCtx;
        const width = canvas.width;
        const height = canvas.height;

        // Clear canvas
        ctx.fillStyle = '#0f172a';
        ctx.fillRect(0, 0, width, height);

        // Draw waveform
        ctx.strokeStyle = '#8b5cf6';
        ctx.lineWidth = 2;
        ctx.beginPath();

        const sliceWidth = width / audioData.length;
        let x = 0;

        for (let i = 0; i < audioData.length; i++) {
            const v = (audioData[i] + 1) / 2; // Normalize to 0-1
            const y = v * height;

            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }

            x += sliceWidth;
        }

        ctx.stroke();
    }

    clearVisualizer() {
        if (!this.visualizerCtx) return;

        const canvas = this.visualizerCanvas;
        const ctx = this.visualizerCtx;

        ctx.fillStyle = '#0f172a';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
    }

    async refreshIoTStatus() {
        // This would call an API endpoint to get Rider-Pi status
        // For now, it's a placeholder
        this.showNotification('IoT status refresh (funkcja w rozwoju)', 'info');

        // Mock data for demonstration
        const iotStatus = document.getElementById('iotStatus');
        const iotMetrics = document.getElementById('iotMetrics');

        if (iotStatus && iotMetrics) {
            iotStatus.innerHTML = '<p class="success-state">Połączony z Rider-Pi</p>';
            iotMetrics.classList.add('is-visible');

            document.getElementById('iotCpuTemp').textContent = '45.2°C';
            document.getElementById('iotMemory').textContent = '42%';
            document.getElementById('iotDisk').textContent = '65%';
        }
    }

    // ========================================
    // THE_CANVAS: Widget Rendering Methods
    // ========================================

    handleRenderWidget(data) {
        if (!data || !data.widget) {
            console.error('Invalid widget data:', data);
            return;
        }

        const widget = data.widget;
        console.log('Rendering widget:', widget);

        // Store widget (również markdown, żeby można było je usunąć)
        this.widgets.set(widget.id, widget);

        if (widget.type === 'markdown') {
            this.renderMarkdownWidget(widget);
            return;
        }

        // Show widgets grid jeśli renderujemy wizualne widgety
        if (this.elements.widgetsGrid) {
            this.elements.widgetsGrid.classList.add('widgets-grid--visible');
        }

        // Render based on type
        switch (widget.type) {
            case 'chart':
                this.renderChartWidget(widget);
                break;
            case 'table':
                this.renderTableWidget(widget);
                break;
            case 'form':
                this.renderFormWidget(widget);
                break;
            case 'mermaid':
                this.renderMermaidWidget(widget);
                break;
            case 'card':
                this.renderCardWidget(widget);
                break;
            case 'custom-html':
                this.renderCustomHTMLWidget(widget);
                break;
            default:
                console.warn('Unknown widget type:', widget.type);
        }
    }

    handleUpdateWidget(data) {
        if (!data || !data.widget_id) {
            console.error('Invalid update widget data:', data);
            return;
        }

        const widgetId = data.widget_id;
        const widget = this.widgets.get(widgetId);

        if (!widget) {
            console.warn('Widget not found for update:', widgetId);
            return;
        }

        // Update widget data
        widget.data = data.data || widget.data;
        this.widgets.set(widgetId, widget);

        // Re-render widget
        const widgetElement = document.getElementById(`widget-${widgetId}`);
        if (widgetElement) {
            widgetElement.remove();
        }
        this.handleRenderWidget({ widget });
    }

    handleRemoveWidget(data) {
        if (!data || !data.widget_id) {
            console.error('Invalid remove widget data:', data);
            return;
        }

        const widgetId = data.widget_id;

        // Remove from storage
        this.widgets.delete(widgetId);

        // Remove from DOM
        const widgetElement = document.getElementById(`widget-${widgetId}`);
        if (widgetElement) {
            widgetElement.remove();
        }

        // Destroy chart instance if exists
        if (this.chartInstances.has(widgetId)) {
            this.chartInstances.get(widgetId).destroy();
            this.chartInstances.delete(widgetId);
        }

        // Hide grid if no widgets
        if (this.widgets.size === 0 && this.elements.widgetsGrid) {
            this.elements.widgetsGrid.classList.remove('widgets-grid--visible');
        }
    }

    renderChartWidget(widget) {
        const container = document.createElement('div');
        container.id = `widget-${widget.id}`;
        container.className = 'widget widget-chart';

        if (widget.data.title) {
            const title = document.createElement('h3');
            title.className = 'widget-title';
            title.textContent = widget.data.title;
            container.appendChild(title);
        }

        const canvas = document.createElement('canvas');
        canvas.id = `chart-${widget.id}`;
        container.appendChild(canvas);

        this.elements.widgetsGrid.appendChild(container);

        // Render chart with Chart.js
        if (typeof Chart !== 'undefined') {
            const ctx = canvas.getContext('2d');
            const chart = new Chart(ctx, {
                type: widget.data.chartType || 'bar',
                data: widget.data.chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: {
                            labels: {
                                color: '#fff'
                            }
                        }
                    },
                    scales: {
                        y: {
                            ticks: { color: '#fff' },
                            grid: { color: '#333' }
                        },
                        x: {
                            ticks: { color: '#fff' },
                            grid: { color: '#333' }
                        }
                    }
                }
            });
            this.chartInstances.set(widget.id, chart);
        }
    }

    renderTableWidget(widget) {
        const container = document.createElement('div');
        container.id = `widget-${widget.id}`;
        container.className = 'widget widget-table';

        if (widget.data.title) {
            const title = document.createElement('h3');
            title.className = 'widget-title';
            title.textContent = widget.data.title;
            container.appendChild(title);
        }

        const table = document.createElement('table');
        table.className = 'widget-table-content';

        // Headers
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        widget.data.headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Rows
        const tbody = document.createElement('tbody');
        widget.data.rows.forEach(row => {
            const tr = document.createElement('tr');
            row.forEach(cell => {
                const td = document.createElement('td');
                td.textContent = cell;
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);

        container.appendChild(table);
        this.elements.widgetsGrid.appendChild(container);
    }

    renderFormWidget(widget) {
        const container = document.createElement('div');
        container.id = `widget-${widget.id}`;
        container.className = 'widget widget-form';

        if (widget.data.title) {
            const title = document.createElement('h3');
            title.className = 'widget-title';
            title.textContent = widget.data.title;
            container.appendChild(title);
        }

        const form = document.createElement('form');
        form.className = 'widget-form-content';

        const schema = widget.data.schema;

        // Generate form fields from schema
        Object.keys(schema.properties || {}).forEach(fieldName => {
            const field = schema.properties[fieldName];
            const fieldDiv = document.createElement('div');
            fieldDiv.className = 'form-field';

            const label = document.createElement('label');
            label.textContent = field.title || fieldName;
            fieldDiv.appendChild(label);

            let input;
            if (field.type === 'string') {
                // Use textarea for multiline, otherwise input[type=text]
                if (field.format === 'textarea' || field.format === 'multiline') {
                    input = document.createElement('textarea');
                } else {
                    input = document.createElement('input');
                    input.type = 'text';
                }
            } else if (field.type === 'number' || field.type === 'integer') {
                input = document.createElement('input');
                input.type = 'number';
            } else if (field.type === 'boolean') {
                input = document.createElement('input');
                input.type = 'checkbox';
            } else {
                input = document.createElement('input');
                input.type = 'text';
            }
            input.name = fieldName;
            input.required = schema.required && schema.required.includes(fieldName);
            fieldDiv.appendChild(input);

            form.appendChild(fieldDiv);
        });

        const submitBtn = document.createElement('button');
        submitBtn.type = 'submit';
        submitBtn.className = 'btn-primary';
        submitBtn.textContent = 'Wyślij';
        form.appendChild(submitBtn);

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const data = Object.fromEntries(formData);
            console.log('Form submitted:', data);
            // TODO: Send to backend with submit_intent
        });

        container.appendChild(form);
        this.elements.widgetsGrid.appendChild(container);
    }

    renderMarkdownWidget(widget) {
        const container = document.createElement('div');
        container.id = `widget-${widget.id}`;
        container.className = 'message assistant message-widget';

        const content = document.createElement('div');
        content.className = 'message-content';

        if (typeof marked !== 'undefined') {
            content.innerHTML = marked.parse(widget.data.content);
        } else {
            content.innerHTML = this.escapeHtml(widget.data.content).replace(
                /(?:\r\n|\r|\n)/g,
                '<br>'
            );
        }

        container.appendChild(content);
        this.elements.chatMessages.appendChild(container);
        this.scrollChatToBottom();
    }

    renderMermaidWidget(widget) {
        const container = document.createElement('div');
        container.id = `widget-${widget.id}`;
        container.className = 'widget widget-mermaid';

        if (widget.data.title) {
            const title = document.createElement('h3');
            title.className = 'widget-title';
            title.textContent = widget.data.title;
            container.appendChild(title);
        }

        const mermaidDiv = document.createElement('div');
        mermaidDiv.className = 'mermaid';
        mermaidDiv.textContent = widget.data.diagram;
        container.appendChild(mermaidDiv);

        this.elements.widgetsGrid.appendChild(container);

        // Render mermaid diagram
        if (typeof mermaid !== 'undefined') {
            mermaid.run({
                nodes: [mermaidDiv]
            });
        }
    }

    renderCardWidget(widget) {
        const container = document.createElement('div');
        container.id = `widget-${widget.id}`;
        container.className = 'widget widget-card';

        const cardContent = document.createElement('div');
        cardContent.className = 'card-content';

        if (widget.data.icon) {
            const icon = document.createElement('div');
            icon.className = 'card-icon';
            icon.textContent = widget.data.icon;
            cardContent.appendChild(icon);
        }

        if (widget.data.title) {
            const title = document.createElement('h3');
            title.className = 'card-title';
            title.textContent = widget.data.title;
            cardContent.appendChild(title);
        }

        if (widget.data.content) {
            const content = document.createElement('p');
            content.className = 'card-text';
            content.textContent = widget.data.content;
            cardContent.appendChild(content);
        }

        // Actions
        if (widget.data.actions && widget.data.actions.length > 0) {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'card-actions';

            widget.data.actions.forEach(action => {
                const btn = document.createElement('button');
                btn.className = 'btn-card-action';
                btn.textContent = action.label || action.id;
                btn.addEventListener('click', () => {
                    console.log('Action clicked:', action.intent);
                    // Send action intent as a new task
                    this.submitIntent(action.intent);
                });
                actionsDiv.appendChild(btn);
            });

            cardContent.appendChild(actionsDiv);
        }

        container.appendChild(cardContent);
        this.elements.widgetsGrid.appendChild(container);
    }

    async submitIntent(intent) {
        /**
         * Sends an intent (command) to the backend as a new task.
         *
         * Args:
         *     intent: Content of the command to execute (e.g., "Show more details")
         */
        try {
            this.showNotification('Wysyłam polecenie...', 'info');

            // Use standard task API to submit intent
            const response = await fetch('/api/v1/tasks', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ content: intent }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            this.showNotification('Polecenie wysłane', 'success');
        } catch (error) {
            console.error('Error submitting intent:', error);
            this.showNotification('Błąd wysyłania polecenia', 'error');
        }
    }

    renderCustomHTMLWidget(widget) {
        const container = document.createElement('div');
        container.id = `widget-${widget.id}`;
        container.className = 'widget widget-custom';

        // Sanitize HTML with DOMPurify if available
        if (typeof DOMPurify !== 'undefined') {
            container.innerHTML = DOMPurify.sanitize(widget.data.html);
        } else {
            // Fallback: use textContent (no HTML)
            container.textContent = widget.data.html;
            console.warn('DOMPurify not available, rendering as text only');
        }

        this.elements.widgetsGrid.appendChild(container);
    }

    clearAllWidgets() {
        // Destroy all chart instances
        this.chartInstances.forEach(chart => chart.destroy());
        this.chartInstances.clear();

        // Clear widgets
        this.widgets.clear();

        // Clear DOM
        if (this.elements.widgetsGrid) {
            this.elements.widgetsGrid.innerHTML = '';
            this.elements.widgetsGrid.classList.remove('widgets-grid--visible');
        }

        document.querySelectorAll('.message-widget').forEach(el => el.remove());

        this.showNotification('Wszystkie widgety zostały wyczyszczone', 'info');
    }

    // ========================================
    // Dashboard v2.1: Integrations Matrix & Active Operations
    // ========================================

    async fetchIntegrationsStatus() {
        try {
            const response = await fetch('/api/v1/system/services');

            if (!response.ok) {
                console.error('Failed to fetch integrations status');
                return;
            }

            const data = await response.json();

            if (data.status === 'success') {
                this.renderIntegrationsMatrix(data.services, data.summary);
            }
        } catch (error) {
            console.error('Error fetching integrations status:', error);
        }
    }

    renderIntegrationsMatrix(services, summary) {
        const container = document.getElementById('integrationsMatrix');
        if (!container) return;

        container.innerHTML = '';

        // Show critical warning if any critical service is offline
        if (summary.critical_offline && summary.critical_offline.length > 0) {
            const warning = document.createElement('div');
            warning.className = 'critical-warning';
            warning.textContent = `⚠️ Krytyczne usługi offline: ${summary.critical_offline.join(', ')}`;
            container.appendChild(warning);
        }

        // Create table
        const table = document.createElement('table');
        table.className = 'integrations-table';

        // Header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        ['Usługa', 'Status', 'Opóźnienie', 'Ostatni Test'].forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Body
        const tbody = document.createElement('tbody');
        services.forEach(service => {
            const row = document.createElement('tr');

            // Service name
            const nameCell = document.createElement('td');
            nameCell.textContent = service.name;
            row.appendChild(nameCell);

            // Status
            const statusCell = document.createElement('td');
            const statusBadge = document.createElement('span');
            statusBadge.className = 'service-status-badge';

            const statusDot = document.createElement('span');
            statusDot.className = `service-status-dot ${service.status}`;

            const statusText = document.createElement('span');
            statusText.textContent = service.status.toUpperCase();

            statusBadge.appendChild(statusDot);
            statusBadge.appendChild(statusText);
            statusCell.appendChild(statusBadge);
            row.appendChild(statusCell);

            // Latency
            const latencyCell = document.createElement('td');
            const latencySpan = document.createElement('span');
            latencySpan.className = 'service-latency';

            if (service.status === 'online') {
                const latency = service.latency_ms;
                if (latency < 100) {
                    latencySpan.className += ' good';
                } else if (latency < 500) {
                    latencySpan.className += ' warning';
                } else {
                    latencySpan.className += ' critical';
                }
                latencySpan.textContent = `${latency} ms`;
            } else {
                latencySpan.textContent = '-';
            }

            latencyCell.appendChild(latencySpan);
            row.appendChild(latencyCell);

            // Last check
            const lastCheckCell = document.createElement('td');
            lastCheckCell.textContent = service.last_check || '-';
            lastCheckCell.className = 'service-last-check';
            row.appendChild(lastCheckCell);

            tbody.appendChild(row);
        });
        table.appendChild(tbody);

        container.appendChild(table);
    }

    startIntegrationsPolling() {
        // Fetch immediately
        this.fetchIntegrationsStatus();

        // Then every 30 seconds - store interval ID for cleanup
        this.integrationsPollingInterval = setInterval(() => {
            this.fetchIntegrationsStatus();
        }, 30000);
    }

    handleSkillStarted(data) {
        if (!data) return;

        const skill = data.skill;
        const action = data.action || '';
        const is_external = data.is_external || false;

        if (!skill) return;

        const operationId = `${skill}-${Date.now()}`;

        // Determine operation type
        let operationType = 'system';
        let icon = '⚙️';

        if (skill.toLowerCase().includes('llm') || skill.toLowerCase().includes('gpt')) {
            operationType = 'thinking';
            icon = '🧠';
        } else if (skill.toLowerCase().includes('file') || skill.toLowerCase().includes('code')) {
            operationType = 'coding';
            icon = '⌨️';
        } else if (is_external || skill.toLowerCase().includes('browser') || skill.toLowerCase().includes('search')) {
            operationType = 'api-call';
            icon = '🌐';
        }

        // Store operation
        this.activeOperations.set(operationId, {
            skill,
            action,
            type: operationType,
            icon,
            startTime: Date.now()
        });

        // Render active operations
        this.renderActiveOperations();
    }

    handleSkillCompleted(data) {
        if (!data) return;

        const skill = data.skill;
        if (!skill) return;

        // Remove matching operation (most recent one)
        // Note: If the same skill runs concurrently, we remove the most recent.
        // A timeout mechanism could be added to clean up stale operations.
        const entries = Array.from(this.activeOperations.entries());
        for (let i = entries.length - 1; i >= 0; i--) {
            const [operationId, operation] = entries[i];
            if (operation.skill === skill) {
                this.activeOperations.delete(operationId);
                break;
            }
        }

        // Render active operations
        this.renderActiveOperations();
    }

    handleSkillFailed(data) {
        // Same as completed - remove operation
        this.handleSkillCompleted(data);
    }

    handleSystemLog(data, message) {
        const level = (data?.level || 'INFO').toLowerCase();
        const component = data?.component ? `[${data.component}] ` : '';
        this.addLogEntry(level, `${component}${message || ''}`.trim());
    }

    renderActiveOperations() {
        const container = document.getElementById('activeOperations');
        if (!container) return;

        container.innerHTML = '';

        if (this.activeOperations.size === 0) {
            const emptyState = document.createElement('div');
            emptyState.className = 'empty-state';
            emptyState.textContent = 'Brak aktywnych operacji';
            container.appendChild(emptyState);
            return;
        }

        // Render badges for each operation
        this.activeOperations.forEach((operation) => {
            const badge = document.createElement('div');
            badge.className = `operation-badge ${operation.type}`;

            const icon = document.createElement('span');
            icon.className = 'operation-icon';
            icon.textContent = operation.icon;

            const text = document.createElement('span');
            text.textContent = operation.action || operation.skill;

            badge.appendChild(icon);
            badge.appendChild(text);

            container.appendChild(badge);
        });
    }

    // History Tab Methods
    async loadHistory(options = {}) {
        return this.loadHistoryWithOptions(options);
    }

    async loadHistoryWithOptions(options = {}) {
        const { silent = false, showLoading = false } = options;
        if (!this.elements.historyTableBody) return;

        if (!silent && this.historyLoading) {
            return;
        }

        if (silent && (this.historyBackgroundLoading || this.historyLoading)) {
            return;
        }

        if (silent) {
            this.historyBackgroundLoading = true;
        } else {
            this.historyLoading = true;
            if (showLoading) {
                this.setHistoryLoadingState('Ładowanie historii...');
            }
        }

        try {
            const response = await fetch('/api/v1/history/requests?limit=50');

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const requests = await response.json();
            this.historyState.requests = Array.isArray(requests) ? requests : [];
            this.historyState.lastUpdated = new Date();
            this.renderHistoryTable();
            this.updateHistoryLastUpdated();

        } catch (error) {
            console.error('Error loading history:', error);
            if (!silent) {
                this.renderHistoryPlaceholder('Błąd ładowania historii');
            }
        }
        finally {
            if (silent) {
                this.historyBackgroundLoading = false;
            } else {
                this.historyLoading = false;
            }
        }
    }

    configureHistoryRow(row, request) {
        row.tabIndex = 0;
        row.setAttribute('role', 'button');
        row.setAttribute('aria-label', `Zobacz szczegóły zadania ${request.request_id}`);
        row.classList.toggle('history-row--selected', request.request_id === this.selectedHistoryId);
    }

    highlightHistorySelection() {
        if (!this.elements.historyTableBody) return;
        const rows = this.elements.historyTableBody.querySelectorAll('.history-row');
        rows.forEach(row => {
            row.classList.toggle(
                'history-row--selected',
                row.dataset.requestId === this.selectedHistoryId
            );
        });
    }

    startHistoryAutoRefresh(options = {}) {
        if (!this.historyState.autoRefresh) return;
        if (!this.isHistoryTabActive()) return;
        if (this.historyRefreshTimer) {
            return;
        }

        const { immediate = true } = options;
        if (immediate) {
            this.loadHistory();
        }

        this.historyRefreshTimer = setInterval(() => {
            this.loadHistory({ silent: true });
        }, 5000);
    }

    stopHistoryAutoRefresh() {
        if (this.historyRefreshTimer) {
            clearInterval(this.historyRefreshTimer);
            this.historyRefreshTimer = null;
        }
    }

    async showHistoryDetail(requestId, options = {}) {
        if (!this.elements.historyModal || !this.elements.historyModalBody) return;

        const { refreshOnly = false } = options;

        if (refreshOnly && !this.isModalVisible(this.elements.historyModal)) {
            return;
        }

        if (!refreshOnly) {
            this.selectedHistoryId = requestId;
            this.historyDetailAutoRefresh = true;
            this.showModal(this.elements.historyModal);
            this.highlightHistorySelection();
        }

        this.elements.historyModalBody.innerHTML = '<div class="loading-state">Ładowanie szczegółów...</div>';

        try {
            const response = await fetch(`/api/v1/history/requests/${requestId}`);

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const detail = await response.json();

            // Render request info
            const createdDate = new Date(detail.created_at);
            const finishedDate = detail.finished_at ? new Date(detail.finished_at) : null;
            const duration = detail.duration_seconds
                ? `${detail.duration_seconds.toFixed(2)}s`
                : 'brak danych';

            let html = `
                <div class="request-info">
                    <div class="request-info-row">
                        <span class="request-info-label">ID:</span>
                        <span class="request-info-value">${this.escapeHtml(detail.request_id)}</span>
                    </div>
                    <div class="request-info-row">
                        <span class="request-info-label">Status:</span>
                        <span class="request-info-value">
                            <span class="status-badge status-${this.escapeHtml(detail.status.toLowerCase())}">
                                ${this.getStatusIcon(detail.status)} ${this.escapeHtml(detail.status)}
                            </span>
                        </span>
                    </div>
                    <div class="request-info-row">
                        <span class="request-info-label">Polecenie:</span>
                        <span class="request-info-value">${this.escapeHtml(detail.prompt)}</span>
                    </div>
                    <div class="request-info-row">
                        <span class="request-info-label">Utworzono:</span>
                        <span class="request-info-value">${this.formatTime(createdDate)}</span>
                    </div>
                    ${finishedDate ? `
                    <div class="request-info-row">
                        <span class="request-info-label">Zakończono:</span>
                        <span class="request-info-value">${this.formatTime(finishedDate)}</span>
                    </div>
                    ` : ''}
                    <div class="request-info-row">
                        <span class="request-info-label">Czas trwania:</span>
                        <span class="request-info-value">${duration}</span>
                    </div>
                </div>

                <h3 class="request-timeline-title">⏱️ Timeline Wykonania</h3>
                <div class="request-timeline">
            `;

            // Render timeline
            if (detail.steps && detail.steps.length > 0) {
                detail.steps.forEach(step => {
                    const stepDate = new Date(step.timestamp);
                    const isError = step.status === 'error';

                    html += `
                        <div class="timeline-item">
                            <div class="timeline-dot ${isError ? 'status-error' : ''}"></div>
                            <div class="timeline-content ${isError ? 'status-error' : ''}">
                                <div class="timeline-header">
                                    <span class="timeline-component">${this.escapeHtml(step.component)}</span>
                                    <span class="timeline-timestamp">${this.formatTime(stepDate)}</span>
                                </div>
                                <div class="timeline-action">${this.escapeHtml(step.action)}</div>
                                ${step.details ? `
                                <div class="timeline-details">${this.escapeHtml(step.details)}</div>
                                ` : ''}
                            </div>
                        </div>
                    `;
                });
            } else {
                html += '<div class="empty-state">Brak kroków w timeline</div>';
            }

            html += '</div>';

            this.elements.historyModalBody.innerHTML = html;

        } catch (error) {
            console.error('Error loading history detail:', error);
            this.elements.historyModalBody.innerHTML = `
                <div class="empty-state">Błąd ładowania szczegółów: ${error.message}</div>
            `;
        }
    }

    closeHistoryModal() {
        if (this.elements.historyModal) {
            this.hideModal(this.elements.historyModal);
        }
        this.historyDetailAutoRefresh = false;
        this.selectedHistoryId = null;
        this.highlightHistorySelection();
    }

    getStatusIcon(status) {
        const icons = {
            'PENDING': '⚪',
            'PROCESSING': '🟡',
            'COMPLETED': '🟢',
            'FAILED': '🔴',
            'LOST': '🔴'
        };
        return icons[status] || '⚪';
    }

    formatTime(date) {
        const now = new Date();
        const diff = now - date;

        // Handle future dates (clock skew)
        if (diff < 0) {
            return 'just now';
        }

        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) {
            return `${days}d ago`;
        } else if (hours > 0) {
            return `${hours}h ago`;
        } else if (minutes > 0) {
            return `${minutes}m ago`;
        } else if (seconds > 0) {
            return `${seconds}s ago`;
        } else {
            return 'just now';
        }
    }

    // ============================================
    // Dashboard v2.3: Queue Governance
    // ============================================

    async startQueueStatusPolling() {
        const pollQueue = async () => {
            try {
                const response = await fetch('/api/v1/queue/status');
                if (response.ok) {
                    const status = await response.json();
                    this.updateQueueStatus(status);
                }
            } catch (error) {
                console.error('Error polling queue status:', error);
            }
        };

        // Initial poll
        await pollQueue();

        // Poll every 2 seconds
        setInterval(pollQueue, 2000);
    }

    updateQueueStatus(status) {
        try {
            if (this.elements.queueActive) {
                this.elements.queueActive.textContent = status.active || 0;
            }
        } catch (err) {
            console.error('Błąd przy aktualizacji queueActive:', err);
        }

        try {
            if (this.elements.queuePending) {
                this.elements.queuePending.textContent = status.pending || 0;
            }
        } catch (err) {
            console.error('Błąd przy aktualizacji queuePending:', err);
        }

        try {
            if (this.elements.queueLimit && status.limit) {
                this.elements.queueLimit.textContent = status.limit;
            }
        } catch (err) {
            console.error('Błąd przy aktualizacji queueLimit:', err);
        }

        // Update button state
        try {
            if (this.elements.pauseResumeBtn) {
                if (status.paused) {
                    this.elements.pauseResumeBtn.classList.remove('pause');
                    this.elements.pauseResumeBtn.classList.add('resume');
                    this.elements.pauseResumeBtn.dataset.state = 'paused';
                    const btnIcon = this.elements.pauseResumeBtn.querySelector('.btn-icon');
                    if (btnIcon) btnIcon.textContent = '▶️';
                    const btnText = this.elements.pauseResumeBtn.querySelector('.btn-text');
                    if (btnText) btnText.textContent = 'WZNÓW';

                    // Visual feedback - yellow mode
                    if (this.elements.governancePanel) {
                        this.elements.governancePanel.classList.add('paused');
                    }
                } else {
                    this.elements.pauseResumeBtn.classList.remove('resume');
                    this.elements.pauseResumeBtn.classList.add('pause');
                    this.elements.pauseResumeBtn.dataset.state = 'running';
                    const btnIcon = this.elements.pauseResumeBtn.querySelector('.btn-icon');
                    if (btnIcon) btnIcon.textContent = '⏸️';
                    const btnText = this.elements.pauseResumeBtn.querySelector('.btn-text');
                    if (btnText) btnText.textContent = 'PAUZA';

                    // Remove yellow mode
                    if (this.elements.governancePanel) {
                        this.elements.governancePanel.classList.remove('paused');
                    }
                }
            }
        } catch (err) {
            console.error('Błąd przy aktualizacji stanu przycisku kolejki:', err);
        }
    }

    async handlePauseResume() {
        const btn = this.elements.pauseResumeBtn;
        const currentState = btn.dataset.state;

        try {
            const endpoint = currentState === 'running' ? '/api/v1/queue/pause' : '/api/v1/queue/resume';
            const response = await fetch(endpoint, { method: 'POST' });

            if (response.ok) {
                const result = await response.json();
                this.showNotification(result.message, 'info');
                // Force immediate update
                const statusResponse = await fetch('/api/v1/queue/status');
                if (statusResponse.ok) {
                    const status = await statusResponse.json();
                    this.updateQueueStatus(status);
                }
            } else {
                throw new Error('Failed to toggle queue state');
            }
        } catch (error) {
            console.error('Error toggling queue:', error);
            this.showNotification('Błąd podczas zmiany stanu kolejki', 'error');
        }
    }

    async handlePurgeQueue() {
        if (!confirm('Czy na pewno chcesz usunąć wszystkie oczekujące zadania? Ta operacja jest nieodwracalna.')) {
            return;
        }

        try {
            const response = await fetch('/api/v1/queue/purge', { method: 'POST' });

            if (response.ok) {
                const result = await response.json();
                this.showNotification(`Kolejka wyczyszczona: ${result.removed} zadań usuniętych`, 'warning');
                // Refresh task list
                await this.refreshTaskList();
            } else {
                throw new Error('Failed to purge queue');
            }
        } catch (error) {
            console.error('Error purging queue:', error);
            this.showNotification('Błąd podczas czyszczenia kolejki', 'error');
        }
    }

    async handleEmergencyStop() {
        if (!confirm('🚨 AWARYJNE ZATRZYMANIE! Czy na pewno chcesz zatrzymać WSZYSTKIE zadania? System zostanie wstrzymany.')) {
            return;
        }

        try {
            const response = await fetch('/api/v1/queue/emergency-stop', { method: 'POST' });

            if (response.ok) {
                const result = await response.json();
                this.showNotification(`Awaryjne zatrzymanie: ${result.cancelled} zadań anulowanych, ${result.purged} usuniętych`, 'error');
                // Refresh task list
                await this.refreshTaskList();
            } else {
                throw new Error('Failed to execute emergency stop');
            }
        } catch (error) {
            console.error('Error executing emergency stop:', error);
            this.showNotification('Błąd podczas awaryjnego zatrzymania', 'error');
        }
    }

    async handleAbortTask(taskId) {
        if (!confirm('Czy na pewno chcesz przerwać to zadanie?')) {
            return;
        }

        try {
            const response = await fetch(`/api/v1/queue/task/${taskId}/abort`, { method: 'POST' });

            if (response.ok) {
                await response.json();
                this.showNotification('Zadanie przerwane', 'warning');
                // Update task in list
                // Uwaga: `element.dataset.taskId` w JS mapuje się na atrybut HTML `data-task-id`.
                // Selector CSS `[data-task-id="${taskId}"]` jest poprawny i zgodny ze standardem.
                const taskCard = document.querySelector(`[data-task-id="${taskId}"]`);
                if (taskCard) {
                    taskCard.remove();
                }
            } else {
                const error = await response.json();
                throw new Error(error.detail || 'Nie udało się przerwać zadania');
            }
        } catch (error) {
            console.error('Error aborting task:', error);
            this.showNotification(`Błąd: ${error.detail || error.message || 'Nie udało się przerwać zadania'}`, 'error');
        }
    }

    // ============================================
    // Dashboard v2.3: Tokenomics
    // ============================================

    async startTokenomicsPolling() {
        const pollTokenomics = async () => {
            try {
                const response = await fetch('/api/v1/metrics/tokens');
                if (response.ok) {
                    const data = await response.json();
                    this.updateTokenomics(data);
                }
            } catch (error) {
                console.error('Error polling tokenomics:', error);
            }
        };

        // Initial poll
        await pollTokenomics();

        // Poll every 5 seconds
        setInterval(pollTokenomics, 5000);
    }

    updateTokenomics(data) {
        if (this.elements.sessionCost) {
            const cost = data.session_cost_usd || 0;
            this.elements.sessionCost.textContent = `$${cost.toFixed(4)}`;
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ============================================
    // Dashboard v2.4: Global Cost Guard
    // ============================================

    async startCostModePolling() {
        const pollCostMode = async () => {
            try {
                const response = await fetch('/api/v1/system/cost-mode');
                if (response.ok) {
                    const data = await response.json();
                    this.updateCostModeUI(data.enabled);
                }
            } catch (error) {
                console.error('Error polling cost mode:', error);
            }
        };

        // Initial poll
        await pollCostMode();

        // Poll every 5 seconds
        setInterval(pollCostMode, 5000);
    }

    updateCostModeUI(enabled) {
        if (!this.elements.costModeToggle || !this.elements.costModeLabel) return;

        // Ustaw checkbox bez triggerowania eventu
        this.elements.costModeToggle.checked = enabled;

        // Zaktualizuj label i style
        if (enabled) {
            this.elements.costModeLabel.textContent = '💸 Tryb Pro';
            this.elements.costModeLabel.classList.add('pro-mode');
            this.elements.costModeLabel.classList.remove('eco-mode');
            if (this.elements.costModeStatusLabel) {
                this.elements.costModeStatusLabel.textContent = 'PRO';
            }
        } else {
            this.elements.costModeLabel.textContent = '🌿 Tryb Eco';
            this.elements.costModeLabel.classList.add('eco-mode');
            this.elements.costModeLabel.classList.remove('pro-mode');
            if (this.elements.costModeStatusLabel) {
                this.elements.costModeStatusLabel.textContent = 'ECO';
            }
        }
    }

    handleCostModeToggle(wantsToEnable) {
        if (wantsToEnable) {
            // Pokazuje modal potwierdzenia
            this.showCostModeModal();
        } else {
            // Wyłączanie - bezpośrednia zmiana
            this.setCostMode(false);
        }
    }

    showCostModeModal() {
        if (this.elements.costModeModal) {
            this.showModal(this.elements.costModeModal);
        }
    }

    closeCostModeModal() {
        if (this.elements.costModeModal) {
            this.hideModal(this.elements.costModeModal);
        }
    }

    async confirmCostModeChange() {
        // Użytkownik potwierdził - włącz Paid Mode
        this.closeCostModeModal();
        await this.setCostMode(true);
    }

    cancelCostModeChange() {
        // Użytkownik anulował - przywróć checkbox do stanu wyłączonego
        if (this.elements.costModeToggle) {
            this.elements.costModeToggle.checked = false;
        }
        this.closeCostModeModal();
    }

    async setCostMode(enable) {
        try {
            const response = await fetch('/api/v1/system/cost-mode', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ enable }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();

            // Zaktualizuj UI
            this.updateCostModeUI(enable);

            // Pokaż notyfikację
            if (enable) {
                this.showNotification('💸 Tryb Pro włączony - dostęp do modeli chmurowych', 'warning');
            } else {
                this.showNotification('🌿 Tryb Eco włączony - tylko lokalne modele', 'info');
            }

            console.log('Cost mode changed:', result);
        } catch (error) {
            console.error('Error setting cost mode:', error);
            this.showNotification('Błąd zmiany trybu kosztowego', 'error');

            // Przywróć poprzedni stan UI
            if (this.elements.costModeToggle) {
                this.elements.costModeToggle.checked = !enable;
            }
        }
    }

    // ============================================
    // AutonomyGate - 5-Level Security System
    // ============================================

    async startAutonomyPolling() {
        const pollAutonomy = async () => {
            try {
                const response = await fetch('/api/v1/system/autonomy');
                if (response.ok) {
                    const data = await response.json();
                    this.updateAutonomyUI(data);
                }
            } catch (error) {
                console.error('Error polling autonomy level:', error);
            }
        };

        // Initial poll
        await pollAutonomy();

        // Poll every 5 seconds
        setInterval(pollAutonomy, 5000);
    }

    updateAutonomyUI(data) {
        const body = document.getElementById('venomBody');
        const selector = document.getElementById('autonomyLevel');
        const guardStatus = this.elements?.autonomyStatusLabel;

        if (!body || !selector) return;

        // Update body theme class
        body.className = `theme-${data.color_name}`;

        // Update selector value (without triggering change event)
        selector.value = data.current_level;

        if (guardStatus && data.current_level_name) {
            guardStatus.textContent = data.current_level_name.toUpperCase();
        }

        // Store current level globally
        window.currentAutonomyLevel = data.current_level;
        window.currentAutonomyName = data.current_level_name;
    }

    async setAutonomyLevel(level) {
        try {
            const response = await fetch('/api/v1/system/autonomy', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ level: parseInt(level) }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();

            // Update UI
            this.updateAutonomyUI({
                current_level: result.level,
                current_level_name: result.level_name,
                color: result.color,
                color_name: this.getColorName(result.color)
            });

            // Show notification
            this.showNotification(`🔐 Poziom autonomii: ${result.level_name}`, 'info');

            // Pulse the autonomy selector
            const selector = document.querySelector('.autonomy-selector');
            if (selector) {
                selector.classList.add('autonomy-pulse');
                setTimeout(() => selector.classList.remove('autonomy-pulse'), 4500);
            }

            console.log('Autonomy level changed:', result);
        } catch (error) {
            console.error('Error setting autonomy level:', error);
            this.showNotification('Błąd zmiany poziomu autonomii', 'error');
        }
    }

    getColorName(hexColor) {
        const colorMap = {
            '#22c55e': 'green',
            '#3b82f6': 'blue',
            '#eab308': 'yellow',
            '#f97316': 'orange',
            '#ef4444': 'red'
        };
        return colorMap[hexColor.toLowerCase()] || 'green';
    }

    handleAutonomyViolation(errorData) {
        // Show modal with error info
        const modal = document.getElementById('autonomyModal');
        const errorMsg = document.getElementById('autonomyErrorMessage');
        const increaseBtn = document.getElementById('increaseAutonomyBtn');

        if (!modal || !errorMsg || !increaseBtn) return;

        errorMsg.textContent = `Zablokowano akcję! Wymagany poziom: ${errorData.required_level_name} (${errorData.required_level})`;

        // Store required level for "Increase" button
        increaseBtn.dataset.requiredLevel = errorData.required_level;

        this.showModal(modal);

        // Pulse the autonomy selector with required color
        const body = document.getElementById('venomBody');
        const tempTheme = this.getThemeForLevel(errorData.required_level);
        const originalTheme = body.className;

        body.className = tempTheme;
        const selector = document.querySelector('.autonomy-selector');
        if (selector) {
            selector.classList.add('autonomy-pulse');
            setTimeout(() => {
                selector.classList.remove('autonomy-pulse');
                body.className = originalTheme;
            }, 4500);
        }
    }

    getThemeForLevel(level) {
        const themeMap = {
            0: 'theme-isolated',
            10: 'theme-connected',
            20: 'theme-funded',
            30: 'theme-builder',
            40: 'theme-root'
        };
        return themeMap[level] || 'theme-isolated';
    }

    closeAutonomyModal() {
        const modal = document.getElementById('autonomyModal');
        if (modal) {
            this.hideModal(modal);
        }
    }

    increaseAutonomyLevel() {
        const increaseBtn = document.getElementById('increaseAutonomyBtn');
        if (!increaseBtn) return;

        const requiredLevel = parseInt(increaseBtn.dataset.requiredLevel || '0');

        if (requiredLevel > 0) {
            this.setAutonomyLevel(requiredLevel);
            this.closeAutonomyModal();
        }
    }
}

// Initialize after DOM loaded
document.addEventListener('DOMContentLoaded', () => {
    window.venomDashboard = new VenomDashboard();
    // Initialize memory tab
    window.venomDashboard.initMemoryTab();
    // Initialize background jobs tab
    window.venomDashboard.initBackgroundJobsTab();
    // Initialize voice tab
    window.venomDashboard.initVoiceTab();
    // Initialize models tab (THE_ARMORY)
    window.venomDashboard.initModelsTab();

    // Initialize autonomy polling
    window.venomDashboard.startAutonomyPolling();

    // Initialize autonomy selector handler
    const autonomyLevel = document.getElementById('autonomyLevel');
    if (autonomyLevel) {
        autonomyLevel.addEventListener('change', (e) => {
            window.venomDashboard.setAutonomyLevel(e.target.value);
        });
    }

    // Initialize autonomy modal handlers
    const closeAutonomyModal = document.getElementById('closeAutonomyModal');
    if (closeAutonomyModal) {
        closeAutonomyModal.addEventListener('click', () => {
            window.venomDashboard.closeAutonomyModal();
        });
    }

    const increaseAutonomyBtn = document.getElementById('increaseAutonomyBtn');
    if (increaseAutonomyBtn) {
        increaseAutonomyBtn.addEventListener('click', () => {
            window.venomDashboard.increaseAutonomyLevel();
        });
    }

    const cancelAutonomyBtn = document.getElementById('cancelAutonomyBtn');
    if (cancelAutonomyBtn) {
        cancelAutonomyBtn.addEventListener('click', () => {
            window.venomDashboard.closeAutonomyModal();
        });
    }
});
