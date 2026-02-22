# LLM Runtime 3-Stack Benchmark Baseline (2026-02-22)

Status: zamrożony baseline porównawczy dla `ollama` / `vllm` / `onnx`.

## Zakres

Ten dokument jest kanoniczną migawką benchmarków dla:
1. Statusu aktywacji runtime.
2. Latencji ścieżki E2E (`prompt -> odpowiedź`) dla `fast`, `normal`, `complex`.
3. Wyników komend testowych i artefaktów.

Powiązane zadanie wdrożeniowe:
- `docs_dev/_to_do/168_onnxruntime_llm_trzeci_silnik_runtime_2026.md`

## Środowisko

1. Data: 2026-02-22
2. Profil runtime: `full`
3. Referencyjna klasa modelu: Gemma 3
4. Testy E2E:
   - `tests/perf/test_latency_modes_e2e.py`
   - `tests/perf/test_llm_latency_e2e.py` (fallback normal dla ONNX)
5. Referencja sprzętowa:
   - GPU: NVIDIA GeForce RTX 3060, 12 GB VRAM, CUDA 13.1
   - CPU: Intel i5-14400F (16 wątków logicznych)
   - RAM po stronie Linux runtime: ~15 GiB
6. Kontekst hosta: Windows 32 GB RAM + WSL2

Odnośniki środowiskowe:
- `docs/PL/RUNTIME_PROFILES.md` (wymagania profili + referencyjne środowisko benchmarkowe)
- `docs/PL/WINDOWS_WSL_D_DRIVE_INSTALL.md` (zasady operacyjne WSL)

## Macierz komend

| Krok | Komenda | Wynik |
|---|---|---|
| Start E2E | `ALLOW_DEGRADED_START=1 make start-dev` | PASS |
| Przełączenie profilu | ustawienie `VENOM_RUNTIME_PROFILE=full` + restart | PASS |
| Testy 3-stack (runtime/provider/model) | `pytest -q tests/test_llm_runtime_utils.py tests/test_llm_server_selection.py tests/test_llm_runtime_activation_api.py tests/test_control_plane_compatibility.py tests/test_generation_params_adapter.py tests/test_model_manager.py tests/test_onnx_llm_client.py tests/test_models_registry_ops_onnx.py` | `117 passed` |
| Podzbiór ONNX | `pytest -q ... -k onnx` | `19 passed, 98 deselected` |
| Podzbiór Ollama | `pytest -q ... -k ollama` | `2 passed, 115 deselected` |
| Podzbiór vLLM | `pytest -q ... -k vllm` | `4 passed, 113 deselected` |
| E2E modes (`ollama`) | `pytest -q -s tests/perf/test_latency_modes_e2e.py` | PASS |
| E2E modes (`vllm`) | `VENOM_LLM_MODEL=gemma-3-4b-it VENOM_LLM_REPEATS=2 pytest -q -s tests/perf/test_latency_modes_e2e.py` | PASS (`1 passed in 26.70s`) |
| E2E modes (`onnx`) | `pytest -q -s tests/perf/test_latency_modes_e2e.py` | FAIL (`503` na fast) |
| E2E normal-only (`onnx`) | `pytest -q -s tests/perf/test_llm_latency_e2e.py` | PASS |

## Status aktywacji runtime

| Stos | Aktywacja | Status runtime po aktywacji | Uwagi |
|---|---|---|---|
| `ollama` | PASS (`start_result.ok=true`) | online | stabilny przebieg E2E |
| `vllm` | PASS (`start_result.ok=true`, `exit_code=0`) | online (`/v1/models` odpowiada, port `8001` nasłuchuje) | retest po instalacji `vllm` (`vllm==0.15.1`), aktywny model `gemma-3-4b-it` |
| `onnx` | PASS (`in_process`) | online/ready (`genai_installed=true`, `model_path_exists=true`) | aktywacja wymaga modelu ONNX zgodnego z `/api/v1/models` |

## E2E Prompt -> Odpowiedź (latencja)

| Stos | Fast (`/api/v1/llm/simple/stream`) | Normal (`/api/v1/tasks` + stream) | Complex | Status testu |
|---|---|---|---|---|
| `ollama` | first_token avg `0.04s`, total avg `9.11s`, min `7.18s`, max `11.05s` | first_token avg `0.02s`, total avg `0.02s`, min `0.02s`, max `0.02s` | timeout (`SSE > 25s`) | PASS (`1 passed`) |
| `vllm` | first_token avg `0.04s`, total avg `0.67s`, min `0.38s`, max `0.97s` | first_token avg `0.03s`, total avg `0.03s`, min `0.03s`, max `0.03s` | timeout (`SSE > 25s`, brak `task_finished`) | PASS (`1 passed in 26.70s`) |
| `onnx` | FAIL: `HTTP 503` (`/api/v1/llm/simple/stream`) | fallback normal-only: first_token avg `0.02s`, total avg `0.02s`, min `0.02s`, max `0.02s` (`tests/perf/test_llm_latency_e2e.py`) | n/d (test zatrzymał się na fast) | FAIL dla `test_latency_modes_e2e`, PASS dla normal-only |

## Ograniczenia i interpretacja

| Obszar | Obserwacja | Wpływ |
|---|---|---|
| Runtime vLLM | `vllm` zainstalowany (`.venv/bin/vllm`, `vllm==0.15.1`) i online na `:8001` | wyniki E2E `vllm` są uznane za wiarygodne (bez fallbacku), ale `complex` dalej timeoutuje przy limicie 25s |
| ONNX fast path | `503` na `/api/v1/llm/simple/stream` | brak pełnego porównania fast-vs-normal w jednym teście dla ONNX |
| Nazewnictwo modelu ONNX | aktywny model-path może nie przejść walidacji testu modes; wartość modelu musi pasować do `/api/v1/models` | wymagany jawny alias ONNX (np. `gemma-3-4b-it-onnx`) |


## Polityka baseline

1. Traktuj ten plik jako referencyjny baseline benchmarkowy.
2. Nowe pomiary dopisuj jako nową sekcję z datą lub nowy plik datowany.
3. Nie nadpisuj historii bez śladu zmian i linków do artefaktów.
