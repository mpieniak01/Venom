"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useTranslation } from "@/lib/i18n";

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
  renderDiagnosticMode?: string;
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

function formatTtsSampleRateLabel(sampleRate?: number | null): string | null {
  if (sampleRate == null) {
    return null;
  }
  return `TTS ${sampleRate} Hz`;
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
  renderDiagnosticMode,
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

  return (
    <Sheet open={isOpen} onOpenChange={(next) => !next && onClose()}>
      <SheetContent
        className="max-h-[90vh] overflow-y-auto border-l border-r-0 border-white/10 pr-2 data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right"
      >
        <SheetHeader className="mb-4 text-left">
          <SheetTitle className="heading-h3">⚙ Diagnostics</SheetTitle>
          <SheetDescription className="text-sm text-muted">
            Diagnostyka voice runtime i request path.
          </SheetDescription>
        </SheetHeader>
        <DevDiagnosticsDrawerContent
          audioStatus={audioStatus}
          lastAudioSignal={lastAudioSignal}
          audioChunkCount={audioChunkCount}
          statusMessage={statusMessage}
          renderDiagnosticMode={renderDiagnosticMode}
          onClose={onClose}
        />
      </SheetContent>
    </Sheet>
  );
}

type DevDiagnosticsDrawerContentProps = Readonly<{
  audioStatus: AudioStatus | null;
  lastAudioSignal: string;
  audioChunkCount: number;
  statusMessage: string | null;
  renderDiagnosticMode?: string;
  onClose: () => void;
}>;

export function DevDiagnosticsDrawerContent({
  audioStatus,
  lastAudioSignal,
  audioChunkCount,
  statusMessage,
  renderDiagnosticMode,
  onClose,
}: DevDiagnosticsDrawerContentProps) {
  const t = useTranslation();
  const latestVoiceSession = audioStatus?.latest_voice_session ?? null;
  const runtimeSnapshot = audioStatus?.runtime_snapshot ?? null;
  const wsState = audioStatus?.enabled ? "online" : "offline";

  const copyJson = async (value: unknown) => {
    if (!navigator?.clipboard) return;
    await navigator.clipboard.writeText(JSON.stringify(value, null, 2));
  };

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge tone={wsState === "online" ? "success" : "warning"}>
          {t("voice.controls.audioWs")}: {wsState}
        </Badge>
        <Badge tone="neutral">
          {t("voice.controls.signal")}: {lastAudioSignal || t("common.unknown")}
        </Badge>
        <Badge tone="neutral">
          {t("voice.controls.chunks")}: {audioChunkCount}
        </Badge>
        {renderDiagnosticMode && renderDiagnosticMode !== "off" && (
          <Badge tone="neutral">render: {renderDiagnosticMode}</Badge>
        )}
        {runtimeSnapshot?.provider && (
          <Badge tone="neutral">
            {t("runtime.snapshot.provider")}: {runtimeSnapshot.provider}
          </Badge>
        )}
        {latestVoiceSession?.session_id && (
          <Badge tone="neutral">
            {t("voice.controls.sessionId")}: {latestVoiceSession.session_id}
          </Badge>
        )}
      </div>

      {statusMessage && (
        <div className="mb-4 rounded-2xl box-muted px-3 py-2 text-xs text-zinc-300">
          {statusMessage}
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        <Button
          size="xs"
          variant="outline"
          onClick={() => copyJson(runtimeSnapshot).catch(() => undefined)}
          disabled={!runtimeSnapshot}
        >
          Kopiuj runtime JSON
        </Button>
        <Button
          size="xs"
          variant="outline"
          onClick={() => copyJson(latestVoiceSession).catch(() => undefined)}
          disabled={!latestVoiceSession}
        >
          Kopiuj sesję JSON
        </Button>
        <Button size="xs" variant="outline" onClick={onClose}>
          Zamknij
        </Button>
      </div>

      <div className="space-y-4">
        <AudioStatusSection audioStatus={audioStatus} />
        <RuntimeSnapshotSection runtimeSnapshot={runtimeSnapshot} />
        <LatestRecordingSection latestVoiceSession={latestVoiceSession} />
      </div>
    </>
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
              formatTtsSampleRateLabel(runtime.tts_sample_rate),
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
            {latestVoiceSession.audio_runtime_provider === "multi_runtime"
              ? "multi_runtime"
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
  const t = useTranslation();
  if (!runtimeSnapshot) return null;
  const capabilities = runtimeSnapshot.runtime_capabilities;
  const pipeline = runtimeSnapshot.voice_pipeline;
  const probeStatus = capabilities?.probe_status ?? t("runtime.snapshot.unknown");
  const probes = capabilities?.probes ?? {};
  const probeSummary = Object.entries(probes)
    .map(([name, probe]) => `${name}:${probe.status ?? "?"}`)
    .join(" · ");

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">{t("runtime.snapshot.title")}</p>
          <p className="mt-1 text-base font-semibold text-white">
            {runtimeSnapshot.model_name ?? t("runtime.snapshot.unknownModel")}
          </p>
          {runtimeSnapshot.error && <p className="mt-1 text-xs text-rose-200">{runtimeSnapshot.error}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={getProbeTone(probeStatus)}>
            {t("runtime.snapshot.probeStatus")}: {probeStatus}
          </Badge>
          <Badge tone="neutral">
            {capabilities?.compatibility_profile ?? pipeline?.profile ?? t("runtime.snapshot.unknown")}
          </Badge>
        </div>
      </div>
      <div className="mb-3 grid gap-2 text-xs sm:grid-cols-3">
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <p className="text-caption">{t("runtime.snapshot.provider")}</p>
          <p className="mt-1 text-white">{runtimeSnapshot.provider ?? runtimeSnapshot.runtime_id ?? "—"}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <p className="text-caption">{t("runtime.snapshot.endpoint")}</p>
          <p className="mt-1 text-white">{runtimeSnapshot.endpoint ?? "—"}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <p className="text-caption">{t("runtime.snapshot.configHash")}</p>
          <p className="mt-1 font-mono text-white">{runtimeSnapshot.config_hash ?? "—"}</p>
        </div>
      </div>
      {capabilities?.probes && Object.keys(capabilities.probes).length > 0 && (
        <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-300">
          <p className="mb-1 text-caption">{t("runtime.snapshot.probes")}</p>
          <p className="font-mono">{probeSummary || "—"}</p>
        </div>
      )}
      {pipeline && (
        <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-300">
          <p className="mb-1 text-caption">{t("runtime.snapshot.voicePipeline")}</p>
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
