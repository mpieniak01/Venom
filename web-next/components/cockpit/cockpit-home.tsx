"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { ListCard } from "@/components/ui/list-card";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel, StatCard } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { MarkdownPreview } from "@/components/ui/markdown";
import { ConversationBubble } from "@/components/cockpit/conversation-bubble";
import { MacroCard, PinnedLogCard } from "@/components/cockpit/macro-card";
import { RepoActionCard } from "@/components/cockpit/model-card";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  emergencyStop,
  fetchHistoryDetail,
  fetchModelConfig,
  fetchTaskDetail,
  gitSync,
  gitUndo,
  purgeQueue,
  sendTask,
  sendFeedback,
  setActiveHiddenPrompt,
  setActiveLlmServer,
  updateModelConfig,
  switchModel,
  toggleQueue,
  useGitStatus,
  useFeedbackLogs,
  useActiveHiddenPrompts,
  useActiveLlmServer,
  useGraphSummary,
  useHistory,
  useHiddenPrompts,
  useLlmServers,
  useLearningLogs,
  useMetrics,
  useModels,
  useModelsUsage,
  useQueueStatus,
  useServiceStatus,
  useTasks,
  useTokenMetrics,
} from "@/hooks/use-api";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { useTaskStream } from "@/hooks/use-task-stream";
import { useToast } from "@/components/ui/toast";
import type { Chart } from "chart.js/auto";
import {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import type { KeyboardEvent } from "react";
import type {
  GenerationParams,
  HistoryRequestDetail,
  HiddenPromptEntry,
  ServiceStatus,
  Task,
} from "@/lib/types";
import type { CockpitInitialData } from "@/lib/server-data";
import { LogEntryType, isLogPayload } from "@/lib/logs";
import { statusTone } from "@/lib/status";
import { formatRelativeTime } from "@/lib/date";
import { useTranslation } from "@/lib/i18n";
import { motion } from "framer-motion";
import { CockpitMetricCard, CockpitTokenCard } from "@/components/cockpit/kpi-card";
import {
  Bot,
  Command,
  Pin,
  PinOff,
  Inbox,
  Package,
  Maximize2,
  Minimize2,
  Settings,
  HelpCircle,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import Link from "next/link";
import { DynamicParameterForm, type GenerationSchema } from "@/components/ui/dynamic-parameter-form";
import { HistoryList } from "@/components/history/history-list";
import { TaskStatusBreakdown } from "@/components/tasks/task-status-breakdown";
import { RecentRequestList } from "@/components/tasks/recent-request-list";
import { QueueStatusCard } from "@/components/queue/queue-status-card";
import { QuickActions } from "@/components/layout/quick-actions";
import { VoiceCommandCenter } from "@/components/voice/voice-command-center";
import { IntegrationMatrix } from "@/components/cockpit/integration-matrix";
import { SelectMenu, type SelectMenuOption } from "@/components/ui/select-menu";
import {
  formatDiskSnapshot,
  formatGbPair,
  formatPercentMetric,
  formatUsd,
  formatVramMetric,
} from "@/lib/formatters";

const TELEMETRY_REFRESH_EVENTS = new Set([
  "AGENT_ACTION",
  "TASK_CREATED",
  "TASK_STARTED",
  "TASK_COMPLETED",
  "TASK_FAILED",
  "TASK_ABORTED",
  "QUEUE_PAUSED",
  "QUEUE_RESUMED",
  "QUEUE_PURGED",
  "EMERGENCY_STOP",
]);

type TelemetryEventPayload = {
  type?: string;
  data?: Record<string, unknown>;
  message?: string;
};

const isTelemetryEventPayload = (payload: unknown): payload is TelemetryEventPayload => {
  if (typeof payload !== "object" || payload === null) return false;
  const candidate = payload as { type?: unknown };
  return typeof candidate.type === "string";
};

type ChatComposerHandle = {
  setDraft: (value: string) => void;
};

type ChatComposerProps = {
  onSend: (payload: string) => Promise<boolean>;
  sending: boolean;
  labMode: boolean;
  setLabMode: (value: boolean) => void;
  selectedLlmServer: string;
  llmServerOptions: SelectMenuOption[];
  setSelectedLlmServer: (value: string) => void;
  selectedLlmModel: string;
  llmModelOptions: SelectMenuOption[];
  setSelectedLlmModel: (value: string) => void;
  hasModels: boolean;
  onOpenTuning: () => void;
  tuningLabel: string;
  compactControls?: boolean;
};

const ChatComposer = memo(
  forwardRef<ChatComposerHandle, ChatComposerProps>(function ChatComposer(
    {
      onSend,
      sending,
      labMode,
      setLabMode,
      selectedLlmServer,
      llmServerOptions,
      setSelectedLlmServer,
      selectedLlmModel,
      llmModelOptions,
      setSelectedLlmModel,
      hasModels,
      onOpenTuning,
      tuningLabel,
      compactControls = false,
    },
    ref,
  ) {
    const [draft, setDraft] = useState("");
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);

    useImperativeHandle(ref, () => ({
      setDraft: (value: string) => {
        setDraft(value);
        requestAnimationFrame(() => textareaRef.current?.focus());
      },
    }));

    const handleSendClick = useCallback(async () => {
      const ok = await onSend(draft);
      if (ok) {
        setDraft("");
      }
    }, [draft, onSend]);

    const handleTextareaKeyDown = useCallback(
      (event: KeyboardEvent<HTMLTextAreaElement>) => {
        const isEnter = event.key === "Enter";
        const isModifier = event.ctrlKey || event.metaKey;
        if (isEnter && isModifier) {
          event.preventDefault();
          handleSendClick();
        }
      },
      [handleSendClick],
    );

    const labelClassName = compactControls ? "sr-only" : "text-caption";
    const controlsWrapperClassName = compactControls
      ? "mt-3 flex flex-wrap items-end gap-3"
      : "mt-3 grid gap-3 md:grid-cols-2";
    const controlStackClassName = compactControls
      ? "flex min-w-[180px] flex-1 flex-col gap-2"
      : "space-y-2";

    return (
      <div className="mt-4 shrink-0 border-t border-white/5 pt-4">
        <textarea
          ref={textareaRef}
          rows={2}
          className="min-h-[72px] w-full rounded-2xl box-base p-3 text-sm text-white outline-none placeholder:text-zinc-500 focus:border-violet-500/60 2xl:text-base"
          placeholder="Opisz zadanie dla Venoma..."
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleTextareaKeyDown}
          data-testid="cockpit-prompt-input"
        />
        <div className={controlsWrapperClassName}>
          <div className={controlStackClassName}>
            <label className={labelClassName}>
              Serwer
            </label>
            <SelectMenu
              value={selectedLlmServer}
              options={llmServerOptions}
              onChange={setSelectedLlmServer}
              ariaLabel="Wybierz serwer LLM"
              placeholder="Wybierz serwer"
              buttonClassName="w-full justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white"
              menuClassName="w-full max-h-72 overflow-y-auto"
            />
          </div>
          <div className={controlStackClassName}>
            <label className={labelClassName}>
              Model
            </label>
            <SelectMenu
              value={selectedLlmModel}
              options={llmModelOptions}
              onChange={setSelectedLlmModel}
              ariaLabel="Wybierz model LLM (czat)"
              placeholder="Brak modeli"
              disabled={!hasModels}
              buttonClassName="w-full justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white"
              menuClassName="w-full max-h-72 overflow-y-auto"
            />
          </div>
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={labMode}
              onChange={(event) => setLabMode(event.target.checked)}
            />
            Lab Mode (nie zapisuj lekcji)
          </label>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onOpenTuning}
              className="border-emerald-400/40 bg-emerald-500/10 text-emerald-200 hover:border-emerald-300/70 hover:bg-emerald-500/20 hover:text-white"
              title="Dostosuj parametry generacji"
            >
              <Settings className="h-4 w-4 mr-1" />
              {tuningLabel}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDraft("")}
              className="text-zinc-300"
            >
              Wyczyść
            </Button>
            <Button
              onClick={handleSendClick}
              disabled={sending}
              size="sm"
              variant="macro"
              className="px-6"
              data-testid="cockpit-send-button"
            >
              {sending ? "Wysyłanie..." : "Wyślij"}
            </Button>
          </div>
        </div>
      </div>
    );
  }),
);

export function CockpitHome({ initialData }: { initialData: CockpitInitialData }) {
  const [isClientReady, setIsClientReady] = useState(false);
  useEffect(() => {
    setIsClientReady(true);
  }, []);
  const [labMode, setLabMode] = useState(false);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [llmActionPending, setLlmActionPending] = useState<string | null>(null);
  const [selectedLlmServer, setSelectedLlmServer] = useState("");
  const [selectedLlmModel, setSelectedLlmModel] = useState("");
  const [historyDetail, setHistoryDetail] = useState<HistoryRequestDetail | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [tokenHistory, setTokenHistory] = useState<TokenSample[]>([]);
  const [macroSending, setMacroSending] = useState<string | null>(null);
  const [customMacros, setCustomMacros] = useState<MacroAction[]>([]);
  const [newMacro, setNewMacro] = useState({
    label: "",
    description: "",
    content: "",
  });
  const [pinnedLogs, setPinnedLogs] = useState<LogEntryType[]>([]);
  const [logFilter, setLogFilter] = useState("");
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [copyStepsMessage, setCopyStepsMessage] = useState<string | null>(null);
  const [feedbackByRequest, setFeedbackByRequest] = useState<
    Record<
      string,
      { rating?: "up" | "down" | null; comment?: string; message?: string | null }
    >
  >({});
  const [feedbackSubmittingId, setFeedbackSubmittingId] = useState<string | null>(null);
  const [quickActionsOpen, setQuickActionsOpen] = useState(false);
  const [exportingPinned, setExportingPinned] = useState(false);
  const [gitAction, setGitAction] = useState<"sync" | "undo" | null>(null);
  const [queueAction, setQueueAction] = useState<
    null | "pause" | "resume" | "purge" | "emergency"
  >(null);
  const [queueActionMessage, setQueueActionMessage] = useState<string | null>(
    null,
  );
  const [optimisticRequests, setOptimisticRequests] = useState<OptimisticRequestState[]>([]);
  const [lastResponseDurationMs, setLastResponseDurationMs] = useState<number | null>(null);
  const [responseDurations, setResponseDurations] = useState<number[]>([]);
  const lastTelemetryRefreshRef = useRef<string | null>(null);
  const [tuningOpen, setTuningOpen] = useState(false);
  const [generationParams, setGenerationParams] = useState<GenerationParams | null>(null);
  const [modelSchema, setModelSchema] = useState<GenerationSchema | null>(null);
  const [loadingSchema, setLoadingSchema] = useState(false);
  const [tuningSaving, setTuningSaving] = useState(false);
  const [chatFullscreen, setChatFullscreen] = useState(false);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const t = useTranslation();
  const streamCompletionRef = useRef<Set<string>>(new Set());
  const promptPresets = useMemo(
    () => [
      {
        id: "preset-creative",
        category: "Kreacja",
        description: "Stwórz logo dla fintechu używając DALL-E",
        prompt: "Stwórz logo dla fintechu używając DALL-E",
        icon: "🎨",
      },
      {
        id: "preset-devops",
        category: "DevOps",
        description: "Sprawdź status serwerów w infrastrukturze",
        prompt: "Sprawdź status serwerów w infrastrukturze",
        icon: "☁️",
      },
      {
        id: "preset-project",
        category: "Status projektu",
        description: "Pokaż status projektu i roadmapy",
        prompt: "Pokaż status projektu",
        icon: "📊",
      },
      {
        id: "preset-research",
        category: "Research",
        description: "Zrób research o trendach AI w 2024",
        prompt: "Zrób research o trendach AI w 2024",
        icon: "🧠",
      },
      {
        id: "preset-code",
        category: "Kod",
        description: "Napisz testy jednostkowe dla modułu API",
        prompt: "Napisz testy jednostkowe dla modułu API",
        icon: "🛠️",
      },
      {
        id: "preset-help",
        category: "Pomoc",
        description: "Co potrafisz? Pokaż dostępne funkcje systemu",
        prompt: "Co potrafisz?",
        icon: "❓",
      },
    ],
    [],
  );
  const { data: liveMetrics, loading: metricsLoading } = useMetrics();
  const metrics = liveMetrics ?? initialData.metrics ?? null;
  const { data: liveTasks, refresh: refreshTasks } = useTasks();
  const tasks = liveTasks ?? initialData.tasks ?? null;
  const { data: liveQueue, loading: queueLoading, refresh: refreshQueue } = useQueueStatus();
  const queue = liveQueue ?? initialData.queue ?? null;
  const { data: liveServices } = useServiceStatus();
  const {
    data: liveLlmServers,
    loading: llmServersLoading,
    refresh: refreshLlmServers,
  } = useLlmServers();
  const {
    data: liveActiveServer,
    refresh: refreshActiveServer,
  } = useActiveLlmServer(15000);
  const services = liveServices ?? initialData.services ?? null;
  const { data: liveGraph } = useGraphSummary();
  const graph = liveGraph ?? initialData.graphSummary ?? null;
  const { data: liveModels, refresh: refreshModels } = useModels();
  const models = liveModels ?? initialData.models ?? null;
  const { data: liveGit, refresh: refreshGit } = useGitStatus();
  const git = liveGit ?? initialData.gitStatus ?? null;
  const { data: liveTokenMetrics, loading: tokenMetricsLoading } = useTokenMetrics();
  const tokenMetrics = liveTokenMetrics ?? initialData.tokenMetrics ?? null;
  const { data: liveHistory, loading: historyLoading, refresh: refreshHistory } = useHistory(6);
  const history = liveHistory ?? initialData.history ?? null;
  const { data: learningLogs, loading: learningLoading, error: learningError } =
    useLearningLogs(6);
  const { data: feedbackLogs, loading: feedbackLoading, error: feedbackError } =
    useFeedbackLogs(6);
  const [hiddenIntentFilter, setHiddenIntentFilter] = useState("all");
  const [hiddenScoreFilter, setHiddenScoreFilter] = useState(1);
  const hiddenIntentParam = hiddenIntentFilter === "all" ? undefined : hiddenIntentFilter;
  const {
    data: hiddenPrompts,
    loading: hiddenLoading,
    error: hiddenError,
  } = useHiddenPrompts(6, 20000, hiddenIntentParam, hiddenScoreFilter);
  const {
    data: activeHiddenPrompts,
    loading: activeHiddenLoading,
    error: activeHiddenError,
  } = useActiveHiddenPrompts(hiddenIntentParam, 20000);
  const feedbackUp = metrics?.feedback?.up ?? 0;
  const feedbackDown = metrics?.feedback?.down ?? 0;
  const feedbackTotal = feedbackUp + feedbackDown;
  const feedbackScore =
    feedbackTotal > 0 ? Math.round((feedbackUp / feedbackTotal) * 100) : null;
  const activeHiddenKeys = useMemo(() => {
    const keys = new Set<string>();
    activeHiddenPrompts?.items?.forEach((entry) => {
      const key = entry.prompt_hash ?? entry.prompt;
      if (key) keys.add(key);
    });
    return keys;
  }, [activeHiddenPrompts]);
  const activeHiddenMap = useMemo(() => {
    const map = new Map<string, HiddenPromptEntry>();
    activeHiddenPrompts?.items?.forEach((entry) => {
      const key = entry.prompt_hash ?? entry.prompt;
      if (key) map.set(key, entry);
    });
    return map;
  }, [activeHiddenPrompts]);

  const hiddenIntentOptions = useMemo(() => {
    const intents = new Set<string>();
    hiddenPrompts?.items?.forEach((entry) => {
      if (entry.intent) intents.add(entry.intent);
    });
    return ["all", ...Array.from(intents).sort()];
  }, [hiddenPrompts]);
  const selectableHiddenPrompts = useMemo(() => {
    if (!hiddenPrompts?.items?.length || hiddenIntentFilter === "all") return [];
    return hiddenPrompts.items.filter(
      (entry) => entry.intent && entry.intent === hiddenIntentFilter,
    );
  }, [hiddenPrompts, hiddenIntentFilter]);
  const activeForIntent = useMemo(() => {
    if (!activeHiddenPrompts?.items?.length || hiddenIntentFilter === "all") return null;
    return activeHiddenPrompts.items.find(
      (entry) => entry.intent === hiddenIntentFilter,
    );
  }, [activeHiddenPrompts, hiddenIntentFilter]);
  const trackedRequestIds = useMemo(() => {
    const ids = new Set<string>();
    optimisticRequests.forEach((entry) => {
      if (entry.requestId) ids.add(entry.requestId);
    });
    (history ?? [])
      .filter((item) => item.status === "PENDING" || item.status === "PROCESSING")
      .forEach((item) => ids.add(item.request_id));
    if (selectedRequestId) ids.add(selectedRequestId);
    return Array.from(ids);
  }, [optimisticRequests, history, selectedRequestId]);
  const { streams: taskStreams } = useTaskStream(trackedRequestIds, {
    enabled: isClientReady && trackedRequestIds.length > 0,
  });
  const { data: liveModelsUsageResponse } = useModelsUsage(10000);
  const modelsUsageResponse =
    liveModelsUsageResponse ?? initialData.modelsUsage ?? null;
  const { connected, entries } = useTelemetryFeed();
  const usageMetrics = modelsUsageResponse?.usage ?? null;
  const llmServers = useMemo(() => liveLlmServers ?? [], [liveLlmServers]);
  const activeServerInfo = liveActiveServer ?? null;
  const activeServerName = activeServerInfo?.active_server ?? "";
  const { pushToast } = useToast();
  const selectedServerEntry = useMemo(
    () => llmServers.find((server) => server.name === selectedLlmServer) ?? null,
    [llmServers, selectedLlmServer],
  );
  const availableModelsForServer = useMemo(() => {
    if (!models || !selectedLlmServer) return [];
    const normalProvider = (value?: string | null) => {
      if (!value) return "";
      return value.toLowerCase();
    };
    const inferProvider = (name?: string | null) => {
      if (!name) return null;
      return name.includes(":") ? "ollama" : "vllm";
    };
    let base =
      models.providers && selectedLlmServer in models.providers
        ? models.providers[selectedLlmServer] ?? []
        : (models.models ?? []).filter(
            (model) => normalProvider(model.provider) === selectedLlmServer,
          );
    base = base.filter((model) => normalProvider(model.provider) !== "onnx");
    const names = new Set(base.map((model) => model.name));
    const fallbackNames: string[] = [];
    if (activeServerInfo?.active_model) {
      const inferred = inferProvider(activeServerInfo.active_model);
      if (inferred === selectedLlmServer) {
        fallbackNames.push(activeServerInfo.active_model);
      }
    }
    const lastModels = activeServerInfo?.last_models ?? {};
    const lastForServer =
      selectedLlmServer === "ollama"
        ? lastModels.ollama || lastModels.previous_ollama
        : selectedLlmServer === "vllm"
          ? lastModels.vllm || lastModels.previous_vllm
          : "";
    if (lastForServer && inferProvider(lastForServer) === selectedLlmServer) {
      fallbackNames.push(lastForServer);
    }
    fallbackNames.forEach((name) => {
      if (!name || names.has(name)) return;
      base = [{ name, provider: selectedLlmServer, source: "cached" }, ...base];
      names.add(name);
    });
    return base;
  }, [
    models,
    selectedLlmServer,
    activeServerInfo?.active_model,
    activeServerInfo?.last_models,
  ]);
  const llmServerOptions = useMemo(
    () =>
      llmServers.map((server) => ({
        value: server.name,
        label: server.display_name,
      })),
    [llmServers],
  );
  const llmModelOptions = useMemo(
    () =>
      availableModelsForServer.map((model) => ({
        value: model.name,
        label:
          model.source === "cached"
            ? `${model.name} (ostatni znany)`
            : model.name,
      })),
    [availableModelsForServer],
  );
  const tasksByPrompt = useMemo(() => {
    const bucket = new Map<string, Task>();
    (tasks || []).forEach((task) => {
      if (task.content) {
        bucket.set(task.content.trim(), task);
      }
    });
    return bucket;
  }, [tasks]);
  const tasksById = useMemo(() => {
    const bucket = new Map<string, Task>();
    (tasks || []).forEach((task) => {
      const key = task.task_id || task.id;
      if (key) {
        bucket.set(key, task);
      }
    });
    return bucket;
  }, [tasks]);
  const serviceStatusMap = useMemo(() => {
    const map = new Map<string, ServiceStatus>();
    (services || []).forEach((svc) => {
      if (svc?.name) {
        map.set(svc.name.toLowerCase(), svc);
      }
    });
    return map;
  }, [services]);
  const selectedTaskRuntime = useMemo(() => {
    const runtime = selectedTask?.context_history?.["llm_runtime"];
    if (runtime && typeof runtime === "object") {
      const ctx = runtime as Record<string, unknown>;
      const statusValue = ctx["status"];
      const errorValue = ctx["error"];
      return {
        status: typeof statusValue === "string" ? statusValue : null,
        error:
          typeof errorValue === "string" || (typeof errorValue === "object" && errorValue)
            ? errorValue
            : null,
      };
    }
    return null;
  }, [selectedTask]);
  const runtimeErrorMeta = useMemo(() => {
    const error = selectedTaskRuntime?.error;
    if (!error) return null;
    if (typeof error === "string") {
      const classes = [
        "routing_mismatch",
        "execution_contract_violation",
        "provider_unreachable",
        "timeout",
        "rate_limited",
        "runtime_error",
        "agent_error",
        "validation_error",
        "cancelled",
      ];
      const errorClass = classes.find((entry) => error.includes(entry)) ?? null;
      return { errorClass, details: [] };
    }
    const errorObj = error as Record<string, unknown>;
    const errorClass =
      (typeof errorObj.error_class === "string" && errorObj.error_class) ||
      (typeof errorObj.error_code === "string" && errorObj.error_code) ||
      null;
    const details: string[] = [];
    const errorDetails =
      typeof errorObj.error_details === "object" && errorObj.error_details
        ? (errorObj.error_details as Record<string, unknown>)
        : {};
    const missing = errorDetails["missing"];
    if (Array.isArray(missing) && missing.length > 0) {
      details.push(`missing: ${missing[0]}`);
    }
    const expectedHash = errorDetails["expected_hash"];
    const actualHash = errorDetails["actual_hash"];
    if (typeof expectedHash === "string") {
      details.push(`expected_hash: ${expectedHash.slice(0, 8)}`);
    }
    if (typeof actualHash === "string") {
      details.push(`active_hash: ${actualHash.slice(0, 8)}`);
    }
    const expectedRuntime = errorDetails["expected_runtime"];
    const actualRuntime = errorDetails["actual_runtime"];
    if (typeof expectedRuntime === "string") {
      details.push(`expected_runtime: ${expectedRuntime}`);
    }
    if (typeof actualRuntime === "string") {
      details.push(`active_runtime: ${actualRuntime}`);
    }
    const stage = errorObj.stage;
    if (typeof stage === "string") {
      details.push(`stage: ${stage}`);
    }
    return { errorClass, details };
  }, [selectedTaskRuntime?.error]);
  const findTaskMatch = useCallback(
    (requestId?: string, prompt?: string | null) => {
      if (requestId) {
        const byId = tasksById.get(requestId);
        if (byId) return byId;
      }
      if (prompt) {
        const trimmed = prompt.trim();
        if (trimmed.length > 0) {
          return tasksByPrompt.get(trimmed) ?? null;
        }
      }
      return null;
    },
    [tasksById, tasksByPrompt],
  );

  const handleLlmServerActivate = useCallback(async () => {
    if (!selectedLlmServer) {
      setMessage("Wybierz serwer LLM.");
      pushToast("Wybierz serwer LLM.", "warning");
      return;
    }
    try {
      setLlmActionPending(`activate:${selectedLlmServer}`);
      if (
        selectedLlmModel &&
        activeServerInfo?.active_server === selectedLlmServer
      ) {
        await switchModel(selectedLlmModel);
        setMessage(
          `Aktywowano model ${selectedLlmModel} na serwerze ${selectedLlmServer}.`,
        );
        pushToast(
          `Aktywny serwer: ${selectedLlmServer}, model: ${selectedLlmModel}.`,
          "success",
        );
        return;
      }
      const response = await setActiveLlmServer(selectedLlmServer);
      if (response.status === "success") {
        setMessage(`Aktywowano serwer ${selectedLlmServer}.`);
        pushToast(`Aktywny serwer: ${selectedLlmServer}.`, "success");
        if (
          selectedLlmModel &&
          response.active_model &&
          response.active_model !== selectedLlmModel
        ) {
          await switchModel(selectedLlmModel);
          setMessage(
            `Aktywowano serwer ${selectedLlmServer} i model ${selectedLlmModel}.`,
          );
          pushToast(
            `Aktywny serwer: ${selectedLlmServer}, model: ${selectedLlmModel}.`,
            "success",
          );
        }
      } else {
        setMessage("Nie udało się aktywować serwera.");
        pushToast("Nie udało się aktywować serwera.", "error");
      }
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Nie udało się aktywować serwera.",
      );
      pushToast(
        err instanceof Error ? err.message : "Nie udało się aktywować serwera.",
        "error",
      );
    } finally {
      setLlmActionPending(null);
      refreshLlmServers();
      refreshActiveServer();
      refreshModels();
    }
  }, [
    selectedLlmServer,
    selectedLlmModel,
    activeServerInfo?.active_server,
    refreshLlmServers,
    refreshActiveServer,
    refreshModels,
    pushToast,
  ]);

  const resolveServerStatus = useCallback(
    (serverName: string, fallback?: string | null) => {
      const lowered = serverName.toLowerCase();
      const match =
        serviceStatusMap.get(lowered) ||
        serviceStatusMap.get(serverName.toLowerCase());
      return (fallback || match?.status || "unknown").toLowerCase();
    },
    [serviceStatusMap],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(MACRO_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as MacroAction[];
        if (Array.isArray(parsed)) {
          setCustomMacros(parsed);
        }
      }
    } catch (err) {
      console.error("Nie udało się odczytać makr z localStorage:", err);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(MACRO_STORAGE_KEY, JSON.stringify(customMacros));
    } catch (err) {
      console.error("Nie udało się zapisać makr do localStorage:", err);
    }
  }, [customMacros]);

  useEffect(() => {
    if (!selectedLlmServer && activeServerInfo?.active_server) {
      setSelectedLlmServer(activeServerInfo.active_server);
    }
  }, [activeServerInfo?.active_server, selectedLlmServer]);

  useEffect(() => {
    if (selectedLlmServer) return;
    if (activeServerInfo?.active_server) {
      setSelectedLlmServer(activeServerInfo.active_server);
      return;
    }
    if (llmServers.length > 0) {
      setSelectedLlmServer(llmServers[0].name);
    }
  }, [selectedLlmServer, activeServerInfo?.active_server, llmServers]);

  useEffect(() => {
    if (!selectedLlmServer) {
      setSelectedLlmModel("");
      return;
    }
    if (availableModelsForServer.length === 0) {
      setSelectedLlmModel("");
      return;
    }
    const currentActive =
      activeServerInfo?.active_server === selectedLlmServer
        ? activeServerInfo?.active_model ?? ""
        : "";
    const lastModels = activeServerInfo?.last_models ?? {};
    const lastForServer =
      selectedLlmServer === "ollama"
        ? lastModels.ollama || lastModels.previous_ollama
        : selectedLlmServer === "vllm"
          ? lastModels.vllm || lastModels.previous_vllm
          : "";
    const availableNames = new Set(
      availableModelsForServer.map((model) => model.name),
    );
    if (selectedLlmModel && availableNames.has(selectedLlmModel)) {
      return;
    }
    if (currentActive && availableNames.has(currentActive)) {
      setSelectedLlmModel(currentActive);
      return;
    }
    if (lastForServer && availableNames.has(lastForServer)) {
      setSelectedLlmModel(lastForServer);
      return;
    }
    setSelectedLlmModel(availableModelsForServer[0].name);
  }, [
    selectedLlmServer,
    availableModelsForServer,
    activeServerInfo?.active_server,
    activeServerInfo?.active_model,
    activeServerInfo?.last_models,
    selectedLlmModel,
  ]);
  useEffect(() => {
    if (!selectedLlmServer) return;
    refreshModels();
    refreshActiveServer();
  }, [selectedLlmServer, refreshModels, refreshActiveServer]);
  useEffect(() => {
    if (tokenMetrics?.total_tokens === undefined) return;
    setTokenHistory((prev) => {
      const next = [
        ...prev,
        {
          timestamp: new Date().toLocaleTimeString(),
          value: tokenMetrics.total_tokens ?? 0,
        },
      ];
      return next.slice(-20);
    });
  }, [tokenMetrics?.total_tokens]);

  useEffect(() => {
    if (!detailOpen || !selectedRequestId) return;
    const fallback = findTaskMatch(selectedRequestId, historyDetail?.prompt);
    if (!fallback) return;
    if (
      !selectedTask ||
      (fallback.logs?.length ?? 0) !== (selectedTask.logs?.length ?? 0) ||
      (fallback.result ?? "") !== (selectedTask.result ?? "")
    ) {
      setSelectedTask(fallback);
    }
  }, [detailOpen, selectedRequestId, historyDetail?.prompt, findTaskMatch, selectedTask]);

  useEffect(() => {
    if (!history || history.length === 0) return;
    let latestDuration: number | null = null;
    setOptimisticRequests((prev) => {
      if (prev.length === 0) return prev;
      let mutated = false;
      const next = prev.filter((entry) => {
        if (!entry.requestId) return true;
        const match = history.find((item) => item.request_id === entry.requestId);
        if (match) {
          mutated = true;
          const finishTs = match.finished_at ?? match.created_at ?? entry.createdAt;
          if (finishTs) {
            const duration = new Date(finishTs).getTime() - entry.startedAt;
            if (Number.isFinite(duration)) {
              latestDuration = duration;
            }
          }
          return false;
        }
        return true;
      });
      return mutated ? next : prev;
    });
    const measuredDuration = latestDuration;
    if (typeof measuredDuration === "number") {
      setLastResponseDurationMs(measuredDuration);
      setResponseDurations((prev) => {
        const next = [...prev, measuredDuration];
        return next.slice(-10);
      });
    }
  }, [history]);

  useEffect(() => {
    if (!entries.length) return;
    const latest = entries[0];
    if (!latest || lastTelemetryRefreshRef.current === latest.id) return;
    lastTelemetryRefreshRef.current = latest.id;
    if (!isTelemetryEventPayload(latest.payload)) return;
    if (!latest.payload.type || !TELEMETRY_REFRESH_EVENTS.has(latest.payload.type)) {
      return;
    }
    const debounce = setTimeout(() => {
      refreshQueue();
      refreshTasks();
      refreshHistory();
    }, 250);
    return () => clearTimeout(debounce);
  }, [entries, refreshQueue, refreshTasks, refreshHistory]);

  useEffect(() => {
    const activeIds = new Set(Object.keys(taskStreams));
    streamCompletionRef.current.forEach((trackedId) => {
      if (!activeIds.has(trackedId)) {
        streamCompletionRef.current.delete(trackedId);
      }
    });

    const entries = Object.entries(taskStreams);
    if (entries.length === 0) return;

    const terminalStatuses = new Set(["COMPLETED", "FAILED", "LOST"]);
    let shouldRefresh = false;
    for (const [taskId, state] of entries) {
      if (!state?.status) continue;
      if (!terminalStatuses.has(state.status)) continue;
      if (streamCompletionRef.current.has(taskId)) continue;
      streamCompletionRef.current.add(taskId);
      shouldRefresh = true;
    }
    if (shouldRefresh) {
      refreshHistory();
      refreshTasks();
    }
  }, [taskStreams, refreshHistory, refreshTasks]);

  const tasksPreview = (tasks || []).slice(0, 4);
  const fallbackAgents: ServiceStatus[] = [
    { name: "Orchestrator", status: "healthy", detail: "Tworzenie i analiza zadań" },
    { name: "Watcher", status: "degraded", detail: "Monitoring repo / usług" },
    { name: "Gardener", status: "healthy", detail: "Lekcje i graf wiedzy" },
  ];
  const agentDeck = services && services.length > 0 ? services : fallbackAgents;
  const cpuUsageValue = formatPercentMetric(usageMetrics?.cpu_usage_percent);
  const gpuUsageValue =
    usageMetrics?.gpu_usage_percent !== undefined
      ? formatPercentMetric(usageMetrics.gpu_usage_percent)
      : usageMetrics?.vram_usage_mb && usageMetrics.vram_usage_mb > 0
        ? "Aktywne"
        : "—";
  const ramValue = formatGbPair(usageMetrics?.memory_used_gb, usageMetrics?.memory_total_gb);
  const vramValue = formatVramMetric(usageMetrics?.vram_usage_mb, usageMetrics?.vram_total_mb);
  const diskValue =
    usageMetrics?.disk_system_used_gb !== undefined &&
    usageMetrics?.disk_system_total_gb !== undefined
      ? formatDiskSnapshot(usageMetrics.disk_system_used_gb, usageMetrics.disk_system_total_gb)
      : formatDiskSnapshot(usageMetrics?.disk_usage_gb, usageMetrics?.disk_limit_gb);
  const diskPercent =
    usageMetrics?.disk_system_usage_percent !== undefined
      ? `${usageMetrics.disk_system_usage_percent.toFixed(1)}%`
      : usageMetrics?.disk_usage_percent !== undefined
        ? `${usageMetrics.disk_usage_percent.toFixed(1)}%`
        : null;
  const sessionCostValue = formatUsd(tokenMetrics?.session_cost_usd);
  const historyMessages = useMemo<ChatMessage[]>(() => {
    if (!history) return [];
    const sortedHistory = [...history].sort((a, b) => {
      const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
      const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
      return aTime - bTime;
    });
    return sortedHistory.flatMap((item) => {
      const prompt = item.prompt?.trim() ?? "";
      const matchedTask = findTaskMatch(item.request_id, prompt);
      const assistantText =
        matchedTask?.result?.trim() ??
        (item.status === "COMPLETED"
          ? "Brak zapisanej odpowiedzi – sprawdź szczegóły zadania."
          : "Odpowiedź w trakcie generowania…");
      const assistantStatus = matchedTask?.status ?? item.status;
      const assistantTimestamp =
        matchedTask?.updated_at ||
        matchedTask?.created_at ||
        item.finished_at ||
        item.created_at;
      return [
        {
          bubbleId: `${item.request_id}-prompt`,
          requestId: item.request_id,
          role: "user",
          text: prompt || "Brak treści zadania.",
          status: item.status,
          timestamp: item.created_at,
          prompt,
          pending: false,
        },
        {
          bubbleId: `${item.request_id}-response`,
          requestId: item.request_id,
          role: "assistant",
          text: assistantText,
          status: assistantStatus,
          timestamp: assistantTimestamp ?? item.created_at,
          prompt,
          pending: false,
        },
      ];
    });
  }, [history, findTaskMatch]);

  const optimisticMessages = useMemo<ChatMessage[]>(() => {
    return optimisticRequests.flatMap((entry) => {
      const baseId = entry.requestId ?? entry.clientId;
      const stream = entry.requestId ? taskStreams[entry.requestId] : null;
      const assistantText =
        stream?.result && stream.result.trim().length > 0
          ? stream.result
          : stream?.logs && stream.logs.length > 0
            ? stream.logs[stream.logs.length - 1] ?? "Generuję odpowiedź…"
            : "Generuję odpowiedź…";
      const assistantStatus =
        stream?.status ??
        (stream?.error ? "Błąd strumienia" : stream ? "W toku" : "W kolejce");
      const isPending =
        !stream?.status || (stream.status !== "COMPLETED" && stream.status !== "FAILED");
      return [
        {
          bubbleId: `${baseId}-optimistic-prompt`,
          requestId: entry.requestId,
          role: "user",
          text: entry.prompt || "Brak treści zadania.",
          status: stream?.status ?? "Wysłano",
          timestamp: entry.createdAt,
          prompt: entry.prompt,
          pending: isPending,
        },
        {
          bubbleId: `${baseId}-optimistic-response`,
          requestId: entry.requestId,
          role: "assistant",
          text: assistantText,
          status: assistantStatus,
          timestamp: entry.createdAt,
          prompt: entry.prompt,
          pending: isPending,
        },
      ];
    });
  }, [optimisticRequests, taskStreams]);

  const chatMessages = useMemo(
    () => [...historyMessages, ...optimisticMessages],
    [historyMessages, optimisticMessages],
  );
  const lastChatScrollTop = useRef(0);
  const didInitialChatScroll = useRef(false);
  const programmaticChatScroll = useRef(false);
  const autoScrollEnabled = useRef(true);
  const scrollChatToBottom = useCallback(() => {
    const container = chatScrollRef.current;
    if (!container) return;
    programmaticChatScroll.current = true;
    container.scrollTop = container.scrollHeight;
    requestAnimationFrame(() => {
      programmaticChatScroll.current = false;
      lastChatScrollTop.current = container.scrollTop;
      autoScrollEnabled.current = true;
    });
  }, []);
  useEffect(() => {
    if (didInitialChatScroll.current) return;
    if (chatMessages.length === 0) return;
    scrollChatToBottom();
    didInitialChatScroll.current = true;
  }, [chatMessages.length, scrollChatToBottom]);
  useEffect(() => {
    if (!autoScrollEnabled.current) return;
    scrollChatToBottom();
  }, [chatMessages, scrollChatToBottom]);
  const handleChatScroll = useCallback(() => {
    const container = chatScrollRef.current;
    if (!container) return;
    if (programmaticChatScroll.current) {
      lastChatScrollTop.current = container.scrollTop;
      return;
    }
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    const isAtBottom = distanceFromBottom <= 12;
    const scrolledUp = container.scrollTop < lastChatScrollTop.current - 2;
    if (scrolledUp) {
      autoScrollEnabled.current = false;
    } else if (isAtBottom) {
      autoScrollEnabled.current = true;
    }
    lastChatScrollTop.current = container.scrollTop;
  }, []);
  const updateFeedbackState = useCallback(
    (
      requestId: string,
      patch: Partial<{
        rating?: "up" | "down" | null;
        comment?: string;
        message?: string | null;
      }>,
    ) => {
      setFeedbackByRequest((prev) => ({
        ...prev,
        [requestId]: { ...prev[requestId], ...patch },
      }));
    },
    [],
  );
  const handleFeedbackSubmit = useCallback(
    async (
      requestId: string,
      override?: { rating: "up" | "down"; comment?: string },
    ) => {
      const state = feedbackByRequest[requestId] || {};
      const rating = override?.rating ?? state.rating;
      const comment = override?.comment ?? state.comment ?? "";
      if (!rating) return;
      setFeedbackSubmittingId(requestId);
      updateFeedbackState(requestId, { message: null });
      try {
        const response = await sendFeedback(
          requestId,
          rating,
          rating === "down" ? comment.trim() : undefined,
        );
        if (rating === "down") {
          updateFeedbackState(requestId, {
            message: response.follow_up_task_id
              ? `Uruchomiono rundę doprecyzowania: ${response.follow_up_task_id}`
              : "Feedback zapisany, runda doprecyzowania wystartuje po chwili.",
          });
        } else {
          updateFeedbackState(requestId, { message: "Feedback zapisany. Dziękuję!" });
        }
        refreshHistory();
        refreshTasks();
      } catch (error) {
        updateFeedbackState(requestId, {
          message:
            error instanceof Error
              ? error.message
              : "Nie udało się zapisać feedbacku.",
        });
      } finally {
        setFeedbackSubmittingId(null);
      }
    },
    [feedbackByRequest, refreshHistory, refreshTasks, updateFeedbackState],
  );
  const handleFeedbackClick = useCallback(
    (requestId: string, rating: "up" | "down") => {
      if (rating === "up") {
        updateFeedbackState(requestId, { rating: "up", comment: "" });
        handleFeedbackSubmit(requestId, { rating: "up" });
        return;
      }
      updateFeedbackState(requestId, { rating: "down" });
    },
    [handleFeedbackSubmit, updateFeedbackState],
  );
  const averageResponseDurationMs =
    responseDurations.length > 0
      ? responseDurations.reduce((acc, value) => acc + value, 0) /
        Math.max(responseDurations.length, 1)
      : null;
  const responseBadgeText =
    lastResponseDurationMs !== null ? `${(lastResponseDurationMs / 1000).toFixed(1)}s` : "n/d";
  const responseBadgeTone =
    lastResponseDurationMs === null
      ? "neutral"
      : lastResponseDurationMs <= 4000
        ? "success"
        : "warning";
  const responseBadgeTitle =
    averageResponseDurationMs !== null
      ? `Średnia z ostatnich ${responseDurations.length} odpowiedzi: ${(averageResponseDurationMs / 1000).toFixed(1)}s`
      : "Brak danych historycznych";
  const logEntries = entries.slice(0, 8);
  const tokenSplits = [
    { label: "Prompt", value: tokenMetrics?.prompt_tokens ?? 0 },
    { label: "Completion", value: tokenMetrics?.completion_tokens ?? 0 },
    { label: "Cached", value: tokenMetrics?.cached_tokens ?? 0 },
  ].filter((item) => item.value && item.value > 0);
  const totalTokens = tokenMetrics?.total_tokens ?? 0;
  const promptTokens = tokenMetrics?.prompt_tokens ?? 0;
  const completionTokens = tokenMetrics?.completion_tokens ?? 0;
  const cachedTokens = tokenMetrics?.cached_tokens ?? 0;
  const tasksCreated = metrics?.tasks?.created ?? 0;
  const successRateValue = metrics?.tasks?.success_rate;
  const successRate = typeof successRateValue === "number" ? successRateValue : null;
  const avgTokensPerTask =
    totalTokens > 0 && tasksCreated > 0
      ? Math.round(totalTokens / Math.max(tasksCreated, 1))
      : null;
  const promptShare =
    totalTokens > 0 ? Math.round((promptTokens / totalTokens) * 100) : null;
  const completionShare =
    totalTokens > 0 ? Math.round((completionTokens / totalTokens) * 100) : null;
  const cachedShare =
    totalTokens > 0 ? Math.round((cachedTokens / totalTokens) * 100) : null;
  const lastTokenSample =
    tokenHistory.length > 0 ? tokenHistory[tokenHistory.length - 1]?.value ?? null : null;
  const prevTokenSample =
    tokenHistory.length > 1 ? tokenHistory[tokenHistory.length - 2]?.value ?? null : null;
  const tokenTrendDelta =
    lastTokenSample !== null && prevTokenSample !== null
      ? lastTokenSample - prevTokenSample
      : null;
  const tokenTrendMagnitude =
    tokenTrendDelta !== null ? Math.abs(tokenTrendDelta).toLocaleString("pl-PL") : null;
  const tokenTrendLabel =
    tokenTrendDelta === null
      ? "Stabilny"
      : tokenTrendDelta > 0
        ? `+${tokenTrendDelta.toLocaleString("pl-PL")}↑`
        : `${tokenTrendDelta.toLocaleString("pl-PL")}↓`;
  const telemetryFeed = useMemo<TelemetryFeedEntry[]>(() => {
    return entries
      .filter((entry) => isTelemetryEventPayload(entry.payload) && entry.payload.type)
      .slice(0, 12)
      .map((entry) => {
        const payload = entry.payload as TelemetryEventPayload;
        return {
          id: entry.id,
          type: payload.type ?? "SYSTEM_LOG",
          message: payload.message || (typeof payload.data?.message === "string" ? payload.data?.message : "Zdarzenie telemetryczne"),
          timestamp: new Date(entry.ts).toLocaleTimeString(),
          tone: mapTelemetryTone(payload.type ?? "SYSTEM_LOG"),
        };
      });
  }, [entries]);
  const promptCompletionRatio =
    completionTokens > 0
      ? (promptTokens / Math.max(completionTokens, 1)).toFixed(1)
      : promptTokens > 0
        ? "∞"
        : null;

  const graphNodes = graph?.summary?.nodes ?? graph?.nodes ?? "—";
  const graphEdges = graph?.summary?.edges ?? graph?.edges ?? "—";
  const historySummary = useMemo(() => {
    const bucket: Record<string, number> = {};
    (history || []).forEach((item) => {
      const key = item.status || "UNKNOWN";
      bucket[key] = (bucket[key] || 0) + 1;
    });
    return Object.entries(bucket)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [history]);
  const historyStatusEntries = historySummary.map((entry) => ({
    label: entry.name,
    value: entry.value,
  }));
  const macroActions = useMemo<MacroAction[]>(
    () => [
      {
        id: "graph-scan",
        label: "Skanuj graf wiedzy",
        description: "Wywołaj /api/v1/graph/scan i odśwież podgląd Brain.",
        content: "Przeskanuj repozytorium i zaktualizuj graf wiedzy.",
      },
      {
        id: "system-health",
        label: "Status usług",
        description: "Sprawdź /api/v1/system/services i zgłoś anomalie.",
        content:
          "Zbadaj kondycję wszystkich usług Venoma i przygotuj raport o stanie wraz z rekomendacjami.",
      },
      {
        id: "roadmap-sync",
        label: "Roadmap sync",
        description: "Poproś Strategy agenta o aktualizację roadmapy.",
        content:
          "Uzgodnij bieżące zadania z roadmapą i wypisz brakujące milestone'y wraz z datami.",
      },
      {
        id: "git-audit",
        label: "Git audit",
        description: "Analiza repo: zmiany, konflikty, propozycje commitów.",
        content:
          "Przeanalizuj repozytorium git, wypisz niezatwierdzone zmiany i zaproponuj strukturę commitów.",
      },
    ],
    [],
  );
  const allMacros = useMemo(
    () => [...macroActions, ...customMacros],
    [macroActions, customMacros],
  );

  const enqueueOptimisticRequest = useCallback((prompt: string) => {
    const entry: OptimisticRequestState = {
      clientId: createOptimisticId(),
      requestId: null,
      prompt,
      createdAt: new Date().toISOString(),
      startedAt: Date.now(),
      confirmed: false,
    };
    setOptimisticRequests((prev) => [...prev, entry]);
    return entry.clientId;
  }, []);

  const linkOptimisticRequest = useCallback((clientId: string, requestId: string | null) => {
    if (!clientId) return;
    setOptimisticRequests((prev) =>
      prev.map((entry) =>
        entry.clientId === clientId
          ? {
              ...entry,
              requestId: requestId ?? entry.requestId ?? entry.clientId,
              confirmed: true,
            }
          : entry,
      ),
    );
  }, []);

  const dropOptimisticRequest = useCallback((clientId: string) => {
    if (!clientId) return;
    setOptimisticRequests((prev) => prev.filter((entry) => entry.clientId !== clientId));
  }, []);

  const handleSend = useCallback(async (payload: string) => {
    const trimmed = payload.trim();
    if (!trimmed) {
      setMessage("Podaj treść zadania.");
      return false;
    }
    autoScrollEnabled.current = true;
    scrollChatToBottom();
    setSending(true);
    setMessage(null);
    const clientId = enqueueOptimisticRequest(trimmed);
    try {
      const res = await sendTask(trimmed, !labMode, generationParams, {
        configHash: activeServerInfo?.config_hash ?? null,
        runtimeId: activeServerInfo?.runtime_id ?? null,
      });
      const resolvedId = res.task_id ?? null;
      linkOptimisticRequest(clientId, resolvedId);
      setMessage(`Wysłano zadanie: ${resolvedId ?? "w toku…"}`);
      await Promise.all([refreshTasks(), refreshQueue(), refreshHistory()]);
      return true;
    } catch (err) {
      dropOptimisticRequest(clientId);
      setMessage(
        err instanceof Error ? err.message : "Nie udało się wysłać zadania",
      );
      return false;
    } finally {
      setSending(false);
    }
  }, [
    enqueueOptimisticRequest,
    labMode,
    generationParams,
    linkOptimisticRequest,
    dropOptimisticRequest,
    refreshTasks,
    refreshQueue,
    refreshHistory,
    activeServerInfo?.config_hash,
    activeServerInfo?.runtime_id,
    scrollChatToBottom,
  ]);

  const handleOpenTuning = useCallback(async () => {
    setTuningOpen(true);
    setLoadingSchema(true);
    setGenerationParams(null);
    try {
      // Pobierz aktywny model z runtime info
      const activeModelName = models?.active?.model || "llama3";
      const config = await fetchModelConfig(activeModelName);
      const schema = config?.generation_schema as GenerationSchema | undefined;
      setModelSchema(schema ?? null);
      if (config?.current_values) {
        setGenerationParams(config.current_values as GenerationParams);
      }
    } catch (err) {
      console.error("Nie udało się pobrać konfiguracji modelu:", err);
      setModelSchema(null);
    } finally {
      setLoadingSchema(false);
    }
  }, [models, setTuningOpen, setLoadingSchema, setModelSchema]);

  const handleApplyTuning = useCallback(async () => {
    const activeModelName = models?.active?.model;
    if (!activeModelName) {
      pushToast("Brak aktywnego modelu do strojenia.", "warning");
      return;
    }
    setTuningSaving(true);
    try {
      await updateModelConfig(activeModelName, {
        runtime: models?.active?.provider,
        params: (generationParams ?? {}) as Record<
          string,
          number | string | boolean | null | undefined
        >,
      });
      pushToast("Zapisano parametry generacji.", "success");
    } catch (err) {
      pushToast(
        err instanceof Error ? err.message : "Nie udało się zapisać parametrów.",
        "error",
      );
    } finally {
      setTuningSaving(false);
    }
  }, [generationParams, models, pushToast]);

  const handleMacroRun = useCallback(
    async (macro: { id: string; content: string; label: string }) => {
      if (macroSending) return;
      setMacroSending(macro.id);
      setMessage(null);
      const clientId = enqueueOptimisticRequest(macro.content);
      try {
        const res = await sendTask(macro.content, !labMode, null, {
          configHash: activeServerInfo?.config_hash ?? null,
          runtimeId: activeServerInfo?.runtime_id ?? null,
        });
        linkOptimisticRequest(clientId, res.task_id ?? null);
        setMessage(`Makro ${macro.label} wysłane: ${res.task_id ?? "w toku…"}`);
        await Promise.all([refreshTasks(), refreshQueue(), refreshHistory()]);
      } catch (err) {
        dropOptimisticRequest(clientId);
        setMessage(err instanceof Error ? err.message : "Nie udało się wykonać makra.");
      } finally {
        setMacroSending(null);
      }
    },
    [
      macroSending,
      enqueueOptimisticRequest,
      labMode,
      linkOptimisticRequest,
      dropOptimisticRequest,
      refreshTasks,
      refreshQueue,
      refreshHistory,
      activeServerInfo?.config_hash,
      activeServerInfo?.runtime_id,
    ],
  );

  const handleExportPinnedLogs = async () => {
    if (pinnedLogs.length === 0) return;
    setExportingPinned(true);
    try {
      const blob = new Blob(
        [JSON.stringify(pinnedLogs.map((log) => log.payload), null, 2)],
        { type: "application/json" },
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "pinned-logs.json";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Clipboard error:", err);
    } finally {
      setExportingPinned(false);
    }
  };

  const handleToggleQueue = async () => {
    if (!queue) return;
    const action = queue.paused ? "resume" : "pause";
    if (queueAction) return;
    setQueueAction(action);
    setQueueActionMessage(null);
    try {
      await toggleQueue(action === "pause");
      setQueueActionMessage(
        action === "pause"
          ? "Kolejka wstrzymana."
          : "Kolejka wznowiona.",
      );
      refreshQueue();
      refreshTasks();
    } catch (err) {
      setQueueActionMessage(
        err instanceof Error
          ? err.message
          : "Nie udało się zmienić stanu kolejki.",
      );
    } finally {
      setQueueAction(null);
    }
  };

  const executeQueueMutation = async (type: "purge" | "emergency") => {
    if (queueAction) return;
    setQueueAction(type);
    setQueueActionMessage(null);
    try {
      if (type === "purge") {
        const res = await purgeQueue();
        setQueueActionMessage(`Wyczyszczono kolejkę (${res.removed} zadań).`);
      } else {
        const res = await emergencyStop();
        setQueueActionMessage(
          `Zatrzymano zadania: cancelled ${res.cancelled}, purged ${res.purged}.`,
        );
      }
      refreshQueue();
      refreshTasks();
    } catch (err) {
      setQueueActionMessage(
        err instanceof Error
          ? err.message
          : "Nie udało się wykonać akcji na kolejce.",
      );
    } finally {
      setQueueAction(null);
    }
  };

  const openRequestDetail = useCallback(async (requestId: string, prompt?: string) => {
    setSelectedRequestId(requestId);
    setDetailOpen(true);
    setHistoryDetail(null);
    setHistoryError(null);
    setCopyStepsMessage(null);
    setSelectedTask(null);
    setLoadingHistory(true);
    const fallback = findTaskMatch(requestId, prompt);
    try {
      const [detailResult, taskResult] = await Promise.allSettled([
        fetchHistoryDetail(requestId),
        fetchTaskDetail(requestId),
      ]);

      if (detailResult.status === "fulfilled") {
        setHistoryDetail(detailResult.value);
      } else {
        setHistoryError(
          detailResult.reason instanceof Error
            ? detailResult.reason.message
            : "Nie udało się pobrać szczegółów",
        );
      }

      if (taskResult.status === "fulfilled") {
        setSelectedTask(taskResult.value);
      } else if (fallback) {
        setSelectedTask(fallback);
      }
    } catch (err) {
      setHistoryError(
        err instanceof Error ? err.message : "Nie udało się pobrać szczegółów",
      );
      if (fallback) {
        setSelectedTask(fallback);
      }
    } finally {
      setLoadingHistory(false);
    }
  }, [findTaskMatch]);

  const handleCopyDetailSteps = async () => {
    if (!historyDetail?.steps || historyDetail.steps.length === 0) {
      setCopyStepsMessage("Brak danych do skopiowania.");
      setTimeout(() => setCopyStepsMessage(null), 2000);
      return;
    }
    try {
      await navigator.clipboard.writeText(JSON.stringify(historyDetail.steps, null, 2));
      setCopyStepsMessage("Skopiowano kroki.");
    } catch (err) {
      console.error("Clipboard error:", err);
      setCopyStepsMessage("Nie udało się skopiować.");
    } finally {
      setTimeout(() => setCopyStepsMessage(null), 2000);
    }
  };

  const composerRef = useRef<ChatComposerHandle | null>(null);

  const handleSuggestionClick = (prompt: string) => {
    composerRef.current?.setDraft(prompt);
  };

  const chatList = useMemo(() => (
    <>
      {chatMessages.length === 0 && (
        <p className="text-sm text-zinc-500">
          Brak historii – wyślij pierwsze zadanie.
        </p>
      )}
      {chatMessages.map((msg) => {
        const requestId = msg.requestId;
        const isSelected = selectedRequestId === requestId;
        const canInspect = Boolean(requestId) && !msg.pending;
        const handleSelect =
          canInspect && requestId
            ? () => openRequestDetail(requestId, msg.prompt)
            : undefined;
        const feedbackState =
          msg.role === "assistant" && requestId ? feedbackByRequest[requestId] : undefined;
        const feedbackLocked = Boolean(feedbackState?.rating);
        const feedbackActions =
          msg.role === "assistant" && requestId ? (
            <div className="flex items-center gap-2">
              <IconButton
                label="Kciuk w górę"
                variant="outline"
                size="xs"
                className={
                  feedbackState?.rating === "up"
                    ? "border-emerald-400/60 bg-emerald-500/10 focus-visible:outline-none focus-visible:ring-0"
                    : "focus-visible:outline-none focus-visible:ring-0"
                }
                icon={
                  <ThumbsUp
                    strokeWidth={2.5}
                    className={
                      feedbackState?.rating === "up"
                        ? "h-3.5 w-3.5 text-emerald-300"
                        : "h-3.5 w-3.5"
                    }
                  />
                }
                disabled={feedbackSubmittingId === requestId || feedbackLocked}
                onClick={(event) => {
                  event.stopPropagation();
                  handleFeedbackClick(requestId, "up");
                }}
              />
              <IconButton
                label="Kciuk w dół"
                variant="outline"
                size="xs"
                className={
                  feedbackState?.rating === "down"
                    ? "border-rose-400/60 bg-rose-500/10 focus-visible:outline-none focus-visible:ring-0"
                    : "focus-visible:outline-none focus-visible:ring-0"
                }
                icon={
                  <ThumbsDown
                    strokeWidth={2.5}
                    className={
                      feedbackState?.rating === "down"
                        ? "h-3.5 w-3.5 text-rose-300"
                        : "h-3.5 w-3.5"
                    }
                  />
                }
                disabled={feedbackSubmittingId === requestId || feedbackLocked}
                onClick={(event) => {
                  event.stopPropagation();
                  handleFeedbackClick(requestId, "down");
                }}
              />
              {feedbackState?.rating === "down" && feedbackState.comment !== undefined ? (
                <Button
                  variant="outline"
                  size="xs"
                  disabled={
                    feedbackSubmittingId === requestId ||
                    !(feedbackState.comment || "").trim()
                  }
                  onClick={(event) => {
                    event.stopPropagation();
                    handleFeedbackSubmit(requestId);
                  }}
                >
                  {feedbackSubmittingId === requestId ? "Wysyłam..." : "Zapisz"}
                </Button>
              ) : null}
            </div>
          ) : null;
        const feedbackExtra =
          msg.role === "assistant" &&
          requestId &&
          !msg.pending &&
          feedbackState?.rating === "down" ? (
            <>
              <textarea
                className="min-h-[70px] w-full rounded-2xl box-muted px-3 py-2 text-xs text-white outline-none placeholder:text-zinc-500"
                placeholder="Opisz krótko, co było nie tak i czego oczekujesz."
                value={feedbackState.comment || ""}
                onChange={(event) =>
                  updateFeedbackState(requestId, {
                    comment: event.target.value,
                  })
                }
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
              />
              {feedbackState.message && (
                <p className="mt-2 text-xs text-zinc-400">
                  {feedbackState.message}
                </p>
              )}
            </>
          ) : null;

        return (
          <div key={msg.bubbleId}>
            <ConversationBubble
              role={msg.role}
              timestamp={msg.timestamp}
              text={msg.text}
              status={msg.status}
              requestId={msg.role === "assistant" ? msg.requestId ?? undefined : undefined}
              isSelected={isSelected}
              pending={msg.pending}
              onSelect={handleSelect}
              footerActions={feedbackActions}
              footerExtra={feedbackExtra}
            />
          </div>
        );
      })}
      {historyLoading && (
        <p className="text-hint">Odświeżam historię…</p>
      )}
    </>
  ), [
    chatMessages,
    selectedRequestId,
    openRequestDetail,
    feedbackByRequest,
    feedbackSubmittingId,
    handleFeedbackClick,
    handleFeedbackSubmit,
    updateFeedbackState,
    historyLoading,
  ]);

  const handleGitSync = async () => {
    if (gitAction) return;
    setGitAction("sync");
    try {
      await gitSync();
      setMessage("Synchronizacja repo zakończona.");
      refreshGit();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Błąd synchronizacji");
    } finally {
      setGitAction(null);
    }
  };

  const handleGitUndo = async () => {
    if (gitAction) return;
    if (!confirm("Cofnąć lokalne zmiany?")) return;
    setGitAction("undo");
    try {
      await gitUndo();
      setMessage("Cofnięto zmiany.");
      refreshGit();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Błąd git undo");
    } finally {
      setGitAction(null);
    }
  };

  if (!isClientReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#020617] p-6 text-sm text-zinc-400">
        Ładowanie kokpitu…
      </div>
    );
  }

  return (
    <div className="space-y-10 pb-14">
      <SectionHeading
        eyebrow="Dashboard Control"
        title="Centrum Dowodzenia AI"
        description={
          <span className="text-zinc-200">
            Monitoruj telemetrię, kolejkę i logi w czasie rzeczywistym – reaguj tak szybko, jak Venom OS.
          </span>
        }
        as="h1"
        size="lg"
        rightSlot={<Command className="page-heading-icon" />}
      />
      <section
        className={`grid gap-6 ${
          chatFullscreen ? "lg:grid-cols-1" : "lg:grid-cols-[minmax(0,420px)_1fr]"
        }`}
      >
        {!chatFullscreen && (
          <div className="space-y-6">
          <Panel
            title="Serwery LLM"
            description="Steruj lokalnymi runtime (vLLM, Ollama) i monitoruj ich status."
            className="allow-overflow overflow-visible"
          >
            <div className="space-y-3">
              {llmServersLoading ? (
                <p className="text-hint">Ładuję status serwerów…</p>
              ) : llmServers.length === 0 ? (
                <EmptyState
                  icon={<Package className="h-4 w-4" />}
                  title="Brak danych"
                  description="Skonfiguruj komendy LLM_*_COMMAND w .env, aby włączyć sterowanie serwerami."
                />
              ) : null}
              <div className="card-shell card-base p-4 text-sm">
                <div className="grid gap-3">
                  <label className="text-xs uppercase tracking-[0.35em] text-zinc-500">
                    Serwer
                  </label>
                  <SelectMenu
                    value={selectedLlmServer}
                    options={llmServerOptions}
                    onChange={setSelectedLlmServer}
                    ariaLabel="Wybierz serwer LLM"
                    placeholder="Wybierz serwer"
                    disabled={llmServers.length === 0}
                    buttonClassName="w-full justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
                    menuClassName="w-full max-h-72 overflow-y-auto"
                  />
                  <label className="text-xs uppercase tracking-[0.35em] text-zinc-500">
                    Model
                  </label>
                  <SelectMenu
                    value={selectedLlmModel}
                    options={llmModelOptions}
                    onChange={setSelectedLlmModel}
                    ariaLabel="Wybierz model LLM"
                    placeholder="Brak modeli"
                    disabled={llmServers.length === 0 || availableModelsForServer.length === 0}
                    buttonClassName="w-full justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
                    menuClassName="w-full max-h-72 overflow-y-auto"
                  />
                  {selectedLlmServer && availableModelsForServer.length === 0 && (
                    <div className="space-y-2">
                      <EmptyState
                        icon={<Package className="h-4 w-4" />}
                        title="Brak modeli"
                        description="Dodaj model dla wybranego serwera, aby go aktywować."
                      />
                    </div>
                  )}
                  <Link
                    href="/docs/llm-models"
                    className="group inline-flex cursor-pointer items-center gap-2 text-xs underline underline-offset-2 transition hover:opacity-90 !text-[color:var(--secondary)]"
                  >
                    <HelpCircle
                      className="h-4 w-4 transition group-hover:opacity-90 !text-[color:var(--secondary)]"
                      aria-hidden="true"
                    />
                    <span className="!text-[color:var(--secondary)]">
                      Instrukcja dodawania modeli
                    </span>
                  </Link>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
                  <span>
                    Status:{" "}
                    {selectedServerEntry
                      ? resolveServerStatus(
                          selectedServerEntry.display_name,
                          selectedServerEntry.status,
                        )
                      : "unknown"}
                  </span>
                  <span>
                    Aktywny: {activeServerInfo?.active_model ?? "—"} @{" "}
                    {activeServerName || "—"}
                  </span>
                </div>
                <Button
                  variant="macro"
                  size="sm"
                  className="mt-4 w-full justify-center text-center tracking-[0.2em]"
                  onClick={handleLlmServerActivate}
                  disabled={
                    llmActionPending === `activate:${selectedLlmServer}` ||
                    !selectedLlmServer ||
                    !selectedLlmModel
                  }
                >
                  {llmActionPending === `activate:${selectedLlmServer}`
                    ? "Aktywuję..."
                    : "Aktywuj"}
                </Button>
              </div>
            </div>
          </Panel>
          <Panel
            title="Live Feed"
            description="/ws/events stream – ostatnie logi operacyjne"
            action={
              <Badge tone={connected ? "success" : "warning"}>
                {connected ? "Połączono" : "Brak sygnału"}
              </Badge>
            }
          >
            <div className="space-y-4">
              <input
                className="w-full rounded-full border border-white/10 bg-white/5 px-3 py-1 text-sm text-white outline-none placeholder:text-zinc-500"
                placeholder="Filtruj logi..."
                value={logFilter}
                onChange={(e) => setLogFilter(e.target.value)}
              />
              <div className="terminal internal-scroll h-64 overflow-y-auto rounded-2xl border border-emerald-500/15 p-4 text-xs shadow-inner shadow-emerald-400/10">
                {logEntries.length === 0 && (
                  <p className="text-emerald-200/70">Oczekiwanie na logi...</p>
                )}
                {logEntries
                  .filter((entry) => {
                    if (!logFilter.trim()) return true;
                    const payload = entry.payload;
                    const text =
                      typeof payload === "string"
                        ? payload
                        : JSON.stringify(payload, null, 2);
                    return text.toLowerCase().includes(logFilter.toLowerCase());
                  })
                  .map((entry) => (
                    <LogEntry
                      key={entry.id}
                      entry={entry}
                      pinned={pinnedLogs.some((log) => log.id === entry.id)}
                      onPin={() =>
                        setPinnedLogs((prev) =>
                          prev.some((log) => log.id === entry.id)
                            ? prev.filter((log) => log.id !== entry.id)
                            : [...prev, entry],
                        )
                      }
                    />
                  ))}
              </div>
              {pinnedLogs.length > 0 && (
                <div className="rounded-3xl card-shell border-emerald-400/20 bg-gradient-to-br from-emerald-500/20 via-emerald-500/5 to-transparent p-4 text-xs">
                  <div className="flex flex-wrap items-center gap-3">
                    <div>
                      <p className="text-caption text-emerald-200/80">
                        Przypięte logi
                      </p>
                      <p className="text-sm text-emerald-100/80">
                        Najważniejsze zdarzenia z kanału /ws/events.
                      </p>
                    </div>
                    <div className="ml-auto flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        size="xs"
                        className="px-3 text-white"
                        disabled={exportingPinned}
                        onClick={handleExportPinnedLogs}
                      >
                        {exportingPinned ? "Eksportuję..." : "Eksportuj JSON"}
                      </Button>
                      <Button
                        variant="danger"
                        size="xs"
                        className="px-3"
                        onClick={() => setPinnedLogs([])}
                      >
                        Wyczyść
                      </Button>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {pinnedLogs.map((log) => (
                      <PinnedLogCard
                        key={`pinned-${log.id}`}
                        log={log}
                        onUnpin={() =>
                          setPinnedLogs((prev) => prev.filter((entry) => entry.id !== log.id))
                        }
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </Panel>
          <Panel
            title="Aktywne zadania"
            description="Podgląd ostatnich requestów /api/v1/tasks."
          >
            <div className="space-y-3">
              {tasksPreview.length === 0 && (
                <EmptyState
                  icon={<Inbox className="h-4 w-4" />}
                  title="Brak zadań"
                  description="Wyślij nowe polecenie, aby pojawiło się na liście."
                />
              )}
              {tasksPreview.map((task, index) => (
                <ListCard
                  key={`${task.task_id ?? task.id ?? "task"}-${index}`}
                  title={task.content}
                  subtitle={
                    task.created_at
                      ? new Date(task.created_at).toLocaleString()
                      : "—"
                  }
                  badge={<Badge tone={statusTone(task.status)}>{task.status}</Badge>}
                />
              ))}
            </div>
          </Panel>
          </div>
        )}
        <div className="space-y-6">
          <motion.div
            className="glass-panel command-console-panel relative flex min-h-[520px] min-h-0 h-[calc(100vh-220px)] max-h-[calc(100vh-220px)] flex-col overflow-hidden px-6 py-6"
            key={chatFullscreen ? "chat-fullscreen" : "chat-default"}
            initial={{ opacity: 0, y: 24, scale: 0.98, rotateX: 6, rotateY: -6 }}
            animate={{
              opacity: 1,
              y: 0,
              scale: chatFullscreen ? 1.01 : 1,
              rotateX: 0,
              rotateY: 0,
            }}
            transition={{ duration: 1.05, ease: [0.22, 1, 0.36, 1] }}
            style={{ transformStyle: "preserve-3d", perspective: 1200 }}
          >
            <IconButton
              label={chatFullscreen ? "Wyłącz pełny ekran" : "Włącz pełny ekran"}
              size="xs"
              variant="outline"
              className="absolute right-6 top-6 z-20 border-white/10 text-white pointer-events-auto"
              icon={
                chatFullscreen ? (
                  <Minimize2 className="h-3.5 w-3.5" />
                ) : (
                  <Maximize2 className="h-3.5 w-3.5" />
                )
              }
              onClick={() => setChatFullscreen((prev) => !prev)}
            />
            <SectionHeading
              eyebrow="Command Console"
              title="Cockpit AI"
              description="Chat operacyjny z Orchestratora i logami runtime."
              as="h2"
              size="md"
              className="items-center"
              rightSlot={
                <div className="flex flex-wrap items-center gap-2 pr-10">
                  <Badge tone={labMode ? "warning" : "success"}>
                    {labMode ? "Lab Mode" : "Prod"}
                  </Badge>
                  <Badge tone={responseBadgeTone} title={responseBadgeTitle}>
                    Odpowiedź {responseBadgeText}
                  </Badge>
                </div>
              }
            />
            <div className="grid-overlay relative mt-5 flex-1 min-h-0 rounded-3xl box-muted p-6 overflow-hidden">
              <div className="flex h-full min-h-0 flex-col">
                <div
                  className="chat-history-scroll flex-1 min-h-0 space-y-4 overflow-y-auto pr-4 overscroll-contain"
                  ref={chatScrollRef}
                  onScroll={handleChatScroll}
                >
                  {chatList}
                </div>
                <div className="shrink-0">
                  <ChatComposer
                    ref={composerRef}
                    onSend={handleSend}
                    sending={sending}
                    labMode={labMode}
                    setLabMode={setLabMode}
                    selectedLlmServer={selectedLlmServer}
                    llmServerOptions={llmServerOptions}
                    setSelectedLlmServer={setSelectedLlmServer}
                    selectedLlmModel={selectedLlmModel}
                    llmModelOptions={llmModelOptions}
                    setSelectedLlmModel={setSelectedLlmModel}
                    hasModels={availableModelsForServer.length > 0}
                    onOpenTuning={handleOpenTuning}
                    tuningLabel={t("common.tuning")}
                    compactControls={chatFullscreen}
                  />
                  <QuickActions open={quickActionsOpen} onOpenChange={setQuickActionsOpen} />
                  {message && (
                    <p className="mt-2 text-xs text-amber-300">{message}</p>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
          {!chatFullscreen && (
            <>
              <div className="mt-4 space-y-3 rounded-2xl box-base px-4 py-4 text-sm text-zinc-300">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-caption">
                    Sugestie szybkich promptów
                  </p>
                  <span className="text-caption text-zinc-600">
                    Kliknij, aby wypełnić chat
                  </span>
                </div>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {promptPresets.map((preset) => (
                    <Button
                      key={preset.id}
                      type="button"
                      onClick={() => handleSuggestionClick(preset.prompt)}
                      title={preset.description}
                      variant="ghost"
                      size="sm"
                      className="w-full items-center gap-3 rounded-2xl box-muted px-4 py-3 text-left transition hover:border-violet-400/50 hover:bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500/60"
                    >
                      <span className="rounded-2xl bg-white/10 px-3 py-2 text-lg">
                        {preset.icon}
                      </span>
                      <div className="flex-1">
                        <p className="font-semibold text-white">{preset.category}</p>
                        <p className="text-hint">{preset.description}</p>
                      </div>
                    </Button>
                  ))}
                </div>
              </div>
              <div className="grid gap-6">
                <Panel
                  eyebrow="KPI kolejki"
                  title="Skuteczność operacji"
                  description="Monitoruj SLA tasków i uptime backendu."
                  className="kpi-panel"
                >
                  {metricsLoading && !metrics ? (
                    <PanelLoadingState label="Ładuję metryki zadań…" />
                  ) : successRate === null ? (
                    <EmptyState
                      icon={<Bot className="h-4 w-4" />}
                      title="Brak danych SLA"
                      description="Po uruchomieniu zadań i aktualizacji /metrics pojawi się trend skuteczności."
                    />
                  ) : (
                    <CockpitMetricCard
                      primaryValue={`${successRate}%`}
                      secondaryLabel={
                        tasksCreated > 0
                          ? `${tasksCreated.toLocaleString("pl-PL")} zadań`
                          : "Brak zadań"
                      }
                      progress={successRate}
                      footer={`Uptime: ${
                        metrics?.uptime_seconds !== undefined
                          ? formatUptime(metrics.uptime_seconds)
                          : "—"
                      }`}
                    />
                  )}
                </Panel>
                <Panel
                  eyebrow="KPI kolejki"
                  title="Zużycie tokenów"
                  description="Trend prompt/completion/cached."
                  className="kpi-panel"
                >
                  {tokenMetricsLoading && !tokenMetrics ? (
                    <PanelLoadingState label="Ładuję statystyki tokenów…" />
                  ) : (
                    <CockpitTokenCard
                      totalValue={totalTokens}
                      splits={
                        tokenSplits.length > 0
                          ? tokenSplits
                          : [{ label: "Brak danych", value: 0 }]
                      }
                      chartSlot={
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <p className="text-caption">Trend próbek</p>
                            <Badge
                              tone={
                                tokenTrendDelta !== null && tokenTrendDelta < 0
                                  ? "success"
                                  : "warning"
                              }
                            >
                              {tokenTrendLabel}
                            </Badge>
                          </div>
                          {tokenHistory.length < 2 ? (
                            <p className="rounded-2xl border border-dashed border-white/10 bg-black/20 px-3 py-2 text-hint">
                              Za mało danych, poczekaj na kolejne odczyty `/metrics/tokens`.
                            </p>
                          ) : (
                            <div className="rounded-2xl box-subtle p-4">
                              <p className="text-caption">Przebieg ostatnich próbek</p>
                              <div className="mt-3 h-32">
                                <TokenChart history={tokenHistory} height={128} />
                              </div>
                            </div>
                          )}
                        </div>
                      }
                    />
                  )}
                </Panel>
              </div>
              <Panel
                eyebrow="Live telemetry"
                title="Zdarzenia /ws/events"
                description="Najświeższe sygnały TASK_* i QUEUE_* – pozwalają śledzić napływające wyniki bez przeładowania."
              >
                {telemetryFeed.length === 0 ? (
                  <p className="text-hint">
                    Brak zdarzeń – czekam na telemetrię.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {telemetryFeed.map((event) => (
                      <div
                        key={event.id}
                        className="list-row items-start gap-3 text-sm text-white"
                      >
                        <div>
                          <p className="font-semibold">{event.type}</p>
                          <p className="text-hint">{event.message}</p>
                        </div>
                        <div className="text-right text-xs text-zinc-500">
                          <Badge tone={event.tone}>{event.timestamp}</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>
            </>
          )}
        </div>
      </section>
      {!chatFullscreen && (
        <>
          <section className="grid gap-6">
            <Panel
              title="Zasoby"
              description="Śledź wykorzystanie CPU/GPU/RAM/VRAM/Dysk oraz koszt sesji."
            >
              <div className="grid gap-3 sm:grid-cols-3">
                <ResourceMetricCard
                  label="CPU"
                  value={cpuUsageValue}
                  hint="Średnie obciążenie modeli"
                />
                <ResourceMetricCard
                  label="GPU"
                  value={gpuUsageValue}
                  hint="Wskaźnik wykorzystania akceleratora"
                />
                <ResourceMetricCard
                  label="RAM"
                  value={ramValue}
                  hint={
                    usageMetrics?.memory_usage_percent
                      ? `${usageMetrics.memory_usage_percent.toFixed(0)}%`
                      : ""
                  }
                />
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <ResourceMetricCard
                  label="VRAM"
                  value={vramValue}
                  hint="Aktywny model/GPU"
                />
                <ResourceMetricCard label="Dysk" value={diskValue} hint={diskPercent ?? ""} />
              </div>
              <div className="mt-4 flex items-center justify-between rounded-2xl box-muted px-4 py-3 text-xs text-zinc-400">
                <span className="uppercase tracking-[0.35em]">Koszt sesji</span>
                <span className="text-base font-semibold text-white">{sessionCostValue}</span>
              </div>
            </Panel>
          </section>

          <section className="grid gap-6 xl:grid-cols-[minmax(0,320px)]">
            <div className="glass-panel flex flex-col gap-4">
              <header className="flex items-center gap-3">
                <div className="rounded-2xl bg-violet-600/30 p-3 text-violet-100 shadow-neon">
                  <Bot className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                    Agenci
                  </p>
                  <h2 className="heading-h2">Aktywność systemowa</h2>
                </div>
              </header>
              <div className="flex flex-wrap gap-2 text-xs">
                <Badge tone="neutral">Węzły: {graphNodes}</Badge>
                <Badge tone="neutral">Krawędzie: {graphEdges}</Badge>
              </div>
              <div className="space-y-3">
                {agentDeck.map((svc) => (
                  <div
                    key={svc.name}
                    className="flex items-center justify-between rounded-xl border border-white/5 bg-white/5 px-3 py-2 text-sm"
                  >
                    <div>
                      <p className="font-semibold text-white">{svc.name}</p>
                      <p className="text-xs text-zinc-500">
                        {svc.detail ?? "Brak opisu"}
                      </p>
                    </div>
                    <Badge tone={serviceTone(svc.status)}>{svc.status}</Badge>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <Panel
            eyebrow="System KPIs"
            title="Status operacyjny"
            description="Najważniejsze liczby backendu."
            className="kpi-panel"
          >
            <div className="grid gap-4 md:grid-cols-4 lg:grid-cols-5">
              <StatCard
                label="Zadania"
                value={metrics?.tasks?.created ?? "—"}
                hint="Łącznie utworzonych"
              />
              <StatCard
                label="Skuteczność"
                value={successRate !== null ? `${successRate}%` : "—"}
                hint="Aktualna skuteczność"
                accent="green"
              />
              <StatCard
                label="Uptime"
                value={
                  metrics?.uptime_seconds !== undefined
                    ? formatUptime(metrics.uptime_seconds)
                    : "—"
                }
                hint="Od startu backendu"
              />
              <StatCard
                label="Kolejka"
                value={queue ? `${queue.active ?? 0} / ${queue.limit ?? "∞"}` : "—"}
                hint="Aktywne / limit"
                accent="blue"
              />
              <StatCard
                label="Jakość"
                value={feedbackScore !== null ? `${feedbackScore}%` : "—"}
                hint={`${feedbackUp} 👍 / ${feedbackDown} 👎`}
                accent="violet"
              />
            </div>
          </Panel>

          <Panel
            title="Zarządzanie kolejką"
            description="Stan kolejki `/api/v1/queue/status`, koszty sesji i akcje awaryjne."
            className="queue-panel"
          >
            {queue ? (
              <>
                <div className="grid gap-3 sm:grid-cols-3">
                  <StatCard
                    label="Aktywne"
                    value={queue.active ?? "—"}
                    hint="Zadania w toku"
                    accent="violet"
                  />
                  <StatCard
                    label="Oczekujące"
                    value={queue.pending ?? "—"}
                    hint="Czekają na wykonanie"
                    accent="indigo"
                  />
                  <StatCard
                    label="Limit"
                    value={queue.limit ?? "∞"}
                    hint="Maksymalna pojemność"
                    accent="blue"
                  />
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="xs"
                    onClick={handleToggleQueue}
                    disabled={queueAction === "pause" || queueAction === "resume"}
                  >
                    {queue.paused ? "Wznów kolejkę" : "Wstrzymaj kolejkę"}
                  </Button>
                  <Button
                    variant="outline"
                    size="xs"
                    onClick={() => executeQueueMutation("purge")}
                    disabled={queueAction === "purge"}
                  >
                    Wyczyść kolejkę
                  </Button>
                  <Button
                    variant="danger"
                    size="xs"
                    onClick={() => executeQueueMutation("emergency")}
                    disabled={queueAction === "emergency"}
                  >
                    Awaryjne zatrzymanie
                  </Button>
                </div>
                {queueActionMessage && (
                  <p className="mt-2 text-xs text-zinc-400">{queueActionMessage}</p>
                )}
              </>
            ) : (
              <EmptyState
                icon={<Package className="h-4 w-4" />}
                title="Kolejka offline"
                description="Brak danych `/api/v1/queue/status` – sprawdź backend lub użyj Quick Actions."
              />
            )}
          </Panel>

          <div className="grid gap-6 lg:grid-cols-2">
            <Panel
              title="Historia requestów"
              description="Ostatnie /api/v1/history/requests – kliknij, by odczytać szczegóły."
            >
              <HistoryList
                entries={history}
                limit={5}
                selectedId={selectedRequestId}
                onSelect={(entry) => openRequestDetail(entry.request_id, entry.prompt)}
                variant="preview"
                viewAllHref="/inspector"
                emptyTitle="Brak historii"
                emptyDescription="Historia requestów pojawi się po wysłaniu zadań."
              />
              {loadingHistory && (
                <p className="mt-2 text-hint">Ładowanie szczegółów...</p>
              )}
              {historyError && (
                <p className="mt-2 text-xs text-rose-300">{historyError}</p>
              )}
              <p className="mt-2 text-caption">
                Kliknij element listy, aby otworzyć panel boczny „Szczegóły requestu”.
              </p>
            </Panel>
            <Panel
              title="Logi nauki"
              description="Ostatnie wpisy LLM-only z `/api/v1/learning/logs`."
            >
              {learningLogs?.items?.length ? (
                <div className="space-y-3">
                  {learningLogs.items.map((entry, idx) => (
                    <div
                      key={`learning-${entry.task_id ?? idx}`}
                      className="rounded-2xl box-muted p-3 text-xs text-zinc-300"
                    >
                      <div className="flex flex-wrap items-center gap-2 text-caption">
                        <Badge tone={entry.success ? "success" : "danger"}>
                          {entry.success ? "OK" : "Błąd"}
                        </Badge>
                        <span>{entry.intent ?? "—"}</span>
                        <span>{formatRelativeTime(entry.timestamp)}</span>
                      </div>
                      <p className="mt-2 text-sm text-white">
                        {(entry.need ?? "Brak opisu potrzeby.").slice(0, 160)}
                      </p>
                      {entry.error && (
                        <p className="mt-2 text-hint text-rose-300">
                          {entry.error.slice(0, 140)}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={<Inbox className="h-4 w-4" />}
                  title="Brak logów nauki"
                  description="LLM-only zapisy pojawią się po pierwszych odpowiedziach."
                />
              )}
              {learningLoading && (
                <p className="mt-2 text-hint">Ładowanie logów nauki...</p>
              )}
              {learningError && (
                <p className="mt-2 text-xs text-rose-300">{learningError}</p>
              )}
            </Panel>
            <Panel
              title="Feedback"
              description="Ostatnie oceny użytkowników z `/api/v1/feedback/logs`."
            >
              {feedbackLogs?.items?.length ? (
                <div className="space-y-3">
                  {feedbackLogs.items.map((entry, idx) => (
                    <div
                      key={`feedback-${entry.task_id ?? "unknown"}-${entry.timestamp ?? idx}-${idx}`}
                      className="rounded-2xl box-muted p-3 text-xs text-zinc-300"
                    >
                      <div className="flex flex-wrap items-center gap-2 text-caption">
                        <Badge tone={entry.rating === "up" ? "success" : "danger"}>
                          {entry.rating === "up" ? "👍" : "👎"}
                        </Badge>
                        <span>{entry.intent ?? "—"}</span>
                        <span>{formatRelativeTime(entry.timestamp)}</span>
                      </div>
                      <p className="mt-2 text-sm text-white">
                        {(entry.prompt ?? "Brak promptu.").slice(0, 160)}
                      </p>
                      {entry.comment && (
                        <p className="mt-2 text-hint">
                          {entry.comment.slice(0, 140)}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={<Inbox className="h-4 w-4" />}
                  title="Brak feedbacku"
                  description="Oceny pojawią się po pierwszych rundach."
                />
              )}
              {feedbackLoading && (
                <p className="mt-2 text-hint">Ładowanie feedbacku...</p>
              )}
              {feedbackError && (
                <p className="mt-2 text-xs text-rose-300">{feedbackError}</p>
              )}
            </Panel>
            <Panel
              title="Hidden prompts"
              description="Zagregowane pary prompt → odpowiedź z kciuka w górę."
            >
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-zinc-400">
                <label className="text-caption">
                  Filtry
                </label>
                <select
                  className="rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-xs text-white"
                  value={hiddenIntentFilter}
                  onChange={(event) => setHiddenIntentFilter(event.target.value)}
                >
                  {hiddenIntentOptions.map((intent) => (
                    <option key={`intent-${intent}`} value={intent}>
                      {intent === "all" ? "Wszystkie intencje" : intent}
                    </option>
                  ))}
                </select>
                <select
                  className="rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-xs text-white"
                  value={String(hiddenScoreFilter)}
                  onChange={(event) => setHiddenScoreFilter(Number(event.target.value))}
                >
                  {[1, 2, 3].map((value) => (
                    <option key={`score-${value}`} value={String(value)}>
                      Score ≥ {value}
                    </option>
                  ))}
                </select>
                <select
                  className="rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-xs text-white"
                  value={activeForIntent?.prompt_hash ?? activeForIntent?.prompt ?? ""}
                  onChange={async (event) => {
                    if (hiddenIntentFilter === "all") return;
                    const nextValue = event.target.value;
                    if (!nextValue) {
                      if (activeForIntent) {
                        await setActiveHiddenPrompt({
                          intent: activeForIntent.intent,
                          prompt: activeForIntent.prompt,
                          approved_response: activeForIntent.approved_response,
                          prompt_hash: activeForIntent.prompt_hash,
                          active: false,
                          actor: "ui",
                        });
                      }
                      return;
                    }
                    const candidate = selectableHiddenPrompts.find(
                      (entry) => (entry.prompt_hash ?? entry.prompt) === nextValue,
                    );
                    if (candidate) {
                      await setActiveHiddenPrompt({
                        intent: candidate.intent,
                        prompt: candidate.prompt,
                        approved_response: candidate.approved_response,
                        prompt_hash: candidate.prompt_hash,
                        active: true,
                        actor: "ui",
                      });
                    }
                  }}
                  disabled={
                    hiddenIntentFilter === "all" || selectableHiddenPrompts.length === 0
                  }
                >
                  <option value="">
                    {hiddenIntentFilter === "all"
                      ? "Wybierz intencję"
                      : "Brak aktywnego"}
                  </option>
                  {selectableHiddenPrompts.map((entry, idx) => {
                    const key = entry.prompt_hash ?? entry.prompt ?? `${idx}`;
                    return (
                      <option key={`active-hidden-${key}`} value={key}>
                        {(entry.prompt ?? "Brak promptu").slice(0, 40)}
                      </option>
                    );
                  })}
                </select>
                {activeHiddenKeys.size > 0 && (
                  <span className="pill-badge text-emerald-100">
                    Aktywne: {activeHiddenKeys.size}
                  </span>
                )}
              </div>
              {hiddenPrompts?.items?.length ? (
                <div className="space-y-3">
                  {hiddenPrompts.items.map((entry, idx) => {
                    const key = entry.prompt_hash ?? entry.prompt ?? `${idx}`;
                    const isActive = activeHiddenKeys.has(key);
                    const activeMeta = isActive ? activeHiddenMap.get(key) : undefined;
                    return (
                      <div
                        key={`hidden-${entry.intent ?? "unknown"}-${idx}`}
                        className="rounded-2xl box-muted p-3 text-xs text-zinc-300"
                      >
                        <div className="flex flex-wrap items-center gap-2 text-caption">
                          <Badge tone="neutral">Score: {entry.score ?? 1}</Badge>
                          <span>{entry.intent ?? "—"}</span>
                          <span>{formatRelativeTime(entry.last_timestamp)}</span>
                          {isActive && (
                            <Badge tone="success">
                              Aktywny
                              {activeMeta?.activated_by
                                ? ` • ${activeMeta.activated_by}`
                                : ""}
                            </Badge>
                          )}
                        </div>
                        <p className="mt-2 text-sm text-white">
                          {(entry.prompt ?? "Brak promptu.").slice(0, 160)}
                        </p>
                        {entry.approved_response && (
                          <p className="mt-2 text-hint">
                            {entry.approved_response.slice(0, 160)}
                          </p>
                        )}
                    {activeMeta?.activated_at && (
                      <p className="mt-2 text-hint text-emerald-200">
                        Aktywne od: {formatRelativeTime(activeMeta.activated_at)}
                      </p>
                    )}
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        size="xs"
                        variant={isActive ? "danger" : "outline"}
                        onClick={async () => {
                          await setActiveHiddenPrompt({
                            intent: entry.intent,
                            prompt: entry.prompt,
                            approved_response: entry.approved_response,
                            prompt_hash: entry.prompt_hash,
                            active: !isActive,
                            actor: "ui",
                          });
                        }}
                      >
                        {isActive ? "Wyłącz" : "Aktywuj"}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon={<Inbox className="h-4 w-4" />}
              title="Brak hidden prompts"
              description="Pojawią się po ocenach z kciukiem w górę."
            />
          )}
          {hiddenLoading && (
            <p className="mt-2 text-hint">Ładowanie hidden prompts...</p>
          )}
          {hiddenError && (
            <p className="mt-2 text-xs text-rose-300">{hiddenError}</p>
          )}
          {activeHiddenLoading && (
            <p className="mt-2 text-hint">Ładowanie aktywnych wpisów...</p>
          )}
          {activeHiddenError && (
            <p className="mt-2 text-xs text-rose-300">{activeHiddenError}</p>
          )}
        </Panel>
      </div>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <VoiceCommandCenter />
        <IntegrationMatrix services={services} events={entries} />
      </section>

      <Panel
        title="Makra Cockpitu"
        description="Najczęściej używane polecenia wysyłane jednym kliknięciem."
        action={
          <div className="flex flex-col gap-3 rounded-2xl box-base p-3 text-xs text-white">
            <form
              className="flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (!newMacro.label.trim() || !newMacro.content.trim()) return;
                setCustomMacros((prev) => [
                  ...prev,
                  {
                    id: `custom-${prev.length + 1}`,
                    label: newMacro.label.trim(),
                    description: newMacro.description.trim() || "Makro użytkownika",
                    content: newMacro.content.trim(),
                    custom: true,
                  },
                ]);
                setNewMacro({ label: "", description: "", content: "" });
              }}
            >
              <p className="text-caption text-zinc-400">
                Dodaj makro
              </p>
              <input
                className="rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                placeholder="Nazwa"
                value={newMacro.label}
                onChange={(e) => setNewMacro((prev) => ({ ...prev, label: e.target.value }))}
              />
              <input
                className="rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                placeholder="Opis"
                value={newMacro.description}
                onChange={(e) => setNewMacro((prev) => ({ ...prev, description: e.target.value }))}
              />
              <textarea
                className="min-h-[60px] rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                placeholder="Treść polecenia / prompt"
                value={newMacro.content}
                onChange={(e) => setNewMacro((prev) => ({ ...prev, content: e.target.value }))}
              />
              <Button type="submit" size="xs" variant="outline" className="px-3">
                Dodaj makro
              </Button>
            </form>
            {customMacros.length > 0 && (
              <Button
                type="button"
                size="xs"
                variant="danger"
                className="px-3"
                onClick={() => setCustomMacros([])}
              >
                Resetuj makra użytkownika
              </Button>
            )}
          </div>
        }
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {allMacros.map((macro) => (
            <MacroCard
              key={macro.id}
              title={macro.label}
              description={macro.description}
              isCustom={macro.custom}
              pending={macroSending === macro.id}
              onRun={() => handleMacroRun(macro)}
              onRemove={
                macro.custom
                  ? () =>
                      setCustomMacros((prev) => prev.filter((item) => item.id !== macro.id))
                  : undefined
              }
            />
          ))}
        </div>
      </Panel>

      <Panel
        title="Task Insights"
        description="Podsumowanie statusów i ostatnich requestów /history/requests."
      >
        <div className="grid gap-4 md:grid-cols-2">
          <TaskStatusBreakdown
            title="Statusy"
            datasetLabel="Ostatnie 50 historii"
            totalLabel="Historia"
            totalValue={(history || []).length}
            entries={historyStatusEntries}
            emptyMessage="Brak historii do analizy."
          />
          <RecentRequestList requests={history} />
        </div>
      </Panel>

        <Panel
          title="Zarządzanie kolejką"
        description="Stan kolejki i szybkie akcje – zarządzaj z jednego miejsca."
        action={
          <Badge tone={queue?.paused ? "warning" : "success"}>
            {queue?.paused ? "Wstrzymana" : "Aktywna"}
          </Badge>
        }
      >
        <div className="space-y-4">
          <QueueStatusCard queue={queue} loading={queueLoading && !queue} />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
              Akcje dostępne w panelu Quick Actions.
            </p>
            <Button
              variant="secondary"
              size="sm"
              className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-4 text-emerald-100 hover:border-emerald-400/60"
              onClick={() => setQuickActionsOpen(true)}
            >
              ⚡ Otwórz Quick Actions
            </Button>
          </div>
        </div>
      </Panel>

      <Panel
        title="Repozytorium"
        description="Status i szybkie akcje git (/api/v1/git/*)."
        action={<Badge tone="neutral">{git?.branch ?? "brak"}</Badge>}
      >
          <div className="space-y-4">
            <div className="card-shell bg-black/30 p-4">
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Stan repo</p>
              <p className="mt-2 text-sm text-white">
                {git?.changes ?? git?.status ?? "Brak danych z API."}
              </p>
              <p className="text-xs text-zinc-500">
                Aktualna gałąź: <span className="font-semibold text-white">{git?.branch ?? "—"}</span>
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <RepoActionCard
                title="Synchronizacja"
                description="Pobierz/publikuj zmiany i odśwież status pipeline’u."
                pending={gitAction === "sync"}
                onClick={handleGitSync}
              />
              <RepoActionCard
                title="Cofnij zmiany"
                description="Przywróć HEAD do stanu origin – operacja nieodwracalna."
                variant="danger"
                pending={gitAction === "undo"}
                onClick={handleGitUndo}
              />
            </div>
          </div>
        </Panel>

      <div className="grid gap-6 md:grid-cols-2">
        <Panel
          title="Efektywność tokenów"
          description="Średnie zużycie i tempo – KPI na bazie /metrics i /metrics/tokens."
        >
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <TokenEfficiencyStat
                label="Śr./zadanie"
                value={
                  avgTokensPerTask !== null
                    ? `${avgTokensPerTask.toLocaleString("pl-PL")} tok`
                    : "—"
                }
                hint="Total tokens ÷ tasks.created"
              />
              <TokenEfficiencyStat
                label="Delta próbki"
                value={tokenTrendMagnitude ? `${tokenTrendMagnitude} tok` : "—"}
                hint="Różnica między dwoma ostatnimi odczytami"
              />
              <TokenEfficiencyStat
                label="Prompt / completion"
                value={promptCompletionRatio ? `${promptCompletionRatio}x` : "—"}
                hint="Większa wartość = dłuższe prompty"
              />
            </div>
            <div className="rounded-3xl border border-emerald-400/20 bg-gradient-to-br from-emerald-500/20 via-sky-500/10 to-emerald-500/5 p-4 text-sm text-emerald-50">
              <p className="text-xs uppercase tracking-[0.35em] text-emerald-100/70">
                Live próbka
              </p>
              <div className="mt-2 flex flex-wrap items-end gap-3">
                <p className="text-3xl font-semibold text-white">
                  {lastTokenSample !== null
                    ? lastTokenSample.toLocaleString("pl-PL")
                    : "—"}
                </p>
                <Badge tone={tokenTrendDelta !== null && tokenTrendDelta < 0 ? "success" : "warning"}>
                  {tokenTrendLabel}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-emerald-100/70">
                {tokenTrendDelta === null
                  ? "Oczekuję kolejnych danych z /metrics/tokens."
                  : tokenTrendDelta >= 0
                    ? "Zużycie rośnie względem poprzedniej próbki – rozważ throttle."
                    : "Zużycie spadło – cache i makra działają."}
              </p>
            </div>
          </div>
        </Panel>
        <Panel
          title="Cache boost"
          description="Udziały prompt/completion/cached – pozwala ocenić optymalizację."
        >
          <div className="space-y-3">
            <TokenShareBar
              label="Prompt"
              percent={promptShare}
              accent="from-emerald-400/70 via-emerald-500/40 to-emerald-500/10"
            />
            <TokenShareBar
              label="Completion"
              percent={completionShare}
              accent="from-sky-400/70 via-blue-500/40 to-violet-500/10"
            />
            <TokenShareBar
              label="Cached"
              percent={cachedShare}
              accent="from-amber-300/70 via-amber-400/40 to-rose-400/10"
            />
            <p className="text-xs text-[--color-muted]">
              Dane z `/api/v1/metrics/tokens`. Dążymy do wysokiego udziału cache przy zachowaniu
              równowagi prompt/completion.
            </p>
          </div>
        </Panel>
      </div>
        </>
      )}
      <Sheet
        open={detailOpen}
        onOpenChange={(open) => {
          setDetailOpen(open);
          if (!open) {
            setHistoryError(null);
            setSelectedRequestId(null);
            setSelectedTask(null);
          }
        }}
      >
        <SheetContent>
          <SheetHeader>
            <SheetTitle>
              Szczegóły requestu {historyDetail?.request_id ?? selectedRequestId ?? ""}
            </SheetTitle>
            <SheetDescription>
              {"Dane z `/api/v1/history/requests` – kliknięcie w czat lub listę historii otwiera ten panel."}
            </SheetDescription>
          </SheetHeader>
          {!historyDetail && !loadingHistory && !historyError && (
            <p className="text-sm text-zinc-500">
              Wybierz request z Cockpitu, aby zobaczyć szczegóły.
            </p>
          )}
          {loadingHistory && (
            <p className="text-sm text-zinc-400">Ładuję szczegóły requestu...</p>
          )}
          {historyError && (
            <p className="text-sm text-rose-300">{historyError}</p>
          )}
          {historyDetail && (
            <>
              <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
                <Badge tone={statusTone(historyDetail.status)}>
                  {historyDetail.status}
                </Badge>
                <span>Start: {formatDateTime(historyDetail.created_at)}</span>
                <span>Stop: {formatDateTime(historyDetail.finished_at)}</span>
                <span>Czas: {formatDurationSeconds(historyDetail.duration_seconds)}</span>
              </div>
              <div className="mt-4 rounded-2xl box-muted p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
                      Źródło LLM
                    </p>
                    <p className="mt-2 text-base font-semibold text-white">
                      {historyDetail.llm_model ?? "Nieznany model"}
                    </p>
                    <p className="text-xs text-zinc-400">
                      {historyDetail.llm_provider ?? "—"}
                      {historyDetail.llm_endpoint ? ` @ ${historyDetail.llm_endpoint}` : ""}
                    </p>
                  </div>
                  <Badge tone={selectedTaskRuntime?.status === "error" ? "danger" : "success"}>
                    {selectedTaskRuntime?.status === "error" ? "Błąd" : "OK"}
                  </Badge>
                </div>
                {selectedTaskRuntime?.error && (
                  <div className="mt-3 space-y-2">
                    {runtimeErrorMeta?.errorClass && (
                      <Badge tone="danger">{runtimeErrorMeta.errorClass}</Badge>
                    )}
                    {runtimeErrorMeta?.details?.length ? (
                      <div className="flex flex-wrap gap-2">
                        {runtimeErrorMeta.details.map((detail) => (
                          <Badge key={detail} tone="neutral">
                            {detail}
                          </Badge>
                        ))}
                      </div>
                    ) : null}
                    <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 p-2 text-xs text-rose-100">
                      {formatRuntimeError(selectedTaskRuntime.error)}
                    </p>
                  </div>
                )}
              </div>
              <div className="mt-4 rounded-2xl box-base p-4">
                <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                  Prompt
                </p>
                <div className="mt-2 text-sm text-white">
                  <MarkdownPreview
                    content={historyDetail.prompt}
                    emptyState="Brak promptu dla tego requestu."
                  />
                </div>
              </div>
              {selectedTask && (
                <div className="mt-4 rounded-2xl border border-emerald-400/10 bg-emerald-400/5 p-4">
                  <p className="text-xs uppercase tracking-[0.3em] text-emerald-200">
                    Odpowiedź / wynik
                  </p>
                  <div className="mt-2 text-sm text-white">
                    <MarkdownPreview
                      content={
                        selectedTask.result && selectedTask.result.trim().length > 0
                          ? selectedTask.result
                          : "Brak odpowiedzi. Zadanie mogło zakończyć się niepowodzeniem lub jeszcze trwa."
                      }
                      emptyState="Brak danych wyjściowych."
                    />
                  </div>
                </div>
              )}
              {selectedRequestId && (
                <div className="mt-4 rounded-2xl box-base p-4">
                  <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
                    Feedback użytkownika
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      size="xs"
                      variant={
                        feedbackByRequest[selectedRequestId]?.rating === "up"
                          ? "primary"
                          : "outline"
                      }
                      onClick={() => {
                        updateFeedbackState(selectedRequestId, { rating: "up", comment: "" });
                        handleFeedbackSubmit(selectedRequestId, { rating: "up" });
                      }}
                    >
                      Kciuk w górę
                    </Button>
                    <Button
                      size="xs"
                      variant={
                        feedbackByRequest[selectedRequestId]?.rating === "down"
                          ? "danger"
                          : "outline"
                      }
                      onClick={() =>
                        updateFeedbackState(selectedRequestId, { rating: "down" })
                      }
                    >
                      Kciuk w dół
                    </Button>
                  </div>
                  {feedbackByRequest[selectedRequestId]?.rating === "down" && (
                    <textarea
                      className="mt-3 min-h-[80px] w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-white outline-none placeholder:text-zinc-500"
                      placeholder="Opisz krótko, co było nie tak i czego oczekujesz."
                      value={feedbackByRequest[selectedRequestId]?.comment || ""}
                      onChange={(event) =>
                        updateFeedbackState(selectedRequestId, {
                          comment: event.target.value,
                        })
                      }
                    />
                  )}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {feedbackByRequest[selectedRequestId]?.rating === "down" && (
                      <Button
                        size="xs"
                        variant="outline"
                        disabled={
                          feedbackSubmittingId === selectedRequestId ||
                          !(feedbackByRequest[selectedRequestId]?.comment || "").trim()
                        }
                        onClick={() => handleFeedbackSubmit(selectedRequestId)}
                      >
                        {feedbackSubmittingId === selectedRequestId
                          ? "Wysyłam..."
                          : "Wyślij feedback"}
                      </Button>
                    )}
                    {feedbackByRequest[selectedRequestId]?.message && (
                      <span className="text-xs text-zinc-400">
                        {feedbackByRequest[selectedRequestId]?.message}
                      </span>
                    )}
                  </div>
                </div>
              )}
              {selectedTask?.logs && selectedTask.logs.length > 0 && (
                <div className="mt-4 rounded-2xl box-muted p-4">
                  <div className="flex items-center justify-between">
                    <h4 className="heading-h4">
                      Logi zadania ({selectedTask.logs.length})
                    </h4>
                  </div>
                  <div className="mt-3 max-h-[180px] space-y-2 overflow-y-auto pr-2 text-xs text-zinc-300">
                    {selectedTask.logs.map((log, idx) => (
                      <p
                        key={`task-log-${idx}`}
                        className="rounded-xl border border-white/10 bg-white/5 px-3 py-2"
                      >
                        {log}
                      </p>
                    ))}
                  </div>
                </div>
              )}
              <div className="mt-4 space-y-2 rounded-2xl box-muted p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h4 className="heading-h4">
                      Kroki RequestTracer ({historyDetail.steps?.length ?? 0})
                    </h4>
                    <div className="flex flex-wrap gap-2 text-xs">
                      {copyStepsMessage && (
                        <span className="text-emerald-300">{copyStepsMessage}</span>
                      )}
                      <Button
                        variant="outline"
                        size="xs"
                        onClick={handleCopyDetailSteps}
                      >
                        Kopiuj JSON
                      </Button>
                    </div>
                  </div>
                <div className="max-h-[45vh] space-y-2 overflow-y-auto pr-2">
                  {(historyDetail.steps || []).length === 0 && (
                    <p className="text-hint">Brak kroków do wyświetlenia.</p>
                  )}
                  {(historyDetail.steps || []).map((step, idx) => (
                    <div
                      key={`${historyDetail.request_id}-${idx}`}
                      className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">
                          {step.component || "step"}
                        </span>
                        {step.status && <Badge tone={statusTone(step.status)}>{step.status}</Badge>}
                      </div>
                      <p className="text-xs text-zinc-400">
                        {step.action || step.details || "Brak opisu kroku."}
                      </p>
                      {step.timestamp && (
                      <p className="text-caption">
                        {formatDateTime(step.timestamp)}
                      </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2 text-xs">
                <Link
                  href="/inspector"
                  className="rounded-full border border-white/10 px-4 py-2 text-white hover:bg-white/10"
                >
                  Otwórz w Inspectorze
                </Link>
                {historyDetail.request_id && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setDetailOpen(false);
                    }}
                  >
                    Zamknij
                  </Button>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>

      {/* Tuning Drawer */}
      <Sheet open={tuningOpen} onOpenChange={setTuningOpen}>
        <SheetContent className="w-full sm:max-w-md overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Parametry Generacji</SheetTitle>
            <SheetDescription>
              Dostosuj parametry modelu, takie jak temperatura, max_tokens, etc.
            </SheetDescription>
          </SheetHeader>
          <div className="mt-6">
            {loadingSchema && (
              <div className="flex items-center justify-center py-12">
                <span className="text-sm text-zinc-400">Ładuję parametry…</span>
              </div>
            )}
            {!loadingSchema && !modelSchema && (
              <p className="text-sm text-zinc-400">
                Brak schematu parametrów dla aktywnego modelu.
              </p>
            )}
            {!loadingSchema && modelSchema && (
              <>
                <DynamicParameterForm
                  schema={modelSchema}
                  values={generationParams || undefined}
                  onChange={(values) => setGenerationParams(values)}
                  onReset={() => setGenerationParams(null)}
                />
                <div className="mt-4 flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="border-white/20 bg-white/5 text-white hover:bg-white/10"
                    disabled={tuningSaving}
                    onClick={handleApplyTuning}
                  >
                    {tuningSaving ? "Zapisuję..." : "Zastosuj"}
                  </Button>
                </div>
              </>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function PanelLoadingState({ label }: { label: string }) {
  return (
    <div className="flex h-32 items-center justify-center text-sm text-zinc-400">
      {label}
    </div>
  );
}

function serviceTone(status: string | undefined) {
  if (!status) return "neutral" as const;
  const s = status.toLowerCase();
  if (s.includes("healthy") || s.includes("ok")) return "success" as const;
  if (s.includes("degraded") || s.includes("warn")) return "warning" as const;
  if (s.includes("down") || s.includes("error") || s.includes("fail"))
    return "danger" as const;
  return "neutral" as const;
}

function mapTelemetryTone(type: string): "success" | "warning" | "danger" | "neutral" {
  if (type.includes("FAILED") || type.includes("ERROR")) return "danger";
  if (type.includes("PAUSED") || type.includes("PURGED")) return "warning";
  if (type.includes("COMPLETED") || type.includes("RESUMED")) return "success";
  return "neutral";
}

function formatUptime(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDurationSeconds(value?: number | null) {
  if (!value || value <= 0) return "—";
  if (value < 60) return `${value.toFixed(1)}s`;
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${minutes}m ${seconds}s`;
}

function LogEntry({
  entry,
  pinned,
  onPin,
}: {
  entry: LogEntryType;
  pinned?: boolean;
  onPin?: () => void;
}) {
  const payload = entry.payload;
  const logObj = isLogPayload(payload) ? payload : null;
  const text = logObj?.message
    ? logObj.message
    : typeof payload === "string"
      ? payload
      : JSON.stringify(payload, null, 2);
  const level = logObj?.level ? logObj.level.toUpperCase() : "INFO";
  const type = logObj?.type || "log";

  return (
    <div className="mb-2 rounded border border-emerald-500/20 bg-black/10 p-2 font-mono text-xs text-emerald-200 shadow-inner">
      <div className="flex items-center justify-between text-caption text-emerald-300/70">
        <span>{new Date(entry.ts).toLocaleTimeString()}</span>
        <div className="flex items-center gap-2">
          <span>
            {type} • {level}
          </span>
          {onPin && (
            <IconButton
              label={pinned ? "Odepnij log" : "Przypnij log"}
              size="xs"
              variant="outline"
              className={
                pinned
                  ? "border-emerald-400/60 bg-emerald-500/20 text-emerald-100"
                  : "border-emerald-400/30 text-emerald-200"
              }
              icon={pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
              onClick={onPin}
            />
          )}
        </div>
      </div>
      {logObj?.details ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-emerald-200">Szczegóły</summary>
          <pre className="mt-1 max-h-40 overflow-auto text-emerald-100">
            {typeof logObj.details === "string"
              ? logObj.details
              : JSON.stringify(logObj.details, null, 2)}
          </pre>
        </details>
      ) : (
        <pre className="mt-1 whitespace-pre-wrap text-emerald-100">{"> " + text}</pre>
      )}
    </div>
  );
}

type ChatMessage = {
  bubbleId: string;
  requestId: string | null;
  role: "user" | "assistant";
  text: string;
  status?: string | null;
  timestamp: string;
  prompt?: string;
  pending?: boolean;
};

type OptimisticRequestState = {
  clientId: string;
  requestId: string | null;
  prompt: string;
  createdAt: string;
  startedAt: number;
  confirmed: boolean;
};

type TokenSample = { timestamp: string; value: number };
type TelemetryFeedEntry = {
  id: string;
  type: string;
  message: string;
  timestamp: string;
  tone: "success" | "warning" | "danger" | "neutral";
};
export type MacroAction = {
  id: string;
  label: string;
  description: string;
  content: string;
  custom?: boolean;
};
const MACRO_STORAGE_KEY = "venom:cockpit-macros";

type TokenEfficiencyStatProps = {
  label: string;
  value: string | number | null;
  hint: string;
};

function TokenEfficiencyStat({ label, value, hint }: TokenEfficiencyStatProps) {
  return (
    <div className="rounded-2xl box-muted p-3">
      <p className="text-caption">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white">{value ?? "—"}</p>
      <p className="text-hint">{hint}</p>
    </div>
  );
}

type TokenShareBarProps = {
  label: string;
  percent: number | null;
  accent: string;
};

function TokenShareBar({ label, percent, accent }: TokenShareBarProps) {
  return (
    <div className="rounded-2xl box-base p-3">
      <div className="flex items-center justify-between text-sm text-white">
        <span>{label}</span>
        <span>{percent !== null ? `${percent}%` : "—"}</span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-white/5">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${accent}`}
          style={{ width: percent !== null ? `${Math.min(percent, 100)}%` : "0%" }}
        />
      </div>
    </div>
  );
}

type ResourceMetricCardProps = {
  label: string;
  value: string;
  hint?: string;
};

function ResourceMetricCard({ label, value, hint }: ResourceMetricCardProps) {
  return (
    <div className="rounded-2xl box-muted p-3 text-sm text-white">
      <p className="text-caption">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      {hint ? <p className="text-hint">{hint}</p> : null}
    </div>
  );
}

function TokenChart({ history, height = 220 }: { history: TokenSample[]; height?: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<Chart | null>(null);
  const chartModuleRef = useRef<typeof import("chart.js/auto") | null>(null);

  useEffect(() => {
    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!canvasRef.current) return;
    if (height) {
      canvasRef.current.style.height = `${height}px`;
    }
    const labels = history.map((h) => h.timestamp);
    const dataPoints = history.map((h) => h.value);

    let isMounted = true;
    const renderChart = async () => {
      if (!canvasRef.current) return;
      let chartModule = chartModuleRef.current;
      if (!chartModule) {
        chartModule = await import("chart.js/auto");
        chartModuleRef.current = chartModule;
      }
      if (!isMounted) return;
      const ChartJS = chartModule.default;

      if (chartRef.current) {
        chartRef.current.data.labels = labels;
        chartRef.current.data.datasets[0].data = dataPoints;
        chartRef.current.update();
        return;
      }

      chartRef.current = new ChartJS(canvasRef.current, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Total tokens",
              data: dataPoints,
              borderColor: "#8b5cf6",
              backgroundColor: "rgba(139,92,246,0.2)",
              tension: 0.3,
              fill: true,
            },
          ],
        },
        options: {
          responsive: true,
          plugins: {
            legend: {
              labels: {
                color: "#e5e7eb",
              },
            },
          },
          scales: {
            x: {
              ticks: { color: "#94a3b8", maxTicksLimit: 5 },
              grid: { color: "rgba(148,163,184,0.2)" },
            },
            y: {
              ticks: { color: "#94a3b8" },
              grid: { color: "rgba(148,163,184,0.2)" },
            },
          },
        },
      });
    };

    renderChart();

    return () => {
      isMounted = false;
    };
  }, [history, height]);

  return <canvas ref={canvasRef} className="w-full" style={{ height }} />;
}

function createOptimisticId() {
  return `opt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

function formatRuntimeError(error?: unknown) {
  if (!error) return "Błąd wykonania";
  if (typeof error === "string") return error;
  const message = (error as Record<string, unknown>)?.error_message;
  if (typeof message === "string" && message.trim()) return message;
  try {
    return JSON.stringify(error);
  } catch {
    return "Błąd wykonania";
  }
}

export default CockpitHome;
