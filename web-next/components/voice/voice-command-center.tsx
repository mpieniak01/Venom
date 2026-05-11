"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
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
  latest_voice_session?: {
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
    runtime?: {
      stt_model?: string | null;
      stt_device?: string | null;
      stt_compute_type?: string | null;
      llm_service_id?: string | null;
      llm_model?: string | null;
      tts_model_path?: string | null;
      tts_fallback?: boolean | null;
      tts_sample_rate?: number | null;
    };
    transcription?: string;
    response_text?: string;
    download_url?: string | null;
    pipeline_id?: string | null;
    audio_runtime_provider?: string | null;
    audio_runtime_model?: string | null;
    audio_input_status?: string | null;
    decoder_source?: string | null;
    fallback_reason?: string | null;
    native_audio_ms?: number | null;
    runtime_log_path?: string | null;
  } | null;
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
    voice_pipeline?: {
      profile?: string | null;
      stt?: string | null;
      reasoning?: string | null;
      tools?: string | null;
      vision?: string | null;
      tts?: string | null;
      notes?: string[] | null;
    } | null;
    error?: string | null;
  } | null;
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
>;

const VOICE_MODE_TITLE_KEYS: Record<VoiceModePreset, string> = {
  standard: "voice.modes.standard.title",
  deep_analysis: "voice.modes.deepAnalysis.title",
  summary: "voice.modes.summary.title",
  action_items: "voice.modes.actionItems.title",
};

type VoiceCommandCenterProps = Readonly<{
  onTranscriptReady?: (text: string) => void;
  voiceModePreset?: VoiceModePreset;
  onStatusUpdate?: (status: VoiceStatusUpdate | null) => void;
}>;

export function VoiceCommandCenter({
  onTranscriptReady,
  voiceModePreset = "standard",
  onStatusUpdate,
}: VoiceCommandCenterProps) {
  const t = useTranslation();
  const audioEnabled = process.env.NEXT_PUBLIC_ENABLE_AUDIO_INTERFACE === "true";
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
  const [audioChunkCount, setAudioChunkCount] = useState(0);
  const [lastAudioSignal, setLastAudioSignal] = useState("idle");
  const [processingStatus, setProcessingStatus] = useState<string | null>(null);
  const [reducedMotion, setReducedMotion] = useState(false);
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

  useEffect(() => {
    const mq = globalThis.matchMedia("(prefers-reduced-motion: reduce)");
    setReducedMotion(mq.matches);
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  useEffect(() => {
    if (!onStatusUpdate) return;
    if (!audioStatus) { onStatusUpdate(null); return; }
    onStatusUpdate({
      enabled:           audioStatus.enabled,
      stt_ready:         audioStatus.stt_ready,
      tts_ready:         audioStatus.tts_ready,
      tts_fallback:      audioStatus.tts_fallback,
      whisper_model_size:audioStatus.whisper_model_size,
      stt_backend:       audioStatus.stt_backend,
      tts_backend:       audioStatus.tts_backend,
      vad_threshold:     audioStatus.vad_threshold,
      dependencies:      audioStatus.dependencies,
      runtime_snapshot:  audioStatus.runtime_snapshot,
    });
  }, [audioStatus, onStatusUpdate]);

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
  }, [audioEnabled, connected, t, voiceModePreset]);

  const refreshAudioStatus = useCallback(async () => {
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
  }, [t]);

  const refreshTtsModelOptions = useCallback(async () => {
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
  }, []);

  const releasePlaybackResources = useCallback(() => {
    const src = ttsSourceRef.current;
    const analyser = ttsAnalyserRef.current;
    ttsSourceRef.current = null;
    ttsAnalyserRef.current = null;
    try { src?.stop(); } catch { /* ignore races with natural end */ }
    try { src?.disconnect(); } catch { /* ignore */ }
    try { analyser?.disconnect(); } catch { /* ignore */ }
  }, []);

  const applyTtsModel = useCallback(
    async (modelPath: string) => {
      if (!modelPath) return;
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
          wsRef.current?.close();
        }
        await refreshAudioStatus();
        await refreshTtsModelOptions();
      } catch {
        setStatusMessage(t("voice.status.ttsVoiceUpdateFailed"));
      } finally {
        setTtsModelChanging(false);
      }
    },
    [refreshAudioStatus, refreshTtsModelOptions, releasePlaybackResources, t],
  );

  const getMediaRecorderMimeType = useCallback(() => {
    if (typeof MediaRecorder === "undefined") return "";
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/ogg",
    ];
    return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? "";
  }, []);

  const ensurePlaybackContext = useCallback(async () => {
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
  }, []);

  const playAudioResponse = useCallback(
    async (base64Audio: string, sampleRate: number) => {
      lastAudioResponseRef.current = { audio: base64Audio, sampleRate };
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
          // Always clean up the graph nodes for this play
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
    },
    [ensurePlaybackContext, releasePlaybackResources, t, ttsMuted],
  );

  const replayLastResponse = useCallback(async () => {
    const last = lastAudioResponseRef.current;
    if (!last) {
      setStatusMessage(t("voice.status.replayUnavailable"));
      return;
    }
    await playAudioResponse(last.audio, last.sampleRate);
  }, [playAudioResponse, t]);

  const handleAudioMessage = useCallback(
    (data: Record<string, unknown>) => {
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
        return;
      }
      if (messageType === "error") {
        handleVoiceError(t, data, setPlaybackState, setStatusMessage, setLastAudioSignal);
      }
    },
    [onTranscriptReady, playAudioResponse, t],
  );

  const releaseRecordingResources = useCallback(() => {
    mediaRecorderRef.current = null;
  }, []);

  const releaseAudioResources = useCallback(() => {
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
  }, []);

  useEffect(() => {
    if (!audioEnabled || !isVoiceModeEnabled) {
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
    void createVoiceCaptureEnvironment({
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
    ensurePlaybackContext,
    getMediaRecorderMimeType,
    isVoiceModeEnabled,
    mediaRecorderRef,
    mediaStreamRef,
    sourceNodeRef,
    audioContextRef,
  ]);

  useEffect(
    () =>
      bindVoiceConnectionLifecycle(
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
      ),
    [
      audioEnabled,
      handleAudioMessage,
      isVoiceModeEnabled,
      refreshAudioStatus,
      releaseAudioResources,
      releasePlaybackResources,
      t,
    ],
  );

  useEffect(() => {
    refreshTtsModelOptions().catch(() => undefined);
  }, [refreshTtsModelOptions]);

  const sendControlMessage = useCallback((payload: Record<string, unknown>): boolean => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
      return true;
    } else {
      setStatusMessage(t("voice.status.channelOffline"));
    }
    return false;
  }, [t]);

  const stopRecording = useCallback(() => {
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
  }, [releaseAudioResources, sendControlMessage, t]);

  const startRecording = useCallback(
    async () =>
      startVoiceCapture({
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
      }),
    [
      ensurePlaybackContext,
      getMediaRecorderMimeType,
      audioEnabled,
      isVoiceModeEnabled,
      releaseRecordingResources,
      releaseAudioResources,
      sendControlMessage,
      stopRecording,
      t,
    ],
  );

  const orbState = deriveOrbState(connected, recording, processingStatus, playbackState, lastAudioSignal);
  const effectsConfig = useOrbEffectsConfig();
  const metricsRef = useOrbMetrics();

  const recordingButtonClass = getRecordingButtonClass(
    audioEnabled,
    isVoiceModeEnabled,
    recording,
    connected,
  );
  const recordingButtonLabel = getRecordingButtonLabel(t, recording, isVoiceModeEnabled);
  const voiceChatModeLabel = isVoiceModeEnabled ? t("voice.controls.voiceChat") : t("voice.controls.textChat");
  const playbackStateLabel = getPlaybackStateLabel(t, playbackState, ttsMuted);
  const audioWsStateLabel = audioStatus?.enabled ? t("voice.controls.ready") : t("voice.controls.offline");

  useEffect(() => bindRecordingReleaseListeners(recording, stopRecording), [recording, stopRecording]);

  const showDevButton =
    process.env.NEXT_PUBLIC_SHOW_DEV_PANEL === "true" ||
    (globalThis.location !== undefined &&
      new URLSearchParams(globalThis.location.search).has("dev"));

  return (
    <>
    <Panel
      title={t("voice.page.title")}
      description={t("voice.page.description")}
      action={
        <div className="flex items-center gap-2">
          <Badge tone={connected ? "success" : "warning"}>
            {connected ? t("voice.status.connected") : t("voice.status.offline")}
          </Badge>
          {showDevButton && (
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
        {/* Orb zone — orb + dialog bubbles */}
        {isVoiceModeEnabled && (
          <OrbZone
            transcription={transcription}
            response={response}
            orbState={orbState}
            effectsConfig={effectsConfig}
            reducedMotion={reducedMotion}
            audioEnabled={audioEnabled}
            micAnalyserRef={analyserRef}
            ttsAnalyserRef={ttsAnalyserRef}
            metricsRef={metricsRef}
          />
        )}

        {/* Push-to-talk */}
        <Button
          type="button"
          onPointerDown={(event) => {
            event.preventDefault();
            if (!recordingRef.current) {
              try {
                event.currentTarget.setPointerCapture(event.pointerId);
              } catch {
                // ignore pointer capture failures
              }
              startRecording().catch(() => undefined);
            }
          }}
          onPointerUp={(event) => {
            event.preventDefault();
            stopRecording();
            try {
              event.currentTarget.releasePointerCapture(event.pointerId);
            } catch {
              // ignore pointer capture failures
            }
          }}
          onPointerCancel={() => stopRecording()}
          onLostPointerCapture={() => stopRecording()}
          variant="outline"
          size="md"
          className={`w-full justify-center rounded-2xl border px-4 py-6 text-lg font-semibold transition ${recordingButtonClass}`}
          disabled={!connected || !isVoiceModeEnabled}
        >
          🎙 {recordingButtonLabel}
        </Button>

        {/* Controls row */}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="xs"
            variant={isVoiceModeEnabled ? "primary" : "outline"}
            onClick={() =>
              setIsVoiceModeEnabled((current) => {
                const next = !current;
                setStatusMessage(next ? t("voice.controls.voiceChat") : t("voice.controls.textChat"));
                return next;
              })
            }
            disabled={!audioEnabled}
          >
            {isVoiceModeEnabled ? t("voice.controls.voice") : t("voice.controls.text")}
          </Button>
          <Button
            type="button"
            size="xs"
            variant="outline"
            onClick={() => setTtsMuted((current) => !current)}
            disabled={!audioEnabled}
          >
            {ttsMuted ? t("voice.controls.ttsMuted") : t("voice.controls.ttsOn")}
          </Button>
          <Button
            type="button"
            size="xs"
            variant="outline"
            onClick={() => replayLastResponse().catch(() => undefined)}
            disabled={!audioEnabled || !lastAudioResponseRef.current}
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

        {/* TTS voice selector */}
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
                disabled={!audioEnabled || ttsModelChanging || ttsModelOptions.length === 0}
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
              {ttsModelChanging ? t("voice.controls.ttsVoiceChanging") : t("voice.controls.ttsVoiceAuto")}
            </span>
          </div>
        </div>

        {/* Status strip */}
        <div className="grid gap-2 sm:grid-cols-3 text-xs">
          <div className="rounded-2xl box-muted p-3 text-zinc-300">
            <p className="text-caption">{t("voice.controls.voiceChat")}</p>
            <p className="text-white">{voiceChatModeLabel}</p>
          </div>
          <div className="rounded-2xl box-muted p-3 text-zinc-300">
            <p className="text-caption">{t("voice.controls.playback")}</p>
            <p className="text-white">{playbackStateLabel}</p>
          </div>
          <div className="rounded-2xl box-muted p-3 text-zinc-300">
            <p className="text-caption">{t("voice.controls.audioWs")}</p>
            <p className="text-white">{audioWsStateLabel}</p>
          </div>
        </div>

        {/* Timing strip — last session stage durations */}
        <TimingStrip timings={audioStatus?.latest_voice_session?.timings_ms} />

        <p className="text-hint text-xs">{statusMessage ?? t("voice.status.channelReady")}</p>
      </div>
    </Panel>
    <DevDiagnosticsDrawer
      isOpen={devDrawerOpen}
      onClose={() => setDevDrawerOpen(false)}
      audioStatus={audioStatus}
      lastAudioSignal={lastAudioSignal}
      audioChunkCount={audioChunkCount}
      statusMessage={statusMessage}
    />
    </>
  );
}
