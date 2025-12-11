// Venom OS - API Module
// Obsługa wywołań REST API

export class ApiClient {
    constructor(dashboard) {
        this.dashboard = dashboard;
        this.baseUrl = '/api/v1';
    }

    async sendTask(content, storeKnowledge = true) {
        const response = await fetch(`${this.baseUrl}/tasks`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                content: content,
                store_knowledge: storeKnowledge,
            }),
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async fetchMetrics() {
        const response = await fetch(`${this.baseUrl}/metrics`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async fetchRepositoryStatus() {
        const response = await fetch(`${this.baseUrl}/repository/status`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async fetchIntegrations() {
        const response = await fetch(`${this.baseUrl}/integrations/status`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async fetchQueueStatus() {
        const response = await fetch(`${this.baseUrl}/queue/status`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async pauseQueue() {
        const response = await fetch(`${this.baseUrl}/queue/pause`, {
            method: 'POST',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async resumeQueue() {
        const response = await fetch(`${this.baseUrl}/queue/resume`, {
            method: 'POST',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async purgeQueue() {
        const response = await fetch(`${this.baseUrl}/queue/purge`, {
            method: 'POST',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async emergencyStop() {
        const response = await fetch(`${this.baseUrl}/queue/emergency-stop`, {
            method: 'POST',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async abortTask(taskId) {
        const response = await fetch(`${this.baseUrl}/tasks/${taskId}/abort`, {
            method: 'POST',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async fetchLessons() {
        const response = await fetch(`${this.baseUrl}/memory/lessons`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async fetchGraphSummary() {
        const response = await fetch(`${this.baseUrl}/memory/graph/summary`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async triggerGraphScan() {
        const response = await fetch(`${this.baseUrl}/memory/graph/scan`, {
            method: 'POST',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async fetchModels() {
        const response = await fetch(`${this.baseUrl}/models`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async installModel(modelName) {
        const response = await fetch(`${this.baseUrl}/models/install`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ model_name: modelName }),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async unloadAllModels() {
        const response = await fetch(`${this.baseUrl}/models/unload-all`, {
            method: 'POST',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async fetchHistory() {
        const response = await fetch(`${this.baseUrl}/history`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async fetchHistoryDetails(historyId) {
        const response = await fetch(`${this.baseUrl}/history/${historyId}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async fetchTokenomics() {
        const response = await fetch(`${this.baseUrl}/tokenomics/session-cost`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async fetchCostMode() {
        const response = await fetch(`${this.baseUrl}/cost-guard/mode`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    async setCostMode(enabled) {
        const response = await fetch(`${this.baseUrl}/cost-guard/mode`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ enabled }),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }
}
