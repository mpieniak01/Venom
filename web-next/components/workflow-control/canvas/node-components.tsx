import { type ReactNode } from "react";
import { Handle, Position, type Node, type NodeProps, type NodeTypes } from "@xyflow/react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import { getStatusTone, type StatusTone } from "@/lib/workflow-control-screen";

import { SWIMLANE_STYLES, WORKFLOW_NODE_THEME, type WorkflowCanvasNodeType } from "./config";
import { readSourceTag, resolveDisplayValue, runtimeBadgeValue } from "./value-formatters";

type DecisionNodeData = { strategy?: string };
type IntentNodeData = { intentMode?: string };
type KernelNodeData = { kernel?: string };
type RuntimeNodeData = { runtime?: { services?: string[] } };
type SourceNodeData = { sourceTag?: string };
type ControlDomainNodeData = {
  domainId?: string;
  label?: string;
  variant?: string;
  optionsCount?: number;
  sourceTag?: string;
};
type RuntimeServiceNodeData = {
  serviceId?: string;
  label?: string;
  kind?: string;
  status?: string;
  dependencyCount?: number;
};
type ExecutionStepNodeData = {
  stepId?: string;
  label?: string;
  variant?: string;
  status?: string;
  stage?: string;
  relatedConfigKeys?: string[];
  relatedServiceId?: string;
  sequenceIndex?: number;
  alternativeVariants?: string[];
  alternativeCount?: number;
  collapsedStepCount?: number;
  groupKey?: string;
  canExpand?: boolean;
  isExpanded?: boolean;
  groupSize?: number;
  onToggleGroup?: (groupKey: string) => void;
  isActiveVariant?: boolean;
};
type SwimlaneNodeData = { label: string; index: number };

type DecisionFlowNode = Node<DecisionNodeData, "decision">;
type IntentFlowNode = Node<IntentNodeData, "intent">;
type KernelFlowNode = Node<KernelNodeData, "kernel">;
type RuntimeFlowNode = Node<RuntimeNodeData, "runtime">;
type SourceFlowNode = Node<SourceNodeData, "provider" | "embedding">;
type ControlDomainFlowNode = Node<ControlDomainNodeData, "control_domain">;
type RuntimeServiceFlowNode = Node<RuntimeServiceNodeData, "runtime_service">;
type ExecutionStepFlowNode = Node<ExecutionStepNodeData, "execution_step">;
type SwimlaneFlowNode = Node<SwimlaneNodeData, "swimlane">;

export function handleExecutionGroupToggleClick(
  event: { stopPropagation: () => void },
  groupKey: string | undefined,
  onToggleGroup: ((groupKey: string) => void) | undefined,
) {
  event.stopPropagation();
  if (groupKey) {
    onToggleGroup?.(groupKey);
  }
}

function SelectedNodePulse({
  selected,
  glowClass,
}: Readonly<{ selected: boolean; glowClass: string }>) {
  if (!selected) return null;
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 rounded-xl border-2 ${glowClass} opacity-70 motion-reduce:animate-none motion-safe:animate-pulse`}
    />
  );
}

function SourceBadge({ sourceTag }: Readonly<{ sourceTag: "local" | "cloud" }>) {
  const t = useTranslation();
  const isCloud = sourceTag === "cloud";
  return (
    <span
      className={[
        "absolute right-2 top-2 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        isCloud
          ? "border-cyan-300/50 bg-cyan-500/15 text-cyan-200"
          : "border-emerald-300/50 bg-emerald-500/15 text-emerald-200",
      ].join(" ")}
    >
      {isCloud
        ? t("workflowControl.labels.cloud")
        : t("workflowControl.labels.installedLocal")}
    </span>
  );
}

function ValueBadge({ value }: Readonly<{ value: string }>) {
  return (
    <span className="absolute right-2 top-2 rounded-full border border-white/15 bg-white/10 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-slate-100">
      {value}
    </span>
  );
}

function statusToneClasses(tone: StatusTone): {
  border: string;
  bg: string;
  text: string;
} {
  if (tone === "success") {
    return {
      border: "border-emerald-300/50",
      bg: "bg-emerald-500/18",
      text: "text-emerald-100",
    };
  }
  if (tone === "warning") {
    return {
      border: "border-amber-300/50",
      bg: "bg-amber-500/18",
      text: "text-amber-100",
    };
  }
  if (tone === "danger") {
    return {
      border: "border-rose-300/55",
      bg: "bg-rose-500/18",
      text: "text-rose-100",
    };
  }
  return {
    border: "border-white/15",
    bg: "bg-white/10",
    text: "text-slate-100",
  };
}

function StatusBadge({ value }: Readonly<{ value: string }>) {
  const tone = statusToneClasses(getStatusTone(value));
  return (
    <span
      className={[
        "absolute right-2 top-2 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        tone.border,
        tone.bg,
        tone.text,
      ].join(" ")}
    >
      {value}
    </span>
  );
}

function MetaBadge({
  value,
  className,
}: Readonly<{ value: string; className?: string }>) {
  return (
    <span className={["rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-slate-300", className].join(" ")}>
      {value}
    </span>
  );
}

function NodeShell({
  selected,
  glowClass,
  children,
  className,
}: Readonly<{
  selected: boolean;
  glowClass: string;
  className: string;
  children: ReactNode;
}>) {
  return (
    <div className={`${className} cursor-pointer`}>
      <SelectedNodePulse selected={selected} glowClass={glowClass} />
      {children}
    </div>
  );
}

function NodeTitle({
  label,
  type,
}: Readonly<{
  label: string;
  type: WorkflowCanvasNodeType;
}>) {
  const theme = WORKFLOW_NODE_THEME[type];
  return <div className={`truncate text-center text-xl font-bold ${theme.titleClass}`}>{label}</div>;
}

function NodeHandles({
  type,
  withTarget = true,
  withSource = true,
}: Readonly<{
  type: WorkflowCanvasNodeType;
  withTarget?: boolean;
  withSource?: boolean;
}>) {
  const theme = WORKFLOW_NODE_THEME[type];
  return (
    <>
      {withTarget ? (
        <Handle type="target" position={Position.Left} className={theme.handleClass} />
      ) : null}
      {withSource ? (
        <Handle type="source" position={Position.Bottom} className={theme.handleClass} />
      ) : null}
    </>
  );
}

export function SwimlaneNode({
  data,
}: NodeProps<SwimlaneFlowNode>) {
  const t = useTranslation();
  const style = SWIMLANE_STYLES[data.label] || {
    bg: "bg-slate-900/20",
    border: "border-slate-800",
    text: "text-slate-500",
    bgContent: "transparent",
  };

  return (
    <div className={`flex h-full w-full flex-row border-b ${style.border}`}>
      <div
        className={`flex h-full w-[40px] items-center justify-center border-r ${style.bg} ${style.border}`}
      >
        <div
          className="w-[200px] -rotate-90 text-center text-[10px] font-extrabold uppercase tracking-widest opacity-90"
          style={{ color: "inherit" }}
        >
          <span className={style.text}>{t(`workflowControl.canvas.${data.label}`)}</span>
        </div>
      </div>
      <div
        className={`h-full flex-1 ${style.bgContent} bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]`}
      />
    </div>
  );
}

export function DecisionNode({ selected = false, data }: NodeProps<DecisionFlowNode>) {
  const t = useTranslation();
  const theme = WORKFLOW_NODE_THEME.decision;
  const badgeValue = resolveDisplayValue(data?.strategy, t, "workflowControl.strategies");
  return (
    <NodeShell
      selected={selected}
      glowClass={theme.glowClass}
      className={theme.shellClass}
    >
      <ValueBadge value={badgeValue} />
      <NodeHandles type="decision" withTarget={false} />
      <NodeTitle type="decision" label={t("workflowControl.sections.decision")} />
    </NodeShell>
  );
}

export function IntentNode({ selected = false, data }: NodeProps<IntentFlowNode>) {
  const t = useTranslation();
  const theme = WORKFLOW_NODE_THEME.intent;
  const badgeValue = resolveDisplayValue(data?.intentMode, t, "workflowControl.intentModes");
  return (
    <NodeShell
      selected={selected}
      glowClass={theme.glowClass}
      className={theme.shellClass}
    >
      <ValueBadge value={badgeValue} />
      <NodeHandles type="intent" />
      <NodeTitle type="intent" label={t("workflowControl.sections.intent")} />
    </NodeShell>
  );
}

export function KernelNode({ selected = false, data }: NodeProps<KernelFlowNode>) {
  const t = useTranslation();
  const theme = WORKFLOW_NODE_THEME.kernel;
  const badgeValue = resolveDisplayValue(data?.kernel, t, "workflowControl.kernelTypes");
  return (
    <NodeShell
      selected={selected}
      glowClass={theme.glowClass}
      className={theme.shellClass}
    >
      <ValueBadge value={badgeValue} />
      <NodeHandles type="kernel" />
      <NodeTitle type="kernel" label={t("workflowControl.labels.currentKernel")} />
    </NodeShell>
  );
}

export function RuntimeNode({ selected = false, data }: NodeProps<RuntimeFlowNode>) {
  const t = useTranslation();
  const theme = WORKFLOW_NODE_THEME.runtime;
  const badgeValue = runtimeBadgeValue(data, t);
  return (
    <NodeShell
      selected={selected}
      glowClass={theme.glowClass}
      className={theme.shellClass}
    >
      <ValueBadge value={badgeValue} />
      <NodeHandles type="runtime" />
      <NodeTitle type="runtime" label={t("workflowControl.labels.runtimeServices")} />
    </NodeShell>
  );
}

export function EmbeddingNode({ selected = false, data }: NodeProps<SourceFlowNode>) {
  const t = useTranslation();
  const theme = WORKFLOW_NODE_THEME.embedding;
  const sourceTag = readSourceTag(data);
  return (
    <NodeShell
      selected={selected}
      glowClass={theme.glowClass}
      className={theme.shellClass}
    >
      <SourceBadge sourceTag={sourceTag} />
      <NodeHandles type="embedding" />
      <NodeTitle type="embedding" label={t("workflowControl.labels.currentEmbedding")} />
    </NodeShell>
  );
}

export function ProviderNode({ selected = false, data }: NodeProps<SourceFlowNode>) {
  const t = useTranslation();
  const theme = WORKFLOW_NODE_THEME.provider;
  const sourceTag = readSourceTag(data);
  return (
    <NodeShell
      selected={selected}
      glowClass={theme.glowClass}
      className={theme.shellClass}
    >
      <SourceBadge sourceTag={sourceTag} />
      <NodeHandles type="provider" withSource={false} />
      <NodeTitle type="provider" label={t("workflowControl.labels.currentProvider")} />
    </NodeShell>
  );
}

export function ControlDomainNode({
  selected = false,
  data,
}: NodeProps<ControlDomainFlowNode>) {
  const theme = WORKFLOW_NODE_THEME.control_domain;
  const sourceTag = readSourceTag(data);
  return (
    <NodeShell selected={selected} glowClass={theme.glowClass} className={theme.shellClass}>
      {data.sourceTag ? <SourceBadge sourceTag={sourceTag} /> : null}
      <Handle type="source" position={Position.Right} className={theme.handleClass} />
      <NodeTitle type="control_domain" label={data.label ?? "Control"} />
      <div className="mt-2 text-center text-sm font-semibold text-slate-100">
        {data.variant ?? "N/A"}
      </div>
      <div className="mt-2 flex justify-center gap-2">
        <MetaBadge value={data.domainId ?? "domain"} />
        {typeof data.optionsCount === "number" && data.optionsCount > 0 ? (
          <MetaBadge value={`${data.optionsCount} alt`} className="text-cyan-200" />
        ) : null}
      </div>
    </NodeShell>
  );
}

export function RuntimeServiceNode({
  selected = false,
  data,
}: NodeProps<RuntimeServiceFlowNode>) {
  const theme = WORKFLOW_NODE_THEME.runtime_service;
  return (
    <NodeShell selected={selected} glowClass={theme.glowClass} className={theme.shellClass}>
      {data.status ? <StatusBadge value={data.status} /> : null}
      <Handle type="target" position={Position.Left} className={theme.handleClass} />
      <Handle type="source" position={Position.Right} className={theme.handleClass} />
      <NodeTitle type="runtime_service" label={data.label ?? "runtime"} />
      <div className="mt-2 text-center text-[11px] uppercase tracking-[0.2em] text-slate-400">
        {data.kind ?? "service"}
      </div>
      <div className="mt-2 flex justify-center gap-2">
        <MetaBadge value={data.serviceId ?? "svc"} />
        <MetaBadge value={`deps ${data.dependencyCount ?? 0}`} className="text-violet-200" />
      </div>
    </NodeShell>
  );
}

function ExecutionStepExpandButton({
  isExpanded,
  groupKey,
  onToggleGroup,
  t,
}: Readonly<{
  isExpanded?: boolean;
  groupKey?: string;
  onToggleGroup?: (groupKey: string) => void;
  t: (path: string) => string;
}>) {
  if (!groupKey) {
    return null;
  }
  return (
    <button
      type="button"
      className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full border border-white/10 bg-slate-950/80 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-200"
      onClick={(event) => {
        handleExecutionGroupToggleClick(event, groupKey, onToggleGroup);
      }}
    >
      {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      {isExpanded
        ? t("workflowControl.actions.collapse")
        : t("workflowControl.actions.expand")}
    </button>
  );
}

function ExecutionStepAlternatives({
  variants,
  remainingAlternatives,
  t,
}: Readonly<{
  variants: string[];
  remainingAlternatives: number;
  t: (path: string) => string;
}>) {
  if (variants.length === 0) {
    return null;
  }
  return (
    <>
      <div className="mt-3 text-center text-[10px] font-semibold uppercase tracking-[0.26em] text-slate-400">
        {t("workflowControl.labels.availableVariants")}
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        {variants.map((variant) => (
          <MetaBadge
            key={variant}
            value={variant}
            className="border-emerald-400/20 bg-emerald-500/10 text-emerald-100"
          />
        ))}
        {remainingAlternatives > 0 ? (
          <MetaBadge
            value={`+${remainingAlternatives}`}
            className="border-white/10 bg-white/5 text-slate-200"
          />
        ) : null}
      </div>
    </>
  );
}

function ExecutionStepMetaBadges({
  data,
  configKeys,
  collapsedStepCount,
  t,
}: Readonly<{
  data: ExecutionStepNodeData;
  configKeys: string[];
  collapsedStepCount: number;
  t: (path: string) => string;
}>) {
  return (
    <div className="mt-3 flex flex-wrap justify-center gap-2">
      {typeof data.sequenceIndex === "number" ? (
        <MetaBadge value={`#${data.sequenceIndex}`} className="text-emerald-200" />
      ) : null}
      {collapsedStepCount > 0 ? (
        <MetaBadge
          value={`+${collapsedStepCount} ${t("workflowControl.labels.branches")}`}
          className="border-amber-400/20 bg-amber-500/10 text-amber-100"
        />
      ) : null}
      {data.isExpanded && (data.groupSize ?? 0) > 1 ? (
        <MetaBadge
          value={`${data.groupSize} ${t("workflowControl.labels.branches")}`}
          className="border-cyan-400/20 bg-cyan-500/10 text-cyan-100"
        />
      ) : null}
      {data.stage ? <MetaBadge value={data.stage} /> : null}
      {data.relatedServiceId ? <MetaBadge value={data.relatedServiceId} /> : null}
      {configKeys.map((configKey) => (
        <MetaBadge key={configKey} value={configKey} />
      ))}
    </div>
  );
}

export function ExecutionStepNode({
  selected = false,
  data,
}: NodeProps<ExecutionStepFlowNode>) {
  const t = useTranslation();
  const theme = WORKFLOW_NODE_THEME.execution_step;
  const configKeys = (data.relatedConfigKeys ?? []).slice(0, 2);
  const visibleAlternatives = data.alternativeVariants ?? [];
  const remainingAlternatives = Math.max(
    0,
    (data.alternativeCount ?? visibleAlternatives.length) - visibleAlternatives.length,
  );
  const collapsedStepCount = data.collapsedStepCount ?? 0;
  const groupKey = data.canExpand ? data.groupKey : undefined;
  return (
    <NodeShell selected={selected} glowClass={theme.glowClass} className={theme.shellClass}>
      {data.status ? <StatusBadge value={data.status} /> : null}
      {data.isActiveVariant ? (
        <span className="absolute right-2 bottom-2 rounded-full border border-cyan-400/30 bg-cyan-500/12 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-100">
          {t("workflowControl.labels.activeVariant")}
        </span>
      ) : null}
      <ExecutionStepExpandButton
        isExpanded={data.isExpanded}
        groupKey={groupKey}
        onToggleGroup={data.onToggleGroup}
        t={t}
      />
      <Handle type="target" position={Position.Left} className={theme.handleClass} />
      <Handle type="source" position={Position.Right} className={theme.handleClass} />
      <NodeTitle type="execution_step" label={data.label ?? "step"} />
      <div className="mt-2 text-center text-[10px] font-semibold uppercase tracking-[0.26em] text-emerald-300">
        {t("workflowControl.labels.activeVariant")}
      </div>
      <div className="mt-1 text-center text-sm font-semibold text-slate-100">
        {data.variant ?? "action"}
      </div>
      <ExecutionStepAlternatives
        variants={visibleAlternatives}
        remainingAlternatives={remainingAlternatives}
        t={t}
      />
      <ExecutionStepMetaBadges
        data={data}
        configKeys={configKeys}
        collapsedStepCount={collapsedStepCount}
        t={t}
      />
    </NodeShell>
  );
}

export const workflowCanvasNodeTypes: NodeTypes = {
  decision: DecisionNode,
  intent: IntentNode,
  kernel: KernelNode,
  runtime: RuntimeNode,
  provider: ProviderNode,
  embedding: EmbeddingNode,
  control_domain: ControlDomainNode,
  runtime_service: RuntimeServiceNode,
  execution_step: ExecutionStepNode,
  swimlane: SwimlaneNode,
};
