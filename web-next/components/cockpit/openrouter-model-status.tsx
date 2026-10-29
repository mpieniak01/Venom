"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import { useTranslation } from "@/lib/i18n";
import { moneyText, type OpenRouterCatalog, type OpenRouterStatus } from "@/lib/openrouter-chat";

export function useOpenRouterCatalog(enabled: boolean) {
  const [result, setResult] = useState<{status: OpenRouterStatus; catalog: OpenRouterCatalog} | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void Promise.all([
      apiFetch<OpenRouterStatus>("/api/v1/openrouter/status", {signal: controller.signal}),
      apiFetch<OpenRouterCatalog>("/api/v1/openrouter/catalog", {signal: controller.signal}),
    ]).then(([status, catalog]) => {
      if (!controller.signal.aborted) { setResult({status, catalog}); setFailed(false); }
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [enabled]);
  return {result: enabled ? result : null, failed: enabled && failed};
}

export function OpenRouterModelStatus({selection, model}: Readonly<{
  selection: ReturnType<typeof useOpenRouterCatalog>; model: string;
}>) {
  const t = useTranslation();
  const {result, failed} = selection;
  if (failed) return <p role="alert">{t("cockpit.openrouter.unavailable")}</p>;
  if (!result) return <p>{t("cockpit.openrouter.loading")}</p>;
  const selected = result.catalog.models.find(item => item.id === model);
  const authentication = result.status.authenticated === null ? "unknown" : String(result.status.authenticated);
  const exact = (value: unknown) => moneyText(value) ?? t("cockpit.openrouter.unknown");
  return <section className="space-y-2 text-xs" data-testid="openrouter-model-status" aria-label={t("cockpit.openrouter.title")}>
    <p>{t("cockpit.openrouter.directOnly")}</p>
    <p>{t(result.status.configured ? "cockpit.openrouter.configured" : "cockpit.openrouter.notConfigured")} · {t("cockpit.openrouter.authentication." + authentication)}</p>
    {!result.status.available && <p role="status">{t("cockpit.openrouter.unavailable")}</p>}
    {selected && <>
      <p>{t("cockpit.openrouter.prices", {input: exact(selected.input_price_per_million), output: exact(selected.output_price_per_million)})}</p>
      <p>{t("cockpit.openrouter.requestPrice", {price: exact(selected.request_price)})}</p>
      <p>{t("cockpit.openrouter.limits", {context: selected.context_length, output: selected.max_output_tokens})}</p>
      <p>{t("cockpit.openrouter.pricingDate", {date: selected.pricing_as_of || result.catalog.pricing_as_of || t("cockpit.openrouter.unknown")})}</p>
    </>}
    <p>{t("cockpit.openrouter.costNotice")}</p>
  </section>;
}
