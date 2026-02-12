"use client";

import type { ReactNode } from "react";
import type {
  FeedbackLogsResponse,
  HistoryRequest,
  LearningLogsResponse,
  QueueStatus,
  ServiceStatus,
} from "@/lib/types";
import { CockpitInsightsSection } from "@/components/cockpit/cockpit-insights-section";

type MacroAction = {
  id: string;
  label: string;
  description: string;
  content: string;
  custom?: boolean;
};

type AgentDeckEntry = {
  name: string;
  status: string;
  detail?: string;
};

type StatusEntry = {
  label: string;
  value: number;
  hint?: string;
  tone?: "success" | "warning" | "danger" | "neutral";
  icon?: ReactNode;
};

type TelemetryEvent = { id: string; ts: number; payload: unknown };

type CockpitRuntimeProps = Readonly<{
  chatFullscreen: boolean;
  showArtifacts: boolean;
  showReferenceSections: boolean;
  showSharedSections: boolean;
  usageMetrics?: { memory_usage_percent?: number | null } | null;
  cpuUsageValue: string;
  gpuUsageValue: string;
  ramValue: string;
  vramValue: string;
  diskValue: string;
  diskPercent?: string | null;
  sessionCostValue: string;
  graphNodes: number;
  graphEdges: number;
  agentDeck: AgentDeckEntry[];
  queue: QueueStatus | null;
  queueLoading: boolean;
  queueAction: string | null;
  queueActionMessage: string | null;
  onToggleQueue: () => void;
  onExecuteQueueMutation: (action: "purge" | "emergency") => void;
  history: HistoryRequest[];
  historyStatusEntries: StatusEntry[];
  selectedRequestId?: string | null;
  onSelectHistory: (entry: HistoryRequest) => void;
  loadingHistory: boolean;
  historyError?: string | null;
  learningLogs?: LearningLogsResponse | null;
  learningLoading: boolean;
  learningError?: string | null;
  feedbackLogs?: FeedbackLogsResponse | null;
  feedbackLoading: boolean;
  feedbackError?: string | null;
  hiddenPromptsPanel: ReactNode;
  services: ServiceStatus[] | null | undefined;
  entries: TelemetryEvent[];
  newMacro: { label: string; description: string; content: string };
  setNewMacro: (value: { label: string; description: string; content: string }) => void;
  customMacros: MacroAction[];
  setCustomMacros: (next: MacroAction[]) => void;
  allMacros: MacroAction[];
  macroSending: string | null;
  onRunMacro: (macro: MacroAction) => void;
  onOpenQuickActions: () => void;
}>;

export function CockpitRuntime(props: CockpitRuntimeProps) {
  return <CockpitInsightsSection {...props} />;
}
