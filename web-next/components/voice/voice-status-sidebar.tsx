"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectMenu } from "@/components/ui/select-menu";
import { Gemma4RuntimeControl } from "@/components/gemma4/gemma4-runtime-control";
import type { VoiceStatusUpdate } from "@/components/voice/voice-command-center";
import { useTranslation } from "@/lib/i18n";
import { resolveRuntimeActivationErrorMessage, useRuntime } from "@/components/models/hooks/use-runtime";

type VoiceStatusSidebarProps = Readonly<{
  status: VoiceStatusUpdate | null;
  isDevMode?: boolean;
  onRuntimeApplied?: () => void;
}>;

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

function formatConfidence(value?: number | null): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

function isGenericFailureResponse(text: string): boolean {
  const normalized = text.trim().toLowerCase();
  if (!normalized) return false;
  return (
    normalized.includes("przepraszam, wystąpił błąd") ||
    normalized.includes("przepraszam, wystapil blad") ||
    normalized.includes("spróbuj ponownie") ||
    normalized.includes("sprobuj ponownie") ||
    normalized.includes("sorry, an error occurred") ||
    normalized.includes("please try again")
  );
}

export function VoiceStatusSidebar({ status, isDevMode = false, onRuntimeApplied }: VoiceStatusSidebarProps) {
  const t = useTranslation();
  const runtime = status?.runtime_snapshot ?? null;
  const latestVoiceSession = status?.latest_voice_session ?? runtime?.latest_voice_session ?? null;
  const runtimeProvider = (runtime?.provider ?? "").trim().toLowerCase();
  const runtimeId = (runtime?.runtime_id ?? "").trim().toLowerCase();
  const isGemma4AudioRuntime =
    runtimeProvider === "multi_runtime" ||
    runtimeProvider === "gemma4_audio" ||
    runtimeProvider.startsWith("multi_runtime@") ||
    runtimeProvider.startsWith("gemma4_audio@") ||
    runtimeId === "multi_runtime" ||
    runtimeId === "gemma4_audio" ||
    runtimeId.startsWith("multi_runtime@") ||
    runtimeId.startsWith("gemma4_audio@");

  if (!status) {
    return (
      <div className="space-y-3">
        <RuntimeSwitchCard />
        <div className="flex items-center gap-3 pt-1">
          <div className="flex-1 border-t border-white/[0.05]" />
          <span className="text-[10px] uppercase tracking-widest text-zinc-600">
            {t("voice.controls.systemStatus")}
          </span>
          <div className="flex-1 border-t border-white/[0.05]" />
        </div>
        <RuntimeOverviewCard
          runtime={null}
          title={t("voice.controls.runtime")}
          loadingLabel={t("voice.status.channelConnecting")}
        />
        {isDevMode ? (
          <Gemma4RuntimeControl variant="voice" runtimeSnapshot={null} />
        ) : (
          <StatusCard title={t("voice.controls.runtime")}>
            <p className="text-[11px] text-zinc-400">{t("voice.controls.devRuntimeHint")}</p>
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
      {isGemma4AudioRuntime && (
        <Gemma4RuntimeControl
          variant="voice"
          runtimeSnapshot={runtime}
          assistantModels={runtime?.assistant_models ?? []}
        />
      )}
      {/* F4-04: separator between control blocks and status/diagnostic blocks */}
      <div className="flex items-center gap-3 pt-1">
        <div className="flex-1 border-t border-white/[0.05]" />
        <span className="text-[10px] uppercase tracking-widest text-zinc-600">
          {t("voice.controls.systemStatus")}
        </span>
        <div className="flex-1 border-t border-white/[0.05]" />
      </div>

      <RuntimeOverviewCard
        runtime={runtime}
        title={t("voice.controls.runtime")}
      />
      {latestVoiceSession && (
        <VoiceSessionCard session={latestVoiceSession} />
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
  const [applied, setApplied] = useState(false);
  const [activationError, setActivationError] = useState<string | null>(null);
  const didAutoSelectPreferredRuntime = useRef(false);
  const nativeVoiceRuntimeIds = useMemo(() => new Set(["multi_runtime", "gemma4_audio"]), []);
  const selectedRuntime = runtime.selectedServer ?? "";
  const selectedModel = runtime.selectedModel ?? "";
  const applyDisabled = pending || !selectedRuntime || !selectedModel;
  const runtimeError = runtime.activeServer.error ?? runtime.llmServers.error;
  const serversLoading = runtime.llmServers.loading ?? false;

  const serverOptions = useMemo(
    () => runtime.serverOptions.map((item) => ({ value: item.value, label: item.label })),
    [runtime.serverOptions],
  );
  let runtimePlaceholder = t("voice.controls.runtime");
  if (serversLoading) {
    runtimePlaceholder = t("voice.controls.loading");
  } else if (serverOptions.length === 0) {
    runtimePlaceholder = t("voice.controls.noRuntimes");
  }
  const modelOptions = useMemo(
    () => runtime.modelOptions.map((item) => ({ value: item.value, label: item.label })),
    [runtime.modelOptions],
  );

  const preferredNativeRuntime = useMemo(
    () =>
      serverOptions.find((option) => nativeVoiceRuntimeIds.has(String(option.value).trim().toLowerCase())) ??
      null,
    [nativeVoiceRuntimeIds, serverOptions],
  );

  useEffect(() => {
    if (didAutoSelectPreferredRuntime.current) {
      return;
    }
    if (!preferredNativeRuntime) {
      return;
    }
    const normalizedSelectedRuntime = selectedRuntime.trim().toLowerCase();
    const normalizedPreferredRuntime = String(preferredNativeRuntime.value).trim().toLowerCase();
    if (normalizedSelectedRuntime === normalizedPreferredRuntime) {
      didAutoSelectPreferredRuntime.current = true;
      return;
    }
    if (normalizedSelectedRuntime && nativeVoiceRuntimeIds.has(normalizedSelectedRuntime)) {
      didAutoSelectPreferredRuntime.current = true;
      return;
    }
    runtime.setSelectedServer(String(preferredNativeRuntime.value));
    didAutoSelectPreferredRuntime.current = true;
  }, [nativeVoiceRuntimeIds, preferredNativeRuntime, runtime, selectedRuntime]);

  const handleApply = async () => {
    if (applyDisabled) return;
    setPending(true);
    setActivationError(null);
    try {
      await runtime.activateRuntimeSelection(selectedRuntime, selectedModel);
      onRuntimeApplied?.();
      setApplied(true);
      setTimeout(() => setApplied(false), 2500);
    } catch (error) {
      setActivationError(resolveRuntimeActivationErrorMessage(error));
    } finally {
      setPending(false);
    }
  };

  return (
    <StatusCard title={t("voice.controls.runtime")}>
      {preferredNativeRuntime && selectedRuntime !== preferredNativeRuntime.value && (
        <p className="mb-2 text-[11px] text-amber-300">
          {t("voice.controls.runtime")} {preferredNativeRuntime.label} ma pierwszeństwo dla voice.
        </p>
      )}
      <div className="space-y-2.5">
        <div>
          <p className="text-caption mb-1">{t("voice.controls.provider")}</p>
          <SelectMenu
            value={selectedRuntime}
            options={serverOptions}
            onChange={(value) => runtime.setSelectedServer(value || null)}
            placeholder={runtimePlaceholder}
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
          <p className="text-caption mb-1">{t("voice.controls.model")}</p>
          <SelectMenu
            value={selectedModel}
            options={modelOptions}
            onChange={(value) => runtime.setSelectedModel(value || null)}
            placeholder={
              modelOptions.length === 0 && selectedRuntime
                ? t("voice.controls.loading")
                : t("voice.controls.model")
            }
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

        {applied && (
          <p className="text-[11px] text-emerald-400">{t("voice.controls.runtimeApplied")}</p>
        )}

        {activationError && (
          <p className="text-[11px] text-rose-300">
            {activationError}
          </p>
        )}

        {runtimeError && (
          <p className="text-[11px] text-rose-300 truncate">
            {String(runtimeError)}
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
  const activeVoiceRuntime = provider || model ? `${provider ?? "—"} / ${model ?? "—"}` : null;
  const runtimeProvider = String(provider ?? "").trim().toLowerCase();
  const isNativeVoiceRuntime =
    runtimeProvider.startsWith("multi_runtime") ||
    runtimeProvider.startsWith("gemma4_audio");
  const probeTone = (() => {
    if (!probeStatus) return "neutral" as const;
    if (probeStatus === "verified") return "success" as const;
    if (probeStatus === "metadata_only") return "warning" as const;
    if (probeStatus === "failed") {
      return isNativeVoiceRuntime ? ("danger" as const) : ("warning" as const);
    }
    return "neutral" as const;
  })();
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
              <Badge tone={probeTone} className="shrink-0 text-[10px]">
                {probeStatus}
              </Badge>
            )}
          </div>
          {provider && <Row label={t("voice.controls.provider")} value={provider} />}
          {activeVoiceRuntime && (
            <Row label="Runtime systemowy voice" value={activeVoiceRuntime} />
          )}
          {endpoint && <Row label={t("voice.controls.endpoint")} value={endpoint} />}
          {profile && <Row label={t("voice.controls.profile")} value={profile} />}
          {runtime.voice_pipeline?.stt && (
            <Row label={t("voice.controls.stt")} value={runtime.voice_pipeline.stt} />
          )}
          {runtime.voice_pipeline?.reasoning && (
            <Row label={t("voice.controls.pipeline")} value={runtime.voice_pipeline.reasoning} />
          )}
          {runtime.voice_pipeline?.reasoning_summary && (
            <Row
              label={t("voice.controls.reasoningStatus")}
              value={runtime.voice_pipeline.reasoning_summary}
            />
          )}
          {runtime.voice_pipeline?.emotion && (
            <Row label={t("voice.controls.emotion")} value={runtime.voice_pipeline.emotion} />
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

function VoiceSessionCard({
  session,
}: Readonly<{
  session: NonNullable<VoiceStatusUpdate["latest_voice_session"]>;
}>) {
  const t = useTranslation();
  const confidence = formatConfidence(session.emotion_confidence);
  const responseText =
    session.response_text && isGenericFailureResponse(session.response_text)
      ? t("voice.status.channelError")
      : session.response_text;

  return (
    <StatusCard title={t("voice.controls.latestSession")}>
      <div className="mb-2">
        <p className="text-sm font-semibold text-white truncate">
          {session.pipeline_id ?? t("voice.controls.noRecordingYet")}
        </p>
        {session.session_id && (
          <p className="text-[10px] text-zinc-500 truncate">{session.session_id}</p>
        )}
      </div>
      {session.voice_mode && <Row label={t("voice.controls.voiceMode")} value={session.voice_mode} />}
      {(session.audio_runtime_provider || session.audio_runtime_model) && (
        <Row
          label="Runtime odpowiedzi"
          value={`${session.audio_runtime_provider ?? "—"} / ${session.audio_runtime_model ?? "—"}`}
        />
      )}
      {session.reasoning_summary_status && (
        <Row
          label={t("voice.controls.reasoningStatus")}
          value={session.reasoning_summary_status}
        />
      )}
      {session.reasoning_summary && (
        <Row label={t("voice.controls.reasoningSummary")} value={session.reasoning_summary} />
      )}
      {session.emotion_label && (
        <Row
          label={t("voice.controls.emotion")}
          value={
            <span className="inline-flex items-center gap-1.5">
              <span>{session.emotion_label}</span>
              {confidence && <span className="text-zinc-500">{confidence}</span>}
            </span>
          }
        />
      )}
      {session.transcription && (
        <Row label={t("voice.controls.transcription")} value={session.transcription} />
      )}
      {responseText && (
        <Row label={t("voice.controls.response")} value={responseText} />
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
