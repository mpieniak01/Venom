// Shared fetch helper for legacy dashboards.
(function () {
    function extractErrorDetail(data) {
        if (!data) return '';
        if (typeof data === 'string') return data;
        if (typeof data.detail === 'string') return data.detail;
        if (typeof data.message === 'string') return data.message;
        return '';
    }

    async function apiFetchJson(url, options = {}, config = {}) {
        const response = await fetch(url, options);
        const contentType = response.headers.get('content-type') || '';
        const isJson = contentType.includes('application/json');
        const data = isJson ? await response.json() : await response.text();

        if (!response.ok) {
            const detail = extractErrorDetail(data);
            const prefix = config.errorMessage ? `${config.errorMessage}: ` : '';
            throw new Error(`${prefix}${detail || `HTTP ${response.status}`}`);
        }

        return data;
    }

    async function apiFetch(url, options = {}, config = {}) {
        const response = await fetch(url, options);
        if (!response.ok) {
            const prefix = config.errorMessage ? `${config.errorMessage}: ` : '';
            throw new Error(`${prefix}HTTP ${response.status}`);
        }
        return response;
    }

    window.VenomApi = {
        apiFetchJson,
        apiFetch
    };
})();
