import { type ReactNode } from "react";
import { Handle, NodeToolbar, Position, type Node, type NodeProps, type NodeTypes } from "@xyflow/react";
import { Info, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";

import { SWIMLANE_STYLES, WORKFLOW_NODE_THEME, type WorkflowCanvasNodeType } from "./config";
import { readSourceTag, resolveDisplayValue, runtimeBadgeValue } from "./value-formatters";

type DecisionNodeData = { strategy?: string };
type IntentNodeData = { intentMode?: string };
type KernelNodeData = { kernel?: string };
type RuntimeNodeData = { runtime?: { services?: string[] } };
type SourceNodeData = { sourceTag?: string };
type SwimlaneNodeData = { label: string; index: number };

type DecisionFlowNode = Node<DecisionNodeData, "decision">;
type IntentFlowNode = Node<IntentNodeData, "intent">;
type KernelFlowNode = Node<KernelNodeData, "kernel">;
type RuntimeFlowNode = Node<RuntimeNodeData, "runtime">;
type SourceFlowNode = Node<SourceNodeData, "provider" | "embedding">;
type SwimlaneFlowNode = Node<SwimlaneNodeData, "swimlane">;

function NodeActions() {
  const t = useTranslation();
  return (
    <NodeToolbar
      position={Position.Top}
      className="flex gap-1 rounded-md border border-white/10 bg-slate-900/90 p-1 shadow-xl backdrop-blur-md"
    >
      <Button
        variant="ghost"
        size="sm"
        className="h-6 w-6 p-0 hover:bg-white/10"
        title={t("workflowControl.actions.edit")}
      >
        <Settings className="h-3 w-3 text-slate-200" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 w-6 p-0 hover:bg-white/10"
        title={t("workflowControl.actions.details")}
      >
        <Info className="h-3 w-3 text-blue-400" />
      </Button>
    </NodeToolbar>
  );
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
    <div className={className}>
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
          <span className={style.text}>{t(`workflowControl.sections.${data.label}`)}</span>
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
      <NodeActions />
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
      <NodeActions />
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
      <NodeActions />
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
      <NodeActions />
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
      <NodeActions />
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
      <NodeActions />
      <NodeTitle type="provider" label={t("workflowControl.labels.currentProvider")} />
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
  swimlane: SwimlaneNode,
};
