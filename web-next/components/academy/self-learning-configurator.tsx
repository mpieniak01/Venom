"use client";

import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
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
  readonly trainableModels: readonly SelfLearningTrainableModelInfo[];
  readonly embeddingProfiles: readonly SelfLearningEmbeddingProfile[];
  readonly onStart: (config: SelfLearningConfig) => Promise<void> | void;
}

type TranslateFn = ReturnType<typeof useTranslation>;

function computeCanStart(params: {
  sourcesCount: number;
  loading: boolean;
  mode: SelfLearningMode;
  effectiveBaseModel: string;
  selectedEmbeddingProfileState: SelfLearningEmbeddingProfile | null;
  embeddingPolicy: SelfLearningEmbeddingPolicy;
}): boolean {
  if (params.sourcesCount === 0 || params.loading) {
    return false;
  }
  if (params.mode === "llm_finetune") {
    return params.effectiveBaseModel.length > 0;
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
          dataset_strategy: params.datasetStrategy,
          task_mix_preset: params.taskMixPreset,
          lora_rank: 16,
          learning_rate: 0.0002,
          num_epochs: 3,
          batch_size: 4,
          max_seq_length: 2048,
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

function ModeSection({
  mode,
  t,
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
      <div className="space-y-3">
        <div className="space-y-1">
          <label htmlFor="self-learning-base-model" className="text-xs text-[color:var(--text-secondary)]">
            {t("academy.selfLearning.config.baseModel")}
          </label>
          <select
            id="self-learning-base-model"
            value={effectiveBaseModel}
            onChange={(event) => onBaseModelChange(event.target.value)}
            className="flex h-9 w-full rounded-md border border-white/10 bg-transparent px-3 py-1 text-sm text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500"
          >
            {trainableModels.length === 0 ? (
              <option value="">{t("academy.selfLearning.config.noTrainableModels")}</option>
            ) : (
              trainableModels.map((model) => (
                <option key={model.model_id} value={model.model_id}>
                  {model.model_id}
                </option>
              ))
            )}
          </select>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor="self-learning-dataset-strategy" className="text-xs text-[color:var(--text-secondary)]">
              {t("academy.selfLearning.config.datasetStrategy")}
            </label>
            <select
              id="self-learning-dataset-strategy"
              value={datasetStrategy}
              onChange={(event) =>
                onDatasetStrategyChange(event.target.value as SelfLearningDatasetStrategy)
              }
              className="flex h-9 w-full rounded-md border border-white/10 bg-transparent px-3 py-1 text-sm text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500"
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
            <label htmlFor="self-learning-task-mix" className="text-xs text-[color:var(--text-secondary)]">
              {t("academy.selfLearning.config.taskMixPreset")}
            </label>
            <select
              id="self-learning-task-mix"
              value={taskMixPreset}
              onChange={(event) => onTaskMixPresetChange(event.target.value as SelfLearningTaskMixPreset)}
              className="flex h-9 w-full rounded-md border border-white/10 bg-transparent px-3 py-1 text-sm text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500"
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

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="self-learning-embedding-profile" className="text-xs text-[color:var(--text-secondary)]">
            {t("academy.selfLearning.config.embeddingProfile")}
          </label>
          <select
            id="self-learning-embedding-profile"
            value={effectiveEmbeddingProfile}
            onChange={(event) => onEmbeddingProfileChange(event.target.value)}
            className="flex h-9 w-full rounded-md border border-white/10 bg-transparent px-3 py-1 text-sm text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500"
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
          <label htmlFor="self-learning-embedding-policy" className="text-xs text-[color:var(--text-secondary)]">
            {t("academy.selfLearning.config.embeddingPolicy")}
          </label>
          <select
            id="self-learning-embedding-policy"
            value={embeddingPolicy}
            onChange={(event) => onEmbeddingPolicyChange(event.target.value as SelfLearningEmbeddingPolicy)}
            className="flex h-9 w-full rounded-md border border-white/10 bg-transparent px-3 py-1 text-sm text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500"
          >
            <option value="strict">{t("academy.selfLearning.config.embeddingPolicyStrict")}</option>
            <option value="allow_fallback">{t("academy.selfLearning.config.embeddingPolicyAllowFallback")}</option>
          </select>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="self-learning-rag-chunking-mode" className="text-xs text-[color:var(--text-secondary)]">
            {t("academy.selfLearning.config.ragChunkingMode")}
          </label>
          <select
            id="self-learning-rag-chunking-mode"
            value={ragChunkingMode}
            onChange={(event) => onRagChunkingModeChange(event.target.value as SelfLearningRagChunkingMode)}
            className="flex h-9 w-full rounded-md border border-white/10 bg-transparent px-3 py-1 text-sm text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500"
          >
            <option value="plain">{t("academy.selfLearning.config.ragChunkingModes.plain")}</option>
            <option value="code_aware">{t("academy.selfLearning.config.ragChunkingModes.codeAware")}</option>
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="self-learning-rag-retrieval-mode" className="text-xs text-[color:var(--text-secondary)]">
            {t("academy.selfLearning.config.ragRetrievalMode")}
          </label>
          <select
            id="self-learning-rag-retrieval-mode"
            value={ragRetrievalMode}
            onChange={(event) => onRagRetrievalModeChange(event.target.value as SelfLearningRagRetrievalMode)}
            className="flex h-9 w-full rounded-md border border-white/10 bg-transparent px-3 py-1 text-sm text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500"
          >
            <option value="vector">{t("academy.selfLearning.config.ragRetrievalModes.vector")}</option>
            <option value="hybrid">{t("academy.selfLearning.config.ragRetrievalModes.hybrid")}</option>
          </select>
        </div>
      </div>
      <div className="space-y-1 rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] px-3 py-2 text-xs text-[color:var(--text-secondary)]">
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
              {t("academy.selfLearning.config.preflightProvider")}: {selectedEmbeddingProfileState.provider}
            </p>
            <p>
              {t("academy.selfLearning.config.preflightModel")}: {selectedEmbeddingProfileState.model}
            </p>
            <p>
              {t("academy.selfLearning.config.preflightDimension")}: {selectedEmbeddingProfileState.dimension ?? "-"}
            </p>
            <p>
              {t("academy.selfLearning.config.preflightFallback")}:{" "}
              {selectedEmbeddingProfileState.fallback_active
                ? t("academy.selfLearning.config.preflightFallbackActive")
                : t("academy.selfLearning.config.preflightFallbackInactive")}
            </p>
          </>
        ) : (
          <p>{t("academy.selfLearning.config.preflightNoProfile")}</p>
        )}
      </div>
    </div>
  );
}

export function SelfLearningConfigurator({
  loading,
  trainableModels,
  embeddingProfiles,
  onStart,
}: Props) {
  const t = useTranslation();
  const [mode, setMode] = useState<SelfLearningMode>("rag_index");
  const [sources, setSources] = useState<SelfLearningSource[]>([
    "docs",
    "docs_dev",
    "code",
  ]);
  const [dryRun, setDryRun] = useState(false);
  const [maxFileSizeKb, setMaxFileSizeKb] = useState(256);
  const [maxFiles, setMaxFiles] = useState(1500);
  const [maxTotalSizeMb, setMaxTotalSizeMb] = useState(200);
  const [selectedBaseModel, setSelectedBaseModel] = useState<string>("");
  const [datasetStrategy, setDatasetStrategy] = useState<SelfLearningDatasetStrategy>("reconstruct");
  const [taskMixPreset, setTaskMixPreset] = useState<SelfLearningTaskMixPreset>("balanced");
  const [selectedEmbeddingProfile, setSelectedEmbeddingProfile] = useState<string>("");
  const [embeddingPolicy, setEmbeddingPolicy] = useState<SelfLearningEmbeddingPolicy>("strict");
  const [ragChunkingMode, setRagChunkingMode] = useState<SelfLearningRagChunkingMode>("plain");
  const [ragRetrievalMode, setRagRetrievalMode] = useState<SelfLearningRagRetrievalMode>("vector");

  const defaultBaseModel = useMemo(
    () => trainableModels.find((item) => item.recommended)?.model_id ?? trainableModels[0]?.model_id ?? "",
    [trainableModels],
  );
  const defaultEmbeddingProfile = useMemo(
    () => embeddingProfiles[0]?.profile_id ?? "",
    [embeddingProfiles],
  );
  const effectiveBaseModel = selectedBaseModel || defaultBaseModel;
  const effectiveEmbeddingProfile = selectedEmbeddingProfile || defaultEmbeddingProfile;
  const selectedEmbeddingProfileState = useMemo(
    () => embeddingProfiles.find((profile) => profile.profile_id === effectiveEmbeddingProfile) ?? null,
    [embeddingProfiles, effectiveEmbeddingProfile],
  );

  const canStart = useMemo(
    () =>
      computeCanStart({
        sourcesCount: sources.length,
        loading,
        mode,
        effectiveBaseModel,
        selectedEmbeddingProfileState,
        embeddingPolicy,
      }),
    [sources.length, loading, mode, effectiveBaseModel, selectedEmbeddingProfileState, embeddingPolicy],
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

  const sourceItems: ReadonlyArray<{ source: SelfLearningSource; labelKey: string }> = [
    { source: "docs", labelKey: "academy.selfLearning.config.sources.docs" },
    { source: "docs_dev", labelKey: "academy.selfLearning.config.sources.docsDev" },
    { source: "code", labelKey: "academy.selfLearning.config.sources.code" },
  ];

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
        trainableModels={trainableModels}
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

      <div className="space-y-3">
        <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-secondary)]">
          {t("academy.selfLearning.config.sourcesLabel")}
        </p>
        <div className="space-y-2 rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-3">
          {sourceItems.map((item) => (
            <label key={item.source} className="flex items-center gap-3 text-sm text-[color:var(--text-primary)]">
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
