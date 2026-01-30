# Plan Wdrożenia: Import Narzędzi MCP (MVP) - nr 102

**Data:** 2026-01-30
**Autor:** Antigravity (Agent)
**Status:** Zakończone

---

## Cel
Wdrożenie mechanizmu importowania i uruchamiania narzędzi MCP (Model Context Protocol) z repozytoriów Git, zgodnie z analizą zawartą w [nr_101](nr_101_analiza_importu_mcp.md).

## Fazy Realizacji

### Faza 1: Fundamenty i Zależności
1.  **[x] Dodać `mcp` do `requirements.txt`**: Zainstalować oficjalne SDK.
2.  **[x] Stworzyć strukturę katalogów**:
    *   `venom_core/skills/mcp/` (moduł zarządzający)
    *   `venom_core/skills/mcp/_repos/` (ukryty katalog na klony Git)

### Faza 2: Generator Proxy (Most Pythona)
1.  **[x] Stworzyć `McpProxyGenerator`**:
    *   Klasa, która przyjmuje ścieżkę do repozytorium i nazwę narzędzia.
    *   Generuje plik `.py` w `venom_core/skills/custom/`.
    *   Wygenerowany kod musi:
        *   Ustawiać ścieżkę do interpretera `python` z venv danego repozytorium.
        *   Uruchamiać proces serwera (np. `python server.py`).
        *   Łączyć się przez stdio używając `mcp-sdk`.

### Faza 3: Skille Zarządzające
1.  **[x] Stworzyć `McpManagerSkill`**:
    *   Funkcja `import_mcp_tool(repo_url, tool_name)`:
        *   `Git clone` do `_repos`.
        *   `venv create` + `pip install`.
        *   `McpProxyGenerator.generate(...)`.
    *   Funkcja `list_imported_tools()`:
        *   Skanuje katalog `custom/` w poszukiwaniu wrapperów MCP.

### Faza 4: Integracja i Testy (POC)
1.  **[x] Test E2E**:
    *   Zaimportowanie przykładowego repozytorium (np. `sqlite-mcp`).
    *   Uruchomienie wygenerowanego skilla.
    *   Wykonanie operacji na bazie danych przez Agenta.

## Decyzje Techniczne (zgodne z nr 101)
*   **Runtime**: Python `virtualenv` (Lite mode).
*   **Komunikacja**: Stdio (Standard Input/Output).
*   **Bezpieczeństwo**: Ostrzeżenie przed importem (User confirmation required).

---
**Status**: Zakończone
