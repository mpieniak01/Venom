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
}

// Initialize after DOM loaded
document.addEventListener('DOMContentLoaded', () => {
    window.venomDashboard = new VenomDashboard();
});
