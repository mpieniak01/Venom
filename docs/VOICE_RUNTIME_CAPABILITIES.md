# Voice runtime and multimodal capabilities

Updated: 2026-10-26.

## Voice chat

The browser /voice screen records audio and sends it through /ws/audio.
Routing follows the active runtime and the selected model's capabilities:

- The automatic route with an empty decoder chain can select ollama_audio_llm_piper for Ollama models declaring audio.
- Text-only models use whisper_llm_piper.
- The separate multi_runtime engine retains its native audio pipeline.

Ollama receives a complete base64 WAV container in messages[].images, with an empty user text and a separate system transcription instruction. Audio is mono PCM16 at 16 kHz; browser sample rates are resampled before submission. A filename, raw PCM or an expected transcript is never substituted for recorded audio.

Native Ollama transcription then enters the same conversation/provider authorization flow as Whisper. Piper produces spoken output. Native audio input does not imply native audio output or permission to execute a command. Shared runtime admission remains enabled; when generation is occupied, Whisper can decode urgent voice commands.

The capability snapshot distinguishes declared metadata from a completed audio turn. A text-only health query cannot verify audio support. Session metadata records the chosen pipeline, transcription, response and timings. Failed or empty input must finish the UI state without inventing a transcript.

Polish recognition depends on the recording and model weights. Validate real recordings after a weight update; API acceptance alone is insufficient to establish transcription quality.

## Model roles and memory

Keep the everyday model lightweight so vision has VRAM available. The local profile retains Gemma2:2b and its adapter, Gemma4 for larger multimodal requests, and Chinese experimental alternatives. One LLM engine/generation runs at a time. Changing the active model does not authorize a second engine to load concurrently.

The neutral code_generation role defaults to qwen2.5-coder:3b. Configure FEEDBACK_LOOP_PRIMARY_MODEL and the comma-separated FEEDBACK_LOOP_FALLBACK_MODELS rather than binding a function to a model family. Resource limits are configured through FEEDBACK_LOOP_MIN_RAM_GB, FEEDBACK_LOOP_MIN_VRAM_MB and FEEDBACK_LOOP_MAX_CONTEXT. The historical OpenCodeInterpreter-Qwen2.5-7B alias remains readable for compatibility and does not require installing 7B.

Codestral, Gemma3 Ollama tags and Qwen2.5-Coder 7B are retired from this local catalog. This does not remove weights belonging to other engines or training adapters.

## Validation

Use tests/test_ollama_voice_input.py for WAV/payload/routing checks and the frontend voice-session timing tests for stage reporting. Operational acceptance additionally requires a saved speech recording through /ws/audio, a meaningful transcript and response, and a Piper audio result. Keep private recordings and raw session evidence out of Git.

Ollama's OpenAI-compatible /v1/chat/completions uses reasoning_effort (none disables thinking); the native /api/chat endpoint uses think. Keep these payload contracts separate. See https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx.

Native Ollama audio requires the automatic route (VOICE_ROUTE_PROFILE=auto), decoder profile auto/hybrid and an empty AUDIO_DECODER_CHAIN. The runtime_lokalny and venom-agent profiles retain Whisper; gemma4 targets the separate daemon. Declared model capabilities do not override an explicit chain or an invalid route contract.
