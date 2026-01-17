# PR 89: Strojenie serwerow LLM (Ollama + vLLM) dla Gemma 3

## Cel
Dostroic oba lokalne serwery (Ollama i vLLM) dla tego samego modelu Gemma 3 pod single-user desktop, z naciskiem na szybkie odpowiedzi i dlugi kontekst. Oba runtime maja uzywac spoinych parametrow generacji i limitow kontekstu, bez optymalizacji pod multi-user ani serwer cloud. Celem PR jest porownanie wynikow testow obu rozwiazan i ewentualna decyzja o oczyszczeniu stosu i pozostawieniu tylko jednego runtime.

## Stan prac / szybki update
- [x] Ustabilizowany start vLLM na 12 GB GPU dla Gemma 3 4B: `max_model_len=1024`, `max_num_batched_tokens=128`, `max_num_seqs=2`, `gpu_memory_utilization=0.85`, model `gemma-3-4b-it` (ustawione w `.env`, `.env.example`, README). vLLM odpowiada na `/v1/models` po restarcie.
- [x] Spójny model po obu stronach: zainstalowane `models/gemma-3-4b-it` (aktywny). Wariant `gemma-3-4b-pt` usunięty z dysku (zwolniono ok. 8 GB) i nie jest już używany.
- [x] Profil generacji (temperature/top_p/max_tokens) ujednolicony w `MODEL_GENERATION_OVERRIDES` dla Gemma 3 (`vllm/gemma-3-4b-it` oraz `ollama/gemma3:4b`: temp 0.3, top_p 0.9, max_tokens/num_predict 800, ctx 1024).
- [x] Testy wydajności/TTFT/tok/s dla Ollama vs vLLM – Pełna integracja Frontend <-> Backend zaimplementowana (poling statusu, obsługa błędów, prawdziwe metryki).
- [x] Jednostkowe testy benchmarku (routing endpointów) – dodane testy, które sprawdzają wybór właściwego endpointu (vLLM vs Ollama) w `BenchmarkService._test_model`.
- [x] Manifest obejmuje aktywny wariant vLLM (`gemma-3-4b-it`) oraz Ollama (`gemma3:4b`); wariant `gemma-3-4b-pt` usunięty z dysku i nie powinien figurować w manifestach. Aktywacja modelu w backendzie aktualizuje `.env`/SETTINGS i restartuje serwer (LLMController) oraz zwraca health status.
- [x] vLLM nadal potrafi nie wystartować na 12 GB (KV cache OOM) -> **STATUS: RESOLVED**. Model `gemma-3-4b-it` (Instruction Tuned) jest utrzymany i skonfigurowany. Odrzucono jedynie wersje wymagające TP (Tensor Parallelism) lub większych zasobów.
- [x] Stan faktyczny (lokalnie): aktywny runtime Ollama `gemma3:4b` ORAZ vLLM `gemma-3-4b-it`.
- [x] Bieżący stan środowiska (lokalny): vLLM skonfigurowany dla `gemma-3-4b-it` (single GPU).
- [x] Tryb DIRECT w UI: zapis lokalnej historii pytania/odpowiedzi (także przy błędzie), brak „znikania” wiadomości.
- [x] Etykiety runtime w historii/szczegółach: użycie faktycznego runtime/endpoint z backendu (bez mylącego „ollama @ 8001”).
- [x] Wymuszenie języka w trybie DIRECT: backend dodaje system prompt „Odpowiadaj po polsku.” dla strumienia prostego.
- [x] Spójny request_id w trybie DIRECT przy CORS: ekspozycja `x-request-id`/`x-session-id` w CORS (żeby frontend mógł zlinkować historię i szczegóły).

## Kolejne kroki (do implementacji)
### Przełączanie modeli/serwerów (bez konsoli, tylko z UI)
- Backend:
  - (Zrealizowane) `ModelRegistry.activate_model`: sprawdza manifest, zapisuje do `.env`/SETTINGS (`LLM_MODEL_NAME`, `VLLM_MODEL_PATH`, `VLLM_SERVED_MODEL_NAME`, `LAST_MODEL_VLLM` / `LAST_MODEL_OLLAMA`) i restartuje vLLM/Ollamę przez `LlmServerController`; zwraca health status.
  - `/api/v1/system/llm-servers/active`: zatrzymuje inne serwery, startuje wybrany, aktywuje zapamiętany model (LAST_MODEL_*), zwraca runtime_id/status.
  - `/api/v1/models/activate`: przyjmuje `runtime` + `name`, aktywuje model (z restartem vLLM gdy zmienia się model), zwraca health/online/offline.
- Frontend:
  - Selektor serwera woła `/system/llm-servers/active`, selektor modelu woła `/models/activate` (runtime, name) i pokazuje loading na czas restartu.
  - Karta modelu pokazuje status (online/offline) i ewentualne błędy 404/400 z backendu.
- Testy:
  - E2E: aktywacja `gemma3:4b` na Ollama → health OK, czat bez błędów.
  - Benchmark: opcjonalnie przed pomiarem wywołuje `/models/activate` dla wybranego modelu/runtime.

### Benchmark i UI
- Podpiąć frontend `/benchmark` do backendu `/api/v1/benchmark` (zastąpić symulację, dodać stream logów/SSE).
- Uruchomić benchmark na Gemma 3 dla obu runtime (`gemma-3-4b-it` na vLLM, `gemma3:4b` na Ollama) i zebrać TTFT/tok/s/VRAM.

## Propozycje profili vLLM (single-user, priorytet TTFT i kontekstu)
- Profil “low-VRAM / stabilny start” (na 12 GB):
  - `VLLM_MAX_MODEL_LEN=1024`
  - `VLLM_MAX_NUM_BATCHED_TOKENS=32–64`
  - `VLLM_MAX_NUM_SEQS=1`
  - `VLLM_GPU_MEMORY_UTILIZATION=0.9`
  - Cel: minimalizować KV cache i zapewnić start bez OOM; krótszy kontekst, szybkie TTFT.
- Profil “balanced context” (jeśli startuje):
  - `VLLM_MAX_MODEL_LEN=2048`
  - `VLLM_MAX_NUM_BATCHED_TOKENS=32`
  - `VLLM_MAX_NUM_SEQS=1`
  - `VLLM_GPU_MEMORY_UTILIZATION=0.9–0.92`
  - Cel: 2k kontekstu kosztem nieco wolniejszego TTFT, nadal niskie QPS.
- Profil “max context (ryzykowny na 12 GB)”:
  - `VLLM_MAX_MODEL_LEN=4096`
  - `VLLM_MAX_NUM_BATCHED_TOKENS=16–32`
  - `VLLM_MAX_NUM_SEQS=1`
  - `VLLM_GPU_MEMORY_UTILIZATION=0.92`
  - Cel: dłuższy kontekst, ale wysokie ryzyko OOM/`Engine core initialization failed` na 12 GB – tylko do testów.
Rekomendacja domyślna: profil “low-VRAM / stabilny start” (1024 ctx, 32–64 batched tokens, 1 seq, gpu_mem 0.9) jako baza pod single-user z priorytetem TTFT. UI powinno sygnalizować, jeśli vLLM nie wstaje, i oferować przełączenie na Ollamę.

## Kontekst i obecne obserwacje
- vLLM przy ustawieniach domyślnych (131072 ctx) walił się na KV cache; zjechaliśmy do 1024 kontekstu i małej współbieżności, żeby zmieścić się w 12 GB VRAM.
- Ollama radzi sobie z Gemma 3, prawdopodobnie dzięki quant/innemu zarządzaniu pamięcią.
- Potrzebujemy porównywalnych parametrów (temperature/top_p/max_tokens/limit kontekstu) dla obu runtime, aby testy szybkosci byly uczciwe.


## Zakres PR (co wchodzi)
1) Ujednolicenie parametrow generacji (single-source-of-truth):
   - Ustalenie spolejnego profilu: temperature, top_p, max_tokens (output), limit kontekstu.
   - Wdrozenie profilu dla obu runtime:
     - Ollama: num_ctx, num_predict, temperature, top_p.
     - vLLM: max_model_len, max_num_batched_tokens, temperature, top_p.
   - Uzycie istniejacego mechanizmu MODEL_GENERATION_OVERRIDES, aby te parametry obowiazywaly dla Gemma 3 niezaleznie od runtime.

2) Stabilny start vLLM na desktopie:
   - Ograniczenie max_model_len do realnego progu VRAM (np. 4096 lub 8192) dla Gemma 3 4B.
   - Dopasowanie max_num_batched_tokens tak, aby vLLM nie padal przy starcie (KV cache).
   - Sprawdzenie, czy samo podniesienie gpu_memory_utilization pomaga, ale bez przesady (ryzyko OOM).

3) Profile uzytkownika (single-user desktop):
   - Ustawienia zoptymalizowane pod szybkie pierwsze tokeny i sensowny kontekst.
   - Brak konfiguracji pod rownolegle sesje (no multi-user concurrency tuning).

4) Testy szybkosci i uzywalnosci (lokalne):
   - Krotki zestaw testow (TTFT, tok/s, stabilnosc pod dluuugim promptem).
   - Testy dla obu runtime przy tych samych parametrach.

## Poza zakresem
- Skalowanie wielosesyjne, multi-user, poziom produkcyjny cloud.
- Zmiana modelu na inny (skupiamy sie na Gemma 3).
- Rozbudowane automaty testowe w CI.

## Proponowany profil parametrow (do potwierdzenia)
- temperature: 0.3 (deterministyczne, stabilne odpowiedzi)
- top_p: 0.9
- max_tokens: 800-1200 (output)
- context length:
  - vLLM: max_model_len 4096 lub 8192 (w zaleznosci od VRAM)
  - Ollama: num_ctx 4096 lub 8192

## Mapowanie parametrow (spojny profil)
- General:
  - temperature -> temperature
  - top_p -> top_p
  - max_tokens ->
    - vLLM: max_tokens
    - Ollama: num_predict
- Context length:
  - vLLM: max_model_len
  - Ollama: num_ctx

## Ryzyka i decyzje
- vLLM w obecnym srodowisku nie utrzyma 131072 ctx; konieczne twarde ograniczenie.
- Jezeli vLLM nadal pada przy 4096, schodzimy nizej (2048) i weryfikujemy VRAM.
- Zachowac jeden model Gemma 3 dla obu runtime; roznice jedynie w implementacji runtime.

## Do dostarczenia w PR
- Zaktualizowane konfiguracje runtime (Ollama + vLLM) z identycznym profilem.
- Dokumentacja "profilu single-user" (krotka sekcja w PR).
- Wyniki testow szybkosci (TTFT, tok/s) dla obu runtime.
- Instrukcja jak odtworzyc test lokalnie.

## Kryteria akceptacji
- vLLM startuje stabilnie i odpowiada na zapytania.
- Ollama i vLLM dzialaja na tym samym modelu Gemma 3 z tymi samymi parametrami generacji.
- Wyniki testow szybkosci sa zebrane i porownane.
