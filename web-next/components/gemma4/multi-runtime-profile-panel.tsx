"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { SelectMenu, type SelectMenuOption } from "@/components/ui/select-menu";
import { useTranslation } from "@/lib/i18n";
import {
  type MultiRuntimeApplyMode,
  type MultiRuntimeProfileUpdateRequest,
} from "@/lib/gemma4-daemon-api";
import {
  type MultiRuntimeProfileState,
  useMultiRuntimeProfile,
} from "@/hooks/use-multi-runtime-profile";

// ---------------------------------------------------------------------------
// Apply-mode badge
// ---------------------------------------------------------------------------

const APPLY_MODE_BADGE: Record<
  MultiRuntimeApplyMode,
  { label: string; variant: "default" | "secondary" | "outline" | "destructive" }
> = {
  live: { label: "live", variant: "default" },
  soft_reload: { label: "soft reload", variant: "secondary" },
  hard_restart: { label: "restart", variant: "destructive" },
  unsupported: { label: "unsupported", variant: "outline" },
};

function ApplyModeBadge({ mode }: Readonly<{ mode: MultiRuntimeApplyMode }>) {
  const { label, variant } = APPLY_MODE_BADGE[mode];
  return <Badge variant={variant}>{label}</Badge>;
}

// ---------------------------------------------------------------------------
// Cache options
// ---------------------------------------------------------------------------

const CACHE_OPTIONS: SelectMenuOption[] = [
  { value: "", label: "default (framework)" },
  { value: "static", label: "static" },
  { value: "dynamic", label: "dynamic" },
  { value: "offloaded", label: "offloaded" },
];

const EXECUTION_MODE_OPTIONS: SelectMenuOption[] = [
  { value: "balanced", label: "balanced" },
  { value: "vision_priority", label: "vision_priority" },
  { value: "voice_priority", label: "voice_priority" },
];

const IMAGE_STRATEGY_OPTIONS: SelectMenuOption[] = [
  { value: "vlm_only", label: "vlm_only" },
  { value: "ocr_first", label: "ocr_first" },
  { value: "hybrid", label: "hybrid" },
];

const RETRIEVAL_MODE_OPTIONS: SelectMenuOption[] = [
  { value: "off", label: "off" },
  { value: "auto", label: "auto" },
  { value: "always", label: "always" },
];

const AUDIO_OUTPUT_MODE_OPTIONS: SelectMenuOption[] = [
  { value: "off", label: "off" },
  { value: "text_first", label: "text_first" },
  { value: "voice_first", label: "voice_first" },
];

const ASSISTANT_MODE_OPTIONS: SelectMenuOption[] = [
  { value: "off", label: "off" },
  { value: "attached", label: "attached" },
  { value: "conditional", label: "conditional" },
];

const ECONOMY_MODE_OPTIONS: SelectMenuOption[] = [
  { value: "off", label: "off" },
  { value: "auto", label: "auto" },
];

// ---------------------------------------------------------------------------
// Main panel (self-contained with hook)
// ---------------------------------------------------------------------------

type Props = Readonly<{
  pollingIntervalMs?: number;
}>;

export function MultiRuntimeProfilePanel({ pollingIntervalMs }: Props) {
  const state = useMultiRuntimeProfile(pollingIntervalMs);
  return <MultiRuntimeProfilePanelInner state={state} />;
}

// ---------------------------------------------------------------------------
// Inner panel (accepts injected state — testable without hooks)
// ---------------------------------------------------------------------------

type InnerProps = Readonly<{
  state: MultiRuntimeProfileState;
}>;

export function MultiRuntimeProfilePanelInner({ state }: InnerProps) {
  const t = useTranslation();
  const { data, loading, error, updatePending, lastUpdateResult, applyUpdate } =
    state;

  const profile = data?.profile ?? null;
  const matrix = data?.apply_matrix ?? null;

  const [localTokens, setLocalTokens] = useState<string>("");
  const [localImageBudget, setLocalImageBudget] = useState<string>("");
  const [localThinking, setLocalThinking] = useState<boolean | null>(null);
  const [localReasoningSummary, setLocalReasoningSummary] = useState<boolean | null>(
    null,
  );
  const [localEmotionDetection, setLocalEmotionDetection] = useState<
    boolean | null
  >(null);
  const [localEmotionResponseStyle, setLocalEmotionResponseStyle] = useState<
    boolean | null
  >(null);
  const [localCache, setLocalCache] = useState<string | null>(null);
  const [localExecutionMode, setLocalExecutionMode] = useState<string | null>(null);
  const [localImageStrategy, setLocalImageStrategy] = useState<string | null>(null);
  const [localRetrievalMode, setLocalRetrievalMode] = useState<string | null>(null);
  const [localAudioOutputMode, setLocalAudioOutputMode] = useState<string | null>(null);
  const [localAssistantMode, setLocalAssistantMode] = useState<string | null>(null);
  const [localEconomyMode, setLocalEconomyMode] = useState<string | null>(null);

  if (loading && !data) {
    return (
      <div
        className="text-sm text-muted-foreground p-4"
        aria-busy="true"
        aria-label={t("runtime.profile.loading")}
      >
        {t("runtime.profile.loading")}
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="text-sm text-destructive p-4" role="alert">
        {error}
      </div>
    );
  }

  const effectiveThinking = localThinking ?? profile?.enable_thinking ?? false;
  const effectiveReasoningSummary =
    localReasoningSummary ?? profile?.reasoning_summary_enabled ?? false;
  const effectiveEmotionDetection =
    localEmotionDetection ?? profile?.emotion_detection_enabled ?? false;
  const effectiveEmotionResponseStyle =
    localEmotionResponseStyle ?? profile?.emotion_response_style_enabled ?? false;
  const effectiveTokens =
    localTokens === "" ? String(profile?.max_new_tokens ?? 128) : localTokens;
  const effectiveImageBudget =
    localImageBudget === ""
      ? String(profile?.image_token_budget ?? 280)
      : localImageBudget;
  const effectiveCache =
    localCache === null ? (profile?.cache_implementation ?? "") : localCache;
  const effectiveExecutionMode =
    localExecutionMode === null
      ? (profile?.execution_mode ?? "balanced")
      : localExecutionMode;
  const effectiveImageStrategy =
    localImageStrategy === null
      ? (profile?.image_strategy ?? "vlm_only")
      : localImageStrategy;
  const effectiveRetrievalMode =
    localRetrievalMode === null
      ? (profile?.retrieval_mode ?? "off")
      : localRetrievalMode;
  const effectiveAudioOutputMode =
    localAudioOutputMode === null
      ? (profile?.audio_output_mode ?? "off")
      : localAudioOutputMode;
  const effectiveAssistantMode =
    localAssistantMode === null
      ? (profile?.assistant_mode ?? "off")
      : localAssistantMode;
  const effectiveEconomyMode =
    localEconomyMode === null ? (profile?.economy_mode ?? "off") : localEconomyMode;

  const busy = updatePending;

  async function handleApplyLive() {
    const parsed = Number.parseInt(effectiveTokens, 10);
    const parsedBudget = Number.parseInt(effectiveImageBudget, 10);
    const update: MultiRuntimeProfileUpdateRequest = {
      max_new_tokens: Number.isNaN(parsed) ? undefined : parsed,
      image_token_budget: Number.isNaN(parsedBudget) ? undefined : parsedBudget,
      enable_thinking: effectiveThinking,
      reasoning_summary_enabled: effectiveReasoningSummary,
      emotion_detection_enabled: effectiveEmotionDetection,
      emotion_response_style_enabled: effectiveEmotionResponseStyle,
    };
    await applyUpdate(update);
  }

  async function handleApplyCacheImpl() {
    await applyUpdate({
      cache_implementation: effectiveCache === "" ? null : effectiveCache,
    });
  }

  async function handleApplyPolicy() {
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
  }

  return (
    <div className="space-y-6 p-4" data-testid="multi-runtime-profile-panel">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">
            {t("runtime.profile.title")}
          </h3>
          {!data?.daemon_reachable && (
            <p className="text-xs text-muted-foreground mt-0.5">
              {t("runtime.profile.daemonOffline")}
            </p>
          )}
        </div>
        {data?.daemon_reachable === true && (
          <Badge variant="default" className="text-xs">
            {t("runtime.profile.daemonOnline")}
          </Badge>
        )}
      </div>

      {/* Model info (read-only — hard_restart) */}
      <section aria-labelledby="profile-model-section">
        <div className="flex items-center gap-2 mb-2" id="profile-model-section">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {t("runtime.profile.model")}
          </span>
          {matrix && <ApplyModeBadge mode={matrix.model_id} />}
        </div>
        <div className="text-sm font-mono bg-muted rounded px-2 py-1 truncate">
          {profile?.model_id ?? "—"}
        </div>
        {profile?.assistant_model_id && (
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-muted-foreground">
              {t("runtime.profile.assistantModel")}:
            </span>
            <span className="text-xs font-mono">{profile.assistant_model_id}</span>
            {matrix && <ApplyModeBadge mode={matrix.assistant_model_id} />}
          </div>
        )}
      </section>

      {/* Live params */}
      <section aria-labelledby="profile-live-section">
        <div className="flex items-center gap-2 mb-3" id="profile-live-section">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {t("runtime.profile.liveParams")}
          </span>
          {matrix && <ApplyModeBadge mode={matrix.max_new_tokens} />}
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-sm" htmlFor="profile-max-tokens">
              {t("voice.daemon.maxNewTokens")}
            </label>
            <input
              id="profile-max-tokens"
              type="number"
              min={1}
              max={32768}
              value={effectiveTokens}
              onChange={(e) => setLocalTokens(e.target.value)}
              disabled={busy}
              className="w-24 text-sm border rounded px-2 py-0.5 text-right disabled:opacity-50"
            />
          </div>

          <div className="flex items-center justify-between">
            <label className="text-sm" htmlFor="profile-image-budget">
              {t("voice.daemon.imageTokenBudget")}
            </label>
            <input
              id="profile-image-budget"
              type="number"
              min={70}
              max={1120}
              value={effectiveImageBudget}
              onChange={(e) => setLocalImageBudget(e.target.value)}
              disabled={busy}
              className="w-24 text-sm border rounded px-2 py-0.5 text-right disabled:opacity-50"
            />
          </div>

          {[
            {
              id: "profile-thinking",
              label: t("voice.daemon.thinking"),
              checked: effectiveThinking,
              set: setLocalThinking,
            },
            {
              id: "profile-reasoning",
              label: t("voice.daemon.reasoningSummary"),
              checked: effectiveReasoningSummary,
              set: setLocalReasoningSummary,
            },
            {
              id: "profile-emotion-detection",
              label: t("voice.daemon.emotionDetection"),
              checked: effectiveEmotionDetection,
              set: setLocalEmotionDetection,
            },
            {
              id: "profile-emotion-style",
              label: t("voice.daemon.emotionResponseStyle"),
              checked: effectiveEmotionResponseStyle,
              set: setLocalEmotionResponseStyle,
            },
          ].map(({ id, label, checked, set }) => (
            <div key={id} className="flex items-center justify-between">
              <label className="text-sm" htmlFor={id}>
                {label}
              </label>
              <Switch
                id={id}
                checked={checked}
                onCheckedChange={set}
                disabled={busy}
              />
            </div>
          ))}
        </div>

        <Button
          size="sm"
          className="mt-3 w-full"
          onClick={handleApplyLive}
          disabled={busy || !data?.daemon_reachable}
        >
          {busy ? t("runtime.profile.applying") : t("runtime.profile.applyLive")}
        </Button>
      </section>

      {/* Cache (soft_reload) */}
      <section aria-labelledby="profile-cache-section">
        <div className="flex items-center gap-2 mb-2" id="profile-cache-section">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {t("runtime.profile.cacheImpl")}
          </span>
          {matrix && <ApplyModeBadge mode={matrix.cache_implementation} />}
        </div>
        <SelectMenu
          value={effectiveCache}
          options={CACHE_OPTIONS}
          onChange={setLocalCache}
          disabled={busy}
        />
        <Button
          size="sm"
          variant="secondary"
          className="mt-2 w-full"
          onClick={handleApplyCacheImpl}
          disabled={busy || !data?.daemon_reachable}
        >
          {t("runtime.profile.stageCacheReload")}
        </Button>
      </section>

      {/* Execution policy (live) */}
      <section aria-labelledby="profile-policy-section">
        <div className="flex items-center gap-2 mb-2" id="profile-policy-section">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Execution Policy
          </span>
          {matrix && <ApplyModeBadge mode={matrix.execution_mode} />}
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm">execution_mode</span>
            <div className="w-48">
              <SelectMenu
                value={effectiveExecutionMode}
                options={EXECUTION_MODE_OPTIONS}
                onChange={setLocalExecutionMode}
                disabled={busy}
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm">image_strategy</span>
            <div className="w-48">
              <SelectMenu
                value={effectiveImageStrategy}
                options={IMAGE_STRATEGY_OPTIONS}
                onChange={setLocalImageStrategy}
                disabled={busy}
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm">retrieval_mode</span>
            <div className="w-48">
              <SelectMenu
                value={effectiveRetrievalMode}
                options={RETRIEVAL_MODE_OPTIONS}
                onChange={setLocalRetrievalMode}
                disabled={busy}
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm">audio_output_mode</span>
            <div className="w-48">
              <SelectMenu
                value={effectiveAudioOutputMode}
                options={AUDIO_OUTPUT_MODE_OPTIONS}
                onChange={setLocalAudioOutputMode}
                disabled={busy}
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm">assistant_mode</span>
            <div className="w-48">
              <SelectMenu
                value={effectiveAssistantMode}
                options={ASSISTANT_MODE_OPTIONS}
                onChange={setLocalAssistantMode}
                disabled={busy}
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm">economy_mode</span>
            <div className="w-48">
              <SelectMenu
                value={effectiveEconomyMode}
                options={ECONOMY_MODE_OPTIONS}
                onChange={setLocalEconomyMode}
                disabled={busy}
              />
            </div>
          </div>
        </div>
        <Button
          size="sm"
          className="mt-3 w-full"
          onClick={handleApplyPolicy}
          disabled={busy || !data?.daemon_reachable}
        >
          {busy ? t("runtime.profile.applying") : "Apply policy"}
        </Button>
      </section>

      {/* Unsupported fields (read-only info) */}
      <section aria-labelledby="profile-unsupported-section">
        <div
          className="flex items-center gap-2 mb-2"
          id="profile-unsupported-section"
        >
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {t("runtime.profile.unsupportedFields")}
          </span>
          {matrix && <ApplyModeBadge mode={matrix.precision} />}
        </div>
        <div className="text-xs text-muted-foreground space-y-1">
          <div>
            {t("runtime.profile.precision")}: <strong>{profile?.precision ?? "auto"}</strong>
          </div>
          <div>
            {t("runtime.profile.quantizationBackend")}:{" "}
            <strong>{profile?.quantization_backend ?? "none"}</strong>
          </div>
          <div>
            {t("runtime.profile.deviceTarget")}:{" "}
            <strong>{profile?.device_target ?? "auto"}</strong>
          </div>
        </div>
      </section>

      {/* Last update result */}
      {lastUpdateResult && (
        <section
          aria-labelledby="profile-update-result"
          className="text-xs border rounded p-2 space-y-1"
        >
          <div className="flex items-center gap-2" id="profile-update-result">
            <span className="font-medium">{t("runtime.profile.lastUpdate")}</span>
            <ApplyModeBadge mode={lastUpdateResult.required_apply_mode} />
            {lastUpdateResult.applied && (
              <Badge variant="default">{t("runtime.profile.applied")}</Badge>
            )}
          </div>
          {lastUpdateResult.rejected.length > 0 && (
            <ul className="text-destructive space-y-0.5">
              {lastUpdateResult.rejected.map((r) => (
                <li key={r.field}>
                  {r.field}: {r.reason}
                </li>
              ))}
            </ul>
          )}
          <p className="text-muted-foreground">{lastUpdateResult.message}</p>
        </section>
      )}
    </div>
  );
}
