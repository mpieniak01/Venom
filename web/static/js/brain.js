// brain.js - Logika grafu wiedzy z Cytoscape.js

let cy = null; // Instancja Cytoscape
let graphData = null; // Dane grafu

// Alpine.js component dla kontrolek
function brainControls() {
    return {
        stats: {
            nodes: 0,
            edges: 0
        },
        status: 'Ładowanie...',
        filters: {
            agents: true,
            files: true,
            memories: true
        },
        
        applyFilters() {
            if (!cy) return;
            
            // Pokaż wszystkie elementy
            cy.elements().style('display', 'element');
            
            // Ukryj te, które nie są zaznaczone
            if (!this.filters.agents) {
                cy.nodes('[type="agent"]').style('display', 'none');
            }
            if (!this.filters.files) {
                cy.nodes('[type="file"]').style('display', 'none');
            }
            if (!this.filters.memories) {
                cy.nodes('[type="memory"]').style('display', 'none');
            }
            
            // Ukryj krawędzie, których źródło lub cel jest ukryte
            cy.edges().forEach(edge => {
                const source = edge.source();
                const target = edge.target();
                if (source.style('display') === 'none' || target.style('display') === 'none') {
                    edge.style('display', 'none');
                }
            });
        }
    };
}

// Funkcja inicjalizująca graf
async function initGraph() {
    showLoading();
    
    try {
        // Pobierz dane grafu z API
        const response = await fetch('/api/v1/knowledge/graph');
        const data = await response.json();
        
        if (data.status !== 'success') {
            throw new Error('Błąd podczas ładowania danych grafu');
        }
        
        graphData = data;
        
        // Aktualizuj statystyki w Alpine
        updateStats(data.stats);
        
        // Inicjalizuj Cytoscape
        cy = cytoscape({
            container: document.getElementById('cy'),
            
            elements: data.elements,
            
            style: [
                // Styl węzłów - bazowy
                {
                    selector: 'node',
                    style: {
                        'label': 'data(label)',
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'font-size': '12px',
                        'font-weight': 'bold',
                        'text-outline-color': '#0f172a',
                        'text-outline-width': 2,
                        'color': '#e2e8f0',
                        'width': 60,
                        'height': 60,
                        'border-width': 3,
                        'border-color': '#64748b',
                        'background-color': '#1e293b'
                    }
                },
                
                // Agenci - diament, fioletowy
                {
                    selector: 'node[type="agent"]',
                    style: {
                        'shape': 'diamond',
                        'background-color': '#a855f7',
                        'border-color': '#c084fc',
                        'width': 80,
                        'height': 80
                    }
                },
                
                // Pliki - kwadrat, niebieski
                {
                    selector: 'node[type="file"]',
                    style: {
                        'shape': 'square',
                        'background-color': '#3b82f6',
                        'border-color': '#60a5fa',
                        'width': 60,
                        'height': 60
                    }
                },
                
                // Lekcje/Pamięć - koło, zielony
                {
                    selector: 'node[type="memory"]',
                    style: {
                        'shape': 'ellipse',
                        'background-color': '#10b981',
                        'border-color': '#34d399',
                        'width': 70,
                        'height': 70
                    }
                },
                
                // Styl krawędzi
                {
                    selector: 'edge',
                    style: {
                        'width': 2,
                        'line-color': '#475569',
                        'target-arrow-color': '#475569',
                        'target-arrow-shape': 'triangle',
                        'curve-style': 'bezier',
                        'arrow-scale': 1.2,
                        'opacity': 0.6
                    }
                },
                
                // Krawędzie różnych typów
                {
                    selector: 'edge[type="DELEGATES"]',
                    style: {
                        'line-color': '#a855f7',
                        'target-arrow-color': '#a855f7'
                    }
                },
                {
                    selector: 'edge[type="EDITS"]',
                    style: {
                        'line-color': '#3b82f6',
                        'target-arrow-color': '#3b82f6'
                    }
                },
                {
                    selector: 'edge[type="LEARNS"]',
                    style: {
                        'line-color': '#10b981',
                        'target-arrow-color': '#10b981'
                    }
                },
                {
                    selector: 'edge[type="IMPORTS"]',
                    style: {
                        'line-color': '#f59e0b',
                        'target-arrow-color': '#f59e0b'
                    }
                },
                
                // Węzeł wybrany (highlighted)
                {
                    selector: 'node.highlighted',
                    style: {
                        'border-width': 5,
                        'border-color': '#fbbf24',
                        'z-index': 9999
                    }
                },
                
                // Sąsiedzi podświetlonego węzła
                {
                    selector: 'node.neighbor',
                    style: {
                        'opacity': 1,
                        'border-color': '#fbbf24'
                    }
                },
                
                // Krawędzie podświetlone
                {
                    selector: 'edge.highlighted',
                    style: {
                        'width': 4,
                        'opacity': 1,
                        'z-index': 9999
                    }
                },
                
                // Przygaszone elementy
                {
                    selector: 'node.faded',
                    style: {
                        'opacity': 0.3
                    }
                },
                {
                    selector: 'edge.faded',
                    style: {
                        'opacity': 0.1
                    }
                }
            ],
            
            layout: {
                name: 'cose', // Compound Spring Embedder - fizyka!
                animate: true,
                animationDuration: 1000,
                animationEasing: 'ease-out',
                nodeRepulsion: 8000,
                idealEdgeLength: 100,
                edgeElasticity: 100,
                nestingFactor: 1.2,
                gravity: 1,
                numIter: 1000,
                initialTemp: 200,
                coolingFactor: 0.95,
                minTemp: 1.0
            },
            
            // Interakcje
            minZoom: 0.3,
            maxZoom: 3,
            wheelSensitivity: 0.2
        });
        
        // Event handlers
        setupEventHandlers();
        
        updateStatus('Gotowy');
        hideLoading();
        
    } catch (error) {
        console.error('Błąd podczas inicjalizacji grafu:', error);
        updateStatus('Błąd');
        hideLoading();
        alert('Nie udało się załadować grafu wiedzy. Sprawdź konsolę.');
    }
}

// Konfiguracja event handlers dla interakcji
function setupEventHandlers() {
    // Kliknięcie w węzeł - pokaż szczegóły
    cy.on('tap', 'node', function(evt) {
        const node = evt.target;
        showNodeDetails(node);
        highlightNode(node);
    });
    
    // Kliknięcie w tło - schowaj szczegóły i usuń podświetlenia
    cy.on('tap', function(evt) {
        if (evt.target === cy) {
            hideNodeDetails();
            clearHighlights();
        }
    });
    
    // Najazd na węzeł - podświetl
    cy.on('mouseover', 'node', function(evt) {
        const node = evt.target;
        if (!node.hasClass('highlighted')) {
            highlightNode(node, true);
        }
    });
    
    // Zjazd z węzła - usuń podświetlenie (jeśli nie jest wybrany)
    cy.on('mouseout', 'node', function(evt) {
        const node = evt.target;
        if (!node.hasClass('highlighted')) {
            clearHighlights();
        }
    });
}

// Podświetl węzeł i jego sąsiadów
function highlightNode(node, isHover = false) {
    // Usuń poprzednie podświetlenia
    if (!isHover) {
        clearHighlights();
    }
    
    // Przygaś wszystkie elementy
    cy.elements().addClass('faded');
    
    // Podświetl wybrany węzeł
    node.removeClass('faded').addClass(isHover ? 'neighbor' : 'highlighted');
    
    // Podświetl sąsiadów (połączone węzły)
    const neighbors = node.neighborhood();
    neighbors.nodes().removeClass('faded').addClass('neighbor');
    neighbors.edges().removeClass('faded').addClass('highlighted');
}

// Usuń wszystkie podświetlenia
function clearHighlights() {
    cy.elements().removeClass('highlighted neighbor faded');
}

// Pokaż szczegóły węzła w panelu
function showNodeDetails(node) {
    const data = node.data();
    const panel = document.getElementById('nodeDetails');
    const title = document.getElementById('nodeDetailsLabel');
    const icon = document.getElementById('nodeDetailsIcon');
    const content = document.getElementById('nodeDetailsContent');
    
    // Ikona zależna od typu
    const icons = {
        'agent': '🔷',
        'file': '📄',
        'memory': '💡'
    };
    icon.textContent = icons[data.type] || '📦';
    title.textContent = data.label;
    
    // Buduj zawartość
    let html = '';
    
    html += `<div class="detail-row">
        <div class="detail-label">Typ</div>
        <div class="detail-value"><code>${data.type}</code></div>
    </div>`;
    
    html += `<div class="detail-row">
        <div class="detail-label">ID</div>
        <div class="detail-value"><code>${data.id}</code></div>
    </div>`;
    
    // Dodatkowe właściwości
    if (data.properties) {
        for (const [key, value] of Object.entries(data.properties)) {
            if (key !== 'id' && key !== 'label' && key !== 'type') {
                html += `<div class="detail-row">
                    <div class="detail-label">${key}</div>
                    <div class="detail-value">${JSON.stringify(value)}</div>
                </div>`;
            }
        }
    }
    
    // Pokaż połączenia
    const edges = node.connectedEdges();
    html += `<div class="detail-row">
        <div class="detail-label">Połączenia</div>
        <div class="detail-value">${edges.length}</div>
    </div>`;
    
    content.innerHTML = html;
    panel.classList.add('visible');
}

// Schowaj panel szczegółów
function hideNodeDetails() {
    const panel = document.getElementById('nodeDetails');
    panel.classList.remove('visible');
    clearHighlights();
}

// Aktualizuj statystyki w Alpine
function updateStats(stats) {
    // Alpine reactive update
    const alpineData = Alpine.$data(document.querySelector('.brain-controls'));
    if (alpineData) {
        alpineData.stats.nodes = stats.nodes || 0;
        alpineData.stats.edges = stats.edges || 0;
    }
}

// Aktualizuj status w Alpine
function updateStatus(status) {
    const alpineData = Alpine.$data(document.querySelector('.brain-controls'));
    if (alpineData) {
        alpineData.status = status;
    }
}

// Pokaż loading overlay
function showLoading() {
    document.getElementById('loadingOverlay').style.display = 'flex';
}

// Schowaj loading overlay
function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

// Inicjalizacja po załadowaniu DOM
document.addEventListener('DOMContentLoaded', function() {
    initGraph();
});
