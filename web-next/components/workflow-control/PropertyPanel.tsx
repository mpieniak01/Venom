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

interface PropertyPanelProps {
  selectedNode: Node | null;
  onUpdateNode: (nodeId: string, data: unknown) => void;
  availableOptions?: {
    strategies?: string[];
    kernels?: string[];
    providers?: string[];
    models?: string[];
  };
}

type RuntimeService = string | { name?: string; id?: string; [key: string]: unknown };
type WorkflowNodeType = "decision" | "intent" | "kernel" | "runtime" | "provider" | "embedding";

type NodeVisualMeta = {
  icon: LucideIcon;
  iconColorClass: string;
  headerBgClass: string;
};

const DEFAULT_OPTIONS: Required<NonNullable<PropertyPanelProps["availableOptions"]>> = {
  strategies: ["standard", "advanced", "heuristic"],
  kernels: ["default", "optimized", "legacy"],
  providers: ["openai", "google", "anthropic", "ollama"],
  models: ["gpt-4", "gemini-pro", "claude-3-opus", "llama3"],
};

const NODE_VISUALS: Record<WorkflowNodeType, NodeVisualMeta> = {
  decision: {
    icon: GitFork,
    iconColorClass: "text-blue-400",
    headerBgClass: "bg-blue-500/20 border-blue-500 shadow-blue-500/20",
  },
  intent: {
    icon: Compass,
    iconColorClass: "text-yellow-400",
    headerBgClass: "bg-yellow-500/20 border-yellow-500 shadow-yellow-500/20",
  },
  kernel: {
    icon: Cpu,
    iconColorClass: "text-green-400",
    headerBgClass: "bg-green-500/20 border-green-500 shadow-green-500/20",
  },
  runtime: {
    icon: Server,
    iconColorClass: "text-purple-400",
    headerBgClass: "bg-purple-500/20 border-purple-500 shadow-purple-500/20",
  },
  provider: {
    icon: Cloud,
    iconColorClass: "text-orange-400",
    headerBgClass: "bg-orange-500/20 border-orange-500 shadow-orange-500/20",
  },
  embedding: {
    icon: Database,
    iconColorClass: "text-pink-400",
    headerBgClass: "bg-pink-500/20 border-pink-500 shadow-pink-500/20",
  },
};

const SECTION_STYLES: Record<WorkflowNodeType, string> = {
  decision: "border-cyan-500/20 bg-cyan-500/5 shadow-[0_4px_25px_rgba(6,182,212,0.05)]",
  intent: "border-yellow-500/20 bg-yellow-500/5 shadow-[0_4px_25px_rgba(234,179,8,0.05)]",
  kernel: "border-green-500/20 bg-green-500/5 shadow-[0_4px_25px_rgba(34,197,94,0.05)]",
  runtime: "border-purple-500/20 bg-purple-500/5 shadow-[0_4px_25px_rgba(168,85,247,0.05)]",
  provider: "border-orange-500/20 bg-orange-500/5 shadow-[0_4px_25px_rgba(249,115,22,0.05)]",
  embedding: "border-pink-500/20 bg-pink-500/5 shadow-[0_4px_25px_rgba(236,72,153,0.05)]",
};

const SECTION_ICON_STYLES: Record<WorkflowNodeType, string> = {
  decision: "bg-cyan-500/10 text-cyan-400",
  intent: "bg-yellow-500/10 text-yellow-400",
  kernel: "bg-green-500/10 text-green-400",
  runtime: "bg-purple-500/10 text-purple-400",
  provider: "bg-orange-500/10 text-orange-400",
  embedding: "bg-pink-500/10 text-pink-400",
};

const SECTION_TEXT_STYLES: Record<WorkflowNodeType, string> = {
  decision: "text-cyan-400",
  intent: "text-yellow-400",
  kernel: "text-green-400",
  runtime: "text-purple-400",
  provider: "text-orange-400",
  embedding: "text-pink-400",
};

function formatRuntimeService(service: RuntimeService): string {
  if (typeof service === "string") return service;
  if (service.name) return service.name;
  if (service.id) return service.id;
  return JSON.stringify(service);
}

function asRecord(value: unknown): Record<string, unknown> {
  return (value as Record<string, unknown>) ?? {};
}

function isWorkflowNodeType(value: string | undefined): value is WorkflowNodeType {
  return value === "decision" || value === "intent" || value === "kernel" || value === "runtime" || value === "provider" || value === "embedding";
}

function SectionCard({
  type,
  icon: Icon,
  title,
  description,
  children,
}: {
  type: WorkflowNodeType;
  icon: LucideIcon;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className={`p-4 rounded-2xl border ${SECTION_STYLES[type]}`}>
      <div className="flex items-center gap-3 mb-3 border-b border-white/10 pb-2">
        <div className={`p-2 rounded-lg ${SECTION_ICON_STYLES[type]}`}>
          <Icon className="w-4 h-4" />
        </div>
        <div>
          <h3 className={`text-[10px] font-bold uppercase tracking-widest ${SECTION_TEXT_STYLES[type]}`}>{title}</h3>
          <p className={`text-[9px] uppercase tracking-tight mt-0.5 ${SECTION_TEXT_STYLES[type]}/50`}>{description}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

function DecisionEditor({
  data,
  options,
  onUpdate,
  t,
}: {
  data: Record<string, unknown>;
  options: Required<NonNullable<PropertyPanelProps["availableOptions"]>>;
  onUpdate: (key: string, value: unknown) => void;
  t: (path: string) => string;
}) {
  return (
    <SectionCard
      type="decision"
      icon={GitFork}
      title={t("workflowControl.sections.decision")}
      description={t("workflowControl.descriptions.decision")}
    >
      <Label htmlFor="strategy" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.strategy")}
      </Label>
      <Select value={(data.strategy as string) ?? ""} onValueChange={(val) => onUpdate("strategy", val)}>
        <SelectTrigger id="strategy" className="bg-slate-900/80 border-cyan-500/30 text-cyan-100 focus:ring-cyan-500/50">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="bg-slate-900 border-cyan-500/30 text-cyan-100">
          {options.strategies.map((opt) => (
            <SelectItem key={opt} value={opt} className="focus:bg-cyan-500/20 focus:text-cyan-100">
              {t(`workflowControl.strategies.${opt}`) || opt}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </SectionCard>
  );
}

function IntentEditor({
  data,
  onUpdate,
  t,
}: {
  data: Record<string, unknown>;
  onUpdate: (key: string, value: unknown) => void;
  t: (path: string) => string;
}) {
  return (
    <SectionCard
      type="intent"
      icon={Compass}
      title={t("workflowControl.sections.intent")}
      description={t("workflowControl.descriptions.intent")}
    >
      <Label htmlFor="intentMode" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.intentMode")}
      </Label>
      <Select value={(data.intentMode as string) ?? ""} onValueChange={(val) => onUpdate("intentMode", val)}>
        <SelectTrigger id="intentMode" className="bg-slate-900/80 border-yellow-500/30 text-yellow-100 focus:ring-yellow-500/50">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="bg-slate-900 border-yellow-500/30 text-yellow-100">
          <SelectItem value="strict" className="focus:bg-yellow-500/20">{t("workflowControl.intentModes.strict")}</SelectItem>
          <SelectItem value="flexible" className="focus:bg-yellow-500/20">{t("workflowControl.intentModes.flexible")}</SelectItem>
        </SelectContent>
      </Select>
    </SectionCard>
  );
}

function KernelEditor({
  data,
  options,
  onUpdate,
  t,
}: {
  data: Record<string, unknown>;
  options: Required<NonNullable<PropertyPanelProps["availableOptions"]>>;
  onUpdate: (key: string, value: unknown) => void;
  t: (path: string) => string;
}) {
  return (
    <SectionCard
      type="kernel"
      icon={Cpu}
      title={t("workflowControl.sections.kernel")}
      description={t("workflowControl.descriptions.kernel")}
    >
      <Label htmlFor="kernel" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.currentKernel")}
      </Label>
      <Select value={(data.kernel as string) ?? ""} onValueChange={(val) => onUpdate("kernel", val)}>
        <SelectTrigger id="kernel" className="bg-slate-900/80 border-green-500/30 text-green-100 focus:ring-green-500/50">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="bg-slate-900 border-green-500/30 text-green-100">
          {options.kernels.map((opt) => (
            <SelectItem key={opt} value={opt} className="focus:bg-green-500/20">
              {t(`workflowControl.kernelTypes.${opt}`) || opt}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </SectionCard>
  );
}

function RuntimeEditor({ data, t }: { data: Record<string, unknown>; t: (path: string) => string }) {
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
          services.map((svc: RuntimeService, idx: number) => (
            <span key={`svc-${idx}-${typeof svc === "string" ? svc : idx}`} className="text-xs font-mono bg-purple-500/20 text-purple-200 px-2 py-1.5 rounded border border-purple-500/40 shadow-[0_0_5px_rgba(168,85,247,0.2)]">
              {formatRuntimeService(svc)}
            </span>
          ))
        ) : (
          <span className="text-xs text-muted-foreground">-</span>
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
}: {
  data: Record<string, unknown>;
  options: Required<NonNullable<PropertyPanelProps["availableOptions"]>>;
  onUpdate: (key: string, value: unknown) => void;
  t: (path: string) => string;
}) {
  const provider = (data.provider as { active?: string } | undefined) ?? {};

  return (
    <SectionCard
      type="provider"
      icon={Cloud}
      title={t("workflowControl.sections.provider")}
      description={t("workflowControl.descriptions.provider")}
    >
      <Label htmlFor="provider" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.activeProvider")}
      </Label>
      <Select value={provider.active ?? ""} onValueChange={(val) => onUpdate("provider", { active: val })}>
        <SelectTrigger id="provider" className="bg-slate-900/80 border-orange-500/30 text-orange-100 focus:ring-orange-500/50">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="bg-slate-900 border-orange-500/30 text-orange-100">
          {options.providers.map((opt) => (
            <SelectItem key={opt} value={opt} className="focus:bg-orange-500/20">
              {t(`workflowControl.providers.${opt}`) || opt}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </SectionCard>
  );
}

function EmbeddingEditor({
  data,
  options,
  onUpdate,
  t,
}: {
  data: Record<string, unknown>;
  options: Required<NonNullable<PropertyPanelProps["availableOptions"]>>;
  onUpdate: (key: string, value: unknown) => void;
  t: (path: string) => string;
}) {
  return (
    <SectionCard
      type="embedding"
      icon={Database}
      title={t("workflowControl.sections.embedding")}
      description={t("workflowControl.descriptions.embedding")}
    >
      <Label htmlFor="model" className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2.5 block px-0.5">
        {t("workflowControl.labels.currentEmbedding")}
      </Label>
      <Select value={(data.model as string) ?? ""} onValueChange={(val) => onUpdate("model", val)}>
        <SelectTrigger id="model" className="bg-slate-900/80 border-pink-500/30 text-pink-100 focus:ring-pink-500/50">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="bg-slate-900 border-pink-500/30 text-pink-100">
          {options.models.map((opt) => (
            <SelectItem key={opt} value={opt} className="focus:bg-pink-500/20">
              {t(`workflowControl.embeddingModels.${opt}`) || opt}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </SectionCard>
  );
}

export function PropertyPanel({
  selectedNode,
  onUpdateNode,
  availableOptions = DEFAULT_OPTIONS,
}: PropertyPanelProps) {
  const t = useTranslation();

  if (!selectedNode) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground p-4 text-center text-sm">
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
      return <DecisionEditor data={data} options={availableOptions} onUpdate={handleUpdate} t={t} />;
    }
    if (nodeType === "intent") {
      return <IntentEditor data={data} onUpdate={handleUpdate} t={t} />;
    }
    if (nodeType === "kernel") {
      return <KernelEditor data={data} options={availableOptions} onUpdate={handleUpdate} t={t} />;
    }
    if (nodeType === "runtime") {
      return <RuntimeEditor data={data} t={t} />;
    }
    if (nodeType === "provider") {
      return <ProviderEditor data={data} options={availableOptions} onUpdate={handleUpdate} t={t} />;
    }
    return <EmbeddingEditor data={data} options={availableOptions} onUpdate={handleUpdate} t={t} />;
  })();

  return (
    <div className="h-full border border-white/10 bg-slate-950/95 backdrop-blur-xl pt-0 p-4 relative overflow-hidden flex flex-col gap-4 rounded-xl shadow-2xl">
      <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/10 blur-[100px] rounded-full pointer-events-none" />
      <div className="absolute bottom-0 left-0 w-64 h-64 bg-violet-500/10 blur-[100px] rounded-full pointer-events-none" />

      <div className="relative z-10 px-2 py-4">
        <h2 className="text-xs font-bold text-slate-300 uppercase tracking-widest flex items-center gap-2 mb-3">
          <Settings2 className="w-3.5 h-3.5" />
          {t("workflowControl.panels.propertyInspector")}
        </h2>
        <div className="h-px w-full bg-white/5 mb-6" />

        <div className="flex items-center gap-4 mb-5 px-1">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center border shadow-[0_4px_20px_rgba(0,0,0,0.4)] ${visual.headerBgClass} ${visual.iconColorClass}`}>
            <IconComponent className="w-6 h-6" />
          </div>
          <div>
            <div className="text-[10px] text-slate-500 font-mono tracking-tight mb-0.5">{selectedNode.id}</div>
            <div className="text-sm font-bold uppercase tracking-wider text-slate-400">
              {nodeType} {t("workflowControl.labels.node")}
            </div>
          </div>
        </div>

        <div className="space-y-2 relative z-10">
          {editor}
          {!editor && (
            <div className="p-4 rounded-xl border border-slate-700 bg-slate-800/30">
              <Label htmlFor="raw-data" className="text-slate-400 mb-2 block">
                {t("workflowControl.labels.rawData")}
              </Label>
              <pre id="raw-data" className="text-xs bg-slate-950/80 p-3 rounded-lg border border-white/5 overflow-auto max-h-60 font-mono text-slate-300 shadow-inner">
                {JSON.stringify(data, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
