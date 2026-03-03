import type { BenchmarkLog } from "@/lib/types";

export interface PreflightMessages {
  preparing: string;
  unloading: string;
  starting: string;
  success: string;
  conflict: string;
  runtimeUnhealthy: string;
}

type TranslateFn = (key: string, params?: Record<string, unknown>) => string;

export function emitPreflightLogs(
  addLog: (message: string, level?: BenchmarkLog["level"]) => void,
  messages: PreflightMessages,
): void {
  addLog(messages.preparing, "info");
  addLog(messages.unloading, "info");
  addLog(messages.starting, "info");
}

export async function emitActiveLlmStateLog(
  buildApiUrl: (path: string) => string,
  addLog: (message: string, level?: BenchmarkLog["level"]) => void,
  t: TranslateFn,
): Promise<void> {
  const unknownLabel = t("benchmark.preflight.unknown");
  try {
    const stateResp = await fetch(buildApiUrl("/api/v1/system/llm-servers/active"));
    if (!stateResp.ok) return;
    const state = await stateResp.json() as { active_server?: string; active_model?: string };
    addLog(
      t("benchmark.preflight.llmState", {
        server: state.active_server ?? unknownLabel,
        model: state.active_model ?? unknownLabel,
      }),
      "info",
    );
  } catch {
    addLog(t("benchmark.preflight.llmStateUnavailable"), "warning");
  }
}

export function resolveStartFailureMessage(
  response: { status: number; statusText?: string },
  detail: string | null | undefined,
  t: TranslateFn,
): string {
  if (response.status === 409) {
    return t("benchmark.preflight.conflict");
  }
  const fallbackMessage = t("benchmark.preflight.genericError", {
    status: response.status,
    statusText: response.statusText || t("benchmark.preflight.unknownStatusText"),
  });
  if (!detail) return fallbackMessage;
  return classifyStartError(detail, {
    conflict: t("benchmark.preflight.conflict"),
    runtimeUnhealthy: t("benchmark.preflight.runtimeUnhealthy"),
  });
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
