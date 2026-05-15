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
import type { DaemonConfigRequest, DaemonRespondResponse } from "@/lib/gemma4-daemon-api";
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
  return (
    <div className="mb-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5">
      <p className="text-[10px] uppercase tracking-widest text-zinc-500">{t("voice.daemon.imageInput")}</p>
      <div className="mt-2 space-y-2">
        <button
          type="button"
          onDragOver={(event) => { event.preventDefault(); }}
          onDrop={async (event) => {
            event.preventDefault();
            await onFileChange(event.dataTransfer.files);
            if (event.dataTransfer.files.item(0)) onImageUrlChange("");
          }}
          onClick={() => imageFileInputRef.current?.click()}
          className="w-full rounded-lg border border-dashed border-white/20 bg-white/[0.02] px-3 py-2 text-left text-[11px] text-zinc-400"
          aria-label={t("voice.daemon.dragDropImage")}
        >
          {t("voice.daemon.dragDropImage")}
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
          {imageFileName && (
            <span className="text-[10px] text-zinc-400 truncate">{imageFileName}</span>
          )}
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
        <input
          type="url"
          value={imageUrlInput}
          onChange={(e) => onImageUrlChange(e.target.value)}
          placeholder={imageDataInput ? t("voice.daemon.fileSelectedUrlDisabled") : t("voice.daemon.imageUrlPlaceholder")}
          disabled={busy || imageProbePending}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
          aria-label={t("voice.daemon.imageUrl")}
        />
        <input
          type="text"
          value={imagePromptInput}
          onChange={(e) => onImagePromptChange(e.target.value)}
          placeholder={t("voice.daemon.imagePromptPlaceholder")}
          disabled={busy || imageProbePending}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
          aria-label={t("voice.daemon.imagePrompt")}
        />
        <Button
          size="xs"
          variant="secondary"
          onClick={onProbe}
          disabled={busy || imageProbePending || (!imageUrlInput.trim() && !imageDataInput)}
        >
          {imageProbePending ? t("voice.daemon.imageProbeRunning") : t("voice.daemon.runImageProbe")}
        </Button>
        {imageProbeResult && (
          <p className="text-[11px] text-zinc-300 whitespace-pre-wrap">{imageProbeResult}</p>
        )}
        {imageProbeDiagnostics && (
          <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-2 text-[10px] text-zinc-400 space-y-1">
            <p><span className="text-zinc-500">selected_policy:</span> {imageProbeDiagnostics.selectedPolicy ?? "—"}</p>
            <p><span className="text-zinc-500">image_strategy:</span> {imageProbeDiagnostics.selectedImageStrategy ?? "—"}</p>
            <p><span className="text-zinc-500">trace:</span> {imageProbeDiagnostics.executionTrace.join(" -> ") || "—"}</p>
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
        )}
        {imageProbeError && (
          <p className="text-[10px] text-rose-400 break-all">{imageProbeError}</p>
        )}
      </div>
    </div>
  );
}

function ProfileModeBadge({ mode }: Readonly<{ mode: string }>) {
  const t = useTranslation();
  const variant =
    mode === "live"
      ? "default"
      : mode === "soft_reload"
        ? "secondary"
        : mode === "hard_restart"
          ? "destructive"
          : "outline";
  const label =
    mode === "live"
      ? t("runtime.profile.applyModeLive")
      : mode === "soft_reload"
        ? t("runtime.profile.applyModeSoftReload")
        : mode === "hard_restart"
          ? t("runtime.profile.applyModeHardRestart")
          : mode === "unsupported"
            ? t("runtime.profile.applyModeUnsupported")
            : mode;
  return <Badge variant={variant}>{label}</Badge>;
}

function RuntimeProfileControls() {
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

  const effectiveExecutionMode =
    localExecutionMode === null ? (profile?.execution_mode ?? "balanced") : localExecutionMode;
  const effectiveImageStrategy =
    localImageStrategy === null ? (profile?.image_strategy ?? "vlm_only") : localImageStrategy;
  const effectiveRetrievalMode =
    localRetrievalMode === null ? (profile?.retrieval_mode ?? "off") : localRetrievalMode;
  const effectiveAudioOutputMode =
    localAudioOutputMode === null ? (profile?.audio_output_mode ?? "off") : localAudioOutputMode;
  const effectiveAssistantMode =
    localAssistantMode === null ? (profile?.assistant_mode ?? "off") : localAssistantMode;
  const effectiveEconomyMode =
    localEconomyMode === null ? (profile?.economy_mode ?? "off") : localEconomyMode;
  const effectiveCache = localCache === null ? (profile?.cache_implementation ?? "") : localCache;

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
        </div>
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5 space-y-1.5 text-[11px] text-zinc-300">
          <div className="flex items-center justify-between gap-2">
            <span className="text-zinc-500">{t("runtime.profile.precision")}</span>
            <div className="flex items-center gap-2">
              <strong>{profile?.precision ?? "auto"}</strong>
              {matrix && <ProfileModeBadge mode={matrix.precision} />}
            </div>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-zinc-500">{t("runtime.profile.quantizationBackend")}</span>
            <div className="flex items-center gap-2">
              <strong>{profile?.quantization_backend ?? "none"}</strong>
              {matrix && <ProfileModeBadge mode={matrix.quantization_backend} />}
            </div>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-zinc-500">{t("runtime.profile.deviceTarget")}</span>
            <div className="flex items-center gap-2">
              <strong>{profile?.device_target ?? "auto"}</strong>
              {matrix && <ProfileModeBadge mode={matrix.device_target} />}
            </div>
          </div>
        </div>
      </div>

      {lastUpdateResult && (
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
      )}
    </section>
  );
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

  const handleImageProbe = () =>
    handleRuntimeImageProbe({
      imageUrlInput,
      imageDataInput,
      imagePromptInput,
      imageProbePending,
      maxNewTokens: status?.params.max_new_tokens ?? 128,
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
          <RuntimeSnapshotSummary snapshot={runtimeSnapshot} />
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
        <RuntimeSnapshotSummary snapshot={runtimeSnapshot} compact />
      )}

      {/* Params */}
      <div className="space-y-2.5 mb-3">
        {/* Thinking toggle */}
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

        {/* Reasoning / emotion shaping */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-2.5 space-y-2">
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
          <select
            value={effectiveCache}
            onChange={(e) => setLocalCache(e.target.value)}
            disabled={busy}
            className="rounded-lg border border-white/10 bg-zinc-900 px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
            aria-label={t("voice.daemon.cacheStrategy")}
          >
            {CACHE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.value === "" ? t("voice.daemon.cacheDefault") : opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <RuntimeProfileControls />

      {/* VRAM */}
      {vram && (
        <VramSection vram={vram} vramPercent={vramPercent} />
      )}

      {/* Drafter */}
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

      {status?.supports_image_input && (
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
      )}

      {lastPipelineResponse && (
        <PipelineDiagnosticsPanel response={lastPipelineResponse} />
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <Button
          size="xs"
          variant="primary"
          onClick={handleApply}
          disabled={busy || !hasLocalChanges}
          data-testid="apply-button"
        >
          {actionPending === "config"
            ? t("voice.daemon.applying")
            : t("voice.daemon.applyConfig")}
        </Button>

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
  const label = enabled ? t("voice.daemon.thinkingOn") : t("voice.daemon.thinkingOff");
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
}>;

function RuntimeSnapshotSummary({
  snapshot,
  compact = false,
}: RuntimeSnapshotSummaryProps) {
  const t = useTranslation();
  if (!snapshot) return null;

  const provider = snapshot.provider ?? "—";
  const model = snapshot.model_name ?? "—";
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
      {snapshot.voice_pipeline?.tts && (
        <p className="mt-0.5 text-[10px] text-zinc-500 truncate">
          {t("voice.controls.tts")}: {snapshot.voice_pipeline.tts}
        </p>
      )}
      {snapshot.voice_pipeline?.reasoning_summary && (
        <p className="mt-0.5 text-[10px] text-zinc-500 truncate">
          {t("voice.controls.reasoningSummary")}: {snapshot.voice_pipeline.reasoning_summary}
        </p>
      )}
      {snapshot.voice_pipeline?.emotion && (
        <p className="mt-0.5 text-[10px] text-zinc-500 truncate">
          {t("voice.controls.emotion")}: {snapshot.voice_pipeline.emotion}
        </p>
      )}
      {snapshot.error && (
        <p className="mt-0.5 text-[10px] text-rose-400 truncate">{snapshot.error}</p>
      )}
    </div>
  );
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
