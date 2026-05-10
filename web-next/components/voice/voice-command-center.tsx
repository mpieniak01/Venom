"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getAudioWsUrl } from "@/lib/env";
import { useTranslation } from "@/lib/i18n";

type AudioStatus = {
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

type Translator = (key: string, variables?: Record<string, string | number>) => string;
type VoiceRuntime = NonNullable<NonNullable<AudioStatus["latest_voice_session"]>["runtime"]>;
type RuntimeSnapshot = NonNullable<AudioStatus["runtime_snapshot"]>;

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}

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

const getBrowserWindow = (): Window | undefined => globalThis as Window;

const getVoiceModeMeta = (t: Translator, mode: VoiceModePreset) => ({
  title: t(VOICE_MODE_TITLE_KEYS[mode]),
  description: t(VOICE_MODE_HINT_KEYS[mode]),
});

const buildTimingSummary = (timings?: Record<string, number | null | undefined> | null): string => {
  if (!timings) return "";
  const entries: Array<[string, string | null]> = [
    ["decode", formatTimingSeconds(timings.decode_ms)],
    ["STT", formatTimingSeconds(timings.stt_ms)],
    ["LLM", formatTimingSeconds(timings.llm_ms)],
    ["TTS", formatTimingSeconds(timings.tts_ms)],
    ["total", formatTimingSeconds(timings.total_backend_ms)],
  ];
  return entries
    .filter((entry): entry is [string, string] => Boolean(entry[1]))
    .map(([label, value]) => `${label} ${value}`)
    .join(" · ");
};

const buildRuntimeSummary = (runtime?: VoiceRuntime | null): string => {
  if (!runtime) return "";
  const parts: Array<string | null> = [
    runtime.llm_model
      ? `LLM ${runtime.llm_service_id ?? "runtime"}:${runtime.llm_model}`
      : null,
    runtime.stt_model
      ? `STT ${runtime.stt_model}/${runtime.stt_device ?? "?"}`
      : null,
    runtime.tts_sample_rate ? `TTS ${runtime.tts_sample_rate} Hz` : null,
  ];
  return parts.filter((part): part is string => Boolean(part)).join(" · ");
};

const buildRuntimeSnapshotSummary = (
  runtimeSnapshot: AudioStatus["runtime_snapshot"],
): string => {
  if (!runtimeSnapshot) return "";
  if (runtimeSnapshot.error) return runtimeSnapshot.error;
  const profile = runtimeSnapshot.runtime_capabilities?.compatibility_profile ?? "";
  const probeStatus = runtimeSnapshot.runtime_capabilities?.probe_status ?? "";
  const pipeline = runtimeSnapshot.voice_pipeline;
  const parts = [
    runtimeSnapshot.model_name ? `${runtimeSnapshot.model_name}` : null,
    profile ? `profile ${profile}` : null,
    probeStatus ? `probe ${probeStatus}` : null,
    pipeline?.stt ? `stt ${pipeline.stt}` : null,
    pipeline?.reasoning ? `reasoning ${pipeline.reasoning}` : null,
    pipeline?.tools ? `tools ${pipeline.tools}` : null,
    pipeline?.vision ? `vision ${pipeline.vision}` : null,
    pipeline?.tts ? `tts ${pipeline.tts}` : null,
  ];
  return parts.filter((part): part is string => Boolean(part)).join(" · ");
};

const getProbeTone = (status?: string | null): "success" | "warning" | "danger" | "neutral" => {
  if (status === "verified") return "success";
  if (status === "failed") return "danger";
  if (status === "metadata_only") return "warning";
  return "neutral";
};

const buildProbeSummary = (runtimeSnapshot: RuntimeSnapshot): string => {
  const probes = runtimeSnapshot.runtime_capabilities?.probes ?? {};
  return Object.entries(probes)
    .map(([name, probe]) => `${name}:${probe.status ?? "?"}`)
    .join(" · ");
};

const buildPipelineEntries = (runtimeSnapshot: RuntimeSnapshot): Array<[string, string]> => {
  const pipeline = runtimeSnapshot.voice_pipeline;
  return [
    ["STT", pipeline?.stt ?? "—"],
    ["Reasoning", pipeline?.reasoning ?? "—"],
    ["Tools", pipeline?.tools ?? "—"],
    ["Vision", pipeline?.vision ?? "—"],
    ["TTS", pipeline?.tts ?? "—"],
  ];
};

type RuntimeSnapshotPanelProps = Readonly<{
  t: Translator;
  runtimeSnapshot: RuntimeSnapshot | null;
  runtimeSnapshotSummary: string;
}>;

function RuntimeSnapshotPanel({
  t,
  runtimeSnapshot,
  runtimeSnapshotSummary,
}: RuntimeSnapshotPanelProps) {
  if (!runtimeSnapshot) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="eyebrow">{t("voice.controls.runtimeSnapshot")}</p>
            <p className="mt-1 text-sm text-zinc-300">{t("voice.controls.noRuntimeSnapshot")}</p>
          </div>
          <Badge tone="neutral">{t("voice.controls.offline")}</Badge>
        </div>
      </div>
    );
  }

  const capabilities = runtimeSnapshot.runtime_capabilities;
  const probeStatus = capabilities?.probe_status ?? "unknown";
  const probeSummary = buildProbeSummary(runtimeSnapshot);
  const pipelineEntries = buildPipelineEntries(runtimeSnapshot);
  const notes = runtimeSnapshot.voice_pipeline?.notes ?? [];

  return (
    <div className="rounded-2xl border border-emerald-400/25 bg-emerald-500/[0.06] p-4 shadow-[0_0_32px_rgba(16,185,129,0.08)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">{t("voice.controls.runtimeSnapshot")}</p>
          <p className="mt-1 text-base font-semibold text-white">
            {runtimeSnapshot.model_name ?? t("voice.controls.unknownModel")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {runtimeSnapshotSummary || runtimeSnapshot.provider || "—"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={getProbeTone(probeStatus)}>
            {t("voice.controls.probeStatus")}: {probeStatus}
          </Badge>
          <Badge tone="neutral">
            {capabilities?.compatibility_profile ?? runtimeSnapshot.voice_pipeline?.profile ?? "unknown"}
          </Badge>
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-300">
          <p className="text-caption">{t("voice.controls.provider")}</p>
          <p className="mt-1 text-white">{runtimeSnapshot.provider ?? runtimeSnapshot.runtime_id ?? "—"}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-300">
          <p className="text-caption">{t("voice.controls.profile")}</p>
          <p className="mt-1 text-white">{capabilities?.compatibility_profile ?? "—"}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-300">
          <p className="text-caption">{t("voice.controls.pipeline")}</p>
          <p className="mt-1 text-white">{runtimeSnapshot.voice_pipeline?.profile ?? "—"}</p>
        </div>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-5">
        {pipelineEntries.map(([label, value]) => (
          <div key={label} className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs">
            <p className="text-caption">{label}</p>
            <p className="mt-1 text-white">{value}</p>
          </div>
        ))}
      </div>

      <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-300">
        <p className="text-caption">{t("voice.controls.probes")}</p>
        <p className="mt-1 text-white">{probeSummary || "—"}</p>
        {notes.length > 0 && <p className="mt-2 text-hint">{notes.join(" · ")}</p>}
      </div>
    </div>
  );
}

const buildQualitySummary = (latestVoiceSession: AudioStatus["latest_voice_session"]): string => {
  const parts: string[] = [];
  if (latestVoiceSession) {
    const peak = latestVoiceSession.peak_before_normalization;
    if (typeof peak === "number" && Number.isFinite(peak)) {
      parts.push(`peak ${peak.toFixed(2)}`);
    }
    const rms = latestVoiceSession.rms_after_normalization;
    if (typeof rms === "number" && Number.isFinite(rms)) {
      parts.push(`rms ${rms.toFixed(3)}`);
    }
  }
  return parts.join(" · ");
};

const buildLatestRecordingSummary = (latestVoiceSession: AudioStatus["latest_voice_session"]): string => {
  const parts: string[] = [];
  if (latestVoiceSession) {
    const duration = latestVoiceSession.duration_sec;
    if (typeof duration === "number" && Number.isFinite(duration)) {
      parts.push(`${duration.toFixed(1)} s`);
    }
    if (
      typeof latestVoiceSession.sample_rate === "number" &&
      Number.isFinite(latestVoiceSession.sample_rate)
    ) {
      parts.push(`${latestVoiceSession.sample_rate} Hz`);
    }
    if (latestVoiceSession.input_format) {
      parts.push(latestVoiceSession.input_format);
    }
    if (latestVoiceSession.voice_mode) {
      parts.push(latestVoiceSession.voice_mode);
    }
    const gain = latestVoiceSession.gain_applied;
    if (typeof gain === "number" && Number.isFinite(gain)) {
      parts.push(`gain ${gain.toFixed(1)}`);
    }
  }
  return parts.join(" · ");
};

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

const getAudioContextCtor = (activeWindow?: Window | undefined): typeof AudioContext | null =>
  activeWindow?.AudioContext || activeWindow?.webkitAudioContext || null;

const isWebSocketOpen = (ws: WebSocket | null | undefined): ws is WebSocket =>
  ws?.readyState === WebSocket.OPEN;

const buildReconnectDelay = (attempt: number): number =>
  Math.min(30000, 1000 * 2 ** attempt) + secureRandomInt(500);

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
  canvasRef?: RefObject<HTMLCanvasElement | null>;
  visualizerFrameRef: RefObject<number | null>;
  recordingRef: RefObject<boolean>;
  recordingStartPendingRef: RefObject<boolean>;
  stopRequestedRef: RefObject<boolean>;
  reconnectAttemptsRef: RefObject<number>;
  reconnectTimeoutRef: RefObject<number | null>;
  lastVoiceModeSentRef: RefObject<string | null>;
  setConnected: (value: boolean) => void;
  setRecording: (value: boolean) => void;
  setStatusMessage: (value: string | null) => void;
  setAudioChunkCount: (value: number | ((current: number) => number)) => void;
  setLastAudioSignal: (value: string) => void;
  clearVisualizer?: () => void;
  releaseAudioResources: () => void;
  releasePlaybackResources: () => void;
  refreshAudioStatus: () => Promise<void>;
  handleAudioMessage: (payload: Record<string, unknown>) => void;
  sendControlMessage: (payload: Record<string, unknown>) => boolean;
  getMediaRecorderMimeType: () => string;
  ensurePlaybackContext: () => Promise<AudioContext | null>;
  drawVisualizer?: (samples: Float32Array) => void;
  scaleAudioChunkForDisplay: (
    samples: Float32Array,
  ) => { normalized: Float32Array; peak: number; gain: number };
  activeWindow?: Window;
};

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

const handleVoiceRecordingStarted = (
  t: Translator,
  setStatusMessage: (value: string | null) => void,
  setLastAudioSignal: (value: string) => void,
) => {
  setStatusMessage(t("voice.status.recordingStarted"));
  setLastAudioSignal("recording:started");
};

const handleVoiceProcessing = (
  t: Translator,
  data: Record<string, unknown>,
  setStatusMessage: (value: string | null) => void,
  setLastAudioSignal: (value: string) => void,
) => {
  const status = toPrimitiveString(data.status) ?? "unknown";
  setStatusMessage(t("voice.status.processing", { status }));
  setLastAudioSignal(`processing:${status}`);
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
) => {
  setStatusMessage(t("voice.status.complete"));
  setLastAudioSignal("complete");
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

const connectVoiceSocket = (deps: VoiceControlDeps): (() => void) => {
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
  deps: Pick<
    VoiceControlDeps,
    | "activeWindow"
    | "audioContextRef"
    | "getMediaRecorderMimeType"
    | "mediaStreamRef"
    | "sourceNodeRef"
    | "analyserRef"
    | "mediaRecorderRef"
    | "ensurePlaybackContext"
  >,
): Promise<VoiceCaptureEnvironment | null> => {
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

const startAnalyserLoop = (deps: VoiceControlDeps, analyser: AnalyserNode) => {
  const {
    recordingRef,
    visualizerFrameRef,
    activeWindow,
    scaleAudioChunkForDisplay,
    drawVisualizer,
    setLastAudioSignal,
  } = deps;
  const timeDomain = new Uint8Array(analyser.fftSize);
  const drawFromAnalyser = () => {
    if (!recordingRef.current) {
      return;
    }
    analyser.getByteTimeDomainData(timeDomain);
    const samples = new Float32Array(timeDomain.length);
    for (let index = 0; index < timeDomain.length; index += 1) {
      samples[index] = ((timeDomain[index] ?? 128) - 128) / 128;
    }
    const { normalized, peak } = scaleAudioChunkForDisplay(samples);
    if (peak > 0) {
      setLastAudioSignal(`media:peak ${peak.toFixed(3)}`);
    }
    drawVisualizer?.(normalized);
    visualizerFrameRef.current = activeWindow?.requestAnimationFrame(drawFromAnalyser) ?? null;
  };
  visualizerFrameRef.current = activeWindow?.requestAnimationFrame(drawFromAnalyser) ?? null;
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
  releaseAudioResources: () => void,
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
    releaseAudioResources();
  };
};

const startVoiceCapture = async (deps: VoiceControlDeps): Promise<void> => {
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
    setStatusMessage,
    releaseAudioResources,
    sendControlMessage,
    ensurePlaybackContext,
    getMediaRecorderMimeType,
    stopRecording,
    activeWindow,
  } = deps as VoiceControlDeps & { activeWindow: Window | undefined };

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
      releaseAudioResources,
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
    environment.recorder.start(250);
    startAnalyserLoop(deps, environment.analyser);
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

const VOICE_MODE_TITLE_KEYS: Record<VoiceModePreset, string> = {
  standard: "voice.modes.standard.title",
  deep_analysis: "voice.modes.deepAnalysis.title",
  summary: "voice.modes.summary.title",
  action_items: "voice.modes.actionItems.title",
};

const VOICE_MODE_HINT_KEYS: Record<VoiceModePreset, string> = {
  standard: "voice.modes.standard.description",
  deep_analysis: "voice.modes.deepAnalysis.description",
  summary: "voice.modes.summary.description",
  action_items: "voice.modes.actionItems.description",
};

type VoiceCommandCenterStatusSidebarProps = Readonly<{
  t: Translator;
  audioStatus: AudioStatus | null;
  latestVoiceSession: AudioStatus["latest_voice_session"];
  latestRecordingSummary: string;
  qualitySummary: string;
  timingSummary: string;
  runtimeSummary: string;
  transcription: string;
  response: string;
}>;

function VoiceCommandCenterStatusSidebar({
  t,
  audioStatus,
  latestVoiceSession,
  latestRecordingSummary,
  qualitySummary,
  timingSummary,
  runtimeSummary,
  transcription,
  response,
}: VoiceCommandCenterStatusSidebarProps) {
  return (
    <div className="space-y-3">
      <div className="rounded-2xl box-muted p-4">
        <p className="eyebrow">{t("voice.controls.audioWs")}</p>
        {audioStatus ? (
          <div className="mt-2 grid gap-2 text-xs text-zinc-300 sm:grid-cols-2">
            <div>
              <p className="text-caption">{t("voice.controls.enabled")}</p>
              <p className="text-white">{audioStatus.enabled ? t("common.yes") : t("common.no")}</p>
            </div>
            <div>
              <p className="text-caption">{t("voice.controls.clients")}</p>
              <p className="text-white">{audioStatus.connected_clients}</p>
            </div>
            <div>
              <p className="text-caption">{t("voice.controls.recordings")}</p>
              <p className="text-white">{audioStatus.active_recordings}</p>
            </div>
            <div>
              <p className="text-caption">VAD</p>
              <p className="text-white">{audioStatus.vad_threshold ?? "—"}</p>
            </div>
            <div>
              <p className="text-caption">{t("voice.controls.whisper")}</p>
              <p className="text-white">{audioStatus.whisper_model_size ?? "—"}</p>
            </div>
            <div>
              <p className="text-caption">{t("voice.controls.sttReady")}</p>
              <p className="text-white">{audioStatus.stt_ready ? t("common.yes") : t("common.no")}</p>
            </div>
            <div>
              <p className="text-caption">{t("voice.controls.ttsReady")}</p>
              <p className="text-white">{audioStatus.tts_ready ? t("common.yes") : t("common.no")}</p>
            </div>
            <div>
              <p className="text-caption">{t("voice.controls.ttsFallback")}</p>
              <p className="text-white">{audioStatus.tts_fallback ? t("common.yes") : t("common.no")}</p>
            </div>
            {audioStatus.dependencies && (
              <div className="sm:col-span-2">
                <p className="text-caption">{t("voice.controls.dependencies")}</p>
                <p className="text-white">
                  {Object.entries(audioStatus.dependencies)
                    .map(([name, ok]) => `${name}:${ok ? "yes" : "no"}`)
                    .join(" · ")}
                </p>
              </div>
            )}
            {latestVoiceSession?.download_url && (
              <div className="sm:col-span-2">
                <p className="text-caption">{t("voice.controls.latestRecording")}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <Button asChild size="xs" variant="outline">
                    <a href={latestVoiceSession.download_url} target="_blank" rel="noreferrer">
                      {t("voice.controls.downloadWav")}
                    </a>
                  </Button>
                  <span className="text-[11px] text-zinc-400">{latestRecordingSummary || "—"}</span>
                </div>
                <p className="mt-1 text-hint">
                  {t("voice.controls.sessionId")}: {latestVoiceSession.session_id}
                </p>
                {qualitySummary && <p className="mt-1 text-hint">{t("voice.controls.quality")}: {qualitySummary}</p>}
                {timingSummary && <p className="mt-1 text-hint">{t("voice.controls.timings")}: {timingSummary}</p>}
                {runtimeSummary && <p className="mt-1 text-hint">{t("voice.controls.runtime")}: {runtimeSummary}</p>}
                {latestVoiceSession.transcription && (
                  <p className="mt-1 text-hint">STT: {latestVoiceSession.transcription}</p>
                )}
              </div>
            )}
            {audioStatus.message && <div className="sm:col-span-2 text-hint">{audioStatus.message}</div>}
          </div>
        ) : (
          <p className="mt-2 text-hint">{t("voice.controls.noRecordingYet")}</p>
        )}
      </div>
      <div className="rounded-2xl box-muted p-4">
        <p className="eyebrow">{t("voice.controls.transcription")}</p>
        <p className="mt-2 text-sm text-white">{transcription || t("voice.status.waitingForVoiceCommand")}</p>
      </div>
      <div className="rounded-2xl box-muted p-4">
        <p className="eyebrow">{t("voice.controls.response")}</p>
        <p className="mt-2 text-sm text-white">{response || t("voice.status.noResponseYet")}</p>
      </div>
    </div>
  );
}

type VoiceCommandCenterProps = Readonly<{
  onTranscriptReady?: (text: string) => void;
  voiceModePreset?: VoiceModePreset;
}>;

export function VoiceCommandCenter({
  onTranscriptReady,
  voiceModePreset = "standard",
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
  const [playbackState, setPlaybackState] = useState<PlaybackState>("idle");
  const [ttsMuted, setTtsMuted] = useState(false);
  const [audioChunkCount, setAudioChunkCount] = useState(0);
  const [lastAudioSignal, setLastAudioSignal] = useState("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const ttsAudioContextRef = useRef<AudioContext | null>(null);
  const ttsSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const visualizerFrameRef = useRef<number | null>(null);
  const recordingRef = useRef(false);
  const recordingStartPendingRef = useRef(false);
  const stopRequestedRef = useRef(false);
  const lastAudioResponseRef = useRef<{ audio: string; sampleRate: number } | null>(null);
  const lastVoiceModeSentRef = useRef<string | null>(null);

  const clearVisualizer = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }, []);

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

  const drawVisualizer = useCallback((samples: Float32Array) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "rgba(15,23,42,0.9)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#34d399";
    ctx.lineWidth = 2;
    ctx.beginPath();
    const sliceWidth = canvas.width / Math.max(samples.length, 1);
    let x = 0;
    for (const [index, value] of samples.entries()) {
      const y = (0.5 + value / 2) * canvas.height;
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
      x += sliceWidth;
    }
    ctx.stroke();
  }, []);

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

  const releasePlaybackResources = useCallback(() => {
    try {
      ttsSourceRef.current?.stop();
    } catch {
      // ignore
    }
    ttsSourceRef.current?.disconnect();
    ttsSourceRef.current = null;
  }, []);

  const scaleAudioChunkForDisplay = useCallback((samples: Float32Array) => {
    let peak = 0;
    for (const sample of samples) {
      const value = Math.abs(sample);
      if (value > peak) {
        peak = value;
      }
    }
    const targetPeak = 0.6;
    const gain = peak > 0 ? Math.min(24, Math.max(1, targetPeak / peak)) : 1;
    const normalized = new Float32Array(samples.length);
    for (let index = 0; index < samples.length; index += 1) {
      const value = (samples[index] ?? 0) * gain;
      normalized[index] = Math.max(-1, Math.min(1, value));
    }
    return { normalized, peak, gain };
  }, []);

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
    const AudioContextCtor = browserWindow.AudioContext || browserWindow.webkitAudioContext;
    if (!AudioContextCtor) {
      return null;
    }
    let ctx = ttsAudioContextRef.current;
    if (!ctx) {
      ctx = new AudioContextCtor();
      ttsAudioContextRef.current = ctx;
    }
    if (ctx.state === "suspended") {
      try {
        await ctx.resume();
      } catch {
        // ignore autoplay policy failures; user can replay after a gesture
      }
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
        source.connect(ctx.destination);
        source.onended = () => {
          if (ttsSourceRef.current === source) {
            setPlaybackState("idle");
            ttsSourceRef.current = null;
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
        handleVoiceRecordingStarted(t, setStatusMessage, setLastAudioSignal);
        return;
      }
      if (messageType === "processing") {
        handleVoiceProcessing(t, data, setStatusMessage, setLastAudioSignal);
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
        handleVoiceCompletion(t, setStatusMessage, setLastAudioSignal);
        return;
      }
      if (messageType === "error") {
        handleVoiceError(t, data, setPlaybackState, setStatusMessage, setLastAudioSignal);
      }
    },
    [onTranscriptReady, playAudioResponse, t],
  );

  const releaseAudioResources = useCallback(() => {
    const browserWindow = getBrowserWindow();
    if (visualizerFrameRef.current !== null) {
      browserWindow?.cancelAnimationFrame(visualizerFrameRef.current);
      visualizerFrameRef.current = null;
    }
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
            audioEnabled,
            isVoiceModeEnabled,
            wsRef,
            reconnectAttemptsRef,
            reconnectTimeoutRef,
            lastVoiceModeSentRef,
            setConnected,
            setRecording,
            setStatusMessage,
            setAudioChunkCount,
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
    clearVisualizer();
    setStatusMessage(t("voice.status.recordingEnded"));
    const recorder = mediaRecorderRef.current;
    if (recorder?.state === "recording") {
      recorder.stop();
    } else {
      sendControlMessage({ command: "stop_recording" });
      releaseAudioResources();
    }
  }, [clearVisualizer, releaseAudioResources, sendControlMessage, t]);

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
        visualizerFrameRef,
        recordingRef,
        recordingStartPendingRef,
        stopRequestedRef,
        setRecording,
        setStatusMessage,
        setAudioChunkCount,
        setLastAudioSignal,
        releaseAudioResources,
        sendControlMessage,
        getMediaRecorderMimeType,
        ensurePlaybackContext,
        drawVisualizer,
        scaleAudioChunkForDisplay,
        stopRecording,
        activeWindow: getBrowserWindow(),
      }),
    [
      drawVisualizer,
      ensurePlaybackContext,
      getMediaRecorderMimeType,
      audioEnabled,
      isVoiceModeEnabled,
      releaseAudioResources,
      scaleAudioChunkForDisplay,
      sendControlMessage,
      stopRecording,
      t,
    ],
  );

  const recordingButtonClass = getRecordingButtonClass(
    audioEnabled,
    isVoiceModeEnabled,
    recording,
    connected,
  );
  const recordingButtonLabel = getRecordingButtonLabel(t, recording, isVoiceModeEnabled);
  const latestVoiceSession = audioStatus?.latest_voice_session;
  const runtimeSnapshot = audioStatus?.runtime_snapshot ?? null;
  const activeVoiceMode: VoiceModePreset = voiceModePreset || "standard";
  const activeVoiceModeMeta = getVoiceModeMeta(t, activeVoiceMode);
  const timingSummary = buildTimingSummary(latestVoiceSession?.timings_ms);
  const runtimeSummary = buildRuntimeSummary(latestVoiceSession?.runtime ?? null);
  const runtimeSnapshotSummary = buildRuntimeSnapshotSummary(runtimeSnapshot);
  const qualitySummary = buildQualitySummary(latestVoiceSession);
  const latestRecordingSummary = buildLatestRecordingSummary(latestVoiceSession);
  const voiceChatModeLabel = isVoiceModeEnabled ? t("voice.controls.voiceChat") : t("voice.controls.textChat");
  const playbackStateLabel = getPlaybackStateLabel(t, playbackState, ttsMuted);
  const audioWsStateLabel = audioStatus?.enabled ? t("voice.controls.ready") : t("voice.controls.offline");

  useEffect(() => bindRecordingReleaseListeners(recording, stopRecording), [recording, stopRecording]);

  return (
    <Panel
      title={t("voice.page.title")}
      description={t("voice.page.description")}
      action={
        <Badge tone={connected ? "success" : "warning"}>
          {connected ? t("voice.status.connected") : t("voice.status.offline")}
        </Badge>
      }
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card-shell card-base space-y-3 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="eyebrow">{t("voice.controls.voiceChat")}</p>
            <div className="flex flex-wrap gap-2">
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
                onClick={() => {
                  replayLastResponse().catch(() => undefined);
                }}
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
                }}
              >
                {t("voice.controls.refresh")}
              </Button>
            </div>
          </div>
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
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="rounded-2xl box-muted p-3 text-xs text-zinc-300">
              <p className="text-caption">{t("voice.controls.voiceChat")}</p>
              <p className="text-white">{voiceChatModeLabel}</p>
            </div>
            <div className="rounded-2xl box-muted p-3 text-xs text-zinc-300">
              <p className="text-caption">{t("voice.controls.playback")}</p>
              <p className="text-white">{playbackStateLabel}</p>
            </div>
            <div className="rounded-2xl box-muted p-3 text-xs text-zinc-300">
              <p className="text-caption">{t("voice.controls.audioWs")}</p>
              <p className="text-white">{audioWsStateLabel}</p>
            </div>
            <div className="rounded-2xl box-muted p-3 text-xs text-zinc-300 sm:col-span-3">
              <p className="text-caption">{t("voice.modes.title")}</p>
              <p className="text-white">{activeVoiceModeMeta.title}</p>
              <p className="text-[11px] text-zinc-400">{activeVoiceModeMeta.description}</p>
            </div>
          </div>
          <RuntimeSnapshotPanel
            t={t}
            runtimeSnapshot={runtimeSnapshot}
            runtimeSnapshotSummary={runtimeSnapshotSummary}
          />
          <canvas ref={canvasRef} width={320} height={80} className="w-full rounded-2xl box-muted" />
          <p className="text-hint">{statusMessage ?? t("voice.status.channelReady")}</p>
          <div className="rounded-2xl box-muted p-3 text-xs text-zinc-300">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <p className="text-caption">{t("voice.controls.signal")}</p>
                <p className="text-white">{lastAudioSignal}</p>
              </div>
              <div>
                <p className="text-caption">{t("voice.controls.chunks")}</p>
              <p className="text-white">{audioChunkCount}</p>
              </div>
            </div>
          </div>
        </div>
        <VoiceCommandCenterStatusSidebar
          t={t}
          audioStatus={audioStatus}
          latestVoiceSession={latestVoiceSession}
          latestRecordingSummary={latestRecordingSummary}
          qualitySummary={qualitySummary}
          timingSummary={timingSummary}
          runtimeSummary={runtimeSummary}
          transcription={transcription}
          response={response}
        />
      </div>
    </Panel>
  );
}
