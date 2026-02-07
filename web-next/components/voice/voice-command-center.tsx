import { useCallback, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

type IoTStatus = {
  connected: boolean;
  cpu_temp?: string;
  memory?: string;
  disk?: string;
  message?: string;
};

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

export function VoiceCommandCenter() {
  const audioEnabled = process.env.NEXT_PUBLIC_ENABLE_AUDIO_INTERFACE === "true";
  const iotStatusEnabled = process.env.NEXT_PUBLIC_ENABLE_IOT_STATUS === "true";
  const [connected, setConnected] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcription, setTranscription] = useState("Oczekiwanie na komendę głosową...");
  const [response, setResponse] = useState("—");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [iotStatus, setIotStatus] = useState<IoTStatus | null>(null);
  const [loadingIoT, setLoadingIoT] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const recordingRef = useRef(false);

  const handleAudioMessage = useCallback((data: Record<string, unknown>) => {
    switch (data.type) {
      case "processing":
        setStatusMessage(`Przetwarzanie (${String(data.status)})`);
        break;
      case "transcription":
        setTranscription(String(data.text ?? "Nie rozpoznano mowy."));
        break;
      case "response_text":
        setResponse(String(data.text ?? "—"));
        break;
      case "error":
        setStatusMessage(String(data.message ?? "Błąd kanału audio."));
        break;
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!audioEnabled) {
      setConnected(false);
      setStatusMessage("Kanał audio wyłączony w konfiguracji.");
      return;
    }
    let destroyed = false;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const connect = () => {
      if (destroyed) return;
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/audio`);
      wsRef.current = ws;
      setStatusMessage("Łączenie z kanałem audio…");
      ws.onopen = () => {
        setConnected(true);
        reconnectAttemptsRef.current = 0;
        setStatusMessage("Kanał audio połączony.");
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
        setStatusMessage("Kanał audio offline.");
      };
      ws.onclose = () => {
        setConnected(false);
        if (!destroyed) {
          const attempt = reconnectAttemptsRef.current;
          const baseDelay = Math.min(30000, 1000 * 2 ** attempt);
          const jitter = secureRandomInt(500);
          const delay = baseDelay + jitter;
          reconnectAttemptsRef.current = Math.min(attempt + 1, 6);
          setStatusMessage(`Kanał audio offline – ponawiam za ${Math.ceil(delay / 1000)}s…`);
          if (reconnectTimeoutRef.current) {
            window.clearTimeout(reconnectTimeoutRef.current);
          }
          reconnectTimeoutRef.current = window.setTimeout(connect, delay);
        }
      };
    };
    connect();
    return () => {
      destroyed = true;
      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
    };
  }, [audioEnabled, handleAudioMessage]);

  const refreshIoTStatus = useCallback(async () => {
    if (!iotStatusEnabled) {
      setIotStatus({
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
          setIotStatus({
            connected: false,
            message: "Offline – endpoint /api/v1/iot/status nie jest dostępny.",
          });
          return;
        }
        throw new Error("HTTP " + res.status);
      }
      const data = (await res.json()) as IoTStatus;
      setIotStatus(data);
    } catch {
      setIotStatus({
        connected: false,
        message: "Offline – brak danych IoT.",
      });
    } finally {
      setLoadingIoT(false);
    }
  }, [iotStatusEnabled]);

  useEffect(() => {
    refreshIoTStatus();
  }, [refreshIoTStatus]);

  const startRecording = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setStatusMessage("Kanał audio nie jest gotowy.");
      return;
    }
    if (recordingRef.current) return;
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = mediaStream;
      const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextCtor) {
        setStatusMessage("Brak wsparcia AudioContext w przeglądarce.");
        return;
      }
      const audioContext = new AudioContextCtor();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(mediaStream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;
      source.connect(processor);
      processor.connect(audioContext.destination);
      recordingRef.current = true;
      setRecording(true);
      setStatusMessage("Nagrywanie…");
      wsRef.current.send(JSON.stringify({ command: "start_recording" }));
      processor.onaudioprocess = (event) => {
        if (!recordingRef.current) return;
        const channelData = event.inputBuffer.getChannelData(0);
        const int16 = new Int16Array(channelData.length);
        for (let i = 0; i < channelData.length; i += 1) {
          int16[i] = Math.max(-32768, Math.min(32767, channelData[i] * 32768));
        }
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(int16.buffer);
        }
        drawVisualizer(channelData);
      };
    } catch (error) {
      console.error("recording error", error);
      setStatusMessage("Nie udało się uruchomić mikrofonu.");
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (!recordingRef.current) return;
    recordingRef.current = false;
    setRecording(false);
    wsRef.current?.send(JSON.stringify({ command: "stop_recording" }));
    processorRef.current?.disconnect();
    processorRef.current = null;
    audioContextRef.current?.close();
    audioContextRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    clearVisualizer();
    setStatusMessage("Nagrywanie zakończone.");
  }, []);

  const drawVisualizer = (samples: Float32Array) => {
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
    const sliceWidth = canvas.width / samples.length;
    let x = 0;
    for (let i = 0; i < samples.length; i += 1) {
      const v = samples[i];
      const y = (0.5 + v / 2) * canvas.height;
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
      x += sliceWidth;
    }
    ctx.stroke();
  };

  const clearVisualizer = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  };

  return (
    <Panel
      title="Voice Command Center"
      description="Kanał /ws/audio + transkrypcja i odpowiedź w czasie rzeczywistym."
      action={
        <Badge tone={connected ? "success" : "warning"}>
          {connected ? "WS połączony" : "WS offline"}
        </Badge>
      }
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card-shell card-base space-y-3 p-4">
          <p className="eyebrow">Sterowanie</p>
          <Button
            type="button"
            onMouseDown={startRecording}
            onMouseUp={stopRecording}
            onMouseLeave={stopRecording}
            onTouchStart={(e) => {
              e.preventDefault();
              startRecording();
            }}
            onTouchEnd={(e) => {
              e.preventDefault();
              stopRecording();
            }}
            variant="outline"
            size="md"
            className={`w-full justify-center rounded-2xl border px-4 py-6 text-lg font-semibold transition ${
              recording
                ? "border-rose-400/60 bg-rose-500/10 text-rose-100"
                : connected
                  ? "border-emerald-400/40 bg-emerald-500/10 text-white"
                  : "border-white/10 bg-white/5 text-zinc-300"
            }`}
            disabled={!connected}
          >
            🎙 {recording ? "Nagrywanie..." : "Przytrzymaj i mów"}
          </Button>
          <canvas ref={canvasRef} width={320} height={80} className="w-full rounded-2xl box-muted" />
          <p className="text-hint">{statusMessage ?? "Kanał gotowy."}</p>
        </div>
        <div className="space-y-3">
          <div className="rounded-2xl box-muted p-4">
            <p className="eyebrow">Transkrypcja</p>
            <p className="mt-2 text-sm text-white">{transcription}</p>
          </div>
          <div className="rounded-2xl box-muted p-4">
            <p className="eyebrow">Odpowiedź</p>
            <p className="mt-2 text-sm text-white">{response}</p>
          </div>
          <div className="rounded-2xl box-muted p-4 text-sm">
            <div className="flex items-center justify-between">
              <p className="eyebrow">Rider-Pi</p>
              <Button
                size="xs"
                variant="outline"
                onClick={refreshIoTStatus}
                disabled={loadingIoT}
              >
                {loadingIoT ? "Odświeżam…" : "Odśwież"}
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
                {iotStatus.message && (
                  <div className="sm:col-span-3 text-hint">
                    {iotStatus.message}
                  </div>
                )}
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
