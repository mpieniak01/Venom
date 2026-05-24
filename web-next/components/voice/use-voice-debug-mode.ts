"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { VoiceOrbState } from "@/components/voice/voice-orb";

type Translator = (key: string, variables?: Record<string, string | number>) => string;

export type VoiceDebugStepId =
  | "ready"
  | "recording"
  | "stt"
  | "thinking"
  | "tts"
  | "complete";

type PlaybackState = "idle" | "playing" | "muted" | "error";

export type VoiceDebugSnapshot = Readonly<{
  enabled: boolean;
  requested: boolean;
  hydrated: boolean;
  connected: boolean;
  isVoiceModeEnabled: boolean;
  recording: boolean;
  transcription: string;
  response: string;
  statusMessage: string;
  audioChunkCount: number;
  lastAudioSignal: string;
  processingStatus: string | null;
  playbackState: PlaybackState;
  currentStepId: VoiceDebugStepId;
  currentStepIndex: number;
  stepCount: number;
  restart: () => void;
  badgeLabel: string;
}>;

type VoiceDebugScenarioStep = Readonly<{
  id: VoiceDebugStepId;
  state: VoiceOrbState;
  recording: boolean;
  transcription: string;
  response: string;
  statusMessage: string;
  processingStatus: string | null;
  playbackState: PlaybackState;
  lastAudioSignal: string;
  audioChunkCount: number;
}>;

type VoiceDebugConfig = Readonly<{
  enabled: boolean;
  stepMs: number;
  loop: boolean;
  transcript: string;
  response: string;
  sequence: VoiceDebugStepId[];
}>;

const DEFAULT_SEQUENCE: VoiceDebugStepId[] = [
  "ready",
  "recording",
  "stt",
  "thinking",
  "tts",
  "complete",
];

const parseBooleanValue = (value: string | null | undefined): boolean | null => {
  if (!value) return null;
  const normalized = value.trim().toLowerCase();
  if (normalized === "1" || normalized === "true" || normalized === "on" || normalized === "yes") return true;
  if (normalized === "0" || normalized === "false" || normalized === "off" || normalized === "no") return false;
  return null;
};

const parsePositiveInteger = (value: string | null | undefined, fallback: number): number => {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

const normalizeSequenceItem = (value: string): VoiceDebugStepId | null => {
  const normalized = value.trim().toLowerCase();
  if (
    normalized === "ready" ||
    normalized === "recording" ||
    normalized === "stt" ||
    normalized === "thinking" ||
    normalized === "tts" ||
    normalized === "complete"
  ) {
    return normalized;
  }
  return null;
};

export function parseVoiceDebugEnabled(urlSearch?: string | null): boolean {
  if (!urlSearch) return false;
  const params = new URLSearchParams(urlSearch);
  if (!params.has("debug")) return false;
  const override = parseBooleanValue(params.get("debug"));
  return override ?? true;
}

function resolveVoiceDebugConfig(urlSearch?: string | null): VoiceDebugConfig {
  const stepMsFallback = parsePositiveInteger(process.env.NEXT_PUBLIC_VOICE_DEBUG_STEP_MS, 3000);
  const loopFallback = parseBooleanValue(process.env.NEXT_PUBLIC_VOICE_DEBUG_LOOP) ?? true;
  const transcriptFallback =
    process.env.NEXT_PUBLIC_VOICE_DEBUG_TRANSCRIPT?.trim() ||
    "Powiedz mi prosze, co to jest kwadrat?";
  const responseFallback =
    process.env.NEXT_PUBLIC_VOICE_DEBUG_RESPONSE?.trim() ||
    "Kwadrat to figura geometryczna z czterema rownymi bokami i czterema katami prostymi.";
  const sequenceFallback =
    process.env.NEXT_PUBLIC_VOICE_DEBUG_SEQUENCE?.split(",")
      .map(normalizeSequenceItem)
      .filter((item): item is VoiceDebugStepId => item !== null) || DEFAULT_SEQUENCE;

  if (!urlSearch) {
    return {
      enabled: false,
      stepMs: stepMsFallback,
      loop: loopFallback,
      transcript: transcriptFallback,
      response: responseFallback,
      sequence: sequenceFallback.length > 0 ? sequenceFallback : DEFAULT_SEQUENCE,
    };
  }

  const params = new URLSearchParams(urlSearch);
  const enabled = parseVoiceDebugEnabled(urlSearch);
  const stepMs = parsePositiveInteger(params.get("debugStepMs"), stepMsFallback);
  const loop = parseBooleanValue(params.get("debugLoop")) ?? loopFallback;
  const transcript = params.get("debugTranscript")?.trim() || transcriptFallback;
  const response = params.get("debugResponse")?.trim() || responseFallback;
  const sequence =
    params
      .get("debugSequence")
      ?.split(",")
      .map(normalizeSequenceItem)
      .filter((item): item is VoiceDebugStepId => item !== null) || sequenceFallback;

  return {
    enabled,
    stepMs,
    loop,
    transcript,
    response,
    sequence: sequence.length > 0 ? sequence : DEFAULT_SEQUENCE,
  };
}

const buildVoiceDebugSteps = (
  t: Translator,
  config: Pick<VoiceDebugConfig, "sequence" | "transcript" | "response">,
): VoiceDebugScenarioStep[] =>
  config.sequence.map((id) => {
    switch (id) {
      case "recording":
        return {
          id,
          state: "recording",
          recording: true,
          transcription: "",
          response: "",
          statusMessage: t("voice.status.recordingStarted"),
          processingStatus: null,
          playbackState: "idle",
          lastAudioSignal: "recording:started",
          audioChunkCount: 4,
        };
      case "stt":
        return {
          id,
          state: "stt",
          recording: false,
          transcription: config.transcript,
          response: "",
          statusMessage: t("voice.status.processing", { status: "stt" }),
          processingStatus: "stt",
          playbackState: "idle",
          lastAudioSignal: "stt:ok",
          audioChunkCount: 0,
        };
      case "thinking":
        return {
          id,
          state: "thinking",
          recording: false,
          transcription: config.transcript,
          response: config.response,
          statusMessage: t("voice.status.processing", { status: "thinking" }),
          processingStatus: "thinking",
          playbackState: "idle",
          lastAudioSignal: "response:text",
          audioChunkCount: 0,
        };
      case "tts":
        return {
          id,
          state: "tts",
          recording: false,
          transcription: config.transcript,
          response: config.response,
          statusMessage: t("voice.status.playbackPlaying"),
          processingStatus: null,
          playbackState: "playing",
          lastAudioSignal: "tts:audio",
          audioChunkCount: 0,
        };
      case "complete":
        return {
          id,
          state: "complete",
          recording: false,
          transcription: config.transcript,
          response: config.response,
          statusMessage: t("voice.status.complete"),
          processingStatus: null,
          playbackState: "idle",
          lastAudioSignal: "complete",
          audioChunkCount: 0,
        };
      case "ready":
      default:
        return {
          id: "ready",
          state: "ready",
          recording: false,
          transcription: "",
          response: "",
          statusMessage: t("voice.status.channelReady"),
          processingStatus: null,
          playbackState: "idle",
          lastAudioSignal: "idle",
          audioChunkCount: 0,
        };
    }
  });

export function useVoiceDebugMode(t: Translator): VoiceDebugSnapshot {
  const readLocationSearch = () =>
    globalThis.location === undefined ? "" : globalThis.location.search;
  const [hydrated, setHydrated] = useState(globalThis.location !== undefined);
  const [urlSearch, setUrlSearch] = useState(() => readLocationSearch());
  const requested = globalThis.location !== undefined && parseVoiceDebugEnabled(readLocationSearch());

  useEffect(() => {
    const syncLocation = () => {
      const nextSearch = readLocationSearch();
      setUrlSearch((current) => (current === nextSearch ? current : nextSearch));
      setHydrated(true);
    };
    syncLocation();
    globalThis.addEventListener?.("popstate", syncLocation);
    globalThis.addEventListener?.("hashchange", syncLocation);
    return () => {
      globalThis.removeEventListener?.("popstate", syncLocation);
      globalThis.removeEventListener?.("hashchange", syncLocation);
    };
  }, []);

  const config = useMemo(
    () => resolveVoiceDebugConfig(hydrated ? urlSearch : ""),
    [hydrated, urlSearch],
  );
  const steps = useMemo(() => buildVoiceDebugSteps(t, config), [config, t]);
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    if (!config.enabled || steps.length <= 1) return undefined;
    const timeoutId = globalThis.setTimeout(() => {
      setStepIndex((current) => {
        const next = current + 1;
        if (next < steps.length) return next;
        return config.loop ? 0 : current;
      });
    }, config.stepMs);
    return () => globalThis.clearTimeout(timeoutId);
  }, [config.enabled, config.loop, config.stepMs, stepIndex, steps.length]);

  const restart = useCallback(() => {
    setStepIndex(0);
  }, []);

  const current = steps[Math.min(stepIndex, Math.max(steps.length - 1, 0))] ?? steps[0];

  if (!config.enabled || !current) {
    return {
      enabled: false,
      requested,
      hydrated,
      connected: false,
      isVoiceModeEnabled: false,
      recording: false,
      transcription: "",
      response: "",
      statusMessage: "",
      audioChunkCount: 0,
      lastAudioSignal: "idle",
      processingStatus: null,
      playbackState: "idle",
      currentStepId: "ready",
      currentStepIndex: 0,
      stepCount: steps.length,
      restart,
      badgeLabel: "",
    };
  }

  return {
    enabled: true,
    requested,
    hydrated,
    connected: true,
    isVoiceModeEnabled: true,
    recording: current.recording,
    transcription: current.transcription,
    response: current.response,
    statusMessage: current.statusMessage,
    audioChunkCount: current.audioChunkCount,
    lastAudioSignal: current.lastAudioSignal,
    processingStatus: current.processingStatus,
    playbackState: current.playbackState,
    currentStepId: current.id,
    currentStepIndex: stepIndex,
    stepCount: steps.length,
    restart,
    badgeLabel: `DEBUG DRY RUN · ${current.id} · ${stepIndex + 1}/${steps.length}`,
  };
}
