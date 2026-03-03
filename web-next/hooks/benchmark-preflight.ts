import type { BenchmarkLog } from "@/lib/types";

export interface PreflightMessages {
  preparing: string;
  unloading: string;
  starting: string;
  success: string;
  conflict: string;
  runtimeUnhealthy: string;
}

export function emitPreflightLogs(
  addLog: (message: string, level?: BenchmarkLog["level"]) => void,
  messages: PreflightMessages,
): void {
  addLog(messages.preparing, "info");
  addLog(messages.unloading, "info");
  addLog(messages.starting, "info");
}

export function classifyStartError(
  detail: string | null | undefined,
  messages: Pick<PreflightMessages, "conflict" | "runtimeUnhealthy">,
): string {
  if (!detail) return messages.runtimeUnhealthy;
  const lowered = detail.toLowerCase();
  if (lowered.includes("lock") || lowered.includes("already running")) {
    return messages.conflict;
  }
  if (lowered.includes("healthcheck") || lowered.includes("unload")) {
    return messages.runtimeUnhealthy;
  }
  return detail;
}
