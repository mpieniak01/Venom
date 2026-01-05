# PR 87: Optymalizacja czasów reakcji aplikacji

## Cel
Skrócić czas reakcji UI i backendu na akcje użytkownika oraz poprawić TTFT (time‑to‑first‑token) bez utraty logów i kontroli routingu.

## Zakres
- Frontend (Next.js / Cockpit)
- Backend API (SSE / RequestTracer)
- LLM runtime (streaming)

## Zmiany w systemie (skrót)
- **Tryby czatu (Direct/Normal/Complex)**: ręczny przełącznik strategii i routing intencji.
- **Streaming i metryki backendu**: `first_token` + `streaming` w `history/requests/{id}`, krok `LLM.start` w RequestTracer.
- **UI timings**: pomiar `submit → historia` oraz TTFT w panelu szczegółów.
- **Optimistic history**: natychmiastowy wpis użytkownika w historii (Direct i Normal).
- **Status odpowiedzi**: badge statusu pokazuje także tryb czatu (Direct/Normal/Complex).
- **Stabilność testów**: stałe stuby i localStorage w testach e2e (bez zależności od runtime/Ollama).

## Wzorzec krytycznej ścieżki (UI → LLM → UI)
- Na ścieżce: wysłanie promptu, TTFT, streaming do UI.
- W tle: trace, memory, odświeżenia paneli pomocniczych.

## Dowody działania (A3)
- **Direct (simple stream, curl)**: streaming przyrostowy działa (wiele fragmentów w trakcie generacji).
- **Normal (SSE tasks, szybkie podłączenie)**: SSE emituje narastające `task_update` z `result` i `streaming.chunk_count`.
- **Uwaga**: opóźnione podłączenie do SSE może dawać wrażenie „jednego strzału”.

## Testy i wyniki referencyjne
- `npm --prefix web-next run test:e2e` — PASS (23 testy), w tym routing/TTFT/streaming.
- `tests/perf/chat-latency.spec.ts` — PASS (Next Cockpit 4.0s).
- Szczegółowe wyniki perf: `docs/TESTING_CHAT_LATENCY.md`.

## Dokumenty docelowe (gdzie przeniesiono wiedzę)
- Tryby czatu, routing, ścieżka krytyczna: `docs/CHAT_SESSION.md`.
- RequestTracer i pola `first_token`/`streaming`: `docs/REQUEST_TRACING_GUIDE.md`.
- Testy wydajności i referencyjne wyniki: `docs/TESTING_CHAT_LATENCY.md`.

## Status
- Brak otwartych zadań implementacyjnych w ramach PR‑87.
- Monitoring regresji: utrzymać stabilność TTFT i SSE w trybie Normal.
