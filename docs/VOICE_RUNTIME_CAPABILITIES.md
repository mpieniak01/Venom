# Voice Runtime and Multimodal Capability Status

Status date: 2026-05-25
Scope: PR 205/205B voice loop, PR 207 runtime capability work

## Summary

Venom now has a working local voice loop, but the local multimodal runtime stack is not mature enough yet to replace the stable STT/TTS pipeline with native model audio.

Current production-safe path:

1. browser `/voice` records microphone input with push-to-talk,
2. backend `/ws/audio` receives audio chunks and stores the latest recording,
3. STT uses `faster-whisper`,
4. LLM reasoning uses the active local runtime/model,
5. TTS uses Piper when a voice model is available,
6. `/voice` shows the transcript, response, recording link, timings, quality metrics, and runtime snapshot.

Two operational answer tracks are now documented explicitly:

1. text-only fallback path: `whisper_llm_piper` - Whisper transcribes the audio, the active text model generates the answer from text, and Piper speaks the response,
2. Gemma4 native-audio path: `multi_runtime_piper` - Gemma4 receives audio directly, returns the transcription plus response text, and Piper speaks that response,
3. both tracks end in the same TTS layer, so spoken output stays consistent even when the answer source changes,
4. when the native path is not selected, the backend uses the text-only track and records the selected path in session metadata; native health-check warnings are diagnostic and do not force an automatic fallback before the native attempt.

### PR246 runtime truth contract

Current runtime contract for `/api/v1/audio/status`:

1. `multi_runtime` is the only native-audio route (`multi_runtime_piper`),
2. every other runtime (`ollama`, `vllm`, `onnx`, and cloud providers) is exposed as `whisper_llm_piper` for voice,
3. payload now carries `runtime_state` with four explicit dimensions:
   - `selected`: operator target runtime/model,
   - `active`: runtime/model currently active in backend,
   - `response`: runtime/model and pipeline of the latest voice response,
   - `switch`: async switch lifecycle state (`idle`, `switching`, `ready`, `failed`),
4. UI should treat `runtime_state` as canonical and use `runtime_snapshot`/`runtime_alignment` as diagnostics.

The current branch also treats the voice orb as a dedicated UI stack, not a loose widget:

1. `VoiceCommandCenter` owns the `/voice` screen state and wires the orb into the rest of the page,
2. `VoiceOrb3D` is the `react-three` rendering path for the orb when 3D visuals are enabled,
3. the CSS orb remains the safe fallback when WebGL is unavailable or 3D is disabled,
4. voice-specific smoke coverage lives in `web-next/tests/voice-orb.spec.ts`.

### Current STT baseline

The default speech-to-text model is `medium`.

Why:

1. after additional Polish tests with natural speech, it gives a clearly better recognition quality than `base`,
2. it remains acceptable for current local CPU latency targets,
3. `large-v3` remains a fallback when we need one more quality step.

Model guidance:

1. `medium` - current default and recommended baseline,
2. `base` - faster fallback when latency is critical and recognition quality remains acceptable,
3. `large-v3` - quality fallback when you want to trade more latency for one more quality check,
4. `large-v3-turbo` - available in newer faster-whisper releases, but treat it as a separate benchmark path before making it a default.

### Available Polish TTS voices

Current local Piper voices are stored in `data/models/piper` and can be selected by changing `TTS_MODEL_PATH`.

| Voice | File | Quality note |
| --- | --- | --- |
| `gosia` | `data/models/piper/pl_PL-gosia-medium.onnx` | default-medium, already in use |
| `darkman` | `data/models/piper/pl_PL-darkman-medium.onnx` | medium quality, already in use |
| `mc_speech` | `data/models/piper/pl_PL-mc_speech-medium.onnx` | medium quality, newly added for comparison |
| `mls_6892` | `data/models/piper/pl_PL-mls_6892-low.onnx` | low quality, useful as a weak baseline only |

Switching example:

```bash
TTS_MODEL_PATH=/home/ubuntu/venom/data/models/piper/pl_PL-mc_speech-medium.onnx
```

### Measured Polish samples

Cold-start CPU benchmarks collected on 2026-05-10:

| Session | Prompt | Model | Time | Result |
| --- | --- | ---: | ---: | --- |
| `20260510_135543_886758_125913349432592_57be75fe` | `Co to jest kwadrat?` | `base` | `2.509 s` | `Co to jest kwadrat?` |
| `20260510_135543_886758_125913349432592_57be75fe` | `Co to jest kwadrat?` | `medium` | `7.030 s` | `Co to jest kwadrat?` |
| `20260510_135543_886758_125913349432592_57be75fe` | `Co to jest kwadrat?` | `large-v3` | `11.318 s` | `Co to jest kwadrat?` |
| `20260510_140146_754253_125913368394688_6872f70f` | `Jakie jest największe dzieło Williama Shakespeare'a?` | `base` | `2.558 s` | `Jakie jest największy dzieło ulijama szekspira?` |
| `20260510_140146_754253_125913368394688_6872f70f` | `Jakie jest największe dzieło Williama Shakespeare'a?` | `medium` | `7.380 s` | `Jakie jest największe dzieło Williama Shakespeare'a?` |
| `20260510_140146_754253_125913368394688_6872f70f` | `Jakie jest największe dzieło Williama Shakespeare'a?` | `large-v3` | `12.095 s` | `Jakie jest największe dzieło Williama Szekspira?` |
| `20260510_140146_754253_125913368394688_6872f70f` | `Jakie jest największe dzieło Williama Shakespeare'a?` | `large-v3-turbo` | `34.875 s` | `Jakie jest największe dzieło Williama Szekspira?` |

Target direction:

1. keep the stable Whisper/Piper fallback,
2. expose runtime capabilities explicitly,
3. use native multimodal features only after active probe verification,
4. keep compatibility with legacy text-only models.

## Recent PR Findings

### PR 205 / 205B - local voice loop

Delivered state:

1. voice chat was moved out of the text chat layout into a dedicated `/voice` screen,
2. push-to-talk recording works through the browser and WebSocket audio channel,
3. backend records the audio and exposes the latest WAV download link,
4. STT is handled by `faster-whisper`,
5. TTS is handled by Piper,
6. UI exposes voice modes: standard, deep analysis, summary, action items,
7. chat history in the text cockpit is no longer blocked by the large voice control panel.

Operational conclusion:

1. this path is usable and should remain the default fallback,
2. audio quality and microphone capture issues were solved at the browser/recording pipeline level,
3. native model audio must not replace this path until it is measured and reversible.

### PR 207 - multimodal runtime capability contract

Delivered or in-progress state:

1. Ollama model metadata is normalized into a runtime capability snapshot,
2. `gemma4:latest` is detected as declaring `completion`, `vision`, `audio`, `tools`, and `thinking`,
3. `/api/v1/models/{model_name}/runtime-capabilities` exposes capability details,
4. `/api/v1/audio/status` includes `runtime_snapshot`,
5. `/voice` shows the active runtime snapshot more prominently,
6. older models remain supported by the legacy text + Whisper + Piper flow.

Current decision:

1. `audio` in Ollama metadata is not treated as proof of usable raw audio input,
2. `gemma4:latest` can improve reasoning after transcription, especially for deep analysis, if thinking probe is verified,
3. native audio stays behind explicit probe and experiment flags.

## Three Local Runtime Stacks

Venom has three local runtime paths. Capability detection must be runtime-neutral, not Ollama-specific.

| Runtime | Current role in Venom | Best fit | Current native audio status |
| --- | --- | --- | --- |
| `ollama` | Local daemon, model install UX, `/api/show` metadata | default local model runtime and compatibility baseline | metadata can declare `audio`, but REST audio input is not stable enough for production use |
| `vllm` | OpenAI-compatible server, benchmarked local stack | first candidate for native audio experiments and high-throughput multimodal serving | better candidate because vLLM documents OpenAI-style `input_audio` |
| `onnx` | In-process ONNX Runtime GenAI adapter | edge/CPU/DirectML/mobile, controlled footprint, possible ONNX Whisper/ASR path | useful for ASR/edge research, not first candidate for Gemma4 native audio |

## Runtime Capability Contract

The long-term contract should be provider-neutral:

```json
{
  "runtime_id": "ollama|vllm|onnx",
  "model": "active model name",
  "metadata_source": "api_show|openai_models|onnx_manifest|config",
  "probe_status": "verified|metadata_only|failed|unsupported",
  "capabilities": {
    "text_completion": "verified|metadata_only|fallback|unsupported",
    "vision_input": "verified|metadata_only|fallback|unsupported",
    "audio_input": "verified|metadata_only|fallback|unsupported",
    "audio_transcription": "verified|metadata_only|fallback|unsupported",
    "tool_calling": "verified|metadata_only|fallback|unsupported",
    "thinking": "verified|metadata_only|fallback|unsupported"
  },
  "fallbacks": {
    "stt": "faster_whisper|vllm_whisper|onnx_whisper",
    "tts": "piper",
    "tools": "policy_gate_required"
  }
}
```

Rules:

1. metadata is a discovery signal, not proof of production support,
2. active probes decide what the router may use,
3. UI must display the chosen path and fallback reason,
4. old text-only models are not errors,
5. every native feature must have a safe fallback.

## Native Audio Decision

Current production status: wait.

Reasoning:

1. Ollama exposes model capabilities through `/api/show`, but the stable public API does not currently provide an equivalent raw audio field as clear as `messages[].images` for vision.
2. vLLM documents OpenAI-compatible `input_audio` and offline `multi_modal_data.audio`, so it is the better next experiment path.
3. ONNX Runtime GenAI is valuable for edge and ASR experiments, but Gemma4 audio-native through ONNX is not the shortest path.
4. Polish STT quality and latency must be compared against the current `faster-whisper` path before any switch.

Acceptance criteria for native audio:

1. repeatable WAV fixture smoke test,
2. stable payload contract for the selected runtime,
3. acceptable Polish transcription quality,
4. measured timings not worse than current fallback for common commands,
5. full fallback to `faster-whisper` without UI failure,
6. runtime snapshot clearly says whether audio is `verified`, `metadata_only`, `fallback`, or `failed`.

## Recommended Next Steps

1. Keep PR 207 focused on the neutral capability contract and Ollama adapter.
2. Rename or generalize backend types from `OllamaRuntimeCapabilities` toward `RuntimeModelCapabilities` before adding more providers.
3. Add `VllmCapabilityProbe` as the first native-audio experiment path.
4. Add `RUN_VLLM_AUDIO_EXPERIMENT=1` smoke using a short WAV fixture and OpenAI-compatible `input_audio`.
5. Keep `RUN_OLLAMA_AUDIO_EXPERIMENT=1` only as a guarded experiment until Ollama exposes a stable audio transport.
6. Treat ONNX as a separate edge/ASR investigation, not as the first Gemma4 audio-native path.
7. Build PR 206 voice orb only on the stable runtime states emitted by PR 207.

## Gemma 4 Operational Runtime Strategy

Current operational direction for Gemma 4 is to keep the Transformers-based
daemon and treat the official Google checkpoints as the base runtime family.

Working assumptions:

1. base model: `google/gemma-4-E2B-it`,
2. optional drafter/assistant: `google/gemma-4-E2B-it-assistant`,
3. preferred runtime controls:
   - `enable_thinking` on/off,
   - `max_new_tokens`,
   - `cache_implementation="static"`,
   - multimodal context limits,
4. long-term optimization candidates:
   - speculative decoding via MTP assistant,
   - KV-cache compression research such as TurboQuant,
5. operational constraint:
   - keep VRAM hygiene strict so a second model never lingers in memory
     after reload or switch.

This means the next implementation step should focus on:

1. switching model variants from daemon/API/UX,
2. exposing thinking/context controls,
3. adding safe reload rules for the daemon,
4. exposing VRAM status and reload state to the UI,
5. keeping future quantized variants compatible with the same daemon rather
   than creating a second runtime stack.

## References

1. Ollama show model details: https://docs.ollama.com/api-reference/show-model-details
2. Ollama thinking: https://docs.ollama.com/capabilities/thinking
3. Ollama vision: https://docs.ollama.com/capabilities/vision
4. Ollama tool calling: https://docs.ollama.com/capabilities/tool-calling
5. Ollama audio input feature request: https://github.com/ollama/ollama/issues/11798
6. vLLM multimodal inputs: https://docs.vllm.ai/en/v0.20.0/features/multimodal_inputs/
7. vLLM tool calling: https://docs.vllm.ai/en/v0.14.0/features/tool_calling/
8. vLLM reasoning outputs: https://docs.vllm.ai/en/v0.8.2/features/reasoning_outputs.html
9. ONNX Runtime GenAI: https://github.com/microsoft/onnxruntime-genai
