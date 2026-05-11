"use client";

import { Badge } from "@/components/ui/badge";
import { Gemma4RuntimeControl } from "@/components/gemma4/gemma4-runtime-control";
import type { VoiceStatusUpdate } from "@/components/voice/voice-command-center";
import { useTranslation } from "@/lib/i18n";

type VoiceStatusSidebarProps = Readonly<{
  status: VoiceStatusUpdate | null;
}>;

function getProbeTone(status?: string | null): "success" | "warning" | "danger" | "neutral" {
  if (status === "verified") return "success";
  if (status === "failed") return "danger";
  if (status === "metadata_only") return "warning";
  return "neutral";
}

function ReadyDot({ ready }: Readonly<{ ready?: boolean | null }>) {
  return (
    <span
      className={`inline-block h-1.5 w-1.5 rounded-full ${ready ? "bg-emerald-400" : "bg-zinc-600"}`}
    />
  );
}

function Row({ label, value }: Readonly<{ label: string; value: React.ReactNode }>) {
  return (
    <div className="flex items-center justify-between gap-2 py-1 border-b border-white/[0.04] last:border-0">
      <span className="text-caption shrink-0">{label}</span>
      <span className="text-white text-right truncate max-w-[60%]">{value}</span>
    </div>
  );
}

export function VoiceStatusSidebar({ status }: VoiceStatusSidebarProps) {
  const t = useTranslation();

  if (!status) {
    return (
      <div className="space-y-3">
        <StatusCard title={`${t("voice.controls.stt")} / ${t("voice.controls.tts")}`}>
          <p className="text-hint text-xs py-2">{t("voice.status.channelConnecting")}</p>
        </StatusCard>
        <StatusCard title={t("voice.controls.runtime")}>
          <p className="text-hint text-xs py-2">{t("voice.status.noData")}</p>
        </StatusCard>
      </div>
    );
  }

  const runtime = status.runtime_snapshot;
  const pipeline = runtime?.voice_pipeline;
  const caps = runtime?.runtime_capabilities;
  const probeStatus = caps?.probe_status;
  const deps = status.dependencies ?? {};
  const depKeys = Object.keys(deps);

  return (
    <div className="space-y-3">
      {/* Gemma 4 daemon controls */}
      <Gemma4RuntimeControl variant="voice" />

      {/* STT / TTS box */}
      <StatusCard title={`${t("voice.controls.stt")} / ${t("voice.controls.tts")}`}>
        <Row
          label={t("voice.controls.stt")}
          value={
            <span className="flex items-center gap-1.5">
              <ReadyDot ready={status.stt_ready} />
              <span>{status.whisper_model_size ?? status.stt_backend ?? "—"}</span>
            </span>
          }
        />
        <Row
          label={t("voice.controls.tts")}
          value={
            <span className="flex items-center gap-1.5">
              <ReadyDot ready={status.tts_ready} />
              <span>
                {status.tts_backend ?? "—"}
                {status.tts_fallback ? ` (${t("voice.controls.ttsFallback")})` : ""}
              </span>
            </span>
          }
        />
        {status.vad_threshold != null && (
          <Row label={t("voice.controls.vad")} value={status.vad_threshold} />
        )}
        {depKeys.length > 0 && (
          <Row
            label={t("voice.controls.dependencies")}
            value={
              <span className="flex flex-wrap gap-x-2 gap-y-0.5 justify-end">
                {depKeys.map((k) => (
                  <span
                    key={k}
                    className={`text-[10px] ${deps[k] ? "text-emerald-400" : "text-rose-400"}`}
                  >
                    {k}
                  </span>
                ))}
              </span>
            }
          />
        )}
      </StatusCard>

      {/* Runtime box */}
      <StatusCard title={t("voice.controls.runtime")}>
        {runtime ? (
          <>
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-sm font-semibold text-white truncate">
                {runtime.model_name ?? t("voice.controls.unknownModel")}
              </span>
              {probeStatus && (
                <Badge tone={getProbeTone(probeStatus)} className="shrink-0 text-[10px]">
                  {probeStatus}
                </Badge>
              )}
            </div>
            {runtime.provider && (
              <Row label={t("voice.controls.provider")} value={runtime.provider} />
            )}
            {caps?.compatibility_profile && (
              <Row label={t("voice.controls.profile")} value={caps.compatibility_profile} />
            )}
            {pipeline?.stt && <Row label={t("voice.controls.stt")} value={pipeline.stt} />}
            {pipeline?.reasoning && <Row label={t("voice.controls.pipeline")} value={pipeline.reasoning} />}
            {pipeline?.tts && <Row label={t("voice.controls.tts")} value={pipeline.tts} />}
            {runtime.error && (
              <p className="mt-1 text-[11px] text-rose-300">{runtime.error}</p>
            )}
          </>
        ) : (
          <p className="text-hint text-xs py-2">{t("voice.controls.noRuntimeSnapshot")}</p>
        )}
      </StatusCard>
    </div>
  );
}

function StatusCard({
  title,
  children,
}: Readonly<{
  title: string;
  children: React.ReactNode;
}>) {
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] p-3 text-xs text-zinc-300">
      <p className="eyebrow mb-2">{title}</p>
      {children}
    </div>
  );
}
