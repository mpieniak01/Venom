"use client";

import type { VoiceOrbState } from "@/components/voice/voice-orb";

export function isIdleVoiceOrbState(state: VoiceOrbState): boolean {
  return state === "ready" || state === "offline";
}

export function isActiveVoiceOrbState(state: VoiceOrbState): boolean {
  return (
    state === "recording" ||
    state === "stt" ||
    state === "thinking" ||
    state === "tts" ||
    state === "complete" ||
    state === "error"
  );
}

export function shouldTrackOrbMetrics(enabled: boolean, state: VoiceOrbState): boolean {
  return enabled && !isIdleVoiceOrbState(state);
}

export function shouldRenderOrbMetricsBars(
  enabled: boolean,
  state: VoiceOrbState,
  reducedMotion: boolean,
): boolean {
  return enabled && !reducedMotion && !isIdleVoiceOrbState(state);
}

export function shouldUseOrbCalmIdle(
  state: VoiceOrbState,
  pageVisible: boolean,
  activeWindow: boolean,
): boolean {
  return !pageVisible || (!activeWindow && isIdleVoiceOrbState(state));
}

export function resolveVisualVoiceOrbState(state: VoiceOrbState, transcription: string): VoiceOrbState {
  if (state !== "thinking") return state;
  return transcription.trim() ? "thinking" : "stt";
}
