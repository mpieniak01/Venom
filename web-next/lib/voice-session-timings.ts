export type VoiceSessionTimingMode = "native_audio" | "whisper_llm_piper" | "unknown";

export type VoiceSessionTimingInput = {
  voice_pipeline_mode?: string | null;
  pipeline_id?: string | null;
  decoder_source?: string | null;
  native_audio_ms?: number | null;
  timings_ms?: Record<string, number | null | undefined> | null;
};

export type VoiceTimingEntry = {
  key: string;
  label: string;
  value: number | null;
  accent?: boolean;
};

function coerce(value: string | null | undefined): string {
  return String(value ?? "").trim().toLowerCase();
}

export function inferVoiceSessionTimingMode(
  session?: VoiceSessionTimingInput | null,
): VoiceSessionTimingMode {
  const pipelineMode = coerce(session?.voice_pipeline_mode);
  if (pipelineMode === "native_multi_runtime") return "native_audio";
  if (pipelineMode === "whisper_llm_piper") return "whisper_llm_piper";

  const pipelineId = coerce(session?.pipeline_id);
  const decoderSource = coerce(session?.decoder_source);
  if (pipelineId === "multi_runtime_piper" || decoderSource === "multi_runtime") {
    return "native_audio";
  }
  if (pipelineId === "whisper_llm_piper" || decoderSource === "faster_whisper") {
    return "whisper_llm_piper";
  }
  if (session?.native_audio_ms != null) {
    return "native_audio";
  }
  return "unknown";
}

export function buildVoiceTimingEntries(
  timings?: Record<string, number | null | undefined> | null,
  session?: VoiceSessionTimingInput | null,
): VoiceTimingEntry[] {
  const mode = inferVoiceSessionTimingMode(session);
  const baseEntries: VoiceTimingEntry[] = [
    { key: "decode_ms", label: "Decode", value: timings?.decode_ms ?? null },
  ];
  const modeEntries: VoiceTimingEntry[] = mode === "native_audio"
    ? [{
      key: "native_audio_ms",
      label: "Native audio",
      value: session?.native_audio_ms ?? timings?.native_audio_ms ?? null,
      accent: true,
    }]
    : [
      { key: "stt_ms", label: "STT", value: timings?.stt_ms ?? null },
      { key: "llm_ms", label: "LLM", value: timings?.llm_ms ?? null },
    ];
  const tailEntries: VoiceTimingEntry[] = [{
    key: "tts_ms",
    label: "TTS",
    value: timings?.tts_ms ?? null,
  }, {
    key: "total_backend_ms",
    label: "Total",
    value: timings?.total_backend_ms ?? null,
    accent: true,
  }];
  return [...baseEntries, ...modeEntries, ...tailEntries];
}
