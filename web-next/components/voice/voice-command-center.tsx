"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getAudioWsUrl } from "@/lib/env";
import { useTranslation } from "@/lib/i18n";

type IoTStatus = {
  connected: boolean;
  cpu_temp?: string;
  memory?: string;
  disk?: string;
  message?: string;
};

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
};

type PlaybackState = "idle" | "playing" | "muted" | "error";

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
  const binary = globalThis.window.atob(base64Audio);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Int16Array(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
};

const formatTimingSeconds = (milliseconds?: number | null): string | null => {
  if (typeof milliseconds !== "number" || !Number.isFinite(milliseconds)) return null;
  return `${(milliseconds / 1000).toFixed(2)}s`;
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
  const iotStatusEnabled = process.env.NEXT_PUBLIC_ENABLE_IOT_STATUS === "true";
  const [connected, setConnected] = useState(false);
  const [voiceMode, setVoiceMode] = useState(audioEnabled);
  const [recording, setRecording] = useState(false);
  const [transcription, setTranscription] = useState("Oczekiwanie na komendę głosową...");
  const [response, setResponse] = useState("—");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [audioStatus, setAudioStatus] = useState<AudioStatus | null>(null);
  const [iotStatus, setIoTStatus] = useState<IoTStatus | null>(null);
  const [loadingIoT, setLoadingIoT] = useState(false);
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
    if (!audioEnabled || !connected) return;
    const mode = voiceModePreset || "standard";
    if (lastVoiceModeSentRef.current === mode) return;
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(
      JSON.stringify({
        command: "voice_mode",
        mode,
      }),
    );
    lastVoiceModeSentRef.current = mode;
    setStatusMessage(`${t("voice.controls.voiceChat")}: ${t(VOICE_MODE_TITLE_KEYS[mode as VoiceModePreset])}`);
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
    for (let index = 0; index < samples.length; index += 1) {
      const value = samples[index] ?? 0;
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
    for (let index = 0; index < samples.length; index += 1) {
      const value = Math.abs(samples[index] ?? 0);
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
    if (globalThis.window === undefined) return null;
    const AudioContextCtor = globalThis.window.AudioContext || globalThis.window.webkitAudioContext;
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
        setStatusMessage("Odpowiedź audio gotowa, ale odtwarzanie jest wyciszone.");
        return;
      }
      if (globalThis.window === undefined) return;
      const ctx = await ensurePlaybackContext();
      if (!ctx) {
        setPlaybackState("error");
        setStatusMessage("Brak wsparcia AudioContext dla playbacku TTS.");
        return;
      }
      const pcm16 = decodeBase64Pcm16(base64Audio);
      if (pcm16.length === 0) {
        setPlaybackState("error");
        setStatusMessage("Otrzymano pusty bufor audio.");
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
      setStatusMessage("Odtwarzam odpowiedź głosową.");
      source.start();
    },
    [ensurePlaybackContext, releasePlaybackResources, ttsMuted],
  );

  const replayLastResponse = useCallback(async () => {
    const last = lastAudioResponseRef.current;
    if (!last) {
      setStatusMessage("Brak ostatniej odpowiedzi audio do odtworzenia.");
      return;
    }
    await playAudioResponse(last.audio, last.sampleRate);
  }, [playAudioResponse]);

  const handleAudioMessage = useCallback(
    (data: Record<string, unknown>) => {
      switch (data.type) {
        case "recording_started":
          setStatusMessage("Nagrywanie rozpoczęte.");
          setLastAudioSignal("recording:started");
          break;
        case "processing":
          setStatusMessage(`Przetwarzanie (${toPrimitiveString(data.status) ?? "unknown"})`);
          setLastAudioSignal(`processing:${toPrimitiveString(data.status) ?? "unknown"}`);
          break;
        case "transcription":
          {
            const transcript = toPrimitiveString(data.text) ?? "Nie rozpoznano mowy.";
            setTranscription(transcript);
            if (transcript.trim()) {
              onTranscriptReady?.(transcript.trim());
              setStatusMessage("Transkrypcja wstawiona do czatu.");
              setLastAudioSignal("stt:ok");
            }
          }
          break;
        case "response_text":
          setResponse(toPrimitiveString(data.text) ?? "—");
          setLastAudioSignal("response:text");
          break;
        case "audio_response": {
          const audio = toPrimitiveString(data.audio) ?? "";
          const sampleRate = Number(data.sample_rate ?? 22050);
          if (audio) {
            void playAudioResponse(audio, sampleRate);
            setLastAudioSignal("tts:audio");
          }
          break;
        }
        case "complete":
          setStatusMessage("Gotowe.");
          setLastAudioSignal("complete");
          break;
        case "error":
          setPlaybackState("error");
          setStatusMessage(toPrimitiveString(data.message) ?? "Błąd kanału audio.");
          setLastAudioSignal("error");
          break;
      }
    },
    [onTranscriptReady, playAudioResponse],
  );

  const releaseAudioResources = useCallback(() => {
    if (visualizerFrameRef.current !== null) {
      window.cancelAnimationFrame(visualizerFrameRef.current);
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

  useEffect(() => {
    if (globalThis.window === undefined) return;
    if (!audioEnabled) {
      setConnected(false);
      setStatusMessage(t("voice.status.channelDisabled"));
      setVoiceMode(false);
      return;
    }
    let destroyed = false;
    const connect = () => {
      if (destroyed) return;
      const ws = new WebSocket(getAudioWsUrl());
      wsRef.current = ws;
      setStatusMessage(t("voice.status.channelConnecting"));
      ws.onopen = () => {
        setConnected(true);
        reconnectAttemptsRef.current = 0;
        lastVoiceModeSentRef.current = null;
        setStatusMessage(t("voice.status.channelReady"));
        setLastAudioSignal("ws:open");
        void refreshAudioStatus();
      };
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          handleAudioMessage(payload);
        } catch {
          // Ignore malformed payloads to avoid console noise.
        }
      };
      ws.onerror = () => {
        setStatusMessage(t("voice.status.channelOffline"));
        setLastAudioSignal("ws:error");
      };
      ws.onclose = () => {
        setConnected(false);
        lastVoiceModeSentRef.current = null;
        if (!destroyed) {
          const attempt = reconnectAttemptsRef.current;
          const baseDelay = Math.min(30000, 1000 * 2 ** attempt);
          const jitter = secureRandomInt(500);
          const delay = baseDelay + jitter;
          reconnectAttemptsRef.current = Math.min(attempt + 1, 6);
          setStatusMessage(`${t("voice.status.channelOffline")} – ponawiam za ${Math.ceil(delay / 1000)}s…`);
          if (reconnectTimeoutRef.current) {
            globalThis.window.clearTimeout(reconnectTimeoutRef.current);
          }
          reconnectTimeoutRef.current = globalThis.window.setTimeout(connect, delay);
        }
      };
    };
    connect();
    void refreshAudioStatus();
    return () => {
      destroyed = true;
      if (reconnectTimeoutRef.current) {
        globalThis.window.clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
      releaseAudioResources();
      releasePlaybackResources();
      ttsAudioContextRef.current?.close().catch(() => {
        // Ignore close errors on unmount.
      });
      ttsAudioContextRef.current = null;
    };
  }, [audioEnabled, handleAudioMessage, releaseAudioResources, releasePlaybackResources, refreshAudioStatus, t]);

  const refreshIoTStatus = useCallback(async () => {
    if (!iotStatusEnabled) {
      setIoTStatus({
        connected: false,
        message: "Status IoT wyłączony w konfiguracji.",
      });
      return;
    }
    setLoadingIoT(true);
    try {
      const res = await fetch("/api/v1/iot/status");
      if (!res.ok) {
        if (res.status === 404) {
          setIoTStatus({
            connected: false,
            message: "Offline – endpoint /api/v1/iot/status nie jest dostępny.",
          });
          return;
        }
        throw new Error(`HTTP ${res.status}`);
      }
      const data = (await res.json()) as IoTStatus;
      setIoTStatus(data);
    } catch {
      setIoTStatus({
        connected: false,
        message: "Offline – brak danych IoT.",
      });
    } finally {
      setLoadingIoT(false);
    }
  }, [iotStatusEnabled]);

  useEffect(() => {
    void refreshIoTStatus();
  }, [refreshIoTStatus]);

  const sendControlMessage = useCallback((payload: Record<string, unknown>): boolean => {
    const ws = wsRef.current;
    if (ws?.readyState !== WebSocket.OPEN) {
      setStatusMessage(t("voice.status.channelOffline"));
      return false;
    }
    ws.send(JSON.stringify(payload));
    return true;
  }, [t]);

  const stopRecording = useCallback(() => {
    if (recordingStartPendingRef.current) {
      stopRequestedRef.current = true;
      setStatusMessage(t("voice.controls.recording"));
      return;
    }
    if (!recordingRef.current) return;
    recordingRef.current = false;
    stopRequestedRef.current = false;
    setRecording(false);
    setLastAudioSignal("recording:stop");
    clearVisualizer();
    setStatusMessage("Nagrywanie zakończone.");
    const recorder = mediaRecorderRef.current;
    if (recorder?.state === "recording") {
      recorder.stop();
      return;
    }
    sendControlMessage({ command: "stop_recording" });
    releaseAudioResources();
  }, [clearVisualizer, releaseAudioResources, sendControlMessage, t]);

  const startRecording = useCallback(async () => {
    if (!voiceMode) {
      setStatusMessage(t("voice.controls.textChat"));
      return;
    }
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      setStatusMessage(t("voice.status.channelOffline"));
      return;
    }
    if (recordingRef.current || recordingStartPendingRef.current) return;
    try {
      recordingStartPendingRef.current = true;
      stopRequestedRef.current = false;
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaStreamRef.current = mediaStream;
      const AudioContextCtor = globalThis.window.AudioContext || globalThis.window.webkitAudioContext;
      if (!AudioContextCtor) {
        setStatusMessage("Brak wsparcia AudioContext w przeglądarce.");
        return;
      }
      if (typeof MediaRecorder === "undefined") {
        setStatusMessage("Brak wsparcia MediaRecorder w przeglądarce.");
        return;
      }
      void ensurePlaybackContext();
      const audioContext = new AudioContextCtor();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(mediaStream);
      sourceNodeRef.current = source;
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 2048;
      analyserRef.current = analyser;
      source.connect(analyser);
      if (audioContext.state === "suspended") {
        await audioContext.resume();
      }
      const mimeType = getMediaRecorderMimeType();
      const recorder = new MediaRecorder(
        mediaStream,
        mimeType ? { mimeType } : undefined,
      );
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size <= 0 || wsRef.current?.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(event.data);
        setAudioChunkCount((current) => current + 1);
        setLastAudioSignal(`media:${event.data.size}B`);
      };
      recorder.onstop = () => {
        sendControlMessage({ command: "stop_recording" });
        releaseAudioResources();
      };
      recordingRef.current = true;
      setRecording(true);
      setAudioChunkCount(0);
      setLastAudioSignal("recording:start");
      setStatusMessage(t("voice.controls.recording"));
      if (
        !sendControlMessage({
          command: "audio_config",
          sample_rate: audioContext.sampleRate,
          channels: 1,
          format: "mediarecorder",
          mime_type: recorder.mimeType || mimeType,
        })
      ) {
        releaseAudioResources();
        return;
      }
      if (
        !sendControlMessage({
          command: "start_recording",
          format: "mediarecorder",
          mime_type: recorder.mimeType || mimeType,
          sample_rate: audioContext.sampleRate,
          channels: 1,
        })
      ) {
        releaseAudioResources();
        return;
      }
      recorder.start(250);

      const timeDomain = new Uint8Array(analyser.fftSize);
      const drawFromAnalyser = () => {
        if (!recordingRef.current) return;
        analyser.getByteTimeDomainData(timeDomain);
        const samples = new Float32Array(timeDomain.length);
        for (let index = 0; index < timeDomain.length; index += 1) {
          samples[index] = ((timeDomain[index] ?? 128) - 128) / 128;
        }
        const { normalized, peak } = scaleAudioChunkForDisplay(samples);
        if (peak > 0) {
          setLastAudioSignal(`media:peak ${peak.toFixed(3)}`);
        }
        drawVisualizer(normalized);
        visualizerFrameRef.current = window.requestAnimationFrame(drawFromAnalyser);
      };
      visualizerFrameRef.current = window.requestAnimationFrame(drawFromAnalyser);
    } catch (error) {
      console.error("recording error", error);
      releaseAudioResources();
      setStatusMessage("Nie udało się uruchomić mikrofonu.");
    } finally {
      recordingStartPendingRef.current = false;
    }
    if (stopRequestedRef.current && recordingRef.current) {
      stopRecording();
    }
  }, [
    drawVisualizer,
    ensurePlaybackContext,
    getMediaRecorderMimeType,
    releaseAudioResources,
    scaleAudioChunkForDisplay,
    stopRecording,
    sendControlMessage,
    t,
    voiceMode,
  ]);

  const recordingButtonClass = (() => {
    if (!voiceMode || !audioEnabled) return "border-white/10 bg-white/5 text-zinc-500";
    if (recording) return "border-rose-400/60 bg-rose-500/10 text-rose-100";
    if (connected) return "border-emerald-400/40 bg-emerald-500/10 text-white";
    return "border-white/10 bg-white/5 text-zinc-300";
  })();
  const latestVoiceSession = audioStatus?.latest_voice_session;
  const activeVoiceMode = voiceModePreset || "standard";
  const latestTimings = latestVoiceSession?.timings_ms;
  const timingSummary = [
    ["decode", formatTimingSeconds(latestTimings?.decode_ms)],
    ["STT", formatTimingSeconds(latestTimings?.stt_ms)],
    ["LLM", formatTimingSeconds(latestTimings?.llm_ms)],
    ["TTS", formatTimingSeconds(latestTimings?.tts_ms)],
    ["total", formatTimingSeconds(latestTimings?.total_backend_ms)],
  ]
    .filter((entry): entry is [string, string] => Boolean(entry[1]))
    .map(([label, value]) => `${label} ${value}`)
    .join(" · ");
  const runtimeSummary = latestVoiceSession?.runtime
    ? [
        latestVoiceSession.runtime.llm_model
          ? `LLM ${latestVoiceSession.runtime.llm_service_id ?? "runtime"}:${latestVoiceSession.runtime.llm_model}`
          : null,
        latestVoiceSession.runtime.stt_model
          ? `STT ${latestVoiceSession.runtime.stt_model}/${latestVoiceSession.runtime.stt_device ?? "?"}`
          : null,
        latestVoiceSession.runtime.tts_sample_rate
          ? `TTS ${latestVoiceSession.runtime.tts_sample_rate} Hz`
          : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : "";
  const qualitySummary = latestVoiceSession
    ? [
        latestVoiceSession.peak_before_normalization != null
          ? `peak ${latestVoiceSession.peak_before_normalization.toFixed(2)}`
          : null,
        latestVoiceSession.rms_after_normalization != null
          ? `rms ${latestVoiceSession.rms_after_normalization.toFixed(3)}`
          : null,
    ]
        .filter(Boolean)
        .join(" · ")
    : "";

  useEffect(() => {
    if (!recording) return;
    const stopOnRelease = () => {
      stopRecording();
    };
    window.addEventListener("pointerup", stopOnRelease);
    window.addEventListener("mouseup", stopOnRelease);
    window.addEventListener("touchend", stopOnRelease);
    window.addEventListener("touchcancel", stopOnRelease);
    window.addEventListener("blur", stopOnRelease);
    return () => {
      window.removeEventListener("pointerup", stopOnRelease);
      window.removeEventListener("mouseup", stopOnRelease);
      window.removeEventListener("touchend", stopOnRelease);
      window.removeEventListener("touchcancel", stopOnRelease);
      window.removeEventListener("blur", stopOnRelease);
    };
  }, [recording, stopRecording]);

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
                variant={voiceMode ? "primary" : "outline"}
                onClick={() =>
                  setVoiceMode((current) => {
                    const next = !current;
                    setStatusMessage(next ? t("voice.controls.voiceChat") : t("voice.controls.textChat"));
                    return next;
                  })
                }
                disabled={!audioEnabled}
              >
                {voiceMode ? t("voice.controls.voice") : t("voice.controls.text")}
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
                onClick={() => void replayLastResponse()}
                disabled={!audioEnabled || !lastAudioResponseRef.current}
              >
                {t("voice.controls.replay")}
              </Button>
              <Button
                type="button"
                size="xs"
                variant="outline"
                onClick={() => void refreshAudioStatus()}
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
                void startRecording();
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
            disabled={!connected || !voiceMode}
          >
            🎙 {recording ? t("voice.controls.recording") : voiceMode ? t("voice.controls.pushToTalk") : t("voice.controls.textChat")}
          </Button>
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="rounded-2xl box-muted p-3 text-xs text-zinc-300">
              <p className="text-caption">{t("voice.controls.voiceChat")}</p>
              <p className="text-white">{voiceMode ? t("voice.controls.voiceChat") : t("voice.controls.textChat")}</p>
            </div>
            <div className="rounded-2xl box-muted p-3 text-xs text-zinc-300">
              <p className="text-caption">{t("voice.controls.playback")}</p>
              <p className="text-white">{ttsMuted ? t("voice.controls.ttsMuted") : playbackState}</p>
            </div>
            <div className="rounded-2xl box-muted p-3 text-xs text-zinc-300">
              <p className="text-caption">{t("voice.controls.audioWs")}</p>
              <p className="text-white">{audioStatus?.enabled ? t("voice.controls.ready") : t("voice.controls.offline")}</p>
            </div>
            <div className="rounded-2xl box-muted p-3 text-xs text-zinc-300 sm:col-span-3">
              <p className="text-caption">{t("voice.modes.title")}</p>
              <p className="text-white">{t(VOICE_MODE_TITLE_KEYS[activeVoiceMode as VoiceModePreset])}</p>
              <p className="text-[11px] text-zinc-400">{t(VOICE_MODE_HINT_KEYS[activeVoiceMode as VoiceModePreset])}</p>
            </div>
          </div>
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
                        <a
                          href={latestVoiceSession.download_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {t("voice.controls.downloadWav")}
                        </a>
                      </Button>
                      <span className="text-[11px] text-zinc-400">
                        {latestVoiceSession.duration_sec != null
                          ? `${latestVoiceSession.duration_sec.toFixed(1)} s`
                          : "—"}
                        {latestVoiceSession.sample_rate
                          ? ` · ${latestVoiceSession.sample_rate} Hz`
                          : ""}
                        {latestVoiceSession.input_format
                          ? ` · ${latestVoiceSession.input_format}`
                          : ""}
                        {latestVoiceSession.voice_mode
                          ? ` · ${latestVoiceSession.voice_mode}`
                          : ""}
                        {latestVoiceSession.gain_applied
                          ? ` · gain ${latestVoiceSession.gain_applied.toFixed(1)}`
                          : ""}
                      </span>
                    </div>
                    <p className="mt-1 text-hint">
                      {t("voice.controls.sessionId")}: {latestVoiceSession.session_id}
                    </p>
                    {qualitySummary && (
                      <p className="mt-1 text-hint">{t("voice.controls.quality")}: {qualitySummary}</p>
                    )}
                    {timingSummary && (
                      <p className="mt-1 text-hint">{t("voice.controls.timings")}: {timingSummary}</p>
                    )}
                    {runtimeSummary && (
                      <p className="mt-1 text-hint">{t("voice.controls.runtime")}: {runtimeSummary}</p>
                    )}
                    {latestVoiceSession.transcription && (
                      <p className="mt-1 text-hint">
                        STT: {latestVoiceSession.transcription}
                      </p>
                    )}
                  </div>
                )}
                {audioStatus.message && (
                  <div className="sm:col-span-2 text-hint">{audioStatus.message}</div>
                )}
              </div>
            ) : (
              <p className="mt-2 text-hint">{t("voice.controls.noRecordingYet")}</p>
            )}
          </div>
          <div className="rounded-2xl box-muted p-4">
            <p className="eyebrow">{t("voice.controls.transcription")}</p>
            <p className="mt-2 text-sm text-white">{transcription}</p>
          </div>
          <div className="rounded-2xl box-muted p-4">
            <p className="eyebrow">{t("voice.controls.response")}</p>
            <p className="mt-2 text-sm text-white">{response}</p>
          </div>
          <div className="rounded-2xl box-muted p-4 text-sm">
            <div className="flex items-center justify-between">
              <p className="eyebrow">Rider-Pi</p>
              <Button size="xs" variant="outline" onClick={() => void refreshIoTStatus()} disabled={loadingIoT}>
                {loadingIoT ? "Odświeżam…" : t("voice.controls.refresh")}
              </Button>
            </div>
            {iotStatus ? (
              <div className="mt-2 grid gap-2 text-xs text-zinc-300 sm:grid-cols-3">
                <div>
                  <p className="text-caption">Połączenie</p>
                  <p className="text-white">{iotStatus.connected ? "Online" : "Offline"}</p>
                </div>
                <div>
                  <p className="text-caption">CPU</p>
                  <p className="text-white">{iotStatus.cpu_temp ?? "—"}</p>
                </div>
                <div>
                  <p className="text-caption">Pamięć</p>
                  <p className="text-white">{iotStatus.memory ?? "—"}</p>
                </div>
                <div>
                  <p className="text-caption">Dysk</p>
                  <p className="text-white">{iotStatus.disk ?? "—"}</p>
                </div>
                {iotStatus.message && <div className="sm:col-span-3 text-hint">{iotStatus.message}</div>}
              </div>
            ) : (
              <p className="mt-2 text-hint">Brak danych IoT.</p>
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}
