# LLM Runtime 3-Stack Benchmark Baseline (aktualizacja 2026-02-26)

Status: kanoniczny baseline latencji dla `onnx` / `ollama` / `vllm`.

## Zakres

Dokument zawiera najnowszy pełny przebieg: jawne komendy i zmierzone czasy.

## Środowisko

1. Data: 2026-02-26
2. Profil runtime: `full`
3. Rodzina modeli: Gemma 3
4. Sprzęt:
   - GPU: NVIDIA GeForce RTX 3060 (12 GB VRAM)
   - CPU: Intel i5-14400F
   - RAM po stronie Linux runtime: ~15 GiB

## Modele testowane

1. `gemma-3-1b-it-onnx-q4` (`onnx`)
2. `gemma-3-1b-it-onnx-q4-genai` (`onnx`)
3. `gemma-3-4b-it-onnx-build-test` (`onnx`)
4. `gemma-3-4b-it-onnx-cpu-int4` (`onnx`)
5. `gemma-3-4b-it-onnx-int4` (`onnx`)
6. `gemma3:4b` (`ollama`)
7. `gemma-3-4b-it` (`vllm`)

## Stosy testowane

1. `onnx`
2. `ollama`
3. `vllm`

## Co uruchomiono

### Zestaw ONNX (wszystkie lokalnie dostępne warianty Gemma3 ONNX)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/system/llm-servers/active -d '{"server_name":"onnx"}'

# powtarzane dla każdego modelu z /api/v1/models providers.onnx
curl -X POST http://127.0.0.1:8000/api/v1/models/switch -d '{"name":"<MODEL>"}'
VENOM_LLM_MODEL=<MODEL> VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_llm_simple_e2e.py
VENOM_LLM_MODEL=<MODEL> VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_llm_latency_e2e.py
VENOM_LLM_MODEL=<MODEL> VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_latency_modes_e2e.py
```

### Ollama

```bash
curl -X POST http://127.0.0.1:8000/api/v1/system/llm-servers/active -d '{"server_name":"ollama"}'
curl -X POST http://127.0.0.1:8000/api/v1/models/switch -d '{"name":"gemma3:4b"}'
VENOM_LLM_MODEL='gemma3:4b' VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_llm_simple_e2e.py
VENOM_LLM_MODEL='gemma3:4b' VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_llm_latency_e2e.py
VENOM_LLM_MODEL='gemma3:4b' VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_latency_modes_e2e.py
```

### vLLM

```bash
curl -X POST http://127.0.0.1:8000/api/v1/system/llm-servers/active -d '{"server_name":"vllm"}'
curl -X POST http://127.0.0.1:8000/api/v1/models/switch -d '{"name":"gemma-3-4b-it"}'
VENOM_LLM_MODEL='gemma-3-4b-it' VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_llm_simple_e2e.py
VENOM_LLM_MODEL='gemma-3-4b-it' VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_llm_latency_e2e.py
VENOM_LLM_MODEL='gemma-3-4b-it' VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_latency_modes_e2e.py
```

## Status wykonania

1. ONNX: 5/5 przełączeń modeli OK, wszystkie testy PASS.
2. Ollama (`gemma3:4b`): wszystkie testy PASS.
3. vLLM (`gemma-3-4b-it`): wszystkie testy PASS.

## Wyniki latencji (średnie)

| Stos / Model | simple total | latency normal total | modes fast total | modes normal total | modes complex total |
|---|---:|---:|---:|---:|---:|
| `onnx / gemma-3-1b-it-onnx-q4` | `0.03s` | `0.12s` | `0.03s` | `0.15s` | `9.36s` |
| `onnx / gemma-3-1b-it-onnx-q4-genai` | `0.04s` | `0.26s` | `0.04s` | `0.17s` | `9.61s` |
| `onnx / gemma-3-4b-it-onnx-build-test` | `0.13s` | `0.18s` | `0.03s` | `0.17s` | `8.92s` |
| `onnx / gemma-3-4b-it-onnx-cpu-int4` | `0.03s` | `0.18s` | `0.03s` | `0.12s` | `9.07s` |
| `onnx / gemma-3-4b-it-onnx-int4` | `0.03s` | `0.24s` | `0.04s` | `0.16s` | `9.93s` |
| `ollama / gemma3:4b` | `1.85s` | `0.02s` | `0.29s` | `0.02s` | `21.19s` |
| `vllm / gemma-3-4b-it` | `0.06s` | `0.04s` | `0.06s` | `0.02s` | `2.63s` |

## Wnioski praktyczne

1. Najniższy czas `complex` w tym przebiegu: `vllm / gemma-3-4b-it` (`2.63s`).
2. Warianty ONNX są stabilne, `complex` w zakresie `8.9s-9.9s`.
3. `ollama / gemma3:4b` jest najwolniejszy w `complex` (`21.19s`), ale działa stabilnie.
4. W tym środowisku brak artefaktu Gemma 3B ONNX; dostępne są warianty 1B i 4B.

## Polityka baseline

1. Ten plik utrzymujemy jako bieżący pełny baseline.
2. Nowe pomiary dopisujemy jawnie w tym pliku (bez zależności od dokumentacji prywatnej).
3. Każda aktualizacja musi zawierać: komendy + czasy.

## Benchmark sanity coding Python (PR 190, 2026-03-03)

Artefakty zrodlowe:
- `data/benchmarks/ollama_first_sieve_rerun_with_timing_20260303/scheduler_summary.json`
- `data/benchmarks/ollama_first_sieve_rerun_with_timing_20260303/single_*_python_sanity.json`

Okno (UTC): `2026-03-03T10:47:12Z` -> `2026-03-03T10:58:35Z`.
Wynik: `7/10 PASS` (`70.0%`).

Definicje czasow:
- `warmup [s]` -> `load_duration` z Ollama
- `coding [s]` -> `eval_duration` z Ollama
- `request [s]` -> calkowity czas requestu po stronie runnera

| Model | Wynik | warmup [s] | coding [s] | request [s] | Uwagi |
|---|---|---:|---:|---:|---|
| `codestral:latest` | PASS | 290.716 | 9.402 | 301.156 | Zaliczony po zwiekszeniu timeout |
| `deepcoder:latest` | PASS | 197.823 | 16.231 | 214.823 | Zaliczony po zwiekszeniu timeout |
| `deepseek-r1:8b` | PASS | 7.287 | 2.791 | 10.302 | Stabilny PASS |
| `gemma3:4b` | PASS | 4.198 | 1.607 | 5.998 | Stabilny PASS |
| `gemma3:latest` | PASS | 0.246 | 1.158 | 1.490 | Stabilny PASS |
| `qwen2.5-coder:7b` | PASS | 13.456 | 1.357 | 15.029 | Stabilny PASS |
| `qwen3:4b` | PASS | 2.981 | 38.335 | 42.426 | Wolna faza kodowania |
| `openclaw-qwen3vl-8b-opt:latest` | FAIL | - | - | - | Pusta odpowiedz z `/api/generate` |
| `qwen2.5-coder:3b` | FAIL | - | - | - | Brak poprawnego bloku kodu w odpowiedzi |
| `voytas26/openclaw-qwen3vl-8b-opt:latest` | FAIL | - | - | - | Pusta odpowiedz z `/api/generate` |
