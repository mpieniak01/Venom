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
