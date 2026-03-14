"use client";

import { useState, useEffect, useCallback } from "react";
import { Play, Loader2, RefreshCw, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SelectMenu, type SelectMenuOption } from "@/components/ui/select-menu";
import { useToast } from "@/components/ui/toast";
import { LogViewer } from "./log-viewer";
import {
  startTraining,
  listJobs,
  getUnifiedModelCatalog,
  resolveAcademyApiErrorMessage,
  type TrainingJob,
  type TrainingJobStatus,
  type TrainableModelInfo,
} from "@/lib/academy-api";
import { ApiError } from "@/lib/api-client";
import { useLanguage, useTranslation } from "@/lib/i18n";
import { normalizeRuntimeId } from "@/lib/cockpit-runtime-selection";

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

export type ModelSectionKey = "localFirst" | "cloudFree" | "cloudOther";
export type ModelPickerOption = SelectMenuOption & {
  kind: "section" | "model";
  sectionKey?: ModelSectionKey;
  model?: TrainableModelInfo;
};

type TranslateFn = (key: string) => string;

export const MODEL_SECTION_ORDER: ModelSectionKey[] = [
  "localFirst",
  "cloudFree",
  "cloudOther",
];

export function resolveTrainingEngineKey(provider: string): SupportedEngine {
  const normalized = provider.trim().toLowerCase();
  if (
    normalized === "unsloth" ||
    normalized === "huggingface" ||
    normalized === "onnx" ||
    normalized === "vllm" ||
    normalized === "ollama" ||
    normalized === "openai" ||
    normalized === "google" ||
    normalized === "config"
  ) {
    return normalized;
  }
  return "unknown";
}

export function getTrainingStatusColor(status: TrainingJobStatus): string {
  switch (status) {
    case "queued":
      return "text-amber-300 bg-amber-500/10";
    case "preparing":
      return "text-indigo-300 bg-indigo-500/10";
    case "finished":
      return "text-emerald-400 bg-emerald-500/10";
    case "running":
      return "text-blue-400 bg-blue-500/10";
    case "failed":
      return "text-red-400 bg-red-500/10";
    case "cancelled":
      return "text-orange-300 bg-orange-500/10";
    default:
      return "text-zinc-400 bg-zinc-500/10";
  }
}

export function getTrainingStatusLabel(
  status: TrainingJobStatus,
  t: TranslateFn,
): string {
  const labels: Record<TrainingJobStatus, string> = {
    queued: t("academy.training.status.queued"),
    preparing: t("academy.training.status.preparing"),
    running: t("academy.training.status.running"),
    finished: t("academy.training.status.finished"),
    failed: t("academy.training.status.failed"),
    cancelled: t("academy.training.status.cancelled"),
  };
  return labels[status];
}

export function getModelCompatibility(model: TrainableModelInfo): string[] {
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

export function getSelectedModelCompatibilityLabel(
  selectedModel: TrainableModelInfo | null,
  getRuntimeDisplayName: (runtimeId: string) => string,
  t: TranslateFn,
): string {
  if (!selectedModel) {
    return "";
  }
  const compatibility = getModelCompatibility(selectedModel);
  if (compatibility.length === 0) {
    return t("academy.training.runtimeUnknown");
  }
  return compatibility.map((runtime) => getRuntimeDisplayName(runtime)).join(" • ");
}

export function resolveTrainingBaseModelPlaceholder(
  modelsLoading: boolean,
  trainableModelsCount: number,
  t: TranslateFn,
): string {
  if (modelsLoading) {
    return t("academy.training.loadingModels");
  }
  if (trainableModelsCount === 0) {
    return t("academy.training.noTrainableModels");
  }
  return t("academy.training.chooseBaseModel");
}

export function getTrainingModelRuntimeBadgeLabel(
  model: TrainableModelInfo,
  selectedRuntime: string,
  getRuntimeDisplayName: (runtimeId: string) => string,
  t: TranslateFn,
): string {
  if (selectedRuntime && model.runtime_compatibility?.[selectedRuntime]) {
    return getRuntimeDisplayName(selectedRuntime);
  }
  if (
    model.recommended_runtime &&
    model.runtime_compatibility?.[model.recommended_runtime]
  ) {
    return getRuntimeDisplayName(model.recommended_runtime);
  }
  const compatibility = getModelCompatibility(model);
  if (compatibility.length > 0) {
    return getRuntimeDisplayName(compatibility[0]);
  }
  return t(`academy.training.engineNames.${resolveTrainingEngineKey(model.provider)}`);
}

export function getTrainingModelInstallStateLabel(
  selectedModel: TrainableModelInfo | null,
  t: TranslateFn,
): string {
  if (!selectedModel) {
    return "";
  }
  return selectedModel.installed_local
    ? t("academy.training.installState.localInstalled")
    : t("academy.training.installState.catalogDownload");
}

type RuntimeOption = { id: string; label: string };
type RuntimeCapabilityMap = Record<
  string,
  {
    supports_native_training?: boolean;
    supports_adapter_runtime_apply?: boolean;
  }
>;

function buildTrainingRuntimeOptions(
  runtimes: NonNullable<Awaited<ReturnType<typeof getUnifiedModelCatalog>>["runtimes"]>,
  getRuntimeDisplayName: (runtimeId: string) => string,
): RuntimeOption[] {
  return runtimes
    .filter(
      (runtime) =>
        runtime.source_type === "local-runtime" &&
        runtime.configured &&
        runtime.available,
    )
    .map((runtime) => ({
      id: normalizeRuntimeId(runtime.runtime_id),
      label: getRuntimeDisplayName(runtime.runtime_id),
    }));
}

function buildTrainingRuntimeCapabilities(
  runtimes: NonNullable<Awaited<ReturnType<typeof getUnifiedModelCatalog>>["runtimes"]>,
): RuntimeCapabilityMap {
  return runtimes.reduce<RuntimeCapabilityMap>((acc, runtime) => {
    acc[runtime.runtime_id] = {
      supports_native_training: runtime.supports_native_training,
      supports_adapter_runtime_apply: runtime.supports_adapter_runtime_apply,
    };
    return acc;
  }, {});
}

function resolvePreferredTrainingRuntime(
  catalog: Awaited<ReturnType<typeof getUnifiedModelCatalog>>,
  runtimeOverride: string | undefined,
  selectedRuntime: string,
): string {
  const activeRuntimeId = normalizeRuntimeId(
    String(catalog.active?.runtime_id || catalog.active?.active_server || ""),
  );
  return (
    normalizeRuntimeId(runtimeOverride || "") ||
    normalizeRuntimeId(selectedRuntime) ||
    activeRuntimeId ||
    ""
  );
}

function filterTrainableModelsForRuntime(
  catalog: Awaited<ReturnType<typeof getUnifiedModelCatalog>>,
  preferredRuntime: string,
): TrainableModelInfo[] {
  const trainableCandidates =
    catalog.trainable_base_models.length > 0
      ? catalog.trainable_base_models
      : catalog.trainable_models;
  return trainableCandidates.filter(
    (model) =>
      model.trainable &&
      (!preferredRuntime || Boolean(model.runtime_compatibility?.[preferredRuntime])),
  );
}

function resetTrainingCatalogState(
  setTrainableModels: React.Dispatch<React.SetStateAction<TrainableModelInfo[]>>,
  setRuntimeOptions: React.Dispatch<React.SetStateAction<RuntimeOption[]>>,
  setRuntimeCapabilities: React.Dispatch<React.SetStateAction<RuntimeCapabilityMap>>,
  setSelectedRuntime: React.Dispatch<React.SetStateAction<string>>,
  setSelectedBaseModel: React.Dispatch<React.SetStateAction<string>>,
): void {
  setTrainableModels([]);
  setRuntimeOptions([]);
  setRuntimeCapabilities({});
  setSelectedRuntime("");
  setSelectedBaseModel("");
}

export function getTrainingModelSectionKey(model: TrainableModelInfo): ModelSectionKey {
  if (model.installed_local) return "localFirst";
  if (model.cost_tier === "free") return "cloudFree";
  return "cloudOther";
}

export function buildTrainingModelPickerOptions(
  trainableModels: TrainableModelInfo[],
  t: TranslateFn,
): ModelPickerOption[] {
  const modelSections = MODEL_SECTION_ORDER.map((sectionKey) => ({
    sectionKey,
    models: trainableModels.filter((model) => getTrainingModelSectionKey(model) === sectionKey),
  })).filter((section) => section.models.length > 0);

  return modelSections.flatMap((section): ModelPickerOption[] => {
    const sectionLabel = t(`academy.training.modelSections.${section.sectionKey}`);
    const sectionMeta = t(`academy.training.modelSectionMeta.${section.sectionKey}`);
    const header: ModelPickerOption = {
      value: `__section__${section.sectionKey}`,
      label: sectionLabel,
      description: sectionMeta,
      disabled: true,
      kind: "section",
      sectionKey: section.sectionKey,
    };
    const sectionModels = section.models.map((model) => ({
      value: model.model_id,
      label: model.model_id,
      kind: "model" as const,
      model,
    }));
    return [header, ...sectionModels];
  });
}

export function resolveTrainingBaseModelSelection(
  currentSelection: string,
  trainableModels: readonly TrainableModelInfo[],
): string {
  if (
    currentSelection &&
    trainableModels.some((model) => model.model_id === currentSelection)
  ) {
    return currentSelection;
  }
  return "";
}

export function TrainingPanel() {
  const { language } = useLanguage();
  const t = useTranslation();
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [loraRank, setLoraRank] = useState(8);
  const [learningRate, setLearningRate] = useState(0.0002);
  const [numEpochs, setNumEpochs] = useState(2);
  const [batchSize, setBatchSize] = useState(1);
  const [onnxConversionMode, setOnnxConversionMode] = useState<"none" | "merge_export">("none");
  const [autoSignForChat, setAutoSignForChat] = useState(false);
  const [chatSigner, setChatSigner] = useState("academy-ui");
  const [chatTargetModelId, setChatTargetModelId] = useState("");
  const [viewingLogs, setViewingLogs] = useState<string | null>(null);
  const [trainableModels, setTrainableModels] = useState<TrainableModelInfo[]>([]);
  const [runtimeOptions, setRuntimeOptions] = useState<RuntimeOption[]>([]);
  const [runtimeCapabilities, setRuntimeCapabilities] = useState<RuntimeCapabilityMap>({});
  const [selectedRuntime, setSelectedRuntime] = useState("");
  const [selectedBaseModel, setSelectedBaseModel] = useState("");
  const [modelsLoading, setModelsLoading] = useState(false);

  const getRuntimeDisplayName = useCallback((runtimeId: string): string => {
    const engineKey = resolveTrainingEngineKey(runtimeId);
    if (engineKey === "unknown") {
      return runtimeId;
    }
    return t(`academy.training.engineNames.${engineKey}`);
  }, [t]);

  const loadJobs = useCallback(async () => {
    try {
      const data = await listJobs({ limit: 50 });
      setJobs(data.jobs);
    } catch (err) {
      console.error("Failed to load jobs:", err);
    }
  }, []);

  const loadTrainableModels = useCallback(async (runtimeOverride?: string) => {
    try {
      setModelsLoading(true);
      const catalog = await getUnifiedModelCatalog();
      const runtimes = catalog.runtimes ?? [];
      const availableRuntimes = buildTrainingRuntimeOptions(
        runtimes,
        getRuntimeDisplayName,
      );
      const runtimeCapabilitiesMap = buildTrainingRuntimeCapabilities(runtimes);
      setRuntimeOptions(availableRuntimes);
      setRuntimeCapabilities(runtimeCapabilitiesMap);
      const preferredRuntime = resolvePreferredTrainingRuntime(
        catalog,
        runtimeOverride,
        selectedRuntime,
      );
      if (preferredRuntime && preferredRuntime !== selectedRuntime) {
        setSelectedRuntime(preferredRuntime);
      }
      const trainable = filterTrainableModelsForRuntime(catalog, preferredRuntime);
      setTrainableModels(trainable);
      setSelectedBaseModel((current) =>
        resolveTrainingBaseModelSelection(current, trainable),
      );
    } catch (err) {
      console.error("Failed to load trainable models:", err);
      resetTrainingCatalogState(
        setTrainableModels,
        setRuntimeOptions,
        setRuntimeCapabilities,
        setSelectedRuntime,
        setSelectedBaseModel,
      );
    } finally {
      setModelsLoading(false);
    }
  }, [getRuntimeDisplayName, selectedRuntime]);

  useEffect(() => {
    loadJobs();
    loadTrainableModels();
  }, [loadJobs, loadTrainableModels]);

  useEffect(() => {
    // Auto-refresh co 10s tylko gdy są joby running
    if (!jobs.some((j) => j.status === "running")) {
      return;
    }
    const interval = setInterval(() => {
      loadJobs();
    }, 10000);
    return () => clearInterval(interval);
  }, [jobs, loadJobs]);

  async function handleStartTraining() {
    if (!selectedBaseModel) return;
    try {
      setLoading(true);
      const trimmedSigner = chatSigner.trim();
      const trimmedChatTargetModelId = chatTargetModelId.trim();
      const response = await startTraining({
        base_model: selectedBaseModel,
        runtime_id: selectedRuntime || null,
        onnx_conversion_mode: onnxConversionMode,
        auto_sign_for_chat: autoSignForChat,
        chat_signer: autoSignForChat
          ? (trimmedSigner || "academy-ui")
          : null,
        chat_target_model_id: autoSignForChat
          ? (trimmedChatTargetModelId || null)
          : null,
        lora_rank: loraRank,
        learning_rate: learningRate,
        num_epochs: numEpochs,
        batch_size: batchSize,
      });
      pushToast(response.message, "success");
      await loadJobs();
    } catch (err) {
      const resolved = resolveAcademyApiErrorMessage(err);
      pushToast(resolved || t("academy.common.unknownError"), "error");
      if (!(err instanceof ApiError && err.status === 400)) {
        console.error("Failed to start training:", err);
      }
    } finally {
      setLoading(false);
    }
  }

  const modelPickerOptions = buildTrainingModelPickerOptions(trainableModels, t);
  const baseModelPlaceholder = resolveTrainingBaseModelPlaceholder(
    modelsLoading,
    trainableModels.length,
    t,
  );
  const selectedRuntimeCapabilities = runtimeCapabilities[selectedRuntime] ?? {};
  const hasRuntimeCompatibleModels = trainableModels.length > 0;
  const isOnnxRuntimeSelected = normalizeRuntimeId(selectedRuntime) === "onnx";
  const selectedModel = trainableModels.find((model) => model.model_id === selectedBaseModel) ?? null;
  const selectedModelCompatibilityLabel = getSelectedModelCompatibilityLabel(
    selectedModel,
    getRuntimeDisplayName,
    t,
  );
  const selectedModelInstallStateLabel = getTrainingModelInstallStateLabel(
    selectedModel,
    t,
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-[color:var(--text-heading)]">{t("academy.training.title")}</h2>
          <p className="text-sm text-hint">
            {t("academy.training.subtitle")}
          </p>
        </div>
        <Button onClick={loadJobs} variant="outline" size="sm" className="gap-2">
          <RefreshCw className="h-4 w-4" />
          {t("academy.common.refresh")}
        </Button>
      </div>

      {/* Formularz parametrów */}
      <div className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-6">
        <h3 className="mb-4 text-sm font-medium text-[color:var(--text-secondary)]">{t("academy.training.paramsTitle")}</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <div className="sm:col-span-2 xl:col-span-5">
            <p className="text-sm font-medium text-[color:var(--text-secondary)]">
              {t("cockpit.models.server")}
            </p>
            <div className="mt-2">
              <SelectMenu
                value={selectedRuntime}
                options={runtimeOptions.map((runtime) => ({
                  value: runtime.id,
                  label: runtime.label,
                }))}
                onChange={(value) => {
                  setSelectedRuntime(value);
                  setSelectedBaseModel("");
                  loadTrainableModels(value);
                }}
                placeholder={t("cockpit.models.chooseServer")}
                ariaLabel={t("cockpit.actions.selectServer")}
                buttonTestId="academy-training-runtime-select"
                optionTestIdPrefix="academy-training-runtime-option"
                disabled={modelsLoading || runtimeOptions.length === 0}
                buttonClassName="mt-0 h-11 w-full justify-between rounded-md border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] px-3 py-2 text-sm text-[color:var(--text-primary)] ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--primary)] focus-visible:ring-offset-2"
                menuClassName="w-[min(980px,96vw)] max-h-[360px] overflow-y-auto rounded-md border border-[color:var(--ui-border-strong)] bg-[color:var(--bg-panel)] p-1 shadow-card backdrop-blur-md"
                optionClassName="rounded-md px-3 py-2 text-[color:var(--text-primary)] hover:bg-[color:var(--ui-surface-hover)]"
              />
            </div>
            {selectedRuntimeCapabilities.supports_native_training === false ? (
              <p className="mt-2 text-xs text-hint">
                {t("academy.training.externalTrainingHint", {
                  runtime: getRuntimeDisplayName(selectedRuntime || "runtime"),
                })}
              </p>
            ) : null}
            {!modelsLoading && selectedRuntime && !hasRuntimeCompatibleModels ? (
              <div className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                {t("academy.training.runtimeModelMismatchWarning", {
                  runtime: getRuntimeDisplayName(selectedRuntime),
                })}
              </div>
            ) : null}
          </div>
          <div className="sm:col-span-2 xl:col-span-5">
            <p className="text-sm font-medium text-[color:var(--text-secondary)]">
              {t("academy.training.baseModel")}
            </p>
            <div className="mt-2">
              <SelectMenu
                value={selectedBaseModel}
                options={modelPickerOptions}
                onChange={setSelectedBaseModel}
                placeholder={baseModelPlaceholder}
                ariaLabel={t("academy.training.baseModel")}
                buttonTestId="academy-training-base-model-select"
                optionTestIdPrefix="academy-training-base-model-option"
                disabled={modelsLoading || !hasRuntimeCompatibleModels}
                buttonClassName="mt-0 h-10 w-full justify-between rounded-md border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] px-3 py-2 text-left text-sm normal-case tracking-normal text-[color:var(--text-primary)] ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--primary)] focus-visible:ring-offset-2"
                menuClassName="w-[min(980px,96vw)] max-h-[360px] overflow-y-auto rounded-md border border-[color:var(--ui-border-strong)] bg-[color:var(--bg-panel)] p-1 shadow-card backdrop-blur-md"
                optionClassName="rounded-md px-3 py-2 text-[color:var(--text-primary)] hover:bg-[color:var(--ui-surface-hover)]"
                renderButton={(option) => {
                  const selectedOption = option as ModelPickerOption | null;
                  if (!selectedOption || selectedOption.kind !== "model" || !selectedOption.model) {
                    return (
                      <span className="min-w-0 flex-1 truncate text-left text-hint">
                        {baseModelPlaceholder}
                      </span>
                    );
                  }
                  return (
                    <div className="flex min-w-0 flex-1 items-center justify-between gap-2 text-left">
                      <span className="min-w-0 flex-1 truncate text-left text-sm text-[color:var(--text-primary)]">
                        {selectedOption.model.model_id}
                      </span>
                      <span className="shrink-0 text-[11px] text-[color:var(--ui-muted)]">
                        {getTrainingModelRuntimeBadgeLabel(
                          selectedOption.model,
                          selectedRuntime,
                          getRuntimeDisplayName,
                          t,
                        )}
                      </span>
                    </div>
                  );
                }}
                renderOption={(option, active) => {
                  const typedOption = option as ModelPickerOption;
                  if (typedOption.kind === "section") {
                    return (
                      <div className="w-full cursor-default border-b border-[color:var(--ui-border)] px-1 py-2 text-left">
                        <p className="text-xs font-semibold uppercase tracking-wide text-[color:var(--text-secondary)]">
                          {typedOption.label}
                        </p>
                        <p className="text-[11px] text-hint">
                          {typedOption.description}
                        </p>
                      </div>
                    );
                  }
                  const model = typedOption.model;
                  if (!model) {
                    return <span className="text-sm text-hint">{typedOption.label}</span>;
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
                          {getTrainingModelRuntimeBadgeLabel(
                            model,
                            selectedRuntime,
                            getRuntimeDisplayName,
                            t,
                          )}
                        </span>
                        <span className="text-[11px] text-hint/80">
                          {model.installed_local
                            ? t("academy.training.installState.localInstalled")
                            : t("academy.training.installState.catalogDownload")}
                        </span>
                      </div>
                    </div>
                  );
                }}
              />
            </div>
            {selectedModel ? (
              <div className="mt-2 rounded-md border border-[color:var(--ui-border-strong)] bg-[color:var(--bg-panel)] px-3 py-2 text-[11px] text-[color:var(--text-primary)]">
                <p className="truncate">
                  <span className="text-[color:var(--text-secondary)]">
                    {t("academy.training.engineLabel")}:
                  </span>{" "}
                  {t(`academy.training.engineNames.${resolveTrainingEngineKey(selectedModel.provider)}`)} •{" "}
                  <span className="text-[color:var(--text-secondary)]">
                    {t("academy.training.compatibilityLabel")}:
                  </span>{" "}
                  {selectedModelCompatibilityLabel} • {selectedModelInstallStateLabel}
                </p>
              </div>
            ) : null}
            {!modelsLoading && hasRuntimeCompatibleModels && !selectedBaseModel ? (
              <div className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                {t("academy.training.baseModelSelectionRequired")}
              </div>
            ) : null}
            <p className="mt-1 text-xs text-hint">{t("academy.training.baseModelHint")}</p>
            <p className="mt-1 text-xs text-hint/60">{t("academy.training.orderingHint")}</p>
          </div>
          <div>
            <Label htmlFor="lora-rank" className="text-[color:var(--text-secondary)]">
              LoRA Rank
            </Label>
            <Input
              id="lora-rank"
              type="number"
              value={loraRank}
              onChange={(e) => setLoraRank(Number.parseInt(e.target.value, 10) || 16)}
              min={4}
              max={64}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-hint">{t("academy.training.loraHint")}</p>
          </div>
          <div>
            <Label htmlFor="learning-rate" className="text-[color:var(--text-secondary)]">
              {t("academy.training.learningRate")}
            </Label>
            <Input
              id="learning-rate"
              type="number"
              step="0.0001"
              value={learningRate}
              onChange={(e) =>
                setLearningRate(Number.parseFloat(e.target.value) || 0.0002)
              }
              min={0.00001}
              max={0.01}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-hint">0.00001-0.01</p>
          </div>
          <div>
            <Label htmlFor="num-epochs" className="text-[color:var(--text-secondary)]">
              Epochs
            </Label>
            <Input
              id="num-epochs"
              type="number"
              value={numEpochs}
              onChange={(e) => setNumEpochs(Number.parseInt(e.target.value, 10) || 3)}
              min={1}
              max={20}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-hint">1-20</p>
          </div>
          <div>
            <Label htmlFor="batch-size" className="text-[color:var(--text-secondary)]">
              Batch Size
            </Label>
            <Input
              id="batch-size"
              type="number"
              value={batchSize}
              onChange={(e) => setBatchSize(Number.parseInt(e.target.value, 10) || 4)}
              min={1}
              max={32}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-hint">{t("academy.training.batchSizeHint")}</p>
          </div>
          <div>
            <Label htmlFor="onnx-conversion-mode" className="text-[color:var(--text-secondary)]">
              {t("academy.training.onnxConversionMode")}
            </Label>
            <SelectMenu
              value={onnxConversionMode}
              options={[
                {
                  value: "none",
                  label: t("academy.training.onnxConversionNone"),
                },
                {
                  value: "merge_export",
                  label: t("academy.training.onnxConversionMergeExport"),
                },
              ]}
              onChange={(value) => {
                setOnnxConversionMode(value === "merge_export" ? "merge_export" : "none");
              }}
              placeholder={t("academy.training.onnxConversionMode")}
              ariaLabel={t("academy.training.onnxConversionMode")}
              buttonTestId="academy-training-onnx-conversion-mode-select"
              optionTestIdPrefix="academy-training-onnx-conversion-mode-option"
              buttonClassName="mt-2 h-10 w-full justify-between rounded-md border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] px-3 py-2 text-sm text-[color:var(--text-primary)] ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--primary)] focus-visible:ring-offset-2"
              menuClassName="w-[min(980px,96vw)] max-h-[320px] overflow-y-auto rounded-md border border-[color:var(--ui-border-strong)] bg-[color:var(--bg-panel)] p-1 shadow-card backdrop-blur-md"
              optionClassName="rounded-md px-3 py-2 text-[color:var(--text-primary)] hover:bg-[color:var(--ui-surface-hover)]"
            />
            <p className="mt-1 text-xs text-hint">
              {isOnnxRuntimeSelected
                ? t("academy.training.onnxConversionHintOnnx")
                : t("academy.training.onnxConversionHint")}
            </p>
          </div>
          <div className="sm:col-span-2 xl:col-span-2">
            <div className="rounded-md border border-[color:var(--ui-border)] bg-[color:var(--bg-panel)] p-3">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="training-auto-sign-for-chat"
                  checked={autoSignForChat}
                  onCheckedChange={(value) => setAutoSignForChat(Boolean(value))}
                />
                <Label htmlFor="training-auto-sign-for-chat" className="text-[color:var(--text-secondary)]">
                  {t("academy.training.autoSignForChat")}
                </Label>
              </div>
              <p className="mt-1 text-xs text-hint">
                {t("academy.training.autoSignForChatHint")}
              </p>
              {autoSignForChat ? (
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <Label htmlFor="chat-signer" className="text-[color:var(--text-secondary)]">
                      {t("academy.training.chatSigner")}
                    </Label>
                    <Input
                      id="chat-signer"
                      value={chatSigner}
                      onChange={(event) => setChatSigner(event.target.value)}
                      className="mt-2"
                    />
                  </div>
                  <div>
                    <Label htmlFor="chat-target-model-id" className="text-[color:var(--text-secondary)]">
                      {t("academy.training.chatTargetModelId")}
                    </Label>
                    <Input
                      id="chat-target-model-id"
                      value={chatTargetModelId}
                      onChange={(event) => setChatTargetModelId(event.target.value)}
                      placeholder={t("academy.training.chatTargetModelIdPlaceholder")}
                      className="mt-2"
                    />
                  </div>
                </div>
              ) : null}
            </div>
          </div>
          <div className="sm:col-span-2 xl:col-span-1 xl:self-end">
            <Button
              onClick={handleStartTraining}
              disabled={loading || modelsLoading || !selectedBaseModel || !hasRuntimeCompatibleModels}
              className="w-full gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t("academy.training.starting")}
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  {t("academy.training.start")}
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* Lista jobów */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-[color:var(--text-secondary)]">
          {t("academy.training.history", { count: jobs.length })}
        </h3>
        <div className="space-y-2">
          {jobs.length === 0 ? (
            <div className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-8 text-center">
              <p className="text-sm text-hint">{t("academy.training.noJobs")}</p>
            </div>
          ) : (
            jobs.map((job) => (
              <div
                key={job.job_id}
                className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4"
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-[color:var(--text-primary)]">{job.job_id}</span>
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${getTrainingStatusColor(job.status)}`}>
                        {getTrainingStatusLabel(job.status, t)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-hint">
                      {t("academy.training.startedAt")}: {new Date(job.started_at).toLocaleString(language)}
                    </p>
                    {job.finished_at && (
                      <p className="text-xs text-hint">
                        {t("academy.training.finishedAt")}: {new Date(job.finished_at).toLocaleString(language)}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <p className="text-xs text-hint">{t("academy.training.epochs")}: {job.parameters.num_epochs}</p>
                      <p className="text-xs text-hint">{t("academy.training.lora")}: {job.parameters.lora_rank}</p>
                    </div>
                    <Button
                      onClick={() => setViewingLogs(job.job_id)}
                      variant="outline"
                      size="sm"
                      className="gap-2"
                    >
                      <Terminal className="h-4 w-4" />
                      {t("academy.training.logs")}
                    </Button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Log Viewer */}
      {viewingLogs && (
        <div className="mt-6">
          <LogViewer
            jobId={viewingLogs}
            onClose={() => setViewingLogs(null)}
          />
        </div>
      )}
    </div>
  );
}
