import { type ReactNode } from "react";
import { Handle, NodeToolbar, Position, type NodeProps } from "@xyflow/react";
import { Info, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";

import { SWIMLANE_STYLES } from "./config";
import { readSourceTag, resolveDisplayValue, runtimeBadgeValue } from "./value-formatters";

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

export function SwimlaneNode({
  data,
}: NodeProps<{ label: string; index: number }>) {
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

export function DecisionNode({ selected = false, data }: NodeProps) {
  const t = useTranslation();
  const badgeValue = resolveDisplayValue(
    (data as { strategy?: unknown } | undefined)?.strategy,
    t,
    "workflowControl.strategies"
  );
  return (
    <NodeShell
      selected={selected}
      glowClass="border-blue-300/90 shadow-[0_0_24px_rgba(96,165,250,0.45)]"
      className="group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-blue-500 bg-slate-900 px-8 py-6 text-blue-100 shadow-[0_0_15px_rgba(59,130,246,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(59,130,246,0.5)]"
    >
      <ValueBadge value={badgeValue} />
      <Handle type="source" position={Position.Bottom} className="!h-3 !w-3 !bg-blue-500" />
      <NodeActions />
      <div className="truncate text-center text-xl font-bold text-blue-400">
        {t("workflowControl.sections.decision")}
      </div>
    </NodeShell>
  );
}

export function IntentNode({ selected = false, data }: NodeProps) {
  const t = useTranslation();
  const badgeValue = resolveDisplayValue(
    (data as { intentMode?: unknown } | undefined)?.intentMode,
    t,
    "workflowControl.intentModes"
  );
  return (
    <NodeShell
      selected={selected}
      glowClass="border-yellow-300/90 shadow-[0_0_24px_rgba(253,224,71,0.45)]"
      className="group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-yellow-500 bg-slate-900 px-8 py-6 text-yellow-100 shadow-[0_0_15px_rgba(234,179,8,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(234,179,8,0.5)]"
    >
      <ValueBadge value={badgeValue} />
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !bg-yellow-500" />
      <Handle type="source" position={Position.Bottom} className="!h-3 !w-3 !bg-yellow-500" />
      <NodeActions />
      <div className="truncate text-center text-xl font-bold text-yellow-400">
        {t("workflowControl.sections.intent")}
      </div>
    </NodeShell>
  );
}

export function KernelNode({ selected = false, data }: NodeProps) {
  const t = useTranslation();
  const badgeValue = resolveDisplayValue(
    (data as { kernel?: unknown } | undefined)?.kernel,
    t,
    "workflowControl.kernelTypes"
  );
  return (
    <NodeShell
      selected={selected}
      glowClass="border-green-300/90 shadow-[0_0_24px_rgba(74,222,128,0.45)]"
      className="group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-green-500 bg-slate-900 px-8 py-6 text-green-100 shadow-[0_0_15px_rgba(34,197,94,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(34,197,94,0.5)]"
    >
      <ValueBadge value={badgeValue} />
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !bg-green-500" />
      <Handle type="source" position={Position.Bottom} className="!h-3 !w-3 !bg-green-500" />
      <NodeActions />
      <div className="truncate text-center text-xl font-bold text-green-400">
        {t("workflowControl.labels.currentKernel")}
      </div>
    </NodeShell>
  );
}

export function RuntimeNode({ selected = false, data }: NodeProps) {
  const t = useTranslation();
  const badgeValue = runtimeBadgeValue(data, t);
  return (
    <NodeShell
      selected={selected}
      glowClass="border-purple-300/90 shadow-[0_0_24px_rgba(196,181,253,0.45)]"
      className="group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-purple-500 bg-slate-900 px-8 py-6 text-purple-100 shadow-[0_0_15px_rgba(168,85,247,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(168,85,247,0.5)]"
    >
      <ValueBadge value={badgeValue} />
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !bg-purple-500" />
      <Handle type="source" position={Position.Bottom} className="!h-3 !w-3 !bg-purple-500" />
      <NodeActions />
      <div className="truncate text-center text-xl font-bold text-purple-400">
        {t("workflowControl.labels.runtimeServices")}
      </div>
    </NodeShell>
  );
}

export function EmbeddingNode({ selected = false, data }: NodeProps) {
  const t = useTranslation();
  const sourceTag = readSourceTag(data);
  return (
    <NodeShell
      selected={selected}
      glowClass="border-pink-300/90 shadow-[0_0_24px_rgba(249,168,212,0.45)]"
      className="group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-pink-500 bg-slate-900 px-8 py-6 text-pink-100 shadow-[0_0_15px_rgba(236,72,153,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(236,72,153,0.5)]"
    >
      <SourceBadge sourceTag={sourceTag} />
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !bg-pink-500" />
      <Handle type="source" position={Position.Bottom} className="!h-3 !w-3 !bg-pink-500" />
      <NodeActions />
      <div className="truncate text-center text-xl font-bold text-pink-400">
        {t("workflowControl.labels.currentEmbedding")}
      </div>
    </NodeShell>
  );
}

export function ProviderNode({ selected = false, data }: NodeProps) {
  const t = useTranslation();
  const sourceTag = readSourceTag(data);
  return (
    <NodeShell
      selected={selected}
      glowClass="border-orange-300/90 shadow-[0_0_24px_rgba(253,186,116,0.45)]"
      className="group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-orange-500 bg-slate-900 px-8 py-6 text-orange-100 shadow-[0_0_15px_rgba(249,115,22,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(249,115,22,0.5)]"
    >
      <SourceBadge sourceTag={sourceTag} />
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !bg-orange-500" />
      <NodeActions />
      <div className="truncate text-center text-xl font-bold text-orange-400">
        {t("workflowControl.labels.currentProvider")}
      </div>
    </NodeShell>
  );
}

export const workflowCanvasNodeTypes = {
  decision: DecisionNode,
  intent: IntentNode,
  kernel: KernelNode,
  runtime: RuntimeNode,
  provider: ProviderNode,
  embedding: EmbeddingNode,
  swimlane: SwimlaneNode,
};
