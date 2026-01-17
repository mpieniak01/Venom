# Podsumowanie Zmian dla PR-88-090 (Memory, Benchmark, Chat Opt)

Dokument zawiera techniczny opis zmian w kodzie oraz dodanych testów w ramach zadań:
- **088**: Analiza i Higiena Pamięci (Memory/Lessons) -> *Feature*
- **089**: Tuning LLM Server & Benchmark -> *Feature*
- **090**: Optymalizacja Czat i Semantic Cache -> *Optimization*

## 1. Backend (Venom Core)

### Memory & Lessons (088)
Zaimplementowano zaawansowane API do zarządzania cyklem życia lekcji (Lessons Hygiene).
- **Nowe Endpointy** w `venom_core/api/routes/memory.py`:
  - `DELETE /lessons/prune/latest`: Usuwa N ostatnich lekcji.
  - `DELETE /lessons/prune/range`: Usuwa lekcje z zadanego zakresu dat.
  - `DELETE /lessons/prune/tag`: Usuwa lekcje otagowane konkretnym tagiem.
  - `DELETE /lessons/prune/ttl`: Usuwa lekcje starsze niż X dni.
  - `POST /lessons/dedupe`: Usuwa zduplikowane lekcje.
  - `DELETE /lessons/purge`: Całkowite czyszczenie bazy lekcji.
- **Logika**: Rozbudowano `LessonsStore` w `venom_core/memory/lessons_store.py` o metody filtracji i usuwania.

### Benchmark LLM (089)
Stworzono pełny stack (API + Service) do porównawczych testów wydajności modeli (vLLM vs Ollama).
- **Service**: `BenchmarkService` w `venom_core/services/benchmark.py` obsługuje:
  - Sekwencyjne uruchamianie testów na liście modeli.
  - Pomiar metryk: TTFT (Time To First Token), Tokens/Sec, VRAM Usage.
  - Obsługę błędów (OOM, Timeout).
- **API**: `venom_core/api/routes/benchmark.py`:
  - `POST /start`: Inicjuje asynchroniczny job benchmarku.
  - `GET /{id}/status`: Zwraca postęp i wyniki (polling).
- **Adapter**: `GenerationParamsAdapter` w `venom_core/core/generation_params_adapter.py` normalizuje parametry (temp, top_p) między różnymi backendami.

### Chat Optimization & Semantic Cache (090)
Ulepszono mechanizm Hidden Prompts (ukrytych promptów wstrzykiwanych do kontekstu) o Semantic Cache.
- **Cache Logic**: Wdrożono wyszukiwanie semantyczne (Sentence Transformers) dla *Hidden Prompts*, aby unikać ponownych zapytań do LLM dla identycznych/podobnych intencji.
- **Payload Exposure**: Backend zwraca pełny kontekst użyty do generacji (w polu `context_used`), co umożliwia frontendowi wyświetlenie debug info.

## 2. Frontend (Web Next)

### Brain Hygiene UI (088)
Dodano interfejs do zarządzania "higieną" wiedzy w panelu `/brain`.
- **Nowy Tab**: `Hygiene` w `web-next/components/brain/brain-home.tsx`.
- **Komponent**: `LessonPruningPanel` (`web-next/components/brain/lesson-pruning.tsx`) umożliwia wywoływanie endpointów API (TTL, Tag, Range, Dedupe) z poziomu UI.

### Benchmark UI (089)
Zastąpiono "mock" benchmarku pełną integracją.
- **Strona**: `web-next/app/benchmark/page.tsx` teraz komunikuje się z backendem.
- **Hook**: `web-next/hooks/use-benchmark.ts` obsługuje cykl życia testu (Start -> Poll Status -> Result).
- **Typy**: Zaktualizowano `web-next/lib/types.ts` o `BenchmarkStartResponse`, `BenchmarkStatusResponse`.

### Chat UX (090)
Optymalizacja responsywności i transparentności czatu.
- **Source Labeling**: UI wyraźnie oznacza źródło odpowiedzi (Live / History / Cache).
- **Debug View**: Panel "Szczegóły" wyświetla surowy payload (prompty, parametry) otrzymany z backendu, co ułatwia debugowanie halucynacji.

## 3. Testy (Unit & Integration)

Dodano szeroki zestaw testów pokrywających nowe funkcjonalności:

### Backend Tests
- **Memory API**: `tests/test_memory_api.py` (53 testy) – weryfikacja wszystkich wariantów pruningu, obsługi błędów i kodów HTTP.
- **Hygiene Logic**: `tests/test_knowledge_hygiene.py` – testy logiki biznesowej usuwania lekcji i spójności danych.
- **Lessons Store**: `tests/test_lessons_store.py` – testy operacji IO na pliku JSON.
- **Benchmark**:
    - `tests/test_benchmark_service.py` – testy serwisu, mockowanie runnerów LLM.
    - `tests/test_llm_server_tuning.py` (w ramach 089) – weryfikacja parametrów generacji.

### Frontend Tests
- **Unit Tests**: `test-web-unit` (Vitest) pokrywa:
    - Renderowanie `LessonPruningPanel`.
    - Logikę hooka `useBenchmark`.
    - Poprawność typów w `types.ts`.

## 4. Podsumowanie Plików (Key Files)
Lista kluczowych plików objętych zmianami kodowymi:

**Backend:**
- `venom_core/api/routes/memory.py`
- `venom_core/api/routes/benchmark.py`
- `venom_core/services/benchmark.py`
- `venom_core/memory/lessons_store.py`
- `venom_core/core/generation_params_adapter.py`

**Frontend:**
- `web-next/app/benchmark/page.tsx`
- `web-next/hooks/use-benchmark.ts`
- `web-next/components/brain/lesson-pruning.tsx`
- `web-next/components/brain/brain-home.tsx`

**Tests:**
- `tests/test_memory_api.py`
- `tests/test_knowledge_hygiene.py`
- `tests/test_lessons_store.py`
- `tests/test_benchmark_service.py`
