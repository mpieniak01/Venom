# LLM Runtime 3-Stack Benchmark Baseline (updated 2026-02-26)

Status: canonical latency baseline for `onnx` / `ollama` / `vllm`.

## Scope

This document captures the latest full run with explicit command set and measured latencies.

## Environment

1. Date: 2026-02-26
2. Runtime profile: `full`
3. Model family: Gemma 3
4. Hardware:
   - GPU: NVIDIA GeForce RTX 3060 (12 GB VRAM)
   - CPU: Intel i5-14400F
   - Linux runtime RAM: ~15 GiB

## What Was Run

### ONNX set (all locally available Gemma3 ONNX variants)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/system/llm-servers/active -d '{"server_name":"onnx"}'

# repeated per model from /api/v1/models providers.onnx
curl -X POST http://127.0.0.1:8000/api/v1/models/switch -d '{"name":"<MODEL>"}'
VENOM_LLM_MODEL=<MODEL> VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_llm_simple_e2e.py
VENOM_LLM_MODEL=<MODEL> VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_llm_latency_e2e.py
VENOM_LLM_MODEL=<MODEL> VENOM_LLM_REPEATS=2 .venv/bin/pytest -q -s tests/perf/test_latency_modes_e2e.py
```

ONNX models tested:
1. `gemma-3-1b-it-onnx-q4`
2. `gemma-3-1b-it-onnx-q4-genai`
3. `gemma-3-4b-it-onnx-build-test`
4. `gemma-3-4b-it-onnx-cpu-int4`
5. `gemma-3-4b-it-onnx-int4`

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

## Execution Status

1. ONNX: 5/5 model switches OK, all tests PASS.
2. Ollama (`gemma3:4b`): all tests PASS.
3. vLLM (`gemma-3-4b-it`): all tests PASS.

## Latency Results (avg)

| Stack / Model | simple total | latency normal total | modes fast total | modes normal total | modes complex total |
|---|---:|---:|---:|---:|---:|
| `onnx / gemma-3-1b-it-onnx-q4` | `0.03s` | `0.12s` | `0.03s` | `0.15s` | `9.36s` |
| `onnx / gemma-3-1b-it-onnx-q4-genai` | `0.04s` | `0.26s` | `0.04s` | `0.17s` | `9.61s` |
| `onnx / gemma-3-4b-it-onnx-build-test` | `0.13s` | `0.18s` | `0.03s` | `0.17s` | `8.92s` |
| `onnx / gemma-3-4b-it-onnx-cpu-int4` | `0.03s` | `0.18s` | `0.03s` | `0.12s` | `9.07s` |
| `onnx / gemma-3-4b-it-onnx-int4` | `0.03s` | `0.24s` | `0.04s` | `0.16s` | `9.93s` |
| `ollama / gemma3:4b` | `1.85s` | `0.02s` | `0.29s` | `0.02s` | `21.19s` |
| `vllm / gemma-3-4b-it` | `0.06s` | `0.04s` | `0.06s` | `0.02s` | `2.63s` |

## Practical Takeaways

1. Lowest `complex` latency in this run: `vllm / gemma-3-4b-it` (`2.63s`).
2. ONNX variants are consistent in `complex` around `8.9s-9.9s`.
3. `ollama / gemma3:4b` is the slowest on `complex` (`21.19s`) but remains stable.
4. In this environment there is no Gemma 3B ONNX artifact; available ONNX set is 1B + 4B variants.

## Baseline Policy

1. Keep this file updated with latest complete run.
2. Add dated measurements directly in this file (no private-doc dependencies).
3. Preserve command + result transparency in each update.
