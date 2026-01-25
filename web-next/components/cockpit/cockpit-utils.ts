"use client";

import type { HistoryStep } from "@/lib/types";

export const SESSION_CONTEXT_MARKERS = [
  "[KONTEKST SESJI]",
  "[HISTORIA SESJI]",
  "[STRESZCZENIE SESJI]",
  "[PAMIĘĆ]",
];

export const CONTEXT_SECTION_REGEX =
  /\[(KONTEKST SESJI|HISTORIA SESJI|STRESZCZENIE SESJI|PAMIĘĆ)\][\s\S]*?(?=\n\n\[|$)/gi;
export const PLAN_STEP_REGEX = /^---\s*Krok[\s\S]*?(?=\n\n|$)/gim;
export const PLAN_DONE_REGEX = /^===\s*PLAN ZAKOŃCZONY\s*===/gim;
export const MATH_BLOCK_TOKEN_REGEX = /\bMATH_BLOCK_\d+\b\s*/g;

export const RESPONSE_SOURCE_LABELS = {
  live: "na zywo",
  history: "historia",
  hidden: "hidden",
} as const;

export const TELEMETRY_REFRESH_EVENTS = new Set([
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

export const TERMINAL_STATUSES = new Set(["COMPLETED", "FAILED", "LOST"]);

export const normalizeMatchValue = (value: string) =>
  value.toLowerCase().replace(/\s+/g, " ").trim();

export function extractContextPreviewMeta(steps?: HistoryStep[]) {
  if (!steps || steps.length === 0) return null;
  const step = steps.find((entry) => entry.action === "context_preview");
  const details = step?.details;
  if (!details || typeof details !== "string") return null;
  try {
    const parsed = JSON.parse(details) as {
      prompt_context_preview?: string;
      prompt_context_truncated?: boolean;
      hidden_prompts_count?: number;
      mode?: string;
    };
    return {
      preview: parsed.prompt_context_preview ?? null,
      truncated: parsed.prompt_context_truncated ?? null,
      hiddenPrompts: parsed.hidden_prompts_count ?? null,
      mode: parsed.mode ?? null,
    };
  } catch {
    return null;
  }
}

export function sanitizeAssistantText(raw: string) {
  if (!raw) return raw;
  const hasMarkers = SESSION_CONTEXT_MARKERS.some((marker) => raw.includes(marker));
  if (!hasMarkers) return raw;
  let text = raw.replace(MATH_BLOCK_TOKEN_REGEX, "").trim();
  const lower = text.toLowerCase();
  const wynikIndex = lower.lastIndexOf("wynik:");
  if (wynikIndex !== -1) {
    text = text.slice(wynikIndex + "wynik:".length).trim();
  }
  text = text.replace(CONTEXT_SECTION_REGEX, "");
  text = text.replace(PLAN_STEP_REGEX, "");
  text = text.replace(PLAN_DONE_REGEX, "");
  text = text.replace(/^\s*cel:\s*/gim, "");
  text = text.replace(/\n{3,}/g, "\n\n").trim();
  return text;
}

export type TelemetryEventPayload = {
  type?: string;
  data?: Record<string, unknown>;
  message?: string;
};

export type TelemetryFeedEntry = {
  id: string;
  type: string;
  message: string;
  timestamp: string;
  tone: "success" | "warning" | "danger" | "neutral";
};

export type RequestPayloadContext = Record<string, unknown> | null;

export function extractPayloadContextDetails(payloadContext: RequestPayloadContext) {
  if (!payloadContext || typeof payloadContext !== "object") {
    return {
      payloadGenerationParams: undefined,
      payloadSessionMeta: undefined,
      payloadForcedRoute: undefined,
      payloadContextUsed: undefined,
    };
  }
  return {
    payloadGenerationParams: payloadContext["generation_params"] as Record<string, unknown> | undefined,
    payloadSessionMeta: payloadContext["session"] as Record<string, unknown> | undefined,
    payloadForcedRoute: payloadContext["forced_route"] as Record<string, unknown> | undefined,
    payloadContextUsed: payloadContext["context_used"] as Record<string, unknown> | undefined,
  };
}

export type MacroAction = {
  id: string;
  label: string;
  description: string;
  content: string;
  custom?: boolean;
};

export const MACRO_STORAGE_KEY = "venom:cockpit-macros";

export const isTelemetryEventPayload = (
  payload: unknown,
): payload is TelemetryEventPayload => {
  if (typeof payload !== "object" || payload === null) return false;
  const candidate = payload as { type?: unknown };
  return typeof candidate.type === "string";
};

export function mapTelemetryTone(
  type: string,
): "success" | "warning" | "danger" | "neutral" {
  if (type.includes("ERROR") || type.includes("FAILED") || type.includes("STOP")) {
    return "danger";
  }
  if (type.includes("WARNING") || type.includes("TIMEOUT")) {
    return "warning";
  }
  if (type.includes("COMPLETED") || type.includes("STARTED") || type.includes("RESUMED")) {
    return "success";
  }
  return "neutral";
}
