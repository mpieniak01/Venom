# 073: Dedykowany ekran zarządzania modelami (Ollama + HuggingFace)

## Cel
Zbudować osobny ekran do zarządzania modelami LLM, zasilany integracją
z **ollama.com** i **huggingface.co** (trendy + instalacja/aktywacja/usuwanie).

## Stan obecny w kodzie (po analizie)
- Backend ma `ModelRegistry` i endpointy:
  - `GET /api/v1/models/providers` (lista modeli z providerów),
  - `POST /api/v1/models/registry/install`, `DELETE /api/v1/models/registry/{name}`,
  - `POST /api/v1/models/activate`,
  - `GET /api/v1/models/operations`.
- `ModelRegistry`:
  - Ollama: pobiera listę z `http://localhost:11434/api/tags`.
  - HuggingFace: lista modeli jest **stubem** (statyczna lista 2 modeli).
  - Brak realnego API do trendów HF/Ollama.
- `GET /api/v1/models` zwraca lokalne modele + `providers` bucket (ollama/vllm).

## Zakres
1. **Nowy ekran**
   - Dedykowana ścieżka w UI (np. `/models`).
   - Sekcje: trendy, zainstalowane, dostępne do pobrania.

2. **Integracja z zewnętrznymi API**
   - Pobranie trendów i list modeli z `ollama.com`.
   - Pobranie trendów i list modeli z `huggingface.co`.
   - Cache i rate‑limit, fallback bez internetu.

3. **Operacje na modelach**
   - Instalacja (pobranie) modelu.
   - Aktywacja modelu dla runtime.
   - Usunięcie modelu.
   - Statusy operacji (progress, błąd, sukces).

4. **Kontrakt danych**
   - Spójne mapowanie: provider → runtime → model.
   - Walidacja kompatybilności (np. Ollama-only vs vLLM).

## Kryteria akceptacji
- Ekran prezentuje trendy i listy modeli z obu źródeł.
- Użytkownik może łatwo zainstalować, aktywować i usunąć model.
- UI pokazuje status operacji i obsługuje błędy.
- Lista modeli jest spójna z runtime i nie miesza providerów.

## Do zrobienia
1. **Backend: integracje**
   - Dodać nowe endpointy: np. `GET /api/v1/models/trending?provider=...`.
   - Ollama: pobierać trendy z publicznego API (brak w kodzie).
   - HuggingFace: pobierać trendy przez HF Hub API (brak w kodzie).
   - Cache (np. TTL 15-60 min) + fallback do ostatniego wyniku.
2. **Backend: kontrakt danych**
   - Zdefiniować spójny format: `provider`, `model_name`, `display_name`,
     `size_gb`, `runtime`, `tags`, `downloads`, `likes`.
   - Walidować kompatybilność: `ollama` → runtime `ollama`,
     HF → runtime `vllm`.
3. **UI: nowy ekran**
   - Strona `/models` z sekcjami: Trendy, Zainstalowane, Dostępne.
   - Akcje: install, activate, delete, podgląd statusu operacji.
   - Widoczny stan offline (brak Internetu) i link do instrukcji.
4. **Telemetria**
   - Log operacji: install/remove/activate z providerem i runtime.
   - Ewentualne powiadomienia toast o sukcesie/błędzie.

## Proponowane pliki do zmiany
- `web-next/app/models/page.tsx` (nowy ekran)
- `web-next/components/models/*`
- `web-next/hooks/use-api.ts`
- `venom_core/api/routes/models.py`
- `venom_core/core/model_manager.py`
- `venom_core/core/model_registry.py`
- `docs/MODEL_MANAGEMENT.md`

## Zależności / uwagi dla wykonawcy
- `ModelRegistry` już obsługuje Ollama listę lokalną, ale HF jest statyczny stub.
- Trzeba odróżnić listy: lokalne (z `/api/v1/models`) vs zewnętrzne trendy.
- Wymagany publiczny client HTTP (np. `httpx`) + caching po stronie backendu.
- Bez internetu ekran powinien pokazywać dane z cache lub „brak danych”.
