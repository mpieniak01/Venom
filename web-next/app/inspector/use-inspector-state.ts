"use client";

import { fetchFlowTrace, fetchHistoryDetail, useHistory, useTasks } from "@/hooks/use-api";
import { useTaskStream } from "@/hooks/use-task-stream";
import { NOTIFICATIONS } from "@/lib/ui-config";
import type { HistoryStep } from "@/lib/types";
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

const FLOW_TRACE_TIMEOUT_MS = 20000;

async function fetchFlowTraceWithTimeout(requestId: string, timeoutMs: number) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  try {
    const result = await Promise.race([
    fetchFlowTrace(requestId),
    new Promise<never>((_, reject) => {
      timer = globalThis.setTimeout(() => {
        reject(new Error(`Flow trace timeout after ${timeoutMs}ms`));
      }, timeoutMs);
    }),
    ]);
    return result;
  } finally {
    if (timer) {
      globalThis.clearTimeout(timer);
    }
  }
}

function isRawSourceRendered(container: HTMLDivElement) {
  const svg = container.querySelector("svg");
  if (!svg) return false;
  const text = svg.textContent ?? "";
  const normalized = text.replaceAll(/\s+/g, " ").trim();
  return normalized.includes("sequenceDiagram") || normalized.includes("graph TD");
}

function renderPlainDiagramFallback(container: HTMLDivElement, source: string) {
  const escaped = source
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
  container.innerHTML = `<pre class="h-full w-full overflow-auto whitespace-pre-wrap rounded-[20px] border border-white/10 bg-[#020617] p-4 text-xs text-zinc-200">${escaped}</pre>`;
}

async function renderMermaidSource(
  container: HTMLDivElement,
  mermaidApi: MermaidAPI,
  source: string,
): Promise<boolean> {
  container.innerHTML = `<div class="mermaid"></div>`;
  const node = container.querySelector(".mermaid");
  if (node) {
    node.textContent = source;
  }
  await mermaidApi.run({
    nodes: container.querySelectorAll(".mermaid"),
  });
  return Boolean(container.querySelector("svg")) && !isRawSourceRendered(container);
}

function diagramFromFlow(flow: Awaited<ReturnType<typeof fetchFlowTrace>>, defaultDiagram: string) {
  const flowSteps = (flow?.steps || []) as HistoryStep[];
  let diagramSource = defaultDiagram;
  const flowDiagram = flow?.mermaid_diagram;
  if (flowDiagram && flowDiagram.trim().length > 0) {
    diagramSource = flowDiagram;
  } else if (flowSteps.length > 0) {
    diagramSource = buildSequenceDiagram(flow);
  }
  return { flowSteps, diagramSource };
}

type HistorySelectionSetters = {
  setDiagramLoading: (value: boolean) => void;
  setDetailError: (value: string | null) => void;
  setSelectedId: (value: string) => void;
  setSteps: (value: HistoryStep[]) => void;
  setFocusedIndex: (value: number | null) => void;
  setStepFilter: (value: string) => void;
  setCopyMessage: (value: string | null) => void;
  setMermaidError: (value: string | null) => void;
};

function resetHistorySelectionState(
  requestId: string,
  setters: HistorySelectionSetters,
) {
  setters.setDiagramLoading(true);
  setters.setDetailError(null);
  setters.setSelectedId(requestId);
  setters.setSteps([]);
  setters.setFocusedIndex(null);
  setters.setStepFilter("");
  setters.setCopyMessage(null);
  setters.setMermaidError(null);
}

type HistorySelectionResult = {
  steps: HistoryStep[];
  diagram: string;
};

async function loadHistorySelectionResult(
  requestId: string,
  defaultDiagram: string,
): Promise<HistorySelectionResult> {
  const flow = await fetchFlowTraceWithTimeout(requestId, FLOW_TRACE_TIMEOUT_MS);
  if (!flow) {
    throw new Error("Flow trace response is empty");
  }
  const { flowSteps, diagramSource } = diagramFromFlow(flow, defaultDiagram);
  return { steps: flowSteps, diagram: diagramSource };
}

async function loadHistorySelectionFallback(
  requestId: string,
  defaultDiagram: string,
  fallbackDiagram: string,
): Promise<HistorySelectionResult> {
  const detail = await fetchHistoryDetail(requestId);
  if (!detail) {
    throw new Error("History detail response is empty");
  }
  const detailSteps = detail.steps || [];
  if (detailSteps.length === 0) {
    return { steps: [], diagram: fallbackDiagram };
  }
  return { steps: detailSteps, diagram: buildFlowchartDiagram(detailSteps) || defaultDiagram };
}

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
  const activeSelectSeqRef = useRef(0);
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
    if (!selectedId) return [];
    return [selectedId];
  }, [selectedId]);

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
        "graph TD",
        "    A[Request] --> B[Flow Trace]",
        "    B --> C[Inspector]",
      ].join("\n");

      try {
        const container = svgRef.current;
        const safeDiagram = sanitizeMermaidDiagram(diagram);
        if (!mermaidApi) {
          throw new Error("Mermaid API not ready.");
        }
        const rendered = await renderMermaidSource(container, mermaidApi, safeDiagram);
        if (!rendered) {
          const fallback = sanitizeMermaidDiagram(fallbackDiagram);
          const fallbackRendered = await renderMermaidSource(
            container,
            mermaidApi,
            fallback,
          );
          if (!fallbackRendered) {
            renderPlainDiagramFallback(container, fallback);
          }
          if (!cancelled) {
            setMermaidError(t("inspector.panels.diagram.simplified"));
            requestAnimationFrame(() => fitViewRef.current?.());
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
          if (svgRef.current) {
            renderPlainDiagramFallback(svgRef.current, sanitizeMermaidDiagram(diagram || defaultDiagram));
          }
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
  }, [defaultDiagram, diagram, mermaidReloadKey, mermaidApi, t]);

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

  const handleHistorySelect = useCallback(
    async (requestId: string, force = false) => {
      if (!force && currentDiagramRequestRef.current === requestId && !detailError) {
        return;
      }
      const seq = activeSelectSeqRef.current + 1;
      activeSelectSeqRef.current = seq;
      currentDiagramRequestRef.current = requestId;
      resetHistorySelectionState(
        requestId,
        {
          setDiagramLoading,
          setDetailError,
          setSelectedId,
          setSteps,
          setFocusedIndex,
          setStepFilter,
          setCopyMessage,
          setMermaidError,
        },
      );

      const isStale = () => activeSelectSeqRef.current !== seq;
      const applyResult = (result: HistorySelectionResult) => {
        setSteps(result.steps);
        setDiagram(result.diagram);
      };
      const fallbackDiagram = t("inspector.panels.diagram.fallback");

      try {
        const primaryResult = await loadHistorySelectionResult(
          requestId,
          defaultDiagram,
        );
        if (isStale()) return;
        applyResult(primaryResult);
      } catch (flowError) {
        if (isStale()) return;
        console.error("Flow trace error:", flowError);
        setDetailError(
          flowError instanceof Error
            ? flowError.message
            : t("inspector.panels.diagram.errorRender"),
        );
        try {
          const fallbackResult = await loadHistorySelectionFallback(
            requestId,
            defaultDiagram,
            fallbackDiagram,
          );
          if (isStale()) return;
          applyResult(fallbackResult);
        } catch (historyError) {
          if (isStale()) return;
          console.error("Fallback detail error:", historyError);
          applyResult({ steps: [], diagram: fallbackDiagram });
        }
      } finally {
        if (!isStale()) {
          setDiagramLoading(false);
        }
      }
    },
    [defaultDiagram, detailError, t],
  );

  useEffect(() => {
    if (historyLoading) return;
    if (!history || history.length === 0) return;
    if (selectedId) return;
    const firstHistoryItem = history[0];
    if (!firstHistoryItem) return;
    handleHistorySelect(firstHistoryItem.request_id);
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
