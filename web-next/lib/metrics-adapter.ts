import type { Metrics } from "@/lib/types";

const numberOrUndefined = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) ? value : undefined;

export const normalizeMetrics = (payload: Metrics | null): Metrics | null => {
  if (!payload) return null;
  return {
    ...payload,
    tasks: {
      ...(payload.tasks ?? {}),
      created: numberOrUndefined(payload.tasks?.created),
      success_rate: numberOrUndefined(payload.tasks?.success_rate),
    },
    routing: {
      ...(payload.routing ?? {}),
      llm_only: numberOrUndefined(payload.routing?.llm_only),
      tool_required: numberOrUndefined(payload.routing?.tool_required),
      learning_logged: numberOrUndefined(payload.routing?.learning_logged),
    },
    feedback: {
      ...(payload.feedback ?? {}),
      up: numberOrUndefined(payload.feedback?.up),
      down: numberOrUndefined(payload.feedback?.down),
    },
    policy: {
      ...(payload.policy ?? {}),
      blocked_count: numberOrUndefined(payload.policy?.blocked_count),
      block_rate: numberOrUndefined(payload.policy?.block_rate),
    },
    network: {
      ...(payload.network ?? {}),
      total_bytes: numberOrUndefined(payload.network?.total_bytes),
    },
    uptime_seconds: numberOrUndefined(payload.uptime_seconds),
  };
};

export const normalizeMetricsRequired = (payload: Metrics): Metrics =>
  normalizeMetrics(payload) ?? payload;
