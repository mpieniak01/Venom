// Venom Strategy Dashboard - War Room

const WAR_ROOM_PREFS_KEY = 'venomWarRoomPreferences';
const WAR_ROOM_PREFS_DEFAULTS = {
    autoRefresh: true
};

class StrategyDashboard {
    constructor() {
        this.API_BASE = '/api';
        this.refreshInterval = null;
        this.state = {
            lastUpdated: null
        };
        this.preferences = this.loadPreferences();
        this.autoRefreshEnabled = this.preferences.autoRefresh;

        this.initElements();
        this.applyPreferencesToControls();
        this.initEventHandlers();
        this.loadRoadmap({ showLoading: true });
        this.startAutoRefresh();
    }

    initElements() {
        this.elements = {
            shell: document.getElementById('warRoomShell'),
            visionContent: document.getElementById('visionContent'),
            milestonesContent: document.getElementById('milestonesContent'),
            roadmapReportContent: document.getElementById('roadmapReportContent'),
            completionRate: document.getElementById('completionRate'),
            milestonesCompleted: document.getElementById('milestonesCompleted'),
            tasksCompleted: document.getElementById('tasksCompleted'),
            lastUpdated: document.getElementById('warRoomLastUpdated'),
            completionMeta: document.getElementById('warRoomCompletionMeta'),
            milestonesMeta: document.getElementById('warRoomMilestonesMeta'),
            tasksMeta: document.getElementById('warRoomTasksMeta'),
            milestoneHealthMeta: document.getElementById('warRoomMilestoneHealth'),
            manualRefreshBtn: document.getElementById('warRoomManualRefresh'),
            quickRefreshBtn: document.getElementById('warRoomRefreshBtn'),
            defineVisionBtn: document.getElementById('warRoomDefineVision'),
            startCampaignBtn: document.getElementById('warRoomStartCampaign'),
            statusReportBtn: document.getElementById('warRoomStatusReport'),
            autoRefreshToggle: document.getElementById('warRoomAutoRefresh'),
            alertBox: document.getElementById('warRoomAlert')
        };

        if (this.elements.shell) {
            this.elements.shell.setAttribute('aria-busy', 'false');
        }
    }

    initEventHandlers() {
        const bind = (btn, handler) => {
            if (btn) {
                btn.addEventListener('click', handler);
            }
        };

        bind(this.elements.manualRefreshBtn, () => this.loadRoadmap({ showLoading: true }));
        bind(this.elements.quickRefreshBtn, () => this.loadRoadmap({ showLoading: true }));
        bind(this.elements.defineVisionBtn, () => this.showDefineVisionDialog());
        bind(this.elements.startCampaignBtn, () => this.startCampaign());
        bind(this.elements.statusReportBtn, () => this.requestStatusReport());

        if (this.elements.autoRefreshToggle) {
            this.elements.autoRefreshToggle.addEventListener('change', (event) => {
                this.toggleAutoRefresh(event.target.checked);
            });
        }
    }

    showNotification(message, type = 'info') {
        if (window.venomDashboard && typeof window.venomDashboard.showNotification === 'function') {
            window.venomDashboard.showNotification(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
            if (type === 'error') {
                alert(message);
            }
        }
    }

    async loadRoadmap(options = {}) {
        const { showLoading = false, silent = false } = options;
        if (showLoading) {
            this.setSectionsLoading(true);
        }

        try {
            const response = await fetch(`${this.API_BASE}/roadmap`);
            if (!response.ok) {
                throw new Error('Failed to load roadmap');
            }
            const data = await response.json();
            this.renderRoadmap(data);
            this.hideAlert();
            this.updateLastUpdated();
        } catch (error) {
            console.error('Error loading roadmap:', error);
            if (!silent) {
                this.renderEmptySections();
            }
            this.showAlert('Błąd ładowania roadmapy. Sprawdź czy serwer działa.');
        } finally {
            if (showLoading) {
                this.setSectionsLoading(false);
            }
        }
    }

    renderRoadmap(data) {
        this.renderVision(data.vision);
        this.renderMilestones(data.milestones);
        this.renderKPIs(data.kpis);
        this.renderReport(data.report);
    }

    renderVision(vision) {
        if (!this.elements.visionContent) return;
        if (!vision) {
            this.elements.visionContent.innerHTML =
                '<div class="empty-state">Brak zdefiniowanej wizji. Kliknij "Zdefiniuj Wizję" aby rozpocząć.</div>';
            return;
        }

        const progress = this.getPercentage(vision.progress);
        this.elements.visionContent.innerHTML = `
            <div class="war-room-vision-title">${this.escapeHtml(vision.title)}</div>
            <div>${this.escapeHtml(vision.description)}</div>
            <div class="war-room-progress">
                <div class="war-room-progress-fill" style="width: ${progress}%"></div>
            </div>
            <div class="war-room-vision-meta">Postęp: ${progress}%</div>
        `;
    }

    renderMilestones(milestones) {
        if (!this.elements.milestonesContent) return;
        if (!Array.isArray(milestones) || milestones.length === 0) {
            this.elements.milestonesContent.innerHTML =
                '<div class="empty-state">Brak kamieni milowych. Zdefiniuj wizję aby automatycznie wygenerować roadmapę.</div>';
            return;
        }

        const milestonesHtml = milestones.map((m) => {
            const progress = this.getPercentage(m.progress);
            const completedTasks = m.tasks?.filter(t => t.status === 'COMPLETED').length || 0;
            const totalTasks = m.tasks?.length || 0;
            const statusClass = (m.status || '').toLowerCase().replace(/_/g, '-');
            return `
                <article class="war-room-milestone ${statusClass}">
                    <div class="war-room-milestone-header">
                        <div class="war-room-milestone-title">
                            <span class="status-emoji">${this.getStatusEmoji(m.status)}</span>
                            ${this.escapeHtml(m.title)}
                        </div>
                        <span class="milestone-status">${this.escapeHtml(m.status)}</span>
                    </div>
                    <p>${this.escapeHtml(m.description || '')}</p>
                    <div class="war-room-progress">
                        <div class="war-room-progress-fill" style="width: ${progress}%"></div>
                    </div>
                    <div class="war-room-milestone-meta">
                        <span>Postęp: ${progress}%</span>
                        <span>Priorytet: ${this.escapeHtml(m.priority)}</span>
                    </div>
                    ${totalTasks > 0 ? `
                        <div class="war-room-task-list">
                            <strong>Zadania (${completedTasks}/${totalTasks}):</strong>
                            ${m.tasks.map(t => `
                                <div class="war-room-task ${t.status === 'COMPLETED' ? 'completed' : ''}">
                                    ${this.getStatusEmoji(t.status)} ${this.escapeHtml(t.title)}
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </article>
            `;
        }).join('');
        this.elements.milestonesContent.innerHTML = milestonesHtml;
    }

    renderKPIs(kpis) {
        if (!kpis) {
            if (this.elements.completionRate) this.elements.completionRate.textContent = '0%';
            if (this.elements.milestonesCompleted) this.elements.milestonesCompleted.textContent = '0/0';
            if (this.elements.tasksCompleted) this.elements.tasksCompleted.textContent = '0/0';
            this.updateMetaCards({
                completion: 0,
                milestonesCompleted: 0,
                milestonesTotal: 0,
                tasksCompleted: 0,
                tasksTotal: 0,
                health: '-'
            });
            return;
        }

        if (this.elements.completionRate) {
            this.elements.completionRate.textContent = `${(kpis.completion_rate || 0).toFixed(0)}%`;
        }
        if (this.elements.milestonesCompleted) {
            this.elements.milestonesCompleted.textContent =
                `${kpis.milestones_completed || 0}/${kpis.milestones_total || 0}`;
        }
        if (this.elements.tasksCompleted) {
            this.elements.tasksCompleted.textContent =
                `${kpis.tasks_completed || 0}/${kpis.tasks_total || 0}`;
        }

        this.updateMetaCards({
            completion: kpis.completion_rate || 0,
            milestonesCompleted: kpis.milestones_completed || 0,
            milestonesTotal: kpis.milestones_total || 0,
            tasksCompleted: kpis.tasks_completed || 0,
            tasksTotal: kpis.tasks_total || 0,
            health: this.calculateHealthBadge(kpis)
        });
    }

    renderReport(report) {
        if (!this.elements.roadmapReportContent) return;
        if (report) {
            this.elements.roadmapReportContent.textContent = report;
        } else {
            this.elements.roadmapReportContent.innerHTML =
                '<div class="empty-state">Brak danych do wyświetlenia</div>';
        }
    }

    showAlert(message) {
        if (!this.elements.alertBox) return;
        this.elements.alertBox.textContent = message;
        this.elements.alertBox.classList.remove('is-hidden');
    }

    hideAlert() {
        if (!this.elements.alertBox) return;
        this.elements.alertBox.classList.add('is-hidden');
    }

    setSectionsLoading(isLoading) {
        if (!this.elements.shell) return;
        this.elements.shell.classList.toggle('is-loading', isLoading);
        this.elements.shell.setAttribute('aria-busy', isLoading ? 'true' : 'false');
    }

    renderEmptySections() {
        this.renderVision(null);
        this.renderMilestones([]);
        this.renderKPIs(null);
        if (this.elements.roadmapReportContent) {
            this.elements.roadmapReportContent.innerHTML =
                '<div class="empty-state">Brak danych do wyświetlenia</div>';
        }
    }

    updateLastUpdated() {
        if (!this.elements.lastUpdated) return;
        const now = new Date();
        this.state.lastUpdated = now;
        this.elements.lastUpdated.textContent = `Ostatnie odświeżenie: ${now.toLocaleString('pl-PL')}`;
    }

    updateMetaCards(summary) {
        if (this.elements.completionMeta) {
            this.elements.completionMeta.textContent = `${summary.completion.toFixed(0)}%`;
        }
        if (this.elements.milestonesMeta) {
            this.elements.milestonesMeta.textContent = `${summary.milestonesCompleted}/${summary.milestonesTotal}`;
        }
        if (this.elements.tasksMeta) {
            this.elements.tasksMeta.textContent = `${summary.tasksCompleted}/${summary.tasksTotal}`;
        }
        if (this.elements.milestoneHealthMeta) {
            this.elements.milestoneHealthMeta.textContent = summary.health || '-';
        }
    }

    calculateHealthBadge(kpis) {
        if (!kpis || !kpis.milestones_total) return '-';
        const completion = kpis.completion_rate || 0;
        const blockers = kpis.blocked_milestones || 0;
        if (blockers > 0) {
            return `🚫 ${blockers} blocker${blockers > 1 ? 's' : ''}`;
        }
        if (completion >= 80) return '🟢 Stabilnie';
        if (completion >= 40) return '🟡 Ryzyko';
        return '🔴 Opóźnienie';
    }

    getStatusEmoji(status) {
        const emojiMap = {
            'PENDING': '⏸️',
            'IN_PROGRESS': '🔄',
            'COMPLETED': '✅',
            'BLOCKED': '🚫',
            'CANCELLED': '❌'
        };
        return emojiMap[status] || '❓';
    }

    showDefineVisionDialog() {
        const vision = prompt('Zdefiniuj wizję projektu:\n\nNp. "Stworzyć najlepszy framework AI do automatyzacji"');
        if (vision) {
            this.defineVision(vision);
        }
    }

    async defineVision(visionText) {
        try {
            const response = await fetch(`${this.API_BASE}/roadmap/create`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({vision: visionText})
            });
            if (!response.ok) {
                throw new Error('Failed to create roadmap');
            }
            await response.json();
            this.showNotification('Roadmapa utworzona! Milestones i Tasks zostały wygenerowane.', 'success');
            this.loadRoadmap({ showLoading: true });
        } catch (error) {
            console.error('Error creating roadmap:', error);
            this.showNotification('Błąd tworzenia roadmapy: ' + error.message, 'error');
        }
    }

    async startCampaign() {
        if (!confirm('Uruchomić Tryb Kampanii?\n\nVenom będzie autonomicznie realizował roadmapę.')) {
            return;
        }
        try {
            const response = await fetch(`${this.API_BASE}/campaign/start`, {
                method: 'POST'
            });
            if (!response.ok) {
                throw new Error('Failed to start campaign');
            }
            this.showNotification('Kampania rozpoczęta! Monitoruj postępy w Task Monitor.', 'success');
        } catch (error) {
            console.error('Error starting campaign:', error);
            this.showNotification('Błąd uruchamiania kampanii: ' + error.message, 'error');
        }
    }

    async requestStatusReport() {
        try {
            const response = await fetch(`${this.API_BASE}/roadmap/status`);
            if (!response.ok) {
                throw new Error('Failed to get status report');
            }
            const data = await response.json();
            this.showNotification(data.report || 'Brak raportu', 'info');
        } catch (error) {
            console.error('Error getting status:', error);
            this.showNotification('Błąd pobierania raportu: ' + error.message, 'error');
        }
    }

    toggleAutoRefresh(enabled) {
        this.autoRefreshEnabled = enabled;
        if (this.elements.autoRefreshToggle) {
            this.elements.autoRefreshToggle.checked = enabled;
        }
        this.persistPreferences({ autoRefresh: this.autoRefreshEnabled });
        if (enabled) {
            this.loadRoadmap({ silent: true });
        } else {
            this.stopAutoRefresh();
        }
        this.startAutoRefresh();
    }

    startAutoRefresh() {
        this.stopAutoRefresh();
        if (!this.autoRefreshEnabled) return;
        this.refreshInterval = setInterval(() => {
            this.loadRoadmap({ silent: true });
        }, 30000);
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    loadPreferences() {
        const defaults = { ...WAR_ROOM_PREFS_DEFAULTS };
        try {
            if (!window?.localStorage) {
                return defaults;
            }
            const raw = window.localStorage.getItem(WAR_ROOM_PREFS_KEY);
            if (!raw) {
                return defaults;
            }
            const parsed = JSON.parse(raw);
            return {
                autoRefresh:
                    parsed.autoRefresh === undefined ? defaults.autoRefresh : !!parsed.autoRefresh
            };
        } catch (error) {
            console.warn('Nie udało się wczytać preferencji War Room:', error);
            return defaults;
        }
    }

    savePreferences() {
        try {
            if (!window?.localStorage) {
                return;
            }
            window.localStorage.setItem(WAR_ROOM_PREFS_KEY, JSON.stringify(this.preferences));
        } catch (error) {
            console.warn('Nie udało się zapisać preferencji War Room:', error);
        }
    }

    persistPreferences(partial) {
        this.preferences = {
            ...this.preferences,
            ...partial
        };
        this.savePreferences();
    }

    applyPreferencesToControls() {
        if (this.elements?.autoRefreshToggle) {
            this.elements.autoRefreshToggle.checked = !!this.autoRefreshEnabled;
        }
    }

    escapeHtml(text) {
        if (!text) return '';
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    getPercentage(value) {
        const parsed = Number(value);
        if (Number.isNaN(parsed)) {
            return 0;
        }
        return Math.min(100, Math.max(0, parsed)).toFixed(1);
    }
}

// Initialize after DOM loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.body?.dataset?.layout === 'strategy') {
        window.strategyDashboard = new StrategyDashboard();
    }
});
