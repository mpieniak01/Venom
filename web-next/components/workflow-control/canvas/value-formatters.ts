import type { ConnectionValidationReasonCode } from "@/lib/workflow-policy";

export type TranslateFn = (
  path: string,
  replacements?: Record<string, string | number>
) => string;

type SourceTagData = { sourceTag?: unknown };
type RuntimeData = { runtime?: { services?: unknown } };

export function readSourceTag(data: SourceTagData | null | undefined): "local" | "cloud" {
  if (!data) {
    return "local";
  }
  const sourceTag = data.sourceTag;
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

export function runtimeBadgeValue(data: RuntimeData | null | undefined, t: TranslateFn): string {
  if (!data) {
    return t("workflowControl.common.auto");
  }
  const runtime = data.runtime;
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
    return reasonDetail ? `${translated}: ${reasonDetail}` : translated;
  }
  return reasonDetail || reasonCode;
}
