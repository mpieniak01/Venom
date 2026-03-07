"use client";

import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { SelectMenu, type SelectMenuOption } from "@/components/ui/select-menu";
import {
  type SelfLearningDatasetStrategy,
  type SelfLearningEmbeddingPolicy,
  type SelfLearningEmbeddingProfile,
  type SelfLearningLimits,
  type SelfLearningLlmConfig,
  type SelfLearningMode,
  type SelfLearningRagChunkingMode,
  type SelfLearningRagConfig,
  type SelfLearningRagRetrievalMode,
  type SelfLearningSource,
  type SelfLearningTaskMixPreset,
  type SelfLearningTrainableModelInfo,
} from "@/lib/academy-api";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";

export interface SelfLearningConfig {
  mode: SelfLearningMode;
  sources: SelfLearningSource[];
  limits: SelfLearningLimits;
  llm_config: SelfLearningLlmConfig | null;
  rag_config: SelfLearningRagConfig | null;
  dry_run: boolean;
}

interface Props {
  readonly loading: boolean;
  readonly runtimeOptions: ReadonlyArray<{ id: string; label: string }>;
  readonly selectedRuntime: string;
  readonly onRuntimeChange: (runtimeId: string) => void;
  readonly trainableModels: readonly SelfLearningTrainableModelInfo[];
  readonly embeddingProfiles: readonly SelfLearningEmbeddingProfile[];
  readonly defaultEmbeddingProfileId?: string | null;
  readonly onStart: (config: SelfLearningConfig) => Promise<void> | void;
}

type TranslateFn = ReturnType<typeof useTranslation>;
type SupportedEngine =
  | "unsloth"
  | "huggingface"
  | "onnx"
  | "vllm"
  | "ollama"
  | "openai"
  | "google"
  | "config"
  | "unknown";

const FIELD_LABEL_CLASS = "text-xs text-[color:var(--text-secondary)]";
const FIELD_SELECT_CLASS =
  "flex h-9 w-full rounded-md border border-white/10 bg-transparent px-3 py-1 text-sm text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500";
const SELECT_MENU_BUTTON_CLASS =
  "mt-0 h-10 w-full justify-between rounded-md border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] px-3 py-2 text-sm text-[color:var(--text-primary)] ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--primary)] focus-visible:ring-offset-2";
const SELECT_MENU_MENU_CLASS =
  "w-[min(980px,96vw)] max-h-[360px] overflow-y-auto rounded-md border border-[color:var(--ui-border-strong)] bg-[color:var(--bg-panel)] p-1 shadow-card backdrop-blur-md";
const SELECT_MENU_OPTION_CLASS =
  "rounded-md px-3 py-2 text-[color:var(--text-primary)] hover:bg-[color:var(--ui-surface-hover)]";
const SUPPORTED_ENGINES: ReadonlySet<SupportedEngine> = new Set([
  "unsloth",
  "huggingface",
  "onnx",
  "vllm",
  "ollama",
  "openai",
  "google",
  "config",
]);

const SOURCE_ITEMS: ReadonlyArray<{
  source: SelfLearningSource;
  labelKey: string;
  nested?: boolean;
}> = [
  { source: "docs", labelKey: "academy.selfLearning.config.sources.docs" },
  { source: "docs_en", labelKey: "academy.selfLearning.config.sources.docsEn", nested: true },
  { source: "docs_pl", labelKey: "academy.selfLearning.config.sources.docsPl", nested: true },
  { source: "docs_dev", labelKey: "academy.selfLearning.config.sources.docsDev" },
  { source: "repo_readmes", labelKey: "academy.selfLearning.config.sources.repoReadmes" },
  { source: "code", labelKey: "academy.selfLearning.config.sources.code" },
];

function resolveEngineKey(provider: string): SupportedEngine {
  const normalized = provider.trim().toLowerCase() as SupportedEngine;
  if (SUPPORTED_ENGINES.has(normalized)) {
    return normalized;
  }
  return "unknown";
}

function getRuntimeDisplayName(runtimeId: string, t: TranslateFn): string {
  const engineKey = resolveEngineKey(runtimeId);
  if (engineKey === "unknown") {
    return runtimeId;
  }
  return t(`academy.training.engineNames.${engineKey}`);
}

function getModelCompatibility(model: SelfLearningTrainableModelInfo): string[] {
  const entries = Object.entries(model.runtime_compatibility ?? {})
    .filter(([, isCompatible]) => Boolean(isCompatible))
    .map(([runtimeId]) => runtimeId);
  const runtimeOrder: Record<string, number> = {
    vllm: 0,
    ollama: 1,
    onnx: 2,
  };
  return entries.sort((left, right) => {
    const leftOrder = runtimeOrder[left] ?? 99;
    const rightOrder = runtimeOrder[right] ?? 99;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return left.localeCompare(right);
  });
}

function resolveDefaultEmbeddingProfileId(
  defaultEmbeddingProfileId: string | null | undefined,
  embeddingProfileIds: Set<string>,
  embeddingProfiles: readonly SelfLearningEmbeddingProfile[],
): string {
  if (defaultEmbeddingProfileId && embeddingProfileIds.has(defaultEmbeddingProfileId)) {
    return defaultEmbeddingProfileId;
  }
  return (
    embeddingProfiles.find((item) => item.healthy)?.profile_id ||
    embeddingProfiles[0]?.profile_id ||
    ""
  );
}

function getInstallStateLabel(
  model: SelfLearningTrainableModelInfo,
  t: TranslateFn,
): string {
  return model.installed_local
    ? t("academy.training.installState.localInstalled")
    : t("academy.training.installState.catalogDownload");
}

function getModelRuntimeBadgeLabel(params: {
  model: SelfLearningTrainableModelInfo;
  selectedRuntime: string;
  t: TranslateFn;
}): string {
  const { model, selectedRuntime, t } = params;
  if (selectedRuntime && model.runtime_compatibility?.[selectedRuntime]) {
    return getRuntimeDisplayName(selectedRuntime, t);
  }
  if (model.recommended_runtime && model.runtime_compatibility?.[model.recommended_runtime]) {
    return getRuntimeDisplayName(model.recommended_runtime, t);
  }
  const compatibility = getModelCompatibility(model);
  if (compatibility.length > 0) {
    return getRuntimeDisplayName(compatibility[0], t);
  }
  return t(`academy.training.engineNames.${resolveEngineKey(model.provider)}`);
}

function computeCanStart(params: {
  sourcesCount: number;
  loading: boolean;
  mode: SelfLearningMode;
  selectedBaseModel: string;
  effectiveEmbeddingProfile: string;
  selectedEmbeddingProfileState: SelfLearningEmbeddingProfile | null;
  embeddingPolicy: SelfLearningEmbeddingPolicy;
}): boolean {
  if (params.sourcesCount === 0 || params.loading) {
    return false;
  }
  if (params.mode === "llm_finetune") {
    return params.selectedBaseModel.length > 0;
  }
  if (params.effectiveEmbeddingProfile.length === 0) {
    return false;
  }
  if (!params.selectedEmbeddingProfileState?.healthy) {
    return false;
  }
  if (
    params.embeddingPolicy === "strict" &&
    params.selectedEmbeddingProfileState.fallback_active
  ) {
    return false;
  }
  return true;
}

function buildSelfLearningConfig(params: {
  mode: SelfLearningMode;
  selectedRuntime: string;
  sources: SelfLearningSource[];
  dryRun: boolean;
  maxFileSizeKb: number;
  maxFiles: number;
  maxTotalSizeMb: number;
  effectiveBaseModel: string;
  datasetStrategy: SelfLearningDatasetStrategy;
  taskMixPreset: SelfLearningTaskMixPreset;
  effectiveEmbeddingProfile: string;
  embeddingPolicy: SelfLearningEmbeddingPolicy;
  ragChunkingMode: SelfLearningRagChunkingMode;
  ragRetrievalMode: SelfLearningRagRetrievalMode;
}): SelfLearningConfig {
  const llmConfig: SelfLearningLlmConfig | null =
    params.mode === "llm_finetune"
      ? {
          base_model: params.effectiveBaseModel,
          runtime_id: params.selectedRuntime || null,
          dataset_strategy: params.datasetStrategy,
          task_mix_preset: params.taskMixPreset,
          lora_rank: 8,
          learning_rate: 0.0002,
          num_epochs: 2,
          batch_size: 1,
          max_seq_length: 1024,
        }
      : null;
  const ragConfig: SelfLearningRagConfig | null =
    params.mode === "rag_index"
      ? {
          collection: "default",
          category: "academy_self_learning",
          chunk_text: false,
          chunking_mode: params.ragChunkingMode,
          retrieval_mode: params.ragRetrievalMode,
          embedding_profile_id: params.effectiveEmbeddingProfile,
          embedding_policy: params.embeddingPolicy,
        }
      : null;

  return {
    mode: params.mode,
    sources: params.sources,
    dry_run: params.dryRun,
    limits: {
      max_file_size_kb: params.maxFileSizeKb,
      max_files: params.maxFiles,
      max_total_size_mb: params.maxTotalSizeMb,
    },
    llm_config: llmConfig,
    rag_config: ragConfig,
  };
}

interface ModeSectionProps {
  readonly mode: SelfLearningMode;
  readonly t: TranslateFn;
  readonly runtimeOptions: ReadonlyArray<{ id: string; label: string }>;
  readonly selectedRuntime: string;
  readonly onRuntimeChange: (runtimeId: string) => void;
  readonly trainableModels: readonly SelfLearningTrainableModelInfo[];
  readonly embeddingProfiles: readonly SelfLearningEmbeddingProfile[];
  readonly effectiveBaseModel: string;
  readonly datasetStrategy: SelfLearningDatasetStrategy;
  readonly taskMixPreset: SelfLearningTaskMixPreset;
  readonly effectiveEmbeddingProfile: string;
  readonly embeddingPolicy: SelfLearningEmbeddingPolicy;
  readonly selectedEmbeddingProfileState: SelfLearningEmbeddingProfile | null;
  readonly ragChunkingMode: SelfLearningRagChunkingMode;
  readonly ragRetrievalMode: SelfLearningRagRetrievalMode;
  readonly onBaseModelChange: (value: string) => void;
  readonly onDatasetStrategyChange: (value: SelfLearningDatasetStrategy) => void;
  readonly onTaskMixPresetChange: (value: SelfLearningTaskMixPreset) => void;
  readonly onEmbeddingProfileChange: (value: string) => void;
  readonly onEmbeddingPolicyChange: (value: SelfLearningEmbeddingPolicy) => void;
  readonly onRagChunkingModeChange: (value: SelfLearningRagChunkingMode) => void;
  readonly onRagRetrievalModeChange: (value: SelfLearningRagRetrievalMode) => void;
}

interface LlmModeSectionProps {
  readonly t: TranslateFn;
  readonly runtimeOptions: ReadonlyArray<{ id: string; label: string }>;
  readonly selectedRuntime: string;
  readonly onRuntimeChange: (runtimeId: string) => void;
  readonly trainableModels: readonly SelfLearningTrainableModelInfo[];
  readonly effectiveBaseModel: string;
  readonly datasetStrategy: SelfLearningDatasetStrategy;
  readonly taskMixPreset: SelfLearningTaskMixPreset;
  readonly onBaseModelChange: (value: string) => void;
  readonly onDatasetStrategyChange: (value: SelfLearningDatasetStrategy) => void;
  readonly onTaskMixPresetChange: (value: SelfLearningTaskMixPreset) => void;
}

function LlmModeSection({
  t,
  runtimeOptions,
  selectedRuntime,
  onRuntimeChange,
  trainableModels,
  effectiveBaseModel,
  datasetStrategy,
  taskMixPreset,
  onBaseModelChange,
  onDatasetStrategyChange,
  onTaskMixPresetChange,
}: LlmModeSectionProps) {
  const selectedModel =
    trainableModels.find((model) => model.model_id === effectiveBaseModel) ?? null;
  const hasRuntimeCompatibleModels = trainableModels.length > 0;
  const compatibility = selectedModel ? getModelCompatibility(selectedModel) : [];
  const compatibilityLabel =
    compatibility.length > 0
      ? compatibility.map((runtime) => getRuntimeDisplayName(runtime, t)).join(" • ")
      : t("academy.training.runtimeUnknown");
  const runtimeSelectOptions: SelectMenuOption[] = runtimeOptions.map((runtime) => ({
    value: runtime.id,
    label: runtime.label,
  }));
  const baseModelOptions: SelectMenuOption[] = trainableModels.map((model) => ({
    value: model.model_id,
    label: model.model_id,
    description: getInstallStateLabel(model, t),
  }));

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <label className={FIELD_LABEL_CLASS}>{t("cockpit.models.server")}</label>
        <SelectMenu
          value={selectedRuntime}
          options={runtimeSelectOptions}
          onChange={onRuntimeChange}
          placeholder={t("cockpit.models.chooseServer")}
          ariaLabel={t("cockpit.actions.selectServer")}
          buttonTestId="academy-self-learning-runtime-select"
          optionTestIdPrefix="academy-self-learning-runtime-option"
          disabled={runtimeSelectOptions.length === 0}
          buttonClassName={SELECT_MENU_BUTTON_CLASS}
          menuClassName={SELECT_MENU_MENU_CLASS}
          optionClassName={SELECT_MENU_OPTION_CLASS}
        />
      </div>
      <div className="space-y-1">
        <label className={FIELD_LABEL_CLASS}>{t("academy.selfLearning.config.baseModel")}</label>
        <SelectMenu
          value={effectiveBaseModel}
          options={baseModelOptions}
          onChange={onBaseModelChange}
          placeholder={
            hasRuntimeCompatibleModels
              ? t("academy.selfLearning.config.chooseBaseModel")
              : t("academy.selfLearning.config.noTrainableModels")
          }
          ariaLabel={t("academy.selfLearning.config.baseModel")}
          buttonTestId="academy-self-learning-base-model-select"
          optionTestIdPrefix="academy-self-learning-base-model-option"
          disabled={baseModelOptions.length === 0}
          buttonClassName={SELECT_MENU_BUTTON_CLASS}
          menuClassName={SELECT_MENU_MENU_CLASS}
          optionClassName={SELECT_MENU_OPTION_CLASS}
          renderButton={(option) => {
            if (!option) {
              return (
                <span className="min-w-0 flex-1 truncate text-left text-hint">
                  {hasRuntimeCompatibleModels
                    ? t("academy.selfLearning.config.chooseBaseModel")
                    : t("academy.selfLearning.config.noTrainableModels")}
                </span>
              );
            }
            const model = trainableModels.find((item) => item.model_id === option.value);
            return (
              <div className="flex min-w-0 flex-1 items-center justify-between gap-2 text-left">
                <span className="min-w-0 flex-1 truncate text-left text-sm text-[color:var(--text-primary)]">
                  {option.label}
                </span>
                {model ? (
                  <span className="shrink-0 text-[11px] text-[color:var(--ui-muted)]">
                    {getModelRuntimeBadgeLabel({ model, selectedRuntime, t })}
                  </span>
                ) : null}
              </div>
            );
          }}
          renderOption={(option, active) => {
            const model = trainableModels.find((item) => item.model_id === option.value);
            if (!model) {
              return (
                <span className={`text-sm ${active ? "text-[color:var(--primary)]" : "text-[color:var(--text-primary)]"}`}>
                  {option.label}
                </span>
              );
            }
            return (
              <div className="flex w-full items-center justify-between gap-2 text-left">
                <span
                  className={`min-w-0 flex-1 truncate text-left text-sm ${
                    active ? "text-[color:var(--primary)]" : "text-[color:var(--text-primary)]"
                  }`}
                >
                  {model.model_id}
                </span>
                <div className="flex shrink-0 items-center gap-2 text-right">
                  <span className="text-[11px] text-[color:var(--ui-muted)]">
                    {getModelRuntimeBadgeLabel({ model, selectedRuntime, t })}
                  </span>
                  <span className="text-[11px] text-hint/80">
                    {getInstallStateLabel(model, t)}
                  </span>
                </div>
              </div>
            );
          }}
        />
        {!hasRuntimeCompatibleModels && selectedRuntime ? (
          <div className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-100">
            {t("academy.selfLearning.config.runtimeModelMismatchWarning", {
              runtime: getRuntimeDisplayName(selectedRuntime, t),
            })}
          </div>
        ) : null}
        {hasRuntimeCompatibleModels && !selectedModel ? (
          <div className="mt-2 rounded-md border border-[color:var(--ui-border)] bg-[color:var(--bg-panel)] px-3 py-2 text-[11px] text-[color:var(--text-secondary)]">
            {t("academy.selfLearning.config.baseModelSelectionRequired")}
          </div>
        ) : null}
        {selectedModel ? (
          <div className="mt-2 rounded-md border border-[color:var(--ui-border-strong)] bg-[color:var(--bg-panel)] px-3 py-2 text-[11px] text-[color:var(--text-primary)]">
            <p>
              <span className="text-[color:var(--text-secondary)]">{t("academy.training.engineLabel")}:</span>{" "}
              {t(`academy.training.engineNames.${resolveEngineKey(selectedModel.provider)}`)} •{" "}
              <span className="text-[color:var(--text-secondary)]">
                {t("academy.training.compatibilityLabel")}:
              </span>{" "}
              {compatibilityLabel} • {getInstallStateLabel(selectedModel, t)}
            </p>
            <p className="mt-1 text-[color:var(--text-secondary)]">
              {t("academy.selfLearning.config.chatDeployHint")}
            </p>
          </div>
        ) : null}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="self-learning-dataset-strategy" className={FIELD_LABEL_CLASS}>
            {t("academy.selfLearning.config.datasetStrategy")}
          </label>
          <select
            id="self-learning-dataset-strategy"
            value={datasetStrategy}
            onChange={(event) =>
              onDatasetStrategyChange(event.target.value as SelfLearningDatasetStrategy)
            }
            className={FIELD_SELECT_CLASS}
          >
            <option value="reconstruct">
              {t("academy.selfLearning.config.datasetStrategies.reconstruct")}
            </option>
            <option value="qa_from_docs">
              {t("academy.selfLearning.config.datasetStrategies.qaFromDocs")}
            </option>
            <option value="repo_tasks_basic">
              {t("academy.selfLearning.config.datasetStrategies.repoTasksBasic")}
            </option>
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="self-learning-task-mix" className={FIELD_LABEL_CLASS}>
            {t("academy.selfLearning.config.taskMixPreset")}
          </label>
          <select
            id="self-learning-task-mix"
            value={taskMixPreset}
            onChange={(event) => onTaskMixPresetChange(event.target.value as SelfLearningTaskMixPreset)}
            className={FIELD_SELECT_CLASS}
            disabled={datasetStrategy === "reconstruct"}
          >
            <option value="balanced">{t("academy.selfLearning.config.taskMixPresets.balanced")}</option>
            <option value="qa-heavy">{t("academy.selfLearning.config.taskMixPresets.qaHeavy")}</option>
            <option value="repair-heavy">{t("academy.selfLearning.config.taskMixPresets.repairHeavy")}</option>
          </select>
        </div>
      </div>
    </div>
  );
}

interface RagModeSectionProps {
  readonly t: TranslateFn;
  readonly embeddingProfiles: readonly SelfLearningEmbeddingProfile[];
  readonly effectiveEmbeddingProfile: string;
  readonly embeddingPolicy: SelfLearningEmbeddingPolicy;
  readonly selectedEmbeddingProfileState: SelfLearningEmbeddingProfile | null;
  readonly ragChunkingMode: SelfLearningRagChunkingMode;
  readonly ragRetrievalMode: SelfLearningRagRetrievalMode;
  readonly onEmbeddingProfileChange: (value: string) => void;
  readonly onEmbeddingPolicyChange: (value: SelfLearningEmbeddingPolicy) => void;
  readonly onRagChunkingModeChange: (value: SelfLearningRagChunkingMode) => void;
  readonly onRagRetrievalModeChange: (value: SelfLearningRagRetrievalMode) => void;
}

function RagModeSection({
  t,
  embeddingProfiles,
  effectiveEmbeddingProfile,
  embeddingPolicy,
  selectedEmbeddingProfileState,
  ragChunkingMode,
  ragRetrievalMode,
  onEmbeddingProfileChange,
  onEmbeddingPolicyChange,
  onRagChunkingModeChange,
  onRagRetrievalModeChange,
}: RagModeSectionProps) {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="self-learning-embedding-profile" className={FIELD_LABEL_CLASS}>
            {t("academy.selfLearning.config.embeddingProfile")}
          </label>
          <select
            id="self-learning-embedding-profile"
            value={effectiveEmbeddingProfile}
            onChange={(event) => onEmbeddingProfileChange(event.target.value)}
            className={FIELD_SELECT_CLASS}
          >
            {embeddingProfiles.length === 0 ? (
              <option value="">{t("academy.selfLearning.config.noEmbeddingProfiles")}</option>
            ) : (
              embeddingProfiles.map((profile) => (
                <option key={profile.profile_id} value={profile.profile_id}>
                  {profile.provider}/{profile.model}
                </option>
              ))
            )}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="self-learning-embedding-policy" className={FIELD_LABEL_CLASS}>
            {t("academy.selfLearning.config.embeddingPolicy")}
          </label>
          <select
            id="self-learning-embedding-policy"
            value={embeddingPolicy}
            onChange={(event) => onEmbeddingPolicyChange(event.target.value as SelfLearningEmbeddingPolicy)}
            className={FIELD_SELECT_CLASS}
          >
            <option value="strict">{t("academy.selfLearning.config.embeddingPolicyStrict")}</option>
            <option value="allow_fallback">
              {t("academy.selfLearning.config.embeddingPolicyAllowFallback")}
            </option>
          </select>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="self-learning-rag-chunking-mode" className={FIELD_LABEL_CLASS}>
            {t("academy.selfLearning.config.ragChunkingMode")}
          </label>
          <select
            id="self-learning-rag-chunking-mode"
            value={ragChunkingMode}
            onChange={(event) => onRagChunkingModeChange(event.target.value as SelfLearningRagChunkingMode)}
            className={FIELD_SELECT_CLASS}
          >
            <option value="plain">{t("academy.selfLearning.config.ragChunkingModes.plain")}</option>
            <option value="code_aware">{t("academy.selfLearning.config.ragChunkingModes.codeAware")}</option>
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="self-learning-rag-retrieval-mode" className={FIELD_LABEL_CLASS}>
            {t("academy.selfLearning.config.ragRetrievalMode")}
          </label>
          <select
            id="self-learning-rag-retrieval-mode"
            value={ragRetrievalMode}
            onChange={(event) => onRagRetrievalModeChange(event.target.value as SelfLearningRagRetrievalMode)}
            className={FIELD_SELECT_CLASS}
          >
            <option value="vector">{t("academy.selfLearning.config.ragRetrievalModes.vector")}</option>
            <option value="hybrid">{t("academy.selfLearning.config.ragRetrievalModes.hybrid")}</option>
          </select>
        </div>
      </div>
      <div className="space-y-1 rounded-lg border border-[color:var(--ui-border-strong)] bg-[color:var(--bg-panel)] px-3 py-2 text-xs text-[color:var(--text-primary)]">
        <p className="font-semibold text-[color:var(--text-heading)]">
          {t("academy.selfLearning.config.preflightTitle")}
        </p>
        {selectedEmbeddingProfileState ? (
          <>
            <p className={selectedEmbeddingProfileState.healthy ? "text-emerald-300" : "text-red-300"}>
              {selectedEmbeddingProfileState.healthy
                ? t("academy.selfLearning.config.preflightHealthy")
                : t("academy.selfLearning.config.preflightUnhealthy")}
            </p>
            <p>
              <span className="text-[color:var(--text-secondary)]">
                {t("academy.selfLearning.config.preflightProvider")}:
              </span>{" "}
              {selectedEmbeddingProfileState.provider}
            </p>
            <p>
              <span className="text-[color:var(--text-secondary)]">
                {t("academy.selfLearning.config.preflightModel")}:
              </span>{" "}
              {selectedEmbeddingProfileState.model}
            </p>
            <p>
              <span className="text-[color:var(--text-secondary)]">
                {t("academy.selfLearning.config.preflightDimension")}:
              </span>{" "}
              {selectedEmbeddingProfileState.dimension ?? "-"}
            </p>
            <p>
              <span className="text-[color:var(--text-secondary)]">
                {t("academy.selfLearning.config.preflightFallback")}:
              </span>{" "}
              {selectedEmbeddingProfileState.fallback_active
                ? t("academy.selfLearning.config.preflightFallbackActive")
                : t("academy.selfLearning.config.preflightFallbackInactive")}
            </p>
          </>
        ) : (
          <p className="text-[color:var(--text-secondary)]">
            {t("academy.selfLearning.config.preflightNoProfile")}
          </p>
        )}
      </div>
    </div>
  );
}

function ModeSection({
  mode,
  t,
  runtimeOptions,
  selectedRuntime,
  onRuntimeChange,
  trainableModels,
  embeddingProfiles,
  effectiveBaseModel,
  datasetStrategy,
  taskMixPreset,
  effectiveEmbeddingProfile,
  embeddingPolicy,
  selectedEmbeddingProfileState,
  ragChunkingMode,
  ragRetrievalMode,
  onBaseModelChange,
  onDatasetStrategyChange,
  onTaskMixPresetChange,
  onEmbeddingProfileChange,
  onEmbeddingPolicyChange,
  onRagChunkingModeChange,
  onRagRetrievalModeChange,
}: ModeSectionProps) {
  if (mode === "llm_finetune") {
    return (
      <LlmModeSection
        t={t}
        runtimeOptions={runtimeOptions}
        selectedRuntime={selectedRuntime}
        onRuntimeChange={onRuntimeChange}
        trainableModels={trainableModels}
        effectiveBaseModel={effectiveBaseModel}
        datasetStrategy={datasetStrategy}
        taskMixPreset={taskMixPreset}
        onBaseModelChange={onBaseModelChange}
        onDatasetStrategyChange={onDatasetStrategyChange}
        onTaskMixPresetChange={onTaskMixPresetChange}
      />
    );
  }
  return (
    <RagModeSection
      t={t}
      embeddingProfiles={embeddingProfiles}
      effectiveEmbeddingProfile={effectiveEmbeddingProfile}
      embeddingPolicy={embeddingPolicy}
      selectedEmbeddingProfileState={selectedEmbeddingProfileState}
      ragChunkingMode={ragChunkingMode}
      ragRetrievalMode={ragRetrievalMode}
      onEmbeddingProfileChange={onEmbeddingProfileChange}
      onEmbeddingPolicyChange={onEmbeddingPolicyChange}
      onRagChunkingModeChange={onRagChunkingModeChange}
      onRagRetrievalModeChange={onRagRetrievalModeChange}
    />
  );
}

function RuntimePreflightSection({
  t,
  selectedRuntime,
  effectiveBaseModel,
  effectiveCompatibility,
  hasCompatibleTrainableModels,
}: {
  t: TranslateFn;
  selectedRuntime: string;
  effectiveBaseModel: string;
  effectiveCompatibility: string[];
  hasCompatibleTrainableModels: boolean;
}) {
  return (
    <div className="space-y-1 rounded-lg border border-[color:var(--ui-border-strong)] bg-[color:var(--bg-panel)] px-3 py-2 text-xs text-[color:var(--text-primary)]">
      <p className="font-semibold text-[color:var(--text-heading)]">
        {t("academy.selfLearning.config.preflightTitle")}
      </p>
      <p>
        <span className="text-[color:var(--text-secondary)]">{t("cockpit.models.server")}:</span>{" "}
        {selectedRuntime ? getRuntimeDisplayName(selectedRuntime, t) : t("academy.training.runtimeUnknown")}
      </p>
      <p>
        <span className="text-[color:var(--text-secondary)]">{t("academy.selfLearning.config.baseModel")}:</span>{" "}
        {effectiveBaseModel || t("academy.selfLearning.config.noTrainableModels")}
      </p>
      <p>
        <span className="text-[color:var(--text-secondary)]">{t("academy.training.compatibilityLabel")}:</span>{" "}
        {effectiveCompatibility.length > 0
          ? effectiveCompatibility.map((runtime) => getRuntimeDisplayName(runtime, t)).join(" • ")
          : t("academy.training.runtimeUnknown")}
      </p>
      {!hasCompatibleTrainableModels && selectedRuntime ? (
        <p className="text-amber-200">
          {t("academy.selfLearning.config.runtimeModelMismatchWarning", {
            runtime: getRuntimeDisplayName(selectedRuntime, t),
          })}
        </p>
      ) : null}
    </div>
  );
}

export function SelfLearningConfigurator({
  loading,
  runtimeOptions,
  selectedRuntime,
  onRuntimeChange,
  trainableModels,
  embeddingProfiles,
  defaultEmbeddingProfileId: defaultEmbeddingProfileIdProp,
  onStart,
}: Props) {
  const t = useTranslation();
  const [mode, setMode] = useState<SelfLearningMode>("rag_index");
  const [sources, setSources] = useState<SelfLearningSource[]>(["docs"]);
  const [dryRun, setDryRun] = useState(false);
  const [maxFileSizeKb, setMaxFileSizeKb] = useState(128);
  const [maxFiles, setMaxFiles] = useState(300);
  const [maxTotalSizeMb, setMaxTotalSizeMb] = useState(32);
  const [selectedBaseModel, setSelectedBaseModel] = useState<string>("");
  const [datasetStrategy, setDatasetStrategy] = useState<SelfLearningDatasetStrategy>("reconstruct");
  const [taskMixPreset, setTaskMixPreset] = useState<SelfLearningTaskMixPreset>("balanced");
  const [selectedEmbeddingProfile, setSelectedEmbeddingProfile] = useState<string>("");
  const [embeddingPolicy, setEmbeddingPolicy] = useState<SelfLearningEmbeddingPolicy>("strict");
  const [ragChunkingMode, setRagChunkingMode] = useState<SelfLearningRagChunkingMode>("plain");
  const [ragRetrievalMode, setRagRetrievalMode] = useState<SelfLearningRagRetrievalMode>("vector");

  const compatibleTrainableModels = useMemo(
    () =>
      selectedRuntime
        ? trainableModels.filter((item) => Boolean(item.runtime_compatibility?.[selectedRuntime]))
        : trainableModels,
    [selectedRuntime, trainableModels],
  );
  const trainableModelIds = useMemo(
    () => new Set(compatibleTrainableModels.map((item) => item.model_id)),
    [compatibleTrainableModels],
  );
  const embeddingProfileIds = useMemo(
    () => new Set(embeddingProfiles.map((item) => item.profile_id)),
    [embeddingProfiles],
  );
  const defaultEmbeddingProfile = useMemo(
    () =>
      resolveDefaultEmbeddingProfileId(
        defaultEmbeddingProfileIdProp,
        embeddingProfileIds,
        embeddingProfiles,
      ),
    [defaultEmbeddingProfileIdProp, embeddingProfileIds, embeddingProfiles],
  );
  const effectiveBaseModel =
    selectedBaseModel && trainableModelIds.has(selectedBaseModel) ? selectedBaseModel : "";
  const effectiveEmbeddingProfile =
    selectedEmbeddingProfile && embeddingProfileIds.has(selectedEmbeddingProfile)
      ? selectedEmbeddingProfile
      : defaultEmbeddingProfile;
  const selectedEmbeddingProfileState = useMemo(
    () => embeddingProfiles.find((profile) => profile.profile_id === effectiveEmbeddingProfile) ?? null,
    [embeddingProfiles, effectiveEmbeddingProfile],
  );
  const selectedBaseModelState = useMemo(
    () => compatibleTrainableModels.find((model) => model.model_id === effectiveBaseModel) ?? null,
    [compatibleTrainableModels, effectiveBaseModel],
  );
  const hasCompatibleTrainableModels = compatibleTrainableModels.length > 0;
  const effectiveCompatibility = useMemo(
    () => (selectedBaseModelState ? getModelCompatibility(selectedBaseModelState) : []),
    [selectedBaseModelState],
  );

  const canStart = useMemo(
    () =>
      computeCanStart({
        sourcesCount: sources.length,
        loading,
        mode,
        selectedBaseModel: effectiveBaseModel,
        effectiveEmbeddingProfile,
        selectedEmbeddingProfileState,
        embeddingPolicy,
      }),
    [
      sources.length,
      loading,
      mode,
      effectiveBaseModel,
      effectiveEmbeddingProfile,
      selectedEmbeddingProfileState,
      embeddingPolicy,
    ],
  );

  const toggleSource = (source: SelfLearningSource) => {
    setSources((prev) =>
      prev.includes(source) ? prev.filter((item) => item !== source) : [...prev, source]
    );
  };

  const handleStart = async () => {
    if (!canStart) return;
    await onStart(
      buildSelfLearningConfig({
        mode,
        selectedRuntime,
        sources,
        dryRun,
        maxFileSizeKb,
        maxFiles,
        maxTotalSizeMb,
        effectiveBaseModel,
        datasetStrategy,
        taskMixPreset,
        effectiveEmbeddingProfile,
        embeddingPolicy,
        ragChunkingMode,
        ragRetrievalMode,
      }),
    );
  };

  return (
    <div className="space-y-6 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-6">
      <div>
        <h3 className="text-base font-semibold text-[color:var(--text-heading)]">
          {t("academy.selfLearning.config.title")}
        </h3>
        <p className="text-sm text-hint">{t("academy.selfLearning.config.description")}</p>
      </div>

      <div className="space-y-3">
        <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-secondary)]">
          {t("academy.selfLearning.config.modeLabel")}
        </p>
        <div className="grid gap-2 md:grid-cols-2">
          <button
            type="button"
            onClick={() => setMode("rag_index")}
            className={cn(
              "rounded-lg border px-3 py-2 text-left text-sm transition",
              mode === "rag_index"
                ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-200"
                : "border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] text-[color:var(--text-secondary)]"
            )}
          >
            <p className="font-semibold">{t("academy.selfLearning.config.modes.rag.title")}</p>
            <p className="text-xs text-hint">{t("academy.selfLearning.config.modes.rag.description")}</p>
          </button>
          <button
            type="button"
            onClick={() => setMode("llm_finetune")}
            className={cn(
              "rounded-lg border px-3 py-2 text-left text-sm transition",
              mode === "llm_finetune"
                ? "border-violet-500/50 bg-violet-500/10 text-violet-200"
                : "border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] text-[color:var(--text-secondary)]"
            )}
          >
            <p className="font-semibold">{t("academy.selfLearning.config.modes.llm.title")}</p>
            <p className="text-xs text-hint">{t("academy.selfLearning.config.modes.llm.description")}</p>
          </button>
        </div>
      </div>

      <ModeSection
          mode={mode}
          t={t}
          runtimeOptions={runtimeOptions}
          selectedRuntime={selectedRuntime}
          onRuntimeChange={onRuntimeChange}
          trainableModels={compatibleTrainableModels}
        embeddingProfiles={embeddingProfiles}
        effectiveBaseModel={effectiveBaseModel}
        datasetStrategy={datasetStrategy}
        taskMixPreset={taskMixPreset}
        effectiveEmbeddingProfile={effectiveEmbeddingProfile}
        embeddingPolicy={embeddingPolicy}
        selectedEmbeddingProfileState={selectedEmbeddingProfileState}
        ragChunkingMode={ragChunkingMode}
        ragRetrievalMode={ragRetrievalMode}
        onBaseModelChange={setSelectedBaseModel}
        onDatasetStrategyChange={setDatasetStrategy}
        onTaskMixPresetChange={setTaskMixPreset}
        onEmbeddingProfileChange={setSelectedEmbeddingProfile}
        onEmbeddingPolicyChange={setEmbeddingPolicy}
        onRagChunkingModeChange={setRagChunkingMode}
        onRagRetrievalModeChange={setRagRetrievalMode}
      />

      {mode === "llm_finetune" ? (
        <RuntimePreflightSection
          t={t}
          selectedRuntime={selectedRuntime}
          effectiveBaseModel={effectiveBaseModel}
          effectiveCompatibility={effectiveCompatibility}
          hasCompatibleTrainableModels={hasCompatibleTrainableModels}
        />
      ) : null}

      <div className="space-y-3">
        <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-secondary)]">
          {t("academy.selfLearning.config.sourcesLabel")}
        </p>
        <div className="space-y-2 rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-3">
          {SOURCE_ITEMS.map((item) => (
            <label
              key={item.source}
              className={cn(
                "flex items-center gap-3 text-sm text-[color:var(--text-primary)]",
                item.nested ? "pl-6 text-xs text-[color:var(--text-secondary)]" : ""
              )}
            >
              <Checkbox checked={sources.includes(item.source)} onCheckedChange={() => toggleSource(item.source)} />
              {t(item.labelKey)}
            </label>
          ))}
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <div className="space-y-1">
          <label htmlFor="max-file-size" className="text-xs text-[color:var(--text-secondary)]">
            {t("academy.selfLearning.config.maxFileSize")}
          </label>
          <Input
            id="max-file-size"
            type="number"
            min={16}
            max={4096}
            value={maxFileSizeKb}
            onChange={(event) => setMaxFileSizeKb(Number.parseInt(event.target.value, 10) || 16)}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="max-files" className="text-xs text-[color:var(--text-secondary)]">
            {t("academy.selfLearning.config.maxFiles")}
          </label>
          <Input
            id="max-files"
            type="number"
            min={1}
            max={10000}
            value={maxFiles}
            onChange={(event) => setMaxFiles(Number.parseInt(event.target.value, 10) || 1)}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="max-total-size" className="text-xs text-[color:var(--text-secondary)]">
            {t("academy.selfLearning.config.maxTotalSize")}
          </label>
          <Input
            id="max-total-size"
            type="number"
            min={1}
            max={4096}
            value={maxTotalSizeMb}
            onChange={(event) => setMaxTotalSizeMb(Number.parseInt(event.target.value, 10) || 1)}
          />
        </div>
      </div>

      <label className="flex items-center gap-3 text-sm text-[color:var(--text-primary)]">
        <Checkbox checked={dryRun} onCheckedChange={(checked) => setDryRun(Boolean(checked))} />
        {t("academy.selfLearning.config.dryRun")}
      </label>

      <Button onClick={handleStart} disabled={!canStart} className="w-full gap-2">
        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        {loading ? t("academy.selfLearning.config.starting") : t("academy.selfLearning.config.start")}
      </Button>
    </div>
  );
}
