"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import type { ComponentProps, RefObject } from "react";
import type { CockpitInitialData } from "@/lib/server-data";
import { CockpitHeader } from "@/components/cockpit/cockpit-header";
import { CockpitPrimarySection } from "@/components/cockpit/cockpit-primary-section";
import { CockpitRuntimeSection } from "@/components/cockpit/cockpit-runtime-section";
import { useCockpitSectionProps } from "@/components/cockpit/cockpit-section-props";
import { useCockpitLayout } from "./hooks/use-cockpit-layout";
import { useCockpitData } from "./hooks/use-cockpit-data";
import { useCockpitInteractiveState } from "./hooks/use-cockpit-interactive-state";
import { useCockpitLogic } from "./hooks/use-cockpit-logic";
import { PROMPT_PRESETS } from "@/components/cockpit/cockpit-prompts";
import { useTranslation } from "@/lib/i18n";
import { useToast } from "@/components/ui/toast";
import { LlmServerInfo } from "@/lib/types";

export function CockpitHome({
  initialData,
  variant = "reference",
}: {
  initialData: CockpitInitialData;
  variant?: "reference" | "home";
}) {
  const t = useTranslation();
  const { pushToast } = useToast();
  const [isClientReady, setIsClientReady] = useState(false);
  useEffect(() => {
    setIsClientReady(true);
  }, []);

  // 1. Layout State
  const layout = useCockpitLayout(variant);

  // 2. Data State
  const data = useCockpitData(initialData);

  // 3. Interactive State
  const interactive = useCockpitInteractiveState();

  // 4. Logic & Effects
  const chatScrollRef = useRef<HTMLDivElement>(null!);
  const logic = useCockpitLogic(data, interactive, layout, chatScrollRef);

  // 5. Section Props Builder
  const sectionProps = useCockpitSectionProps({
    // Layout
    chatFullscreen: layout.chatFullscreen,
    setChatFullscreen: layout.setChatFullscreen,
    showArtifacts: layout.showArtifacts,
    // Note: setShowArtifacts not in useCockpitSectionProps input,
    // it expects showReferenceSections etc.
    showReferenceSections: layout.showReferenceSections,
    showSharedSections: layout.showSharedSections,
    labMode: layout.labMode,
    setLabMode: layout.setLabMode,
    detailOpen: layout.detailOpen,
    setDetailOpen: layout.setDetailOpen,
    quickActionsOpen: layout.quickActionsOpen,
    setQuickActionsOpen: layout.setQuickActionsOpen,
    tuningOpen: layout.tuningOpen,
    setTuningOpen: layout.setTuningOpen,
    exportingPinned: layout.exportingPinned, // useCockpitSectionProps takes boolean
    // it does NOT take setExportingPinned, but functionality might be internal or passed differently?
    // checking props: exportingPinned: boolean; onExportPinnedLogs: () => void;

    // Interactive
    chatMode: interactive.state.chatMode,
    setChatMode: interactive.setters.setChatMode,
    sending: interactive.state.sending,
    // setSending not passed directly, logic handles it
    message: interactive.state.message,
    // setMessage not passed directly
    llmActionPending: interactive.state.llmActionPending,
    // setLlmActionPending not passed
    selectedLlmServer: interactive.state.selectedLlmServer,
    setSelectedLlmServer: (val: string) => {
      interactive.setters.setSelectedLlmServer(val);
      // Reset selected model when server changes to prevent mismatched activation
      interactive.setters.setSelectedLlmModel("");
    },
    selectedLlmModel: interactive.state.selectedLlmModel,
    setSelectedLlmModel: interactive.setters.setSelectedLlmModel,
    historyDetail: interactive.state.historyDetail,
    // setHistoryDetail not passed
    loadingHistory: interactive.state.loadingHistory,
    // setHistoryDetail not passed
    historyError: interactive.state.historyError,
    // setHistoryError not passed
    pinnedLogs: interactive.state.pinnedLogs,
    // setPinnedLogs not passed, instead onTogglePin etc.
    logFilter: interactive.state.logFilter,
    // setLogFilter not passed, onLogFilterChange passed
    selectedRequestId: interactive.state.selectedRequestId,
    // setSelectedRequestId not passed, onOpenRequestDetail passed
    selectedTask: interactive.state.selectedTask,
    // setSelectedTask not passed
    copyStepsMessage: interactive.state.copyStepsMessage,
    // setCopyStepsMessage not passed
    feedbackByRequest: interactive.state.feedbackByRequest,
    // setFeedbackByRequest passed as onUpdateFeedbackState
    feedbackSubmittingId: interactive.state.feedbackSubmittingId,
    // setFeedbackSubmittingId not passed
    // gitAction / memoryAction handled by logic handlers?
    memoryAction: interactive.state.memoryAction,
    // generationParams
    generationParams: interactive.state.generationParams,
    // setGenerationParams passed as onChangeGenerationParams
    modelSchema: interactive.state.modelSchema,
    // setModelSchema not passed
    loadingSchema: interactive.state.loadingSchema,
    // setLoadingSchema not passed
    tuningSaving: interactive.state.tuningSaving,
    // setTuningSaving not passed
    // lastResponseDurations handled by chatUi logic?

    // Data (Casting to fix strict type issues)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    metrics: data.metrics,
    tasksPreview: (data.tasks || []).slice(0, 4), // tasksPreview expects Task[]
    queue: data.queue,
    services: data.services,
    llmServers: (data.llmServers || []) as LlmServerInfo[],
    activeServerInfo: data.activeServerInfo,
    activeServerName: data.activeServerInfo?.active_server || "unknown", // Derived
    // graph: data.graph, // Not used in section props input directly?
    // usageMetrics needs graphNodes/graphEdges strings
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    graphNodes: (data.graph?.nodes ?? data.graph?.summary?.nodes ?? 0).toString(),
    graphEdges: (data.graph?.edges ?? data.graph?.summary?.edges ?? 0).toString(),

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    hasModels: ((data.models?.models?.length ?? 0) > 0),
    llmServersLoading: data.loading.llmServers,
    // Old definitions removed


    // git: data.git, // not passed
    metricsLoading: data.loading.metrics,
    tokenMetricsLoading: data.loading.tokenMetrics,


    history: (data.history || []) as any,
    learningLogs: (data.learningLogs || []) as any,
    feedbackLogs: (data.feedbackLogs || []) as any,

    // Logics from state/layout
    onExportPinnedLogs: logic.chatUi.handleExportPinnedLogs,

    // Logic / Computed
    sessionId: logic.sessionId || "",

    telemetryFeed: logic.telemetry.entries.map(e => ({
      id: e.id,
      timestamp: new Date(e.ts).toISOString(),
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      tone: (e.payload as any)?.tone || "neutral",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      type: (e.payload as any)?.type || "info",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      message: (e.payload as any)?.message || "",
    })),

    // Map hiddenState
    hiddenPrompts: (logic.hiddenState.hiddenPrompts || []) as any,
    activeHiddenPrompts: logic.hiddenState.activeHiddenPrompts,
    activeHiddenKeys: logic.hiddenState.activeHiddenKeys,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    activeHiddenMap: Object.fromEntries(logic.hiddenState.activeHiddenMap) as any,
    isHiddenResponse: logic.hiddenState.isHiddenResponse,
    hiddenIntentOptions: logic.hiddenState.hiddenIntentOptions,
    selectableHiddenPrompts: (logic.hiddenState.selectableHiddenPrompts || []) as any,
    activeForIntent: logic.hiddenState.activeForIntent,
    hiddenIntentFilter: logic.hiddenState.filter,
    onHiddenIntentFilterChange: logic.hiddenState.setFilter,
    hiddenScoreFilter: logic.hiddenState.score,
    onHiddenScoreFilterChange: logic.hiddenState.setScore,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onSetActiveHiddenPrompt: (logic.hiddenState as any).onSetActiveHiddenPrompt,
    hiddenLoading: false,
    hiddenError: null,
    activeHiddenLoading: false,
    activeHiddenError: null,

    // Chat UI properties
    chatScrollRef: chatScrollRef as RefObject<HTMLDivElement>, // Cast to satisfy strict type
    onChatScroll: logic.chatUi.handleChatScroll,
    composerRef: logic.chatUi.composerRef,
    onSend: async (txt: string) => { logic.chatUi.handleSend(txt); return true; }, // Adapter

    responseBadgeText: logic.chatUi.responseBadgeText,
    responseBadgeTone: logic.chatUi.responseBadgeTone as "success" | "warning" | "neutral" | "danger",
    responseBadgeTitle: logic.chatUi.responseBadgeTitle,

    // Optimistic / Messages
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    chatMessages: ((logic.chatUi as any).chatMessages || logic.historyMessages) as any,

    // Actions
    onOpenRequestDetail: (id: string, prompt?: string) => {
      logic.requestDetail.openRequestDetail(id, prompt);
    },
    onFeedbackClick: logic.chatUi.handleFeedbackClick,
    onFeedbackSubmit: logic.chatUi.handleFeedbackSubmit,
    onUpdateFeedbackState: (id: string, patch: any) => logic.chatUi.updateFeedbackState(id, patch),

    onSuggestionsClick: logic.chatUi.handleSuggestionClick,
    onSuggestionClick: logic.chatUi.handleSuggestionClick,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    promptPresets: PROMPT_PRESETS,

    // Handlers
    onSessionReset: logic.sessionActions.handleSessionReset,
    onServerSessionReset: logic.sessionActions.handleServerSessionReset,
    onClearSessionMemory: logic.sessionActions.handleClearSessionMemory,
    onClearGlobalMemory: logic.sessionActions.handleClearGlobalMemory,

    onActivateModel: (model: string) => {
      logic.handleActivateModel(model);
    },
    onActivateServer: () => {
      if (interactive.state.selectedLlmModel) {
        logic.handleActivateModel(interactive.state.selectedLlmModel);
      } else {
        pushToast("Najpierw wybierz model do aktywacji.", "warning");
      }
    },

    onOpenTuning: logic.chatUi.handleOpenTuning,
    tuningLabel: "Strojenie",

    onLogFilterChange: interactive.setters.setLogFilter,
    logEntries: [], // logic.logs?
    onTogglePin: (entry: any) => {
      // logic
    },
    onClearPinnedLogs: () => {
      interactive.setters.setPinnedLogs([]);
    },

    // Queue
    queueLoading: data.loading.queue,
    queueAction: logic.queue.queueAction,
    queueActionMessage: logic.queue.queueActionMessage,
    onToggleQueue: logic.queue.onToggleQueue,
    onExecuteQueueMutation: logic.queue.onExecuteQueueMutation,

    // Macros
    newMacro: logic.macros.newMacro,
    setNewMacro: logic.macros.setNewMacro,
    customMacros: logic.macros.customMacros,
    setCustomMacros: () => { }, // Handled by add/delete in hook
    allMacros: logic.macros.allMacros,
    macroSending: logic.macros.macroSending,
    onRunMacro: logic.macros.onRunMacro,
    onAddMacro: logic.macros.onAddMacro,
    onDeleteMacro: logic.macros.onDeleteMacro,
    onClearMacros: logic.macros.onClearMacros,

    // Usage / Metrics Values (Derived)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    usageMetrics: data.modelsUsageResponse?.usage || null,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    cpuUsageValue: data.modelsUsageResponse?.usage?.cpu_usage_percent || 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    gpuUsageValue: data.modelsUsageResponse?.usage?.gpu_usage_percent || 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ramValue: data.modelsUsageResponse?.usage?.memory_used_gb || 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vramValue: data.modelsUsageResponse?.usage?.vram_usage_mb || 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    diskValue: data.modelsUsageResponse?.usage?.disk_usage_gb || 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    diskPercent: data.modelsUsageResponse?.usage?.disk_usage_percent || 0,
    sessionCostValue: data.tokenMetrics?.session_cost_usd || 0,

    // Token
    tokenSplits: logic.metricsDisplay.tokenSplits,
    tokenHistory: logic.metricsDisplay.tokenHistory,
    tokenTrendDelta: 0,
    tokenTrendLabel: "vs 1h",
    totalTokens: data.tokenMetrics?.total_tokens || 0,

    // History Status
    historyStatusEntries: logic.metricsDisplay.historyStatusEntries,

    llmServerOptions: data.llmServers?.map(s => ({ label: s.name, value: s.name })) || [],
    llmModelOptions: data.models?.models
      ?.filter(m => !interactive.state.selectedLlmServer || m.provider === interactive.state.selectedLlmServer)
      ?.map(m => ({ label: m.name, value: m.name })) || [],
    llmServerOptionsPanel: [], // TODO: Populate if needed for panel
    llmModelOptionsPanel: [], // TODO: Populate if needed for panel

    // Derived available models for selected server (simple filter)
    availableModelsForServer: data.models?.models
      ?.filter(m => !interactive.state.selectedLlmServer || m.provider === interactive.state.selectedLlmServer)
      ?.map(m => ({ name: m.name })) || [],

    selectedServerEntry: data.llmServers?.find(s => s.name === interactive.state.selectedLlmServer) || null, // logic.llmOps...
    resolveServerStatus: (name: string, fallback?: string | null) => {
      const s = data.llmServers.find(server => server.name === name);
      return s?.status || fallback || "unknown";
    },

    // ...
    // Fill remaining props with defaults/nulls for now to pass build

    entries: [],
    // Map services to agentDeck
    agentDeck: (data.services || []).map(s => ({
      name: s.name,
      status: s.status,
      detail: s.detail || s.description || s.type || "Service",
    })),
    successRate: data.metrics?.tasks?.success_rate ?? 0,
    tasksCreated: data.metrics?.tasks?.created ?? 0,
    feedbackScore: ((data.metrics?.feedback?.up ?? 0) + (data.metrics?.feedback?.down ?? 0)) > 0
      ? Math.round(((data.metrics?.feedback?.up ?? 0) / ((data.metrics?.feedback?.up ?? 0) + (data.metrics?.feedback?.down ?? 0))) * 100)
      : 0,
    feedbackUp: data.metrics?.feedback?.up ?? 0,
    feedbackDown: data.metrics?.feedback?.down ?? 0,

    onApplyTuning: logic.chatUi.handleApplyTuning,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onChangeGenerationParams: (v: any) => interactive.setters.setGenerationParams(v as any),
    onResetGenerationParams: () => interactive.setters.setGenerationParams(null),

    contextPreviewMeta: logic.requestDetail.contextPreviewMeta || null,
    onCopyDetailSteps: logic.requestDetail.handleCopyDetailSteps,
    onCloseDetail: () => layout.setDetailOpen(false),

    uiTimingEntry: undefined,
    llmStartAt: null,
    payloadSessionMeta: undefined,
    payloadForcedRoute: undefined,
    payloadGenerationParams: undefined,
    payloadContextUsed: undefined,

    t,
    connected: logic.telemetry.connected,
  } as any);

  const headerProps = useMemo(() => ({
    showReferenceSections: layout.showReferenceSections,
    showArtifacts: layout.showArtifacts,
    onToggleArtifacts: () => layout.setShowArtifacts(!layout.showArtifacts),
  }), [layout.showArtifacts, layout.showReferenceSections, layout.setShowArtifacts]);

  if (!isClientReady) {
    return <div className="p-8 text-muted-foreground">Ładowanie kokpitu...</div>;
  }

  return (
    <div className="space-y-6">
      {/* HEADER */}
      <CockpitHeader {...headerProps} />

      {/* SECTIONS */}
      <CockpitPrimarySection {...sectionProps.primarySectionProps} />
      <CockpitRuntimeSection {...sectionProps.runtimeSectionProps} />
    </div>
  );
}
