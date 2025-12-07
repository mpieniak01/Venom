// Venom Cockpit - Main Application

class VenomDashboard {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.tasks = new Map();

        // Constants
        this.TASK_CONTENT_TRUNCATE_LENGTH = 50;
        this.LOG_ENTRY_MAX_COUNT = 100;

        this.initElements();
        this.initWebSocket();
        this.initEventHandlers();
        this.startMetricsPolling();
        this.startRepositoryStatusPolling();
        this.initNotificationContainer();
    }

    initNotificationContainer() {
        // Create notification container for toast messages
        const container = document.createElement('div');
        container.id = 'notification-container';
        container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 10px;
        `;
        document.body.appendChild(container);
    }

    showNotification(message, type = 'info') {
        const container = document.getElementById('notification-container');
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
            notification.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 5000);
    }

    initElements() {
        this.elements = {
            connectionStatus: document.getElementById('connectionStatus'),
            statusText: document.getElementById('statusText'),
            taskInput: document.getElementById('taskInput'),
            sendButton: document.getElementById('sendButton'),
            chatMessages: document.getElementById('chatMessages'),
            liveFeed: document.getElementById('liveFeed'),
            taskList: document.getElementById('taskList'),
            metricTasks: document.getElementById('metricTasks'),
            metricSuccess: document.getElementById('metricSuccess'),
            metricUptime: document.getElementById('metricUptime'),
            // Repository status elements
            branchName: document.getElementById('branchName'),
            changesText: document.getElementById('changesText'),
            repoChanges: document.getElementById('repoChanges'),
        };
    }

    initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/events`;

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.updateConnectionStatus(true);
                this.reconnectAttempts = 0;
                this.addLogEntry('info', 'Connected to Venom Telemetry');
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
                console.error('WebSocket error:', error);
                this.addLogEntry('error', 'WebSocket connection error');
            };

            this.ws.onclose = () => {
                console.log('WebSocket closed');
                this.updateConnectionStatus(false);
                this.attemptReconnect();
            };
        } catch (error) {
            console.error('Cannot create WebSocket:', error);
            this.updateConnectionStatus(false);
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);

            this.addLogEntry('warning', `Reconnecting in ${delay/1000}s... (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

            setTimeout(() => {
                this.initWebSocket();
            }, delay);
        } else {
            this.addLogEntry('error', 'Cannot connect to server. Please refresh the page.');
        }
    }

    updateConnectionStatus(connected) {
        if (connected) {
            this.elements.connectionStatus.classList.add('connected');
            this.elements.statusText.textContent = 'Connected';
        } else {
            this.elements.connectionStatus.classList.remove('connected');
            this.elements.statusText.textContent = 'Disconnected';
        }
    }

    handleWebSocketMessage(data) {
        const { type, agent, message, data: eventData } = data;

        // Add to live feed
        const logLevel = this.getLogLevel(type);
        this.addLogEntry(logLevel, `[${type}] ${agent ? agent + ': ' : ''}${message}`);

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
                this.addChatMessage('assistant', message, agent);
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
                content: data.content || 'New task',
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
        this.addChatMessage('assistant', 'Plan created - details in Live Feed', 'Architect');
    }

    handleHealingStarted(data) {
        if (data && data.task_id) {
            this.showNotification('🔄 Rozpoczynam automatyczne testy i naprawy', 'info');
            this.addChatMessage('assistant', `Uruchamiam pętlę samonaprawy (max ${data.max_iterations} iteracji)`, 'Guardian');
        }
    }

    handleTestRunning(data) {
        if (data && data.task_id) {
            const iterationInfo = data.iteration ? ` - Próba ${data.iteration}` : '';
            this.addChatMessage('assistant', `🔍 Uruchamiam testy${iterationInfo}`, 'Guardian');
        }
    }

    handleTestResult(data, message) {
        if (data && data.task_id) {
            if (data.success) {
                // Testy przeszły ✅
                this.showNotification('✅ Wszystkie testy przeszły pomyślnie!', 'success');
                this.addChatMessage('assistant', `✅ ${message}`, 'Guardian');
                
                // Pokaż zielony pasek
                this.showTestProgressBar(data.task_id, true, data.iterations || 1);
            } else {
                // Testy nie przeszły ❌
                this.addChatMessage('assistant', `❌ ${message}`, 'Guardian');
                
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
                'Guardian'
            );
            
            // Pokaż fragment raportu jeśli dostępny
            if (data.final_report) {
                const reportPreview = data.final_report.substring(0, 200);
                this.addChatMessage('assistant', `Ostatni raport: ${reportPreview}...`, 'Guardian');
            }
        }
    }

    handleHealingError(data) {
        if (data && data.task_id) {
            this.showNotification('❌ Błąd podczas pętli samonaprawy', 'error');
            this.addChatMessage('assistant', `❌ Błąd: ${data.error}`, 'Guardian');
        }
    }

    showTestProgressBar(taskId, success, iteration) {
        // Stwórz lub zaktualizuj pasek postępu testów
        let progressBar = document.getElementById(`test-progress-${taskId}`);
        
        if (!progressBar) {
            // Utwórz nowy pasek postępu
            progressBar = document.createElement('div');
            progressBar.id = `test-progress-${taskId}`;
            progressBar.className = 'test-progress';
            progressBar.style.cssText = `
                margin: 10px 0;
                padding: 10px;
                border-radius: 6px;
                background: ${success ? '#d1fae5' : '#fee2e2'};
                border: 2px solid ${success ? '#10b981' : '#ef4444'};
            `;
            
            // Dodaj do chat messages
            this.elements.chatMessages.appendChild(progressBar);
        }
        
        // Zaktualizuj zawartość
        const emoji = success ? '🟢' : '🔴';
        const statusText = success ? 'SUKCES' : 'BŁĄD';
        const color = success ? '#10b981' : '#ef4444';
        
        progressBar.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px;">
                <div style="font-size: 24px;">${emoji}</div>
                <div>
                    <div style="font-weight: bold; color: ${color};">${statusText}</div>
                    <div style="font-size: 12px; color: #6b7280;">Iteracja: ${iteration}</div>
                </div>
            </div>
        `;
        
        // Auto-scroll
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
    }

    addLogEntry(level, message) {
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

    addChatMessage(role, content, agent = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        if (agent) {
            const agentSpan = document.createElement('strong');
            agentSpan.textContent = agent + ': ';
            messageDiv.appendChild(agentSpan);

            const contentSpan = document.createElement('span');
            contentSpan.textContent = content;
            messageDiv.appendChild(contentSpan);
        } else {
            messageDiv.textContent = content;
        }

        this.elements.chatMessages.appendChild(messageDiv);
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
    }

    updateTaskList() {
        // Clear task list
        this.elements.taskList.innerHTML = '';

        if (this.tasks.size === 0) {
            // Brak aktywnych zadań - use DOM methods for consistency
            const emptyState = document.createElement('p');
            emptyState.className = 'empty-state';
            emptyState.textContent = 'Brak aktywnych zadań';
            this.elements.taskList.appendChild(emptyState);
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

            const contentDiv = document.createElement('div');
            const strong = document.createElement('strong');
            strong.textContent = `${statusEmoji} ${truncatedContent}...`;
            contentDiv.appendChild(strong);

            const statusDiv = document.createElement('div');
            statusDiv.className = 'task-status';
            statusDiv.textContent = `Status: ${task.status}`;

            taskItem.appendChild(contentDiv);
            taskItem.appendChild(statusDiv);

            this.elements.taskList.appendChild(taskItem);
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

        // Repository quick actions
        const syncBtn = document.getElementById('syncRepoBtn');
        if (syncBtn) {
            syncBtn.addEventListener('click', () => {
                this.handleSyncRepo();
            });
        }

        const undoBtn = document.getElementById('undoChangesBtn');
        if (undoBtn) {
            undoBtn.addEventListener('click', () => {
                this.handleUndoChanges();
            });
        }
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

            // Send via API
            const response = await fetch('/api/v1/tasks', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ content }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();

            // Clear input
            this.elements.taskInput.value = '';

            this.addLogEntry('info', `Task sent: ${result.task_id}`);
            this.showNotification('Zadanie wysłane pomyślnie', 'success');

        } catch (error) {
            console.error('Error sending task:', error);
            this.addLogEntry('error', `Cannot send task: ${error.message}`);
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
                return;
            }

            const data = await response.json();

            if (data.status === 'success' && data.is_git_repo) {
                this.updateRepositoryStatus(
                    data.branch,
                    data.has_changes,
                    data.modified_count
                );
            } else {
                // Not a git repo or error
                this.updateRepositoryStatus('-', false, 0);
            }

        } catch (error) {
            console.error('Error fetching repository status:', error);
            // Don't update UI on error
        }
    }

    // Memory Tab Functions
    initMemoryTab() {
        // Setup tab switching
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                const tabName = button.getAttribute('data-tab');
                this.switchTab(tabName);
            });
        });

        // Setup refresh buttons
        const refreshLessons = document.getElementById('refreshLessons');
        if (refreshLessons) {
            refreshLessons.addEventListener('click', () => {
                this.fetchLessons();
            });
        }

        const scanGraph = document.getElementById('scanGraph');
        if (scanGraph) {
            scanGraph.addEventListener('click', () => {
                this.triggerGraphScan();
            });
        }

        // Initial load
        this.fetchLessons();
        this.fetchGraphSummary();
    }

    switchTab(tabName) {
        // Update buttons
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(btn => {
            if (btn.getAttribute('data-tab') === tabName) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        // Update content
        const tabContents = document.querySelectorAll('.tab-content');
        tabContents.forEach(content => {
            content.classList.remove('active');
        });

        if (tabName === 'feed') {
            document.getElementById('feedTab').classList.add('active');
        } else if (tabName === 'jobs') {
            document.getElementById('jobsTab').classList.add('active');
            // Refresh data when switching to jobs tab
            this.fetchBackgroundJobsStatus();
        } else if (tabName === 'memory') {
            document.getElementById('memoryTab').classList.add('active');
            // Refresh data when switching to memory tab
            this.fetchLessons();
            this.fetchGraphSummary();
        }
    }

    async fetchLessons() {
        try {
            const response = await fetch('/api/v1/lessons?limit=10');
            const data = await response.json();

            const lessonsList = document.getElementById('lessonsList');
            if (!lessonsList) return;

            if (data.status === 'success' && data.lessons.length > 0) {
                lessonsList.innerHTML = '';
                data.lessons.forEach(lesson => {
                    const lessonItem = this.createLessonElement(lesson);
                    lessonsList.appendChild(lessonItem);
                });
            } else {
                lessonsList.innerHTML = '<p class="empty-state">Brak lekcji</p>';
            }
        } catch (error) {
            console.error('Error fetching lessons:', error);
            const lessonsList = document.getElementById('lessonsList');
            if (lessonsList) {
                lessonsList.innerHTML = '<p class="empty-state">Błąd ładowania lekcji</p>';
            }
        }
    }

    createLessonElement(lesson) {
        const div = document.createElement('div');
        const isError = lesson.result.toLowerCase().includes('błąd') ||
                        lesson.result.toLowerCase().includes('error');
        div.className = `lesson-item ${isError ? 'error' : 'success'}`;

        const situation = document.createElement('div');
        situation.className = 'lesson-situation';
        situation.textContent = lesson.situation.slice(0, 80) + (lesson.situation.length > 80 ? '...' : '');

        const feedback = document.createElement('div');
        feedback.className = 'lesson-feedback';
        feedback.textContent = '💡 ' + lesson.feedback.slice(0, 100) + (lesson.feedback.length > 100 ? '...' : '');

        const tags = document.createElement('div');
        tags.className = 'lesson-tags';
        lesson.tags.forEach(tag => {
            const tagSpan = document.createElement('span');
            tagSpan.className = 'lesson-tag';
            tagSpan.textContent = tag;
            tags.appendChild(tagSpan);
        });

        div.appendChild(situation);
        div.appendChild(feedback);
        if (lesson.tags.length > 0) {
            div.appendChild(tags);
        }

        return div;
    }

    async fetchGraphSummary() {
        try {
            const response = await fetch('/api/v1/graph/summary');
            const data = await response.json();

            const graphSummary = document.getElementById('graphSummary');
            if (!graphSummary) return;

            if (data.status === 'success' && data.summary) {
                const summary = data.summary;

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
                scanButton.textContent = '🔍 Skanuj';
                scanButton.disabled = false;
            }
        }
    }

    // Update repository status in header
    updateRepositoryStatus(branch, hasChanges, changeCount = 0) {
        if (!this.elements.branchName || !this.elements.repoChanges) {
            return;
        }

        // Update branch name
        this.elements.branchName.textContent = branch || '-';

        // Update changes status
        if (hasChanges) {
            this.elements.repoChanges.classList.add('dirty');
            const filesText = changeCount === 1 ? 'file' : 'files';
            this.elements.repoChanges.innerHTML = `🔴 <span id="changesText">${changeCount} modified ${filesText}</span>`;
        } else {
            this.elements.repoChanges.classList.remove('dirty');
            this.elements.repoChanges.innerHTML = `🟢 <span id="changesText">Clean</span>`;
        }

        // Re-cache the changesText reference after innerHTML update
        this.elements.changesText = document.getElementById('changesText');
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
        const refreshBtn = document.getElementById('refreshJobsBtn');

        if (pauseBtn) {
            pauseBtn.addEventListener('click', () => this.pauseBackgroundJobs());
        }

        if (resumeBtn) {
            resumeBtn.addEventListener('click', () => this.resumeBackgroundJobs());
        }

        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.fetchBackgroundJobsStatus());
        }
    }

    async fetchBackgroundJobsStatus() {
        // Fetch all background job statuses
        await Promise.all([
            this.fetchSchedulerStatus(),
            this.fetchSchedulerJobs(),
            this.fetchWatcherStatus(),
            this.fetchDocumenterStatus(),
            this.fetchGardenerStatus()
        ]);
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
                            ${scheduler.is_running ? '🟢 Running' : '🔴 Stopped'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Jobs Count:</span>
                        <span class="status-value">${scheduler.jobs_count}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Paused:</span>
                        <span class="status-value">${scheduler.paused ? '⏸️ Yes' : '▶️ No'}</span>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error fetching scheduler status:', error);
            document.getElementById('schedulerStatus').innerHTML = 
                '<p class="error-state">❌ Nie można pobrać statusu schedulera</p>';
        }
    }

    async fetchSchedulerJobs() {
        try {
            const response = await fetch('/api/v1/scheduler/jobs');
            if (!response.ok) throw new Error('Failed to fetch jobs');
            
            const data = await response.json();
            const jobsDiv = document.getElementById('jobsList');
            
            if (data.jobs && data.jobs.length > 0) {
                jobsDiv.innerHTML = data.jobs.map(job => {
                    // Walidacja i formatowanie daty
                    let nextRunText = 'N/A';
                    if (job.next_run_time) {
                        try {
                            const date = new Date(job.next_run_time);
                            if (!isNaN(date.getTime())) {
                                nextRunText = date.toLocaleString();
                            }
                        } catch (e) {
                            console.warn('Invalid date format:', job.next_run_time);
                        }
                    }
                    
                    return `
                    <div class="job-item">
                        <div class="job-header">
                            <span class="job-id">${job.id}</span>
                            <span class="job-type">${job.type || 'interval'}</span>
                        </div>
                        <div class="job-description">${job.description || 'No description'}</div>
                        <div class="job-next-run">
                            Next run: ${nextRunText}
                        </div>
                    </div>
                `}).join('');
            } else {
                jobsDiv.innerHTML = '<p class="empty-state">Brak aktywnych zadań</p>';
            }
        } catch (error) {
            console.error('Error fetching jobs:', error);
            document.getElementById('jobsList').innerHTML = 
                '<p class="error-state">❌ Nie można pobrać listy zadań</p>';
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
                statusDiv.innerHTML = `
                    <div class="status-item">
                        <span class="status-label">Status:</span>
                        <span class="status-value ${watcher.is_running ? 'status-active' : 'status-inactive'}">
                            ${watcher.is_running ? '🟢 Watching' : '🔴 Stopped'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Workspace:</span>
                        <span class="status-value">${watcher.workspace_root}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Monitoring:</span>
                        <span class="status-value">${watcher.monitoring_extensions.join(', ')}</span>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error fetching watcher status:', error);
            document.getElementById('watcherStatus').innerHTML = 
                '<p class="error-state">❌ Nie można pobrać statusu watchera</p>';
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
                        <span class="status-label">Enabled:</span>
                        <span class="status-value ${documenter.enabled ? 'status-active' : 'status-inactive'}">
                            ${documenter.enabled ? '🟢 Yes' : '🔴 No'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Processing Files:</span>
                        <span class="status-value">${documenter.processing_files}</span>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error fetching documenter status:', error);
            document.getElementById('documenterStatus').innerHTML = 
                '<p class="error-state">❌ Nie można pobrać statusu documentera</p>';
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
                        <span class="status-label">Running:</span>
                        <span class="status-value ${gardener.is_running ? 'status-active' : 'status-inactive'}">
                            ${gardener.is_running ? '🟢 Yes' : '🔴 No'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Idle Refactoring:</span>
                        <span class="status-value">${gardener.idle_refactoring_enabled ? '✅ Enabled' : '❌ Disabled'}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">In Progress:</span>
                        <span class="status-value">${gardener.idle_refactoring_in_progress ? '🔄 Yes' : '✅ No'}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Last Scan:</span>
                        <span class="status-value">${gardener.last_scan_time ? new Date(gardener.last_scan_time).toLocaleString() : 'Never'}</span>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error fetching gardener status:', error);
            document.getElementById('gardenerStatus').innerHTML = 
                '<p class="error-state">❌ Nie można pobrać statusu gardenera</p>';
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
        micButton.querySelector('.mic-text').textContent = 'Push to Talk';

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
            iotMetrics.style.display = 'grid';
            
            document.getElementById('iotCpuTemp').textContent = '45.2°C';
            document.getElementById('iotMemory').textContent = '42%';
            document.getElementById('iotDisk').textContent = '65%';
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
});
