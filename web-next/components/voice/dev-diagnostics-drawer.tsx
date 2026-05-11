"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

type AudioStatus = {
  enabled: boolean;
  connected_clients: number;
  active_recordings: number;
  vad_threshold?: number;
  whisper_model_size?: string | null;
  stt_ready?: boolean;
  tts_engine?: string | null;
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
    pipeline_id?: string | null;
    audio_runtime_provider?: string | null;
    audio_runtime_model?: string | null;
    audio_input_status?: string | null;
    decoder_source?: string | null;
    fallback_reason?: string | null;
    native_audio_ms?: number | null;
    runtime_log_path?: string | null;
  } | null;
  runtime_snapshot?: {
    runtime_id?: string | null;
    provider?: string | null;
    model_name?: string | null;
    endpoint?: string | null;
    config_hash?: string | null;
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

function getProbeTone(status?: string | null): "success" | "warning" | "danger" | "neutral" {
  if (status === "verified") return "success";
  if (status === "failed") return "danger";
  if (status === "metadata_only") return "warning";
  return "neutral";
}

function formatSeconds(milliseconds?: number | null): string | null {
  if (typeof milliseconds !== "number" || !Number.isFinite(milliseconds)) return null;
  return `${(milliseconds / 1000).toFixed(2)}s`;
}

function joinParts(parts: Array<string | null | false | undefined>): string {
  return parts.filter(Boolean).join(" · ");
}

export function DevDiagnosticsDrawer({
  isOpen,
  onClose,
  audioStatus,
  lastAudioSignal,
  audioChunkCount,
  statusMessage,
}: DevDiagnosticsDrawerProps) {
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const latestVoiceSession = audioStatus?.latest_voice_session ?? null;
  const runtimeSnapshot = audioStatus?.runtime_snapshot ?? null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <button
        type="button"
        aria-label="Zamknij diagnostics drawer"
        className="absolute inset-0 z-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div
        className="relative z-10 max-h-[80vh] w-full max-w-3xl overflow-y-auto rounded-t-3xl border border-white/10 bg-zinc-950 p-6 shadow-2xl"
        style={{ animation: "slideUpDrawer 220ms ease-out" }}
      >
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-zinc-200">⚙ Diagnostics</p>
            <p className="text-xs text-zinc-500">
              {lastAudioSignal || "no signal"} · chunks {audioChunkCount}
            </p>
            {statusMessage && <p className="text-xs text-zinc-400">{statusMessage}</p>}
          </div>
          <Button size="xs" variant="outline" onClick={onClose}>
            Zamknij
          </Button>
        </div>

        <div className="space-y-3">
          <AudioStatusSection audioStatus={audioStatus} />
          <LatestRecordingSection latestVoiceSession={latestVoiceSession} />
          <RuntimeSnapshotSection runtimeSnapshot={runtimeSnapshot} />
        </div>
      </div>
    </div>
  );
}

function AudioStatusSection({ audioStatus }: Readonly<{ audioStatus: AudioStatus | null }>) {
  return (
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
            <p className="text-caption">TTS Engine</p>
            <p className="text-white">{audioStatus.tts_engine ?? "piper_local"}</p>
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
          {audioStatus.message && <div className="sm:col-span-2 text-hint">{audioStatus.message}</div>}
        </div>
      ) : (
        <p className="text-hint text-xs">Brak danych</p>
      )}
    </div>
  );
}

function LatestRecordingSection({
  latestVoiceSession,
}: Readonly<{
  latestVoiceSession: AudioStatus["latest_voice_session"];
}>) {
  if (!latestVoiceSession?.download_url) return null;

  const timings = latestVoiceSession.timings_ms;
  const runtime = latestVoiceSession.runtime;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <p className="eyebrow mb-2">Ostatnie nagranie</p>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Button asChild size="xs" variant="outline">
          <a href={latestVoiceSession.download_url} target="_blank" rel="noreferrer">
            Pobierz WAV
          </a>
        </Button>
      </div>
      <div className="space-y-1 text-xs text-zinc-400">
        <p>ID sesji: {latestVoiceSession.session_id}</p>
        {latestVoiceSession.duration_sec != null && (
          <p>
            {latestVoiceSession.duration_sec.toFixed(1)}s · {latestVoiceSession.sample_rate} Hz ·{" "}
            {latestVoiceSession.input_format} · {latestVoiceSession.voice_mode} · gain{" "}
            {latestVoiceSession.gain_applied?.toFixed(1)}
          </p>
        )}
        {(latestVoiceSession.peak_before_normalization != null ||
          latestVoiceSession.rms_after_normalization != null) && (
          <p>
            peak {latestVoiceSession.peak_before_normalization?.toFixed(2)} · rms{" "}
            {latestVoiceSession.rms_after_normalization?.toFixed(3)}
          </p>
        )}
        {timings && (
          <p>
            {joinParts([
              formatSeconds(timings.stt_ms) && `STT ${formatSeconds(timings.stt_ms)}`,
              formatSeconds(timings.llm_ms) && `LLM ${formatSeconds(timings.llm_ms)}`,
              formatSeconds(timings.tts_ms) && `TTS ${formatSeconds(timings.tts_ms)}`,
              formatSeconds(timings.total_backend_ms) && `total ${formatSeconds(timings.total_backend_ms)}`,
            ])}
          </p>
        )}
        {runtime && (
          <p>
            {joinParts([
              runtime.llm_model && `LLM ${runtime.llm_service_id}:${runtime.llm_model}`,
              runtime.stt_model && `STT ${runtime.stt_model}/${runtime.stt_device}`,
              runtime.tts_sample_rate != null ? `TTS ${runtime.tts_sample_rate} Hz` : null,
            ])}
          </p>
        )}
        {latestVoiceSession.transcription && <p>STT: {latestVoiceSession.transcription}</p>}
        {latestVoiceSession.pipeline_id && (
          <p>Pipeline: {latestVoiceSession.pipeline_id}</p>
        )}
        {latestVoiceSession.audio_runtime_provider && (
          <p>
            STT backend:{" "}
            {latestVoiceSession.audio_runtime_provider === "gemma4_audio"
              ? "gemma4_audio"
              : "faster-whisper"}
            {latestVoiceSession.audio_runtime_model
              ? ` (${latestVoiceSession.audio_runtime_model})`
              : ""}
          </p>
        )}
        {latestVoiceSession.decoder_source && (
          <p>Decoder source: {latestVoiceSession.decoder_source}</p>
        )}
        {latestVoiceSession.audio_input_status && (
          <p>Audio input: {latestVoiceSession.audio_input_status}</p>
        )}
        {latestVoiceSession.fallback_reason && (
          <p className="text-amber-400">Fallback: {latestVoiceSession.fallback_reason}</p>
        )}
        {latestVoiceSession.native_audio_ms != null && (
          <p>Native audio: {formatSeconds(latestVoiceSession.native_audio_ms)}</p>
        )}
        {latestVoiceSession.runtime_log_path && (
          <p className="truncate text-zinc-500">Log: {latestVoiceSession.runtime_log_path}</p>
        )}
      </div>
    </div>
  );
}

function RuntimeSnapshotSection({
  runtimeSnapshot,
}: Readonly<{
  runtimeSnapshot: AudioStatus["runtime_snapshot"];
}>) {
  if (!runtimeSnapshot) return null;
  const capabilities = runtimeSnapshot.runtime_capabilities;
  const pipeline = runtimeSnapshot.voice_pipeline;
  const probeStatus = capabilities?.probe_status ?? "unknown";
  const probes = capabilities?.probes ?? {};
  const probeSummary = Object.entries(probes)
    .map(([name, probe]) => `${name}:${probe.status ?? "?"}`)
    .join(" · ");

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Snapshot Runtime</p>
          <p className="mt-1 text-base font-semibold text-white">
            {runtimeSnapshot.model_name ?? "Unknown model"}
          </p>
          {runtimeSnapshot.error && <p className="mt-1 text-xs text-rose-200">{runtimeSnapshot.error}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={getProbeTone(probeStatus)}>Probe: {probeStatus}</Badge>
          <Badge tone="neutral">{capabilities?.compatibility_profile ?? pipeline?.profile ?? "unknown"}</Badge>
        </div>
      </div>
      <div className="mb-3 grid gap-2 text-xs sm:grid-cols-3">
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <p className="text-caption">Provider</p>
          <p className="mt-1 text-white">{runtimeSnapshot.provider ?? runtimeSnapshot.runtime_id ?? "—"}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <p className="text-caption">Endpoint</p>
          <p className="mt-1 text-white">{runtimeSnapshot.endpoint ?? "—"}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <p className="text-caption">Config hash</p>
          <p className="mt-1 font-mono text-white">{runtimeSnapshot.config_hash ?? "—"}</p>
        </div>
      </div>
      {capabilities?.probes && Object.keys(capabilities.probes).length > 0 && (
        <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-300">
          <p className="mb-1 text-caption">Probes</p>
          <p className="font-mono">{probeSummary || "—"}</p>
        </div>
      )}
      {pipeline && (
        <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-300">
          <p className="mb-1 text-caption">Voice pipeline</p>
          <p className="font-mono">
            {joinParts([
              pipeline.profile && `profile:${pipeline.profile}`,
              pipeline.stt && `stt:${pipeline.stt}`,
              pipeline.reasoning && `reasoning:${pipeline.reasoning}`,
              pipeline.tools && `tools:${pipeline.tools}`,
              pipeline.vision && `vision:${pipeline.vision}`,
              pipeline.tts && `tts:${pipeline.tts}`,
            ]) || "—"}
          </p>
          {pipeline.notes && pipeline.notes.length > 0 && (
            <ul className="mt-2 list-disc pl-4 text-zinc-400">
              {pipeline.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
