import { useTranslation } from "@/lib/i18n";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Node } from "@xyflow/react";
import {
  AlertTriangle,
  GitFork,
  Compass,
  Cpu,
  Server,
  Cloud,
  Database,
  Settings2,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { ConfigFieldsEditor } from "./ConfigFieldsEditor";
import type { OperatorConfigField } from "@/types/workflow-control";
import {
  getCompatibleEmbeddings,
  getCompatibleIntentModes,
  getCompatibleKernels,
  getCompatibleProviders,
} from "@/lib/workflow-control-options";

interface PropertyPanelProps {
  selectedNode: Node | null;
  onUpdateNode: (nodeId: string, data: unknown) => void;
  configFields?: OperatorConfigField[];
  availableOptions?: {
    strategies?: string[];
    intentModes?: string[];
    kernels?: string[];
    providers?: string[];
    models?: string[];
    providersBySource?: { local: string[]; cloud: string[] };
    modelsBySource?: { local: string[]; cloud: string[] };
    kernelRuntimes?: Record<string, string[]>;
    intentRequirements?: Record<string, { requires_embedding?: boolean; min_model_size?: string }>;
    providerEmbeddings?: Record<string, string[]>;
    embeddingProviders?: Record<string, string[]>;
  };
}

type RuntimeService = string | { name?: string; id?: string; [key: string]: unknown };
type WorkflowNodeType = "decision" | "intent" | "kernel" | "runtime" | "provider" | "embedding" | "config";
type SourceType = "local" | "cloud";
type SourceTypeLike = SourceType | "installed_local" | "installed-local";

type NodeVisualMeta = {
  icon: LucideIcon;
  iconColorClass: string;
  headerBgClass: string;
  accentClass: string;
};

const DEFAULT_OPTIONS: Required<NonNullable<PropertyPanelProps["availableOptions"]>> = {
  strategies: ["standard", "advanced", "heuristic"],
  intentModes: ["simple", "advanced", "expert"],
  kernels: ["default", "optimized", "legacy"],
  providers: ["openai", "google", "anthropic", "ollama"],
  models: ["gpt-4", "gemini-pro", "claude-3-opus", "llama3"],
  providersBySource: {
    local: ["huggingface", "ollama", "vllm"],
    cloud: ["openai", "google"],
  },
  modelsBySource: {
    local: ["sentence-transformers"],
    cloud: ["openai-embeddings", "google-embeddings"],
  },
  kernelRuntimes: {},
  intentRequirements: {},
  providerEmbeddings: {},
  embeddingProviders: {},
};

type ResolvedAvailableOptions = Required<NonNullable<PropertyPanelProps["availableOptions"]>>;

function resolveArrayOption(
  value: string[] | undefined,
  fallback: string[],
): string[] {
  return Array.isArray(value) ? value : fallback;
}

function resolveSourceOptions(
  value: { local: string[]; cloud: string[] } | undefined,
  fallback: { local: string[]; cloud: string[] },
): { local: string[]; cloud: string[] } {
  return {
    local: resolveArrayOption(value?.local, fallback.local),
    cloud: resolveArrayOption(value?.cloud, fallback.cloud),
  };
}

function resolveRecordOption<T extends Record<string, unknown>>(
  value: T | undefined,
  fallback: T,
): T {
  return value && typeof value === "object" ? value : fallback;
}

function resolveAvailableOptions(
  options?: PropertyPanelProps["availableOptions"]
) : ResolvedAvailableOptions {
  if (!options) return DEFAULT_OPTIONS;
  return {
    strategies: resolveArrayOption(options.strategies, DEFAULT_OPTIONS.strategies),
    intentModes: resolveArrayOption(options.intentModes, DEFAULT_OPTIONS.intentModes),
    kernels: resolveArrayOption(options.kernels, DEFAULT_OPTIONS.kernels),
    providers: resolveArrayOption(options.providers, DEFAULT_OPTIONS.providers),
    models: resolveArrayOption(options.models, DEFAULT_OPTIONS.models),
    providersBySource: resolveSourceOptions(
      options.providersBySource,
      DEFAULT_OPTIONS.providersBySource,
    ),
    modelsBySource: resolveSourceOptions(
      options.modelsBySource,
      DEFAULT_OPTIONS.modelsBySource,
    ),
    kernelRuntimes: resolveRecordOption(
      options.kernelRuntimes,
      DEFAULT_OPTIONS.kernelRuntimes,
    ) as ResolvedAvailableOptions["kernelRuntimes"],
    intentRequirements: resolveRecordOption(
      options.intentRequirements,
      DEFAULT_OPTIONS.intentRequirements,
    ) as ResolvedAvailableOptions["intentRequirements"],
    providerEmbeddings: resolveRecordOption(
      options.providerEmbeddings,
      DEFAULT_OPTIONS.providerEmbeddings,
    ) as ResolvedAvailableOptions["providerEmbeddings"],
    embeddingProviders: resolveRecordOption(
      options.embeddingProviders,
      DEFAULT_OPTIONS.embeddingProviders,
    ) as ResolvedAvailableOptions["embeddingProviders"],
  };
}

const NODE_VISUALS: Record<WorkflowNodeType, NodeVisualMeta> = {
  decision: {
    icon: GitFork,
    iconColorClass: "text-cyan-300",
    headerBgClass: "bg-cyan-500/10 border-cyan-400/30",
    accentClass: "text-cyan-300",
  },
  intent: {
    icon: Compass,
    iconColorClass: "text-amber-300",
    headerBgClass: "bg-amber-500/10 border-amber-400/30",
    accentClass: "text-amber-300",
  },
  kernel: {
    icon: Cpu,
    iconColorClass: "text-emerald-300",
    headerBgClass: "bg-emerald-500/10 border-emerald-400/30",
    accentClass: "text-emerald-300",
  },
  runtime: {
    icon: Server,
    iconColorClass: "text-violet-300",
    headerBgClass: "bg-violet-500/10 border-violet-400/30",
    accentClass: "text-violet-300",
  },
  provider: {
    icon: Cloud,
    iconColorClass: "text-orange-300",
    headerBgClass: "bg-orange-500/10 border-orange-400/30",
    accentClass: "text-orange-300",
  },
  embedding: {
    icon: Database,
    iconColorClass: "text-fuchsia-300",
    headerBgClass: "bg-fuchsia-500/10 border-fuchsia-400/30",
    accentClass: "text-fuchsia-300",
  },
  config: {
    icon: Settings2,
    iconColorClass: "text-sky-300",
    headerBgClass: "bg-sky-500/10 border-sky-400/30",
    accentClass: "text-sky-300",
  },
};

const SECTION_STYLES: Record<WorkflowNodeType, string> = {
  decision: "border-cyan-400/20 bg-slate-900/80",
  intent: "border-amber-400/20 bg-slate-900/80",
  kernel: "border-emerald-400/20 bg-slate-900/80",
  runtime: "border-violet-400/20 bg-slate-900/80",
  provider: "border-orange-400/20 bg-slate-900/80",
  embedding: "border-fuchsia-400/20 bg-slate-900/80",
  config: "border-sky-400/20 bg-slate-900/80",
};

const SECTION_ICON_STYLES: Record<WorkflowNodeType, string> = {
  decision: "bg-cyan-500/10 text-cyan-300 border border-cyan-400/20",
  intent: "bg-amber-500/10 text-amber-300 border border-amber-400/20",
  kernel: "bg-emerald-500/10 text-emerald-300 border border-emerald-400/20",
  runtime: "bg-violet-500/10 text-violet-300 border border-violet-400/20",
  provider: "bg-orange-500/10 text-orange-300 border border-orange-400/20",
  embedding: "bg-fuchsia-500/10 text-fuchsia-300 border border-fuchsia-400/20",
  config: "bg-sky-500/10 text-sky-300 border border-sky-400/20",
};

const SECTION_TEXT_STYLES: Record<WorkflowNodeType, string> = {
  decision: "text-cyan-300",
  intent: "text-amber-300",
  kernel: "text-emerald-300",
  runtime: "text-violet-300",
  provider: "text-orange-300",
  embedding: "text-fuchsia-300",
  config: "text-sky-300",
};

const SELECT_TRIGGER_BASE =
  "bg-slate-950/70 border-white/10 text-slate-100 focus:ring-cyan-500/30";
const SELECT_CONTENT_BASE = "bg-slate-950 border-white/10 text-slate-100";

function formatRuntimeService(service: RuntimeService): string {
  if (typeof service === "string") return service;
  if (service.name) return service.name;
  if (service.id) return service.id;
  return JSON.stringify(service);
}

function translateOption(
  t: (path: string) => string,
  key: string,
  fallback: string
): string {
  const translated = t(key);
  return translated === key ? fallback : translated;
}

function asRecord(value: unknown): Record<string, unknown> {
  return (value as Record<string, unknown>) ?? {};
}

function isWorkflowNodeType(value: string | undefined): value is WorkflowNodeType {
  return value === "decision" || value === "intent" || value === "kernel" || value === "runtime" || value === "provider" || value === "embedding" || value === "config";
}

function normalizeSourceType(value: SourceTypeLike | undefined): SourceType {
  if (!value) return "local";
  const normalized = value.trim().toLowerCase();
  if (normalized === "cloud") return "cloud";
  if (
    normalized === "local" ||
    normalized === "installed_local" ||
    normalized === "installed-local"
  ) {
    return "local";
  }
  return "local";
}

function withCurrentOption(options: string[], current: unknown): string[] {
  if (typeof current !== "string") return options;
  const normalizedCurrent = current.trim();
  if (!normalizedCurrent || options.includes(normalizedCurrent)) return options;
  return [normalizedCurrent, ...options];
}

function SectionCard({
  type,
  icon: Icon,
  title,
  description,
  children,
}: Readonly<{
  type: WorkflowNodeType;
  icon: LucideIcon;
  title: string;
  description: string;
  children: ReactNode;
}>) {
  return (
    <div className={`rounded-[24px] border p-4 shadow-[0_12px_40px_rgba(2,6,23,0.28)] ${SECTION_STYLES[type]}`}>
      <div className="mb-4 flex items-center gap-3 border-b border-white/10 pb-3">
        <div className={`p-2 rounded-lg ${SECTION_ICON_STYLES[type]}`}>
          <Icon className="w-4 h-4" />
        </div>
        <div>
          <h3 className={`text-[11px] font-semibold uppercase tracking-[0.24em] ${SECTION_TEXT_STYLES[type]}`}>{title}</h3>
          <p className="mt-1 text-[11px] text-slate-500">{description}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

function GuardNotice({
  tone = "warning",
  text,
}: Readonly<{
  tone?: "warning" | "neutral";
  text: string;
}>) {
  return (
    <div
      className={[
        "mt-3 flex items-start gap-2 rounded-2xl border px-3 py-2 text-xs",
        tone === "warning"
          ? "border-amber-400/20 bg-amber-500/10 text-amber-100"
          : "border-white/10 bg-slate-950/60 text-slate-400",
      ].join(" ")}
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>{text}</span>
    </div>
  );
}

function OptionRail({
  label,
  value,
  options,
  onChange,
  renderOption,
  toneClass,
}: Readonly<{
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  renderOption?: (option: string) => string;
  toneClass: string;
}>) {
  if (options.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
        {label}
      </div>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const isActive = option === value;
          return (
            <button
              key={option}
              type="button"
              onClick={() => onChange(option)}
              className={[
                "rounded-full border px-3 py-1.5 text-xs transition",
                isActive
                  ? `${toneClass} border-current shadow-[0_0_20px_rgba(15,23,42,0.18)]`
                  : "border-white/10 bg-slate-950/70 text-slate-400 hover:border-white/20 hover:text-slate-200",
              ].join(" ")}
            >
              {renderOption ? renderOption(option) : option}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function DecisionEditor({
  data,
  options,
  onUpdate,
  t,
}: Readonly<{
  data: Record<string, unknown>;
  options: Required<NonNullable<PropertyPanelProps["availableOptions"]>>;
  onUpdate: (key: string, value: unknown) => void;
  t: (path: string) => string;
}>) {
  const strategyOptions = withCurrentOption(
    options.strategies,
    data.strategy as string | undefined
  );
  return (
    <SectionCard
      type="decision"
      icon={GitFork}
      title={t("workflowControl.sections.decision")}
      description={t("workflowControl.descriptions.decision")}
    >
      <OptionRail
        label={t("workflowControl.labels.stepAlternatives")}
        value={(data.strategy as string) ?? ""}
        options={strategyOptions}
        onChange={(val) => onUpdate("strategy", val)}
        renderOption={(opt) => translateOption(t, `workflowControl.strategies.${opt}`, opt)}
        toneClass="bg-cyan-500/10 text-cyan-200"
      />
      <Label htmlFor="strategy" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.stepConfiguration")}
      </Label>
      <Select value={(data.strategy as string) ?? ""} onValueChange={(val) => onUpdate("strategy", val)}>
        <SelectTrigger id="strategy" className={SELECT_TRIGGER_BASE}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent className={SELECT_CONTENT_BASE}>
          {strategyOptions.map((opt) => (
            <SelectItem key={opt} value={opt} className="focus:bg-cyan-500/15 focus:text-slate-100">
              {translateOption(t, `workflowControl.strategies.${opt}`, opt)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </SectionCard>
  );
}

function IntentEditor({
  data,
  options,
  onUpdate,
  t,
}: Readonly<{
  data: Record<string, unknown>;
  options: Required<NonNullable<PropertyPanelProps["availableOptions"]>>;
  onUpdate: (key: string, value: unknown) => void;
  t: (path: string) => string;
}>) {
  const hasEmbedding =
    typeof data.embeddingModel === "string" && data.embeddingModel.trim().length > 0;
  const intentModeOptions = withCurrentOption(
    getCompatibleIntentModes(options, hasEmbedding),
    data.intentMode as string | undefined
  );
  const currentIntentMode = data.intentMode as string | undefined;
  const requiresEmbedding = Boolean(
    currentIntentMode && options.intentRequirements[currentIntentMode]?.requires_embedding,
  );
  return (
    <SectionCard
      type="intent"
      icon={Compass}
      title={t("workflowControl.sections.intent")}
      description={t("workflowControl.descriptions.intent")}
    >
      <OptionRail
        label={t("workflowControl.labels.stepAlternatives")}
        value={(data.intentMode as string) ?? ""}
        options={intentModeOptions}
        onChange={(val) => onUpdate("intentMode", val)}
        renderOption={(opt) => translateOption(t, `workflowControl.intentModes.${opt}`, opt)}
        toneClass="bg-amber-500/10 text-amber-200"
      />
      <Label htmlFor="intentMode" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.stepConfiguration")}
      </Label>
      <Select value={(data.intentMode as string) ?? ""} onValueChange={(val) => onUpdate("intentMode", val)}>
        <SelectTrigger id="intentMode" className={SELECT_TRIGGER_BASE}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent className={SELECT_CONTENT_BASE}>
          {intentModeOptions.map((opt) => (
            <SelectItem key={opt} value={opt} className="focus:bg-amber-500/15">
              {translateOption(t, `workflowControl.intentModes.${opt}`, opt)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {requiresEmbedding && !hasEmbedding ? (
        <GuardNotice text={t("workflowControl.messages.intentCompatibilityHint")} />
      ) : null}
    </SectionCard>
  );
}

function KernelEditor({
  data,
  options,
  onUpdate,
  t,
}: Readonly<{
  data: Record<string, unknown>;
  options: Required<NonNullable<PropertyPanelProps["availableOptions"]>>;
  onUpdate: (key: string, value: unknown) => void;
  t: (path: string) => string;
}>) {
  const workflowRuntime =
    typeof data.workflowRuntime === "string" ? data.workflowRuntime : "";
  const compatibleKernels = getCompatibleKernels(options, workflowRuntime);
  const kernelOptions = withCurrentOption(
    compatibleKernels,
    data.kernel as string | undefined,
  );
  const hadCompatibilityFilter =
    Boolean(workflowRuntime) && compatibleKernels.length < options.kernels.length;
  return (
    <SectionCard
      type="kernel"
      icon={Cpu}
      title={t("workflowControl.sections.kernel")}
      description={t("workflowControl.descriptions.kernel")}
    >
      <OptionRail
        label={t("workflowControl.labels.stepAlternatives")}
        value={(data.kernel as string) ?? ""}
        options={kernelOptions}
        onChange={(val) => onUpdate("kernel", val)}
        renderOption={(opt) => translateOption(t, `workflowControl.kernelTypes.${opt}`, opt)}
        toneClass="bg-emerald-500/10 text-emerald-200"
      />
      <Label htmlFor="kernel" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.stepConfiguration")}
      </Label>
      <Select value={(data.kernel as string) ?? ""} onValueChange={(val) => onUpdate("kernel", val)}>
        <SelectTrigger id="kernel" className={SELECT_TRIGGER_BASE}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent className={SELECT_CONTENT_BASE}>
          {kernelOptions.map((opt) => (
            <SelectItem key={opt} value={opt} className="focus:bg-emerald-500/15">
              {translateOption(t, `workflowControl.kernelTypes.${opt}`, opt)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {hadCompatibilityFilter ? (
        <GuardNotice
          text={t("workflowControl.messages.kernelCompatibilityHint").replace(
            "{{value}}",
            workflowRuntime,
          )}
        />
      ) : null}
    </SectionCard>
  );
}

function RuntimeEditor({ data, t }: Readonly<{ data: Record<string, unknown>; t: (path: string) => string }>) {
  const runtime = (data.runtime as { services?: RuntimeService[] } | undefined) ?? {};
  const services = runtime.services ?? [];

  return (
    <SectionCard
      type="runtime"
      icon={Server}
      title={t("workflowControl.sections.runtime")}
      description={t("workflowControl.descriptions.runtime")}
    >
      <Label htmlFor="runtime-services" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3.5 block px-0.5">
        {t("workflowControl.labels.runtimeServices")}
      </Label>
      <div id="runtime-services" className="flex flex-wrap gap-2">
        {services.length > 0 ? (
          services.map((svc: RuntimeService, index: number) => (
            <span key={`${formatRuntimeService(svc)}-${index}`} className="rounded-full border border-white/10 bg-slate-950/70 px-2.5 py-1 text-xs font-mono text-slate-300">
              {formatRuntimeService(svc)}
            </span>
          ))
        ) : (
          <span className="text-xs text-muted-foreground">{t("workflowControl.common.auto")}</span>
        )}
      </div>
    </SectionCard>
  );
}

function ProviderEditor({
  data,
  options,
  onUpdate,
  t,
}: Readonly<{
  data: Record<string, unknown>;
  options: Required<NonNullable<PropertyPanelProps["availableOptions"]>>;
  onUpdate: (key: string, value: unknown) => void;
  t: (path: string) => string;
}>) {
  const provider = (data.provider as { active?: string; sourceType?: SourceTypeLike } | undefined) ?? {};
  const activeEmbeddingModel =
    typeof data.embeddingModel === "string" ? data.embeddingModel : "";
  const providerBySource = options.providersBySource ?? DEFAULT_OPTIONS.providersBySource;
  const nodeSourceType = data.sourceType as SourceTypeLike | undefined;
  const nodeSourceTag = data.sourceTag as SourceTypeLike | undefined;
  const inferSource = (value: string | undefined): SourceType => {
    if (value && providerBySource.cloud.includes(value)) return "cloud";
    return "local";
  };
  let sourceType: SourceType;
  if (provider.sourceType) {
    sourceType = normalizeSourceType(provider.sourceType);
  } else if (nodeSourceType) {
    sourceType = normalizeSourceType(nodeSourceType);
  } else if (nodeSourceTag) {
    sourceType = normalizeSourceType(nodeSourceTag);
  } else {
    sourceType = inferSource(provider.active);
  }
  const compatibleProviders = getCompatibleProviders(
    options,
    sourceType,
    activeEmbeddingModel,
  );
  const sourceProviders = withCurrentOption(compatibleProviders, provider.active);
  const safeActive = provider.active ?? "";
  const hadCompatibilityFilter =
    Boolean(activeEmbeddingModel) &&
    compatibleProviders.length < (providerBySource[sourceType] ?? []).length;

  return (
    <SectionCard
      type="provider"
      icon={Cloud}
      title={t("workflowControl.sections.provider")}
      description={t("workflowControl.descriptions.provider")}
    >
      <OptionRail
        label={t("workflowControl.labels.stepAlternatives")}
        value={sourceType}
        options={["local", "cloud"]}
        onChange={(val) => {
          const nextSource = normalizeSourceType(val as SourceTypeLike);
          const nextProviders = providerBySource[nextSource];
          const nextActive = provider.active && nextProviders.includes(provider.active) ? provider.active : "";
          onUpdate("provider", { active: nextActive, sourceType: nextSource });
        }}
        renderOption={(opt) =>
          opt === "local"
            ? t("workflowControl.labels.installedLocal")
            : t("workflowControl.labels.cloud")
        }
        toneClass="bg-orange-500/10 text-orange-200"
      />
      <Label htmlFor="provider" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.stepConfiguration")}
      </Label>
      <Select
        value={sourceType}
        onValueChange={(val) => {
          const nextSource = normalizeSourceType(val as SourceTypeLike);
          const nextProviders = providerBySource[nextSource];
          const nextActive = provider.active && nextProviders.includes(provider.active) ? provider.active : "";
          onUpdate("provider", { active: nextActive, sourceType: nextSource });
        }}
      >
        <SelectTrigger id="provider-source" className={`${SELECT_TRIGGER_BASE} mb-2.5`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent className={SELECT_CONTENT_BASE}>
          <SelectItem value="local" className="focus:bg-orange-500/15">
            {t("workflowControl.labels.installedLocal")}
          </SelectItem>
          <SelectItem value="cloud" className="focus:bg-orange-500/15">
            {t("workflowControl.labels.cloud")}
          </SelectItem>
        </SelectContent>
      </Select>
      <OptionRail
        label={t("workflowControl.labels.availableVariants")}
        value={safeActive}
        options={sourceProviders}
        onChange={(val) => onUpdate("provider", { active: val, sourceType })}
        renderOption={(opt) => translateOption(t, `workflowControl.providers.${opt}`, opt)}
        toneClass="bg-orange-500/10 text-orange-200"
      />
      <Label htmlFor="provider" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.activeProvider")}
      </Label>
      <Select value={safeActive} onValueChange={(val) => onUpdate("provider", { active: val, sourceType })}>
        <SelectTrigger id="provider" className={SELECT_TRIGGER_BASE}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent className={SELECT_CONTENT_BASE}>
          {sourceProviders.map((opt) => (
            <SelectItem key={opt} value={opt} className="focus:bg-orange-500/15">
              {translateOption(t, `workflowControl.providers.${opt}`, opt)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {hadCompatibilityFilter ? (
        <GuardNotice
          text={t("workflowControl.messages.providerCompatibilityHint").replace(
            "{{value}}",
            activeEmbeddingModel,
          )}
        />
      ) : null}
    </SectionCard>
  );
}

function EmbeddingEditor({
  data,
  options,
  onUpdate,
  t,
}: Readonly<{
  data: Record<string, unknown>;
  options: Required<NonNullable<PropertyPanelProps["availableOptions"]>>;
  onUpdate: (key: string, value: unknown) => void;
  t: (path: string) => string;
}>) {
  const modelsBySource = options.modelsBySource ?? DEFAULT_OPTIONS.modelsBySource;
  const activeProvider =
    typeof data.providerActive === "string" ? data.providerActive : "";
  const nodeSourceTag = data.sourceTag as SourceTypeLike | undefined;
  const inferSource = (value: string | undefined): SourceType => {
    if (value && modelsBySource.cloud.includes(value)) return "cloud";
    return "local";
  };
  const dataSourceType = data.sourceType as SourceTypeLike | undefined;
  let sourceType: SourceType;
  if (dataSourceType) {
    sourceType = normalizeSourceType(dataSourceType);
  } else if (nodeSourceTag) {
    sourceType = normalizeSourceType(nodeSourceTag);
  } else {
    sourceType = inferSource(data.model as string | undefined);
  }
  const compatibleEmbeddings = getCompatibleEmbeddings(
    options,
    sourceType,
    activeProvider,
  );
  const sourceModels = withCurrentOption(
    compatibleEmbeddings,
    data.model as string | undefined,
  );
  const safeModel = (data.model as string | undefined) ?? "";
  const hadCompatibilityFilter =
    Boolean(activeProvider) &&
    compatibleEmbeddings.length < (modelsBySource[sourceType] ?? []).length;

  return (
    <SectionCard
      type="embedding"
      icon={Database}
      title={t("workflowControl.sections.embedding")}
      description={t("workflowControl.descriptions.embedding")}
    >
      <OptionRail
        label={t("workflowControl.labels.stepAlternatives")}
        value={sourceType}
        options={["local", "cloud"]}
        onChange={(val) => {
          const nextSource = normalizeSourceType(val as SourceTypeLike);
          const nextModels = modelsBySource[nextSource];
          const currentModel = data.model as string | undefined;
          let nextModel = "";
          if (currentModel && nextModels.includes(currentModel)) {
            nextModel = currentModel;
          }
          onUpdate("sourceType", nextSource);
          onUpdate("model", nextModel);
        }}
        renderOption={(opt) =>
          opt === "local"
            ? t("workflowControl.labels.installedLocal")
            : t("workflowControl.labels.cloud")
        }
        toneClass="bg-fuchsia-500/10 text-fuchsia-200"
      />
      <Label htmlFor="model" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.stepConfiguration")}
      </Label>
      <Select
        value={sourceType}
        onValueChange={(val) => {
          const nextSource = normalizeSourceType(val as SourceTypeLike);
          const nextModels = modelsBySource[nextSource];
          const currentModel = data.model as string | undefined;
          let nextModel = "";
          if (currentModel && nextModels.includes(currentModel)) {
            nextModel = currentModel;
          }
          onUpdate("sourceType", nextSource);
          onUpdate("model", nextModel);
        }}
      >
        <SelectTrigger id="embedding-source" className={`${SELECT_TRIGGER_BASE} mb-2.5`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent className={SELECT_CONTENT_BASE}>
          <SelectItem value="local" className="focus:bg-fuchsia-500/15">
            {t("workflowControl.labels.installedLocal")}
          </SelectItem>
          <SelectItem value="cloud" className="focus:bg-fuchsia-500/15">
            {t("workflowControl.labels.cloud")}
          </SelectItem>
        </SelectContent>
      </Select>
      <OptionRail
        label={t("workflowControl.labels.availableVariants")}
        value={safeModel}
        options={sourceModels}
        onChange={(val) => onUpdate("model", val)}
        renderOption={(opt) => translateOption(t, `workflowControl.embeddingModels.${opt}`, opt)}
        toneClass="bg-fuchsia-500/10 text-fuchsia-200"
      />
      <Label htmlFor="model" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.currentEmbedding")}
      </Label>
      <Select value={safeModel} onValueChange={(val) => onUpdate("model", val)}>
        <SelectTrigger id="model" className={SELECT_TRIGGER_BASE}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent className={SELECT_CONTENT_BASE}>
          {sourceModels.map((opt) => (
            <SelectItem key={opt} value={opt} className="focus:bg-fuchsia-500/15">
              {translateOption(t, `workflowControl.embeddingModels.${opt}`, opt)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {hadCompatibilityFilter ? (
        <GuardNotice
          text={t("workflowControl.messages.embeddingCompatibilityHint").replace(
            "{{value}}",
            activeProvider,
          )}
        />
      ) : null}
    </SectionCard>
  );
}

export function PropertyPanel({
  selectedNode,
  onUpdateNode,
  configFields,
  availableOptions,
}: Readonly<PropertyPanelProps>) {
  const t = useTranslation();
  const resolvedOptions = resolveAvailableOptions(availableOptions);

  if (!selectedNode) {
    return (
      <div className="rounded-[28px] border border-white/10 bg-slate-950/90 p-6 text-center text-sm text-slate-400 shadow-[0_18px_60px_rgba(2,6,23,0.45)]">
        {t("workflowControl.messages.selectNode")}
      </div>
    );
  }

  const nodeType = selectedNode.type;
  const data = asRecord(selectedNode.data);
  const handleUpdate = (key: string, value: unknown) => {
    onUpdateNode(selectedNode.id, {
      ...data,
      [key]: value,
    });
  };

  const visual = isWorkflowNodeType(nodeType) ? NODE_VISUALS[nodeType] : NODE_VISUALS.intent;
  const IconComponent = visual.icon;

  const editor = (() => {
    if (!isWorkflowNodeType(nodeType)) return null;
    if (nodeType === "decision") {
      return <DecisionEditor data={data} options={resolvedOptions} onUpdate={handleUpdate} t={t} />;
    }
    if (nodeType === "intent") {
      return <IntentEditor data={data} options={resolvedOptions} onUpdate={handleUpdate} t={t} />;
    }
    if (nodeType === "kernel") {
      return <KernelEditor data={data} options={resolvedOptions} onUpdate={handleUpdate} t={t} />;
    }
    if (nodeType === "runtime") {
      return <RuntimeEditor data={data} t={t} />;
    }
    if (nodeType === "config") {
      const nodeConfigFields =
        Array.isArray((data as { configFields?: unknown[] }).configFields)
          ? ((data as { configFields?: OperatorConfigField[] }).configFields ?? [])
          : configFields ?? [];
      return (
        <ConfigFieldsEditor
          configFields={nodeConfigFields}
          onUpdateField={(field, value) => {
            const nextConfigFields = nodeConfigFields.map((item) =>
              item.key === field.key ? { ...item, value } : item
            );
            handleUpdate("configFields", nextConfigFields);
          }}
        />
      );
    }
    if (nodeType === "provider") {
      return <ProviderEditor data={data} options={resolvedOptions} onUpdate={handleUpdate} t={t} />;
    }
    return <EmbeddingEditor data={data} options={resolvedOptions} onUpdate={handleUpdate} t={t} />;
  })();

  return (
    <div className="rounded-[28px] border border-white/10 bg-slate-950/90 p-5 shadow-[0_18px_60px_rgba(2,6,23,0.45)]">
      <div className="px-1 py-1">
        <h2 className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-400">
          <Settings2 className="w-3.5 h-3.5" />
          {t("workflowControl.panels.propertyInspector")}
        </h2>
        <div className="mb-6 h-px w-full bg-white/10" />

        <div className="mb-5 flex items-center gap-4 px-1">
          <div className={`flex h-12 w-12 items-center justify-center rounded-2xl border ${visual.headerBgClass} ${visual.iconColorClass}`}>
            <IconComponent className="w-6 h-6" />
          </div>
          <div>
            <div className="mb-0.5 text-[10px] font-mono tracking-tight text-slate-500">{selectedNode.id}</div>
            <div className={`text-sm font-semibold uppercase tracking-[0.22em] ${visual.accentClass}`}>
              {nodeType} {t("workflowControl.labels.node")}
            </div>
          </div>
        </div>

        <div className="mb-4 rounded-2xl border border-white/10 bg-slate-950/50 px-4 py-3 text-xs text-slate-400">
          {t("workflowControl.messages.stepComposerHint")}
        </div>

        <div className="space-y-3">
          {editor}
          {!editor && (
            <div className="rounded-[24px] border border-white/10 bg-slate-900/80 p-4">
              <Label htmlFor="raw-data" className="text-slate-400 mb-2 block">
                {t("workflowControl.labels.rawData")}
              </Label>
              <pre id="raw-data" className="max-h-60 overflow-auto rounded-2xl border border-white/10 bg-slate-950/80 p-3 text-xs font-mono text-slate-300">
                {JSON.stringify(data, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
