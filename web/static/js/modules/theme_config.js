// Venom OS - Theme Configuration Module
// Bridge between CSS variables and JavaScript libraries
// Extracts values from modules/variables.css and provides configuration for Chart.js, Mermaid, Cytoscape

/**
 * Pobiera wartość CSS variable z :root
 * @param {string} varName - Nazwa zmiennej CSS (z lub bez --)
 * @returns {string} Wartość zmiennej
 */
function getCSSVariable(varName) {
    const name = varName.startsWith('--') ? varName : `--${varName}`;
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * Konwertuje hex color na rgba z zadaną przezroczystością
 * @param {string} hex - Kolor hex w formacie '#RRGGBB' (np. #00ff9d)
 * @param {number} alpha - Przezroczystość 0-1
 * @returns {string} Kolor rgba
 * @throws {Error} Jeśli format hex jest niepoprawny
 */
function hexToRgba(hex, alpha) {
    // Walidacja formatu hex
    if (typeof hex !== 'string' || !hex.startsWith('#') || hex.length !== 7) {
        console.error(`Invalid hex color format: ${hex}. Expected format: #RRGGBB`);
        return `rgba(0, 0, 0, ${alpha})`; // Fallback to black
    }
    
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    
    // Sprawdź czy parsing się udał
    if (isNaN(r) || isNaN(g) || isNaN(b)) {
        console.error(`Invalid hex color value: ${hex}. Could not parse RGB components.`);
        return `rgba(0, 0, 0, ${alpha})`; // Fallback to black
    }
    
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Główna konfiguracja motywu - eksportowana dla bibliotek JS
 */
export const THEME = {
    // Podstawowe kolory z variables.css
    bgDark: getCSSVariable('bg-dark'),
    bgPanel: getCSSVariable('bg-panel'),
    bgMedium: getCSSVariable('bg-medium'),
    bgLight: getCSSVariable('bg-light'),
    
    // Akcenty - Dual accent approach (Purple UI + Neon Green Brand)
    primary: getCSSVariable('primary-green'),        // #00ff9d - Neon green brand
    primaryColor: getCSSVariable('primary-color'),   // #8b5cf6 - Purple UI
    primaryHover: getCSSVariable('primary-hover'),   // #7c3aed - Purple hover
    secondary: getCSSVariable('secondary'),          // #00b8ff - Cyan
    secondaryColor: getCSSVariable('secondary-color'), // #06b6d4 - Cyan alt
    
    // Status colors
    success: getCSSVariable('success-color'),
    error: getCSSVariable('error-color'),
    warning: getCSSVariable('warning-color'),
    
    // Kolory tekstu
    textMain: getCSSVariable('text-main'),
    textPrimary: getCSSVariable('text-primary'),
    textSecondary: getCSSVariable('text-secondary'),
    textMuted: getCSSVariable('text-muted'),
    
    // Borders
    borderColor: getCSSVariable('border-color'),
    
    // Fonty
    fontUI: getCSSVariable('font-ui'),
    fontTech: getCSSVariable('font-tech'),
    
    // Konfiguracja dla Chart.js
    chartDefaults: {
        color: getCSSVariable('text-secondary'),           // #94a3b8
        font: {
            family: getCSSVariable('font-tech'),            // JetBrains Mono
            size: 12
        },
        plugins: {
            legend: {
                labels: {
                    color: getCSSVariable('text-primary'),  // #f1f5f9
                    font: {
                        family: getCSSVariable('font-tech'),
                        size: 12
                    }
                }
            },
            tooltip: {
                backgroundColor: getCSSVariable('bg-medium'), // #1e293b
                titleColor: getCSSVariable('text-primary'),
                bodyColor: getCSSVariable('text-secondary'),
                borderColor: getCSSVariable('border-color'),
                borderWidth: 1,
                titleFont: {
                    family: getCSSVariable('font-tech')
                },
                bodyFont: {
                    family: getCSSVariable('font-tech')
                }
            }
        },
        scales: {
            x: {
                ticks: {
                    color: getCSSVariable('text-secondary'),
                    font: {
                        family: getCSSVariable('font-tech')
                    }
                },
                grid: {
                    color: 'rgba(255, 255, 255, 0.1)',
                    borderColor: getCSSVariable('border-color')
                }
            },
            y: {
                ticks: {
                    color: getCSSVariable('text-secondary'),
                    font: {
                        family: getCSSVariable('font-tech')
                    }
                },
                grid: {
                    color: 'rgba(255, 255, 255, 0.1)',
                    borderColor: getCSSVariable('border-color')
                }
            }
        }
    },
    
    // Konfiguracja dla Mermaid.js
    mermaidConfig: {
        theme: 'base',
        themeVariables: {
            // Tło i główne kolory
            primaryColor: getCSSVariable('bg-panel'),        // Przezroczyste panele
            primaryTextColor: getCSSVariable('text-main'),    // #ffffff
            primaryBorderColor: getCSSVariable('primary-green'), // #00ff9d - Neon green
            
            // Linie i połączenia
            lineColor: getCSSVariable('secondary'),           // #00b8ff - Cyan
            
            // Drugorzędne elementy
            secondaryColor: getCSSVariable('bg-medium'),      // #1e293b
            tertiaryColor: getCSSVariable('primary-color'),   // #8b5cf6 - Purple
            
            // Tekst
            textColor: getCSSVariable('text-primary'),
            fontSize: '14px',
            fontFamily: getCSSVariable('font-tech'),
            
            // Tło i obramowania
            mainBkg: getCSSVariable('bg-dark'),               // #030407
            secondBkg: getCSSVariable('bg-medium'),
            tertiaryBkg: getCSSVariable('bg-light'),
            
            // Sequence Diagram specifics
            actorBkg: getCSSVariable('bg-medium'),
            actorBorder: getCSSVariable('primary-color'),     // Purple border
            actorTextColor: getCSSVariable('text-primary'),
            actorLineColor: getCSSVariable('secondary'),
            signalColor: getCSSVariable('text-secondary'),
            signalTextColor: getCSSVariable('text-primary'),
            labelBoxBkgColor: getCSSVariable('bg-panel'),
            labelBoxBorderColor: getCSSVariable('border-color'),
            labelTextColor: getCSSVariable('text-primary'),
            loopTextColor: getCSSVariable('text-primary'),
            noteBorderColor: getCSSVariable('primary-green'), // Neon green notes
            noteBkgColor: hexToRgba(getCSSVariable('primary-green'), 0.1), // Subtle green background
            noteTextColor: getCSSVariable('text-primary'),
            
            // Activation boxes
            activationBorderColor: getCSSVariable('primary-color'),
            activationBkgColor: hexToRgba(getCSSVariable('primary-color'), 0.15), // Subtle purple
            
            // Flowchart
            nodeBorder: getCSSVariable('primary-color'),
            clusterBkg: getCSSVariable('bg-panel'),
            clusterBorder: getCSSVariable('border-color'),
            defaultLinkColor: getCSSVariable('secondary'),
            
            // Git graph
            git0: getCSSVariable('primary-green'),
            git1: getCSSVariable('primary-color'),
            git2: getCSSVariable('secondary'),
            git3: getCSSVariable('warning-color'),
            git4: getCSSVariable('error-color'),
            git5: getCSSVariable('success-color'),
            git6: getCSSVariable('text-secondary'),
            git7: getCSSVariable('text-muted')
        },
        // Dodatkowa konfiguracja
        darkMode: true,
        securityLevel: 'strict',
        startOnLoad: false,
        logLevel: 'error'
    },
    
    // Konfiguracja dla Cytoscape.js (The Brain)
    cytoscapeStyles: {
        // Styl węzłów - bazowy (hologram effect)
        nodeBase: {
            'label': 'data(label)',
            'text-valign': 'center',
            'text-halign': 'center',
            'font-size': '12px',
            'font-family': getCSSVariable('font-tech'),
            'font-weight': 'bold',
            'text-outline-color': getCSSVariable('bg-dark'),
            'text-outline-width': 2,
            'color': getCSSVariable('text-primary'),
            'width': 60,
            'height': 60,
            'border-width': 3,
            'border-color': getCSSVariable('secondary'),      // Neon blue border
            'background-color': getCSSVariable('bg-panel')    // Przezroczyste tło (rgba from CSS)
        },
        
        // Węzeł aktywny - Neon green highlight
        // Note: Cytoscape doesn't support box-shadow, using border and opacity instead
        nodeActive: {
            'border-width': 5,
            'border-color': getCSSVariable('primary-green'),  // #00ff9d
            'border-opacity': 1,
            'background-opacity': 0.9,
            'z-index': 9999
        },
        
        // Krawędzie - cienkie, półprzezroczyste
        edgeBase: {
            'width': 2,
            'line-color': 'rgba(255, 255, 255, 0.2)',
            'target-arrow-color': 'rgba(255, 255, 255, 0.2)',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'arrow-scale': 1.2,
            'opacity': 0.4
        },
        
        // Krawędź podświetlona
        edgeHighlighted: {
            'width': 4,
            'line-color': getCSSVariable('primary-green'),
            'target-arrow-color': getCSSVariable('primary-green'),
            'opacity': 1,
            'z-index': 9999
        }
    }
};

// Helper: Apply Chart.js defaults
export function applyChartDefaults() {
    if (typeof Chart !== 'undefined') {
        Chart.defaults.color = THEME.chartDefaults.color;
        Chart.defaults.font.family = THEME.chartDefaults.font.family;
        Chart.defaults.font.size = THEME.chartDefaults.font.size;
        
        // Log only in dev mode
        if (window.location.hostname === 'localhost') {
            console.log('✅ Chart.js defaults applied from theme');
        }
    }
}

// Helper: Get Mermaid config
export function getMermaidConfig() {
    return THEME.mermaidConfig;
}

// Helper: Get Cytoscape style array
export function getCytoscapeStyles() {
    return [
        {
            selector: 'node',
            style: THEME.cytoscapeStyles.nodeBase
        },
        {
            selector: 'node.highlighted',
            style: THEME.cytoscapeStyles.nodeActive
        },
        {
            selector: 'edge',
            style: THEME.cytoscapeStyles.edgeBase
        },
        {
            selector: 'edge.highlighted',
            style: THEME.cytoscapeStyles.edgeHighlighted
        }
    ];
}

// Auto-log konfiguracji dla debugowania (tylko w dev mode)
if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
    console.log('🎨 Venom Theme Config loaded:', {
        primary: THEME.primary,
        primaryColor: THEME.primaryColor,
        secondary: THEME.secondary,
        fontTech: THEME.fontTech
    });
}
