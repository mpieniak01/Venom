// Venom OS - UI Module
// Obsługa manipulacji DOM i renderowania widgetów

export class UIManager {
    constructor(dashboard) {
        this.dashboard = dashboard;
    }

    // === CHAT MESSAGES ===
    addChatMessage(role, content, agent = null, metadata = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        if (agent && role === 'assistant') {
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
        if (metadata && typeof metadata === 'object' && metadata.model_name) {
            const badge = document.createElement('span');
            badge.className = metadata.is_paid ? 'model-badge paid' : 'model-badge free';

            const icon = metadata.is_paid ? '⚡' : '🤖';
            const modelName = metadata.model_name || 'Nieznany';

            badge.textContent = `${icon} ${modelName}`;
            badge.title = `Dostawca: ${metadata.provider || 'nieznany'}`;

            messageDiv.appendChild(badge);
        }

        this.dashboard.elements.chatMessages.appendChild(messageDiv);
        this.scrollChatToBottom();
    }

    formatMessageContent(text) {
        if (!text) {
            return '';
        }
        const safeText = this.escapeHtml(text);
        return safeText.replace(/(?:\r\n|\r|\n)/g, '<br>');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    scrollChatToBottom() {
        if (this.dashboard.elements.chatMessages) {
            this.dashboard.elements.chatMessages.scrollTop = this.dashboard.elements.chatMessages.scrollHeight;
        }
    }

    // === LOG ENTRIES ===
    addLogEntry(level, message) {
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${level}`;

        const timestampSpan = document.createElement('span');
        timestampSpan.className = 'timestamp';
        timestampSpan.textContent = `[${this.getCurrentTime()}]`;

        const messageSpan = document.createElement('span');
        messageSpan.className = 'message';
        messageSpan.textContent = message;

        logEntry.appendChild(timestampSpan);
        logEntry.appendChild(messageSpan);

        const liveFeed = this.dashboard.elements.liveFeed;
        if (liveFeed) {
            liveFeed.appendChild(logEntry);
            
            // Limit entries
            const entries = liveFeed.getElementsByClassName('log-entry');
            if (entries.length > this.dashboard.LOG_ENTRY_MAX_COUNT) {
                entries[0].remove();
            }

            // Auto scroll
            liveFeed.scrollTop = liveFeed.scrollHeight;
        }
    }

    getCurrentTime() {
        const now = new Date();
        return now.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    // === NOTIFICATIONS ===
    showNotification(message, type = 'info') {
        const container = document.getElementById('notification-container');
        if (!container) return;

        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.style.cssText = `
            background-color: ${type === 'error' ? '#ef4444' : type === 'warning' ? '#f59e0b' : '#10b981'};
            color: white;
            padding: 12px 20px;
            border-radius: 6px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            min-width: 250px;
            max-width: 400px;
            animation: slideIn 0.3s ease-out;
        `;
        notification.textContent = message;

        container.appendChild(notification);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            notification.style.animation = 'fadeOut 0.3s ease-out';
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }

    // === METRICS ===
    updateMetrics(metrics) {
        const elements = this.dashboard.elements;
        
        if (elements.metricTasks) {
            elements.metricTasks.textContent = metrics.tasks_count || 0;
        }
        if (elements.metricSuccess) {
            elements.metricSuccess.textContent = `${metrics.success_rate || 0}%`;
        }
        if (elements.metricUptime) {
            elements.metricUptime.textContent = this.formatUptime(metrics.uptime_seconds || 0);
        }
        if (elements.metricNetwork) {
            elements.metricNetwork.textContent = this.formatBytes(metrics.network_io || 0);
        }
    }

    formatUptime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else if (minutes > 0) {
            return `${minutes}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    }

    // === QUEUE STATUS ===
    updateQueueStatus(status) {
        const elements = this.dashboard.elements;
        
        if (elements.queueActive) {
            elements.queueActive.textContent = status.active_count || 0;
        }
        if (elements.queuePending) {
            elements.queuePending.textContent = status.pending_count || 0;
        }
        if (elements.queueLimit) {
            elements.queueLimit.textContent = status.max_active || 5;
        }

        // Update pause/resume button
        const pauseResumeBtn = elements.pauseResumeBtn;
        if (pauseResumeBtn) {
            const isPaused = status.is_paused || false;
            pauseResumeBtn.dataset.state = isPaused ? 'paused' : 'running';
            pauseResumeBtn.querySelector('.btn-text').textContent = isPaused ? 'WZNÓW' : 'PAUZA';
            pauseResumeBtn.querySelector('.btn-icon').textContent = isPaused ? '▶️' : '⏸️';
        }
    }

    // === CONNECTION STATUS ===
    updateConnectionStatus(connected) {
        const elements = this.dashboard.elements;
        
        if (elements.connectionStatus) {
            if (connected) {
                elements.connectionStatus.classList.add('connected');
            } else {
                elements.connectionStatus.classList.remove('connected');
            }
        }
        
        if (elements.statusText) {
            elements.statusText.textContent = connected ? 'Połączono' : 'Rozłączono';
        }
    }

    // === TABS ===
    switchTab(tabName) {
        // Remove active from all tab buttons and contents
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });

        // Activate target tab
        const targetButton = document.querySelector(`[data-tab="${tabName}"]`);
        if (targetButton) {
            targetButton.classList.add('active');
        }

        const targetContent = document.getElementById(`${tabName}Tab`);
        if (targetContent) {
            targetContent.classList.add('active');
        }
    }
}
