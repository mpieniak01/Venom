/**
 * Unit tests for theme_config.js module
 * 
 * Tests można uruchomić w środowisku Node.js z JSDOM lub w przeglądarce
 * zgodnie z wytycznymi projektu (punkt 3: "Testy jednostkowe / logiczne")
 */

// Mock środowisko DOM dla testów Node.js
if (typeof window === 'undefined') {
    const { JSDOM } = require('jsdom');
    const dom = new JSDOM('<!DOCTYPE html><html><head></head><body></body></html>');
    global.window = dom.window;
    global.document = dom.window.document;
    global.getComputedStyle = dom.window.getComputedStyle;
}

// Import modułu do testowania
// W środowisku Node.js może wymagać transpilacji lub użycia flag --experimental-modules
// W przeglądarce załaduj jako ES6 module

describe('theme_config.js', () => {
    
    describe('hexToRgba function', () => {
        // Testy dla poprawnych wartości
        test('converts valid hex color to rgba', () => {
            const result = hexToRgba('#00ff9d', 0.5);
            expect(result).toBe('rgba(0, 255, 157, 0.5)');
        });
        
        test('handles full opacity', () => {
            const result = hexToRgba('#8b5cf6', 1);
            expect(result).toBe('rgba(139, 92, 246, 1)');
        });
        
        test('handles zero opacity', () => {
            const result = hexToRgba('#00b8ff', 0);
            expect(result).toBe('rgba(0, 184, 255, 0)');
        });
        
        test('handles lowercase hex', () => {
            const result = hexToRgba('#abcdef', 0.8);
            expect(result).toBe('rgba(171, 205, 239, 0.8)');
        });
        
        test('handles uppercase hex', () => {
            const result = hexToRgba('#ABCDEF', 0.3);
            expect(result).toBe('rgba(171, 205, 239, 0.3)');
        });
        
        // Testy dla niepoprawnych formatów - powinny zwrócić fallback
        test('returns fallback for hex without hash', () => {
            const result = hexToRgba('00ff9d', 0.5);
            expect(result).toBe('rgba(0, 0, 0, 0.5)');
        });
        
        test('returns fallback for short hex', () => {
            const result = hexToRgba('#fff', 0.5);
            expect(result).toBe('rgba(0, 0, 0, 0.5)');
        });
        
        test('returns fallback for long hex', () => {
            const result = hexToRgba('#00ff9daa', 0.5);
            expect(result).toBe('rgba(0, 0, 0, 0.5)');
        });
        
        test('returns fallback for non-hex characters', () => {
            const result = hexToRgba('#gghhii', 0.5);
            expect(result).toBe('rgba(0, 0, 0, 0.5)');
        });
        
        test('returns fallback for empty string', () => {
            const result = hexToRgba('', 0.5);
            expect(result).toBe('rgba(0, 0, 0, 0.5)');
        });
        
        test('returns fallback for null', () => {
            const result = hexToRgba(null, 0.5);
            expect(result).toBe('rgba(0, 0, 0, 0.5)');
        });
        
        test('returns fallback for undefined', () => {
            const result = hexToRgba(undefined, 0.5);
            expect(result).toBe('rgba(0, 0, 0, 0.5)');
        });
    });
    
    describe('getCSSVariable function', () => {
        beforeEach(() => {
            // Setup CSS variables dla testów
            document.documentElement.style.setProperty('--test-color', '#00ff9d');
            document.documentElement.style.setProperty('--test-font', 'JetBrains Mono');
            document.documentElement.style.setProperty('--test-spacing', '16px');
        });
        
        afterEach(() => {
            // Cleanup
            document.documentElement.style.removeProperty('--test-color');
            document.documentElement.style.removeProperty('--test-font');
            document.documentElement.style.removeProperty('--test-spacing');
        });
        
        test('retrieves CSS variable with -- prefix', () => {
            const result = getCSSVariable('--test-color');
            expect(result).toBe('#00ff9d');
        });
        
        test('retrieves CSS variable without -- prefix', () => {
            const result = getCSSVariable('test-color');
            expect(result).toBe('#00ff9d');
        });
        
        test('trims whitespace from value', () => {
            document.documentElement.style.setProperty('--test-whitespace', '  value  ');
            const result = getCSSVariable('test-whitespace');
            expect(result).toBe('value');
            document.documentElement.style.removeProperty('--test-whitespace');
        });
        
        test('returns empty string for non-existent variable', () => {
            const result = getCSSVariable('--non-existent');
            expect(result).toBe('');
        });
    });
    
    describe('THEME object', () => {
        test('THEME object is exported and defined', () => {
            expect(typeof THEME).toBe('object');
            expect(THEME).not.toBeNull();
        });
        
        test('THEME has required color properties', () => {
            expect(THEME).toHaveProperty('primary');
            expect(THEME).toHaveProperty('primaryColor');
            expect(THEME).toHaveProperty('secondary');
            expect(THEME).toHaveProperty('bgDark');
        });
        
        test('THEME has font properties', () => {
            expect(THEME).toHaveProperty('fontUI');
            expect(THEME).toHaveProperty('fontTech');
        });
        
        test('THEME has chartDefaults configuration', () => {
            expect(THEME).toHaveProperty('chartDefaults');
            expect(THEME.chartDefaults).toHaveProperty('color');
            expect(THEME.chartDefaults).toHaveProperty('font');
        });
        
        test('THEME has mermaidConfig configuration', () => {
            expect(THEME).toHaveProperty('mermaidConfig');
            expect(THEME.mermaidConfig).toHaveProperty('theme');
            expect(THEME.mermaidConfig).toHaveProperty('themeVariables');
        });
        
        test('THEME has cytoscapeStyles configuration', () => {
            expect(THEME).toHaveProperty('cytoscapeStyles');
            expect(THEME.cytoscapeStyles).toHaveProperty('nodeBase');
            expect(THEME.cytoscapeStyles).toHaveProperty('edgeBase');
        });
    });
    
    describe('Helper functions', () => {
        test('applyChartDefaults is exported', () => {
            expect(typeof applyChartDefaults).toBe('function');
        });
        
        test('getMermaidConfig is exported', () => {
            expect(typeof getMermaidConfig).toBe('function');
        });
        
        test('getMermaidConfig returns valid config', () => {
            const config = getMermaidConfig();
            expect(config).toHaveProperty('theme');
            expect(config).toHaveProperty('themeVariables');
            expect(config.theme).toBe('base');
        });
        
        test('getCytoscapeStyles is exported', () => {
            expect(typeof getCytoscapeStyles).toBe('function');
        });
        
        test('getCytoscapeStyles returns array of style objects', () => {
            const styles = getCytoscapeStyles();
            expect(Array.isArray(styles)).toBe(true);
            expect(styles.length).toBeGreaterThan(0);
            expect(styles[0]).toHaveProperty('selector');
            expect(styles[0]).toHaveProperty('style');
        });
    });
    
    describe('Integration tests', () => {
        test('hexToRgba integrates correctly with theme colors', () => {
            // Symuluj CSS variable
            document.documentElement.style.setProperty('--primary-green', '#00ff9d');
            
            const primaryGreen = getCSSVariable('--primary-green');
            const rgba = hexToRgba(primaryGreen, 0.1);
            
            expect(rgba).toBe('rgba(0, 255, 157, 0.1)');
            
            document.documentElement.style.removeProperty('--primary-green');
        });
        
        test('theme config handles missing CSS variables gracefully', () => {
            // Jeśli CSS variable nie istnieje, funkcja powinna działać bez crash
            const nonExistent = getCSSVariable('--this-does-not-exist');
            expect(nonExistent).toBe('');
            
            // hexToRgba z pustym stringiem powinno zwrócić fallback
            const rgba = hexToRgba(nonExistent, 0.5);
            expect(rgba).toBe('rgba(0, 0, 0, 0.5)');
        });
    });
});

// Export dla użycia w innych testach
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        // Funkcje testowe mogą być eksportowane jeśli potrzebne
    };
}

/**
 * Instrukcje uruchamiania testów:
 * 
 * 1. W środowisku Node.js z Jest:
 *    npm install --save-dev jest jsdom
 *    npx jest theme_config.test.js
 * 
 * 2. W przeglądarce z test runner (np. Jasmine, Mocha):
 *    Załaduj jako moduł i uruchom w konsoli przeglądarki
 * 
 * 3. Zgodnie z wytycznymi projektu (pytest dla Python):
 *    Te testy JavaScript są analogiczne do testów jednostkowych pytest
 *    i służą weryfikacji logiki modułu bez ciężkich zależności
 */
