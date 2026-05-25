# Voice Single-pass Trace Contract

## Scope
This contract defines the end-to-end evidence record for voice requests handled by `multi_runtime / google/gemma-4-E2B-it`.

## Required fields per session
1. `request_id`: unique request identifier returned by `/v1/respond`.
2. `trace_id`: same value as `request_id` (compatibility alias).
3. `audio_hash`: SHA-256 of the WAV payload sent to runtime.
4. `transcription`: transcription returned from the same `/v1/respond` call.
5. `transcription_used_for_generation`: transcription string used for final answer generation.
6. `response_text`: final text response returned from the same `/v1/respond` call.
7. `decoder_selected`: first decoder selected from route profile/chain.
8. `decoder_effective`: decoder that actually processed the request.
9. `decoder_fallback_reason`: fallback reason if `decoder_effective != decoder_selected`.
10. `trace_inconsistent`: boolean set when transcription differs from transcription used for generation.

## Single-pass invariant
For one voice request there is exactly one `/v1/respond` call used as source of truth for both:
1. transcription,
2. final response.

No secondary `/audio/transcribe` call is allowed for the same request in the `gemma4` route.

## Route profiles
1. `gemma4`: requires `gemma_native` as first decoder.
2. `runtime_lokalny`: forces `faster_whisper` path.
3. `venom-agent`: forces `faster_whisper` path with agent execution.
4. `chat_tekstowy`: disables voice audio pipeline.
5. `auto`: runtime-driven selection.

## Operator controls
Profiles are configurable without code edits via:
1. `GET/POST /api/v1/audio/routes/profile`,
2. Voice sidebar controls in `web-next`,
3. `make voice-route-profile-show` and `make voice-route-profile-set`.
