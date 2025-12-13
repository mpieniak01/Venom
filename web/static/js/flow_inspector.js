(() => {
    const DIAGRAM_AUTO_REFRESH_INTERVAL_MS = 3000;
    const TASKS_AUTO_REFRESH_INTERVAL_MS = 5000;

    let selectedTaskId = null;
    let diagramRefreshTimer = null;
    let tasksRefreshTimer = null;

    const PREFS_KEY = 'venomFlowInspectorPrefs';
    const defaultPrefs = {
        filterStatus: 'all',
        searchQuery: '',
        autoRefresh: true
    };

    const loadPreferences = () => {
        try {
            if (!window?.localStorage) {
                return { ...defaultPrefs };
            }
            const raw = window.localStorage.getItem(PREFS_KEY);
            if (!raw) {
                return { ...defaultPrefs };
            }
            const parsed = JSON.parse(raw);
            return {
                filterStatus: parsed.filterStatus || defaultPrefs.filterStatus,
                searchQuery: parsed.searchQuery || defaultPrefs.searchQuery,
                autoRefresh:
                    parsed.autoRefresh === undefined
                        ? defaultPrefs.autoRefresh
                        : !!parsed.autoRefresh
            };
        } catch (error) {
            console.warn('Nie można wczytać preferencji Flow Inspector:', error);
            return { ...defaultPrefs };
        }
    };

    const savePreferences = (prefs) => {
        try {
            if (!window?.localStorage) {
                return;
            }
            window.localStorage.setItem(PREFS_KEY, JSON.stringify({
                filterStatus: prefs.filterStatus,
                searchQuery: prefs.searchQuery,
                autoRefresh: prefs.autoRefresh
            }));
        } catch (error) {
            console.warn('Nie można zapisać preferencji Flow Inspector:', error);
        }
    };

    const storedPrefs = loadPreferences();

    const state = {
        tasks: [],
        filterStatus: storedPrefs.filterStatus,
        searchQuery: storedPrefs.searchQuery,
        autoRefresh: storedPrefs.autoRefresh,
        lastDiagramCode: '',
        lastDiagramSvg: null,
        lastUpdated: null
    };

    const qs = (id) => document.getElementById(id);
    const copyBtn = qs('copyMermaidBtn');
    const downloadBtn = qs('downloadDiagramBtn');
    const flowActiveCountEl = qs('flowActiveCount');
    const flowLastUpdatedEl = qs('flowLastUpdated');

    const escapeHtml = (text) => {
        if (text === undefined || text === null) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    const downloadBlob = (blob, filename) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    const setExportButtonsEnabled = (enabled) => {
        [copyBtn, downloadBtn].forEach((btn) => {
            if (!btn) return;
            btn.disabled = !enabled;
            if (!enabled) {
                btn.classList.remove('is-success');
            }
        });
    };

    const flashButtonState = (btn, text) => {
        if (!btn) return;
        const original = btn.dataset.defaultLabel || btn.textContent;
        btn.dataset.defaultLabel = original;
        btn.textContent = text;
        btn.classList.add('is-success');
        setTimeout(() => {
            btn.textContent = btn.dataset.defaultLabel || original;
            btn.classList.remove('is-success');
        }, 1500);
    };

    const copyMermaidCode = async () => {
        if (!state.lastDiagramCode) return;
        let success = false;
        try {
            if (navigator?.clipboard?.writeText) {
                await navigator.clipboard.writeText(state.lastDiagramCode);
                success = true;
            }
        } catch (error) {
            console.warn('Clipboard API unavailable:', error);
        }

        if (!success) {
            const textarea = document.createElement('textarea');
            textarea.value = state.lastDiagramCode;
            textarea.setAttribute('readonly', '');
            textarea.style.position = 'absolute';
            textarea.style.left = '-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                success = document.execCommand('copy');
            } catch (error) {
                success = false;
            } finally {
                document.body.removeChild(textarea);
            }
        }

        flashButtonState(copyBtn, success ? '✅ Skopiowano' : '⚠️ Błąd');
    };

    const getSvgDimensions = (svgEl) => {
        if (!svgEl) {
            return { width: 0, height: 0 };
        }
        const viewBox = svgEl.viewBox && svgEl.viewBox.baseVal;
        if (viewBox && viewBox.width && viewBox.height) {
            return { width: viewBox.width, height: viewBox.height };
        }
        const rect = svgEl.getBoundingClientRect();
        const width = rect.width || svgEl.clientWidth || 1200;
        const height = rect.height || svgEl.clientHeight || 600;
        return { width, height };
    };

    const downloadDiagramPng = () => {
        const svg = state.lastDiagramSvg || document.querySelector('#mermaidContainer svg');
        if (!svg || !state.lastDiagramCode) return;

        const serializer = new XMLSerializer();
        const svgString = serializer.serializeToString(svg);
        const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
        const image = new Image();
        image.crossOrigin = 'anonymous';
        const { width, height } = getSvgDimensions(svg);
        const scale = Math.max(window.devicePixelRatio || 1, 2);

        const objectUrl = URL.createObjectURL(svgBlob);

        image.onload = () => {
            const canvas = document.createElement('canvas');
            canvas.width = width * scale;
            canvas.height = height * scale;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#020617';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

            URL.revokeObjectURL(objectUrl);

            canvas.toBlob((blob) => {
                if (blob) {
                    downloadBlob(blob, `flow-${(selectedTaskId || 'diagram').slice(0, 12)}.png`);
                    flashButtonState(downloadBtn, '✅ Zapisano');
                } else {
                    downloadBlob(svgBlob, `flow-${(selectedTaskId || 'diagram').slice(0, 12)}.svg`);
                    flashButtonState(downloadBtn, '⬇️ SVG');
                }
            }, 'image/png');
        };

        image.onerror = () => {
            URL.revokeObjectURL(objectUrl);
            downloadBlob(svgBlob, `flow-${(selectedTaskId || 'diagram').slice(0, 12)}.svg`);
            flashButtonState(downloadBtn, '⬇️ SVG');
        };

        image.src = objectUrl;
    };

    setExportButtonsEnabled(false);

    const initMermaid = () => {
        if (typeof mermaid === 'undefined') return;
        mermaid.initialize({
            startOnLoad: false,
            theme: 'default',
            securityLevel: 'strict',
            sequence: {
                showSequenceNumbers: true,
                actorMargin: 50,
                width: 150,
                height: 65,
                boxMargin: 10,
                noteMargin: 10
            }
        });
    };

    const toggleSection = (element, show) => {
        if (!element) return;
        element.classList.toggle('is-hidden', !show);
    };

    const setTaskLoading = () => {
        const container = qs('taskListContainer');
        if (!container) return;
        container.innerHTML = `
            <div class="flow-loading">
                <div class="flow-spinner"></div>
                <p>Ładowanie zadań...</p>
            </div>
        `;
    };

    const persistPreferences = () => {
        savePreferences({
            filterStatus: state.filterStatus,
            searchQuery: state.searchQuery,
            autoRefresh: state.autoRefresh
        });
    };

    const matchesFilters = (task) => {
        const status = (task.status || 'unknown').toLowerCase();
        const query = (state.searchQuery || '').toLowerCase();
        const statusMatch = state.filterStatus === 'all' ? true : status === state.filterStatus;
        if (!statusMatch) return false;
        if (!query) return true;
        const lowerPrompt = (task.prompt || '').toLowerCase();
        const lowerId = (task.request_id || '').toLowerCase();
        return lowerPrompt.includes(query) || lowerId.includes(query);
    };

    const updateHeaderMeta = () => {
        if (flowActiveCountEl) {
            const activeCount = state.tasks.filter((task) => (task.status || '').toLowerCase() === 'processing').length;
            flowActiveCountEl.textContent = String(activeCount);
        }
        if (flowLastUpdatedEl) {
            flowLastUpdatedEl.textContent = state.lastUpdated
                ? state.lastUpdated.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                : '-';
        }
    };

    const renderTasks = () => {
        const container = qs('taskListContainer');
        if (!container) return;

        const filtered = state.tasks.filter(matchesFilters);
        if (filtered.length === 0) {
            const hasQuery = (state.searchQuery || '').trim().length > 0;
            const message = hasQuery
                ? 'Brak wyników spełniających kryteria'
                : 'Brak zadań w historii';
            container.innerHTML = `
                <div class="empty-state">
                    <p>${message}</p>
                </div>
            `;
            return;
        }

        container.innerHTML = filtered.map(task => {
            const status = escapeHtml((task.status || 'unknown').toLowerCase());
            const requestId = escapeHtml(task.request_id || 'unknown');
            const shortId = escapeHtml((task.request_id || 'unknown').slice(0, 8));
            const prompt = escapeHtml(task.prompt || '---');
            const createdAt = task.created_at ? new Date(task.created_at).toLocaleString('pl-PL') : '-';

            return `
                <div class="flow-task-item status-${status} ${requestId === selectedTaskId ? 'selected' : ''}"
                     data-task-id="${requestId}" tabindex="0" role="button"
                     aria-label="Pokaż przepływ zadania ${requestId}">
                    <div class="flow-task-header">
                        <span class="flow-task-id">${shortId}...</span>
                        <span class="flow-task-status">${status.toUpperCase()}</span>
                    </div>
                    <div class="flow-task-prompt">${prompt}</div>
                    <div class="flow-task-time">${escapeHtml(createdAt)}</div>
                </div>
            `;
        }).join('');

        container.querySelectorAll('.flow-task-item').forEach(item => {
            item.addEventListener('click', () => selectTask(item.dataset.taskId));
            item.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    selectTask(item.dataset.taskId);
                }
            });
        });
    };

    const loadTasks = async () => {
        const container = qs('taskListContainer');
        if (!container) return;
        setTaskLoading();
        try {
            const response = await fetch('/api/v1/history/requests?limit=50');
            const tasks = await response.json();
            state.tasks = Array.isArray(tasks) ? tasks : [];
            state.lastUpdated = new Date();
            updateHeaderMeta();
            renderTasks();
        } catch (error) {
            console.error('Błąd podczas ładowania zadań:', error);
            container.innerHTML = `
                <div class="empty-state">
                    <p>Błąd podczas ładowania zadań</p>
                </div>
            `;
            updateHeaderMeta();
        }
    };

    const renderMermaidDiagram = async (mermaidCode) => {
        const container = qs('mermaidContainer');
        if (!container) return;
        setExportButtonsEnabled(false);
        state.lastDiagramCode = mermaidCode;
        state.lastDiagramSvg = null;
        container.innerHTML = `<div class="mermaid">${mermaidCode}</div>`;
        if (typeof mermaid === 'undefined') return;
        try {
            await mermaid.run({ querySelector: '#mermaidContainer .mermaid' });
            state.lastDiagramSvg = container.querySelector('svg');
            setExportButtonsEnabled(!!state.lastDiagramSvg);
        } catch (error) {
            console.error('Błąd renderowania Mermaid:', error);
            container.innerHTML = `
                <div class="empty-state">
                    <p>Błąd renderowania diagramu</p>
                    <pre>${escapeHtml(mermaidCode)}</pre>
                </div>
            `;
        }
    };

    const renderFlowSteps = (steps) => {
        const list = qs('flowStepsList');
        if (!list) return;
        if (!Array.isArray(steps) || steps.length === 0) {
            list.innerHTML = '<li class="empty-state">Brak kroków w tym przepływie</li>';
            return;
        }

        list.innerHTML = steps.map(step => {
            const component = escapeHtml(step.component || '---');
            const action = escapeHtml(step.action || '---');
            const details = step.details ? `<div class="flow-step-details">${escapeHtml(step.details)}</div>` : '';
            const time = step.timestamp ? new Date(step.timestamp).toLocaleTimeString('pl-PL') : '-';
            const badges = step.is_decision_gate ? '<span class="flow-badge">🔀 Decision Gate</span>' : '';
            const extraClasses = [step.is_decision_gate ? 'decision-gate' : '', step.status === 'error' ? 'error' : ''].join(' ');

            return `
                <li class="flow-step ${extraClasses}">
                    <div class="flow-step-header">
                        <span class="flow-step-component">${component} ${badges}</span>
                        <span class="flow-step-time">${escapeHtml(time)}</span>
                    </div>
                    <div class="flow-step-action">${action}</div>
                    ${details}
                </li>
            `;
        }).join('');
    };

    const loadFlowData = async (taskId) => {
        const viz = qs('flowVisualization');
        const details = qs('flowDetails');
        toggleSection(viz, true);
        toggleSection(details, true);
        try {
            const response = await fetch(`/api/v1/flow/${taskId}`);
            const flowData = await response.json();
            const diagram = flowData?.mermaid_diagram || (flowData?.data && flowData.data.mermaid_diagram) || 'graph TD; A[Brak danych];';
            const steps = flowData?.steps || flowData?.data?.steps || [];
            await renderMermaidDiagram(diagram);
            renderFlowSteps(steps);
            const status = (flowData?.status || flowData?.data?.status || '').toUpperCase();
            if (status === 'PROCESSING') {
                startDiagramAutoRefresh(taskId);
            } else {
                stopDiagramAutoRefresh();
            }
        } catch (error) {
            console.error('Błąd podczas ładowania danych przepływu:', error);
            const container = qs('mermaidContainer');
            if (container) {
                container.innerHTML = `
                    <div class="empty-state">
                        <p>Błąd podczas ładowania danych przepływu</p>
                    </div>
                `;
            }
            state.lastDiagramCode = '';
            state.lastDiagramSvg = null;
            setExportButtonsEnabled(false);
        }
    };

    const selectTask = (taskId) => {
        if (!taskId) return;
        selectedTaskId = taskId;
        document.querySelectorAll('.flow-task-item').forEach(item => {
            item.classList.toggle('selected', item.dataset.taskId === taskId);
        });
        loadFlowData(taskId);
    };

    const startDiagramAutoRefresh = (taskId) => {
        stopDiagramAutoRefresh();
        diagramRefreshTimer = setInterval(() => loadFlowData(taskId), DIAGRAM_AUTO_REFRESH_INTERVAL_MS);
    };

    const stopDiagramAutoRefresh = () => {
        if (diagramRefreshTimer) {
            clearInterval(diagramRefreshTimer);
            diagramRefreshTimer = null;
        }
    };

    const startTasksAutoRefresh = () => {
        if (!state.autoRefresh) return;
        stopTasksAutoRefresh();
        tasksRefreshTimer = setInterval(loadTasks, TASKS_AUTO_REFRESH_INTERVAL_MS);
    };

    const stopTasksAutoRefresh = () => {
        if (tasksRefreshTimer) {
            clearInterval(tasksRefreshTimer);
            tasksRefreshTimer = null;
        }
    };

    const bindEvents = () => {
        const refreshTasksBtn = qs('refreshTasksBtn');
        if (refreshTasksBtn) {
            refreshTasksBtn.addEventListener('click', () => {
                loadTasks();
            });
        }

        const refreshFlowBtn = qs('refreshFlowBtn');
        if (refreshFlowBtn) {
            refreshFlowBtn.addEventListener('click', () => {
                if (selectedTaskId) {
                    loadFlowData(selectedTaskId);
                }
            });
        }

        if (copyBtn) {
            copyBtn.addEventListener('click', copyMermaidCode);
        }

        if (downloadBtn) {
            downloadBtn.addEventListener('click', downloadDiagramPng);
        }

        const syncFilterButtons = () => {
            document.querySelectorAll('.flow-filter-btn').forEach((btn) => {
                btn.classList.toggle('active', btn.dataset.status === state.filterStatus);
            });
        };

        const searchInput = qs('flowSearchInput');
        if (searchInput) {
            searchInput.value = state.searchQuery || '';
            searchInput.addEventListener('input', (event) => {
                state.searchQuery = event.target.value || '';
                persistPreferences();
                renderTasks();
            });
        }

        document.querySelectorAll('.flow-filter-btn').forEach(button => {
            button.addEventListener('click', () => {
                state.filterStatus = button.dataset.status || 'all';
                syncFilterButtons();
                persistPreferences();
                renderTasks();
            });
        });
        syncFilterButtons();

        const autoRefreshToggle = qs('flowAutoRefreshToggle');
        if (autoRefreshToggle) {
            autoRefreshToggle.checked = state.autoRefresh;
            autoRefreshToggle.addEventListener('change', (event) => {
                state.autoRefresh = event.target.checked;
                persistPreferences();
                if (state.autoRefresh) {
                    startTasksAutoRefresh();
                } else {
                    stopTasksAutoRefresh();
                }
            });
        }

        window.addEventListener('beforeunload', () => {
            stopDiagramAutoRefresh();
            stopTasksAutoRefresh();
        });
    };

    const init = () => {
        if (!document.body || !document.body.matches('[data-layout="flow"]')) return;
        initMermaid();
        bindEvents();
        loadTasks().then(() => {
            startTasksAutoRefresh();
        });
    };

    document.addEventListener('DOMContentLoaded', init);
})();
