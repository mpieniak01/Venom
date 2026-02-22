# LLM Runtime 3-Stack Benchmark Baseline (2026-02-22)

Status: frozen baseline for comparison across `ollama` / `vllm` / `onnx`.

## Scope

This document is the canonical benchmark snapshot for:
1. Runtime activation status.
2. E2E path latency (`prompt -> response`) for `fast`, `normal`, `complex`.
3. Test command results and artifacts.

Related implementation task:
- `docs_dev/_to_do/168_onnxruntime_llm_trzeci_silnik_runtime_2026.md`

## Environment

1. Date: 2026-02-22
2. Runtime profile: `full`
3. Reference model class: Gemma 3
4. E2E test:
   - `tests/perf/test_latency_modes_e2e.py`
   - `tests/perf/test_llm_latency_e2e.py` (ONNX normal fallback)
5. Hardware reference:
   - GPU: NVIDIA GeForce RTX 3060, 12 GB VRAM, CUDA 13.1
   - CPU: Intel i5-14400F (16 logical threads)
   - RAM in Linux runtime: ~15 GiB
6. Host context: Windows 32 GB RAM + WSL2

Environment references:
- `docs/RUNTIME_PROFILES.md` (profile requirements + reference benchmark environment)
- `docs/WINDOWS_WSL_D_DRIVE_INSTALL.md` (WSL operational guidance)

## Command Matrix

| Step | Command | Result |
|---|---|---|
| Start E2E | `ALLOW_DEGRADED_START=1 make start-dev` | PASS |
| Switch profile | set `VENOM_RUNTIME_PROFILE=full` + restart | PASS |
| 3-stack tests (runtime/provider/model) | `pytest -q tests/test_llm_runtime_utils.py tests/test_llm_server_selection.py tests/test_llm_runtime_activation_api.py tests/test_control_plane_compatibility.py tests/test_generation_params_adapter.py tests/test_model_manager.py tests/test_onnx_llm_client.py tests/test_models_registry_ops_onnx.py` | `117 passed` |
| ONNX subset | `pytest -q ... -k onnx` | `19 passed, 98 deselected` |
| Ollama subset | `pytest -q ... -k ollama` | `2 passed, 115 deselected` |
| vLLM subset | `pytest -q ... -k vllm` | `4 passed, 113 deselected` |
| E2E modes (`ollama`) | `pytest -q -s tests/perf/test_latency_modes_e2e.py` | PASS |
| E2E modes (`vllm`) | `VENOM_LLM_MODEL=gemma-3-4b-it VENOM_LLM_REPEATS=2 pytest -q -s tests/perf/test_latency_modes_e2e.py` | PASS (`1 passed in 26.70s`) |
| E2E modes (`onnx`) | `pytest -q -s tests/perf/test_latency_modes_e2e.py` | FAIL (`503` on fast) |
| E2E normal-only (`onnx`) | `pytest -q -s tests/perf/test_llm_latency_e2e.py` | PASS |

## Runtime Activation Status

| Stack | Activation | Runtime status after activation | Notes |
|---|---|---|---|
| `ollama` | PASS (`start_result.ok=true`) | online | stable E2E run |
| `vllm` | PASS (`start_result.ok=true`, `exit_code=0`) | online (`/v1/models` ok, port `8001` listening) | retest after `vllm` install (`vllm==0.15.1`), active model `gemma-3-4b-it` |
| `onnx` | PASS (`in_process`) | online/ready (`genai_installed=true`, `model_path_exists=true`) | activation requires ONNX model consistent with `/api/v1/models` |

## E2E Prompt -> Response Latency

| Stack | Fast (`/api/v1/llm/simple/stream`) | Normal (`/api/v1/tasks` + stream) | Complex | Test status |
|---|---|---|---|---|
| `ollama` | first_token avg `0.04s`, total avg `9.11s`, min `7.18s`, max `11.05s` | first_token avg `0.02s`, total avg `0.02s`, min `0.02s`, max `0.02s` | timeout (`SSE > 25s`) | PASS (`1 passed`) |
| `vllm` | first_token avg `0.04s`, total avg `0.67s`, min `0.38s`, max `0.97s` | first_token avg `0.03s`, total avg `0.03s`, min `0.03s`, max `0.03s` | timeout (`SSE > 25s`, no `task_finished`) | PASS (`1 passed in 26.70s`) |
| `onnx` | FAIL: `HTTP 503` (`/api/v1/llm/simple/stream`) | normal-only fallback: first_token avg `0.02s`, total avg `0.02s`, min `0.02s`, max `0.02s` (`tests/perf/test_llm_latency_e2e.py`) | n/a (test stopped on fast) | FAIL for `test_latency_modes_e2e`, PASS for normal-only |

## Constraints and Interpretation

| Area | Observation | Impact |
|---|---|---|
| vLLM runtime | `vllm` installed (`.venv/bin/vllm`, `vllm==0.15.1`) and online on `:8001` | `vllm` E2E results are considered reliable (no fallback), but `complex` still times out with 25s limit |
| ONNX fast path | `503` on `/api/v1/llm/simple/stream` | no complete fast-vs-normal comparison in one test for ONNX |
| ONNX model naming | active model-path can fail modes validation; model value must match `/api/v1/models` | requires explicit ONNX alias (e.g. `gemma-3-4b-it-onnx`) |


## Baseline Policy

1. Treat this file as the reference benchmark baseline.
2. New measurements should be added as a new dated section or a new dated file.
3. Do not overwrite historical values without keeping change trace and artifact links.
