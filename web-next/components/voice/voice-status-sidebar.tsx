"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectMenu } from "@/components/ui/select-menu";
import { Gemma4RuntimeControl } from "@/components/gemma4/gemma4-runtime-control";
import type { VoiceStatusUpdate } from "@/components/voice/voice-command-center";
import { useTranslation } from "@/lib/i18n";
import { canonicalRuntimeId, isMultiRuntime } from "@/lib/runtime-id";
import {
  formatVoiceRuntimeTuple,
} from "@/lib/voice-runtime-state";
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
  const runtimeAlignment = status?.runtime_alignment ?? null;
  const runtimeProvider = runtime?.provider ?? "";
  const runtimeId = runtime?.runtime_id ?? "";
  const isGemma4AudioRuntime = isMultiRuntime(runtimeProvider) || isMultiRuntime(runtimeId);

  if (!status) {
    return (
      <div className="space-y-3">
        <RuntimeSwitchCard onRuntimeApplied={onRuntimeApplied} />
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
      <RuntimeSwitchCard onRuntimeApplied={onRuntimeApplied} />
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
        <VoiceSessionCard session={latestVoiceSession} runtimeAlignment={runtimeAlignment} />
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

function RuntimeSwitchCard({
  onRuntimeApplied,
}: Readonly<{ onRuntimeApplied?: () => void }>) {
  const t = useTranslation();
  const runtime = useRuntime();
  const [pending, setPending] = useState(false);
  const [applied, setApplied] = useState(false);
  const [voiceRoutePending, setVoiceRoutePending] = useState(false);
  const [voiceRouteApplied, setVoiceRouteApplied] = useState(false);
  const [activationError, setActivationError] = useState<string | null>(null);
  const [voiceRouteError, setVoiceRouteError] = useState<string | null>(null);
  const [voiceRouteProfile, setVoiceRouteProfile] = useState("auto");
  const [audioDecoderProfile, setAudioDecoderProfile] = useState("auto");
  const [audioDecoderChain, setAudioDecoderChain] = useState("");
  const runtimeAppliedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const voiceRouteAppliedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const selectedRuntime = runtime.selectedServer ?? "";
  const selectedModel = runtime.selectedModel ?? "";
  const runtimeStateView = runtime.runtimeState;
  const selectedRuntimeSummary = formatVoiceRuntimeTuple(
    runtimeStateView.selected.runtimeId,
    runtimeStateView.selected.modelName,
  );
  const activeRuntimeId =
    runtimeStateView.active.runtimeId || runtime.activeServer.data?.active_server || null;
  const activeRuntimeModel =
    runtimeStateView.active.modelName || runtime.activeServer.data?.active_model || null;
  const activeRuntimeSummary = formatVoiceRuntimeTuple(
    activeRuntimeId,
    activeRuntimeModel,
  );
  const gateSwitching = runtimeStateView.switch.state === "switching" || runtime.runtimeSwitchInProgress;
  const applyDisabled = pending || gateSwitching || !selectedRuntime || !selectedModel;
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

  useEffect(() => {
    return () => {
      if (runtimeAppliedTimerRef.current) {
        clearTimeout(runtimeAppliedTimerRef.current);
      }
      if (voiceRouteAppliedTimerRef.current) {
        clearTimeout(voiceRouteAppliedTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const loadVoiceRoute = async () => {
      try {
        const response = await fetch("/api/v1/audio/routes/profile");
        if (!response.ok) return;
        const payload = (await response.json()) as {
          voice_route_profile?: string;
          audio_decoder_profile?: string;
          audio_decoder_chain?: string[];
        };
        const loadedVoiceRouteProfile = payload.voice_route_profile ?? "auto";
        const loadedAudioDecoderProfile = payload.audio_decoder_profile ?? "auto";
        const loadedAudioDecoderChain = payload.audio_decoder_chain ?? [];
        setVoiceRouteProfile(loadedVoiceRouteProfile);
        setAudioDecoderProfile(loadedAudioDecoderProfile);
        setAudioDecoderChain(loadedAudioDecoderChain.join(","));

        if (loadedVoiceRouteProfile === "chat_tekstowy") {
          const fallbackVoiceRouteProfile = "auto";
          setVoiceRouteProfile(fallbackVoiceRouteProfile);
          await fetch("/api/v1/audio/routes/profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              voice_route_profile: fallbackVoiceRouteProfile,
              audio_decoder_profile: loadedAudioDecoderProfile,
              audio_decoder_chain: loadedAudioDecoderChain,
            }),
          });
          onRuntimeApplied?.();
        }
      } catch {
        // Best effort diagnostics panel. Runtime controls remain usable.
      }
    };
    loadVoiceRoute().catch(() => undefined);
  }, [onRuntimeApplied]);

  const handleApply = async () => {
    if (applyDisabled) return;
    setPending(true);
    setActivationError(null);
    try {
      await runtime.activateRuntimeSelection(selectedRuntime, selectedModel);
      onRuntimeApplied?.();
      setApplied(true);
      if (runtimeAppliedTimerRef.current) {
        clearTimeout(runtimeAppliedTimerRef.current);
      }
      runtimeAppliedTimerRef.current = setTimeout(() => {
        setApplied(false);
        runtimeAppliedTimerRef.current = null;
      }, 2500);
    } catch (error) {
      setActivationError(
        resolveRuntimeActivationErrorMessage(error, t("models.toasts.activateError")),
      );
    } finally {
      setPending(false);
    }
  };

  const handleVoiceRouteApply = async () => {
    setVoiceRoutePending(true);
    setVoiceRouteError(null);
    try {
      const chain = audioDecoderChain
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const response = await fetch("/api/v1/audio/routes/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          voice_route_profile: voiceRouteProfile,
          audio_decoder_profile: audioDecoderProfile,
          audio_decoder_chain: chain,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail || `HTTP ${response.status}`);
      }
      setVoiceRouteApplied(true);
      if (voiceRouteAppliedTimerRef.current) {
        clearTimeout(voiceRouteAppliedTimerRef.current);
      }
      voiceRouteAppliedTimerRef.current = setTimeout(() => {
        setVoiceRouteApplied(false);
        voiceRouteAppliedTimerRef.current = null;
      }, 2500);
      onRuntimeApplied?.();
    } catch (error) {
      setVoiceRouteError(String(error instanceof Error ? error.message : error));
    } finally {
      setVoiceRoutePending(false);
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
          {pending || gateSwitching ? t("voice.controls.refreshing") : t("voice.controls.refresh")}
        </Button>
        {gateSwitching && (
          <p className="text-[11px] text-amber-300">
            {t("voice.controls.runtimeSwitchInProgress")
              .replace("{{from}}", runtimeStateView.switch.fromRuntime || "—")
              .replace("{{to}}", runtimeStateView.switch.toRuntime || "—")}
          </p>
        )}
        {!gateSwitching && runtime.lastRuntimeSwitch?.at_utc && (
          <p className="text-[11px] text-zinc-400">
            {t("voice.controls.runtimeLastSwitch").replace(
              "{{at}}",
              runtime.lastRuntimeSwitch.at_utc,
            )}
          </p>
        )}
        <Row label={t("voice.controls.selectedRuntime")} value={selectedRuntimeSummary} />
        <Row label={t("voice.controls.systemVoiceRuntime")} value={activeRuntimeSummary} />
        <Row
          label={t("voice.controls.runtimeState")}
          value={runtimeStateView.switch.state}
        />

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

        <div className="border-t border-white/[0.06] pt-2">
          <p className="text-caption mb-1">{t("voice.controls.voiceRouteProfile")}</p>
          <SelectMenu
            value={voiceRouteProfile}
            options={[
              { value: "auto", label: "auto" },
              { value: "gemma4", label: "gemma4" },
              { value: "runtime_lokalny", label: "runtime_lokalny" },
              { value: "venom-agent", label: "venom-agent" },
              { value: "chat_tekstowy", label: "chat_tekstowy" },
            ]}
            onChange={(value) => setVoiceRouteProfile(value || "auto")}
            className="w-full"
            disabled={voiceRoutePending}
          />
          <p className="text-caption mt-2 mb-1">{t("voice.controls.audioDecoderProfile")}</p>
          <SelectMenu
            value={audioDecoderProfile}
            options={[
              { value: "auto", label: "auto" },
              { value: "gemma_native", label: "gemma_native" },
              { value: "faster_whisper", label: "faster_whisper" },
              { value: "hybrid", label: "hybrid" },
            ]}
            onChange={(value) => setAudioDecoderProfile(value || "auto")}
            className="w-full"
            disabled={voiceRoutePending}
          />
          <p className="text-caption mt-2 mb-1">{t("voice.controls.audioDecoderChain")}</p>
          <input
            value={audioDecoderChain}
            onChange={(event) => setAudioDecoderChain(event.target.value)}
            className="w-full rounded-full border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-3 py-1.5 text-xs text-[color:var(--text-primary)]"
            placeholder="gemma_native,faster_whisper"
            disabled={voiceRoutePending}
          />
          <Button
            type="button"
            size="xs"
            variant="outline"
            onClick={handleVoiceRouteApply}
            disabled={voiceRoutePending}
            className="mt-2 w-full"
          >
            {voiceRoutePending ? t("voice.controls.refreshing") : t("voice.controls.applyVoiceRoute")}
          </Button>
          {voiceRouteApplied ? (
            <p className="text-[11px] text-emerald-400">{t("voice.controls.voiceRouteApplied")}</p>
          ) : null}
          {voiceRouteError ? (
            <p className="text-[11px] text-rose-300">{voiceRouteError}</p>
          ) : null}
        </div>
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
  const provider = canonicalRuntimeId(runtime?.provider ?? runtime?.runtime_id ?? "");
  const model = runtime?.model_name ?? null;
  const endpoint = runtime?.endpoint ?? null;
  const probeStatus = runtime?.runtime_capabilities?.probe_status ?? null;
  const activeVoiceRuntime = provider || model ? formatVoiceRuntimeTuple(provider, model) : null;
  const runtimeProvider = String(provider ?? "").trim().toLowerCase();
  const isNativeVoiceRuntime =
    isMultiRuntime(runtimeProvider);
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
              {formatVoiceRuntimeTuple(provider, model ?? t("voice.controls.unknownModel"))}
            </span>
            {probeStatus && (
              <Badge tone={probeTone} className="shrink-0 text-[10px]">
                {probeStatus}
              </Badge>
            )}
          </div>
          {activeVoiceRuntime && <Row label={t("voice.controls.runtime")} value={activeVoiceRuntime} />}
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
  runtimeAlignment,
}: Readonly<{
  session: NonNullable<VoiceStatusUpdate["latest_voice_session"]>;
  runtimeAlignment?: VoiceStatusUpdate["runtime_alignment"] | null;
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
          label={t("voice.controls.responseRuntime")}
          value={
            runtimeAlignment?.response_runtime_fresh === false
              ? `${formatVoiceRuntimeTuple(session.audio_runtime_provider, session.audio_runtime_model)} (${t("voice.controls.previousSession")})`
              : formatVoiceRuntimeTuple(session.audio_runtime_provider, session.audio_runtime_model)
          }
        />
      )}
      {runtimeAlignment?.response_runtime_fresh === false && (
        <p className="text-[11px] text-amber-300">
          {t("voice.controls.runtimeAfterSwitch")}
        </p>
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
      {session.transcription_used_for_generation && (
        <Row
          label={t("voice.controls.transcriptionUsedForGeneration")}
          value={session.transcription_used_for_generation}
        />
      )}
      {session.trace_inconsistent ? (
        <p className="text-[11px] text-rose-300">
          {t("voice.controls.traceInconsistent")}
        </p>
      ) : null}
      {session.request_id && (
        <Row label={t("voice.controls.requestId")} value={session.request_id} />
      )}
      {session.trace_id && (
        <Row label={t("voice.controls.traceId")} value={session.trace_id} />
      )}
      {session.audio_hash && (
        <Row label={t("voice.controls.audioHash")} value={session.audio_hash} />
      )}
      {session.voice_pipeline_mode && (
        <Row label={t("voice.controls.pipelineMode")} value={session.voice_pipeline_mode} />
      )}
      {session.voice_route_profile && (
        <Row label={t("voice.controls.voiceRouteProfile")} value={session.voice_route_profile} />
      )}
      {session.audio_decoder_profile && (
        <Row label={t("voice.controls.audioDecoderProfile")} value={session.audio_decoder_profile} />
      )}
      {session.decoder_selected && (
        <Row label={t("voice.controls.decoderSelected")} value={session.decoder_selected} />
      )}
      {session.decoder_effective && (
        <Row label={t("voice.controls.decoderEffective")} value={session.decoder_effective} />
      )}
      {session.decoder_fallback_reason && (
        <Row label={t("voice.controls.decoderFallbackReason")} value={session.decoder_fallback_reason} />
      )}
      {session.native_audio_ms != null && (
        <Row
          label={t("voice.controls.nativeAudio")}
          value={`${(session.native_audio_ms / 1000).toFixed(2)}s`}
        />
      )}
      {session.execution_trace_annotations?.length ? (
        <Row
          label={t("voice.controls.traceSemantics")}
          value={session.execution_trace_annotations
            .map((item) => `${item.label ?? item.stage ?? t("voice.controls.stage")}:${item.status ?? t("common.unknown")}`)
            .join(" · ")}
        />
      ) : null}
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
