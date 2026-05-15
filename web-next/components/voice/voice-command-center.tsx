"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  Dispatch,
  MutableRefObject,
  PointerEvent as ReactPointerEvent,
  RefObject,
  SetStateAction,
} from "react";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getAudioWsUrl } from "@/lib/env";
import { useTranslation } from "@/lib/i18n";
import type { VoiceOrbState } from "@/components/voice/voice-orb";
import { useOrbEffectsConfig } from "@/components/voice/use-orb-effects-config";
import { useOrbMetrics } from "@/components/voice/use-orb-metrics";
import { OrbZone } from "@/components/voice/orb-zone";
import { DevDiagnosticsDrawer } from "@/components/voice/dev-diagnostics-drawer";
import {
  shouldTrackOrbMetrics,
  shouldUseOrbCalmIdle,
  resolveVisualVoiceOrbState,
} from "@/components/voice/orb-visibility";
import {
  applyOrbDiagnosticProfile,
  resolveDiagnosticOrbState,
  useVoiceRenderDiagnostics,
} from "@/components/voice/voice-render-diagnostics";
import { usePageVisibility } from "@/components/voice/use-page-visibility";
import { useOrbActivityWindow } from "@/components/voice/use-orb-activity-window";
import { useVoiceDebugMode } from "@/components/voice/use-voice-debug-mode";
import type { VoiceDebugSnapshot } from "@/components/voice/use-voice-debug-mode";
import {
  RuntimeDiagnosticsPanel,
  type RuntimeSummaryItem,
} from "@/components/runtime/runtime-diagnostics-panel";

export type AudioStatus = {
  enabled: boolean;
  connected_clients: number;
  active_recordings: number;
  vad_threshold?: number;
  silence_duration?: number;
  operator_ready?: boolean;
  stt_backend?: string | null;
  stt_ready?: boolean;
  whisper_model_size?: string | null;
  whisper_device?: string | null;
  tts_backend?: string | null;
  tts_ready?: boolean;
  tts_model_path?: string | null;
  tts_fallback?: boolean | null;
  dependencies?: Record<string, boolean>;
  latest_voice_session?: VoiceSessionDiagnostics | null;
  message?: string;
  runtime_snapshot?: {
    runtime_id?: string | null;
    provider?: string | null;
    model_name?: string | null;
    endpoint?: string | null;
    config_hash?: string | null;
    runtime_capabilities?: {
      compatibility_profile?: string | null;
      probe_status?: string | null;
      capabilities?: Record<string, boolean | string | null | undefined>;
      probes?: Record<string, { status?: string | null; reason?: string | null }>;
      fallbacks?: Record<string, string | null | undefined>;
    } | null;
    assistant_models?: string[] | null;
    voice_pipeline?: {
      profile?: string | null;
      stt?: string | null;
      reasoning?: string | null;
      reasoning_summary?: string | null;
      emotion?: string | null;
      tools?: string | null;
      vision?: string | null;
      tts?: string | null;
      notes?: string[] | null;
    } | null;
    latest_voice_session?: VoiceSessionDiagnostics | null;
    error?: string | null;
  } | null;
};

type VoiceRuntimeInfo = {
  stt_model?: string | null;
  stt_device?: string | null;
  stt_compute_type?: string | null;
  llm_service_id?: string | null;
  llm_model?: string | null;
  tts_model_path?: string | null;
  tts_fallback?: boolean | null;
  tts_sample_rate?: number | null;
};

type VoiceSessionDiagnostics = {
  session_id: string;
  created_at?: string | null;
  duration_sec?: number | null;
  sample_rate?: number | null;
  input_format?: string | null;
  mime_type?: string | null;
  voice_mode?: string | null;
  gain_applied?: number | null;
  peak_before_normalization?: number | null;
  peak_after_normalization?: number | null;
  rms_before_normalization?: number | null;
  rms_after_normalization?: number | null;
  timings_ms?: Record<string, number | null | undefined>;
  runtime?: VoiceRuntimeInfo;
  reasoning_summary_enabled?: boolean | null;
  reasoning_summary_status?: "disabled" | "summary" | "raw_available" | null;
  reasoning_summary?: string | null;
  raw_thinking_available?: boolean | null;
  emotion_detection_enabled?: boolean | null;
  emotion_response_style_enabled?: boolean | null;
  emotion_source?: string | null;
  emotion_label?: string | null;
  emotion_confidence?: number | null;
  transcription?: string;
  response_text?: string;
  download_url?: string | null;
  pipeline_id?: string | null;
  execution_trace?: string[] | null;
  selected_policy?: string | null;
  selected_image_strategy?: string | null;
  retrieval_used?: boolean | null;
  retrieval_context_items?: number | null;
  retrieval_route?: string | null;
  assistant_used?: boolean | null;
  economy_mode_activated?: boolean | null;
  degradation_reasons?: string[] | null;
  component_snapshot?: Array<{
    component_id?: string | null;
    health?: string | null;
    backend?: string | null;
    available?: boolean | null;
  }> | null;
  audio_runtime_provider?: string | null;
  audio_runtime_model?: string | null;
  audio_input_status?: string | null;
  decoder_source?: string | null;
  fallback_reason?: string | null;
  native_audio_ms?: number | null;
  runtime_log_path?: string | null;
};

type PlaybackState = "idle" | "playing" | "muted" | "error";
type TtsModelOption = {
  id: string;
  label: string;
  path: string;
};

type Translator = (key: string, variables?: Record<string, string | number>) => string;

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}

type BrowserWindowLike = Window & {
  AudioContext?: typeof AudioContext;
  webkitAudioContext?: typeof AudioContext;
};

let secureRandomFallbackCounter = 0;

const nextSecureRandomFallbackInt = () => {
  secureRandomFallbackCounter += 1;
  const perfNow = typeof performance === "undefined" ? 0 : Math.floor(performance.now());
  return Date.now() + perfNow + secureRandomFallbackCounter;
};

const secureRandomInt = (maxExclusive: number): number => {
  if (maxExclusive <= 0) return 0;
  if (typeof crypto !== "undefined" && "getRandomValues" in crypto) {
    const maxUint32 = 2 ** 32;
    const unbiasedLimit = maxUint32 - (maxUint32 % maxExclusive);
    const bytes = new Uint32Array(1);
    let value = maxUint32;
    while (value >= unbiasedLimit) {
      crypto.getRandomValues(bytes);
      value = bytes[0] ?? maxUint32;
    }
    return value % maxExclusive;
  }
  return nextSecureRandomFallbackInt() % maxExclusive;
};

const toPrimitiveString = (value: unknown): string | null => {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value);
  }
  return null;
};

const decodeBase64Pcm16 = (base64Audio: string): Int16Array => {
  const binary = globalThis.atob(base64Audio);
  const bytes = Uint8Array.from(binary, (char) => char.codePointAt(0) ?? 0);
  return new Int16Array(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
};

const formatTimingSeconds = (milliseconds?: number | null): string | null => {
  if (typeof milliseconds !== "number" || !Number.isFinite(milliseconds)) return null;
  return `${(milliseconds / 1000).toFixed(2)}s`;
};

const buildDebugAudioStatus = (recording: boolean): AudioStatus => ({
  enabled: true,
  connected_clients: 1,
  active_recordings: recording ? 1 : 0,
  operator_ready: true,
  stt_ready: true,
  whisper_model_size: "debug",
  whisper_device: "dry-run",
  stt_backend: "debug",
  tts_backend: "debug",
  tts_ready: true,
  tts_fallback: false,
  dependencies: { debug: true },
  message: "Debug dry run",
  latest_voice_session: null,
  runtime_snapshot: {
    runtime_id: "debug://voice-dry-run",
    provider: "debug",
    model_name: "debug-dry-run",
    endpoint: "debug://offline",
    config_hash: "debug-dry-run",
    runtime_capabilities: {
      compatibility_profile: "debug_dry_run",
      probe_status: "verified",
      capabilities: { audio: true, text: true },
      probes: {
        dry_run: { status: "verified", reason: "Visual dry run active" },
      },
      fallbacks: {},
    },
    voice_pipeline: {
      profile: "debug_dry_run",
      stt: "debug",
      reasoning: "debug",
      reasoning_summary: "disabled",
      emotion: "disabled",
      tts: "debug",
      notes: ["No backend services", "No models", "Visual dry run only"],
    },
  },
});

const getBrowserWindow = (): BrowserWindowLike | undefined =>
  globalThis as unknown as BrowserWindowLike;

const TIMING_STAGES: Array<{ key: string; label: string; accent?: boolean }> = [
  { key: "decode_ms", label: "Decode" },
  { key: "stt_ms", label: "STT" },
  { key: "llm_ms", label: "LLM" },
  { key: "tts_ms", label: "TTS" },
  { key: "total_backend_ms", label: "Total", accent: true },
];

type TimingStripProps = Readonly<{
  timings?: Record<string, number | null | undefined> | null;
}>;

function TimingStrip({ timings }: TimingStripProps) {
  const hasAny = Boolean(timings) && TIMING_STAGES.some((s) => timings[s.key] != null);
  return (
    <div className="grid grid-cols-5 gap-1.5 text-xs">
      {TIMING_STAGES.map(({ key, label, accent }) => {
        const raw = timings?.[key];
        const val = formatTimingSeconds(typeof raw === "number" ? raw : null);
        return (
          <div
            key={key}
            className={`rounded-xl p-2 text-center ${
              accent
                ? "border border-white/10 bg-white/[0.06]"
                : "rounded-xl box-muted"
            } ${hasAny ? "" : "opacity-40"}`}
          >
            <p className="text-caption leading-none">{label}</p>
            <p className={`mt-1 font-mono font-semibold leading-none ${accent ? "text-white" : "text-zinc-200"}`}>
              {val ?? "—"}
            </p>
          </div>
        );
      })}
    </div>
  );
}

const getRecordingButtonClass = (
  audioEnabled: boolean,
  isVoiceModeEnabled: boolean,
  recording: boolean,
  connected: boolean,
): string => {
  if (audioEnabled && isVoiceModeEnabled) {
    if (recording) {
      return "border-rose-400/60 bg-rose-500/10 text-rose-100";
    }
    if (connected) {
      return "border-emerald-400/40 bg-emerald-500/10 text-white";
    }
    return "border-white/10 bg-white/5 text-zinc-300";
  }
  return "border-white/10 bg-white/5 text-zinc-500";
};

const getRecordingButtonLabel = (
  t: Translator,
  recording: boolean,
  isVoiceModeEnabled: boolean,
): string => {
  if (recording) {
    return t("voice.controls.recording");
  }
  if (isVoiceModeEnabled) {
    return t("voice.controls.pushToTalk");
  }
  return t("voice.controls.textChat");
};

const getAudioContextCtor = (activeWindow?: BrowserWindowLike | undefined): typeof AudioContext | null =>
  activeWindow?.AudioContext || activeWindow?.webkitAudioContext || null;

const isWebSocketOpen = (ws: WebSocket | null | undefined): ws is WebSocket =>
  ws?.readyState === WebSocket.OPEN;

const buildReconnectDelay = (attempt: number): number =>
  Math.min(30000, 1000 * 2 ** attempt) + secureRandomInt(500);

const closeAudioContext = (ctx: AudioContext | null | undefined) => {
  if (!ctx) return;
  ctx.close().catch(() => undefined);
};

const createPlaybackContext = (
  AudioContextCtor: typeof AudioContext,
  sourceRef: RefObject<MediaElementAudioSourceNode | null>,
): AudioContext | null => {
  try {
    const context = new AudioContextCtor();
    context.onstatechange = () => {
      if (context.state === "suspended" && sourceRef.current) {
        context.resume().catch(() => undefined);
      }
    };
    return context;
  } catch {
    return null;
  }
};

const tryResumeAudioContext = async (ctx: AudioContext): Promise<boolean> => {
  try {
    await ctx.resume();
    return true;
  } catch {
    return false;
  }
};

const syncVoiceModeSelection = (
  deps: Pick<
    VoiceControlDeps,
    | "audioEnabled"
    | "connected"
    | "t"
    | "voiceModePreset"
    | "lastVoiceModeSentRef"
    | "wsRef"
    | "setStatusMessage"
  >,
) => {
  const { audioEnabled, connected, t, voiceModePreset, lastVoiceModeSentRef, wsRef, setStatusMessage } = deps;
  if (audioEnabled && connected) {
    const mode = voiceModePreset || "standard";
    if (lastVoiceModeSentRef.current !== mode) {
      const ws = wsRef.current;
      if (isWebSocketOpen(ws)) {
        ws.send(
          JSON.stringify({
            command: "voice_mode",
            mode,
          }),
        );
        lastVoiceModeSentRef.current = mode;
        setStatusMessage(`${t("voice.controls.voiceChat")}: ${t(VOICE_MODE_TITLE_KEYS[mode])}`);
      }
    }
  }
};

type VoiceControlDeps = {
  t: Translator;
  audioEnabled: boolean;
  isVoiceModeEnabled: boolean;
  connected?: boolean;
  wsRef: RefObject<WebSocket | null>;
  audioContextRef?: RefObject<AudioContext | null>;
  ttsAudioContextRef: RefObject<AudioContext | null>;
  ttsSourceRef?: RefObject<AudioBufferSourceNode | null>;
  sourceNodeRef?: RefObject<MediaStreamAudioSourceNode | null>;
  analyserRef?: RefObject<AnalyserNode | null>;
  mediaRecorderRef?: RefObject<MediaRecorder | null>;
  mediaStreamRef?: RefObject<MediaStream | null>;
  recordingRef: RefObject<boolean>;
  recordingStartPendingRef: RefObject<boolean>;
  stopRequestedRef: RefObject<boolean>;
  reconnectAttemptsRef: RefObject<number>;
  reconnectTimeoutRef: RefObject<number | null>;
  lastVoiceModeSentRef: RefObject<string | null>;
  voiceModePreset?: VoiceModePreset | null;
  setConnected: (value: boolean) => void;
  setRecording: (value: boolean) => void;
  setStatusMessage: (value: string | null) => void;
  setAudioChunkCount: (value: number | ((current: number) => number)) => void;
  setLastAudioSignal: (value: string) => void;
  releaseRecordingResources: () => void;
  releaseAudioResources: () => void;
  releasePlaybackResources: () => void;
  refreshAudioStatus: () => Promise<void>;
  handleAudioMessage: (payload: Record<string, unknown>) => void;
  sendControlMessage: (payload: Record<string, unknown>) => boolean;
  getMediaRecorderMimeType: () => string;
  ensurePlaybackContext: () => Promise<AudioContext | null>;
  stopRecording: () => void;
  activeWindow?: BrowserWindowLike;
};

type VoiceSocketDeps = Readonly<{
  t: Translator;
  wsRef: RefObject<WebSocket | null>;
  reconnectAttemptsRef: RefObject<number>;
  reconnectTimeoutRef: RefObject<number | null>;
  lastVoiceModeSentRef: RefObject<string | null>;
  setConnected: (value: boolean) => void;
  setStatusMessage: (value: string | null) => void;
  setLastAudioSignal: (value: string) => void;
  refreshAudioStatus: () => Promise<void>;
  handleAudioMessage: (payload: Record<string, unknown>) => void;
  releaseAudioResources: () => void;
  releasePlaybackResources: () => void;
  ttsAudioContextRef: RefObject<AudioContext | null>;
}>;

type VoiceCaptureEnvironmentDeps = Readonly<{
  activeWindow?: BrowserWindowLike;
  audioContextRef: RefObject<AudioContext | null>;
  getMediaRecorderMimeType: () => string;
  mediaStreamRef: RefObject<MediaStream | null>;
  sourceNodeRef: RefObject<MediaStreamAudioSourceNode | null>;
  analyserRef: RefObject<AnalyserNode | null>;
  mediaRecorderRef: RefObject<MediaRecorder | null>;
  ensurePlaybackContext: () => Promise<AudioContext | null>;
}>;

type VoiceCaptureDeps = Readonly<{
  t: Translator;
  audioEnabled: boolean;
  isVoiceModeEnabled: boolean;
  wsRef: RefObject<WebSocket | null>;
  audioContextRef: RefObject<AudioContext | null>;
  sourceNodeRef: RefObject<MediaStreamAudioSourceNode | null>;
  analyserRef: RefObject<AnalyserNode | null>;
  mediaRecorderRef: RefObject<MediaRecorder | null>;
  mediaStreamRef: RefObject<MediaStream | null>;
  recordingRef: RefObject<boolean>;
  recordingStartPendingRef: RefObject<boolean>;
  stopRequestedRef: RefObject<boolean>;
  setRecording: (value: boolean) => void;
  setStatusMessage: (value: string | null) => void;
  setAudioChunkCount: (value: number | ((current: number) => number)) => void;
  setLastAudioSignal: (value: string) => void;
  releaseRecordingResources: () => void;
  releaseAudioResources: () => void;
  sendControlMessage: (payload: Record<string, unknown>) => boolean;
  getMediaRecorderMimeType: () => string;
  ensurePlaybackContext: () => Promise<AudioContext | null>;
  stopRecording: () => void;
  activeWindow?: BrowserWindowLike;
}>;

const handleVoiceSocketOpen = (
  deps: Pick<
    VoiceControlDeps,
    | "t"
    | "setConnected"
    | "reconnectAttemptsRef"
    | "lastVoiceModeSentRef"
    | "setStatusMessage"
    | "setLastAudioSignal"
    | "refreshAudioStatus"
  >,
) => {
  const {
    t,
    setConnected,
    reconnectAttemptsRef,
    lastVoiceModeSentRef,
    setStatusMessage,
    setLastAudioSignal,
    refreshAudioStatus,
  } = deps;
  setConnected(true);
  reconnectAttemptsRef.current = 0;
  lastVoiceModeSentRef.current = null;
  setStatusMessage(t("voice.status.channelReady"));
  setLastAudioSignal("ws:open");
  refreshAudioStatus().catch(() => undefined);
};

const handleVoiceSocketMessage = (
  deps: Pick<VoiceControlDeps, "handleAudioMessage">,
  event: MessageEvent<string>,
) => {
  try {
    deps.handleAudioMessage(JSON.parse(event.data));
  } catch {
    // Ignore malformed payloads to avoid console noise.
  }
};

const handleVoiceSocketClose = (
  deps: Pick<
    VoiceControlDeps,
    | "t"
    | "setConnected"
    | "reconnectAttemptsRef"
    | "reconnectTimeoutRef"
    | "lastVoiceModeSentRef"
    | "setStatusMessage"
  >,
  destroyed: () => boolean,
  reconnect: () => void,
) => {
  const {
    t,
    setConnected,
    reconnectAttemptsRef,
    reconnectTimeoutRef,
    lastVoiceModeSentRef,
    setStatusMessage,
  } = deps;
  setConnected(false);
  lastVoiceModeSentRef.current = null;
  if (destroyed()) {
    return;
  }
  const attempt = reconnectAttemptsRef.current;
  const delay = buildReconnectDelay(attempt);
  reconnectAttemptsRef.current = Math.min(attempt + 1, 6);
  setStatusMessage(buildVoiceChannelOfflineMessage(t, Math.ceil(delay / 1000)));
  if (reconnectTimeoutRef.current) {
    getBrowserWindow()?.clearTimeout(reconnectTimeoutRef.current);
  }
  reconnectTimeoutRef.current = getBrowserWindow()?.setTimeout(reconnect, delay) ?? null;
};

const handleVoiceSocketError = (
  deps: Pick<VoiceControlDeps, "t" | "setStatusMessage" | "setLastAudioSignal">,
) => {
  deps.setStatusMessage(deps.t("voice.status.channelOffline"));
  deps.setLastAudioSignal("ws:error");
};

const bindRecordingReleaseListeners = (recording: boolean, stopRecording: () => void) => {
  if (!recording) {
    return undefined;
  }
  const stopOnRelease = () => {
    stopRecording();
  };
  const browserWindow = getBrowserWindow();
  browserWindow?.addEventListener("pointerup", stopOnRelease);
  browserWindow?.addEventListener("mouseup", stopOnRelease);
  browserWindow?.addEventListener("touchend", stopOnRelease);
  browserWindow?.addEventListener("touchcancel", stopOnRelease);
  browserWindow?.addEventListener("blur", stopOnRelease);
  return () => {
    browserWindow?.removeEventListener("pointerup", stopOnRelease);
    browserWindow?.removeEventListener("mouseup", stopOnRelease);
    browserWindow?.removeEventListener("touchend", stopOnRelease);
    browserWindow?.removeEventListener("touchcancel", stopOnRelease);
    browserWindow?.removeEventListener("blur", stopOnRelease);
  };
};

const bindVoiceConnectionLifecycle = (
  audioEnabled: boolean,
  t: Translator,
  setConnected: (value: boolean) => void,
  setStatusMessage: (value: string | null) => void,
  setIsVoiceModeEnabled: (value: boolean) => void,
  connect: () => (() => void) | undefined,
) => {
  if (!audioEnabled) {
    setConnected(false);
    setStatusMessage(t("voice.status.channelDisabled"));
    setIsVoiceModeEnabled(false);
    return undefined;
  }
  return connect();
};

const buildVoiceChannelOfflineMessage = (t: Translator, delaySeconds: number): string =>
  t("voice.status.channelRetrying", { seconds: delaySeconds });

const getPlaybackStateLabel = (
  t: Translator,
  playbackState: PlaybackState,
  ttsMuted: boolean,
): string => {
  if (ttsMuted) {
    return t("voice.status.playbackMutedShort");
  }
  if (playbackState === "playing") {
    return t("voice.status.playbackPlayingShort");
  }
  if (playbackState === "error") {
    return t("voice.status.playbackErrorShort");
  }
  if (playbackState === "muted") {
    return t("voice.status.playbackMutedShort");
  }
  return t("voice.status.playbackIdleShort");
};

const deriveOrbState = (
  connected: boolean,
  recording: boolean,
  processingStatus: string | null,
  playbackState: PlaybackState,
  lastAudioSignal: string,
): VoiceOrbState => {
  if (!connected) return "offline";
  if (recording) return "recording";
  if (processingStatus) {
    const s = processingStatus.toLowerCase();
    if (s.includes("stt") || s.includes("transcri") || s.includes("whisper")) return "stt";
    if (s.includes("tts") || s.includes("speak")) return "tts";
    return "thinking";
  }
  if (playbackState === "playing") return "tts";
  if (playbackState === "error") return "error";
  if (lastAudioSignal === "complete") return "complete";
  return "ready";
};

const COMPLETE_SETTLE_MS = 1200;

const handleVoiceRecordingStarted = (
  t: Translator,
  setStatusMessage: (value: string | null) => void,
  setLastAudioSignal: (value: string) => void,
  setProcessingStatus?: (value: string | null) => void,
) => {
  setStatusMessage(t("voice.status.recordingStarted"));
  setLastAudioSignal("recording:started");
  setProcessingStatus?.(null);
};

const handleVoiceProcessing = (
  t: Translator,
  data: Record<string, unknown>,
  setStatusMessage: (value: string | null) => void,
  setLastAudioSignal: (value: string) => void,
  setProcessingStatus?: (value: string | null) => void,
) => {
  const status = toPrimitiveString(data.status) ?? "unknown";
  setStatusMessage(t("voice.status.processing", { status }));
  setLastAudioSignal(`processing:${status}`);
  setProcessingStatus?.(status);
};

const handleVoiceTranscript = (
  t: Translator,
  data: Record<string, unknown>,
  onTranscriptReady: ((text: string) => void) | undefined,
  setTranscription: (value: string) => void,
  setStatusMessage: (value: string | null) => void,
  setLastAudioSignal: (value: string) => void,
) => {
  const transcript = toPrimitiveString(data.text) ?? t("voice.status.noTranscript");
  setTranscription(transcript);
  if (transcript.trim()) {
    onTranscriptReady?.(transcript.trim());
    setStatusMessage(t("voice.status.transcriptionInserted"));
    setLastAudioSignal("stt:ok");
  }
};

const handleVoiceResponseText = (
  data: Record<string, unknown>,
  setResponse: (value: string) => void,
  setLastAudioSignal: (value: string) => void,
) => {
  setResponse(toPrimitiveString(data.text) ?? "");
  setLastAudioSignal("response:text");
};

const handleVoiceAudioResponse = (
  data: Record<string, unknown>,
  playAudioResponse: (base64Audio: string, sampleRate: number) => Promise<void>,
  setLastAudioSignal: (value: string) => void,
) => {
  const audio = toPrimitiveString(data.audio) ?? "";
  const sampleRate = Number(data.sample_rate ?? 22050);
  if (audio) {
    playAudioResponse(audio, sampleRate).catch(() => undefined);
    setLastAudioSignal("tts:audio");
  }
};

const handleVoiceCompletion = (
  t: Translator,
  setStatusMessage: (value: string | null) => void,
  setLastAudioSignal: (value: string) => void,
  setProcessingStatus?: (value: string | null) => void,
) => {
  setStatusMessage(t("voice.status.complete"));
  setLastAudioSignal("complete");
  setProcessingStatus?.(null);
};

const handleVoiceError = (
  t: Translator,
  data: Record<string, unknown>,
  setPlaybackState: (value: PlaybackState) => void,
  setStatusMessage: (value: string | null) => void,
  setLastAudioSignal: (value: string) => void,
) => {
  setPlaybackState("error");
  setStatusMessage(toPrimitiveString(data.message) ?? t("voice.status.channelError"));
  setLastAudioSignal("error");
};

const connectVoiceSocket = (deps: VoiceSocketDeps): (() => void) => {
  const {
    t,
    wsRef,
    reconnectAttemptsRef,
    reconnectTimeoutRef,
    lastVoiceModeSentRef,
    setConnected,
    setStatusMessage,
    setLastAudioSignal,
    refreshAudioStatus,
    handleAudioMessage,
    releaseAudioResources,
    releasePlaybackResources,
    ttsAudioContextRef,
  } = deps;

  let destroyed = false;
  const connect = () => {
    if (destroyed) return;
    const ws = new WebSocket(getAudioWsUrl());
    wsRef.current = ws;
    setStatusMessage(t("voice.status.channelConnecting"));
    ws.onopen = () =>
      handleVoiceSocketOpen({
        t,
        setConnected,
        reconnectAttemptsRef,
        lastVoiceModeSentRef,
        setStatusMessage,
        setLastAudioSignal,
        refreshAudioStatus,
      });
    ws.onmessage = (event) => handleVoiceSocketMessage({ handleAudioMessage }, event);
    ws.onerror = () => handleVoiceSocketError({ t, setStatusMessage, setLastAudioSignal });
    ws.onclose = () =>
      handleVoiceSocketClose(
        {
          t,
          setConnected,
          reconnectAttemptsRef,
          reconnectTimeoutRef,
          lastVoiceModeSentRef,
          setStatusMessage,
        },
        () => destroyed,
        connect,
      );
  };

  connect();
  refreshAudioStatus().catch(() => undefined);
  return () => {
    destroyed = true;
    if (reconnectTimeoutRef.current) {
      getBrowserWindow()?.clearTimeout(reconnectTimeoutRef.current);
    }
    wsRef.current?.close();
    releaseAudioResources();
    releasePlaybackResources();
    ttsAudioContextRef.current?.close().catch(() => {
      // Ignore close errors on unmount.
    });
    ttsAudioContextRef.current = null;
  };
};

type VoiceCaptureEnvironment = Readonly<{
  mediaStream: MediaStream;
  audioContext: AudioContext;
  source: MediaStreamAudioSourceNode;
  analyser: AnalyserNode;
  recorder: MediaRecorder;
  mimeType: string;
}>;

const createVoiceCaptureEnvironment = async (
  deps: VoiceCaptureEnvironmentDeps,
): Promise<VoiceCaptureEnvironment | null> => {
  const existingMediaStream = deps.mediaStreamRef.current;
  const existingAudioContext = deps.audioContextRef?.current;
  const existingSource = deps.sourceNodeRef?.current;
  const existingAnalyser = deps.analyserRef?.current;
  if (existingMediaStream && existingAudioContext && existingSource && existingAnalyser) {
    const mimeType = deps.getMediaRecorderMimeType();
    const recorder = new MediaRecorder(existingMediaStream, mimeType ? { mimeType } : undefined);
    deps.mediaRecorderRef.current = recorder;
    return {
      mediaStream: existingMediaStream,
      audioContext: existingAudioContext,
      source: existingSource,
      analyser: existingAnalyser,
      recorder,
      mimeType,
    };
  }

  const mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
  const audioContextCtor = getAudioContextCtor(deps.activeWindow);
  if (!audioContextCtor || typeof MediaRecorder === "undefined") {
    mediaStream.getTracks().forEach((track) => track.stop());
    return null;
  }
  await deps.ensurePlaybackContext().catch(() => undefined);
  const audioContext = new audioContextCtor();
  const source = audioContext.createMediaStreamSource(mediaStream);
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 2048;
  source.connect(analyser);
  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }
  const mimeType = deps.getMediaRecorderMimeType();
  const recorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : undefined);
  deps.mediaStreamRef.current = mediaStream;
  if (deps.audioContextRef) {
    deps.audioContextRef.current = audioContext;
  }
  if (deps.sourceNodeRef) {
    deps.sourceNodeRef.current = source;
  }
  if (deps.analyserRef) {
    deps.analyserRef.current = analyser;
  }
  deps.mediaRecorderRef.current = recorder;
  return { mediaStream, audioContext, source, analyser, recorder, mimeType };
};

const sendRecordingStartMessages = (
  deps: Pick<VoiceControlDeps, "sendControlMessage" | "setStatusMessage" | "setAudioChunkCount" | "setLastAudioSignal">,
  audioContext: AudioContext,
  recorder: MediaRecorder,
  mimeType: string,
): boolean => {
  deps.setAudioChunkCount(0);
  deps.setLastAudioSignal("recording:start");
  const audioConfigured = deps.sendControlMessage({
    command: "audio_config",
    sample_rate: audioContext.sampleRate,
    channels: 1,
    format: "mediarecorder",
    mime_type: recorder.mimeType || mimeType,
  });
  const recordingStarted = deps.sendControlMessage({
    command: "start_recording",
    format: "mediarecorder",
    mime_type: recorder.mimeType || mimeType,
    sample_rate: audioContext.sampleRate,
    channels: 1,
  });
  return audioConfigured && recordingStarted;
};

const getVoiceCaptureStartError = (
  t: Translator,
  audioEnabled: boolean,
  isVoiceModeEnabled: boolean,
  isConnected: boolean,
): string | null => {
  if (!isVoiceModeEnabled) {
    return t("voice.controls.textChat");
  }
  if (!audioEnabled) {
    return t("voice.status.channelDisabled");
  }
  if (!isConnected) {
    return t("voice.status.channelOffline");
  }
  return null;
};

const attachRecordingStreamHandlers = (
  recorder: MediaRecorder,
  wsRef: RefObject<WebSocket | null>,
  setAudioChunkCount: (value: number | ((current: number) => number)) => void,
  setLastAudioSignal: (value: string) => void,
  sendControlMessage: (payload: Record<string, unknown>) => boolean,
  releaseRecordingResources: () => void,
) => {
  recorder.ondataavailable = (event) => {
    const ws = wsRef.current;
    if (event.data.size <= 0 || !isWebSocketOpen(ws)) {
      return;
    }
    ws.send(event.data);
    setAudioChunkCount((current) => current + 1);
    setLastAudioSignal(`media:${event.data.size}B`);
  };
  recorder.onstop = () => {
    sendControlMessage({ command: "stop_recording" });
    releaseRecordingResources();
  };
};

const startVoiceCapture = async (deps: VoiceCaptureDeps): Promise<void> => {
  const {
    t,
    audioEnabled,
    isVoiceModeEnabled,
    wsRef,
    recordingRef,
    recordingStartPendingRef,
    stopRequestedRef,
    audioContextRef,
    sourceNodeRef,
    analyserRef,
    mediaRecorderRef,
    mediaStreamRef,
    setRecording,
    setAudioChunkCount,
    setLastAudioSignal,
    releaseRecordingResources,
    setStatusMessage,
    releaseAudioResources,
    sendControlMessage,
    ensurePlaybackContext,
    getMediaRecorderMimeType,
    stopRecording,
    activeWindow,
  } = deps;

  const startError = getVoiceCaptureStartError(
    t,
    audioEnabled,
    isVoiceModeEnabled,
    Boolean(wsRef.current),
  );
  if (startError) {
    setStatusMessage(startError);
    return;
  }
  if (recordingRef.current || recordingStartPendingRef.current) {
    return;
  }

  recordingStartPendingRef.current = true;
  stopRequestedRef.current = false;

  try {
    const environment = await createVoiceCaptureEnvironment({
      activeWindow,
      audioContextRef,
      getMediaRecorderMimeType,
      mediaStreamRef,
      sourceNodeRef,
      analyserRef,
      mediaRecorderRef,
      ensurePlaybackContext,
    });
    if (!environment) {
      setStatusMessage(t("voice.status.browserAudioContextMissing"));
      return;
    }

    attachRecordingStreamHandlers(
      environment.recorder,
      wsRef,
      setAudioChunkCount,
      setLastAudioSignal,
      sendControlMessage,
      releaseRecordingResources,
    );

    recordingRef.current = true;
    setRecording(true);
    setStatusMessage(t("voice.controls.recording"));
    if (
      !sendRecordingStartMessages(
        { sendControlMessage, setStatusMessage, setAudioChunkCount, setLastAudioSignal },
        environment.audioContext,
        environment.recorder,
        environment.mimeType,
      )
    ) {
      releaseAudioResources();
      return;
    }
    environment.recorder.start(100);
    getBrowserWindow()?.setTimeout(() => {
      if (environment.recorder.state === "recording") {
        try {
          environment.recorder.requestData();
        } catch {
          // Ignore requestData races on fast stop/start.
        }
      }
    }, 120);
  } catch (error) {
    console.error("recording error", error);
    releaseAudioResources();
    setStatusMessage(t("voice.status.recordingFailed"));
  } finally {
    recordingStartPendingRef.current = false;
  }

  if (stopRequestedRef.current && recordingRef.current) {
    stopRecording();
  }
};

export type VoiceModePreset = "standard" | "deep_analysis" | "summary" | "action_items";
export type VoiceStatusUpdate = Pick<AudioStatus,
  | "enabled" | "stt_ready" | "tts_ready" | "tts_fallback"
  | "whisper_model_size" | "stt_backend" | "tts_backend"
  | "vad_threshold" | "dependencies" | "runtime_snapshot"
  | "latest_voice_session"
>;

const VOICE_MODE_TITLE_KEYS: Record<VoiceModePreset, string> = {
  standard: "voice.modes.standard.title",
  deep_analysis: "voice.modes.deepAnalysis.title",
  summary: "voice.modes.summary.title",
  action_items: "voice.modes.actionItems.title",
};

function getTtsModelStatusText(
  t: Translator,
  debugDryRunActive: boolean,
  ttsModelChanging: boolean,
): string {
  if (debugDryRunActive) {
    return "Debug dry run";
  }
  if (ttsModelChanging) {
    return t("voice.controls.ttsVoiceChanging");
  }
  return t("voice.controls.ttsVoiceAuto");
}

function useVoiceCommandCenterDebugBootstrap(params: {
  debugDryRunRequested: boolean;
  debugRecording: boolean;
  onStatusUpdate?: (status: VoiceStatusUpdate | null) => void;
  refreshAudioStatus: () => Promise<void>;
  refreshTtsModelOptions: () => Promise<void>;
}) {
  const {
    debugDryRunRequested,
    debugRecording,
    onStatusUpdate,
    refreshAudioStatus,
    refreshTtsModelOptions,
  } = params;

  useEffect(() => {
    if (!debugDryRunRequested) return;
    onStatusUpdate?.(buildDebugAudioStatus(debugRecording));
    refreshAudioStatus().catch(() => undefined);
    refreshTtsModelOptions().catch(() => undefined);
  }, [debugDryRunRequested, debugRecording, onStatusUpdate, refreshAudioStatus, refreshTtsModelOptions]);
}

function useVoiceCommandCenterCompleteReset(params: {
  debugDryRunRequested: boolean;
  lastAudioSignal: string;
  recording: boolean;
  processingStatus: string | null;
  playbackState: PlaybackState;
  setLastAudioSignal: Dispatch<SetStateAction<string>>;
}) {
  const {
    debugDryRunRequested,
    lastAudioSignal,
    recording,
    processingStatus,
    playbackState,
    setLastAudioSignal,
  } = params;

  useEffect(() => {
    if (debugDryRunRequested) {
      return;
    }
    if (
      lastAudioSignal !== "complete" ||
      recording ||
      processingStatus !== null ||
      playbackState !== "idle"
    ) {
      return;
    }

    const timeoutId = globalThis.setTimeout(() => {
      setLastAudioSignal((current) => (current === "complete" ? "idle" : current));
    }, COMPLETE_SETTLE_MS);

    return () => globalThis.clearTimeout(timeoutId);
  }, [debugDryRunRequested, lastAudioSignal, playbackState, processingStatus, recording, setLastAudioSignal]);
}

function useVoiceCommandCenterTtsModelRefresh(params: {
  debugDryRunRequested: boolean;
  refreshAudioStatus: () => Promise<void>;
  refreshTtsModelOptions: () => Promise<void>;
}) {
  const { debugDryRunRequested, refreshAudioStatus, refreshTtsModelOptions } = params;

  useEffect(() => {
    if (debugDryRunRequested) {
      refreshAudioStatus().catch(() => undefined);
      refreshTtsModelOptions().catch(() => undefined);
      return;
    }
    refreshTtsModelOptions().catch(() => undefined);
  }, [debugDryRunRequested, refreshAudioStatus, refreshTtsModelOptions]);
}

function buildTtsModelUpdateStatus(params: {
  t: Translator;
  debugDryRunRequested: boolean;
  modelPath: string;
  setSelectedTtsModelPath: Dispatch<SetStateAction<string>>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
  setTtsModelChanging: Dispatch<SetStateAction<boolean>>;
  refreshAudioStatus: () => Promise<void>;
  refreshTtsModelOptions: () => Promise<void>;
  releasePlaybackResources: () => void;
  closeCurrentWs: () => void;
}) {
  const {
    t,
    debugDryRunRequested,
    modelPath,
    setSelectedTtsModelPath,
    setStatusMessage,
    setTtsModelChanging,
    refreshAudioStatus,
    refreshTtsModelOptions,
    releasePlaybackResources,
    closeCurrentWs,
  } = params;
  return async () => {
    if (!modelPath) return;
    if (debugDryRunRequested) {
      setSelectedTtsModelPath(modelPath);
      setStatusMessage(t("voice.status.debugDryRunNoRuntimeSwitch"));
      return;
    }
    setTtsModelChanging(true);
    try {
      const response = await fetch("/api/v1/audio/tts/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modelPath }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = (await response.json()) as {
        effective_tts_model_path?: string;
      };
      const effectiveModelPath =
        typeof data.effective_tts_model_path === "string"
          ? data.effective_tts_model_path
          : modelPath;
      setSelectedTtsModelPath(effectiveModelPath);
      setStatusMessage(
        effectiveModelPath === modelPath
          ? t("voice.status.ttsVoiceUpdated")
          : t("voice.status.ttsVoiceUpdateFailed"),
      );
      if (effectiveModelPath === modelPath) {
        releasePlaybackResources();
        closeCurrentWs();
      }
      await refreshAudioStatus();
      await refreshTtsModelOptions();
    } catch {
      setStatusMessage(t("voice.status.ttsVoiceUpdateFailed"));
    } finally {
      setTtsModelChanging(false);
    }
  };
}

function createSendControlMessage(params: {
  wsRef: RefObject<WebSocket | null>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
  t: Translator;
}) {
  const { wsRef, setStatusMessage, t } = params;
  return (payload: Record<string, unknown>): boolean => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
      return true;
    }
    setStatusMessage(t("voice.status.channelOffline"));
    return false;
  };
}

function createStopRecordingHandler(params: {
  debugDryRunRequested: boolean;
  debugMode: VoiceDebugSnapshot;
  recordingStartPendingRef: MutableRefObject<boolean>;
  stopRequestedRef: MutableRefObject<boolean>;
  recordingRef: MutableRefObject<boolean>;
  mediaRecorderRef: RefObject<MediaRecorder | null>;
  setRecording: Dispatch<SetStateAction<boolean>>;
  setLastAudioSignal: Dispatch<SetStateAction<string>>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
  sendControlMessage: (payload: Record<string, unknown>) => boolean;
  releaseAudioResources: () => void;
  t: Translator;
}) {
  const {
    debugDryRunRequested,
    debugMode,
    recordingStartPendingRef,
    stopRequestedRef,
    recordingRef,
    mediaRecorderRef,
    setRecording,
    setLastAudioSignal,
    setStatusMessage,
    sendControlMessage,
    releaseAudioResources,
    t,
  } = params;
  return () => {
    if (debugDryRunRequested) {
      debugMode.restart();
      return;
    }
    if (recordingStartPendingRef.current) {
      stopRequestedRef.current = true;
      setStatusMessage(t("voice.controls.recording"));
      return;
    }
    if (!recordingRef.current) {
      return;
    }
    recordingRef.current = false;
    stopRequestedRef.current = false;
    setRecording(false);
    setLastAudioSignal("recording:stop");
    setStatusMessage(t("voice.status.recordingEnded"));
    const recorder = mediaRecorderRef.current;
    if (recorder?.state === "recording") {
      recorder.stop();
    } else {
      sendControlMessage({ command: "stop_recording" });
      releaseAudioResources();
    }
  };
}

function createStartRecordingHandler(params: {
  debugDryRunRequested: boolean;
  debugMode: VoiceDebugSnapshot;
  t: Translator;
  audioEnabled: boolean;
  isVoiceModeEnabled: boolean;
  wsRef: RefObject<WebSocket | null>;
  audioContextRef: RefObject<AudioContext | null>;
  sourceNodeRef: RefObject<MediaStreamAudioSourceNode | null>;
  analyserRef: RefObject<AnalyserNode | null>;
  mediaRecorderRef: RefObject<MediaRecorder | null>;
  mediaStreamRef: RefObject<MediaStream | null>;
  recordingRef: MutableRefObject<boolean>;
  recordingStartPendingRef: MutableRefObject<boolean>;
  stopRequestedRef: MutableRefObject<boolean>;
  setRecording: Dispatch<SetStateAction<boolean>>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
  setAudioChunkCount: Dispatch<SetStateAction<number>>;
  setLastAudioSignal: Dispatch<SetStateAction<string>>;
  releaseRecordingResources: () => void;
  releaseAudioResources: () => void;
  sendControlMessage: (payload: Record<string, unknown>) => boolean;
  getMediaRecorderMimeType: () => string;
  ensurePlaybackContext: () => Promise<AudioContext | null>;
  stopRecording: () => void;
  activeWindow: Window | null;
}) {
  const {
    debugDryRunRequested,
    debugMode,
    t,
    audioEnabled,
    isVoiceModeEnabled,
    wsRef,
    audioContextRef,
    sourceNodeRef,
    analyserRef,
    mediaRecorderRef,
    mediaStreamRef,
    recordingRef,
    recordingStartPendingRef,
    stopRequestedRef,
    setRecording,
    setStatusMessage,
    setAudioChunkCount,
    setLastAudioSignal,
    releaseRecordingResources,
    releaseAudioResources,
    sendControlMessage,
    getMediaRecorderMimeType,
    ensurePlaybackContext,
    stopRecording,
    activeWindow,
  } = params;
  return async () => {
    if (debugDryRunRequested) {
      debugMode.restart();
      return;
    }
    return startVoiceCapture({
      t,
      audioEnabled,
      isVoiceModeEnabled,
      wsRef,
      audioContextRef,
      sourceNodeRef,
      analyserRef,
      mediaRecorderRef,
      mediaStreamRef,
      recordingRef,
      recordingStartPendingRef,
      stopRequestedRef,
      setRecording,
      setStatusMessage,
      setAudioChunkCount,
      setLastAudioSignal,
      releaseRecordingResources,
      releaseAudioResources,
      sendControlMessage,
      getMediaRecorderMimeType,
      ensurePlaybackContext,
      stopRecording,
      activeWindow,
    });
  };
}

function createRefreshAudioStatusHandler(params: {
  t: Translator;
  debugDryRunRequested: boolean;
  debugRecording: boolean;
  setAudioStatus: Dispatch<SetStateAction<AudioStatus | null>>;
}) {
  const { t, debugDryRunRequested, debugRecording, setAudioStatus } = params;
  return async () => {
    if (debugDryRunRequested) {
      setAudioStatus(buildDebugAudioStatus(debugRecording));
      return;
    }
    try {
      const res = await fetch("/api/v1/audio/status");
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = (await res.json()) as AudioStatus;
      setAudioStatus(data);
    } catch {
      setAudioStatus({
        enabled: false,
        connected_clients: 0,
        active_recordings: 0,
        message: t("voice.status.noData"),
      });
    }
  };
}

function createRefreshTtsModelOptionsHandler(params: {
  debugDryRunRequested: boolean;
  setTtsModelOptions: Dispatch<SetStateAction<TtsModelOption[]>>;
  setSelectedTtsModelPath: Dispatch<SetStateAction<string>>;
}) {
  const { debugDryRunRequested, setTtsModelOptions, setSelectedTtsModelPath } = params;
  return async () => {
    if (debugDryRunRequested) {
      const option: TtsModelOption = {
        id: "debug-dry-run",
        label: "Debug Dry Run",
        path: "debug://dry-run",
      };
      setTtsModelOptions([option]);
      setSelectedTtsModelPath(option.path);
      return;
    }
    try {
      const response = await fetch("/api/v1/audio/tts/models");
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = (await response.json()) as {
        models?: TtsModelOption[];
        current_model_path?: string;
      };
      setTtsModelOptions(Array.isArray(data.models) ? data.models : []);
      if (typeof data.current_model_path === "string") {
        setSelectedTtsModelPath(data.current_model_path);
      }
    } catch {
      setTtsModelOptions([]);
    }
  };
}

function createReleasePlaybackResourcesHandler(params: {
  ttsSourceRef: MutableRefObject<AudioBufferSourceNode | null>;
  ttsAnalyserRef: MutableRefObject<AnalyserNode | null>;
}) {
  const { ttsSourceRef, ttsAnalyserRef } = params;
  return () => {
    const src = ttsSourceRef.current;
    const analyser = ttsAnalyserRef.current;
    ttsSourceRef.current = null;
    ttsAnalyserRef.current = null;
    try { src?.stop(); } catch { /* ignore races with natural end */ }
    try { src?.disconnect(); } catch { /* ignore */ }
    try { analyser?.disconnect(); } catch { /* ignore */ }
  };
}

function createGetMediaRecorderMimeTypeHandler() {
  return () => {
    if (typeof MediaRecorder === "undefined") return "";
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/ogg",
    ];
    return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? "";
  };
}

function createEnsurePlaybackContextHandler(params: {
  ttsAudioContextRef: MutableRefObject<AudioContext | null>;
  ttsSourceRef: MutableRefObject<AudioBufferSourceNode | null>;
}) {
  const { ttsAudioContextRef, ttsSourceRef } = params;
  return async () => {
    const browserWindow = getBrowserWindow();
    if (!browserWindow) return null;
    const AudioContextCtor = getAudioContextCtor(browserWindow);
    if (!AudioContextCtor) return null;

    let ctx = ttsAudioContextRef.current;

    if (!ctx || ctx.state === "closed") {
      ctx = createPlaybackContext(AudioContextCtor, ttsSourceRef);
      if (ctx) ttsAudioContextRef.current = ctx;
      return ctx;
    }

    if (ctx.state === "suspended" && !(await tryResumeAudioContext(ctx))) {
      closeAudioContext(ctx);
      ctx = createPlaybackContext(AudioContextCtor, ttsSourceRef);
      if (ctx) ttsAudioContextRef.current = ctx;
      return ctx;
    }

    if (ctx.state !== "running") {
      closeAudioContext(ctx);
      ctx = createPlaybackContext(AudioContextCtor, ttsSourceRef);
      if (ctx) ttsAudioContextRef.current = ctx;
    }

    return ctx;
  };
}

function createPlayAudioResponseHandler(params: {
  ensurePlaybackContext: () => Promise<AudioContext | null>;
  releasePlaybackResources: () => void;
  t: Translator;
  ttsMuted: boolean;
  setPlaybackState: Dispatch<SetStateAction<PlaybackState>>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
  setLastAudioSignal: Dispatch<SetStateAction<string>>;
  setHasReplayAudio: Dispatch<SetStateAction<boolean>>;
  lastAudioResponseRef: MutableRefObject<{ audio: string; sampleRate: number } | null>;
  ttsAudioContextRef: MutableRefObject<AudioContext | null>;
  ttsSourceRef: MutableRefObject<AudioBufferSourceNode | null>;
  ttsAnalyserRef: MutableRefObject<AnalyserNode | null>;
}) {
  const {
    ensurePlaybackContext,
    releasePlaybackResources,
    t,
    ttsMuted,
    setPlaybackState,
    setStatusMessage,
    setLastAudioSignal,
    setHasReplayAudio,
    lastAudioResponseRef,
    ttsAudioContextRef,
    ttsSourceRef,
    ttsAnalyserRef,
  } = params;
  return async (base64Audio: string, sampleRate: number) => {
    lastAudioResponseRef.current = { audio: base64Audio, sampleRate };
    setHasReplayAudio(true);
    if (ttsMuted) {
      setPlaybackState("muted");
      setStatusMessage(t("voice.status.playbackMuted"));
      return;
    }
    const browserWindow = getBrowserWindow();
    if (browserWindow) {
      const ctx = await ensurePlaybackContext();
      if (!ctx) {
        setPlaybackState("error");
        setStatusMessage(t("voice.status.playbackNoAudioContext"));
        return;
      }
      const pcm16 = decodeBase64Pcm16(base64Audio);
      if (pcm16.length === 0) {
        setPlaybackState("error");
        setStatusMessage(t("voice.status.playbackEmptyBuffer"));
        return;
      }
      releasePlaybackResources();
      const audioBuffer = ctx.createBuffer(1, pcm16.length, sampleRate || 22050);
      const channelData = audioBuffer.getChannelData(0);
      for (let index = 0; index < pcm16.length; index += 1) {
        channelData[index] = (pcm16[index] ?? 0) / 32768;
      }
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      const ttsAnalyser = ctx.createAnalyser();
      ttsAnalyser.fftSize = 512;
      source.connect(ttsAnalyser);
      ttsAnalyser.connect(ctx.destination);
      ttsAnalyserRef.current = ttsAnalyser;
      source.onended = () => {
        try { source.disconnect(); } catch { /* ignore */ }
        try { ttsAnalyser.disconnect(); } catch { /* ignore */ }
        if (ttsSourceRef.current === source) {
          setPlaybackState("idle");
          ttsSourceRef.current = null;
          ttsAnalyserRef.current = null;
        }
      };
      ttsSourceRef.current = source;
      setPlaybackState("playing");
      setStatusMessage(t("voice.status.playbackPlaying"));
      source.start();
      return;
    }
    setPlaybackState("error");
    setStatusMessage(t("voice.status.playbackNoAudioContext"));
    setLastAudioSignal("error");
    if (ttsAudioContextRef.current?.state === "closed") {
      ttsAudioContextRef.current = null;
    }
  };
}

function createHandleAudioMessageHandler(params: {
  t: Translator;
  onTranscriptReady?: (text: string) => void;
  playAudioResponse: (base64Audio: string, sampleRate: number) => Promise<void>;
  refreshAudioStatus: () => Promise<void>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
  setLastAudioSignal: Dispatch<SetStateAction<string>>;
  setProcessingStatus: Dispatch<SetStateAction<string | null>>;
  setTranscription: Dispatch<SetStateAction<string>>;
  setResponse: Dispatch<SetStateAction<string>>;
  setPlaybackState: Dispatch<SetStateAction<PlaybackState>>;
}) {
  const {
    t,
    onTranscriptReady,
    playAudioResponse,
    refreshAudioStatus,
    setStatusMessage,
    setLastAudioSignal,
    setProcessingStatus,
    setTranscription,
    setResponse,
    setPlaybackState,
  } = params;
  return (data: Record<string, unknown>) => {
    const messageType = toPrimitiveString(data.type) ?? "";
    if (messageType === "recording_started") {
      handleVoiceRecordingStarted(t, setStatusMessage, setLastAudioSignal, setProcessingStatus);
      return;
    }
    if (messageType === "processing") {
      handleVoiceProcessing(t, data, setStatusMessage, setLastAudioSignal, setProcessingStatus);
      return;
    }
    if (messageType === "transcription") {
      handleVoiceTranscript(t, data, onTranscriptReady, setTranscription, setStatusMessage, setLastAudioSignal);
      return;
    }
    if (messageType === "response_text") {
      handleVoiceResponseText(data, setResponse, setLastAudioSignal);
      return;
    }
    if (messageType === "audio_response") {
      handleVoiceAudioResponse(data, playAudioResponse, setLastAudioSignal);
      return;
    }
    if (messageType === "complete") {
      handleVoiceCompletion(t, setStatusMessage, setLastAudioSignal, setProcessingStatus);
      refreshAudioStatus().catch(() => undefined);
      return;
    }
    if (messageType === "error") {
      handleVoiceError(t, data, setPlaybackState, setStatusMessage, setLastAudioSignal);
      refreshAudioStatus().catch(() => undefined);
    }
  };
}

function createReleaseAudioResourcesHandler(params: {
  mediaRecorderRef: MutableRefObject<MediaRecorder | null>;
  sourceNodeRef: MutableRefObject<MediaStreamAudioSourceNode | null>;
  analyserRef: MutableRefObject<AnalyserNode | null>;
  audioContextRef: MutableRefObject<AudioContext | null>;
  mediaStreamRef: MutableRefObject<MediaStream | null>;
}) {
  const { mediaRecorderRef, sourceNodeRef, analyserRef, audioContextRef, mediaStreamRef } = params;
  return () => {
    if (mediaRecorderRef.current?.state === "recording") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore recorder shutdown races
      }
    }
    mediaRecorderRef.current = null;
    sourceNodeRef.current?.disconnect();
    sourceNodeRef.current = null;
    analyserRef.current?.disconnect();
    analyserRef.current = null;
    const audioContext = audioContextRef.current;
    if (audioContext) {
      audioContext.close().catch(() => {
        // Ignore close errors when context is already shutting down.
      });
    }
    audioContextRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  };
}

const selectVoiceState = <T,>(useDebugSnapshot: boolean, debugValue: T, liveValue: T): T =>
  useDebugSnapshot ? debugValue : liveValue;

function resolveEffectiveAudioStatus(
  debugDryRunActive: boolean,
  effectiveRecording: boolean,
  debugMode: VoiceDebugSnapshot,
  audioStatus: AudioStatus | null,
): AudioStatus | null {
  if (!debugDryRunActive) {
    return audioStatus;
  }
  return buildDebugAudioStatus(selectVoiceState(debugDryRunActive, debugMode.recording, effectiveRecording));
}

type VoiceCommandCenterViewState = Readonly<{
  effectiveAudioEnabled: boolean;
  effectiveConnected: boolean;
  effectiveIsVoiceModeEnabled: boolean;
  effectiveRecording: boolean;
  effectiveTranscription: string;
  effectiveResponse: string;
  effectiveStatusMessage: string | null;
  effectiveAudioChunkCount: number;
  effectiveLastAudioSignal: string;
  effectiveProcessingStatus: string | null;
  effectivePlaybackState: PlaybackState;
  effectiveAudioStatus: AudioStatus | null;
  orbState: VoiceOrbState;
  effectiveOrbState: VoiceOrbState;
  visualOrbState: VoiceOrbState;
  effectiveEffectsConfig: ReturnType<typeof useOrbEffectsConfig>;
  orbReducedMotion: boolean;
  metricsRef: ReturnType<typeof useOrbMetrics>;
  recordingButtonClass: string;
  recordingButtonLabel: string;
  voiceChatModeLabel: string;
  playbackStateLabel: string;
  audioWsStateLabel: string;
  showDevButton: boolean;
  showOrbZone: boolean;
  showOrbDiagnosticFallback: boolean;
}>;

function buildVoiceCommandCenterViewState(params: {
  audioEnabled: boolean;
  debugDryRunActive: boolean;
  debugMode: VoiceDebugSnapshot;
  connected: boolean;
  isVoiceModeEnabled: boolean;
  recording: boolean;
  transcription: string;
  response: string;
  statusMessage: string | null;
  audioChunkCount: number;
  lastAudioSignal: string;
  processingStatus: string | null;
  playbackState: PlaybackState;
  audioStatus: AudioStatus | null;
  reducedMotion: boolean;
  pageVisible: boolean;
  ttsMuted: boolean;
  t: Translator;
  renderDiagnostics: ReturnType<typeof useVoiceRenderDiagnostics>;
  effectsConfig: ReturnType<typeof useOrbEffectsConfig>;
  orbActivityWindow: boolean;
  metricsRef: ReturnType<typeof useOrbMetrics>;
}): VoiceCommandCenterViewState {
  const {
    audioEnabled,
    debugDryRunActive,
    debugMode,
    connected,
    isVoiceModeEnabled,
    recording,
    transcription,
    response,
    statusMessage,
    audioChunkCount,
    lastAudioSignal,
    processingStatus,
    playbackState,
    audioStatus,
    reducedMotion,
    pageVisible,
    ttsMuted,
    t,
    renderDiagnostics,
    effectsConfig,
    orbActivityWindow,
    metricsRef,
  } = params;

  const effectiveAudioEnabled = selectVoiceState(debugDryRunActive, true, audioEnabled);
  const effectiveConnected = selectVoiceState(debugDryRunActive, debugMode.connected, connected);
  const effectiveIsVoiceModeEnabled = selectVoiceState(
    debugDryRunActive,
    debugMode.isVoiceModeEnabled,
    isVoiceModeEnabled,
  );
  const effectiveRecording = selectVoiceState(debugDryRunActive, debugMode.recording, recording);
  const effectiveTranscription = selectVoiceState(
    debugDryRunActive,
    debugMode.transcription,
    transcription,
  );
  const effectiveResponse = selectVoiceState(debugDryRunActive, debugMode.response, response);
  const effectiveStatusMessage = selectVoiceState(
    debugDryRunActive,
    debugMode.statusMessage,
    statusMessage,
  );
  const effectiveAudioChunkCount = selectVoiceState(
    debugDryRunActive,
    debugMode.audioChunkCount,
    audioChunkCount,
  );
  const effectiveLastAudioSignal = selectVoiceState(
    debugDryRunActive,
    debugMode.lastAudioSignal,
    lastAudioSignal,
  );
  const effectiveProcessingStatus = selectVoiceState(
    debugDryRunActive,
    debugMode.processingStatus,
    processingStatus,
  );
  const effectivePlaybackState = selectVoiceState(
    debugDryRunActive,
    debugMode.playbackState,
    playbackState,
  );
  const effectiveAudioStatus = resolveEffectiveAudioStatus(
    debugDryRunActive,
    effectiveRecording,
    debugMode,
    audioStatus,
  );
  const orbState = deriveOrbState(
    effectiveConnected,
    effectiveRecording,
    effectiveProcessingStatus,
    effectivePlaybackState,
    effectiveLastAudioSignal,
  );
  const effectiveOrbState = resolveDiagnosticOrbState(orbState, renderDiagnostics);
  const visualOrbState = resolveVisualVoiceOrbState(effectiveOrbState, effectiveTranscription);
  const effectiveEffectsConfig = applyOrbDiagnosticProfile(effectsConfig, renderDiagnostics);
  const orbReducedMotion = reducedMotion || !pageVisible || shouldUseOrbCalmIdle(effectiveOrbState, pageVisible, orbActivityWindow);
  const metricsEnabled =
    renderDiagnostics.metricsEnabled &&
    pageVisible &&
    shouldTrackOrbMetrics(effectiveEffectsConfig.orbMetricsBars, effectiveOrbState);
  const metricsRefValue = metricsEnabled ? metricsRef : null;
  const recordingButtonClass = getRecordingButtonClass(
    effectiveAudioEnabled,
    effectiveIsVoiceModeEnabled,
    effectiveRecording,
    effectiveConnected,
  );
  const recordingButtonLabel = debugDryRunActive
    ? "Debug Run"
    : getRecordingButtonLabel(t, effectiveRecording, effectiveIsVoiceModeEnabled);
  const voiceChatModeLabel = effectiveIsVoiceModeEnabled
    ? t("voice.controls.voiceChat")
    : t("voice.controls.textChat");
  const playbackStateLabel = getPlaybackStateLabel(t, effectivePlaybackState, ttsMuted);
  const audioWsStateLabel = effectiveAudioStatus?.enabled
    ? t("voice.controls.ready")
    : t("voice.controls.offline");

  return {
    effectiveAudioEnabled,
    effectiveConnected,
    effectiveIsVoiceModeEnabled,
    effectiveRecording,
    effectiveTranscription,
    effectiveResponse,
    effectiveStatusMessage,
    effectiveAudioChunkCount,
    effectiveLastAudioSignal,
    effectiveProcessingStatus,
    effectivePlaybackState,
    effectiveAudioStatus,
    orbState,
    effectiveOrbState,
    visualOrbState,
    effectiveEffectsConfig,
    orbReducedMotion,
    metricsRef: metricsRefValue,
    recordingButtonClass,
    recordingButtonLabel,
    voiceChatModeLabel,
    playbackStateLabel,
    audioWsStateLabel,
    showDevButton: true,
    showOrbZone: renderDiagnostics.showOrbZone,
    showOrbDiagnosticFallback: !renderDiagnostics.showOrbZone,
  };
}

function useVoiceCommandCenterReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(() => {
    if (globalThis.window === undefined || globalThis.matchMedia === undefined) {
      return false;
    }
    return globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });

  useEffect(() => {
    const mq = globalThis.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  return reducedMotion;
}

function useVoiceCommandCenterWarmup(params: {
  debugDryRunRequested: boolean;
  audioEnabled: boolean;
  isVoiceModeEnabled: boolean;
  analyzerRef: MutableRefObject<AnalyserNode | null>;
  audioContextRef: MutableRefObject<AudioContext | null>;
  sourceNodeRef: MutableRefObject<MediaStreamAudioSourceNode | null>;
  mediaRecorderRef: MutableRefObject<MediaRecorder | null>;
  mediaStreamRef: MutableRefObject<MediaStream | null>;
  getMediaRecorderMimeType: () => string;
  ensurePlaybackContext: () => Promise<AudioContext | null>;
}) {
  const {
    debugDryRunRequested,
    audioEnabled,
    isVoiceModeEnabled,
    analyzerRef,
    audioContextRef,
    sourceNodeRef,
    mediaRecorderRef,
    mediaStreamRef,
    getMediaRecorderMimeType,
    ensurePlaybackContext,
  } = params;

  useEffect(() => {
    if (debugDryRunRequested) {
      return;
    }
    if (!audioEnabled || !isVoiceModeEnabled) {
      return;
    }
    if (
      mediaStreamRef.current &&
      audioContextRef.current &&
      sourceNodeRef.current &&
      analyzerRef.current &&
      mediaRecorderRef.current
    ) {
      return;
    }

    let cancelled = false;
    createVoiceCaptureEnvironment({
      activeWindow: getBrowserWindow(),
      audioContextRef,
      getMediaRecorderMimeType,
      mediaStreamRef,
      sourceNodeRef,
      analyserRef: analyzerRef,
      mediaRecorderRef,
      ensurePlaybackContext,
    }).catch((error) => {
      if (!cancelled) {
        console.warn("Voice capture warmup failed", error);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [
    analyzerRef,
    audioContextRef,
    audioEnabled,
    debugDryRunRequested,
    ensurePlaybackContext,
    getMediaRecorderMimeType,
    isVoiceModeEnabled,
    mediaRecorderRef,
    mediaStreamRef,
    sourceNodeRef,
  ]);
}

function useVoiceCommandCenterConnectionLifecycle(params: {
  debugDryRunRequested: boolean;
  audioEnabled: boolean;
  t: Translator;
  setConnected: Dispatch<SetStateAction<boolean>>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
  setIsVoiceModeEnabled: Dispatch<SetStateAction<boolean>>;
  setLastAudioSignal: Dispatch<SetStateAction<string>>;
  wsRef: MutableRefObject<WebSocket | null>;
  reconnectAttemptsRef: MutableRefObject<number>;
  reconnectTimeoutRef: MutableRefObject<number | null>;
  lastVoiceModeSentRef: MutableRefObject<string | null>;
  releaseAudioResources: () => void;
  releasePlaybackResources: () => void;
  refreshAudioStatus: () => Promise<void>;
  handleAudioMessage: (data: Record<string, unknown>) => void;
  ttsAudioContextRef: MutableRefObject<AudioContext | null>;
}) {
  const {
    debugDryRunRequested,
    audioEnabled,
    t,
    setConnected,
    setStatusMessage,
    setIsVoiceModeEnabled,
    setLastAudioSignal,
    wsRef,
    reconnectAttemptsRef,
    reconnectTimeoutRef,
    lastVoiceModeSentRef,
    releaseAudioResources,
    releasePlaybackResources,
    refreshAudioStatus,
    handleAudioMessage,
    ttsAudioContextRef,
  } = params;

  useEffect(
    () => {
      if (debugDryRunRequested) {
        return undefined;
      }
      return bindVoiceConnectionLifecycle(
        audioEnabled,
        t,
        setConnected,
        setStatusMessage,
        setIsVoiceModeEnabled,
        () =>
          connectVoiceSocket({
            t,
            wsRef,
            reconnectAttemptsRef,
            reconnectTimeoutRef,
            lastVoiceModeSentRef,
            setConnected,
            setStatusMessage,
            setLastAudioSignal,
            releaseAudioResources,
            releasePlaybackResources,
            refreshAudioStatus,
            handleAudioMessage,
            ttsAudioContextRef,
          }),
      );
    },
    [
      audioEnabled,
      debugDryRunRequested,
      handleAudioMessage,
      releaseAudioResources,
      releasePlaybackResources,
      refreshAudioStatus,
      setConnected,
      setIsVoiceModeEnabled,
      setStatusMessage,
      setLastAudioSignal,
      t,
      wsRef,
      reconnectAttemptsRef,
      reconnectTimeoutRef,
      lastVoiceModeSentRef,
      ttsAudioContextRef,
    ],
  );
}

function useVoiceCommandCenterStatusExpiry(params: {
  debugDryRunRequested: boolean;
  lastAudioSignal: string;
  playbackState: PlaybackState;
  processingStatus: string | null;
  recording: boolean;
  setLastAudioSignal: Dispatch<SetStateAction<string>>;
}) {
  const {
    debugDryRunRequested,
    lastAudioSignal,
    playbackState,
    processingStatus,
    recording,
    setLastAudioSignal,
  } = params;

  useEffect(() => {
    if (debugDryRunRequested) {
      return undefined;
    }
    if (!recording && !processingStatus && playbackState === "idle" && lastAudioSignal === "complete") {
      const timeoutId = globalThis.setTimeout(() => {
        setLastAudioSignal((current) => (current === "complete" ? "idle" : current));
      }, 2500);
      return () => globalThis.clearTimeout(timeoutId);
    }
    return undefined;
  }, [debugDryRunRequested, lastAudioSignal, playbackState, processingStatus, recording, setLastAudioSignal]);
}

function useVoiceStatusUpdateEmitter(params: {
  onStatusUpdate?: (status: VoiceStatusUpdate | null) => void;
  debugDryRunRequested: boolean;
  debugRecording: boolean;
  audioStatus: AudioStatus | null;
}) {
  const { onStatusUpdate, debugDryRunRequested, debugRecording, audioStatus } = params;

  useEffect(() => {
    if (!onStatusUpdate) return;
    if (debugDryRunRequested) {
      onStatusUpdate(buildDebugAudioStatus(debugRecording));
      return;
    }
    onStatusUpdate(audioStatus);
  }, [audioStatus, debugDryRunRequested, debugRecording, onStatusUpdate]);
}

function useVoiceModeSyncEffect(params: {
  audioEnabled: boolean;
  connected: boolean;
  t: ReturnType<typeof useTranslation>;
  voiceModePreset: VoiceModePreset;
  lastVoiceModeSentRef: MutableRefObject<string | null>;
  wsRef: MutableRefObject<WebSocket | null>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
}) {
  const {
    audioEnabled,
    connected,
    t,
    voiceModePreset,
    lastVoiceModeSentRef,
    wsRef,
    setStatusMessage,
  } = params;
  useEffect(() => {
    syncVoiceModeSelection({
      audioEnabled,
      connected,
      t,
      voiceModePreset,
      lastVoiceModeSentRef,
      wsRef,
      setStatusMessage,
    });
  }, [audioEnabled, connected, t, voiceModePreset, lastVoiceModeSentRef, wsRef, setStatusMessage]);
}

function useVoiceCaptureWarmupEffect(params: {
  debugDryRunRequested: boolean;
  audioEnabled: boolean;
  isVoiceModeEnabled: boolean;
  mediaStreamRef: MutableRefObject<MediaStream | null>;
  audioContextRef: MutableRefObject<AudioContext | null>;
  sourceNodeRef: MutableRefObject<MediaStreamAudioSourceNode | null>;
  analyserRef: MutableRefObject<AnalyserNode | null>;
  mediaRecorderRef: MutableRefObject<MediaRecorder | null>;
  ensurePlaybackContext: () => Promise<AudioContext>;
  getMediaRecorderMimeType: () => string;
}) {
  const {
    debugDryRunRequested,
    audioEnabled,
    isVoiceModeEnabled,
    mediaStreamRef,
    audioContextRef,
    sourceNodeRef,
    analyserRef,
    mediaRecorderRef,
    ensurePlaybackContext,
    getMediaRecorderMimeType,
  } = params;
  useEffect(() => {
    if (debugDryRunRequested || !audioEnabled || !isVoiceModeEnabled) {
      return;
    }
    if (
      mediaStreamRef.current &&
      audioContextRef.current &&
      sourceNodeRef.current &&
      analyserRef.current &&
      mediaRecorderRef.current
    ) {
      return;
    }

    let cancelled = false;
    createVoiceCaptureEnvironment({
      activeWindow: getBrowserWindow(),
      audioContextRef,
      getMediaRecorderMimeType,
      mediaStreamRef,
      sourceNodeRef,
      analyserRef,
      mediaRecorderRef,
      ensurePlaybackContext,
    }).catch((error) => {
      if (!cancelled) {
        console.warn("Voice capture warmup failed", error);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [
    audioEnabled,
    analyserRef,
    audioContextRef,
    debugDryRunRequested,
    ensurePlaybackContext,
    getMediaRecorderMimeType,
    isVoiceModeEnabled,
    mediaRecorderRef,
    mediaStreamRef,
    sourceNodeRef,
  ]);
}

type VoiceCommandCenterProps = Readonly<{
  onTranscriptReady?: (text: string) => void;
  voiceModePreset?: VoiceModePreset;
  onStatusUpdate?: (status: VoiceStatusUpdate | null) => void;
  isDevMode?: boolean;
}>;

export function VoiceCommandCenter(props: VoiceCommandCenterProps) {
  return <VoiceCommandCenterPanel {...props} />;
}

function tryCapturePointer(element: HTMLButtonElement, pointerId: number): void {
  try {
    element.setPointerCapture(pointerId);
  } catch {
    // pointer capture not supported in this environment
  }
}

function tryReleasePointer(element: HTMLButtonElement, pointerId: number): void {
  try {
    element.releasePointerCapture(pointerId);
  } catch {
    // pointer capture not supported in this environment
  }
}

function replayLastVoiceResponse(params: {
  lastAudioResponseRef: MutableRefObject<{ audio: string; sampleRate: number } | null>;
  playAudioResponse: (base64Audio: string, sampleRate: number) => Promise<void>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
  t: ReturnType<typeof useTranslation>;
}) {
  const last = params.lastAudioResponseRef.current;
  if (!last) {
    params.setStatusMessage(params.t("voice.status.replayUnavailable"));
    return Promise.resolve();
  }
  return params.playAudioResponse(last.audio, last.sampleRate);
}

function toggleVoiceMode(params: {
  debugDryRunActive: boolean;
  isVoiceModeEnabled: boolean;
  setIsVoiceModeEnabled: Dispatch<SetStateAction<boolean>>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
  t: ReturnType<typeof useTranslation>;
}) {
  if (params.debugDryRunActive) return;
  const next = !params.isVoiceModeEnabled;
  params.setIsVoiceModeEnabled(next);
  params.setStatusMessage(next ? params.t("voice.controls.voiceChat") : params.t("voice.controls.textChat"));
}

function isDebugDryRunActive(debugMode: VoiceDebugSnapshot): boolean {
  return debugMode.hydrated && debugMode.enabled;
}

function buildVoiceCommandCenterOrbState(params: {
  debugDryRunActive: boolean;
  debugMode: VoiceDebugSnapshot;
  connected: boolean;
  recording: boolean;
  processingStatus: string | null;
  playbackState: PlaybackState;
  lastAudioSignal: string;
}): VoiceOrbState {
  return deriveOrbState(
    params.debugDryRunActive ? params.debugMode.connected : params.connected,
    params.debugDryRunActive ? params.debugMode.recording : params.recording,
    params.debugDryRunActive ? params.debugMode.processingStatus : params.processingStatus,
    params.debugDryRunActive ? params.debugMode.playbackState : params.playbackState,
    params.debugDryRunActive ? params.debugMode.lastAudioSignal : params.lastAudioSignal,
  );
}

function useVoiceCommandCenterMetricsRef(params: {
  renderDiagnostics: ReturnType<typeof useVoiceRenderDiagnostics>;
  pageVisible: boolean;
  effectsConfig: ReturnType<typeof useOrbEffectsConfig>;
  effectiveOrbState: VoiceOrbState;
}): ReturnType<typeof useOrbMetrics> {
  return useOrbMetrics(
    params.renderDiagnostics.metricsEnabled &&
      params.pageVisible &&
      shouldTrackOrbMetrics(
        applyOrbDiagnosticProfile(params.effectsConfig, params.renderDiagnostics).orbMetricsBars,
        params.effectiveOrbState,
      ),
  );
}

function VoiceCommandCenterPanel({
  onTranscriptReady,
  voiceModePreset = "standard",
  onStatusUpdate,
}: VoiceCommandCenterProps) {
  const t = useTranslation();
  const audioEnabled = process.env.NEXT_PUBLIC_ENABLE_AUDIO_INTERFACE === "true";
  const debugMode = useVoiceDebugMode(t);
  const debugDryRunRequested = debugMode.requested;
  const debugDryRunActive = isDebugDryRunActive(debugMode);
  const [connected, setConnected] = useState(false);
  const [isVoiceModeEnabled, setIsVoiceModeEnabled] = useState<boolean>(audioEnabled);
  const [recording, setRecording] = useState(false);
  const [transcription, setTranscription] = useState("");
  const [response, setResponse] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [audioStatus, setAudioStatus] = useState<AudioStatus | null>(null);
  const [ttsModelOptions, setTtsModelOptions] = useState<TtsModelOption[]>([]);
  const [selectedTtsModelPath, setSelectedTtsModelPath] = useState("");
  const [ttsModelChanging, setTtsModelChanging] = useState(false);
  const [playbackState, setPlaybackState] = useState<PlaybackState>("idle");
  const [ttsMuted, setTtsMuted] = useState(false);
  const [hasReplayAudio, setHasReplayAudio] = useState(false);
  const [audioChunkCount, setAudioChunkCount] = useState(0);
  const [lastAudioSignal, setLastAudioSignal] = useState("idle");
  const [processingStatus, setProcessingStatus] = useState<string | null>(null);
  const [devDrawerOpen, setDevDrawerOpen] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const ttsAudioContextRef = useRef<AudioContext | null>(null);
  const ttsSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const ttsAnalyserRef = useRef<AnalyserNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordingRef = useRef(false);
  const recordingStartPendingRef = useRef(false);
  const stopRequestedRef = useRef(false);
  const lastAudioResponseRef = useRef<{ audio: string; sampleRate: number } | null>(null);
  const lastVoiceModeSentRef = useRef<string | null>(null);

  useVoiceCommandCenterCompleteReset({
    debugDryRunRequested,
    lastAudioSignal,
    recording,
    processingStatus,
    playbackState,
    setLastAudioSignal,
  });

  const reducedMotion = useVoiceCommandCenterReducedMotion();

  useVoiceModeSyncEffect({
    audioEnabled,
    connected,
    t,
    voiceModePreset,
    lastVoiceModeSentRef,
    wsRef,
    setStatusMessage,
  });

  const refreshAudioStatus = useCallback(
    () =>
      createRefreshAudioStatusHandler({
        t,
        debugDryRunRequested,
        debugRecording: debugMode.recording,
        setAudioStatus,
      })(),
    [debugDryRunRequested, debugMode.recording, t],
  );

  const refreshTtsModelOptions = useCallback(
    () =>
      createRefreshTtsModelOptionsHandler({
        debugDryRunRequested,
        setTtsModelOptions,
        setSelectedTtsModelPath,
      })(),
    [debugDryRunRequested, setTtsModelOptions, setSelectedTtsModelPath],
  );

  useVoiceStatusUpdateEmitter({
    onStatusUpdate,
    debugDryRunRequested,
    debugRecording: debugMode.recording,
    audioStatus,
  });

  useVoiceCommandCenterDebugBootstrap({
    debugDryRunRequested,
    debugRecording: debugMode.recording,
    onStatusUpdate,
    refreshAudioStatus,
    refreshTtsModelOptions,
  });

  useVoiceCommandCenterTtsModelRefresh({
    debugDryRunRequested,
    refreshAudioStatus,
    refreshTtsModelOptions,
  });

  const releasePlaybackResources = useCallback(
    () =>
      createReleasePlaybackResourcesHandler({
        ttsSourceRef,
        ttsAnalyserRef,
      })(),
    [],
  );

  const applyTtsModel = useCallback(
    (modelPath: string) =>
      buildTtsModelUpdateStatus({
        t,
        debugDryRunRequested,
        modelPath,
        setSelectedTtsModelPath,
        setStatusMessage,
        setTtsModelChanging,
        refreshAudioStatus,
        refreshTtsModelOptions,
        releasePlaybackResources,
        closeCurrentWs: () => wsRef.current?.close(),
      })(),
    [
      debugDryRunRequested,
      refreshAudioStatus,
      refreshTtsModelOptions,
      releasePlaybackResources,
      t,
      setSelectedTtsModelPath,
      setStatusMessage,
      setTtsModelChanging,
    ],
  );

  const getMediaRecorderMimeType = useCallback(() => createGetMediaRecorderMimeTypeHandler()(), []);

  const ensurePlaybackContext = useCallback(
    () =>
      createEnsurePlaybackContextHandler({
        ttsAudioContextRef,
        ttsSourceRef,
      })(),
    [],
  );

  const playAudioResponse = useCallback(
    (base64Audio: string, sampleRate: number) =>
      createPlayAudioResponseHandler({
        ensurePlaybackContext,
        releasePlaybackResources,
        t,
        ttsMuted,
        setPlaybackState,
        setStatusMessage,
        setLastAudioSignal,
        setHasReplayAudio,
        lastAudioResponseRef,
        ttsAudioContextRef,
        ttsSourceRef,
        ttsAnalyserRef,
      })(base64Audio, sampleRate),
    [
      ensurePlaybackContext,
      releasePlaybackResources,
      t,
      ttsMuted,
      setStatusMessage,
      setLastAudioSignal,
      setHasReplayAudio,
    ],
  );

  const replayLastResponse = useCallback(async () => {
    await replayLastVoiceResponse({
      lastAudioResponseRef,
      playAudioResponse,
      setStatusMessage,
      t,
    });
  }, [playAudioResponse, t, setStatusMessage]);

  const handleAudioMessage = useCallback(
    (data: Record<string, unknown>) =>
      createHandleAudioMessageHandler({
        t,
        onTranscriptReady,
        playAudioResponse,
        refreshAudioStatus,
        setStatusMessage,
        setLastAudioSignal,
        setProcessingStatus,
        setTranscription,
        setResponse,
        setPlaybackState,
      })(data),
    [
      onTranscriptReady,
      playAudioResponse,
      refreshAudioStatus,
      t,
      setStatusMessage,
      setLastAudioSignal,
      setProcessingStatus,
      setTranscription,
      setResponse,
      setPlaybackState,
    ],
  );

  const releaseRecordingResources = useCallback(() => {
    mediaRecorderRef.current = null;
  }, []);

  const releaseAudioResources = useCallback(
    () =>
      createReleaseAudioResourcesHandler({
        mediaRecorderRef,
        sourceNodeRef,
        analyserRef,
        audioContextRef,
        mediaStreamRef,
      })(),
    [],
  );

  useVoiceCaptureWarmupEffect({
    debugDryRunRequested,
    audioEnabled,
    isVoiceModeEnabled,
    mediaStreamRef,
    audioContextRef,
    sourceNodeRef,
    analyserRef,
    mediaRecorderRef,
    ensurePlaybackContext,
    getMediaRecorderMimeType,
  });

  useEffect(
    () => {
      if (debugDryRunRequested) {
        return undefined;
      }
      return bindVoiceConnectionLifecycle(
        audioEnabled,
        t,
        setConnected,
        setStatusMessage,
        setIsVoiceModeEnabled,
        () =>
          connectVoiceSocket({
            t,
            wsRef,
            reconnectAttemptsRef,
            reconnectTimeoutRef,
            lastVoiceModeSentRef,
            setConnected,
            setStatusMessage,
            setLastAudioSignal,
            releaseAudioResources,
            releasePlaybackResources,
            refreshAudioStatus,
            handleAudioMessage,
            ttsAudioContextRef,
          }),
      );
    },
    [
      audioEnabled,
      debugDryRunRequested,
      handleAudioMessage,
      isVoiceModeEnabled,
      refreshAudioStatus,
      releaseAudioResources,
      releasePlaybackResources,
      t,
    ],
  );

  const sendControlMessage = useCallback(
    (payload: Record<string, unknown>) =>
      createSendControlMessage({
        wsRef,
        setStatusMessage,
        t,
      })(payload),
    [t, setStatusMessage],
  );

  const stopRecording = useCallback(
    () =>
      createStopRecordingHandler({
        debugDryRunRequested,
        debugMode,
        recordingStartPendingRef,
        stopRequestedRef,
        recordingRef,
        mediaRecorderRef,
        setRecording,
        setLastAudioSignal,
        setStatusMessage,
        sendControlMessage,
        releaseAudioResources,
        t,
      })(),
    [
      debugDryRunRequested,
      debugMode,
      releaseAudioResources,
      sendControlMessage,
      t,
      setRecording,
      setLastAudioSignal,
      setStatusMessage,
      recordingStartPendingRef,
      stopRequestedRef,
      recordingRef,
      mediaRecorderRef,
    ],
  );

  const startRecording = useCallback(
    () =>
      createStartRecordingHandler({
        debugDryRunRequested,
        debugMode,
        t,
        audioEnabled,
        isVoiceModeEnabled,
        wsRef,
        audioContextRef,
        sourceNodeRef,
        analyserRef,
        mediaRecorderRef,
        mediaStreamRef,
        recordingRef,
        recordingStartPendingRef,
        stopRequestedRef,
        setRecording,
        setStatusMessage,
        setAudioChunkCount,
        setLastAudioSignal,
        releaseRecordingResources,
        releaseAudioResources,
        sendControlMessage,
        getMediaRecorderMimeType,
        ensurePlaybackContext,
        stopRecording,
        activeWindow: getBrowserWindow(),
      })(),
    [
      debugDryRunRequested,
      debugMode,
      ensurePlaybackContext,
      getMediaRecorderMimeType,
      audioEnabled,
      isVoiceModeEnabled,
      releaseRecordingResources,
      releaseAudioResources,
      sendControlMessage,
      stopRecording,
      t,
      setRecording,
      setStatusMessage,
      setAudioChunkCount,
      setLastAudioSignal,
      recordingStartPendingRef,
      stopRequestedRef,
      recordingRef,
      mediaRecorderRef,
      mediaStreamRef,
      audioContextRef,
      sourceNodeRef,
      analyserRef,
    ],
  );

  const effectsConfig = useOrbEffectsConfig();
  const renderDiagnostics = useVoiceRenderDiagnostics();
  const pageVisible = usePageVisibility();
  useVoiceCommandCenterWarmup({
    debugDryRunRequested,
    audioEnabled,
    isVoiceModeEnabled,
    analyzerRef: analyserRef,
    audioContextRef,
    sourceNodeRef,
    mediaRecorderRef,
    mediaStreamRef,
    getMediaRecorderMimeType,
    ensurePlaybackContext,
  });

  useVoiceCommandCenterConnectionLifecycle({
    debugDryRunRequested,
    audioEnabled,
    t,
    setConnected,
    setStatusMessage,
    setIsVoiceModeEnabled,
    setLastAudioSignal,
    wsRef,
    reconnectAttemptsRef,
    reconnectTimeoutRef,
    lastVoiceModeSentRef,
    releaseAudioResources,
    releasePlaybackResources,
    refreshAudioStatus,
    handleAudioMessage,
    ttsAudioContextRef,
  });

  const derivedOrbState = buildVoiceCommandCenterOrbState({
    debugDryRunActive,
    debugMode,
    connected,
    recording,
    processingStatus,
    playbackState,
    lastAudioSignal,
  });
  const effectiveOrbState = resolveDiagnosticOrbState(derivedOrbState, renderDiagnostics);
  const orbActivityWindow = useOrbActivityWindow(effectiveOrbState, pageVisible);
  const metricsRef = useVoiceCommandCenterMetricsRef({
    renderDiagnostics,
    pageVisible,
    effectsConfig,
    effectiveOrbState,
  });

  const viewState = buildVoiceCommandCenterViewState({
    audioEnabled,
    debugDryRunActive,
    debugMode,
    connected,
    isVoiceModeEnabled,
    recording,
    transcription,
    response,
    statusMessage,
    audioChunkCount,
    lastAudioSignal,
    processingStatus,
    playbackState,
    audioStatus,
    reducedMotion,
    pageVisible,
    ttsMuted,
    t,
    renderDiagnostics,
    effectsConfig,
    orbActivityWindow,
    metricsRef,
  });

  useEffect(() => bindRecordingReleaseListeners(viewState.effectiveRecording, stopRecording), [
    stopRecording,
    viewState.effectiveRecording,
  ]);

  useVoiceCommandCenterStatusExpiry({
    debugDryRunRequested,
    lastAudioSignal,
    playbackState,
    processingStatus,
    recording,
    setLastAudioSignal,
  });

  const onRecordingPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLButtonElement>) => {
      event.preventDefault();
      if (!recording) {
        tryCapturePointer(event.currentTarget, event.pointerId);
        startRecording().catch(() => undefined);
      }
    },
    [recording, startRecording],
  );

  const onRecordingPointerUp = useCallback(
    (event: ReactPointerEvent<HTMLButtonElement>) => {
      event.preventDefault();
      stopRecording();
      tryReleasePointer(event.currentTarget, event.pointerId);
    },
    [stopRecording],
  );

  const onVoiceModeToggle = useCallback(() => {
    toggleVoiceMode({
      debugDryRunActive,
      isVoiceModeEnabled,
      setIsVoiceModeEnabled,
      setStatusMessage,
      t,
    });
  }, [debugDryRunActive, isVoiceModeEnabled, setIsVoiceModeEnabled, setStatusMessage, t]);

  return (
    <>
      <Panel
        title={t("voice.page.title")}
        description={t("voice.page.description")}
        action={
          <div className="flex items-center gap-2">
            <Badge tone={viewState.effectiveConnected ? "success" : "warning"}>
              {viewState.effectiveConnected ? t("voice.status.connected") : t("voice.status.offline")}
            </Badge>
            {debugDryRunActive && <Badge tone="warning">{debugMode.badgeLabel}</Badge>}
            {viewState.showDevButton && (
              <Button
                type="button"
                size="xs"
                variant="outline"
                onClick={() => setDevDrawerOpen(true)}
                title={t("voice.controls.diagnostics")}
                aria-label={t("voice.controls.diagnostics")}
              >
                ⚙
              </Button>
            )}
          </div>
        }
      >
        <div className="space-y-4">
          {viewState.effectiveIsVoiceModeEnabled && viewState.showOrbZone && (
            <OrbZone
              transcription={viewState.effectiveTranscription}
              response={viewState.effectiveResponse}
              orbState={viewState.visualOrbState}
              effectsConfig={viewState.effectiveEffectsConfig}
              reducedMotion={viewState.orbReducedMotion}
              audioEnabled={viewState.effectiveAudioEnabled}
              micAnalyserRef={analyserRef}
              ttsAnalyserRef={ttsAnalyserRef}
              metricsRef={viewState.metricsRef}
              showOrb={renderDiagnostics.showOrb}
              showDialogs={renderDiagnostics.showDialogs}
              plainOrbWrapper={renderDiagnostics.plainOrbWrapper}
              diagnosticMode={renderDiagnostics.mode}
            />
          )}

          {viewState.effectiveIsVoiceModeEnabled && viewState.showOrbDiagnosticFallback && (
            <div className="rounded-2xl border border-dashed border-white/10 bg-transparent p-6 text-center text-xs uppercase tracking-[0.28em] text-zinc-500">
              voice diagnostic: {renderDiagnostics.mode}
            </div>
          )}

          <Button
            type="button"
            onPointerDown={onRecordingPointerDown}
            onPointerUp={onRecordingPointerUp}
            onPointerCancel={stopRecording}
            onLostPointerCapture={stopRecording}
            variant="outline"
            size="md"
            className={`w-full justify-center rounded-2xl border px-4 py-6 text-lg font-semibold transition ${viewState.recordingButtonClass}`}
            disabled={!viewState.effectiveConnected || !viewState.effectiveIsVoiceModeEnabled}
          >
            🎙 {viewState.recordingButtonLabel}
          </Button>

          <div className="flex flex-wrap items-center gap-2" data-testid="voice-mode-toggle">
            <Button
              type="button"
              size="xs"
              variant={viewState.effectiveIsVoiceModeEnabled ? "primary" : "outline"}
              onClick={onVoiceModeToggle}
              disabled={!viewState.effectiveAudioEnabled || debugDryRunActive}
            >
              {viewState.effectiveIsVoiceModeEnabled ? t("voice.controls.voice") : t("voice.controls.text")}
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="xs"
              variant="outline"
              onClick={() => setTtsMuted((current) => !current)}
              disabled={!viewState.effectiveAudioEnabled}
            >
              {ttsMuted ? t("voice.controls.ttsMuted") : t("voice.controls.ttsOn")}
            </Button>
            <Button
              type="button"
              size="xs"
              variant="outline"
              onClick={() => replayLastResponse().catch(() => undefined)}
              disabled={debugDryRunActive || !viewState.effectiveAudioEnabled || !hasReplayAudio}
            >
              {t("voice.controls.replay")}
            </Button>
            <Button
              type="button"
              size="xs"
              variant="outline"
              onClick={() => {
                refreshAudioStatus().catch(() => undefined);
                refreshTtsModelOptions().catch(() => undefined);
              }}
            >
              {t("voice.controls.refresh")}
            </Button>
          </div>

          <div className="rounded-2xl box-muted p-3 text-xs text-zinc-300">
            <p className="text-caption">{t("voice.controls.ttsVoice")}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <div className="min-w-[260px] flex-1">
                <Select
                  value={selectedTtsModelPath}
                  onValueChange={(value) => {
                    setSelectedTtsModelPath(value);
                    applyTtsModel(value).catch(() => undefined);
                  }}
                  disabled={!viewState.effectiveAudioEnabled || ttsModelChanging || ttsModelOptions.length === 0}
                >
                  <SelectTrigger className="h-8 border-white/10 bg-white/5 text-xs text-zinc-100">
                    <SelectValue placeholder={t("voice.controls.ttsVoiceSelect")} />
                  </SelectTrigger>
                  <SelectContent className="border-white/10 bg-zinc-950 text-zinc-100">
                    {ttsModelOptions.map((option) => (
                      <SelectItem key={option.path} value={option.path}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <span className="text-[11px] text-zinc-400">
                {getTtsModelStatusText(t, debugDryRunActive, ttsModelChanging)}
              </span>
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-3 text-xs">
            <div className="rounded-2xl box-muted p-3 text-zinc-300">
              <p className="text-caption">{t("voice.controls.voiceChat")}</p>
              <p className="text-white">{viewState.voiceChatModeLabel}</p>
            </div>
            <div className="rounded-2xl box-muted p-3 text-zinc-300">
              <p className="text-caption">{t("voice.controls.playback")}</p>
              <p className="text-white">{viewState.playbackStateLabel}</p>
            </div>
            <div className="rounded-2xl box-muted p-3 text-zinc-300">
              <p className="text-caption">{t("voice.controls.audioWs")}</p>
              <p className="text-white">{viewState.audioWsStateLabel}</p>
            </div>
          </div>

          <TimingStrip timings={viewState.effectiveAudioStatus?.latest_voice_session?.timings_ms} />

          {viewState.effectiveAudioStatus?.latest_voice_session && (
            <RuntimeDiagnosticsPanel
              title={t("runtime.diagnostics.title")}
              description={t("runtime.diagnostics.description")}
              summaryItems={
                [
                  {
                    label: t("runtime.diagnostics.policy"),
                    value: viewState.effectiveAudioStatus.latest_voice_session.selected_policy ?? "—",
                    tone: "neutral",
                  },
                  {
                    label: t("runtime.diagnostics.image"),
                    value: viewState.effectiveAudioStatus.latest_voice_session.selected_image_strategy ?? "—",
                    tone: "neutral",
                    hint: `${t("runtime.diagnostics.retrieval")} ${viewState.effectiveAudioStatus.latest_voice_session.retrieval_used ? t("runtime.diagnostics.on") : t("runtime.diagnostics.off")}`,
                  },
                  {
                    label: t("runtime.diagnostics.route"),
                    value: viewState.effectiveAudioStatus.latest_voice_session.retrieval_route ?? "—",
                    tone: "neutral",
                    hint: `${t("runtime.diagnostics.assistant")} ${viewState.effectiveAudioStatus.latest_voice_session.assistant_used ? t("runtime.diagnostics.on") : t("runtime.diagnostics.off")}`,
                  },
                  {
                    label: t("runtime.diagnostics.economy"),
                    value: viewState.effectiveAudioStatus.latest_voice_session.economy_mode_activated
                      ? t("runtime.diagnostics.on")
                      : t("runtime.diagnostics.off"),
                    tone: viewState.effectiveAudioStatus.latest_voice_session.economy_mode_activated ? "warning" : "success",
                    hint: `${t("runtime.diagnostics.retrievalItems")} ${viewState.effectiveAudioStatus.latest_voice_session.retrieval_context_items ?? 0}`,
                  },
                ] as RuntimeSummaryItem[]
              }
              trace={viewState.effectiveAudioStatus.latest_voice_session.execution_trace ?? []}
              componentSnapshot={viewState.effectiveAudioStatus.latest_voice_session.component_snapshot ?? []}
              degradationReasons={viewState.effectiveAudioStatus.latest_voice_session.degradation_reasons ?? []}
              className="border-white/10 bg-white/[0.02]"
            />
          )}

          <p className="text-hint text-xs">{viewState.effectiveStatusMessage ?? t("voice.status.channelReady")}</p>
        </div>
      </Panel>
      <DevDiagnosticsDrawer
        isOpen={devDrawerOpen}
        onClose={() => setDevDrawerOpen(false)}
        audioStatus={viewState.effectiveAudioStatus}
        lastAudioSignal={viewState.effectiveLastAudioSignal}
        audioChunkCount={viewState.effectiveAudioChunkCount}
        statusMessage={viewState.effectiveStatusMessage}
        renderDiagnosticMode={renderDiagnostics.mode}
      />
    </>
  );
}
