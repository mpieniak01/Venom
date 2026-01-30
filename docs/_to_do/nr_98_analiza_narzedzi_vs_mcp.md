# Analiza Zgodności Narzędzi (Tools) ze Standardem MCP

**Data:** 2026-01-30
**Autor:** Antigravity (Agent)
**Status:** Analiza wykonana

---

## 1. Stan Obecny (AS-IS)

Obecny system narzędzi w Venom oparty jest na **Microsoft Semantic Kernel**.

### Struktura Narzędzi
- **Lokalizacja:** `venom_core/execution/skills/` oraz `venom_core/agents/toolmaker.py`.
- **Implementacja:** Klasy Python z metodami dekorowanymi `@kernel_function`.
- **Przykład (`FileSkill`):**
  ```python
  class FileSkill:
      @kernel_function(name="write_file", description="...")
      async def write_file(self, ...): ...
  ```
- **Zarządzanie:** `SkillManager` (`venom_core/execution/skill_manager.py`) dynamicznie ładuje pliki `.py`, waliduje AST i rejestruje je w jądrze (Kernel).

### Sposób Komunikacji
- **Wewnętrzna:** Narzędzia są wywoływane bezpośrednio przez `Kernel` w procesie Python.
- **Brak API:** Narzędzia nie są wystawione jako API HTTP/OpenAPI. Nie ma endpointu `GET /tools` ani `POST /tools/execute`.
- **Brak MCP:** System nie implementuje protokołu **Model Context Protocol (MCP)** (JSON-RPC 2.0).

---

## 2. Analiza Zgodności z MCP

**Model Context Protocol (MCP)** to otwarty standard Anthropic umożliwiający bezpieczne wystawianie narzędzi i kontekstu dla modeli AI.

| Cecha | Venom (Obecnie) | Standard MCP | Werdykt |
|-------|-----------------|--------------|---------|
| **Definicja** | Dekoratory Semantic Kernel (`@kernel_function`) | JSON Schema (OpenAPI-like) | ⚠️ Częściowo zgodne (SK generuje schematy wewnętrznie) |
| **Transport** | In-process Python calls | JSON-RPC 2.0 (Stdio / SSE) | ❌ Niezgodne |
| **Discovery** | `SkillManager` skanuje pliki | Metoda `tools/list` | ❌ Niezgodne |
| **Wywołanie** | `kernel.invoke()` | Metoda `tools/call` | ❌ Niezgodne |
| **Bezpieczeństwo** | Walidacja AST (`validate_skill`) | Model uprawnień MCP | ⚠️ Własne rozwiązanie |

**Wniosek:** Narzędzia są ustandaryzowane w ramach frameworku Semantic Kernel, ale **nie są zgodne** ze standardem MCP/OpenAPI w warstwie komunikacji.

---

## 3. Plan Standaryzacji (Rekomendacja)

Aby osiągnąć zgodność z MCP, nie trzeba przepisywać samych narzędzi. Należy stworzyć **Adapter MCP**, który wystawi istniejące pluginy Semantic Kernel jako serwer MCP.

### Kroki Migracji (Propozycja do Planu nr 98)

1.  **Instalacja SDK**: Dodanie biblioteki `mcp` (Python SDK).
2.  **MCP Server Adapter (`venom_core/api/mcp_server.py`)**:
    - Implementacja serwera MCP (FastMcp lub LowLevel).
    - Mapowanie: `SkillManager.get_loaded_skills()` -> `mcp.list_tools()`.
    - Mapowanie: `mcp.call_tool()` -> `kernel.invoke()`.
3.  **Transport**:
    - Wystawienie endpointu SSE: `POST /api/v1/mcp/sse` (dla klientów HTTP).
    - Opcjonalnie obsługa Stdio (dla lokalnych agentów jak Claude Desktop).
4.  **Generowanie Schematów**:
    - Wykorzystanie wbudowanych funkcji Semantic Kernel do generowania JSON Schema dla funkcji i przekazywanie ich do MCP.

### Korzyści
- Możliwość podłączenia Venoma do Claude Desktop jako narzędzia.
- Umożliwienie innym agentom (nie tylko wewnętrznym) korzystania z narzędzi Venoma.
- Standaryzacja obsługi błędów i logowania.

---

## 4. Decyzja
Czy rozpocząć implementację **MCP Adaptera**?
