import "server-only";

import {
  GitStatus,
  GraphSummary,
  HistoryRequest,
  KnowledgeGraph,
  LessonsResponse,
  LessonsStats,
  Metrics,
  ModelsResponse,
  ModelsUsage,
  ModelsUsageResponse,
  QueueStatus,
  ServiceStatus,
  Task,
  TokenMetrics,
} from "@/lib/types";
import { getServerApiBaseUrl } from "@/lib/env";
import { normalizeMetrics } from "@/lib/metrics-adapter";

const KNOWLEDGE_GRAPH_LIMIT = Number(process.env.NEXT_PUBLIC_KNOWLEDGE_GRAPH_LIMIT ?? "500");

const API_BASE = getServerApiBaseUrl();

const sanitizeBase = (value: string) => value.replace(/\/$/, "");
const apiBase = sanitizeBase(API_BASE);

const buildUrl = (path: string) => {
  if (path.startsWith("http")) return path;
  return `${apiBase}${path}`;
};

async function fetchJson<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(buildUrl(path), {
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
      },
    });
    if (!response.ok) {
      logFetchError(path, response.status);
      return null;
    }
    return (await response.json()) as T;
  } catch (err) {
    logFetchError(path, err);
    return null;
  }
}

const logFetchError = (path: string, details: unknown) => {
  if (process.env.NEXT_PHASE === "phase-production-build") {
    return;
  }
  const message = `[server-data] Nie udało się pobrać ${path}`;
  if (process.env.NODE_ENV === "production") {
    console.error(message, normalizeDetail(details));
  } else {
    console.warn(message, details);
  }
};

const normalizeDetail = (details: unknown) => {
  if (details instanceof Error) {
    return {
      message: details.message,
      stack: details.stack,
    };
  }
  return details;
};

const normalizeModelsUsage = (
  payload: ModelsUsageResponse | ModelsUsage | null,
): ModelsUsageResponse | null => {
  if (!payload) return null;
  if ("usage" in payload) {
    return payload;
  }
  return { usage: payload as ModelsUsage };
};

const normalizeServiceStatus = (
  payload: { services?: ServiceStatus[] } | ServiceStatus[] | null,
): ServiceStatus[] | null => {
  if (!payload) return null;
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload.services)) {
    return payload.services;
  }
  return null;
};

export type LayoutInitialData = {
  queue: QueueStatus | null;
  metrics: Metrics | null;
  tasks: Task[] | null;
  modelsUsage: ModelsUsageResponse | null;
  tokenMetrics: TokenMetrics | null;
  gitStatus: GitStatus | null;
};

export async function fetchLayoutInitialData(): Promise<LayoutInitialData> {
  const [queue, metricsRaw, tasks, modelsUsagePayload, tokenMetrics, gitStatus] =
    await Promise.all([
      fetchJson<QueueStatus>("/api/v1/queue/status"),
      fetchJson<Metrics>("/api/v1/metrics"),
      fetchJson<Task[]>("/api/v1/tasks"),
      fetchJson<ModelsUsageResponse | ModelsUsage>("/api/v1/models/usage"),
      fetchJson<TokenMetrics>("/api/v1/metrics/tokens"),
      fetchJson<GitStatus>("/api/v1/git/status"),
    ]);

  return {
    queue,
    metrics: normalizeMetrics(metricsRaw),
    tasks,
    modelsUsage: normalizeModelsUsage(modelsUsagePayload),
    tokenMetrics,
    gitStatus,
  };
}

export type CockpitInitialData = {
  metrics: Metrics | null;
  tasks: Task[] | null;
  queue: QueueStatus | null;
  services: ServiceStatus[] | null;
  graphSummary: GraphSummary | null;
  models: ModelsResponse | null;
  gitStatus: GitStatus | null;
  tokenMetrics: TokenMetrics | null;
  modelsUsage: ModelsUsageResponse | null;
  history: HistoryRequest[] | null;
};

export const EMPTY_COCKPIT_INITIAL_DATA: CockpitInitialData = {
  metrics: null,
  tasks: null,
  queue: null,
  services: null,
  graphSummary: null,
  models: null,
  gitStatus: null,
  tokenMetrics: null,
  modelsUsage: null,
  history: null,
};

export async function fetchCockpitInitialData(): Promise<CockpitInitialData> {
  const [
    metricsRaw,
    tasks,
    queue,
    servicesPayload,
    graphSummary,
    models,
    gitStatus,
    tokenMetrics,
    modelsUsagePayload,
    history,
  ] = await Promise.all([
    fetchJson<Metrics>("/api/v1/metrics"),
    fetchJson<Task[]>("/api/v1/tasks"),
    fetchJson<QueueStatus>("/api/v1/queue/status"),
    fetchJson<{ services?: ServiceStatus[] } | ServiceStatus[]>("/api/v1/system/services"),
    fetchJson<GraphSummary>("/api/v1/graph/summary"),
    fetchJson<ModelsResponse>("/api/v1/models"),
    fetchJson<GitStatus>("/api/v1/git/status"),
    fetchJson<TokenMetrics>("/api/v1/metrics/tokens"),
    fetchJson<ModelsUsageResponse | ModelsUsage>("/api/v1/models/usage"),
    fetchJson<HistoryRequest[]>("/api/v1/history/requests?limit=6"),
  ]);

  return {
    metrics: normalizeMetrics(metricsRaw),
    tasks,
    queue,
    services: normalizeServiceStatus(servicesPayload),
    graphSummary,
    models,
    gitStatus,
    tokenMetrics,
    modelsUsage: normalizeModelsUsage(modelsUsagePayload),
    history,
  };
}

export type BrainInitialData = {
  summary: GraphSummary | null;
  knowledgeGraph: KnowledgeGraph | null;
  lessons: LessonsResponse | null;
  lessonsStats: LessonsStats | null;
};

export const EMPTY_BRAIN_INITIAL_DATA: BrainInitialData = {
  summary: null,
  knowledgeGraph: null,
  lessons: null,
  lessonsStats: null,
};

export async function fetchBrainInitialData(): Promise<BrainInitialData> {
  const [summary, knowledgeGraph, lessons, lessonsStats] = await Promise.all([
    fetchJson<GraphSummary>("/api/v1/graph/summary"),
    fetchJson<KnowledgeGraph>(`/api/v1/knowledge/graph?limit=${KNOWLEDGE_GRAPH_LIMIT}`),
    fetchJson<LessonsResponse>("/api/v1/lessons?limit=5"),
    fetchJson<LessonsStats>("/api/v1/lessons/stats"),
  ]);

  return {
    summary,
    knowledgeGraph,
    lessons,
    lessonsStats,
  };
}
