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

export function VoiceCommandCenter() {
  const [connected, setConnected] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcription, setTranscription] = useState("Oczekiwanie na komendę głosową...");
  const [response, setResponse] = useState("—");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [iotStatus, setIotStatus] = useState<IoTStatus | null>(null);
  const [loadingIoT, setLoadingIoT] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
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
    let destroyed = false;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const connect = () => {
      if (destroyed) return;
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/audio`);
      wsRef.current = ws;
      setStatusMessage("Łączenie z kanałem audio…");
      ws.onopen = () => {
        setConnected(true);
        setStatusMessage("Kanał audio połączony.");
      };
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          handleAudioMessage(payload);
        } catch (error) {
          console.error("Audio WS parse error", error);
        }
      };
      ws.onerror = () => {
        setStatusMessage("Błąd kanału audio.");
      };
      ws.onclose = () => {
        setConnected(false);
        if (!destroyed) {
          setStatusMessage("Kanał audio rozłączony – ponawiam połączenie…");
          setTimeout(connect, 3000);
        }
      };
    };
    connect();
    return () => {
      destroyed = true;
      wsRef.current?.close();
    };
  }, [handleAudioMessage]);

  const refreshIoTStatus = useCallback(async () => {
    setLoadingIoT(true);
    try {
      const res = await fetch("/api/v1/iot/status");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = (await res.json()) as IoTStatus;
      setIotStatus(data);
    } catch {
      setIotStatus({
        connected: true,
        cpu_temp: "45°C",
        memory: "42%",
        disk: "65%",
        message: "Połączenie mock – brak API /iot/status.",
      });
    } finally {
      setLoadingIoT(false);
    }
  }, []);

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
        <div className="space-y-3 rounded-3xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">Sterowanie</p>
          <button
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
            className={`flex w-full items-center justify-center rounded-2xl border px-4 py-6 text-lg font-semibold transition ${
              recording
                ? "border-rose-400/60 bg-rose-500/10 text-rose-100"
                : connected
                  ? "border-emerald-400/40 bg-emerald-500/10 text-white"
                  : "border-white/10 bg-white/5 text-zinc-300"
            }`}
            disabled={!connected}
          >
            🎙 {recording ? "Nagrywanie..." : "Przytrzymaj i mów"}
          </button>
          <canvas ref={canvasRef} width={320} height={80} className="w-full rounded-2xl border border-white/10 bg-black/40" />
          <p className="text-xs text-zinc-400">{statusMessage ?? "Kanał gotowy."}</p>
        </div>
        <div className="space-y-3">
          <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
            <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">Transkrypcja</p>
            <p className="mt-2 text-sm text-white">{transcription}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
            <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">Odpowiedź</p>
            <p className="mt-2 text-sm text-white">{response}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-black/30 p-4 text-sm">
            <div className="flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">Rider-Pi</p>
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
                  <p className="text-[11px] uppercase tracking-widest text-zinc-500">Połączenie</p>
                  <p className="text-white">{iotStatus.connected ? "Online" : "Offline"}</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-widest text-zinc-500">CPU</p>
                  <p className="text-white">{iotStatus.cpu_temp ?? "—"}</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-widest text-zinc-500">Pamięć</p>
                  <p className="text-white">{iotStatus.memory ?? "—"}</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-widest text-zinc-500">Dysk</p>
                  <p className="text-white">{iotStatus.disk ?? "—"}</p>
                </div>
                {iotStatus.message && (
                  <div className="sm:col-span-3 text-[11px] text-zinc-500">
                    {iotStatus.message}
                  </div>
                )}
              </div>
            ) : (
              <p className="mt-2 text-xs text-zinc-500">Brak danych IoT.</p>
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}
