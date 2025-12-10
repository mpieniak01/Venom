/**
 * inspector.js - Interaktywny Inspektor Przepływu
 * Alpine.js + Mermaid.js + svg-pan-zoom
 */

// Inicjalizacja Mermaid
mermaid.initialize({
    startOnLoad: false,
    theme: 'default',
    securityLevel: 'loose', // Potrzebne dla interaktywności
    sequence: {
        showSequenceNumbers: true,
        actorMargin: 50,
        width: 150,
        height: 65,
        boxMargin: 10,
        noteMargin: 10
    }
});

// Globalna zmienna dla svg-pan-zoom
let panZoomInstance = null;

/**
 * Główny komponent Alpine.js dla Inspectora
 */
function inspectorApp() {
    return {
        // Stan aplikacji
        traces: [],
        currentTraceId: null,
        selectedStep: null,
        loading: false,
        currentFlowData: null,

        // Inicjalizacja
        init() {
            console.log('🔧 Inspector initialized');
            this.loadTraces();
        },

        /**
         * Ładuje listę śladów z API
         */
        async loadTraces() {
            this.loading = true;
            try {
                const response = await fetch('/api/v1/history/requests?limit=50');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                this.traces = await response.json();
                console.log(`✅ Loaded ${this.traces.length} traces`);
            } catch (error) {
                console.error('❌ Error loading traces:', error);
                this.traces = [];
            } finally {
                this.loading = false;
            }
        },

        /**
         * Wybiera ślad i ładuje jego dane
         */
        async selectTrace(traceId) {
            console.log(`🎯 Selecting trace: ${traceId}`);
            this.currentTraceId = traceId;
            this.selectedStep = null;
            
            try {
                const response = await fetch(`/api/v1/flow/${traceId}`);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                this.currentFlowData = await response.json();
                console.log('✅ Flow data loaded:', this.currentFlowData);
                
                // Renderuj diagram
                await this.renderDiagram();
            } catch (error) {
                console.error('❌ Error loading flow data:', error);
            }
        },

        /**
         * Generuje kod Mermaid Sequence Diagram z Decision Gates
         */
        generateMermaidDiagram(flowData) {
            const lines = ['sequenceDiagram'];
            lines.push('    autonumber');
            
            // Dodaj uczestników
            const participants = new Set();
            participants.add('User');
            
            for (const step of flowData.steps) {
                if (step.component !== 'DecisionGate') {
                    participants.add(step.component);
                }
            }
            
            // Definicje uczestników
            for (const participant of Array.from(participants).sort()) {
                if (participant !== 'User') {
                    lines.push(`    participant ${participant}`);
                }
            }
            
            // Prompt użytkownika
            lines.push('');
            const promptText = flowData.prompt.length > 50 
                ? flowData.prompt.slice(0, 50) + '...' 
                : flowData.prompt;
            lines.push(`    User->>Orchestrator: ${promptText}`);
            
            let lastComponent = 'Orchestrator';
            
            // Dodaj kroki
            for (let i = 0; i < flowData.steps.length; i++) {
                const step = flowData.steps[i];
                
                if (step.is_decision_gate) {
                    // Decision Gate - wyróżnij jako notatka z tłem
                    const details = step.details || '';
                    const detailText = details.length > 40 ? details.slice(0, 40) + '...' : details;
                    lines.push(`    rect rgb(255, 245, 224)`);
                    lines.push(`        Note over Orchestrator: 🔀 ${step.action}<br/>${detailText}`);
                    lines.push(`    end`);
                } else {
                    // Standardowy krok
                    const arrow = step.status === 'ok' ? '->>' : '--x';
                    const details = step.details || '';
                    const detailText = details.length > 40 ? details.slice(0, 40) + '...' : details;
                    const message = detailText ? `${step.action}: ${detailText}` : step.action;
                    
                    if (step.component !== lastComponent) {
                        lines.push(`    ${lastComponent}${arrow}${step.component}: ${message}`);
                        lastComponent = step.component;
                    } else {
                        lines.push(`    Note right of ${step.component}: ${message}`);
                    }
                }
            }
            
            // Zwrot do użytkownika
            if (flowData.status === 'COMPLETED') {
                lines.push(`    ${lastComponent}->>User: ✅ Task completed`);
            } else if (flowData.status === 'FAILED') {
                lines.push(`    ${lastComponent}--xUser: ❌ Task failed`);
            } else if (flowData.status === 'PROCESSING') {
                lines.push(`    Note over ${lastComponent}: ⏳ Processing...`);
            }
            
            return lines.join('\n');
        },

        /**
         * Renderuje diagram Mermaid i dodaje interaktywność
         */
        async renderDiagram() {
            if (!this.currentFlowData) return;
            
            const container = document.getElementById('mermaidSvgContainer');
            
            // Wygeneruj kod Mermaid
            const mermaidCode = this.generateMermaidDiagram(this.currentFlowData);
            console.log('📝 Generated Mermaid code:', mermaidCode);
            
            // Wyczyść kontener
            container.innerHTML = '';
            
            try {
                // Renderuj diagram
                const { svg, bindFunctions } = await mermaid.render('mermaidDiagram', mermaidCode);
                container.innerHTML = svg;
                
                // Hydrate - dodaj interaktywność
                this.hydrateDiagram(container);
                
                // Inicjalizuj svg-pan-zoom
                this.initPanZoom();
                
                console.log('✅ Diagram rendered successfully');
            } catch (error) {
                console.error('❌ Error rendering Mermaid diagram:', error);
                container.innerHTML = `
                    <div style="padding: 2rem; text-align: center; color: #f44336;">
                        <p>Błąd renderowania diagramu</p>
                        <pre style="text-align: left; font-size: 0.8rem; color: #666; background: #f5f5f5; padding: 1rem; border-radius: 6px; overflow-x: auto;">${mermaidCode}</pre>
                    </div>
                `;
            }
        },

        /**
         * Dodaje event listenery do elementów SVG (hydratacja)
         */
        hydrateDiagram(container) {
            const svg = container.querySelector('svg');
            if (!svg) return;
            
            // Znajdź wszystkie klikalne elementy
            const actors = svg.querySelectorAll('.actor');
            const messages = svg.querySelectorAll('.messageLine0, .messageLine1');
            const notes = svg.querySelectorAll('.note');
            
            // Dodaj handlery kliknięć
            const addClickHandler = (elements, stepIndex) => {
                elements.forEach((element, idx) => {
                    element.style.cursor = 'pointer';
                    element.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const step = this.currentFlowData.steps[stepIndex || idx];
                        if (step) {
                            this.selectedStep = step;
                            console.log('🎯 Selected step:', step);
                        }
                    });
                    
                    // Dodaj hover effect
                    element.addEventListener('mouseenter', () => {
                        element.style.opacity = '0.7';
                    });
                    element.addEventListener('mouseleave', () => {
                        element.style.opacity = '1';
                    });
                });
            };
            
            addClickHandler(messages);
            addClickHandler(notes);
            
            // Aktorzy - pokaż podstawowe info
            actors.forEach((actor) => {
                actor.style.cursor = 'pointer';
                actor.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const actorName = actor.querySelector('text')?.textContent || 'Unknown';
                    this.selectedStep = {
                        component: actorName,
                        action: 'Actor info',
                        details: `Uczestnik: ${actorName}`,
                        timestamp: new Date().toISOString()
                    };
                });
            });
        },

        /**
         * Inicjalizuje svg-pan-zoom
         */
        initPanZoom() {
            // Zniszcz poprzednią instancję jeśli istnieje
            if (panZoomInstance) {
                panZoomInstance.destroy();
                panZoomInstance = null;
            }
            
            const container = document.getElementById('mermaidSvgContainer');
            const svg = container.querySelector('svg');
            
            if (!svg) return;
            
            try {
                panZoomInstance = svgPanZoom(svg, {
                    zoomEnabled: true,
                    controlIconsEnabled: false,
                    fit: true,
                    center: true,
                    minZoom: 0.1,
                    maxZoom: 10,
                    zoomScaleSensitivity: 0.3
                });
                
                console.log('✅ Pan-Zoom initialized');
            } catch (error) {
                console.error('❌ Error initializing pan-zoom:', error);
            }
        },

        /**
         * Kontrolki zoom
         */
        zoomIn() {
            if (panZoomInstance) {
                panZoomInstance.zoomIn();
            }
        },

        zoomOut() {
            if (panZoomInstance) {
                panZoomInstance.zoomOut();
            }
        },

        resetZoom() {
            if (panZoomInstance) {
                panZoomInstance.reset();
            }
        }
    };
}

// Eksportuj dla Alpine.js
window.inspectorApp = inspectorApp;
