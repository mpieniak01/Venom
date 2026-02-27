import type { ConnectionValidationReasonCode } from "@/lib/workflow-policy";

export type TranslateFn = (
  path: string,
  replacements?: Record<string, string | number>
) => string;

export function readSourceTag(data: unknown): "local" | "cloud" {
  if (!data || typeof data !== "object") {
    return "local";
  }
  const sourceTag = (data as { sourceTag?: unknown }).sourceTag;
  return sourceTag === "cloud" ? "cloud" : "local";
}

export function resolveDisplayValue(
  value: unknown,
  t: TranslateFn,
  fallbackKey?: string
): string {
  if (typeof value === "string" && value.trim().length > 0) {
    if (fallbackKey) {
      const key = `${fallbackKey}.${value}`;
      const translated = t(key);
      if (translated && translated !== key) {
        return translated;
      }
    }
    return value;
  }
  return t("workflowControl.common.missing");
}

export function runtimeBadgeValue(data: unknown, t: TranslateFn): string {
  if (!data || typeof data !== "object") {
    return t("workflowControl.common.auto");
  }
  const runtime = (data as { runtime?: { services?: unknown } }).runtime;
  const services = Array.isArray(runtime?.services)
    ? runtime.services.filter(
        (service) => typeof service === "string" && service.trim().length > 0
      )
    : [];
  if (services.length === 0) return t("workflowControl.common.auto");
  if (services.length === 1) return String(services[0]);
  return t("workflowControl.canvas.servicesCount", { count: services.length });
}

export function resolveConnectionReasonText(
  reasonCode: ConnectionValidationReasonCode | undefined,
  reasonDetail: string | undefined,
  t: TranslateFn
): string {
  if (!reasonCode) {
    return t("workflowControl.common.unknown");
  }
  const key = `workflowControl.messages.${reasonCode}`;
  const translated = t(key);
  if (translated !== key) {
    return translated;
  }
  return reasonDetail || reasonCode;
}
