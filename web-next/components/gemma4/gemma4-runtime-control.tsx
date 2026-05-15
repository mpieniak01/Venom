"use client";

import { useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectMenu, type SelectMenuOption } from "@/components/ui/select-menu";
import {
  ConfirmDialog,
  ConfirmDialogActions,
  ConfirmDialogContent,
  ConfirmDialogDescription,
  ConfirmDialogTitle,
  ConfirmDialogTrigger,
} from "@/components/ui/confirm-dialog";
import { Switch } from "@/components/ui/switch";
import { useTranslation } from "@/lib/i18n";
import type {
  DaemonConfigRequest,
  DaemonRespondResponse,
  DaemonStatus,
} from "@/lib/gemma4-daemon-api";
import { postDaemonRespond } from "@/lib/gemma4-daemon-api";
import { PipelineDiagnosticsPanel } from "@/components/gemma4/pipeline-diagnostics-panel";
import { getGemma4ApiBaseUrl } from "@/lib/env";
import { type Gemma4DaemonState, useGemma4Daemon } from "@/hooks/use-gemma4-daemon";
import {
  type MultiRuntimeProfileUpdateRequest,
  useMultiRuntimeProfile,
} from "@/hooks/use-multi-runtime-profile";

const CACHE_OPTIONS = [
  { value: "", label: "default" },
  { value: "static", label: "static" },
  { value: "quantized", label: "quantized" },
  { value: "offloaded_static", label: "offloaded_static" },
] as const;

const PROFILE_CACHE_OPTIONS = [
  { value: "", labelKey: "runtime.profile.cacheDefaultFramework" },
  { value: "static", labelKey: "runtime.profile.cacheStatic" },
  { value: "dynamic", labelKey: "runtime.profile.cacheDynamic" },
  { value: "offloaded", labelKey: "runtime.profile.cacheOffloaded" },
] as const;

const PROFILE_EXECUTION_MODE_OPTIONS = [
  { value: "balanced", labelKey: "runtime.profile.executionModeBalanced" },
  { value: "vision_priority", labelKey: "runtime.profile.executionModeVisionPriority" },
  { value: "voice_priority", labelKey: "runtime.profile.executionModeVoicePriority" },
] as const;

const PROFILE_IMAGE_STRATEGY_OPTIONS = [
  { value: "vlm_only", labelKey: "runtime.profile.imageStrategyVlmOnly" },
  { value: "ocr_first", labelKey: "runtime.profile.imageStrategyOcrFirst" },
  { value: "hybrid", labelKey: "runtime.profile.imageStrategyHybrid" },
] as const;

const PROFILE_RETRIEVAL_MODE_OPTIONS = [
  { value: "off", labelKey: "runtime.profile.retrievalModeOff" },
  { value: "auto", labelKey: "runtime.profile.retrievalModeAuto" },
  { value: "always", labelKey: "runtime.profile.retrievalModeAlways" },
] as const;

const PROFILE_AUDIO_OUTPUT_MODE_OPTIONS = [
  { value: "off", labelKey: "runtime.profile.audioOutputModeOff" },
  { value: "text_first", labelKey: "runtime.profile.audioOutputModeTextFirst" },
  { value: "voice_first", labelKey: "runtime.profile.audioOutputModeVoiceFirst" },
] as const;

const PROFILE_ASSISTANT_MODE_OPTIONS = [
  { value: "off", labelKey: "runtime.profile.assistantModeOff" },
  { value: "attached", labelKey: "runtime.profile.assistantModeAttached" },
  { value: "conditional", labelKey: "runtime.profile.assistantModeConditional" },
] as const;

const PROFILE_ECONOMY_MODE_OPTIONS = [
  { value: "off", labelKey: "runtime.profile.economyModeOff" },
  { value: "auto", labelKey: "runtime.profile.economyModeAuto" },
] as const;

type Variant = "cockpit" | "voice";

type RuntimeSnapshotLike = Readonly<{
  runtime_id?: string | null;
  provider?: string | null;
  model_name?: string | null;
  endpoint?: string | null;
  config_hash?: string | null;
  runtime_capabilities?: {
    compatibility_profile?: string | null;
    probe_status?: string | null;
    capabilities?: Record<string, boolean | string | null | undefined>;
    probes?: Record<string, { status?: string | null; reason?: string | null }>;
    fallbacks?: Record<string, string | null | undefined>;
  } | null;
  voice_pipeline?: {
      profile?: string | null;
      stt?: string | null;
      reasoning?: string | null;
      reasoning_summary?: string | null;
      emotion?: string | null;
      tools?: string | null;
      vision?: string | null;
      tts?: string | null;
    notes?: string[] | null;
  } | null;
  error?: string | null;
}> | null;

type Props = Readonly<{
  variant?: Variant;
  pollingIntervalMs?: number;
  runtimeSnapshot?: RuntimeSnapshotLike;
  assistantModels?: string[];
}>;

export function Gemma4RuntimeControl({
  variant = "voice",
  pollingIntervalMs,
  runtimeSnapshot = null,
  assistantModels = [],
}: Props) {
  const daemon = useGemma4Daemon(pollingIntervalMs);
  return (
    <Gemma4RuntimeControlInner
      daemon={daemon}
      variant={variant}
      runtimeSnapshot={runtimeSnapshot}
      assistantModels={assistantModels}
    />
  );
}

type InnerProps = Readonly<{
  daemon: Gemma4DaemonState;
  variant: Variant;
  runtimeSnapshot?: RuntimeSnapshotLike;
  assistantModels?: string[];
}>;

export function Gemma4RuntimeControlInner(props: InnerProps) {
  return <Gemma4RuntimeControlPanel {...props} />;
}

// ---------------------------------------------------------------------------
// Image probe diagnostics sub-component (extracted to reduce parent complexity)
// ---------------------------------------------------------------------------

type ImageProbeDiagnostics = {
  executionTrace: string[];
  selectedPolicy: string | null;
  selectedImageStrategy: string | null;
  retrievalUsed: boolean;
  retrievalContextItems: number;
  retrievalRoute: string | null;
  assistantUsed: boolean;
  economyModeActivated: boolean;
  degradationReasons: string[];
};

type ImageProbeSectionProps = Readonly<{
  busy: boolean;
  imageProbePending: boolean;
  imageUrlInput: string;
  imageDataInput: string | null;
  imageFileName: string | null;
  imagePromptInput: string;
  imageProbeResult: string | null;
  imageProbeDiagnostics: ImageProbeDiagnostics | null;
  imageProbeError: string | null;
  imageFileInputRef: RefObject<HTMLInputElement | null>;
  onFileChange: (files: FileList | null) => Promise<void>;
  onImageUrlChange: (url: string) => void;
  onImagePromptChange: (prompt: string) => void;
  onClearImageData: () => void;
  onProbe: () => void;
}>;

function ImageProbeSection({
  busy,
  imageProbePending,
  imageUrlInput,
  imageDataInput,
  imageFileName,
  imagePromptInput,
  imageProbeResult,
  imageProbeDiagnostics,
  imageProbeError,
  imageFileInputRef,
  onFileChange,
  onImageUrlChange,
  onImagePromptChange,
  onClearImageData,
  onProbe,
}: ImageProbeSectionProps) {
  const t = useTranslation();
  const hasResult = !!(imageProbeResult || imageProbeDiagnostics || imageProbeError);
  return (
    <div className="space-y-2">
        <button
          type="button"
          onDragOver={(event) => { event.preventDefault(); }}
          onDrop={async (event) => {
            event.preventDefault();
            await onFileChange(event.dataTransfer.files);
            if (event.dataTransfer.files.item(0)) onImageUrlChange("");
          }}
          onClick={() => imageFileInputRef.current?.click()}
          className={`w-full rounded-lg border border-dashed px-3 py-3 text-center text-[11px] flex flex-col items-center gap-1.5 transition-colors ${
            imageDataInput
              ? "border-emerald-500/40 bg-emerald-500/[0.04] text-emerald-400"
              : "border-white/20 bg-white/[0.02] text-zinc-400 hover:border-white/40 hover:bg-white/[0.04]"
          }`}
          aria-label={t("voice.daemon.dragDropImage")}
        >
          {imageDataInput ? (
            <>
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
              <span className="truncate max-w-full">{imageFileName ?? t("voice.daemon.fileLoaded")}</span>
            </>
          ) : (
            <>
              <svg className="h-5 w-5 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
              </svg>
              <span>{t("voice.daemon.dragDropImage")}</span>
            </>
          )}
        </button>
        <div className="flex items-center gap-2">
          <Button
            size="xs"
            variant="ghost"
            onClick={() => imageFileInputRef.current?.click()}
            disabled={busy || imageProbePending}
          >
            {t("voice.daemon.chooseImageFromDisk")}
          </Button>
          {imageDataInput && (
            <Button size="xs" variant="ghost" onClick={onClearImageData} disabled={busy || imageProbePending}>
              {t("voice.daemon.clearImageFile")}
            </Button>
          )}
          <input
            ref={imageFileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={async (e) => {
              await onFileChange(e.currentTarget.files);
              if (e.currentTarget.files?.item(0)) onImageUrlChange("");
              e.currentTarget.value = "";
            }}
          />
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 mb-0.5">{t("voice.daemon.imageUrl")}</p>
          <input
            type="url"
            value={imageUrlInput}
            onChange={(e) => onImageUrlChange(e.target.value)}
            placeholder={imageDataInput ? t("voice.daemon.fileSelectedUrlDisabled") : t("voice.daemon.imageUrlPlaceholder")}
            disabled={busy || imageProbePending || !!imageDataInput}
            className="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
            aria-label={t("voice.daemon.imageUrl")}
          />
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 mb-0.5">{t("voice.daemon.imagePrompt")}</p>
          <input
            type="text"
            value={imagePromptInput}
            onChange={(e) => onImagePromptChange(e.target.value)}
            placeholder={t("voice.daemon.imagePromptPlaceholder")}
            disabled={busy || imageProbePending}
            className="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
            aria-label={t("voice.daemon.imagePrompt")}
          />
        </div>
        <Button
          size="xs"
          variant="primary"
          onClick={onProbe}
          disabled={busy || imageProbePending || (!imageUrlInput.trim() && !imageDataInput)}
        >
          {imageProbePending ? t("voice.daemon.imageProbeRunning") : t("voice.daemon.runImageProbe")}
        </Button>
        {hasResult && (
          <div className="mt-2 rounded-lg border border-white/[0.08] bg-white/[0.02] p-2.5 space-y-1.5">
            <p className="text-[10px] uppercase tracking-widest text-zinc-500">
              {t("voice.daemon.probeResult")}
            </p>
            {imageProbeResult && (
              <p className="text-[11px] text-zinc-300 whitespace-pre-wrap">{imageProbeResult}</p>
            )}
            {imageProbeDiagnostics && (
              <details className="text-[10px] text-zinc-400">
                <summary className="cursor-pointer text-zinc-500 hover:text-zinc-300 transition-colors">
                  {t("voice.daemon.probeDiagnostics")}
                </summary>
                <div className="mt-1 space-y-1">
                  <p><span className="text-zinc-500">selected_policy:</span> {imageProbeDiagnostics.selectedPolicy ?? "—"}</p>
                  <p><span className="text-zinc-500">image_strategy:</span> {imageProbeDiagnostics.selectedImageStrategy ?? "—"}</p>
                  <p><span className="text-zinc-500">trace:</span> {imageProbeDiagnostics.executionTrace.join(" → ") || "—"}</p>
                  <p>
                    <span className="text-zinc-500">retrieval_used:</span>{" "}
                    {imageProbeDiagnostics.retrievalUsed ? "yes" : "no"}{" · "}
                    <span className="text-zinc-500">retrieval_route:</span>{" "}
                    {imageProbeDiagnostics.retrievalRoute ?? "—"}{" · "}
                    <span className="text-zinc-500">retrieval_items:</span>{" "}
                    {imageProbeDiagnostics.retrievalContextItems}{" · "}
                    <span className="text-zinc-500">assistant_used:</span>{" "}
                    {imageProbeDiagnostics.assistantUsed ? "yes" : "no"}{" · "}
                    <span className="text-zinc-500">economy_mode:</span>{" "}
                    {imageProbeDiagnostics.economyModeActivated ? "on" : "off"}
                  </p>
                  {imageProbeDiagnostics.degradationReasons.length > 0 && (
                    <p>
                      <span className="text-zinc-500">degradations:</span>{" "}
                      {imageProbeDiagnostics.degradationReasons.join(" | ")}
                    </p>
                  )}
                </div>
              </details>
            )}
            {imageProbeError && (
              <p className="text-[10px] text-rose-400 break-all">{imageProbeError}</p>
            )}
          </div>
        )}
    </div>
  );
}

export function ImageProbeCard() {
  const t = useTranslation();
  const daemon = useGemma4Daemon();
  const { status, actionPending } = daemon;
  const busy = actionPending !== null;

  const [imageUrlInput, setImageUrlInput] = useState("");
  const [imageDataInput, setImageDataInput] = useState<string | null>(null);
  const [imageFileName, setImageFileName] = useState<string | null>(null);
  const [imagePromptInput, setImagePromptInput] = useState("");
  const [imageProbePending, setImageProbePending] = useState(false);
  const [imageProbeResult, setImageProbeResult] = useState<string | null>(null);
  const [imageProbeDiagnostics, setImageProbeDiagnostics] = useState<ImageProbeDiagnostics | null>(null);
  const [imageProbeError, setImageProbeError] = useState<string | null>(null);
  const [lastPipelineResponse, setLastPipelineResponse] = useState<DaemonRespondResponse | null>(null);
  const imageFileInputRef = useRef<HTMLInputElement | null>(null);

  if (!status?.supports_image_input) return null;

  const handleImageProbe = () =>
    handleRuntimeImageProbe({
      imageUrlInput,
      imageDataInput,
      imagePromptInput,
      imageProbePending,
      maxNewTokens: status.params.max_new_tokens ?? 128,
      setImageProbeResult,
      setImageProbeDiagnostics,
      setImageProbeError,
      setImageProbePending,
      setLastPipelineResponse,
    });

  const handleImageFileChange = (fileList: FileList | null) =>
    handleRuntimeImageFileSelection({
      fileList,
      setImageProbeError,
      setImageDataInput,
      setImageFileName,
    });

  const imageBudget = status.params.image_token_budget;

  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] p-3 text-xs text-zinc-300">
      <div className="flex items-center justify-between mb-2">
        <p className="eyebrow">{t("voice.daemon.imageInput")}</p>
        <span className="text-[10px] text-zinc-500">
          {t("voice.daemon.imageBudgetShort")}: {imageBudget}
        </span>
      </div>
      <ImageProbeSection
        busy={busy}
        imageProbePending={imageProbePending}
        imageUrlInput={imageUrlInput}
        imageDataInput={imageDataInput}
        imageFileName={imageFileName}
        imagePromptInput={imagePromptInput}
        imageProbeResult={imageProbeResult}
        imageProbeDiagnostics={imageProbeDiagnostics}
        imageProbeError={imageProbeError}
        imageFileInputRef={imageFileInputRef}
        onFileChange={handleImageFileChange}
        onImageUrlChange={setImageUrlInput}
        onImagePromptChange={setImagePromptInput}
        onClearImageData={() => { setImageDataInput(null); setImageFileName(null); }}
        onProbe={handleImageProbe}
      />
      {lastPipelineResponse && (
        <PipelineDiagnosticsPanel response={lastPipelineResponse} />
      )}
    </div>
  );
}

function ProfileModeBadge({ mode }: Readonly<{ mode: string }>) {
  const t = useTranslation();
  const badge = getProfileModeBadgeConfig(mode, t);
  const variant = badge.variant;
  const label = badge.label;
  return <Badge variant={variant}>{label}</Badge>;
}

function getProfileModeBadgeConfig(
  mode: string,
  t: ReturnType<typeof useTranslation>,
): Readonly<{ variant: "default" | "secondary" | "destructive" | "outline"; label: string }> {
  switch (mode) {
    case "live":
      return { variant: "default", label: t("runtime.profile.applyModeLive") };
    case "soft_reload":
      return { variant: "secondary", label: t("runtime.profile.applyModeSoftReload") };
    case "hard_restart":
      return { variant: "destructive", label: t("runtime.profile.applyModeHardRestart") };
    case "unsupported":
      return { variant: "outline", label: t("runtime.profile.applyModeUnsupported") };
    default:
      return { variant: "outline", label: mode };
  }
}

function RuntimeProfileControls({
  daemonStatus,
}: Readonly<{ daemonStatus: DaemonStatus | null }>) {
  const t = useTranslation();
  const profileState = useMultiRuntimeProfile();
  const { data, updatePending, lastUpdateResult, applyUpdate } = profileState;
  const profile = data?.profile ?? null;
  const matrix = data?.apply_matrix ?? null;
  const busy = updatePending;

  const [localExecutionMode, setLocalExecutionMode] = useState<string | null>(null);
  const [localImageStrategy, setLocalImageStrategy] = useState<string | null>(null);
  const [localRetrievalMode, setLocalRetrievalMode] = useState<string | null>(null);
  const [localAudioOutputMode, setLocalAudioOutputMode] = useState<string | null>(null);
  const [localAssistantMode, setLocalAssistantMode] = useState<string | null>(null);
  const [localEconomyMode, setLocalEconomyMode] = useState<string | null>(null);
  const [localCache, setLocalCache] = useState<string | null>(null);
  const [localPrecision, setLocalPrecision] = useState<string | null>(null);
  const [localQuantizationBackend, setLocalQuantizationBackend] = useState<string | null>(null);
  const [localDeviceTarget, setLocalDeviceTarget] = useState<string | null>(null);

  const profileCacheOptions = useMemo(
    () =>
      PROFILE_CACHE_OPTIONS.map((option) => ({
        value: option.value,
        label: t(option.labelKey),
      })),
    [t],
  );
  const profileExecutionModeOptions = useMemo(
    () =>
      PROFILE_EXECUTION_MODE_OPTIONS.map((option) => ({
        value: option.value,
        label: t(option.labelKey),
      })),
    [t],
  );
  const profileImageStrategyOptions = useMemo(
    () =>
      PROFILE_IMAGE_STRATEGY_OPTIONS.map((option) => ({
        value: option.value,
        label: t(option.labelKey),
      })),
    [t],
  );
  const profileRetrievalModeOptions = useMemo(
    () =>
      PROFILE_RETRIEVAL_MODE_OPTIONS.map((option) => ({
        value: option.value,
        label: t(option.labelKey),
      })),
    [t],
  );
  const profileAudioOutputModeOptions = useMemo(
    () =>
      PROFILE_AUDIO_OUTPUT_MODE_OPTIONS.map((option) => ({
        value: option.value,
        label: t(option.labelKey),
      })),
    [t],
  );
  const profileAssistantModeOptions = useMemo(
    () =>
      PROFILE_ASSISTANT_MODE_OPTIONS.map((option) => ({
        value: option.value,
        label: t(option.labelKey),
      })),
    [t],
  );
  const profileEconomyModeOptions = useMemo(
    () =>
      PROFILE_ECONOMY_MODE_OPTIONS.map((option) => ({
        value: option.value,
        label: t(option.labelKey),
      })),
    [t],
  );

  // Quantization options derived from backend-reported supported_options
  const precisionOptions = useMemo<SelectMenuOption[]>(
    () =>
      (data?.supported_options?.precision ?? ["auto", "float16", "bfloat16", "float32", "int8", "int4"]).map(
        (v) => ({ value: v, label: v }),
      ),
    [data?.supported_options?.precision],
  );
  const deviceTargetOptions = useMemo<SelectMenuOption[]>(
    () =>
      (data?.supported_options?.device_target ?? ["auto", "cpu", "cuda"]).map(
        (v) => ({ value: v, label: v }),
      ),
    [data?.supported_options?.device_target],
  );
  const quantizationBackendOptions = useMemo<SelectMenuOption[]>(
    () =>
      (data?.supported_options?.quantization_backend ?? [null, "bitsandbytes"]).map(
        (v) => ({ value: v ?? "", label: v ?? t("runtime.profile.quantizationBackendNone") }),
      ),
    [data?.supported_options?.quantization_backend, t],
  );

  const effectiveState = resolveRuntimeProfileEffectiveState({
    profile,
    localExecutionMode,
    localImageStrategy,
    localRetrievalMode,
    localAudioOutputMode,
    localAssistantMode,
    localEconomyMode,
    localCache,
    localPrecision,
    localQuantizationBackend,
    localDeviceTarget,
  });
  const {
    effectiveExecutionMode,
    effectiveImageStrategy,
    effectiveRetrievalMode,
    effectiveAudioOutputMode,
    effectiveAssistantMode,
    effectiveEconomyMode,
    effectiveCache,
    effectivePrecision,
    effectiveQuantizationBackend,
    effectiveDeviceTarget,
  } = effectiveState;
  const stagedConfig = daemonStatus?.staged_runtime_config ?? daemonStatus?.params ?? null;
  const activeConfig = daemonStatus?.active_runtime_config ?? daemonStatus?.params ?? null;
  const stagedRuntimeLine = stagedConfig
    ? `${stagedConfig.precision}/${stagedConfig.quantization_backend ?? "none"}/${stagedConfig.device_target}`
    : "—";
  const activeRuntimeLine = activeConfig
    ? `${activeConfig.precision}/${activeConfig.quantization_backend ?? "none"}/${activeConfig.device_target}`
    : "—";
  const runtimeConfigDrift = hasRuntimeConfigDrift(stagedRuntimeLine, activeRuntimeLine);
  const quantizationInactiveReason = getQuantizationInactiveReason(daemonStatus);

  const handleApplyPolicy = async () => {
    await applyUpdate({
      execution_mode:
        effectiveExecutionMode as MultiRuntimeProfileUpdateRequest["execution_mode"],
      image_strategy:
        effectiveImageStrategy as MultiRuntimeProfileUpdateRequest["image_strategy"],
      retrieval_mode:
        effectiveRetrievalMode as MultiRuntimeProfileUpdateRequest["retrieval_mode"],
      audio_output_mode:
        effectiveAudioOutputMode as MultiRuntimeProfileUpdateRequest["audio_output_mode"],
      assistant_mode:
        effectiveAssistantMode as MultiRuntimeProfileUpdateRequest["assistant_mode"],
      economy_mode:
        effectiveEconomyMode as MultiRuntimeProfileUpdateRequest["economy_mode"],
    });
  };

  const handleApplyCacheImpl = async () => {
    await applyUpdate({
      cache_implementation: effectiveCache === "" ? null : effectiveCache,
    });
  };

  const handleApplyQuantization = async () => {
    await applyUpdate({
      precision: effectivePrecision,
      quantization_backend: effectiveQuantizationBackend === "" ? null : effectiveQuantizationBackend,
      device_target: effectiveDeviceTarget,
    });
  };

  if (!data) {
    return null;
  }

  return (
    <section className="mt-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 space-y-3" data-testid="runtime-profile-inline">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <p className="text-[10px] uppercase tracking-widest text-zinc-500">{t("runtime.profile.title")}</p>
          {matrix && <ProfileModeBadge mode={matrix.execution_mode} />}
        </div>
        {data.daemon_reachable === true ? (
          <Badge variant="default" className="text-[10px]">
            {t("runtime.profile.daemonOnline")}
          </Badge>
        ) : (
          <span className="text-[10px] text-zinc-500">{t("runtime.profile.daemonOffline")}</span>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
            {t("runtime.profile.executionPolicy")}
          </span>
          {matrix && <ProfileModeBadge mode={matrix.execution_mode} />}
        </div>
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5 space-y-2">
          <RuntimeProfileRow label={t("runtime.profile.executionMode")}>
            <SelectMenu
              value={effectiveExecutionMode}
              options={profileExecutionModeOptions}
              onChange={setLocalExecutionMode}
              disabled={busy}
            />
          </RuntimeProfileRow>
          <RuntimeProfileRow label={t("runtime.profile.imageStrategy")}>
            <SelectMenu
              value={effectiveImageStrategy}
              options={profileImageStrategyOptions}
              onChange={setLocalImageStrategy}
              disabled={busy}
            />
          </RuntimeProfileRow>
          <RuntimeProfileRow label={t("runtime.profile.retrievalMode")}>
            <SelectMenu
              value={effectiveRetrievalMode}
              options={profileRetrievalModeOptions}
              onChange={setLocalRetrievalMode}
              disabled={busy}
            />
          </RuntimeProfileRow>
          <RuntimeProfileRow label={t("runtime.profile.audioOutputMode")}>
            <SelectMenu
              value={effectiveAudioOutputMode}
              options={profileAudioOutputModeOptions}
              onChange={setLocalAudioOutputMode}
              disabled={busy}
            />
          </RuntimeProfileRow>
          <RuntimeProfileRow label={t("runtime.profile.assistantMode")}>
            <SelectMenu
              value={effectiveAssistantMode}
              options={profileAssistantModeOptions}
              onChange={setLocalAssistantMode}
              disabled={busy}
            />
          </RuntimeProfileRow>
          <RuntimeProfileRow label={t("runtime.profile.economyMode")}>
            <SelectMenu
              value={effectiveEconomyMode}
              options={profileEconomyModeOptions}
              onChange={setLocalEconomyMode}
              disabled={busy}
            />
          </RuntimeProfileRow>
        </div>
        <Button
          size="xs"
          variant="secondary"
          className="w-full"
          onClick={handleApplyPolicy}
          disabled={busy || !data.daemon_reachable}
        >
          {busy ? t("runtime.profile.applying") : t("runtime.profile.applyPolicy")}
        </Button>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
            {t("runtime.profile.cacheImpl")}
          </span>
          {matrix && <ProfileModeBadge mode={matrix.cache_implementation} />}
        </div>
        <SelectMenu
          value={effectiveCache}
          options={profileCacheOptions}
          onChange={setLocalCache}
          disabled={busy}
        />
        <Button
          size="xs"
          className="w-full"
          onClick={handleApplyCacheImpl}
          disabled={busy || !data.daemon_reachable}
        >
          {t("runtime.profile.stageCacheReload")}
        </Button>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
            {t("runtime.profile.quantizationSection")}
          </span>
          {matrix && <ProfileModeBadge mode={matrix.precision} />}
        </div>
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5 space-y-2">
          <RuntimeProfileRow label={t("runtime.profile.precision")}>
            <SelectMenu
              value={effectivePrecision}
              options={precisionOptions}
              onChange={(v) => setLocalPrecision(v)}
              disabled={busy}
            />
          </RuntimeProfileRow>
          <RuntimeProfileRow label={t("runtime.profile.quantizationBackend")}>
            <SelectMenu
              value={effectiveQuantizationBackend}
              options={quantizationBackendOptions}
              onChange={(v) => setLocalQuantizationBackend(v)}
              disabled={busy}
            />
          </RuntimeProfileRow>
          <RuntimeProfileRow label={t("runtime.profile.deviceTarget")}>
            <SelectMenu
              value={effectiveDeviceTarget}
              options={deviceTargetOptions}
              onChange={(v) => setLocalDeviceTarget(v)}
              disabled={busy}
            />
          </RuntimeProfileRow>
          <RuntimeProfileRow label={t("runtime.profile.stagedRuntime")}>
            <span className="text-xs text-zinc-300">{stagedRuntimeLine}</span>
          </RuntimeProfileRow>
          <RuntimeProfileRow label={t("runtime.profile.activeRuntime")}>
            <span className="text-xs text-zinc-300">{activeRuntimeLine}</span>
          </RuntimeProfileRow>
          <RuntimeProfileRow label={t("runtime.profile.effectivePrecisionMode")}>
            <span className="text-xs text-zinc-300">
              {daemonStatus?.effective_precision_mode ?? "unknown"}
            </span>
          </RuntimeProfileRow>
          {daemonStatus?.effective_config_reason && (
            <RuntimeProfileRow label={t("runtime.profile.effectiveConfigReason")}>
              <span className="text-xs text-zinc-400">{daemonStatus.effective_config_reason}</span>
            </RuntimeProfileRow>
          )}
          {runtimeConfigDrift && (
            <div className="flex items-center justify-end">
              <Badge variant="secondary">{t("runtime.profile.notAppliedYet")}</Badge>
            </div>
          )}
          {quantizationInactiveReason && (
            <p className="text-[10px] text-amber-300">
              {t("runtime.profile.quantizationEffectiveNo")}: {quantizationInactiveReason}
            </p>
          )}
        </div>
        {daemonStatus?.vram_interpretation_hint && (
          <p className="text-[10px] text-zinc-500">
            {t("runtime.profile.vramInterpretationHint")}: {daemonStatus.vram_interpretation_hint}
          </p>
        )}
        <Button
          size="xs"
          variant="secondary"
          className="w-full"
          onClick={handleApplyQuantization}
          disabled={busy || !data.daemon_reachable}
        >
          {busy ? t("runtime.profile.applying") : t("runtime.profile.applyQuantization")}
        </Button>
      </div>

      <RuntimeProfileLastUpdateSummary lastUpdateResult={lastUpdateResult} />
    </section>
  );
}

function RuntimeProfileLastUpdateSummary({
  lastUpdateResult,
}: Readonly<{
  lastUpdateResult: MultiRuntimeProfileUpdateResponse | null;
}>) {
  const t = useTranslation();
  if (!lastUpdateResult) return null;
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2 text-[11px] space-y-1">
      <div className="flex items-center gap-2">
        <span className="font-medium">{t("runtime.profile.lastUpdate")}</span>
        <ProfileModeBadge mode={lastUpdateResult.required_apply_mode} />
        {lastUpdateResult.applied && (
          <Badge variant="default">{t("runtime.profile.applied")}</Badge>
        )}
      </div>
      {lastUpdateResult.rejected.length > 0 && (
        <ul className="text-rose-300 space-y-0.5">
          {lastUpdateResult.rejected.map((rejection) => (
            <li key={rejection.field}>
              {rejection.field}: {rejection.reason}
            </li>
          ))}
        </ul>
      )}
      {Object.keys(lastUpdateResult.accepted).length > 0 && (
        <div className="text-zinc-400">
          Accepted: {Object.keys(lastUpdateResult.accepted).join(", ")}
        </div>
      )}
    </div>
  );
}

function hasRuntimeConfigDrift(stagedRuntimeLine: string, activeRuntimeLine: string): boolean {
  if (stagedRuntimeLine === "—" || activeRuntimeLine === "—") return false;
  return stagedRuntimeLine !== activeRuntimeLine;
}

function resolveRuntimeProfileEffectiveState(params: {
  profile: NonNullable<ReturnType<typeof useMultiRuntimeProfile>["data"]>["profile"] | null;
  localExecutionMode: string | null;
  localImageStrategy: string | null;
  localRetrievalMode: string | null;
  localAudioOutputMode: string | null;
  localAssistantMode: string | null;
  localEconomyMode: string | null;
  localCache: string | null;
  localPrecision: string | null;
  localQuantizationBackend: string | null;
  localDeviceTarget: string | null;
}): {
  effectiveExecutionMode: string;
  effectiveImageStrategy: string;
  effectiveRetrievalMode: string;
  effectiveAudioOutputMode: string;
  effectiveAssistantMode: string;
  effectiveEconomyMode: string;
  effectiveCache: string;
  effectivePrecision: string;
  effectiveQuantizationBackend: string;
  effectiveDeviceTarget: string;
} {
  return {
    effectiveExecutionMode:
      params.localExecutionMode ?? params.profile?.execution_mode ?? "balanced",
    effectiveImageStrategy:
      params.localImageStrategy ?? params.profile?.image_strategy ?? "vlm_only",
    effectiveRetrievalMode:
      params.localRetrievalMode ?? params.profile?.retrieval_mode ?? "off",
    effectiveAudioOutputMode:
      params.localAudioOutputMode ?? params.profile?.audio_output_mode ?? "off",
    effectiveAssistantMode:
      params.localAssistantMode ?? params.profile?.assistant_mode ?? "off",
    effectiveEconomyMode:
      params.localEconomyMode ?? params.profile?.economy_mode ?? "off",
    effectiveCache: params.localCache ?? params.profile?.cache_implementation ?? "",
    effectivePrecision: params.localPrecision ?? params.profile?.precision ?? "auto",
    effectiveQuantizationBackend:
      params.localQuantizationBackend ?? params.profile?.quantization_backend ?? "",
    effectiveDeviceTarget: params.localDeviceTarget ?? params.profile?.device_target ?? "auto",
  };
}

function getQuantizationInactiveReason(
  daemonStatus: DaemonStatus | null,
): string | null {
  if (daemonStatus?.quantization_effective !== false) return null;
  return daemonStatus.quantization_effective_reason ?? null;
}

function RuntimeProfileRow({
  label,
  children,
}: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm text-zinc-400">{label}</span>
      <div className="w-48">{children}</div>
    </div>
  );
}

function resolveRuntimeComponentLabel(
  componentId: string,
  t: (path: string) => string,
): string {
  switch (componentId) {
    case "main_model":
      return t("runtime.profile.componentLabels.mainModel");
    case "assistant_model":
      return t("runtime.profile.componentLabels.assistantModel");
    case "image_input":
      return t("runtime.profile.componentLabels.imageInput");
    case "ocr_component":
      return t("runtime.profile.componentLabels.ocrComponent");
    case "stt_component":
      return t("runtime.profile.componentLabels.sttComponent");
    case "tts_component":
      return t("runtime.profile.componentLabels.ttsComponent");
    case "embedding_component":
      return t("runtime.profile.componentLabels.embeddingComponent");
    default:
      return componentId;
  }
}

function resolveRuntimeComponentHealthLabel(
  health: string | null | undefined,
  t: (path: string) => string,
): string {
  switch (health) {
    case "ok":
      return t("runtime.profile.componentHealth.ok");
    case "disabled":
      return t("runtime.profile.componentHealth.disabled");
    case "degraded":
      return t("runtime.profile.componentHealth.degraded");
    case "error":
      return t("runtime.profile.componentHealth.error");
    default:
      return health ?? t("common.unknown");
  }
}

function resolveRuntimeComponentHealthTone(
  health: string | null | undefined,
): "success" | "warning" | "danger" | "neutral" {
  switch (health) {
    case "ok":
      return "success";
    case "disabled":
      return "neutral";
    case "degraded":
      return "warning";
    case "error":
      return "danger";
    default:
      return "neutral";
  }
}

function vramBarColor(pct: number): string {
  if (pct > 90) return "bg-rose-500";
  if (pct > 70) return "bg-amber-400";
  return "bg-emerald-400";
}

function parseTokenInput(raw: string): number | undefined {
  const n = Number.parseInt(raw, 10);
  return Number.isNaN(n) || n <= 0 ? undefined : n;
}

function resetLocalRuntimeDraft(params: {
  setLocalThinking: (value: boolean | null) => void;
  setLocalTokens: (value: string) => void;
  setLocalImageBudget: (value: string) => void;
  setLocalCache: (value: string | null) => void;
}) {
  params.setLocalThinking(null);
  params.setLocalTokens("");
  params.setLocalImageBudget("");
  params.setLocalCache(null);
}

function buildDaemonConfigRequestFromLocalDraft(draft: {
  localThinking: boolean | null;
  localReasoningSummary: boolean | null;
  localEmotionDetection: boolean | null;
  localEmotionResponseStyle: boolean | null;
  localTokens: string;
  localImageBudget: string;
  localCache: string | null;
}): DaemonConfigRequest {
  const params: DaemonConfigRequest = {};
  if (draft.localThinking !== null) params.enable_thinking = draft.localThinking;
  if (draft.localReasoningSummary !== null) {
    params.reasoning_summary_enabled = draft.localReasoningSummary;
  }
  if (draft.localEmotionDetection !== null) {
    params.emotion_detection_enabled = draft.localEmotionDetection;
  }
  if (draft.localEmotionResponseStyle !== null) {
    params.emotion_response_style_enabled = draft.localEmotionResponseStyle;
  }
  if (draft.localTokens !== "") {
    const n = parseTokenInput(draft.localTokens);
    if (n !== undefined) params.max_new_tokens = n;
  }
  if (draft.localImageBudget !== "") {
    const n = parseTokenInput(draft.localImageBudget);
    if (n !== undefined) params.image_token_budget = n;
  }
  if (draft.localCache !== null) {
    params.cache_implementation = draft.localCache === "" ? null : draft.localCache;
  }
  return params;
}

async function attachAssistantModel(params: {
  daemon: Gemma4DaemonState;
  drafterInput: string;
  setDrafterInput: (value: string) => void;
  setShowDrafterInput: (value: boolean) => void;
}) {
  const id = params.drafterInput.trim();
  if (!id) return;
  await params.daemon.attachAssistant(id);
  params.setDrafterInput("");
  params.setShowDrafterInput(false);
}

async function applyRuntimeControlDraft(params: {
  daemon: Gemma4DaemonState;
  localThinking: boolean | null;
  localReasoningSummary: boolean | null;
  localEmotionDetection: boolean | null;
  localEmotionResponseStyle: boolean | null;
  localTokens: string;
  localImageBudget: string;
  localCache: string | null;
  resetDraft: () => void;
}) {
  const request = buildDaemonConfigRequestFromLocalDraft(params);
  const result = await params.daemon.applyConfig(request);
  if (result) {
    params.resetDraft();
  }
}

async function handleRuntimeImageProbe(params: {
  imageUrlInput: string;
  imageDataInput: string | null;
  imagePromptInput: string;
  imageProbePending: boolean;
  maxNewTokens: number;
  setImageProbeResult: (value: string | null) => void;
  setImageProbeDiagnostics: (
    value: {
      executionTrace: string[];
      selectedPolicy: string | null;
      selectedImageStrategy: string | null;
      retrievalUsed: boolean;
      retrievalContextItems: number;
      retrievalRoute: string | null;
      assistantUsed: boolean;
      economyModeActivated: boolean;
      degradationReasons: string[];
    } | null,
  ) => void;
  setImageProbeError: (value: string | null) => void;
  setImageProbePending: (value: boolean) => void;
  setLastPipelineResponse: (value: DaemonRespondResponse | null) => void;
}) {
  const url = params.imageUrlInput.trim();
  if ((!url && !params.imageDataInput) || params.imageProbePending) return;
  params.setImageProbePending(true);
  params.setImageProbeError(null);
  params.setImageProbeResult(null);
  params.setImageProbeDiagnostics(null);
  try {
    const result = await runImageProbe({
      imageUrlInput: params.imageUrlInput,
      imageDataInput: params.imageDataInput,
      imagePromptInput: params.imagePromptInput,
      imageProbePending: params.imageProbePending,
      maxNewTokens: params.maxNewTokens,
    });
    params.setImageProbeResult(result.text);
    params.setImageProbeDiagnostics(result.diagnostics);
    params.setLastPipelineResponse(result.rawResponse);
  } catch (e) {
    params.setImageProbeError(e instanceof Error ? e.message : "Image request failed");
  } finally {
    params.setImageProbePending(false);
  }
}

async function handleRuntimeImageFileSelection(params: {
  fileList: FileList | null;
  setImageProbeError: (value: string | null) => void;
  setImageDataInput: (value: string | null) => void;
  setImageFileName: (value: string | null) => void;
}) {
  const file = params.fileList?.item(0);
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    params.setImageProbeError("Only image files are supported");
    return;
  }
  params.setImageProbeError(null);
  const loaded = await readImageFileAsDataUrl(file);
  params.setImageDataInput(loaded);
  params.setImageFileName(file.name);
}

async function readImageFileAsDataUrl(file: File): Promise<string> {
  const reader = new FileReader();
  return new Promise<string>((resolve, reject) => {
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
        return;
      }
      reject(new Error("Unexpected file reader result type"));
    };
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}

async function runImageProbe(params: {
  imageUrlInput: string;
  imageDataInput: string | null;
  imagePromptInput: string;
  imageProbePending: boolean;
  maxNewTokens: number;
}): Promise<{
  text: string;
  rawResponse: DaemonRespondResponse;
  diagnostics: {
    executionTrace: string[];
    selectedPolicy: string | null;
    selectedImageStrategy: string | null;
    retrievalUsed: boolean;
    retrievalContextItems: number;
    retrievalRoute: string | null;
    assistantUsed: boolean;
    economyModeActivated: boolean;
    degradationReasons: string[];
  };
}> {
  const url = params.imageUrlInput.trim();
  if ((!url && !params.imageDataInput) || params.imageProbePending) {
    throw new Error("Image input is missing");
  }
  const imageContent = params.imageDataInput
    ? ({ type: "image", data: params.imageDataInput } as const)
    : ({ type: "image", url } as const);
  const result = await postDaemonRespond(getGemma4ApiBaseUrl(), {
    messages: [
      {
        role: "user",
        content: [
          imageContent,
          {
            type: "text",
            text: params.imagePromptInput.trim() || "Describe the image and extract visible text.",
          },
        ],
      },
    ],
    task: "question",
    max_new_tokens: params.maxNewTokens,
  });
  return {
    text: result.text,
    rawResponse: result,
    diagnostics: {
      executionTrace: result.execution_trace ?? [],
      selectedPolicy: result.selected_policy ?? null,
      selectedImageStrategy: result.selected_image_strategy ?? null,
      retrievalUsed: Boolean(result.retrieval_used),
      retrievalContextItems: Number(result.retrieval_context_items ?? 0),
      retrievalRoute: result.retrieval_route ?? null,
      assistantUsed: Boolean(result.assistant_used),
      economyModeActivated: Boolean(result.economy_mode_activated),
      degradationReasons: Array.isArray(result.degradation_reasons)
        ? result.degradation_reasons
        : [],
    },
  };
}

function Gemma4RuntimeControlPanel({
  daemon,
  variant,
  runtimeSnapshot = null,
  assistantModels = [],
}: InnerProps) {
  const t = useTranslation();
  const { status, loading, error, actionPending } = daemon;

  const [localTokens, setLocalTokens] = useState<string>("");
  const [localImageBudget, setLocalImageBudget] = useState<string>("");
  const [localThinking, setLocalThinking] = useState<boolean | null>(null);
  const [localReasoningSummary, setLocalReasoningSummary] = useState<boolean | null>(null);
  const [localEmotionDetection, setLocalEmotionDetection] = useState<boolean | null>(null);
  const [localEmotionResponseStyle, setLocalEmotionResponseStyle] = useState<boolean | null>(null);
  const [localCache, setLocalCache] = useState<string | null>(null);
  const [drafterInput, setDrafterInput] = useState("");
  const [showDrafterInput, setShowDrafterInput] = useState(false);
  const [showDrafter, setShowDrafter] = useState(false);

  const busy = actionPending !== null;

  const effectiveThinking = localThinking ?? status?.params.enable_thinking ?? false;
  const effectiveReasoningSummary =
    localReasoningSummary ?? status?.params.reasoning_summary_enabled ?? false;
  const effectiveEmotionDetection =
    localEmotionDetection ?? status?.params.emotion_detection_enabled ?? false;
  const effectiveEmotionResponseStyle =
    localEmotionResponseStyle ?? status?.params.emotion_response_style_enabled ?? false;
  const effectiveTokens =
    localTokens === "" ? String(status?.params.max_new_tokens ?? 128) : localTokens;
  const effectiveImageBudget =
    localImageBudget === ""
      ? String(status?.params.image_token_budget ?? 280)
      : localImageBudget;
  const effectiveCache =
    localCache === null ? (status?.params.cache_implementation ?? "") : localCache;
  const cacheOptions = useMemo(
    () =>
      CACHE_OPTIONS.map((opt) => ({
        value: opt.value,
        label: opt.value === "" ? t("voice.daemon.cacheDefault") : opt.label,
      })),
    [t],
  );
  const responseShapingToggles = [
    {
      label: t("voice.daemon.reasoningSummary"),
      checked: effectiveReasoningSummary,
      set: setLocalReasoningSummary,
      ariaLabel: t("voice.daemon.reasoningSummary"),
    },
    {
      label: t("voice.daemon.emotionDetection"),
      checked: effectiveEmotionDetection,
      set: setLocalEmotionDetection,
      ariaLabel: t("voice.daemon.emotionDetection"),
    },
    {
      label: t("voice.daemon.emotionResponseStyle"),
      checked: effectiveEmotionResponseStyle,
      set: setLocalEmotionResponseStyle,
      ariaLabel: t("voice.daemon.emotionResponseStyle"),
    },
  ] as const;

  const hasLocalChanges =
    localThinking !== null ||
    localReasoningSummary !== null ||
    localEmotionDetection !== null ||
    localEmotionResponseStyle !== null ||
    localTokens !== "" ||
    localImageBudget !== "" ||
    localCache !== null;

  const handleApply = () =>
    applyRuntimeControlDraft({
      daemon,
      localThinking,
      localReasoningSummary,
      localEmotionDetection,
      localEmotionResponseStyle,
      localTokens,
      localImageBudget,
      localCache,
      resetDraft: () =>
        resetLocalRuntimeDraft({
          setLocalThinking,
          setLocalTokens,
          setLocalImageBudget,
          setLocalCache,
        }),
    });

  const handleAttach = () =>
    attachAssistantModel({
      daemon,
      drafterInput,
      setDrafterInput,
      setShowDrafterInput,
    });

  const vram = status?.vram;
  const vramPercent =
    vram && vram.total_mb > 0
      ? Math.min(100, Math.round((vram.allocated_mb / vram.total_mb) * 100))
      : null;

  if (loading && !status) {
    return (
      <DaemonCard variant={variant}>
        <p className="text-hint text-xs py-2">{t("voice.daemon.daemonLoading")}</p>
      </DaemonCard>
    );
  }

  if (error && !status) {
    const hasRuntimeSnapshot = Boolean(runtimeSnapshot?.provider || runtimeSnapshot?.model_name);
    return (
      <DaemonCard variant={variant}>
        <p className="text-xs text-rose-400 py-1">{t("voice.daemon.daemonUnavailable")}</p>
        <p className="text-[10px] text-zinc-500 truncate">{error}</p>
        {hasRuntimeSnapshot && (
          <RuntimeSnapshotSummary snapshot={runtimeSnapshot} targetModelOverride={status?.target_model ?? null} />
        )}
      </DaemonCard>
    );
  }

  return (
    <DaemonCard variant={variant}>
      {/* Header row — model + mode badges */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-white truncate">
            {status?.target_model ?? "—"}
          </p>
          <p className="text-[10px] text-zinc-500 truncate mt-0.5">
            {t("voice.daemon.targetModel")}
          </p>
        </div>
        <div className="flex gap-1 flex-shrink-0">
          {status?.target_loaded === false && (
            <Badge tone="warning" className="text-[10px]">{t("voice.daemon.warming")}</Badge>
          )}
          {status?.mode === "target_with_assistant" && (
            <Badge tone="success" className="text-[10px]">
              {t("voice.daemon.assistantActive")}
            </Badge>
          )}
          {status?.supports_image_input && (
            <Badge tone="neutral" className="text-[10px]">image</Badge>
          )}
        </div>
      </div>

      {/* Pending reload banner */}
      {status?.pending_reload && (
        <div
          data-testid="reload-banner"
          className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300"
        >
          <span className="font-semibold">{t("voice.daemon.reloadRequired")}: </span>
          {status.reload_reason}
        </div>
      )}

      {runtimeSnapshot && (
        <RuntimeSnapshotSummary
          snapshot={runtimeSnapshot}
          compact
          targetModelOverride={status?.target_model ?? null}
        />
      )}

      {/* Params */}
      <div className="space-y-2.5 mb-3">
        {/* Reasoning / emotion shaping — thinking + response shaping group */}
        <p className="text-[10px] uppercase tracking-widest text-zinc-500">{t("voice.daemon.responseShaping")}</p>
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-2.5 space-y-2">
          {/* Thinking — first item in group */}
          <div className="flex items-center justify-between gap-2">
            <label className="text-xs text-zinc-400">{t("voice.daemon.thinking")}</label>
            <div className="flex items-center gap-2">
              <Switch
                checked={effectiveThinking}
                onCheckedChange={(v) => setLocalThinking(v)}
                disabled={busy}
                aria-label={t("voice.daemon.thinking")}
              />
              {status && (
                <ThinkingStatusLabel localThinking={localThinking} enabled={status.params.enable_thinking} />
              )}
            </div>
          </div>
          <div className="border-t border-white/[0.05]" />
          {responseShapingToggles.map((toggle) => (
            <div key={toggle.ariaLabel} className="flex items-center justify-between gap-2">
              <label className="text-xs text-zinc-400">{toggle.label}</label>
              <div className="flex items-center gap-2">
                <Switch
                  checked={toggle.checked}
                  onCheckedChange={(value) => toggle.set(value)}
                  disabled={busy}
                  aria-label={toggle.ariaLabel}
                />
                <ToggleStateLabel enabled={toggle.checked} />
              </div>
            </div>
          ))}
        </div>

        {/* Generation params */}
        <p className="text-[10px] uppercase tracking-widest text-zinc-500">{t("voice.daemon.generationParams")}</p>

        {/* Max tokens */}
        <div className="flex items-center justify-between gap-2">
          <label className="text-xs text-zinc-400">{t("voice.daemon.maxTokens")}</label>
          <input
            type="number"
            min={1}
            max={4096}
            value={effectiveTokens}
            onChange={(e) => setLocalTokens(e.target.value)}
            disabled={busy}
            className="w-20 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-right text-xs text-white focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
            aria-label={t("voice.daemon.maxTokens")}
          />
        </div>

        <div className="flex items-center justify-between gap-2">
          <label className="text-xs text-zinc-400">{t("voice.daemon.imageTokenBudget")}</label>
          <input
            type="number"
            min={70}
            max={1120}
            step={70}
            value={effectiveImageBudget}
            onChange={(e) => setLocalImageBudget(e.target.value)}
            disabled={busy}
            className="w-20 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-right text-xs text-white focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
            aria-label={t("voice.daemon.imageTokenBudget")}
          />
        </div>

        {/* Cache strategy */}
        <div className="flex items-center justify-between gap-2">
          <label className="text-xs text-zinc-400">{t("voice.daemon.cacheStrategy")}</label>
          <SelectMenu
            value={effectiveCache}
            options={cacheOptions}
            onChange={(v) => setLocalCache(v)}
            disabled={busy}
            ariaLabel={t("voice.daemon.cacheStrategy")}
          />
        </div>
        </div>

      <RuntimeProfileControls daemonStatus={status ?? null} />

      {/* VRAM */}
      {vram && (
        <VramSection vram={vram} vramPercent={vramPercent} />
      )}

      {/* Drafter — collapsible, collapsed by default */}
      <div className="mb-3">
        <button
          type="button"
          data-testid="drafter-accordion-toggle"
          onClick={() => setShowDrafter(!showDrafter)}
          className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <span>{t("voice.daemon.assistantDrafter")}</span>
          <span className="text-zinc-600">{showDrafter ? "▲" : "▼"}</span>
        </button>
        {showDrafter && (
          <DrafterBox
            daemon={daemon}
            assistantModel={status?.assistant_model ?? null}
            assistantModels={assistantModels}
            busy={busy}
            actionPending={actionPending}
            drafterInput={drafterInput}
            setDrafterInput={setDrafterInput}
            showDrafterInput={showDrafterInput}
            setShowDrafterInput={setShowDrafterInput}
            onAttach={handleAttach}
          />
        )}
      </div>

      {/* Actions */}
      <div className="space-y-2">
        <p className="text-[10px] uppercase tracking-widest text-zinc-500">
          {t("runtime.profile.manualOverrides")}
        </p>
        <div className="flex flex-wrap gap-2">
        {buildDaemonConfirmActions({ t, daemon }).map((action) => (
          <DaemonConfirmActionButton
            key={action.key}
            buttonVariant={action.buttonVariant}
            busy={busy}
            actionPending={actionPending}
            actionName={action.actionName}
            pendingLabel={action.pendingLabel}
            buttonLabel={action.buttonLabel}
            title={action.title}
            description={action.description}
            confirmLabel={action.confirmLabel}
            confirmVariant={action.confirmVariant}
            onConfirm={action.onConfirm}
            testId={action.testId}
          />
        ))}

        <Button
          size="xs"
          variant="ghost"
          onClick={daemon.fallback}
          disabled={busy}
          data-testid="fallback-button"
        >
          {actionPending === "fallback" ? t("voice.daemon.busy") : t("voice.daemon.fallback")}
        </Button>
        </div>
        <p className="text-[10px] text-zinc-500">
          {t("runtime.profile.manualOverridesHint")}
        </p>
        <details className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5">
          <summary className="cursor-pointer text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors">
            {t("runtime.profile.advancedActions")}
          </summary>
          <div className="mt-2">
            <Button
              size="xs"
              variant="primary"
              onClick={handleApply}
              disabled={busy || !hasLocalChanges}
              data-testid="apply-button"
            >
              {actionPending === "config"
                ? t("voice.daemon.applying")
                : t("runtime.profile.applyLegacyConfig")}
            </Button>
          </div>
        </details>
      </div>

      {/* Last signal feedback */}
      {daemon.lastAppliedSignal && daemon.lastAppliedSignal !== "none" && (
        <p className="mt-2 text-[10px] text-amber-300">
          {daemon.lastAppliedSignal === "soft_reload"
            ? t("voice.daemon.signalReload")
            : t("voice.daemon.signalRestart")}
        </p>
      )}

      {error && (
        <p className="mt-2 text-[10px] text-rose-400 truncate">{error}</p>
      )}

      {status?.component_snapshot && status.component_snapshot.length > 0 && (
        <div className="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5">
          <p className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
            {t("runtime.profile.componentSnapshot")}
          </p>
          <div className="space-y-1.5">
            {status.component_snapshot.slice(0, 7).map((component) => (
              <div
                key={component.component_id}
                className="flex items-center justify-between gap-2 text-[10px]"
              >
                <span className="text-zinc-300 truncate">
                  {resolveRuntimeComponentLabel(component.component_id, t)}
                </span>
                <Badge
                  tone={resolveRuntimeComponentHealthTone(component.health)}
                  className="truncate text-[10px] uppercase tracking-wide"
                >
                  {resolveRuntimeComponentHealthLabel(component.health, t)}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}
    </DaemonCard>
  );
}

// ── Sub-components extracted to reduce cognitive complexity ───────────────────

function ThinkingStatusLabel({
  localThinking,
  enabled,
}: Readonly<{ localThinking: boolean | null; enabled: boolean }>) {
  const t = useTranslation();
  if (localThinking !== null) {
    return <span className="text-[10px] text-zinc-500">{t("voice.daemon.signalLive")}</span>;
  }
  const label = enabled ? t("common.yes") : t("common.no");
  return <span className="text-[10px] text-zinc-500">{label}</span>;
}

function ToggleStateLabel({ enabled }: Readonly<{ enabled: boolean }>) {
  const t = useTranslation();
  return <span className="text-[10px] text-zinc-500">{enabled ? t("common.yes") : t("common.no")}</span>;
}

type VramInfo = Readonly<{
  backend: string;
  allocated_mb: number;
  total_mb: number;
}>;

function VramSection({
  vram,
  vramPercent,
}: Readonly<{ vram: VramInfo; vramPercent: number | null }>) {
  const t = useTranslation();
  const label =
    vram.backend === "cuda"
      ? `${vram.allocated_mb} / ${vram.total_mb} MB`
      : t("voice.daemon.vramCpu");

  return (
    <div className="mb-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] uppercase tracking-widest text-zinc-500">
          {t("voice.daemon.vram")}
        </span>
        <span className="text-[10px] text-zinc-400">{label}</span>
      </div>
      {vram.backend === "cuda" && vramPercent !== null && (
        <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
          <div
            data-testid="vram-bar"
            className={`h-full rounded-full transition-all ${vramBarColor(vramPercent)}`}
            style={{ width: `${vramPercent}%` }}
          />
        </div>
      )}
    </div>
  );
}

type RuntimeSnapshotSummaryProps = Readonly<{
  snapshot: RuntimeSnapshotLike;
  compact?: boolean;
  targetModelOverride?: string | null;
}>;

function RuntimeSnapshotSummary({
  snapshot,
  compact = false,
  targetModelOverride = null,
}: RuntimeSnapshotSummaryProps) {
  const t = useTranslation();
  if (!snapshot) return null;

  const provider = snapshot.provider ?? "—";
  const model = resolveRuntimeSnapshotModel(snapshot, targetModelOverride);
  const profile = snapshot.runtime_capabilities?.compatibility_profile ?? snapshot.voice_pipeline?.profile ?? null;
  const title = t("voice.daemon.runtimeSnapshot");

  return (
    <div className={`mb-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5 ${compact ? "" : "mt-2"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-widest text-zinc-500">{title}</span>
        {snapshot.runtime_capabilities?.probe_status && (
          <span className="text-[10px] text-zinc-400">
            {snapshot.runtime_capabilities.probe_status}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-white truncate">
        {provider} / {model}
      </p>
      {profile && (
        <p className="mt-0.5 text-[10px] text-zinc-500 truncate">
          {t("voice.controls.profile")}: {profile}
        </p>
      )}
      {snapshot.error && (
        <p className="mt-0.5 text-[10px] text-rose-400 truncate">{snapshot.error}</p>
      )}
    </div>
  );
}

function resolveRuntimeSnapshotModel(
  snapshot: RuntimeSnapshotLike,
  targetModelOverride: string | null,
): string {
  const fallbackModel = snapshot?.model_name ?? "—";
  if (!targetModelOverride) return fallbackModel;

  const runtimeId = String(snapshot?.runtime_id ?? "").trim().toLowerCase();
  const provider = String(snapshot?.provider ?? "").trim().toLowerCase();
  const isMultiRuntimeSnapshot =
    runtimeId === "multi_runtime" ||
    runtimeId === "gemma4_audio" ||
    runtimeId.startsWith("multi_runtime@") ||
    runtimeId.startsWith("gemma4_audio@") ||
    provider === "multi_runtime" ||
    provider === "gemma4_audio" ||
    provider.startsWith("multi_runtime@") ||
    provider.startsWith("gemma4_audio@");
  return isMultiRuntimeSnapshot ? targetModelOverride : fallbackModel;
}

type DrafterBoxProps = Readonly<{
  daemon: Gemma4DaemonState;
  assistantModel: string | null;
  assistantModels: string[];
  busy: boolean;
  actionPending: string | null;
  drafterInput: string;
  setDrafterInput: (v: string) => void;
  showDrafterInput: boolean;
  setShowDrafterInput: (v: boolean) => void;
  onAttach: () => void;
}>;

function DrafterBox({
  daemon,
  assistantModel,
  assistantModels,
  busy,
  actionPending,
  drafterInput,
  setDrafterInput,
  showDrafterInput,
  setShowDrafterInput,
  onAttach,
}: DrafterBoxProps) {
  const t = useTranslation();
  const assistantModelOptions = useMemo<SelectMenuOption[]>(() => {
    const seen = new Set<string>();
    return assistantModels
      .map((modelId) => modelId.trim())
      .filter((modelId) => {
        if (!modelId || seen.has(modelId)) return false;
        seen.add(modelId);
        return true;
      })
      .map((modelId) => ({
        value: modelId,
        label: modelId,
      }));
  }, [assistantModels]);
  const hasAssistantOptions = assistantModelOptions.length > 0;

  return (
    <div className="mb-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-widest text-zinc-500">
          {t("voice.daemon.assistantDrafter")}
        </span>
        {assistantModel ? (
          <Button size="xs" variant="ghost" onClick={daemon.detachAssistant} disabled={busy}>
            {actionPending === "detach" ? t("voice.daemon.busy") : t("voice.daemon.detachDrafter")}
          </Button>
        ) : (
          <Button
            size="xs"
            variant="ghost"
            onClick={() => {
              setShowDrafterInput(!showDrafterInput);
              if (!showDrafterInput && !drafterInput.trim() && assistantModelOptions[0]) {
                setDrafterInput(assistantModelOptions[0].value);
              }
            }}
            disabled={busy}
          >
            {t("voice.daemon.attachDrafter")}
          </Button>
        )}
      </div>

      {assistantModel ? (
        <p className="mt-1 text-xs text-white truncate">{assistantModel}</p>
      ) : (
        <p className="mt-1 text-[10px] text-zinc-600">{t("voice.daemon.noDrafter")}</p>
      )}

      {showDrafterInput && !assistantModel && (
        <div className="mt-2 flex gap-2">
          {hasAssistantOptions ? (
            <SelectMenu
              value={drafterInput.trim()}
              options={assistantModelOptions}
              onChange={(value) => setDrafterInput(value)}
              placeholder={t("voice.daemon.drafterModelPlaceholder")}
              ariaLabel={t("voice.daemon.drafterModelPlaceholder")}
              buttonClassName="flex-1 justify-between rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white normal-case tracking-normal"
              menuClassName="w-full"
              menuWidth="content"
            />
          ) : (
            <input
              type="text"
              value={drafterInput}
              onChange={(e) => setDrafterInput(e.target.value)}
              placeholder={t("voice.daemon.drafterModelPlaceholder")}
              disabled={busy}
              className="flex-1 min-w-0 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
            />
          )}
          <Button
            size="xs"
            variant="primary"
            onClick={onAttach}
            disabled={busy || !drafterInput.trim()}
          >
            {actionPending === "attach" ? t("voice.daemon.busy") : t("voice.daemon.ok")}
          </Button>
        </div>
      )}
    </div>
  );
}

function DaemonCard({
  variant,
  children,
}: Readonly<{ variant: Variant; children: React.ReactNode }>) {
  const t = useTranslation();
  const cardClass =
    variant === "voice"
      ? "rounded-2xl border border-white/[0.07] bg-white/[0.03] p-3 text-xs text-zinc-300"
      : "mt-3 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-xs text-zinc-400";
  const titleClass =
    variant === "voice"
      ? "eyebrow mb-2"
      : "mb-2 text-[10px] uppercase tracking-widest text-zinc-500";

  return (
    <div className={cardClass}>
      <p className={titleClass}>{t("voice.daemon.title")}</p>
      {children}
    </div>
  );
}

type ConfirmActionDefinition = Readonly<{
  key: "reload" | "restart";
  buttonVariant: "ghost" | "secondary";
  confirmVariant?: "default" | "danger";
  onConfirm: () => void | Promise<void>;
}>;

function buildDaemonConfirmActions({
  t,
  daemon,
}: Readonly<{
  t: (key: string) => string;
  daemon: Gemma4DaemonState;
}>): Array<DaemonConfirmActionButtonProps & { key: string }> {
  const defs: ConfirmActionDefinition[] = [
    {
      key: "reload",
      buttonVariant: "secondary",
      onConfirm: daemon.reload,
    },
    {
      key: "restart",
      buttonVariant: "ghost",
      confirmVariant: "danger",
      onConfirm: daemon.restart,
    },
  ];

  return defs.map((def) => {
    const isReload = def.key === "reload";
    return {
      key: def.key,
      buttonVariant: def.buttonVariant,
      busy: false, // overridden at render call site
      actionPending: null, // overridden at render call site
      actionName: def.key,
      pendingLabel: isReload ? t("voice.daemon.reloading") : t("voice.daemon.restarting"),
      buttonLabel: isReload ? t("voice.daemon.reload") : t("voice.daemon.restart"),
      title: isReload
        ? t("voice.daemon.confirmReloadTitle")
        : t("voice.daemon.confirmRestartTitle"),
      description: isReload
        ? t("voice.daemon.confirmReloadDesc")
        : t("voice.daemon.confirmRestartDesc"),
      confirmLabel: isReload ? t("voice.daemon.reload") : t("voice.daemon.restart"),
      onConfirm: def.onConfirm,
      confirmVariant: def.confirmVariant,
      testId: isReload ? "reload-button" : "restart-button",
    };
  });
}

type DaemonConfirmActionButtonProps = Readonly<{
  busy: boolean;
  actionPending: string | null;
  actionName: string;
  pendingLabel: string;
  buttonLabel: string;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void | Promise<void>;
  buttonVariant: "ghost" | "secondary";
  confirmVariant?: "default" | "danger";
  testId: string;
}>;

function DaemonConfirmActionButton({
  busy,
  actionPending,
  actionName,
  pendingLabel,
  buttonLabel,
  title,
  description,
  confirmLabel,
  onConfirm,
  buttonVariant,
  confirmVariant,
  testId,
}: DaemonConfirmActionButtonProps) {
  return (
    <ConfirmDialog>
      <ConfirmDialogTrigger asChild>
        <Button size="xs" variant={buttonVariant} disabled={busy} data-testid={testId}>
          {actionPending === actionName ? pendingLabel : buttonLabel}
        </Button>
      </ConfirmDialogTrigger>
      <ConfirmDialogContent>
        <ConfirmDialogTitle>{title}</ConfirmDialogTitle>
        <ConfirmDialogDescription>{description}</ConfirmDialogDescription>
        <ConfirmDialogActions
          onConfirm={onConfirm}
          onCancel={() => {}}
          confirmLabel={confirmLabel}
          confirmVariant={confirmVariant}
        />
      </ConfirmDialogContent>
    </ConfirmDialog>
  );
}
