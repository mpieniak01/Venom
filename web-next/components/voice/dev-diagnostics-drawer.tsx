"use client";

import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

type AudioStatus = {
  enabled: boolean;
  connected_clients: number;
  active_recordings: number;
  vad_threshold?: number;
  whisper_model_size?: string | null;
  stt_ready?: boolean;
  tts_ready?: boolean;
  tts_fallback?: boolean | null;
  dependencies?: Record<string, boolean>;
  message?: string;
  latest_voice_session?: {
    session_id: string;
    duration_sec?: number | null;
    sample_rate?: number | null;
    input_format?: string | null;
    voice_mode?: string | null;
    gain_applied?: number | null;
    peak_before_normalization?: number | null;
    rms_after_normalization?: number | null;
    timings_ms?: Record<string, number | null | undefined>;
    download_url?: string | null;
    transcription?: string;
    runtime?: {
      stt_model?: string | null;
      stt_device?: string | null;
      llm_service_id?: string | null;
      llm_model?: string | null;
      tts_sample_rate?: number | null;
    };
  } | null;
  runtime_snapshot?: {
    runtime_id?: string | null;
    provider?: string | null;
    model_name?: string | null;
    error?: string | null;
    runtime_capabilities?: {
      compatibility_profile?: string | null;
      probe_status?: string | null;
      probes?: Record<string, { status?: string | null; reason?: string | null }>;
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
  } | null;
};

type DevDiagnosticsDrawerProps = Readonly<{
  isOpen: boolean;
  onClose: () => void;
  audioStatus: AudioStatus | null;
  lastAudioSignal: string;
  audioChunkCount: number;
  statusMessage: string | null;
}>;

export function DevDiagnosticsDrawer({
  isOpen,
  onClose,
  audioStatus,
  lastAudioSignal,
  audioChunkCount,
  statusMessage,
}: DevDiagnosticsDrawerProps) {
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    setTimeout(() => document.addEventListener("mousedown", handler), 0);
    return () => document.removeEventListener("mousedown", handler);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const latestVoiceSession = audioStatus?.latest_voice_session;
  const runtimeSnapshot = audioStatus?.runtime_snapshot ?? null;
  const capabilities = runtimeSnapshot?.runtime_capabilities;
  const probeStatus = capabilities?.probe_status ?? "unknown";
  const probes = capabilities?.probes ?? {};
  const probeSummary = Object.entries(probes)
    .map(([name, probe]) => `${name}:${probe.status ?? "?"}`)
    .join(" · ");
  const pipeline = runtimeSnapshot?.voice_pipeline;

  const getProbeTone = (status?: string | null): "success" | "warning" | "danger" | "neutral" => {
    if (status === "verified") return "success";
    if (status === "failed") return "danger";
    if (status === "metadata_only") return "warning";
    return "neutral";
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div
        ref={drawerRef}
        className="relative z-10 w-full max-w-3xl max-h-[80vh] overflow-y-auto rounded-t-3xl border border-white/10 bg-zinc-950 p-6 shadow-2xl"
        style={{ animation: "slideUpDrawer 220ms ease-out" }}
      >
        <div className="mb-4 flex items-center justify-between">
          <p className="text-sm font-semibold text-zinc-200">⚙ Diagnostics</p>
          <Button size="xs" variant="outline" onClick={onClose}>
            Zamknij
          </Button>
        </div>

        <div className="space-y-3">
          {/* Audio WS status */}
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <p className="eyebrow mb-2">Audio WS</p>
            {audioStatus ? (
              <div className="grid gap-2 text-xs text-zinc-300 sm:grid-cols-2">
                <div>
                  <p className="text-caption">Włączony</p>
                  <p className="text-white">{audioStatus.enabled ? "Tak" : "Nie"}</p>
                </div>
                <div>
                  <p className="text-caption">Klienci</p>
                  <p className="text-white">{audioStatus.connected_clients}</p>
                </div>
                <div>
                  <p className="text-caption">Nagrania</p>
                  <p className="text-white">{audioStatus.active_recordings}</p>
                </div>
                <div>
                  <p className="text-caption">VAD</p>
                  <p className="text-white">{audioStatus.vad_threshold ?? "—"}</p>
                </div>
                <div>
                  <p className="text-caption">Whisper</p>
                  <p className="text-white">{audioStatus.whisper_model_size ?? "—"}</p>
                </div>
                <div>
                  <p className="text-caption">STT gotowe</p>
                  <p className="text-white">{audioStatus.stt_ready ? "Tak" : "Nie"}</p>
                </div>
                <div>
                  <p className="text-caption">TTS gotowe</p>
                  <p className="text-white">{audioStatus.tts_ready ? "Tak" : "Nie"}</p>
                </div>
                <div>
                  <p className="text-caption">TTS Fallback</p>
                  <p className="text-white">{audioStatus.tts_fallback ? "Tak" : "Nie"}</p>
                </div>
                {audioStatus.dependencies && (
                  <div className="sm:col-span-2">
                    <p className="text-caption">Zależności</p>
                    <p className="text-white">
                      {Object.entries(audioStatus.dependencies)
                        .map(([name, ok]) => `${name}:${ok ? "yes" : "no"}`)
                        .join(" · ")}
                    </p>
                  </div>
                )}
                {audioStatus.message && (
                  <div className="sm:col-span-2 text-hint">{audioStatus.message}</div>
                )}
              </div>
            ) : (
              <p className="text-hint text-xs">Brak danych</p>
            )}
          </div>

          {/* Latest recording */}
          {latestVoiceSession?.download_url && (
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <p className="eyebrow mb-2">Ostatnie nagranie</p>
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <Button asChild size="xs" variant="outline">
                  <a href={latestVoiceSession.download_url} target="_blank" rel="noreferrer">
                    Pobierz WAV
                  </a>
                </Button>
              </div>
              <div className="space-y-1 text-xs text-zinc-400">
                <p>ID sesji: {latestVoiceSession.session_id}</p>
                {latestVoiceSession.duration_sec != null && (
                  <p>{latestVoiceSession.duration_sec.toFixed(1)}s · {latestVoiceSession.sample_rate} Hz · {latestVoiceSession.input_format} · {latestVoiceSession.voice_mode} · gain {latestVoiceSession.gain_applied?.toFixed(1)}</p>
                )}
                {(latestVoiceSession.peak_before_normalization != null || latestVoiceSession.rms_after_normalization != null) && (
                  <p>peak {latestVoiceSession.peak_before_normalization?.toFixed(2)} · rms {latestVoiceSession.rms_after_normalization?.toFixed(3)}</p>
                )}
                {latestVoiceSession.timings_ms && (
                  <p>
                    {[
                      latestVoiceSession.timings_ms.stt_ms != null && `STT ${(latestVoiceSession.timings_ms.stt_ms / 1000).toFixed(2)}s`,
                      latestVoiceSession.timings_ms.llm_ms != null && `LLM ${(latestVoiceSession.timings_ms.llm_ms / 1000).toFixed(2)}s`,
                      latestVoiceSession.timings_ms.tts_ms != null && `TTS ${(latestVoiceSession.timings_ms.tts_ms / 1000).toFixed(2)}s`,
                      latestVoiceSession.timings_ms.total_backend_ms != null && `total ${(latestVoiceSession.timings_ms.total_backend_ms / 1000).toFixed(2)}s`,
                    ].filter(Boolean).join(" · ")}
                  </p>
                )}
                {latestVoiceSession.runtime && (
                  <p>
                    {[
                      latestVoiceSession.runtime.llm_model && `LLM ${latestVoiceSession.runtime.llm_service_id}:${latestVoiceSession.runtime.llm_model}`,
                      latestVoiceSession.runtime.stt_model && `STT ${latestVoiceSession.runtime.stt_model}/${latestVoiceSession.runtime.stt_device}`,
                      latestVoiceSession.runtime.tts_sample_rate && `TTS ${latestVoiceSession.runtime.tts_sample_rate} Hz`,
                    ].filter(Boolean).join(" · ")}
                  </p>
                )}
                {latestVoiceSession.transcription && (
                  <p>STT: {latestVoiceSession.transcription}</p>
                )}
              </div>
            </div>
          )}

          {/* Runtime snapshot */}
          {runtimeSnapshot && (
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                <div>
                  <p className="eyebrow">Snapshot Runtime</p>
                  <p className="mt-1 text-base font-semibold text-white">
                    {runtimeSnapshot.model_name ?? "Unknown model"}
                  </p>
                  {runtimeSnapshot.error && (
                    <p className="mt-1 text-xs text-rose-200">{runtimeSnapshot.error}</p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge tone={getProbeTone(probeStatus)}>
                    Probe: {probeStatus}
                  </Badge>
                  <Badge tone="neutral">
                    {capabilities?.compatibility_profile ?? pipeline?.profile ?? "unknown"}
                  </Badge>
                </div>
              </div>
              <div className="grid gap-2 text-xs sm:grid-cols-3 mb-3">
                <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                  <p className="text-caption">Provider</p>
                  <p className="mt-1 text-white">{runtimeSnapshot.provider ?? runtimeSnapshot.runtime_id ?? "—"}</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                  <p className="text-caption">Profil</p>
                  <p className="mt-1 text-white">{capabilities?.compatibility_profile ?? "—"}</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                  <p className="text-caption">Pipeline</p>
                  <p className="mt-1 text-white">{pipeline?.profile ?? "—"}</p>
                </div>
              </div>
              {pipeline && (
                <div className="grid gap-2 text-xs sm:grid-cols-5 mb-3">
                  {[["STT", pipeline.stt], ["Reasoning", pipeline.reasoning], ["Tools", pipeline.tools], ["Vision", pipeline.vision], ["TTS", pipeline.tts]].map(([label, val]) => (
                    <div key={label} className="rounded-xl border border-white/10 bg-black/20 p-3">
                      <p className="text-caption">{label}</p>
                      <p className="mt-1 text-white">{val ?? "—"}</p>
                    </div>
                  ))}
                </div>
              )}
              {probeSummary && (
                <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-300">
                  <p className="text-caption">Probes</p>
                  <p className="mt-1 text-white">{probeSummary}</p>
                  {pipeline?.notes && pipeline.notes.length > 0 && (
                    <p className="mt-2 text-hint">{pipeline.notes.join(" · ")}</p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Signal */}
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <p className="eyebrow mb-2">Sygnał</p>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <p className="text-caption">Sygnał</p>
                <p className="text-white">{lastAudioSignal}</p>
              </div>
              <div>
                <p className="text-caption">Chunki</p>
                <p className="text-white">{audioChunkCount}</p>
              </div>
              {statusMessage && (
                <div className="col-span-2">
                  <p className="text-caption">Status</p>
                  <p className="text-white">{statusMessage}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
