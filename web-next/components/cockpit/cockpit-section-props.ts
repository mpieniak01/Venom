"use client";

import { createElement, useMemo, useCallback } from "react";
import type {
  ServiceStatus,
  HistoryRequest,
  GenerationParams,
  ContextUsed,
  LlmRuntimeModelOption,
} from "@/lib/types";
import type { LogEntryType } from "@/lib/logs";
import { CockpitHiddenPromptsPanel } from "@/components/cockpit/cockpit-hidden-prompts-panel";
import { useCockpitRuntimeSectionProps } from "@/components/cockpit/cockpit-runtime-props";
import { PROMPT_PRESETS } from "@/components/cockpit/cockpit-prompts";
import { useTranslation } from "@/lib/i18n";
import { useCockpitContext } from "@/components/cockpit/cockpit-context";
import { mapTelemetryTone, type TelemetryFeedEntry } from "@/components/cockpit/cockpit-utils";
import { setActiveLlmServer } from "@/hooks/use-api";
import { filterRuntimeBaseModels } from "@/lib/runtime-model-filters";
import { normalizeRuntimeId } from "@/lib/cockpit-runtime-selection";



export function formatRuntimeModelOptionLabel(
  model: Pick<
    LlmRuntimeModelOption,
    "name" | "feedback_loop_tier" | "canonical_model_id"
  > & {
    runtime_id?: string;
  },
  t: (key: string) => string,
): string {
  const runtimeLabel = model.runtime_id ? ` [${model.runtime_id}]` : "";
  const canonicalAlias = model.canonical_model_id ?? null;
  const aliasSuffix =
    canonicalAlias && canonicalAlias.toLowerCase() !== model.name.toLowerCase()
      ? ` <-> ${canonicalAlias}`
      : "";
  const baseLabel = `${model.name}${aliasSuffix}${runtimeLabel}`;
  if (model.feedback_loop_tier === "primary") {
    return `${baseLabel} · ${t("cockpit.models.feedbackLoopPrimaryBadge")}`;
  }
  if (model.feedback_loop_tier === "fallback") {
    return `${baseLabel} · ${t("cockpit.models.feedbackLoopFallbackBadge")}`;
  }
  return baseLabel;
}


export function useCockpitSectionProps() {
  const { data, interactive, layout, logic, chatScrollRef } = useCockpitContext();
  const t = useTranslation();

  const {
    chatFullscreen,
    setChatFullscreen,
    showArtifacts,
    showReferenceSections,
    showSharedSections,
    labMode,
    setLabMode,
    detailOpen,
    setDetailOpen,
    quickActionsOpen,
    setQuickActionsOpen,
    tuningOpen,
    setTuningOpen,
    exportingPinned,
  } = layout;

  const {
    state: {
      chatMode,
      sending,
      message,
      llmActionPending,
      selectedLlmServer,
      selectedLlmModel,
      historyDetail,
      loadingHistory: historyLoading,
      historyError,
      pinnedLogs,
      logFilter,
      selectedRequestId,
      selectedTask,
      copyStepsMessage,
      feedbackByRequest,
      feedbackSubmittingId,
      generationParams,
      modelSchema,
      loadingSchema,
      tuningSaving,
    },
    setters: {
      setChatMode,
      setSelectedLlmServer,
      setSelectedLlmModel,
    },
  } = interactive;

  const onOpenRequestDetail = logic.requestDetail.openRequestDetail;
  const onFeedbackClick = logic.chatUi.handleFeedbackClick;
  const onFeedbackSubmit = logic.chatUi.handleFeedbackSubmit;
  const onUpdateFeedbackState = logic.chatUi.updateFeedbackState;
  const onChangeGenerationParams = useCallback((vals: Record<string, unknown>) => {
    // Validate and convert unknown values to GenerationParams
    // Only accept primitive types that GenerationParams expects
    const params: Partial<GenerationParams> = {};
    for (const [key, value] of Object.entries(vals)) {
      const valueType = typeof value;
      if (valueType === 'number' || valueType === 'string' || valueType === 'boolean') {
        params[key as keyof GenerationParams] = value as number | string | boolean;
      }
    }
    interactive.setters.setGenerationParams(params);
  }, [interactive.setters]);
  const handleActivateModel = logic.handleActivateModel;

  const composerRef = logic.chatUi.composerRef;
  const onSend = useCallback(
    async (txt: string) => {
      return await logic.chatUi.handleSend(txt);
    },
    [logic.chatUi],
  );
  const onActivateModel = useCallback(
    async (model: string) => handleActivateModel(model),
    [handleActivateModel],
  );
  const handleSelectLlmServer = useCallback(
    (value: string) => {
      const normalizedValue = normalizeRuntimeId(value);
      const normalizedSelected = normalizeRuntimeId(selectedLlmServer);
      if (!normalizedValue || normalizedValue === normalizedSelected) {
        return;
      }
      setSelectedLlmServer(value.trim());
      setSelectedLlmModel("");
    },
    [selectedLlmServer, setSelectedLlmModel, setSelectedLlmServer],
  );

  const runtimeTargets = useMemo(
    () => data.unifiedModelCatalog?.runtimes ?? [],
    [data.unifiedModelCatalog],
  );
  const normalizedSelectedLlmServer = useMemo(
    () => normalizeRuntimeId(selectedLlmServer),
    [selectedLlmServer],
  );
  const llmServerOptions = useMemo(
    () => runtimeTargets.map((runtime) => ({ label: runtime.runtime_id, value: runtime.runtime_id })),
    [runtimeTargets],
  );
  const resolvedServerId = normalizeRuntimeId(
    normalizedSelectedLlmServer ||
      data.activeServerInfo?.active_server ||
      data.unifiedModelCatalog?.active?.active_server ||
      "",
  );
  const activeRuntimeModel = useMemo(
    () =>
      (
        data.activeServerInfo?.active_model ||
        data.unifiedModelCatalog?.active?.active_model ||
        ""
      ).trim(),
    [data.activeServerInfo?.active_model, data.unifiedModelCatalog?.active?.active_model],
  );
  const selectedRuntimeModels = useMemo(() => {
    if (!resolvedServerId) return [];
    const target = runtimeTargets.find(
      (runtime) => normalizeRuntimeId(runtime.runtime_id) === resolvedServerId,
    );
    return filterRuntimeBaseModels(
      (target?.models ?? []).filter((model) => model.chat_compatible !== false),
    );
  }, [resolvedServerId, runtimeTargets]);
  const selectedRuntimeTarget = useMemo(
    () =>
      runtimeTargets.find(
        (runtime) => normalizeRuntimeId(runtime.runtime_id) === resolvedServerId,
      ) ?? null,
    [resolvedServerId, runtimeTargets],
  );
  const adapterDeploySupported = Boolean(
    selectedRuntimeTarget?.supports_adapter_runtime_apply ??
      selectedRuntimeTarget?.adapter_deploy_supported,
  );
  const adapterDeployReason = adapterDeploySupported
    ? null
    : t("cockpit.models.adapterRuntimeNotSupported", { runtime: resolvedServerId || "unknown" });
  const modelAuditIssuesCount = Number(
    data.unifiedModelCatalog?.model_audit?.issues_count ?? 0,
  );
  const llmModelOptions = useMemo(
    () => {
      const options = selectedRuntimeModels.map((model) => ({
        label: formatRuntimeModelOptionLabel(model, t),
        value: model.name,
      }));
      options.unshift({
        label: t("cockpit.models.noneSelected"),
        value: "__none__",
      });
      const selected = (selectedLlmModel || "").trim();
      if (selected && !options.some((option) => option.value === selected)) {
        options.unshift({
          label: selected,
          value: selected,
        });
      }
      return options;
    },
    [selectedLlmModel, selectedRuntimeModels, t],
  );
  const llmModelMetadata = useMemo(
    () => {
      const metadata = selectedRuntimeModels.reduce<
        Record<string, { canonical_model_id?: string | null }>
      >((acc, model) => {
        acc[model.name] = { canonical_model_id: model.canonical_model_id ?? null };
        return acc;
      }, {});
      const selected = (selectedLlmModel || "").trim();
      if (selected && !metadata[selected]) {
        metadata[selected] = { canonical_model_id: selected };
      }
      return metadata;
    },
    [selectedLlmModel, selectedRuntimeModels],
  );
  const hasModels = useMemo(
    () => llmModelOptions.length > 0,
    [llmModelOptions],
  );

  const onOpenTuning = logic.chatUi.handleOpenTuning;
  const tuningLabel = t("common.tuning");

  const onSuggestionClick = logic.chatUi.handleSuggestionClick;
  const onNewChat = logic.sessionActions.handleServerSessionReset;

  const llmServersLoading = data.loading.llmServers;
  const llmServers = useMemo(() => data.llmServers || [], [data.llmServers]);
  const llmServerOptionsPanel = llmServerOptions;
  const llmModelOptionsPanel = llmModelOptions;

  const availableModelsForServer = useMemo(
    () => selectedRuntimeModels.map((model) => ({ name: model.name, provider: model.provider })),
    [selectedRuntimeModels],
  );

  const selectedServerEntry = useMemo(
    () =>
      data.llmServers?.find(
        (s) => normalizeRuntimeId(s.name) === normalizedSelectedLlmServer,
      ) || null,
    [data.llmServers, normalizedSelectedLlmServer],
  );

  const resolveServerStatus = useCallback((name?: string, fallback?: string | null) => {
    const runtimeMatch = runtimeTargets.find(
      (runtime) => normalizeRuntimeId(runtime.runtime_id) === normalizeRuntimeId(name),
    );
    if (runtimeMatch?.status) return runtimeMatch.status;
    const s = data.llmServers.find(
      (server) => normalizeRuntimeId(server.name) === normalizeRuntimeId(name),
    );
    return s?.status || fallback || "unknown";
  }, [data.llmServers, runtimeTargets]);

  const sessionId = logic.sessionId || "";
  const memoryAction = interactive.state.memoryAction;

  const onSessionReset = logic.sessionActions.handleSessionReset;
  const onServerSessionReset = logic.sessionActions.handleServerSessionReset;
  const onClearSessionMemory = logic.sessionActions.handleClearSessionMemory;
  const onClearGlobalMemory = logic.sessionActions.handleClearGlobalMemory;

  const activeServerInfo = data.activeServerInfo;
  const activeServerName = data.activeServerInfo?.active_server || "unknown";

  const onActivateServer = useCallback(() => {
    const selectedServer = (selectedRuntimeTarget?.runtime_id || interactive.state.selectedLlmServer || "").trim();
    const selectedModel = interactive.state.selectedLlmModel;
    if (!selectedServer) return;
    if (availableModelsForServer.length > 0 && !selectedModel) {
      interactive.setters.setMessage(t("cockpit.chatMessages.modelSelectionRequired"));
      return;
    }

    if (selectedModel) {
      handleActivateModel(selectedModel).catch((error) => {
        const message =
          error instanceof Error ? error.message : "Nie udało się aktywować modelu.";
        interactive.setters.setMessage(message);
      });
      return;
    }

    const activateServerOnly = async () => {
      try {
        interactive.setters.setLlmActionPending(`activate:${selectedServer}`);
        await setActiveLlmServer(selectedServer);
        interactive.setters.setMessage(`Aktywowano serwer ${selectedServer}.`);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Nie udało się aktywować serwera.";
        interactive.setters.setMessage(message);
      } finally {
        interactive.setters.setLlmActionPending(null);
        data.refresh.llmServers();
        data.refresh.activeServer();
        data.refresh.models();
      }
    };
    activateServerOnly().catch((error) => {
      const message =
        error instanceof Error ? error.message : "Nie udało się aktywować serwera.";
      interactive.setters.setMessage(message);
    });
  }, [
    availableModelsForServer.length,
    data.refresh,
    handleActivateModel,
    interactive.state.selectedLlmModel,
    interactive.state.selectedLlmServer,
    interactive.setters,
    selectedRuntimeTarget?.runtime_id,
    t,
  ]);

  const connected = logic.telemetry.connected;

  const onLogFilterChange = interactive.setters.setLogFilter;
  const logEntries = logic.telemetry.entries;
  const onTogglePin = useCallback((entry: LogEntryType) => {
    interactive.setters.setPinnedLogs((prev: LogEntryType[]) => {
      if (prev.some(e => e.id === entry.id)) {
        return prev.filter(e => e.id !== entry.id);
      }
      return [...prev, entry];
    });
  }, [interactive.setters]);
  const onExportPinnedLogs = logic.chatUi.handleExportPinnedLogs;
  const onClearPinnedLogs = useMemo(() => () => interactive.setters.setPinnedLogs([]), [interactive.setters]);

  const tasksPreview = (data.tasks || []).slice(0, 4);

  const hiddenScoreFilter = logic.hiddenState.score;
  const hiddenIntentFilter = logic.hiddenState.filter;
  const onHiddenIntentFilterChange = logic.hiddenState.setFilter;
  const onHiddenScoreFilterChange = logic.hiddenState.setScore;
  const hiddenIntentOptions = logic.hiddenState.hiddenIntentOptions;
  const selectableHiddenPrompts = useMemo(() => logic.hiddenState.selectableHiddenPrompts || [], [logic.hiddenState.selectableHiddenPrompts]);
  const activeHiddenKeys = logic.hiddenState.activeHiddenKeys;
  const activeHiddenMap = logic.hiddenState.activeHiddenMap;
  const activeForIntent = logic.hiddenState.activeForIntent || null;
  const hiddenPrompts = logic.hiddenState.hiddenPrompts || null;
  const hiddenLoading = false;
  const hiddenError = null;
  const activeHiddenLoading = false;
  const activeHiddenError = null;
  const onSetActiveHiddenPrompt = logic.hiddenState.onSetActiveHiddenPrompt;

  const history = useMemo(() => data.history || [], [data.history]);

  const metrics = data.metrics;
  const metricsLoading = data.loading.metrics;
  const successRate = data.metrics?.tasks?.success_rate ?? 0;
  const tasksCreated = data.metrics?.tasks?.created ?? 0;
  const queue = data.queue;
  const feedbackScore = ((data.metrics?.feedback?.up ?? 0) + (data.metrics?.feedback?.down ?? 0)) > 0
    ? Math.round(((data.metrics?.feedback?.up ?? 0) / ((data.metrics?.feedback?.up ?? 0) + (data.metrics?.feedback?.down ?? 0))) * 100)
    : 0;
  const feedbackUp = data.metrics?.feedback?.up ?? 0;
  const feedbackDown = data.metrics?.feedback?.down ?? 0;

  const tokenMetricsLoading = data.loading.tokenMetrics;
  const tokenSplits = logic.metricsDisplay.tokenSplits;
  const tokenHistory = logic.metricsDisplay.tokenHistory;
  const tokenTrendDelta = 0;
  const tokenTrendLabel = "vs 1h";
  const totalTokens = data.tokenMetrics?.total_tokens || 0;

  const telemetryFeed = useMemo<TelemetryFeedEntry[]>(() => {
    const isTelemetryTone = (
      value: unknown,
    ): value is TelemetryFeedEntry["tone"] =>
      value === "success" || value === "warning" || value === "danger" || value === "neutral";

    return logic.telemetry.entries.map((e) => {
      const payload = e.payload as Record<string, unknown> | undefined;
      const type = typeof payload?.type === "string" ? payload.type : "info";
      const rawTone = payload?.tone;
      return {
        id: e.id,
        timestamp: new Date(e.ts).toISOString(),
        tone: isTelemetryTone(rawTone) ? rawTone : mapTelemetryTone(type),
        type,
        message: typeof payload?.message === "string" ? payload.message : "",
      };
    });
  }, [logic.telemetry.entries]);

  const usageMetrics = data.modelsUsageResponse?.usage || null;
  const cpuUsageValue = data.modelsUsageResponse?.usage?.cpu_usage_percent || 0;
  const gpuUsageValue = data.modelsUsageResponse?.usage?.gpu_usage_percent || 0;
  const ramValue = data.modelsUsageResponse?.usage?.memory_used_gb || 0;
  const vramValue = data.modelsUsageResponse?.usage?.vram_usage_mb || 0;
  const diskValue = data.modelsUsageResponse?.usage?.disk_usage_gb || 0;
  const diskPercent = data.modelsUsageResponse?.usage?.disk_usage_percent || 0;
  const sessionCostValue = data.tokenMetrics?.session_cost_usd || 0;
  const graphNodes = (data.graph?.nodes ?? data.graph?.summary?.nodes ?? 0).toString();
  const graphEdges = (data.graph?.edges ?? data.graph?.summary?.edges ?? 0).toString();

  const agentDeck = (data.services || []).map(s => ({
    label: s.name,
    value: s.detail || s.description || s.type || "Service",
  }));

  const queueLoading = data.loading.queue;
  const queueAction = logic.queue.queueAction;
  const queueActionMessage = logic.queue.queueActionMessage;
  const onToggleQueue = logic.queue.onToggleQueue;
  const onExecuteQueueMutation = logic.queue.onExecuteQueueMutation;

  const historyStatusEntries = logic.metricsDisplay.historyStatusEntries;

  const learningLogs = data.learningLogs || null;
  const learningLoading = data.loading.learning;
  const learningError = null;

  const feedbackLogs = data.feedbackLogs || null;
  const feedbackLoading = data.loading.feedback;
  const feedbackError = null;

  const services = data.services || [];
  const entries = logic.telemetry.entries;

  const {
    newMacro,
    setNewMacro,
    customMacros,
    allMacros,
    macroSending,
    onRunMacro,
    setCustomMacros,
  } = logic.macros;

  const onCloseDetail = () => setDetailOpen(false);

  const uiTimingEntry = undefined;
  const llmStartAt = null;
  const payloadSessionMeta = undefined;
  const payloadForcedRoute = undefined;
  const payloadGenerationParams = undefined;
  const payloadContextUsed = historyDetail?.context_used as ContextUsed | undefined;

  const contextPreviewMeta = logic.requestDetail.contextPreviewMeta || null;
  const onCopyDetailSteps = logic.requestDetail.handleCopyDetailSteps;

  const detailFeedbackByRequest = feedbackByRequest;
  const detailFeedbackSubmittingId = feedbackSubmittingId;
  const onFeedbackSubmitDetail = onFeedbackSubmit;

  // note: CockpitHome used const t = useTranslation();
  // We can import it here as we are a hook.

  const onResetGenerationParams = () => interactive.setters.setGenerationParams(null);
  const onApplyTuning = logic.chatUi.handleApplyTuning;

  const responseBadgeTone = logic.chatUi.responseBadgeTone;
  const responseBadgeTitle = logic.chatUi.responseBadgeTitle;
  const responseBadgeText = logic.chatUi.responseBadgeText;
  const chatMessages = logic.chatUi.chatMessages || logic.historyMessages;
  const onChatScroll = logic.chatUi.handleChatScroll;
  const promptPresets = useMemo(() => PROMPT_PRESETS.map(p => ({
    id: p.id,
    category: t(p.categoryKey),
    description: t(p.descriptionKey),
    prompt: t(p.promptKey),
    icon: p.icon,
  })), [t]);

  // --- Sub-props construction ---

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
    selectedLlmServer: normalizedSelectedLlmServer,
    llmServerOptions,
    setSelectedLlmServer: handleSelectLlmServer,
    selectedLlmModel,
    activeRuntimeModel,
    llmModelOptions,
    llmModelMetadata,
    setSelectedLlmModel,
    onActivateModel,
    hasModels,
    onOpenTuning,
    tuningLabel,
    adapterDeploySupported,
    adapterDeployReason,
    modelAuditIssuesCount,
    compactControls: chatFullscreen,
  }), [
    adapterDeployReason,
    adapterDeploySupported,
    modelAuditIssuesCount,
    chatFullscreen,
    chatMode,
    composerRef,
    hasModels,
    labMode,
    llmModelOptions,
    llmModelMetadata,
    llmServerOptions,
    onActivateModel,
    onOpenTuning,
    onSend,
    handleSelectLlmServer,
    selectedLlmModel,
    activeRuntimeModel,
    normalizedSelectedLlmServer,
    sending,
    setChatMode,
    setLabMode,
    setSelectedLlmModel,
    tuningLabel,
  ]);

  const llmOpsPanelProps = useMemo(() => ({
    llmServersLoading,
    llmServers,
    selectedLlmServer: normalizedSelectedLlmServer,
    llmServerOptions: llmServerOptionsPanel,
    onSelectLlmServer: handleSelectLlmServer,
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
    handleSelectLlmServer,
    selectedLlmModel,
    normalizedSelectedLlmServer,
    selectedServerEntry,
    setSelectedLlmModel,
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
    history: history,
    selectedRequestId,
    onSelect: (entry: HistoryRequest) =>
      onOpenRequestDetail(entry.request_id, entry.prompt),
    loadingHistory: historyLoading,
    historyError,
  }), [
    history,
    historyError,
    historyLoading,
    onOpenRequestDetail,
    selectedRequestId,
  ]);

  const metricsProps = useMemo(() => ({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    metrics: metrics as any,
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
      graphNodes: typeof graphNodes === 'string' ? Number.parseInt(graphNodes, 10) || 0 : graphNodes,
      graphEdges: typeof graphEdges === 'string' ? Number.parseInt(graphEdges, 10) || 0 : graphEdges,
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
      loadingHistory: historyLoading,
      historyError,
      learningLogs,
      learningLoading,
      learningError,
      feedbackLogs,
      feedbackLoading,
      feedbackError,
      hiddenPromptsPanel: createElement(CockpitHiddenPromptsPanel, hiddenPromptsPanelProps),
      services: services.map(s => typeof s.status === 'string' ? { name: s.name, status: s.status } as ServiceStatus : s.status),
      entries: entries.map(e => ({ id: e.id, payload: e.payload, ts: e.ts })),
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
      loadingHistory: historyLoading,
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
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onFeedbackSubmit: onFeedbackSubmitDetail as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onUpdateFeedbackState: onUpdateFeedbackState as any,
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
    onNewChat,
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
    onNewChat,
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
