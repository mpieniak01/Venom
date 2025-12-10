// Venom Strategy Dashboard - War Room

class StrategyDashboard {
    constructor() {
        this.API_BASE = '/api';
        this.refreshInterval = null;

        // Add war-room-page class to body
        document.body.classList.add('war-room-page');

        this.initElements();
        this.initEventHandlers();
        this.loadRoadmap();
        this.startAutoRefresh();
    }

    initElements() {
        this.elements = {
            visionContent: document.getElementById('visionContent'),
            milestonesContent: document.getElementById('milestonesContent'),
            roadmapReportContent: document.getElementById('roadmapReportContent'),
            completionRate: document.getElementById('completionRate'),
            milestonesCompleted: document.getElementById('milestonesCompleted'),
            tasksCompleted: document.getElementById('tasksCompleted'),
        };
    }

    initEventHandlers() {
        // Przypisujemy event handlery do przycisków
        // Używamy funkcji strzałkowych aby zachować kontekst 'this'
        window.loadRoadmap = () => this.loadRoadmap();
        window.showDefineVisionDialog = () => this.showDefineVisionDialog();
        window.startCampaign = () => this.startCampaign();
        window.requestStatusReport = () => this.requestStatusReport();
    }

    showNotification(message, type = 'info') {
        // Sprawdź czy VenomDashboard jest dostępny (z app.js)
        if (window.venomDashboard && typeof window.venomDashboard.showNotification === 'function') {
            window.venomDashboard.showNotification(message, type);
        } else {
            // Fallback do alert
            console.log(`[${type.toUpperCase()}] ${message}`);
            if (type === 'error') {
                alert(message);
            }
        }
    }

    async loadRoadmap() {
        try {
            const response = await fetch(`${this.API_BASE}/roadmap`);
            if (!response.ok) {
                throw new Error('Failed to load roadmap');
            }
            const data = await response.json();
            this.renderRoadmap(data);
        } catch (error) {
            console.error('Error loading roadmap:', error);
            this.showNotification('Błąd ładowania roadmapy. Sprawdź czy serwer działa.', 'error');
        }
    }

    renderRoadmap(data) {
        // Render Vision
        if (data.vision && this.elements.visionContent) {
            const visionHtml = `
                <div class="vision-title">${this.escapeHtml(data.vision.title)}</div>
                <div>${this.escapeHtml(data.vision.description)}</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${data.vision.progress}%"></div>
                </div>
                <div style="text-align: right; margin-top: 5px;">${data.vision.progress.toFixed(1)}%</div>
            `;
            this.elements.visionContent.innerHTML = visionHtml;
        }

        // Render Milestones
        if (data.milestones && data.milestones.length > 0 && this.elements.milestonesContent) {
            const milestonesHtml = data.milestones.map(m => `
                <div class="milestone-item ${m.status.toLowerCase().replace('_', '-')}">
                    <div class="milestone-header">
                        <div class="milestone-title">
                            <span class="status-emoji">${this.getStatusEmoji(m.status)}</span>
                            ${this.escapeHtml(m.title)}
                        </div>
                        <div class="milestone-status">${this.escapeHtml(m.status)}</div>
                    </div>
                    <div>${this.escapeHtml(m.description || '')}</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${m.progress}%"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-top: 5px; font-size: 0.9em;">
                        <span>Postęp: ${m.progress.toFixed(1)}%</span>
                        <span>Priorytet: ${this.escapeHtml(m.priority)}</span>
                    </div>
                    ${m.tasks && m.tasks.length > 0 ? `
                        <div class="task-list">
                            <strong>Zadania (${m.tasks.filter(t => t.status === 'COMPLETED').length}/${m.tasks.length}):</strong>
                            ${m.tasks.map(t => `
                                <div class="task-item ${t.status === 'COMPLETED' ? 'completed' : ''}">
                                    ${this.getStatusEmoji(t.status)} ${this.escapeHtml(t.title)}
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            `).join('');
            this.elements.milestonesContent.innerHTML = milestonesHtml;
        }

        // Render KPIs
        if (data.kpis) {
            if (this.elements.completionRate) {
                this.elements.completionRate.textContent = `${data.kpis.completion_rate.toFixed(0)}%`;
            }
            if (this.elements.milestonesCompleted) {
                this.elements.milestonesCompleted.textContent =
                    `${data.kpis.milestones_completed}/${data.kpis.milestones_total}`;
            }
            if (this.elements.tasksCompleted) {
                this.elements.tasksCompleted.textContent =
                    `${data.kpis.tasks_completed}/${data.kpis.tasks_total}`;
            }
        }

        // Render full report
        if (data.report && this.elements.roadmapReportContent) {
            this.elements.roadmapReportContent.textContent = data.report;
        }
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
            const data = await response.json();
            this.showNotification('Roadmapa utworzona! Milestones i Tasks zostały wygenerowane.', 'success');
            this.loadRoadmap();
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

    startAutoRefresh() {
        // Auto-refresh every 30 seconds
        this.refreshInterval = setInterval(() => {
            this.loadRoadmap();
        }, 30000);
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
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
}

// Initialize after DOM loaded
document.addEventListener('DOMContentLoaded', () => {
    window.strategyDashboard = new StrategyDashboard();
});
