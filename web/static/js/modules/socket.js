// Venom OS - WebSocket Module
// Obsługa połączenia WebSocket i zdarzeń w czasie rzeczywistym

export class SocketManager {
    constructor(dashboard) {
        this.dashboard = dashboard;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    init() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/events`;

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('Połączono z WebSocket');
                this.dashboard.updateConnectionStatus(true);
                this.reconnectAttempts = 0;
                this.dashboard.addLogEntry('info', 'Połączono z telemetrią Venoma');
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };

            this.ws.onerror = (error) => {
                console.error('Błąd WebSocket:', error);
                this.dashboard.addLogEntry('error', 'Błąd połączenia WebSocket');
            };

            this.ws.onclose = () => {
                console.log('Połączenie WebSocket zamknięte');
                this.dashboard.updateConnectionStatus(false);
                this.attemptReconnect();
            };
        } catch (error) {
            console.error('Nie można utworzyć WebSocket:', error);
            this.dashboard.updateConnectionStatus(false);
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);

            this.dashboard.addLogEntry('warning', `Ponowna próba za ${delay/1000}s... (podejście ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

            setTimeout(() => {
                this.init();
            }, delay);
        } else {
            this.dashboard.addLogEntry('error', 'Nie można połączyć z serwerem. Odśwież stronę.');
        }
    }

    handleMessage(data) {
        const { type, agent, message, data: eventData } = data;

        // Add to live feed
        const logLevel = this.getLogLevel(type);
        this.dashboard.addLogEntry(logLevel, `[${type}] ${agent ? agent + ': ' : ''}${message}`);

        // Delegate to dashboard for specific event handling
        this.dashboard.handleWebSocketEvent(type, agent, message, eventData);
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

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket not connected, cannot send:', data);
        }
    }

    close() {
        if (this.ws) {
            this.ws.close();
        }
    }
}
