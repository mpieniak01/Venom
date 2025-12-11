# JavaScript Module Tests

## Overview

Testy jednostkowe dla modułów JavaScript zgodnie z wytycznymi projektu (punkt 3: "Testy jednostkowe / logiczne").

## Test Files

- `theme_config.test.js` - Testy dla modułu theme_config.js

## Running Tests

### Option 1: Jest (Recommended)

```bash
# Install dependencies
npm install --save-dev jest jsdom @types/jest

# Add to package.json scripts:
# "test:js": "jest web/static/js/modules/*.test.js"

# Run tests
npm run test:js
```

### Option 2: Browser Console

1. Open `web/templates/base.html` in browser
2. Load test file as module:
   ```javascript
   import('./static/js/modules/theme_config.test.js');
   ```
3. Tests will run automatically if using a test framework

### Option 3: Node.js Direct

```bash
# Requires ES6 module support
node --experimental-modules web/static/js/modules/theme_config.test.js
```

## Test Structure

Testy są zorganizowane według wzorca AAA (Arrange-Act-Assert):

- **Unit tests** - Testują pojedyncze funkcje w izolacji
- **Integration tests** - Testują współpracę funkcji
- **Edge cases** - Testują obsługę błędnych danych

## Coverage

Testy obejmują:

- ✅ `hexToRgba()` - konwersja hex → rgba z walidacją
- ✅ `getCSSVariable()` - pobieranie zmiennych CSS
- ✅ `THEME` object - struktura i properties
- ✅ Helper functions - `applyChartDefaults()`, `getMermaidConfig()`, `getCytoscapeStyles()`
- ✅ Error handling - obsługa niepoprawnych danych
- ✅ Integration - współpraca funkcji

## Guidelines

Zgodnie z zasadami projektu:

1. **Testy jednostkowe** - szybkie i deterministyczne (bez GPU/modeli)
2. **Mocki** - używane gdzie sensowne (np. DOM, CSS variables)
3. **Bez ciężkich zależności** - testy nie ładują Chart.js, Mermaid, Cytoscape

## Adding New Tests

Przy dodawaniu nowych funkcji do `theme_config.js`:

1. Dodaj testy w odpowiednim `describe()` bloku
2. Użyj `test()` dla pojedynczych przypadków
3. Dodaj `beforeEach()`/`afterEach()` dla setup/cleanup
4. Testuj happy path + edge cases
5. Dokumentuj expected behavior w komentarzach

## CI/CD Integration

Testy mogą być dodane do pipeline CI:

```yaml
# .github/workflows/test.yml
- name: Run JS tests
  run: npm run test:js
```

## Reference

- Jest documentation: https://jestjs.io/
- JSDOM: https://github.com/jsdom/jsdom
- Project guidelines: `docs/` (punkt 3: Testy)
