"use client";

import { createElement, useMemo } from "react";
import type { ComponentProps, RefObject } from "react";
import type { LogEntryType } from "@/lib/logs";
import type { HistoryRequest, HistoryRequestDetail, ServiceStatus, Task, LlmServerInfo, HiddenPromptEntry, HiddenPromptsResponse, LearningLogsResponse, FeedbackLogsResponse } from "@/lib/types";
import type { GenerationParams } from "@/lib/types";
import type { TokenSample } from "@/components/cockpit/token-types";
import type { GenerationSchema } from "@/components/ui/dynamic-parameter-form";
import type { SessionHistoryEntry } from "@/components/cockpit/cockpit-hooks";
import { CockpitHiddenPromptsPanel } from "@/components/cockpit/cockpit-hidden-prompts-panel";
import { CockpitPrimarySection } from "@/components/cockpit/cockpit-primary-section";
import { CockpitRuntimeSection } from "@/components/cockpit/cockpit-runtime-section";
import { useCockpitRuntimeSectionProps } from "@/components/cockpit/cockpit-runtime-props";

type PrimarySectionProps = ComponentProps<typeof CockpitPrimarySection>;
type RuntimeSectionProps = ComponentProps<typeof CockpitRuntimeSection>;

type CockpitSectionPropsInput = {
  chatFullscreen: boolean;
  setChatFullscreen: (value: boolean) => void;
  showArtifacts: boolean;
  showReferenceSections: boolean;
  showSharedSections: boolean;
  labMode: boolean;
  responseBadgeTone: "success" | "warning" | "danger" | "neutral" | string;
  responseBadgeTitle: string;
  responseBadgeText: string;
  chatMessages: PrimarySectionProps["chatThreadProps"]["chatMessages"];
  selectedRequestId: string | null;
  historyLoading: boolean;
  feedbackByRequest: Record<string, { rating?: "up" | "down" | null; comment?: string; message?: string | null }>;
  feedbackSubmittingId: string | null;
  onOpenRequestDetail: (requestId: string, prompt?: string) => void;
  onFeedbackClick: (requestId: string, rating: "up" | "down") => void;
  onFeedbackSubmit: (requestId: string, override?: { rating: "up" | "down"; comment?: string }) => void;
  onUpdateFeedbackState: (requestId: string, patch: { rating?: "up" | "down" | null; comment?: string; message?: string | null }) => void;
  chatScrollRef: RefObject<HTMLDivElement>;
  onChatScroll: () => void;
  composerRef: PrimarySectionProps["composerProps"]["ref"];
  onSend: (payload: string) => Promise<boolean>;
  sending: boolean;
  chatMode: PrimarySectionProps["composerProps"]["chatMode"];
  setChatMode: PrimarySectionProps["composerProps"]["setChatMode"];
  setLabMode: (value: boolean) => void;
  selectedLlmServer: string;
  llmServerOptions: PrimarySectionProps["composerProps"]["llmServerOptions"];
  setSelectedLlmServer: (value: string) => void;
  selectedLlmModel: string;
  llmModelOptions: PrimarySectionProps["composerProps"]["llmModelOptions"];
  setSelectedLlmModel: (value: string) => void;
  onActivateModel: (value: string) => void;
  hasModels: boolean;
  onOpenTuning: () => void;
  tuningLabel: string;
  quickActionsOpen: boolean;
  setQuickActionsOpen: (value: boolean) => void;
  message: string | null;
  promptPresets: ReadonlyArray<{ id: string; category: string; description: string; prompt: string; icon: string }>;
  onSuggestionClick: (prompt: string) => void;
  llmServersLoading: boolean;
  llmServers: LlmServerInfo[];
  llmServerOptionsPanel: PrimarySectionProps["llmOpsPanelProps"]["llmServerOptions"];
  llmModelOptionsPanel: PrimarySectionProps["llmOpsPanelProps"]["llmModelOptions"];
  availableModelsForServer: Array<{ name?: string }>;
  selectedServerEntry: PrimarySectionProps["llmOpsPanelProps"]["selectedServerEntry"];
  resolveServerStatus: (displayName?: string, status?: string | null) => string;
  sessionId: string;
  memoryAction: null | "session" | "global";
  onSessionReset: () => void;
  onServerSessionReset: () => void;
  onClearSessionMemory: () => void;
  onClearGlobalMemory: () => void;
  activeServerInfo: PrimarySectionProps["llmOpsPanelProps"]["activeServerInfo"];
  activeServerName: string;
  llmActionPending: string | null;
  onActivateServer: (override?: { server?: string; model?: string }) => void;
  connected: boolean;
  logFilter: string;
  onLogFilterChange: (value: string) => void;
  logEntries: LogEntryType[];
  pinnedLogs: LogEntryType[];
  onTogglePin: (entry: LogEntryType) => void;
  exportingPinned: boolean;
  onExportPinnedLogs: () => void;
  onClearPinnedLogs: () => void;
  tasksPreview: Array<Task>;
  hiddenScoreFilter: number;
  hiddenIntentFilter: string;
  onHiddenIntentFilterChange: (value: string) => void;
  onHiddenScoreFilterChange: (value: number) => void;
  hiddenIntentOptions: string[];
  selectableHiddenPrompts: HiddenPromptEntry[];
  activeHiddenKeys: Set<string>;
  activeHiddenMap: Map<string, HiddenPromptEntry>;
  activeForIntent: HiddenPromptEntry | null;
  hiddenPrompts: HiddenPromptsResponse | null;
  hiddenLoading: boolean;
  hiddenError: string | null;
  activeHiddenLoading: boolean;
  activeHiddenError: string | null;
  onSetActiveHiddenPrompt: (payload: {
    intent?: string;
    prompt?: string;
    approved_response?: string;
    prompt_hash?: string;
    active: boolean;
    actor: string;
  }) => Promise<void>;
  history: Array<HistoryRequest>;
  loadingHistory: boolean;
  historyError: string | null;
  metrics: PrimarySectionProps["metricsProps"]["metrics"];
  metricsLoading: boolean;
  successRate: number | null;
  tasksCreated: number;
  queue: PrimarySectionProps["metricsProps"]["queue"];
  feedbackScore: number | null;
  feedbackUp: number;
  feedbackDown: number;
  tokenMetricsLoading: boolean;
  tokenSplits: Array<{ label: string; value: number }>;
  tokenHistory: TokenSample[];
  tokenTrendDelta: number;
  tokenTrendLabel: string;
  totalTokens: number;
  telemetryFeed: Array<{ id: string; type: string; message: string; timestamp: string; tone: "success" | "warning" | "danger" | "neutral" }>;
  usageMetrics: Record<string, number> | null;
  cpuUsageValue: number | null;
  gpuUsageValue: number | null;
  ramValue: number | null;
  vramValue: number | null;
  diskValue: number | null;
  diskPercent: number | null;
  sessionCostValue: number | null;
  graphNodes: string | number;
  graphEdges: string | number;
  agentDeck: Array<{ label: string; value: string }>;
  queueLoading: boolean;
  queueAction: string | null;
  queueActionMessage: string | null;
  onToggleQueue: () => void;
  onExecuteQueueMutation: (action: "purge" | "emergency") => Promise<void>;
  historyStatusEntries: Array<{ label: string; value: number }>;
  learningLogs: LearningLogsResponse | null;
  learningLoading: boolean;
  learningError: string | null;
  feedbackLogs: FeedbackLogsResponse | null;
  feedbackLoading: boolean;
  feedbackError: string | null;
  services: Array<{ name: string; status: ServiceStatus }>;
  entries: Array<{ id: string; payload: unknown; timestamp: string }>;
  newMacro: { label: string; description: string; content: string };
  setNewMacro: (value: { label: string; description: string; content: string }) => void;
  customMacros: Array<{ id: string; label: string; description: string; content: string; type?: "system" | "user" }>;
  setCustomMacros: (value: Array<any>) => void;
  allMacros: Array<{ id: string; label: string; description: string; content: string; type?: "system" | "user" }>;
  macroSending: string | null;
  onRunMacro: (macro: any) => void;
  onAddMacro: () => void;
  onDeleteMacro: (id: string) => void;
  onClearMacros: () => void;
  detailOpen: boolean;
  setDetailOpen: (value: boolean) => void;
  onCloseDetail: () => void;
  historyDetail: HistoryRequestDetail | null;
  selectedTask: Task | null;
  uiTimingEntry: Record<string, number> | undefined;
  llmStartAt: string | null;
  payloadSessionMeta: Record<string, unknown> | undefined;
  payloadForcedRoute: Record<string, unknown> | undefined;
  payloadGenerationParams: Record<string, unknown> | undefined;
  payloadContextUsed: Record<string, unknown> | undefined;
  contextPreviewMeta: { preview?: string | null; truncated?: boolean | null; hiddenPrompts?: number | null; mode?: string | null } | null;
  copyStepsMessage: string | null;
  onCopyDetailSteps: () => void;
  t: (key: string, replacements?: Record<string, string | number>) => string;
  tuningOpen: boolean;
  setTuningOpen: (value: boolean) => void;
  loadingSchema: boolean;
  modelSchema: GenerationSchema | null;
  generationParams: GenerationParams | null;
  onChangeGenerationParams: (values: Record<string, unknown>) => void;
  onResetGenerationParams: () => void;
  tuningSaving: boolean;
  onApplyTuning: () => void;
};

export function useCockpitSectionProps({
  chatFullscreen,
  setChatFullscreen,
  showArtifacts,
  showReferenceSections,
  showSharedSections,
  labMode,
  responseBadgeTone,
  responseBadgeTitle,
  responseBadgeText,
  chatMessages,
  selectedRequestId,
  historyLoading,
  feedbackByRequest,
  feedbackSubmittingId,
  onOpenRequestDetail,
  onFeedbackClick,
  onFeedbackSubmit,
  onUpdateFeedbackState,
  chatScrollRef,
  onChatScroll,
  composerRef,
  onSend,
  sending,
  chatMode,
  setChatMode,
  setLabMode,
  selectedLlmServer,
  llmServerOptions,
  setSelectedLlmServer,
  selectedLlmModel,
  llmModelOptions,
  setSelectedLlmModel,
  onActivateModel,
  hasModels,
  onOpenTuning,
  tuningLabel,
  quickActionsOpen,
  setQuickActionsOpen,
  message,
  promptPresets,
  onSuggestionClick,
  llmServersLoading,
  llmServers,
  llmServerOptionsPanel,
  llmModelOptionsPanel,
  availableModelsForServer,
  selectedServerEntry,
  resolveServerStatus,
  sessionId,
  memoryAction,
  onSessionReset,
  onServerSessionReset,
  onClearSessionMemory,
  onClearGlobalMemory,
  activeServerInfo,
  activeServerName,
  llmActionPending,
  onActivateServer,
  connected,
  logFilter,
  onLogFilterChange,
  logEntries,
  pinnedLogs,
  onTogglePin,
  exportingPinned,
  onExportPinnedLogs,
  onClearPinnedLogs,
  tasksPreview,
  hiddenScoreFilter,
  hiddenIntentFilter,
  onHiddenIntentFilterChange,
  onHiddenScoreFilterChange,
  hiddenIntentOptions,
  selectableHiddenPrompts,
  activeHiddenKeys,
  activeHiddenMap,
  activeForIntent,
  hiddenPrompts,
  hiddenLoading,
  hiddenError,
  activeHiddenLoading,
  activeHiddenError,
  onSetActiveHiddenPrompt,
  history,
  loadingHistory,
  historyError,
  metrics,
  metricsLoading,
  successRate,
  tasksCreated,
  queue,
  feedbackScore,
  feedbackUp,
  feedbackDown,
  tokenMetricsLoading,
  tokenSplits,
  tokenHistory,
  tokenTrendDelta,
  tokenTrendLabel,
  totalTokens,
  telemetryFeed,
  usageMetrics,
  cpuUsageValue,
  gpuUsageValue,
  ramValue,
  vramValue,
  diskValue,
  diskPercent,
  sessionCostValue,
  graphNodes,
  graphEdges,
  agentDeck,
  queueLoading,
  queueAction,
  queueActionMessage,
  onToggleQueue,
  onExecuteQueueMutation,
  historyStatusEntries,
  learningLogs,
  learningLoading,
  learningError,
  feedbackLogs,
  feedbackLoading,
  feedbackError,
  services,
  entries,
  newMacro,
  setNewMacro,
  customMacros,
  setCustomMacros,
  allMacros,
  macroSending,
  onRunMacro,
  detailOpen,
  setDetailOpen,
  onCloseDetail,
  historyDetail,
  selectedTask,
  uiTimingEntry,
  llmStartAt,
  payloadSessionMeta,
  payloadForcedRoute,
  payloadGenerationParams,
  payloadContextUsed,
  contextPreviewMeta,
  copyStepsMessage,
  onCopyDetailSteps,
  feedbackByRequest: detailFeedbackByRequest,
  feedbackSubmittingId: detailFeedbackSubmittingId,
  onFeedbackSubmit: onFeedbackSubmitDetail,
  onUpdateFeedbackState: onUpdateFeedbackStateDetail,
  t,
  tuningOpen,
  setTuningOpen,
  loadingSchema,
  modelSchema,
  generationParams,
  onChangeGenerationParams,
  onResetGenerationParams,
  tuningSaving,
  onApplyTuning,
  onAddMacro,
  onDeleteMacro,
  onClearMacros,
}: CockpitSectionPropsInput) {
  const chatThreadProps = useMemo(() => ({
    chatMessages,
    selectedRequestId,
    historyLoading,
    feedbackByRequest,
    feedbackSubmittingId,
    onOpenRequestDetail,
    onFeedbackClick,
    onFeedbackSubmit,
    onUpdateFeedbackState,
  }), [
    chatMessages,
    feedbackByRequest,
    feedbackSubmittingId,
    historyLoading,
    onFeedbackClick,
    onFeedbackSubmit,
    onOpenRequestDetail,
    onUpdateFeedbackState,
    selectedRequestId,
  ]);

  const composerProps = useMemo(() => ({
    ref: composerRef,
    onSend,
    sending,
    chatMode,
    setChatMode,
    labMode,
    setLabMode,
    selectedLlmServer,
    llmServerOptions,
    setSelectedLlmServer,
    selectedLlmModel,
    llmModelOptions,
    setSelectedLlmModel,
    onActivateModel,
    hasModels,
    onOpenTuning,
    tuningLabel,
    compactControls: chatFullscreen,
  }), [
    chatFullscreen,
    chatMode,
    composerRef,
    hasModels,
    labMode,
    llmModelOptions,
    llmServerOptions,
    onActivateModel,
    onOpenTuning,
    onSend,
    selectedLlmModel,
    selectedLlmServer,
    sending,
    setChatMode,
    setLabMode,
    setSelectedLlmModel,
    setSelectedLlmServer,
    tuningLabel,
  ]);

  const llmOpsPanelProps = useMemo(() => ({
    llmServersLoading,
    llmServers,
    selectedLlmServer,
    llmServerOptions: llmServerOptionsPanel,
    onSelectLlmServer: setSelectedLlmServer,
    selectedLlmModel,
    llmModelOptions: llmModelOptionsPanel,
    onSelectLlmModel: setSelectedLlmModel,
    availableModelsForServer,
    selectedServerEntry,
    resolveServerStatus,
    sessionId,
    memoryAction,
    onSessionReset,
    onServerSessionReset,
    onClearSessionMemory,
    onClearGlobalMemory,
    activeServerInfo,
    activeServerName,
    llmActionPending,
    onActivateServer,
    connected,
    logFilter,
    onLogFilterChange,
    logEntries,
    pinnedLogs,
    onTogglePin,
    exportingPinned,
    onExportPinnedLogs,
    onClearPinnedLogs,
    tasksPreview,
  }), [
    activeServerInfo,
    activeServerName,
    availableModelsForServer,
    connected,
    exportingPinned,
    llmActionPending,
    llmModelOptionsPanel,
    llmServerOptionsPanel,
    llmServers,
    llmServersLoading,
    logEntries,
    logFilter,
    memoryAction,
    onActivateServer,
    onClearGlobalMemory,
    onClearSessionMemory,
    onExportPinnedLogs,
    onLogFilterChange,
    onSessionReset,
    onServerSessionReset,
    onTogglePin,
    onClearPinnedLogs,
    pinnedLogs,
    resolveServerStatus,
    selectedLlmModel,
    selectedLlmServer,
    selectedServerEntry,
    setSelectedLlmModel,
    setSelectedLlmServer,
    sessionId,
    tasksPreview,
  ]);

  const hiddenPromptsPanelProps = useMemo(() => ({
    hiddenScoreFilter,
    hiddenIntentFilter,
    onHiddenIntentFilterChange,
    onHiddenScoreFilterChange,
    hiddenIntentOptions,
    selectableHiddenPrompts,
    activeHiddenKeys,
    activeHiddenMap,
    activeForIntent,
    hiddenPrompts,
    hiddenLoading,
    hiddenError,
    activeHiddenLoading,
    activeHiddenError,
    onSetActiveHiddenPrompt,
  }), [
    activeForIntent,
    activeHiddenError,
    activeHiddenKeys,
    activeHiddenLoading,
    activeHiddenMap,
    hiddenError,
    hiddenIntentFilter,
    hiddenIntentOptions,
    hiddenLoading,
    hiddenPrompts,
    hiddenScoreFilter,
    onHiddenIntentFilterChange,
    onHiddenScoreFilterChange,
    onSetActiveHiddenPrompt,
    selectableHiddenPrompts,
  ]);

  const historyPanelProps = useMemo(() => ({
    history: history as HistoryRequest[],
    selectedRequestId,
    onSelect: (entry: HistoryRequest) =>
      onOpenRequestDetail(entry.request_id, entry.prompt),
    loadingHistory,
    historyError,
  }), [
    history,
    historyError,
    loadingHistory,
    onOpenRequestDetail,
    selectedRequestId,
  ]);

  const metricsProps = useMemo(() => ({
    metrics,
    metricsLoading,
    successRate,
    tasksCreated,
    queue,
    feedbackScore,
    feedbackUp,
    feedbackDown,
    tokenMetricsLoading,
    tokenSplits,
    tokenHistory,
    tokenTrendDelta,
    tokenTrendLabel,
    totalTokens,
    showReferenceSections,
    telemetryFeed,
  }), [
    feedbackDown,
    feedbackScore,
    feedbackUp,
    metrics,
    metricsLoading,
    queue,
    showReferenceSections,
    successRate,
    tasksCreated,
    telemetryFeed,
    tokenHistory,
    tokenMetricsLoading,
    tokenSplits,
    tokenTrendDelta,
    tokenTrendLabel,
    totalTokens,
  ]);

  const runtimeSectionProps = useCockpitRuntimeSectionProps({
    runtimeProps: {
      chatFullscreen,
      showArtifacts,
      showReferenceSections,
      showSharedSections,
      usageMetrics,
      cpuUsageValue: (cpuUsageValue ?? 0).toString(),
      gpuUsageValue: (gpuUsageValue ?? 0).toString(),
      ramValue: (ramValue ?? 0).toString(),
      vramValue: (vramValue ?? 0).toString(),
      diskValue: (diskValue ?? 0).toString(),
      diskPercent: (diskPercent ?? 0).toString(),
      sessionCostValue: (sessionCostValue ?? 0).toString(),
      graphNodes: typeof graphNodes === 'string' ? parseInt(graphNodes, 10) || 0 : graphNodes,
      graphEdges: typeof graphEdges === 'string' ? parseInt(graphEdges, 10) || 0 : graphEdges,
      agentDeck: agentDeck.map(a => ({ name: a.label, status: a.value })),
      queue: queue ? { active: queue.active ?? 0, pending: 0, limit: typeof queue.limit === 'number' ? queue.limit : undefined } : null,
      queueLoading,
      queueAction,
      queueActionMessage,
      onToggleQueue,
      onExecuteQueueMutation,
      history,
      historyStatusEntries,
      selectedRequestId,
      onSelectHistory: (entry) => onOpenRequestDetail(entry.request_id, entry.prompt),
      loadingHistory,
      historyError,
      learningLogs,
      learningLoading,
      learningError,
      feedbackLogs,
      feedbackLoading,
      feedbackError,
      hiddenPromptsPanel: createElement(CockpitHiddenPromptsPanel, hiddenPromptsPanelProps),
      services: services.map(s => typeof s.status === 'string' ? { name: s.name, status: s.status } as ServiceStatus : s.status),
      entries: entries.map(e => ({ id: e.id, payload: e.payload, ts: new Date(e.timestamp).getTime() })),
      newMacro,
      setNewMacro,
      customMacros,
      setCustomMacros,
      allMacros,
      macroSending,

      onRunMacro,
      onOpenQuickActions: () => setQuickActionsOpen(true),
    },
    requestDetailProps: {
      open: detailOpen,
      onOpenChange: setDetailOpen,
      onClose: onCloseDetail,
      historyDetail,
      loadingHistory,
      historyError,
      selectedRequestId,
      selectedTask,
      uiTimingEntry,
      llmStartAt,
      payloadSessionMeta,
      payloadForcedRoute,
      payloadGenerationParams,
      payloadContextUsed,
      contextPreviewMeta,
      copyStepsMessage,
      onCopyDetailSteps,
      feedbackByRequest: detailFeedbackByRequest,
      feedbackSubmittingId: detailFeedbackSubmittingId,
      onFeedbackSubmit: onFeedbackSubmitDetail as any,
      onUpdateFeedbackState: onUpdateFeedbackStateDetail as any,
      t,
    },
    tuningDrawerProps: {
      open: tuningOpen,
      onOpenChange: setTuningOpen,
      loadingSchema,
      modelSchema,
      generationParams,
      onChangeGenerationParams,
      onResetGenerationParams,
      tuningSaving,
      onApply: onApplyTuning,
    },
  });

  const primarySectionProps = useMemo(() => ({
    chatFullscreen,
    setChatFullscreen,
    showArtifacts,
    showReferenceSections,
    showSharedSections,
    labMode,
    responseBadgeTone: responseBadgeTone as "success" | "warning" | "neutral" | "danger",
    responseBadgeTitle,
    responseBadgeText,
    chatThreadProps,
    chatScrollRef,
    onChatScroll,
    composerProps,
    quickActionsOpen,
    setQuickActionsOpen,
    message,
    promptPresets,
    onSuggestionClick,
    llmOpsPanelProps,
    hiddenPromptsPanelProps,
    historyPanelProps,
    metricsProps,
  }), [
    chatFullscreen,
    chatScrollRef,
    chatThreadProps,
    composerProps,
    hiddenPromptsPanelProps,
    historyPanelProps,
    labMode,
    llmOpsPanelProps,
    message,
    metricsProps,
    onChatScroll,
    onSuggestionClick,
    promptPresets,
    quickActionsOpen,
    responseBadgeText,
    responseBadgeTitle,
    responseBadgeTone,
    setChatFullscreen,
    setQuickActionsOpen,
    showArtifacts,
    showReferenceSections,
    showSharedSections,
  ]);

  return { primarySectionProps, runtimeSectionProps };
}
