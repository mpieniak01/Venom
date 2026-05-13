"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectMenu } from "@/components/ui/select-menu";
import { Gemma4RuntimeControl } from "@/components/gemma4/gemma4-runtime-control";
import type { VoiceStatusUpdate } from "@/components/voice/voice-command-center";
import { useTranslation } from "@/lib/i18n";
import { useRuntime } from "@/components/models/hooks/use-runtime";

type VoiceStatusSidebarProps = Readonly<{
  status: VoiceStatusUpdate | null;
  isDevMode?: boolean;
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

export function VoiceStatusSidebar({ status, isDevMode = false }: VoiceStatusSidebarProps) {
  const t = useTranslation();
  const devModeEnabled = isDevMode;
  const runtime = status?.runtime_snapshot ?? null;
  const isGemma4AudioRuntime =
    (runtime?.provider ?? "").toLowerCase() === "gemma4_audio" ||
    (runtime?.runtime_id ?? "").toLowerCase() === "gemma4_audio";

  if (!status) {
    return (
      <div className="space-y-3">
        <RuntimeSwitchCard />
        <RuntimeOverviewCard
          runtime={null}
          title={t("voice.controls.runtime")}
          loadingLabel={t("voice.status.channelConnecting")}
        />
        {devModeEnabled ? (
          <Gemma4RuntimeControl variant="voice" runtimeSnapshot={null} />
        ) : (
          <StatusCard title={t("voice.controls.runtime")}>
            <p className="text-[11px] text-zinc-400">
              Use `?dev=1` to show Gemma 4 runtime controls.
            </p>
          </StatusCard>
        )}
        <StatusCard title={`${t("voice.controls.stt")} / ${t("voice.controls.tts")}`}>
          <p className="text-hint text-xs py-2">{t("voice.status.channelConnecting")}</p>
        </StatusCard>
      </div>
    );
  }

  const deps = status.dependencies ?? {};
  const depKeys = Object.keys(deps);

  return (
    <div className="space-y-3">
      <RuntimeSwitchCard />
      <RuntimeOverviewCard
        runtime={runtime}
        title={t("voice.controls.runtime")}
      />
      {isGemma4AudioRuntime && devModeEnabled && (
        <Gemma4RuntimeControl variant="voice" runtimeSnapshot={runtime} />
      )}

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

    </div>
  );
}

function RuntimeSwitchCard() {
  const t = useTranslation();
  const runtime = useRuntime();
  const [pending, setPending] = useState(false);
  const selectedRuntime = runtime.selectedServer ?? "";
  const selectedModel = runtime.selectedModel ?? "";
  const applyDisabled = pending || !selectedRuntime || !selectedModel;
  const runtimeError = runtime.activeServer.error ?? runtime.llmServers.error;

  const serverOptions = useMemo(
    () => runtime.serverOptions.map((item) => ({ value: item.value, label: item.label })),
    [runtime.serverOptions],
  );
  const modelOptions = useMemo(
    () => runtime.modelOptions.map((item) => ({ value: item.value, label: item.label })),
    [runtime.modelOptions],
  );

  const handleApply = async () => {
    if (applyDisabled) return;
    setPending(true);
    try {
      await runtime.activateRuntimeSelection(selectedRuntime, selectedModel);
    } finally {
      setPending(false);
    }
  };

  return (
    <StatusCard title={t("voice.controls.runtime")}>
      <div className="space-y-2.5">
        <div>
          <p className="text-caption mb-1">{t("voice.controls.provider")}</p>
          <SelectMenu
            value={selectedRuntime}
            options={serverOptions}
            onChange={(value) => runtime.setSelectedServer(value || null)}
            placeholder={t("voice.controls.runtime")}
            className="w-full"
            disabled={pending || serverOptions.length === 0}
            buttonClassName="w-full justify-between rounded-full border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-3 py-1.5 text-xs font-medium normal-case tracking-normal text-[color:var(--text-primary)] hover:border-[color:var(--ui-border-strong)] hover:bg-[color:var(--ui-surface-hover)] overflow-hidden"
            renderButton={(opt) => (
              <span className="flex-1 truncate text-left text-[color:var(--text-primary)]">
                {opt?.label ?? t("voice.controls.runtime")}
              </span>
            )}
            renderOption={(opt) => (
              <span className="w-full text-left text-sm normal-case tracking-normal text-[color:var(--text-primary)]">
                {opt.label}
              </span>
            )}
          />
        </div>

        <div>
          <p className="text-caption mb-1">Model</p>
          <SelectMenu
            value={selectedModel}
            options={modelOptions}
            onChange={(value) => runtime.setSelectedModel(value || null)}
            placeholder={t("voice.controls.runtime")}
            className="w-full"
            disabled={pending || modelOptions.length === 0}
            buttonClassName="w-full justify-between rounded-full border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-3 py-1.5 text-xs font-medium normal-case tracking-normal text-[color:var(--text-primary)] hover:border-[color:var(--ui-border-strong)] hover:bg-[color:var(--ui-surface-hover)] overflow-hidden"
            renderButton={(opt) => (
              <span className="flex-1 truncate text-left text-[color:var(--text-primary)]">
                {opt?.label ?? t("voice.controls.runtime")}
              </span>
            )}
            renderOption={(opt) => (
              <span className="w-full text-left text-sm normal-case tracking-normal text-[color:var(--text-primary)]">
                {opt.label}
              </span>
            )}
          />
        </div>

        <Button
          type="button"
          size="xs"
          variant="primary"
          onClick={handleApply}
          disabled={applyDisabled}
          className="w-full"
        >
          {pending ? t("voice.controls.refreshing") : t("voice.controls.refresh")}
        </Button>

        {runtimeError && (
          <p className="text-[11px] text-rose-300 truncate">
            {runtimeError.message}
          </p>
        )}
      </div>
    </StatusCard>
  );
}

function RuntimeOverviewCard({
  runtime,
  title,
  loadingLabel,
}: Readonly<{
  runtime: VoiceStatusUpdate["runtime_snapshot"];
  title: string;
  loadingLabel?: string;
}>) {
  const profile = runtime?.runtime_capabilities?.compatibility_profile ?? runtime?.voice_pipeline?.profile ?? null;
  const provider = runtime?.provider ?? null;
  const model = runtime?.model_name ?? null;
  const endpoint = runtime?.endpoint ?? null;
  const probeStatus = runtime?.runtime_capabilities?.probe_status ?? null;
  const t = useTranslation();

  return (
    <StatusCard title={title}>
      {runtime ? (
        <>
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-sm font-semibold text-white truncate">
              {provider ?? "—"} / {model ?? t("voice.controls.unknownModel")}
            </span>
            {probeStatus && (
              <Badge tone={getProbeTone(probeStatus)} className="shrink-0 text-[10px]">
                {probeStatus}
              </Badge>
            )}
          </div>
          {provider && <Row label={t("voice.controls.provider")} value={provider} />}
          {endpoint && <Row label={t("voice.controls.endpoint")} value={endpoint} />}
          {profile && <Row label={t("voice.controls.profile")} value={profile} />}
          {runtime.voice_pipeline?.stt && (
            <Row label={t("voice.controls.stt")} value={runtime.voice_pipeline.stt} />
          )}
          {runtime.voice_pipeline?.reasoning && (
            <Row label={t("voice.controls.pipeline")} value={runtime.voice_pipeline.reasoning} />
          )}
          {runtime.voice_pipeline?.tts && (
            <Row label={t("voice.controls.tts")} value={runtime.voice_pipeline.tts} />
          )}
          {runtime.error && <p className="mt-1 text-[11px] text-rose-300">{runtime.error}</p>}
        </>
      ) : (
        <p className="text-hint text-xs py-2">{loadingLabel ?? t("voice.status.noData")}</p>
      )}
    </StatusCard>
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
