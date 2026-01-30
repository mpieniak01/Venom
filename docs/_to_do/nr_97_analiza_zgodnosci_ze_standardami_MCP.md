# Plan Głębokiego Refaktoringu: Ujednolicenie API Czatów (Direct Mode -> SSE)

**Data:** 2026-01-30
**Cel:** Wyeliminowanie długu technicznego w obsłudze trybu "Direct" poprzez migrację z surowego strumienia tekstu na format Server-Sent Events (SSE), spójny z resztą systemu.
**Zakres:** Backend (`llm_simple.py`), Frontend (`cockpit-chat-send.ts`), Testy (Pytest, E2E).

---

## 1. Analiza stanu obecnego

### Backend: `POST /api/v1/llm/simple/stream`
- Zwraca `StreamingResponse` z `media-type: text/plain`.
- Chunkuje odpowiedź z LLM i wysyła fragmenty tekstu bezpośrednio.
- Rzuca wyjątkami `HTTPException` w trakcie streamu, co zrywa połączenie (klient widzi błąd sieci).

### Frontend: `useChatSend` (Direct Mode)
- Używa `sendSimpleChatStream` (fetch).
- Pobiera `response.body.getReader()`.
- W pętli `while(true)` ręcznie dekoduje bajty (`TextDecoder`).
- "Symuluje" wpisy w lokalnej historii (`setLocalSessionHistory`), ponieważ backend nie tworzy zadania w `SessionStore` (tryb "Simple").
- Ryzyko: Jeśli backend zmieni format (np. doda prefixy `data:`), frontend przestanie działać.

### Testy
- `tests/test_llm_simple_stream.py`: Oczekuje surowego tekstu (`"".join(list(response.iter_text()))`).
- E2E Playwright: Testy wydajnościowe (latency) korzystają z tego trybu.

---

## 2. Specyfikacja zmian (Scope)

### A. Backend (`venom_core/api/routes/llm_simple.py`)
1.  **Zmiana formatu odpowiedzi**:
    - Kontent typu: `text/event-stream`.
    - Format danych: `event: content\ndata: {"text": "..."}\n\n` (lub po prostu `data: ...` dla zgodności z OpenAI style, ale lepiej użyć eventów nazwanych dla spójności z `task_update`).
    - Sugerowany format zdarzeń:
        - `event: content` -> `data: {"text": "fragment"}`
        - `event: error` -> `data: {"code": "...", "message": "..."}` (zamiast zrywania połączenia)
        - `event: done` -> `data: {}` (sygnał końca)

2.  **Obsługa błędów**:
    - Zamiast `raise HTTPException`, wyślij zdarzenie `event: error`. Pozwoli to frontendowi wyświetlić błąd w dymku czatu zamiast "Network Error".

### B. Frontend (`web-next/components/cockpit/cockpit-chat-send.ts`)
1.  **Usunięcie `reader.read()`**:
    - Zastąpienie pętli dekodującej użyciem adaptera SSE (np. `fetchEventSource` lub istniejącego `useTaskStream`-like logic).
2.  **Wspólna logika strumienia**:
    - Stworzenie pomocniczej funkcji `handleSseStream(url, payload, callback)`, która obsługuje eventy `content`, `error`, `done`.
    - Callback `onContent` aktualizowałby `localSessionHistory` (tak jak teraz, bo Direct nadal nie zapisuje w bazie backendu).

### C. Testy
1.  **Backend Pytest**:
    - Aktualizacja `test_llm_simple_stream.py`: Test musi parsować format SSE (szukać `data: ...`).
2.  **E2E Playwright**:
    - Weryfikacja czy testy `latency` przechodzą po zmianie protokołu.
    - Testy funkcjonalne czatu w trybie Direct.

---

## 3. Plan Realizacji (Kroki)

### Faza 1: Backend (API Contract)
1.  [x] Zmodyfikuj `llm_simple.py`:
    - Zmień `StreamingResponse` na format SSE.
    - Zaimplementuj generator `sse_generator()`.
2.  [x] Zaktualizuj `test_llm_simple_stream.py`:
    - Dostosuj asercje do nowego formatu (očekuj `data:` prefixów).

### Faza 2: Frontend (Consumer)
3.  [x] Zaktualizuj `api-client.ts` (opcjonalnie) lub dodaj helper do obsługi SSE ad-hoc.
4.  [x] Refaktoring `cockpit-chat-send.ts`:
    - Przełącz logikę Direct Mode na konsumpcję SSE.
    - Obsłuż eventy `content`, `error` i `done`.
5.  [x] Weryfikacja manualna w UI (czy tekst się pojawia, czy błędy są widoczne).

### Faza 3: Stabilizacja i Testy
6.  [x] Uruchomienie pełnych testów E2E (`npm run test:e2e`).
7.  [x] Sprawdzenie czy nie wpłynęło to negatywnie na TTFT (Time To First Token) - narzut SSE jest minimalny, ale warto sprawdzić.

---

## 4. Kryteria Akceptacji (DoD)
- [x] Tryb Direct działa w UI tak samo szybko jak wcześniej.
- [x] Backend zwraca poprawny `text/event-stream`.
- [x] Testy jednostkowe backendu (`pytest`) przechodzą.
- [x] Testy E2E frontendu przechodzą.
- [x] Kod frontendu nie zawiera już ręcznego dekodowania `TextDecoder` w pętli `while`.
