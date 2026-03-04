"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  type SelfLearningEmbeddingPolicy,
  type SelfLearningEmbeddingProfile,
  type SelfLearningLimits,
  type SelfLearningLlmConfig,
  type SelfLearningMode,
  type SelfLearningRagConfig,
  type SelfLearningSource,
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
  const [selectedEmbeddingProfile, setSelectedEmbeddingProfile] = useState<string>("");
  const [embeddingPolicy, setEmbeddingPolicy] = useState<SelfLearningEmbeddingPolicy>("strict");

  const defaultBaseModel = useMemo(
    () => trainableModels.find((item) => item.recommended)?.model_id ?? trainableModels[0]?.model_id ?? "",
    [trainableModels],
  );
  const defaultEmbeddingProfile = useMemo(
    () => embeddingProfiles[0]?.profile_id ?? "",
    [embeddingProfiles],
  );
  const selectedEmbeddingProfileState = useMemo(
    () => embeddingProfiles.find((profile) => profile.profile_id === selectedEmbeddingProfile) ?? null,
    [embeddingProfiles, selectedEmbeddingProfile],
  );

  useEffect(() => {
    if (!selectedBaseModel && defaultBaseModel) {
      setSelectedBaseModel(defaultBaseModel);
    }
  }, [defaultBaseModel, selectedBaseModel]);

  useEffect(() => {
    if (!selectedEmbeddingProfile && defaultEmbeddingProfile) {
      setSelectedEmbeddingProfile(defaultEmbeddingProfile);
    }
  }, [defaultEmbeddingProfile, selectedEmbeddingProfile]);

  const canStart = useMemo(() => {
    if (sources.length === 0 || loading) return false;
    if (mode === "llm_finetune") return selectedBaseModel.length > 0;
    if (!selectedEmbeddingProfileState || !selectedEmbeddingProfileState.healthy) return false;
    if (embeddingPolicy === "strict" && selectedEmbeddingProfileState.fallback_active) return false;
    return true;
  }, [
    sources.length,
    loading,
    mode,
    selectedBaseModel,
    selectedEmbeddingProfileState,
    embeddingPolicy,
  ]);

  const toggleSource = (source: SelfLearningSource) => {
    setSources((prev) =>
      prev.includes(source) ? prev.filter((item) => item !== source) : [...prev, source]
    );
  };

  const handleStart = async () => {
    if (!canStart) return;
    await onStart({
      mode,
      sources,
      dry_run: dryRun,
      limits: {
        max_file_size_kb: maxFileSizeKb,
        max_files: maxFiles,
        max_total_size_mb: maxTotalSizeMb,
      },
      llm_config:
        mode === "llm_finetune"
          ? {
              base_model: selectedBaseModel,
              lora_rank: 16,
              learning_rate: 0.0002,
              num_epochs: 3,
              batch_size: 4,
              max_seq_length: 2048,
            }
          : null,
      rag_config:
        mode === "rag_index"
          ? {
              collection: "default",
              category: "academy_self_learning",
              chunk_text: false,
              embedding_profile_id: selectedEmbeddingProfile,
              embedding_policy: embeddingPolicy,
            }
          : null,
    });
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

      {mode === "llm_finetune" ? (
        <div className="space-y-1">
          <label htmlFor="self-learning-base-model" className="text-xs text-[color:var(--text-secondary)]">
            {t("academy.selfLearning.config.baseModel")}
          </label>
          <select
            id="self-learning-base-model"
            value={selectedBaseModel}
            onChange={(event) => setSelectedBaseModel(event.target.value)}
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
      ) : (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <label htmlFor="self-learning-embedding-profile" className="text-xs text-[color:var(--text-secondary)]">
                {t("academy.selfLearning.config.embeddingProfile")}
              </label>
              <select
                id="self-learning-embedding-profile"
                value={selectedEmbeddingProfile}
                onChange={(event) => setSelectedEmbeddingProfile(event.target.value)}
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
                onChange={(event) => setEmbeddingPolicy(event.target.value as SelfLearningEmbeddingPolicy)}
                className="flex h-9 w-full rounded-md border border-white/10 bg-transparent px-3 py-1 text-sm text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500"
              >
                <option value="strict">{t("academy.selfLearning.config.embeddingPolicyStrict")}</option>
                <option value="allow_fallback">{t("academy.selfLearning.config.embeddingPolicyAllowFallback")}</option>
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
      )}

      <div className="space-y-3">
        <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-secondary)]">
          {t("academy.selfLearning.config.sourcesLabel")}
        </p>
        <div className="space-y-2 rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-3">
          <label className="flex items-center gap-3 text-sm text-[color:var(--text-primary)]">
            <Checkbox checked={sources.includes("docs")} onCheckedChange={() => toggleSource("docs")} />
            {t("academy.selfLearning.config.sources.docs")}
          </label>
          <label className="flex items-center gap-3 text-sm text-[color:var(--text-primary)]">
            <Checkbox
              checked={sources.includes("docs_dev")}
              onCheckedChange={() => toggleSource("docs_dev")}
            />
            {t("academy.selfLearning.config.sources.docsDev")}
          </label>
          <label className="flex items-center gap-3 text-sm text-[color:var(--text-primary)]">
            <Checkbox checked={sources.includes("code")} onCheckedChange={() => toggleSource("code")} />
            {t("academy.selfLearning.config.sources.code")}
          </label>
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
