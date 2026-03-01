"use client";

import { fetchFlowTrace, fetchHistoryDetail, useHistory, useTasks } from "@/hooks/use-api";
import { useTaskStream } from "@/hooks/use-task-stream";
import { NOTIFICATIONS } from "@/lib/ui-config";
import type { HistoryStep, Task } from "@/lib/types";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  adjustMermaidSizing,
  buildFlowchartDiagram,
  buildInspectorStats,
  buildSequenceDiagram,
  buildTaskBreakdown,
  decorateExecutionFailed,
  filterSteps,
  formatDuration,
  sanitizeMermaidDiagram,
} from "./inspector-utils";

type MermaidAPI = typeof import("mermaid").default;

type Translator = (key: string, params?: Record<string, string | number>) => string;

export function useInspectorState(t: Translator) {
  const {
    data: history,
    refresh: refreshHistory,
    loading: historyLoading,
  } = useHistory(50);
  const { data: tasks, refresh: refreshTasks } = useTasks(0);

  const defaultDiagram = [
    "sequenceDiagram",
    "    autonumber",
    `    ${t("inspector.panels.diagram.defaultNote")}`,
  ].join("\n");

  const [diagram, setDiagram] = useState<string>(defaultDiagram);
  const [diagramLoading, setDiagramLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [steps, setSteps] = useState<HistoryStep[]>([]);
  const [stepFilter, setStepFilter] = useState("");
  const [contractOnly, setContractOnly] = useState(false);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const [historyRefreshPending, setHistoryRefreshPending] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [mermaidError, setMermaidError] = useState<string | null>(null);
  const [mermaidReloadKey, setMermaidReloadKey] = useState(0);
  const [flowFullscreen, setFlowFullscreen] = useState(false);
  const [mermaidApi, setMermaidApi] = useState<MermaidAPI | null>(null);

  const svgRef = useRef<HTMLDivElement | null>(null);
  const mermaidInitializedRef = useRef(false);
  const fitViewRef = useRef<(() => void) | null>(null);
  const currentDiagramRequestRef = useRef<string | null>(null);
  const streamRefreshRef = useRef<Record<string, string | null>>({});
  const lastHistoryAutoRefreshRef = useRef<number>(0);

  const historyAutoRefreshMs = 5000;

  const filteredSteps = useMemo(
    () => filterSteps(steps, stepFilter, contractOnly),
    [steps, stepFilter, contractOnly],
  );
  const stepsCount = steps.length;

  const selectedRequest = useMemo(
    () => (history || []).find((req) => req.request_id === selectedId) ?? null,
    [history, selectedId],
  );

  const focusedStep = useMemo(
    () => (focusedIndex === null ? null : filteredSteps[focusedIndex]),
    [filteredSteps, focusedIndex],
  );

  const inspectorStats = useMemo(() => buildInspectorStats(history, tasks), [history, tasks]);
  const taskBreakdown = useMemo(() => buildTaskBreakdown(tasks), [tasks]);

  const trackedTaskIds = useMemo(() => {
    const ids = new Set<string>();
    (history ?? []).forEach((entry) => {
      if (entry.status === "PENDING" || entry.status === "PROCESSING") {
        ids.add(entry.request_id);
      }
    });
    (tasks ?? []).forEach((task) => {
      const legacyTaskId = (task as Task & { task_id?: string }).task_id;
      const identifier = legacyTaskId || task.id;
      if (!identifier) return;
      const normalized = (task.status || "").toUpperCase();
      if (normalized === "PENDING" || normalized === "PROCESSING") {
        ids.add(identifier);
      }
    });
    if (selectedId) {
      ids.add(selectedId);
    }
    return Array.from(ids);
  }, [history, tasks, selectedId]);

  const { streams: inspectorStreams } = useTaskStream(trackedTaskIds, {
    enabled: trackedTaskIds.length > 0,
  });

  const streamForSelected = selectedId ? inspectorStreams[selectedId] : undefined;
  const liveSelectedStatus = streamForSelected?.status ?? selectedRequest?.status ?? "—";

  const latencyCards = useMemo(
    () => [
      {
        label: t("inspector.latency.avgSla"),
        value: formatDuration(inspectorStats.avgDuration),
        hint: t("inspector.latency.reqDuration"),
      },
      {
        label: t("inspector.latency.activeTracing"),
        value: inspectorStats.processing.toString(),
        hint: t("inspector.latency.logsCount", { total: inspectorStats.total }),
      },
      {
        label: t("inspector.latency.stepsFilter"),
        value: filteredSteps.length.toString(),
        hint: t("inspector.latency.stepsInFlow", { count: stepsCount }),
      },
    ],
    [filteredSteps.length, inspectorStats.avgDuration, inspectorStats.processing, inspectorStats.total, stepsCount, t],
  );

  useEffect(() => {
    refreshHistory();
    refreshTasks();
  }, [refreshHistory, refreshTasks]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState !== "visible") return;
      refreshHistory();
      refreshTasks();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    globalThis.window.addEventListener("focus", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      globalThis.window.removeEventListener("focus", handleVisibility);
    };
  }, [refreshHistory, refreshTasks]);

  useEffect(() => {
    if (globalThis.window === undefined) return;
    let cancelled = false;
    import("mermaid")
      .then((mod) => {
        if (cancelled) return;
        const mermaidModule = mod.default ?? (mod as unknown as MermaidAPI);
        setMermaidApi(mermaidModule);
      })
      .catch((err) => {
        console.error("Mermaid import failed:", err);
        if (!cancelled) {
          setMermaidError(t("inspector.panels.diagram.errorLibrary"));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  useEffect(() => {
    if (!mermaidApi || mermaidInitializedRef.current) {
      return;
    }

    mermaidApi.initialize({
      startOnLoad: false,
      theme: "dark",
      securityLevel: "loose",
      themeCSS: `
        :root {
          --mermaid-font-family: 'Inter, JetBrains Mono', sans-serif;
        }
        .node > rect,
        .node > circle,
        .node > polygon,
        .actor {
          fill: #0f172a !important;
          stroke: #38bdf8 !important;
          stroke-width: 1.4px;
        }
        .messageLine0,
        .loopLine {
          stroke: #38bdf8 !important;
        }
        .messageText,
        .actor > text,
        .noteText {
          fill: #e2e8f0 !important;
        }
        .note {
          fill: #1c1917 !important;
          stroke: #fbbf24 !important;
        }
        .execution-failed-marker {
          fill: #f87171 !important;
          font-weight: 700;
        }
      `,
    });

    mermaidInitializedRef.current = true;
  }, [mermaidApi]);

  useEffect(() => {
    let cancelled = false;

    const render = async () => {
      if (!svgRef.current) return;

      const fallbackDiagram = [
        "sequenceDiagram",
        "    autonumber",
        "    participant User",
        "    participant System",
        "    User->>System: diagram_error",
      ].join("\n");

      try {
        const container = svgRef.current;
        const safeDiagram = sanitizeMermaidDiagram(diagram);
        container.innerHTML = `<div class="mermaid"></div>`;
        const node = container.querySelector(".mermaid");
        if (node) {
          node.textContent = safeDiagram;
        }
        if (!mermaidApi) {
          throw new Error("Mermaid API not ready.");
        }

        try {
          await mermaidApi.run({
            nodes: container.querySelectorAll(".mermaid"),
          });
        } catch (err) {
          console.warn("Mermaid render failed, using fallback diagram:", err);
          const fallback = sanitizeMermaidDiagram(fallbackDiagram);
          if (node) {
            node.textContent = fallback;
          }
          await mermaidApi.run({
            nodes: container.querySelectorAll(".mermaid"),
          });
          if (!cancelled) {
            setMermaidError(t("inspector.panels.diagram.simplified"));
          }
          return;
        }

        decorateExecutionFailed(container);
        adjustMermaidSizing(container);
        if (!cancelled) {
          setMermaidError(null);
          requestAnimationFrame(() => fitViewRef.current?.());
        }
      } catch (err) {
        console.error("Mermaid render error:", err);
        if (!cancelled) {
          setMermaidError(t("inspector.panels.diagram.errorRender"));
        }
      }
    };

    if (diagram && mermaidApi) {
      render();
    } else if (svgRef.current) {
      svgRef.current.innerHTML = "";
    }

    return () => {
      cancelled = true;
    };
  }, [diagram, mermaidReloadKey, mermaidApi, t]);

  useEffect(() => {
    if (!filteredSteps.length) {
      setFocusedIndex(null);
      return;
    }
    setFocusedIndex((current) => {
      if (current === null || current >= filteredSteps.length) {
        return 0;
      }
      return current;
    });
  }, [filteredSteps]);

  const handleHistoryRefresh = useCallback(async () => {
    setHistoryRefreshPending(true);
    try {
      await refreshHistory();
    } finally {
      setHistoryRefreshPending(false);
    }
  }, [refreshHistory]);

  const handleHistorySelect = useCallback(async (requestId: string, force = false) => {
    if (!force && currentDiagramRequestRef.current === requestId) {
      return;
    }

    currentDiagramRequestRef.current = requestId;
    setDiagramLoading(true);
    setDetailError(null);
    setSelectedId(requestId);
    setSteps([]);
    setFocusedIndex(null);
    setStepFilter("");
    setCopyMessage(null);
    setMermaidError(null);

    try {
      const flow = await fetchFlowTrace(requestId);
      if (!flow) {
        throw new Error("Flow trace response is empty");
      }
      const flowSteps = (flow.steps || []) as HistoryStep[];
      setSteps(flowSteps);
      let diagramSource: string | null = null;
      if (flow.mermaid_diagram && flow.mermaid_diagram.trim().length > 0) {
        diagramSource = flow.mermaid_diagram;
      } else if (flowSteps.length > 0) {
        diagramSource = buildSequenceDiagram(flow);
      }
      setDiagram(diagramSource ?? defaultDiagram);
    } catch (flowError) {
      console.error("Flow trace error:", flowError);
      setDetailError(
        flowError instanceof Error ? flowError.message : t("inspector.panels.diagram.errorRender"),
      );
      try {
        const detail = await fetchHistoryDetail(requestId);
        if (!detail) {
          throw new Error("History detail response is empty");
        }
        const detailSteps = detail.steps || [];
        setSteps(detailSteps as HistoryStep[]);
        setDiagram(detailSteps.length > 0 ? buildFlowchartDiagram(detailSteps as HistoryStep[]) : defaultDiagram);
      } catch (historyError) {
        console.error("Fallback detail error:", historyError);
        setSteps([]);
        setDiagram(t("inspector.panels.diagram.fallback"));
      }
    } finally {
      setDiagramLoading(false);
    }
  }, [defaultDiagram, t]);

  useEffect(() => {
    if (historyLoading) return;
    if (!history || history.length === 0) return;
    if (selectedId) return;
    handleHistorySelect(history.at(-1)!.request_id);
  }, [historyLoading, history, selectedId, handleHistorySelect]);

  useEffect(() => {
    if (!selectedId) return;
    const stream = inspectorStreams[selectedId];
    if (!stream?.lastEventAt) return;
    const previousTs = streamRefreshRef.current[selectedId];
    if (previousTs === stream.lastEventAt) return;
    streamRefreshRef.current[selectedId] = stream.lastEventAt;
    const now = Date.now();
    if (now - lastHistoryAutoRefreshRef.current < historyAutoRefreshMs) {
      return;
    }
    lastHistoryAutoRefreshRef.current = now;
    refreshHistory();
  }, [inspectorStreams, selectedId, refreshHistory]);

  const handleCopySteps = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(filteredSteps, null, 2));
      setCopyMessage(t("inspector.actions.copySuccess"));
      setTimeout(() => setCopyMessage(null), NOTIFICATIONS.COPY_MESSAGE_TIMEOUT_MS);
    } catch (err) {
      console.error("Clipboard error:", err);
      setCopyMessage(t("inspector.actions.copyFailed"));
      setTimeout(() => setCopyMessage(null), NOTIFICATIONS.COPY_MESSAGE_TIMEOUT_MS);
    }
  }, [filteredSteps, t]);

  return {
    history,
    historyLoading,
    tasks,
    historyRefreshPending,
    selectedId,
    selectedRequest,
    steps,
    filteredSteps,
    focusedStep,
    focusedIndex,
    stepFilter,
    contractOnly,
    copyMessage,
    detailError,
    diagram,
    diagramLoading,
    mermaidError,
    mermaidReloadKey,
    flowFullscreen,
    inspectorStats,
    taskBreakdown,
    latencyCards,
    liveSelectedStatus,
    streamForSelected,
    svgRef,
    fitViewRef,
    setFocusedIndex,
    setStepFilter,
    setContractOnly,
    setMermaidReloadKey,
    setFlowFullscreen,
    handleHistoryRefresh,
    handleHistorySelect,
    handleCopySteps,
  };
}
