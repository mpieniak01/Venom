// Logika grafu wiedzy z Cytoscape.js
// Import theme config for unified Deep Space styling
import { THEME, getCytoscapeStyles } from './modules/theme_config.js';

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
            memories: true,
            functions: true,
            classes: true
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
            if (!this.filters.functions) {
                cy.nodes('[type="function"]').style('display', 'none');
            }
            if (!this.filters.classes) {
                cy.nodes('[type="class"]').style('display', 'none');
            }
            
            // Ukryj krawędzie, których źródło lub cel jest ukryte (batchowo, wydajnie)
            const hiddenNodeIds = new Set(
                cy.nodes().filter(n => n.style('display') === 'none').map(n => n.id())
            );
            const edgesToHide = cy.edges().filter(edge => 
                hiddenNodeIds.has(edge.source().id()) || hiddenNodeIds.has(edge.target().id())
            );
            edgesToHide.style('display', 'none');
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
                // Base styles from theme config (hologram effect)
                ...getCytoscapeStyles(),
                
                // Styl węzłów - bazowy (overwrites for data-driven properties)
                {
                    selector: 'node',
                    style: {
                        'label': 'data(label)',
                        'text-valign': 'center',
                        'text-halign': 'center'
                    }
                },
                
                // Agenci - diament, purple (UI accent)
                {
                    selector: 'node[type="agent"]',
                    style: {
                        'shape': 'diamond',
                        'background-color': THEME.primaryColor,      // #8b5cf6 Purple
                        'border-color': THEME.secondary,             // #00b8ff Neon cyan
                        'width': 80,
                        'height': 80
                    }
                },
                
                // Pliki - kwadrat, secondary (cyan)
                {
                    selector: 'node[type="file"]',
                    style: {
                        'shape': 'square',
                        'background-color': THEME.secondary,         // #00b8ff Cyan
                        'border-color': THEME.secondaryColor,        // #06b6d4 Cyan alt
                        'width': 60,
                        'height': 60
                    }
                },
                
                // Lekcje/Pamięć - koło, neon green (brand)
                {
                    selector: 'node[type="memory"]',
                    style: {
                        'shape': 'ellipse',
                        'background-color': THEME.primary,           // #00ff9d Neon green
                        'border-color': THEME.success,               // #10b981 Success green
                        'width': 70,
                        'height': 70
                    }
                },
                
                // Funkcje/Metody - okrąg, warning (pomarańczowy)
                {
                    selector: 'node[type="function"]',
                    style: {
                        'shape': 'round-rectangle',
                        'background-color': THEME.warning,           // #f59e0b Warning orange
                        'border-color': THEME.primaryColor,          // #8b5cf6 Purple border
                        'width': 55,
                        'height': 55
                    }
                },
                
                // Klasy - sześciokąt, różowy/purpurowy
                {
                    selector: 'node[type="class"]',
                    style: {
                        'shape': 'hexagon',
                        'background-color': THEME.primaryHover,      // #7c3aed Purple dark
                        'border-color': THEME.primaryColor,          // #8b5cf6 Purple
                        'width': 65,
                        'height': 65
                    }
                },
                
                // Styl krawędzi - override base z dodatkowymi właściwościami
                {
                    selector: 'edge',
                    style: {
                        'width': 2,
                        'line-color': 'rgba(255, 255, 255, 0.2)',    // Półprzezroczyste
                        'target-arrow-color': 'rgba(255, 255, 255, 0.2)',
                        'target-arrow-shape': 'triangle',
                        'curve-style': 'bezier',
                        'arrow-scale': 1.2,
                        'opacity': 0.4
                    }
                },
                
                // Krawędzie różnych typów - theme colors
                {
                    selector: 'edge[type="DELEGATES"]',
                    style: {
                        'line-color': THEME.primaryColor,            // Purple
                        'target-arrow-color': THEME.primaryColor
                    }
                },
                {
                    selector: 'edge[type="EDITS"]',
                    style: {
                        'line-color': THEME.secondary,               // Cyan
                        'target-arrow-color': THEME.secondary
                    }
                },
                {
                    selector: 'edge[type="LEARNS"]',
                    style: {
                        'line-color': THEME.primary,                 // Neon green
                        'target-arrow-color': THEME.primary
                    }
                },
                {
                    selector: 'edge[type="IMPORTS"]',
                    style: {
                        'line-color': THEME.warning,                 // Orange
                        'target-arrow-color': THEME.warning
                    }
                },
                
                // Węzeł wybrany (highlighted) - Neon green highlight
                // Note: Cytoscape doesn't support box-shadow
                {
                    selector: 'node.highlighted',
                    style: {
                        'border-width': 5,
                        'border-color': THEME.primary,               // #00ff9d Neon green
                        'border-opacity': 1,
                        'background-opacity': 0.9,
                        'z-index': 9999
                    }
                },
                
                // Sąsiedzi podświetlonego węzła
                {
                    selector: 'node.neighbor',
                    style: {
                        'opacity': 1,
                        'border-color': THEME.secondary              // Cyan for neighbors
                    }
                },
                
                // Krawędzie podświetlone - Neon green
                {
                    selector: 'edge.highlighted',
                    style: {
                        'width': 4,
                        'line-color': THEME.primary,
                        'target-arrow-color': THEME.primary,
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
        showError('Nie udało się załadować grafu wiedzy. Sprawdź konsolę.');
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
        'memory': '💡',
        'function': '⚙️',
        'class': '🔶'
    };
    icon.textContent = icons[data.type] || '📦';
    title.textContent = data.label;
    
    // Buduj zawartość
    // Escape HTML characters
    const escapeHtml = (text) => {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };
    
    let html = '';
    
    html += `<div class="detail-row">
        <div class="detail-label">Typ</div>
        <div class="detail-value"><code>${escapeHtml(data.type)}</code></div>
    </div>`;
    
    html += `<div class="detail-row">
        <div class="detail-label">ID</div>
        <div class="detail-value"><code>${escapeHtml(data.id)}</code></div>
    </div>`;
    
    // Dodatkowe właściwości
    if (data.properties) {
        for (const [key, value] of Object.entries(data.properties)) {
            if (key !== 'id' && key !== 'label' && key !== 'type') {
                const safeKey = escapeHtml(key);
                const safeValue = escapeHtml(JSON.stringify(value));
                html += `<div class="detail-row">
                    <div class="detail-label">${safeKey}</div>
                    <div class="detail-value">${safeValue}</div>
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

// Aktualizuj statystyki w Alpine Store
function updateStats(stats) {
    if (window.Alpine && Alpine.store('brain')) {
        Alpine.store('brain').stats.nodes = stats.nodes || 0;
        Alpine.store('brain').stats.edges = stats.edges || 0;
    }
}

// Aktualizuj status w Alpine Store
function updateStatus(status) {
    if (window.Alpine && Alpine.store('brain')) {
        Alpine.store('brain').status = status;
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

// Wyświetl komunikat błędu w sposób nieinwazyjny
function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        background: rgba(239, 68, 68, 0.95);
        color: #fff;
        padding: 16px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        z-index: 3000;
        max-width: 400px;
        font-size: 14px;
        animation: slideIn 0.3s ease-out;
    `;
    errorDiv.textContent = message;
    document.body.appendChild(errorDiv);
    setTimeout(() => {
        errorDiv.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => errorDiv.remove(), 300);
    }, 5000);
}

// Inicjalizacja po załadowaniu DOM
document.addEventListener('DOMContentLoaded', function() {
    initGraph();
});
